package storagenode.storage;

import com.google.gson.Gson;
import storagenode.antivirus.ScanResult;
import storagenode.crypto.HashUtil;
import storagenode.session.UploadSession;

import java.io.*;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import java.util.logging.Logger;

/**
 * Manages physical file storage on disk.
 *
 * Directory layout:
 *   data/temp/{sessionId}/         – chunks being uploaded
 *   data/temp/{sessionId}/meta.properties  – session metadata on disk
 *   data/temp/{sessionId}/chunk_0
 *   data/temp/{sessionId}/chunk_1
 *   ...
 *   data/store/{sha256[0:2]}/{sha256}  – completed files (content-addressed)
 *
 * The 2-char prefix subdirectory avoids too many entries in one directory.
 */
public class FileStore {

    private static final Logger LOG = Logger.getLogger(FileStore.class.getName());
    private static final Gson GSON = new Gson();

    private final Path dataDir;   // permanent storage
    private final Path tempDir;   // in-progress uploads
    private final Path quarantineDir; // blocked infected uploads
    private final int chunkSize;

    public FileStore(Path dataDir, Path tempDir, int chunkSize) throws IOException {
        this(dataDir, tempDir, defaultQuarantineDir(dataDir), chunkSize);
    }

    public FileStore(Path dataDir, Path tempDir, Path quarantineDir, int chunkSize) throws IOException {
        this.dataDir = dataDir;
        this.tempDir = tempDir;
        this.quarantineDir = quarantineDir;
        this.chunkSize = chunkSize;
        Files.createDirectories(dataDir);
        Files.createDirectories(tempDir);
        Files.createDirectories(quarantineDir);
    }

    // ═══════════════════════ TEMP (upload in-progress) ═══════════════════════

    /** Create a temp directory for a new upload session. */
    public Path createSessionDir(String sessionId) throws IOException {
        Path dir = tempDir.resolve(sessionId);
        Files.createDirectories(dir);
        return dir;
    }

    /** Write a chunk to the session's temp directory. */
    public void writeChunk(String sessionId, int chunkIndex, byte[] data) throws IOException {
        Path dir = tempDir.resolve(sessionId);
        Path chunkFile = dir.resolve("chunk_" + chunkIndex);
        Files.write(chunkFile, data);
    }

    /** Read a chunk from the session's temp directory. */
    public byte[] readTempChunk(String sessionId, int chunkIndex) throws IOException {
        Path chunkFile = tempDir.resolve(sessionId).resolve("chunk_" + chunkIndex);
        return Files.readAllBytes(chunkFile);
    }

