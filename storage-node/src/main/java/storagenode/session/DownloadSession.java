package storagenode.session;

import java.nio.file.Path;
import java.time.Instant;
import java.util.BitSet;

/**
 * Tracks the state of an in-progress download.
 *
 * Created when client sends OPEN_DOWNLOAD with a valid ticket.
 * The node reads the stored file in chunks and sends them to the client.
 */
public class DownloadSession {

    public enum Status {
        INIT, DOWNLOADING, COMPLETED, FAILED
    }

    private final String sessionId;
    private final String fileId;
    private final String sha256Whole;
    private final Path filePath;
    private final long fileSize;
    private final int totalChunks;
    private final int chunkSize;
    private final String downloaderId;

    private volatile Status status;
    private volatile int lastSentChunk;
    private final BitSet sentChunks;
    private final Instant createdAt;
    private volatile Instant lastActivity;

    public DownloadSession(String sessionId, String fileId, String sha256Whole,
                           Path filePath, long fileSize, int totalChunks,
                           int chunkSize, String downloaderId) {
        this.sessionId = sessionId;
        this.fileId = fileId;
        this.sha256Whole = sha256Whole;
        this.filePath = filePath;
        this.fileSize = fileSize;
        this.totalChunks = totalChunks;
        this.chunkSize = chunkSize;
        this.downloaderId = downloaderId;

        this.status = Status.INIT;
        this.lastSentChunk = -1;
        this.sentChunks = new BitSet(totalChunks);
        this.createdAt = Instant.now();
        this.lastActivity = Instant.now();
    }

    /** Mark a chunk as sent. */
    public synchronized void markChunkSent(int chunkIndex) {
        if (chunkIndex < 0 || chunkIndex >= totalChunks) {
            throw new IllegalArgumentException("Chunk index out of range: " + chunkIndex);
        }
        this.lastSentChunk = chunkIndex;
        this.sentChunks.set(chunkIndex);
        this.lastActivity = Instant.now();
        if (status == Status.INIT) {
            status = Status.DOWNLOADING;
        }
    }

    /** Check if all chunks have been sent. */
    public synchronized boolean isComplete() {
        return sentChunks.cardinality() == totalChunks;
    }

    /** Progress as a percentage. */
    public synchronized int getProgressPercent() {
        if (totalChunks == 0) return 100;
        return (int) ((sentChunks.cardinality() * 100L) / totalChunks);
    }

    public boolean isValidChunkIndex(int chunkIndex) {
        return chunkIndex >= 0 && chunkIndex < totalChunks;
    }

    public synchronized int getSentCount() {
        return sentChunks.cardinality();
    }

    // ── Getters & Setters ──

    public String getSessionId() { return sessionId; }
    public String getFileId() { return fileId; }
    public String getSha256Whole() { return sha256Whole; }
    public Path getFilePath() { return filePath; }
    public long getFileSize() { return fileSize; }
    public int getTotalChunks() { return totalChunks; }
    public int getChunkSize() { return chunkSize; }
    public String getDownloaderId() { return downloaderId; }
    public Status getStatus() { return status; }
    public void setStatus(Status status) { this.status = status; }
    public int getLastSentChunk() { return lastSentChunk; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getLastActivity() { return lastActivity; }
}
