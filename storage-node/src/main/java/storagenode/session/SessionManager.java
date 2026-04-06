package storagenode.session;

import storagenode.storage.FileStore;

import java.io.IOException;
import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.logging.Logger;

/**
 * Manages all active upload and download sessions.
 *
 * Thread-safe. Sessions are automatically expired after their timeout period.
 * On startup, recovers interrupted upload sessions from disk.
 */
public class SessionManager {

    private static final Logger LOG = Logger.getLogger(SessionManager.class.getName());

    private final ConcurrentHashMap<String, UploadSession> uploadSessions = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, DownloadSession> downloadSessions = new ConcurrentHashMap<>();

    private final FileStore fileStore;
    private final int uploadTimeoutMinutes;
    private final int downloadTimeoutMinutes;

    public SessionManager(FileStore fileStore, int uploadTimeoutMinutes, int downloadTimeoutMinutes) {
        this.fileStore = fileStore;
        this.uploadTimeoutMinutes = uploadTimeoutMinutes;
        this.downloadTimeoutMinutes = downloadTimeoutMinutes;
    }

    // ═══════════════════════ UPLOAD SESSIONS ═══════════════════════

    /** Create and register a new upload session. */
    public UploadSession createUploadSession(String sessionId, String fileId, String fileName,
                                              String sha256Whole, long fileSize,
                                              int totalChunks, int chunkSize, String uploaderId) throws IOException {
        UploadSession session = new UploadSession(
            sessionId, fileId, fileName, sha256Whole,
            fileSize, totalChunks, chunkSize, uploaderId
        );

        // Create temp directory on disk
        fileStore.createSessionDir(sessionId);

        // Persist session metadata
        fileStore.saveSessionMeta(sessionId, session.toProperties());

        uploadSessions.put(sessionId, session);
        LOG.info("Upload session created: " + sessionId +
                 " file=" + fileName + " chunks=" + totalChunks);
        return session;
    }

    /** Get an active upload session. */
    public UploadSession getUploadSession(String sessionId) {
        return uploadSessions.get(sessionId);
    }

    /** Remove a completed/failed upload session. */
    public void removeUploadSession(String sessionId) {
        uploadSessions.remove(sessionId);
        LOG.info("Upload session removed: " + sessionId);
    }

    /** Get all active upload sessions. */
    public Collection<UploadSession> getAllUploadSessions() {
        return Collections.unmodifiableCollection(uploadSessions.values());
    }

    // ═══════════════════════ DOWNLOAD SESSIONS ═══════════════════════

    /** Create and register a new download session. */
    public DownloadSession createDownloadSession(String sessionId, String fileId,
                                                  String sha256Whole, long fileSize,
                                                  int totalChunks, int chunkSize,
                                                  String downloaderId) {
        java.nio.file.Path filePath = fileStore.getStorePath(sha256Whole);
        DownloadSession session = new DownloadSession(
            sessionId, fileId, sha256Whole, filePath,
            fileSize, totalChunks, chunkSize, downloaderId
        );
        downloadSessions.put(sessionId, session);
        LOG.info("Download session created: " + sessionId + " file=" + sha256Whole);
        return session;
    }

    /** Get an active download session. */
    public DownloadSession getDownloadSession(String sessionId) {
        return downloadSessions.get(sessionId);
    }

    /** Remove a completed/failed download session. */
    public void removeDownloadSession(String sessionId) {
        downloadSessions.remove(sessionId);
    }

    /** Get all active download sessions. */
    public Collection<DownloadSession> getAllDownloadSessions() {
        return Collections.unmodifiableCollection(downloadSessions.values());
    }

    // ═══════════════════════ RECOVERY ═══════════════════════

    /**
     * Recover upload sessions from disk after a restart.
     * Scans the temp directory for session folders with metadata.
     */
    public int recoverSessions() {
        int recovered = 0;
        try {
            java.nio.file.Path tempDir = fileStore.getTempDir();
            if (!java.nio.file.Files.exists(tempDir)) return 0;

            try (java.nio.file.DirectoryStream<java.nio.file.Path> dirs =
                     java.nio.file.Files.newDirectoryStream(tempDir)) {
                for (java.nio.file.Path dir : dirs) {
                    if (!java.nio.file.Files.isDirectory(dir)) continue;
                    String sessionId = dir.getFileName().toString();
                    try {
                        Properties meta = fileStore.loadSessionMeta(sessionId);
                        if (meta.isEmpty()) continue;

                        UploadSession session = UploadSession.fromProperties(meta);

                        // Re-scan disk for received chunks
                        Set<Integer> onDisk = fileStore.getReceivedChunks(sessionId);
                        for (int idx : onDisk) {
                            byte[] chunkData = fileStore.readTempChunk(sessionId, idx);
                            String hash = storagenode.crypto.HashUtil.sha256(chunkData);
                            session.markChunkReceived(idx, hash);
                        }

                        session.setStatus(UploadSession.Status.PAUSED);
                        uploadSessions.put(sessionId, session);
                        recovered++;
                        LOG.info("Recovered upload session: " + sessionId +
                                 " chunks=" + onDisk.size() + "/" + session.getTotalChunks());
                    } catch (Exception e) {
                        LOG.warning("Failed to recover session " + sessionId + ": " + e.getMessage());
                    }
                }
            }
        } catch (IOException e) {
            LOG.warning("Failed to scan temp dir for recovery: " + e.getMessage());
        }
        return recovered;
    }

    // ═══════════════════════ EXPIRY ═══════════════════════

    /** Clean up expired sessions. Call periodically from a timer. */
    public int cleanExpiredSessions() {
        int cleaned = 0;
        Instant now = Instant.now();

        // Upload sessions
        for (Map.Entry<String, UploadSession> entry : uploadSessions.entrySet()) {
            UploadSession s = entry.getValue();
            Duration idle = Duration.between(s.getLastActivity(), now);
            if (idle.toMinutes() > uploadTimeoutMinutes) {
                LOG.info("Expiring upload session: " + s.getSessionId());
                uploadSessions.remove(entry.getKey());
                try {
                    fileStore.cleanSessionDir(s.getSessionId());
                } catch (IOException e) {
                    LOG.warning("Failed to clean session dir: " + e.getMessage());
                }
                cleaned++;
            }
        }

        // Download sessions
        for (Map.Entry<String, DownloadSession> entry : downloadSessions.entrySet()) {
            DownloadSession s = entry.getValue();
            Duration idle = Duration.between(s.getLastActivity(), now);
            if (idle.toMinutes() > downloadTimeoutMinutes) {
                LOG.info("Expiring download session: " + s.getSessionId());
                downloadSessions.remove(entry.getKey());
                cleaned++;
            }
        }

        return cleaned;
    }

    // ═══════════════════════ STATS ═══════════════════════

    public int getActiveUploadCount() { return uploadSessions.size(); }
    public int getActiveDownloadCount() { return downloadSessions.size(); }
}
