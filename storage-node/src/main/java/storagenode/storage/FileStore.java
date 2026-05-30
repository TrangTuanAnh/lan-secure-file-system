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
import java.util.regex.Pattern;

/**
 * Quản lý nhập/xuất file thật trên ổ đĩa của nút lưu trữ.
 *
 * Cấu trúc thư mục:
 *   data/temp/{sessionId}/         - nơi lưu tạm các khối đang tải lên
 *   data/temp/{sessionId}/meta.properties  - siêu dữ liệu để phục hồi phiên tải lên
 *   data/temp/{sessionId}/chunk_0
 *   data/temp/{sessionId}/chunk_1
 *   ...
 *   data/store/{sha256[0:2]}/{sha256}  - nơi lưu file đã hoàn tất theo hash
 *
 * Thư mục con 2 ký tự đầu của hash giúp tránh quá nhiều file trong một thư mục.
 */
public class FileStore {

    private static final Logger LOG = Logger.getLogger(FileStore.class.getName());
    private static final Gson GSON = new Gson();

    // Chỉ chấp nhận định danh an toàn để tránh tấn công đi ngược đường dẫn.
    // Ví dụ không cho sessionId chứa "../" để ghi file ra ngoài thư mục dự kiến.
    private static final Pattern UUID_LIKE = Pattern.compile(
            "^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$");
    private static final Pattern SHA256_HEX = Pattern.compile(
            "^[0-9a-fA-F]{64}$");

    /** Kiểm tra sessionId có an toàn để dùng làm tên thư mục không. */
    public static void validateSessionId(String sessionId) {
        if (sessionId == null || sessionId.isEmpty()) {
            throw new IllegalArgumentException("sessionId is required");
        }
        if (sessionId.contains("/") || sessionId.contains("\\") || sessionId.contains("..")) {
            throw new IllegalArgumentException("sessionId contains path traversal characters");
        }
        if (!UUID_LIKE.matcher(sessionId).matches()) {
            throw new IllegalArgumentException("sessionId has invalid format: " + sessionId);
        }
    }

    /** Kiểm tra sha256 có đúng 64 ký tự hệ hex không. */
    public static void validateSha256(String sha256) {
        if (sha256 == null || !SHA256_HEX.matcher(sha256).matches()) {
            throw new IllegalArgumentException("sha256 must be 64 hex chars, got: " + sha256);
        }
    }

    // Thư mục lưu file đã hoàn tất.
    private final Path dataDir;
    // Thư mục lưu các khối đang tải lên.
    private final Path tempDir;
    // Thư mục cách ly file bị antivirus từ chối.
    private final Path quarantineDir;
    private final int chunkSize;

    public FileStore(Path dataDir, Path tempDir, int chunkSize) throws IOException {
        this(dataDir, tempDir, defaultQuarantineDir(dataDir), chunkSize);
    }

    public FileStore(Path dataDir, Path tempDir, Path quarantineDir, int chunkSize) throws IOException {
        this.dataDir = dataDir;
        this.tempDir = tempDir;
        this.quarantineDir = quarantineDir;
        this.chunkSize = chunkSize;
        // Tạo sẵn các thư mục nhập/xuất nếu chưa tồn tại.
        Files.createDirectories(dataDir);
        Files.createDirectories(tempDir);
        Files.createDirectories(quarantineDir);
    }

    // ═══════════════════════ VÙNG TẠM CHO FILE ĐANG TẢI LÊN ═══════════════════════

    /** Tạo thư mục tạm cho một phiên tải lên mới. */
    public Path createSessionDir(String sessionId) throws IOException {
        validateSessionId(sessionId);
        Path dir = tempDir.resolve(sessionId);
        Files.createDirectories(dir);
        return dir;
    }

    /** Ghi một khối dữ liệu vào thư mục tạm của phiên tải lên. */
    public void writeChunk(String sessionId, int chunkIndex, byte[] data) throws IOException {
        validateSessionId(sessionId);
        if (chunkIndex < 0) {
            throw new IllegalArgumentException("chunkIndex must be >= 0");
        }
        Path dir = tempDir.resolve(sessionId);
        // Mỗi khối được lưu thành một file riêng: chunk_0, chunk_1, ...
        Path chunkFile = dir.resolve("chunk_" + chunkIndex);
        Files.write(chunkFile, data);
    }