    /** Check which chunks exist for a session. */
    public Set<Integer> getReceivedChunks(String sessionId) throws IOException {
        Path dir = tempDir.resolve(sessionId);
        Set<Integer> received = new TreeSet<>();
        if (!Files.exists(dir)) return received;

        try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir, "chunk_*")) {
            for (Path p : stream) {
                String name = p.getFileName().toString();
                String idx = name.substring("chunk_".length());
                try {
                    received.add(Integer.parseInt(idx));
                } catch (NumberFormatException ignored) {}
            }
        }
        return received;
    }

    /** Save session metadata to disk (for crash recovery). */
    public void saveSessionMeta(String sessionId, Properties meta) throws IOException {
        Path metaFile = tempDir.resolve(sessionId).resolve("meta.properties");
        try (OutputStream os = Files.newOutputStream(metaFile)) {
            meta.store(os, "Upload session metadata");
        }
    }

    /** Load session metadata from disk. */
    public Properties loadSessionMeta(String sessionId) throws IOException {
        Path metaFile = tempDir.resolve(sessionId).resolve("meta.properties");
        Properties meta = new Properties();
        if (Files.exists(metaFile)) {
            try (InputStream is = Files.newInputStream(metaFile)) {
                meta.load(is);
            }
        }
        return meta;
    }

    // ═══════════════════════ ASSEMBLE & FINALIZE ═══════════════════════

    /** Assemble all chunks into a single temporary file for final validation. */
    public Path assembleTempFile(String sessionId, int totalChunks) throws IOException {
        Path sessionDir = tempDir.resolve(sessionId);
        Path assembledFile = sessionDir.resolve("assembled");

        try (OutputStream out = new BufferedOutputStream(Files.newOutputStream(assembledFile))) {
            for (int i = 0; i < totalChunks; i++) {
                Path chunkFile = sessionDir.resolve("chunk_" + i);
                if (!Files.exists(chunkFile)) {
                    throw new IOException("Missing chunk " + i + " for session " + sessionId);
                }
                Files.copy(chunkFile, out);
            }
        }
        return assembledFile;
    }

    /** Verify the assembled file SHA-256 and delete it on mismatch. */
    public boolean verifyAssembledHash(Path assembledFile, String expectedSha256, String sessionId)
            throws IOException {
        String actualHash = HashUtil.sha256File(assembledFile);
        if (!actualHash.equalsIgnoreCase(expectedSha256)) {
            LOG.warning("Hash mismatch for session " + sessionId +
                        ": expected=" + expectedSha256 + " actual=" + actualHash);
            Files.deleteIfExists(assembledFile);
            return false;
        }
        return true;
    }

    /** Move a validated clean assembled file to permanent content-addressed storage. */
    public Path commitAssembledFile(Path assembledFile, String expectedSha256) throws IOException {
        Path storePath = getStorePath(expectedSha256);
        Files.createDirectories(storePath.getParent());

        if (Files.exists(storePath)) {
            // Dedup: file already exists with same hash
            LOG.info("Dedup hit: file already exists at " + storePath);
        } else {
            Files.move(assembledFile, storePath, StandardCopyOption.ATOMIC_MOVE);
        }

        LOG.info("File stored: " + storePath + " (sha256=" + expectedSha256 + ")");
        return storePath;
    }

    /**
     * Assemble all chunks into a single file, verify SHA-256, and move
     * to permanent storage.
     *
     * @return the final storage path if hash matches, null if mismatch
     */
    public Path assembleAndStore(String sessionId, int totalChunks, String expectedSha256)
            throws IOException {

        Path assembledFile = assembleTempFile(sessionId, totalChunks);
        if (!verifyAssembledHash(assembledFile, expectedSha256, sessionId)) {
            return null;
        }

        Path storePath = commitAssembledFile(assembledFile, expectedSha256);
        cleanSessionDir(sessionId);
        return storePath;
    }

    /** Move an infected assembled file into quarantine and write audit metadata beside it. */
    public Path quarantineFile(UploadSession session, Path assembledFile, ScanResult scanResult)
            throws IOException {
        Files.createDirectories(quarantineDir);

        String safeSessionId = sanitizeFileName(session.getSessionId());
        String safeHash = sanitizeFileName(session.getSha256Whole());
        String baseName = safeSessionId + "_" + safeHash;
        Path quarantinePath = quarantineDir.resolve(baseName + ".blocked");
        Path metadataPath = quarantineDir.resolve(baseName + ".metadata.json");

        moveWithAtomicFallback(assembledFile, quarantinePath);

        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("quarantinedAt", Instant.now().toString());
        metadata.put("sessionId", session.getSessionId());
        metadata.put("fileId", session.getFileId());
        metadata.put("fileName", session.getFileName());
        metadata.put("sha256Whole", session.getSha256Whole());
        metadata.put("fileSize", session.getFileSize());
        metadata.put("uploaderId", session.getUploaderId());
        metadata.put("scanStatus", scanResult.getStatus().name());
        metadata.put("threatName", scanResult.getThreatName());
        metadata.put("scanner", scanResult.getScanner());
        metadata.put("scanDurationMs", scanResult.getDurationMs());
        metadata.put("rawResponse", scanResult.getRawResponse());
        metadata.put("quarantinePath", quarantinePath.toString());

        try (Writer writer = Files.newBufferedWriter(metadataPath)) {
            GSON.toJson(metadata, writer);
        }

        LOG.warning("File quarantined: " + quarantinePath + " threat=" + scanResult.getThreatName());
        return quarantinePath;
    }

    /** Delete a session's temp directory and all its contents. */
    public void cleanSessionDir(String sessionId) throws IOException {
        Path dir = tempDir.resolve(sessionId);
        if (Files.exists(dir)) {
            try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir)) {
                for (Path p : stream) {
                    Files.deleteIfExists(p);
                }
            }
            Files.deleteIfExists(dir);
        }
    }

    // ═══════════════════════ PERMANENT STORAGE (download) ═══════════════════════

    /** Get the storage path for a file by its SHA-256 hash. */
    public Path getStorePath(String sha256) {
        String prefix = sha256.substring(0, 2);
        return dataDir.resolve(prefix).resolve(sha256);
    }

    /** Check if a file exists in permanent storage. */
    public boolean fileExists(String sha256) {
        return Files.exists(getStorePath(sha256));
    }

    /** Get the size of a stored file. */
    public long getFileSize(String sha256) throws IOException {
        return Files.size(getStorePath(sha256));
    }

    /**
     * Read a chunk from a stored file for download.
     *
     * @param sha256     file hash
     * @param chunkIndex 0-based index
     * @param chunkSize  chunk size in bytes
     * @return chunk data (may be smaller for the last chunk)
     */
    public byte[] readStoredChunk(String sha256, int chunkIndex, int chunkSize) throws IOException {
        Path filePath = getStorePath(sha256);
        long fileSize = Files.size(filePath);
        long offset = (long) chunkIndex * chunkSize;

        if (offset >= fileSize) {
            throw new IOException("Chunk index " + chunkIndex + " out of range");
        }

        int readLen = (int) Math.min(chunkSize, fileSize - offset);
        byte[] data = new byte[readLen];

        try (RandomAccessFile raf = new RandomAccessFile(filePath.toFile(), "r")) {
            raf.seek(offset);
            raf.readFully(data);
        }
        return data;
    }

    /** Calculate total number of chunks for a file. */
    public int calculateTotalChunks(long fileSize) {
        return (int) Math.ceil((double) fileSize / chunkSize);
    }

    /** List all stored file hashes. */
    public List<String> listStoredFiles() throws IOException {
        List<String> hashes = new ArrayList<>();
        if (!Files.exists(dataDir)) return hashes;

        try (DirectoryStream<Path> prefixDirs = Files.newDirectoryStream(dataDir)) {
            for (Path prefixDir : prefixDirs) {
                if (Files.isDirectory(prefixDir)) {
                    try (DirectoryStream<Path> files = Files.newDirectoryStream(prefixDir)) {
                        for (Path f : files) {
                            hashes.add(f.getFileName().toString());
                        }
                    }
                }
            }
        }
        return hashes;
    }

    public Path getDataDir() { return dataDir; }
    public Path getTempDir() { return tempDir; }
    public Path getQuarantineDir() { return quarantineDir; }

    private static Path defaultQuarantineDir(Path dataDir) {
        Path parent = dataDir.getParent();
        if (parent == null) {
            return Paths.get("data/quarantine");
        }
        return parent.resolve("quarantine");
    }

    private static String sanitizeFileName(String value) {
        if (value == null || value.trim().isEmpty()) {
            return "unknown";
        }
        return value.replaceAll("[^A-Za-z0-9._-]", "_");
    }

    private static void moveWithAtomicFallback(Path source, Path target) throws IOException {
        try {
            Files.move(source, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } catch (AtomicMoveNotSupportedException e) {
            Files.move(source, target, StandardCopyOption.REPLACE_EXISTING);
        }
    }
}
