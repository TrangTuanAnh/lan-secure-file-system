package storagenode.session;

import java.time.Instant;
import java.util.*;

/**
 * Tracks the state of an in-progress upload.
 *
 * The upload session is created when the client sends OPEN_UPLOAD with a valid ticket.
 * Chunks are received one by one; on FINALIZE_UPLOAD the file is assembled and verified.
 *
 * Status lifecycle: INIT -> UPLOADING -> FINALIZING -> COMPLETED / FAILED
 */
public class UploadSession {

    public enum Status {
        INIT, UPLOADING, PAUSED, FINALIZING, COMPLETED, FAILED
    }

    private final String sessionId;
    private final String fileId;
    private final String fileName;
    private final String sha256Whole;     // expected whole-file hash
    private final long fileSize;
    private final int totalChunks;
    private final int chunkSize;
    private final String uploaderId;

    private volatile Status status;
    private final BitSet receivedChunks;
    private final Map<Integer, String> chunkHashes;  // chunkIndex -> sha256
    private final Instant createdAt;
    private volatile Instant lastActivity;

    public UploadSession(String sessionId, String fileId, String fileName,
                         String sha256Whole, long fileSize, int totalChunks,
                         int chunkSize, String uploaderId) {
        this.sessionId = sessionId;
        this.fileId = fileId;
        this.fileName = fileName;
        this.sha256Whole = sha256Whole;
        this.fileSize = fileSize;
        this.totalChunks = totalChunks;
        this.chunkSize = chunkSize;
        this.uploaderId = uploaderId;

        this.status = Status.INIT;
        this.receivedChunks = new BitSet(totalChunks);
        this.chunkHashes = new HashMap<>();
        this.createdAt = Instant.now();
        this.lastActivity = Instant.now();
    }

    /** Mark a chunk as received, recording its hash. */
    public synchronized void markChunkReceived(int chunkIndex, String chunkHash) {
        if (!isValidChunkIndex(chunkIndex)) {
            throw new IllegalArgumentException("Chunk index out of range: " + chunkIndex);
        }
        receivedChunks.set(chunkIndex);
        chunkHashes.put(chunkIndex, chunkHash);
        lastActivity = Instant.now();
        if (status == Status.INIT) {
            status = Status.UPLOADING;
        }
    }

    /** Check if a specific chunk has been received. */
    public boolean hasChunk(int chunkIndex) {
        if (!isValidChunkIndex(chunkIndex)) {
            return false;
        }
        return receivedChunks.get(chunkIndex);
    }

    /** Check if all chunks have been received. */
    public boolean isComplete() {
        return receivedChunks.cardinality() == totalChunks;
    }

    /** Atomically move a complete active session into finalization. */
    public synchronized boolean tryBeginFinalizing() {
        if (status == Status.FINALIZING || status == Status.COMPLETED || status == Status.FAILED) {
            return false;
        }
        status = Status.FINALIZING;
        lastActivity = Instant.now();
        return true;
    }

    /** Get the list of missing chunk indices. */
    public List<Integer> getMissingChunks() {
        List<Integer> missing = new ArrayList<>();
        for (int i = 0; i < totalChunks; i++) {
            if (!receivedChunks.get(i)) {
                missing.add(i);
            }
        }
        return missing;
    }

    /** Number of chunks received so far. */
    public int getReceivedCount() {
        return receivedChunks.cardinality();
    }

    /** Progress as a percentage (0-100). */
    public int getProgressPercent() {
        if (totalChunks == 0) return 100;
        return (int) ((receivedChunks.cardinality() * 100L) / totalChunks);
    }

    /** Whether the chunk index is valid for this upload session. */
    public boolean isValidChunkIndex(int chunkIndex) {
        return chunkIndex >= 0 && chunkIndex < totalChunks;
    }

    /**
     * Expected size (bytes) for a specific chunk index.
     * Non-last chunks must be exactly chunkSize, last chunk can be smaller.
     */
    public int expectedChunkSize(int chunkIndex) {
        if (!isValidChunkIndex(chunkIndex)) {
            throw new IllegalArgumentException("Chunk index out of range: " + chunkIndex);
        }
        if (chunkIndex < totalChunks - 1) {
            return chunkSize;
        }
        long lastChunk = fileSize - ((long) (totalChunks - 1) * chunkSize);
        return (int) (lastChunk > 0 ? lastChunk : chunkSize);
    }

    // ── Getters & Setters ──

    public String getSessionId() { return sessionId; }
    public String getFileId() { return fileId; }
    public String getFileName() { return fileName; }
    public String getSha256Whole() { return sha256Whole; }
    public long getFileSize() { return fileSize; }
    public int getTotalChunks() { return totalChunks; }
    public int getChunkSize() { return chunkSize; }
    public String getUploaderId() { return uploaderId; }
    public Status getStatus() { return status; }
    public void setStatus(Status status) { this.status = status; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getLastActivity() { return lastActivity; }
    public Map<Integer, String> getChunkHashes() { return Collections.unmodifiableMap(chunkHashes); }

    /** Convert to a Properties object for disk persistence. */
    public Properties toProperties() {
        Properties p = new Properties();
        p.setProperty("sessionId", sessionId);
        p.setProperty("fileId", fileId);
        p.setProperty("fileName", fileName);
        p.setProperty("sha256Whole", sha256Whole);
        p.setProperty("fileSize", String.valueOf(fileSize));
        p.setProperty("totalChunks", String.valueOf(totalChunks));
        p.setProperty("chunkSize", String.valueOf(chunkSize));
        p.setProperty("uploaderId", uploaderId);
        p.setProperty("status", status.name());
        p.setProperty("createdAt", createdAt.toString());
        return p;
    }

    /** Reconstruct session from persisted properties (chunks are re-scanned from disk). */
    public static UploadSession fromProperties(Properties p) {
        UploadSession s = new UploadSession(
            p.getProperty("sessionId"),
            p.getProperty("fileId"),
            p.getProperty("fileName"),
            p.getProperty("sha256Whole"),
            Long.parseLong(p.getProperty("fileSize")),
            Integer.parseInt(p.getProperty("totalChunks")),
            Integer.parseInt(p.getProperty("chunkSize")),
            p.getProperty("uploaderId")
        );
        s.status = Status.valueOf(p.getProperty("status", "INIT"));
        return s;
    }
}