    /** Đọc một khối từ thư mục tạm của phiên tải lên. */
    public byte[] readTempChunk(String sessionId, int chunkIndex) throws IOException {
        validateSessionId(sessionId);
        if (chunkIndex < 0) {
            throw new IllegalArgumentException("chunkIndex must be >= 0");
        }
        Path chunkFile = tempDir.resolve(sessionId).resolve("chunk_" + chunkIndex);
        return Files.readAllBytes(chunkFile);
    }

    /** Kiểm tra phiên này đã nhận được những khối nào. */
    public Set<Integer> getReceivedChunks(String sessionId) throws IOException {
        validateSessionId(sessionId);
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

    /** Lưu siêu dữ liệu phiên xuống đĩa để phục hồi nếu nút bị dừng giữa chừng. */
    public void saveSessionMeta(String sessionId, Properties meta) throws IOException {
        validateSessionId(sessionId);
        Path metaFile = tempDir.resolve(sessionId).resolve("meta.properties");
        // Ghi siêu dữ liệu vào meta.properties trong thư mục tạm của phiên.
        try (OutputStream os = Files.newOutputStream(metaFile)) {
            meta.store(os, "Upload session metadata");
        }
    }

    /** Đọc lại siêu dữ liệu phiên từ ổ đĩa khi cần phục hồi tải lên. */
    public Properties loadSessionMeta(String sessionId) throws IOException {
        validateSessionId(sessionId);
        Path metaFile = tempDir.resolve(sessionId).resolve("meta.properties");
        Properties meta = new Properties();
        if (Files.exists(metaFile)) {
            try (InputStream is = Files.newInputStream(metaFile)) {
                meta.load(is);
            }
        }
        return meta;
    }

    // ═══════════════════════ GHÉP KHỐI VÀ HOÀN TẤT FILE ═══════════════════════

    /** Ghép toàn bộ khối thành một file tạm hoàn chỉnh để kiểm tra lần cuối. */
    public Path assembleTempFile(String sessionId, int totalChunks) throws IOException {
        validateSessionId(sessionId);
        Path sessionDir = tempDir.resolve(sessionId);
        Path assembledFile = sessionDir.resolve("assembled");

        try (OutputStream out = new BufferedOutputStream(Files.newOutputStream(assembledFile))) {
            for (int i = 0; i < totalChunks; i++) {
                // Ghép theo đúng thứ tự chunk_0, chunk_1, ... để khôi phục file gốc.
                Path chunkFile = sessionDir.resolve("chunk_" + i);
                if (!Files.exists(chunkFile)) {
                    throw new IOException("Missing chunk " + i + " for session " + sessionId);
                }
                // Sao chép từng khối vào luồng ghi của file đã ghép.
                Files.copy(chunkFile, out);
            }
        }
        return assembledFile;
    }

    /** Kiểm tra SHA-256 của file đã ghép; nếu sai thì xóa file tạm. */
    public boolean verifyAssembledHash(Path assembledFile, String expectedSha256, String sessionId)
            throws IOException {
        validateSha256(expectedSha256);
        String actualHash = HashUtil.sha256File(assembledFile);
        if (!actualHash.equalsIgnoreCase(expectedSha256)) {
            LOG.warning("Hash mismatch for session " + sessionId +
                        ": expected=" + expectedSha256 + " actual=" + actualHash);
            Files.deleteIfExists(assembledFile);
            return false;
        }
        return true;
    }

    /** Chuyển file đã kiểm tra hợp lệ vào kho lưu trữ chính theo hash. */
    public Path commitAssembledFile(Path assembledFile, String expectedSha256) throws IOException {
        validateSha256(expectedSha256);
        Path storePath = getStorePath(expectedSha256);
        Files.createDirectories(storePath.getParent());

        if (Files.exists(storePath)) {
            // Nếu file cùng hash đã tồn tại thì xóa bản vừa ghép để tránh tốn dung lượng.
            LOG.info("Dedup hit: file already exists at " + storePath);
            try {
                Files.deleteIfExists(assembledFile);
            } catch (IOException ignored) {}
        } else {
            // Ưu tiên di chuyển nguyên tử; nếu hệ điều hành không hỗ trợ thì dùng di chuyển thường.
            moveWithAtomicFallback(assembledFile, storePath);
        }

        LOG.info("File stored: " + storePath + " (sha256=" + expectedSha256 + ")");
        return storePath;
    }

    /**
     * Ghép các khối thành một file, kiểm tra SHA-256 rồi chuyển vào kho lưu trữ chính.
     *
     * @return đường dẫn lưu trữ cuối cùng nếu hash khớp; null nếu hash sai
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

    /** Chuyển file nhiễm virus vào khu cách ly và ghi siêu dữ liệu kiểm tra đi kèm. */
    public Path quarantineFile(UploadSession session, Path assembledFile, ScanResult scanResult)
            throws IOException {
        Files.createDirectories(quarantineDir);

        String safeSessionId = sanitizeFileName(session.getSessionId());
        String safeHash = sanitizeFileName(session.getSha256Whole());
        String baseName = safeSessionId + "_" + safeHash;
        Path quarantinePath = quarantineDir.resolve(baseName + ".blocked");
        Path metadataPath = quarantineDir.resolve(baseName + ".metadata.json");

        // Di chuyển file bị chặn vào khu cách ly thay vì lưu vào kho chính.
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

        // Ghi thêm file siêu dữ liệu JSON để biết file bị chặn vì lý do gì.
        try (Writer writer = Files.newBufferedWriter(metadataPath)) {
            GSON.toJson(metadata, writer);
        }

        LOG.warning("File quarantined: " + quarantinePath + " threat=" + scanResult.getThreatName());
        return quarantinePath;
    }

    /** Xóa thư mục tạm của phiên và toàn bộ khối bên trong. */
    public void cleanSessionDir(String sessionId) throws IOException {
        validateSessionId(sessionId);
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

    // ═══════════════════════ KHO LƯU TRỮ CHÍNH CHO TẢI XUỐNG ═══════════════════════

    /** Lấy đường dẫn lưu trữ của file theo SHA-256. */
    public Path getStorePath(String sha256) {
        validateSha256(sha256);
        String prefix = sha256.substring(0, 2);
        return dataDir.resolve(prefix).resolve(sha256);
    }

    /** Kiểm tra file có tồn tại trong kho lưu trữ chính không. */
    public boolean fileExists(String sha256) {
        return Files.exists(getStorePath(sha256));
    }

    /** Lấy kích thước file đã lưu. */
    public long getFileSize(String sha256) throws IOException {
        return Files.size(getStorePath(sha256));
    }

    /**
     * Đọc một khối từ file đã lưu để phục vụ tải xuống.
     *
     * @param sha256     hash của file
     * @param chunkIndex chỉ số khối, bắt đầu từ 0
     * @param chunkSize  kích thước mỗi khối tính bằng byte
     * @return dữ liệu khối; khối cuối có thể nhỏ hơn chunkSize
     */
    public byte[] readStoredChunk(String sha256, int chunkIndex, int chunkSize) throws IOException {
        validateSha256(sha256);
        if (chunkIndex < 0) {
            throw new IOException("chunkIndex must be >= 0");
        }
        Path filePath = getStorePath(sha256);
        long fileSize = Files.size(filePath);
        // Tính vị trí bắt đầu đọc trong file: chunkIndex * chunkSize.
        long offset = (long) chunkIndex * chunkSize;

        if (offset >= fileSize) {
            throw new IOException("Chunk index " + chunkIndex + " out of range");
        }

        int readLen = (int) Math.min(chunkSize, fileSize - offset);
        byte[] data = new byte[readLen];

        try (RandomAccessFile raf = new RandomAccessFile(filePath.toFile(), "r")) {
            // Nhảy thẳng tới vị trí cần đọc, không cần đọc từ đầu file.
            raf.seek(offset);
            raf.readFully(data);
        }
        return data;
    }

    /** Tính tổng số khối của file bằng số nguyên để tránh sai số với file lớn. */
    public int calculateTotalChunks(long fileSize) {
        if (fileSize <= 0) return 0;
        return (int) ((fileSize + chunkSize - 1) / chunkSize);
    }

    /** Liệt kê toàn bộ hash file đang được lưu trong kho chính. */
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
