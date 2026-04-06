package storagenode.storage;

import storagenode.crypto.HashUtil;

import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
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

    private final Path dataDir;   // permanent storage
    private final Path tempDir;   // in-progress uploads
    private final int chunkSize;

    public FileStore(Path dataDir, Path tempDir, int chunkSize) throws IOException {
        this.dataDir = dataDir;
        this.tempDir = tempDir;
        this.chunkSize = chunkSize;
        Files.createDirectories(dataDir);
        Files.createDirectories(tempDir);
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

    /**
     * Assemble all chunks into a single file, verify SHA-256, and move
     * to permanent storage.
     *
     * @return the final storage path if hash matches, null if mismatch
     */
    public Path assembleAndStore(String sessionId, int totalChunks, String expectedSha256)
            throws IOException {

        Path sessionDir = tempDir.resolve(sessionId);
        Path assembledFile = sessionDir.resolve("assembled");

        // 1. Concatenate chunks in order
        try (OutputStream out = new BufferedOutputStream(Files.newOutputStream(assembledFile))) {
            for (int i = 0; i < totalChunks; i++) {
                Path chunkFile = sessionDir.resolve("chunk_" + i);
                if (!Files.exists(chunkFile)) {
                    throw new IOException("Missing chunk " + i + " for session " + sessionId);
                }
                Files.copy(chunkFile, out);
            }
        }

        // 2. Verify whole-file hash
        String actualHash = HashUtil.sha256File(assembledFile);
        if (!actualHash.equalsIgnoreCase(expectedSha256)) {
            LOG.warning("Hash mismatch for session " + sessionId +
                        ": expected=" + expectedSha256 + " actual=" + actualHash);
            Files.deleteIfExists(assembledFile);
            return null;
        }

        // 3. Move to permanent content-addressed storage
        Path storePath = getStorePath(expectedSha256);
        Files.createDirectories(storePath.getParent());

        if (Files.exists(storePath)) {
            // Dedup: file already exists with same hash
            LOG.info("Dedup hit: file already exists at " + storePath);
        } else {
            Files.move(assembledFile, storePath, StandardCopyOption.ATOMIC_MOVE);
        }

        // 4. Clean up temp directory
        cleanSessionDir(sessionId);

        LOG.info("File stored: " + storePath + " (sha256=" + expectedSha256 + ")");
        return storePath;
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
}
