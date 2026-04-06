package storagenode.monitor;

import storagenode.session.SessionManager;
import storagenode.session.UploadSession;
import storagenode.session.DownloadSession;
import storagenode.storage.DedupStore;
import storagenode.storage.FileStore;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Timer;
import java.util.TimerTask;
import java.util.logging.Logger;

/**
 * Periodically logs storage node statistics and cleans expired sessions.
 *
 * Logs:
 *   - Active upload/download session counts
 *   - Upload progress per session
 *   - Disk usage
 *   - Dedup store size
 *   - Chunk error counts
 */
public class StorageMonitor {

    private static final Logger LOG = Logger.getLogger(StorageMonitor.class.getName());

    private final SessionManager sessionManager;
    private final FileStore fileStore;
    private final DedupStore dedupStore;
    private final Timer timer;

    private long totalChunksReceived = 0;
    private long totalChunkErrors = 0;
    private long totalBytesReceived = 0;
    private long totalBytesServed = 0;
    private long totalUploadsCompleted = 0;
    private long totalDownloadsCompleted = 0;

    public StorageMonitor(SessionManager sessionManager, FileStore fileStore, DedupStore dedupStore) {
        this.sessionManager = sessionManager;
        this.fileStore = fileStore;
        this.dedupStore = dedupStore;
        this.timer = new Timer("StorageMonitor", true);
    }

    /** Start periodic monitoring (every intervalSeconds). */
    public void start(int intervalSeconds) {
        // Stats logging task
        timer.scheduleAtFixedRate(new TimerTask() {
            @Override
            public void run() {
                logStats();
            }
        }, intervalSeconds * 1000L, intervalSeconds * 1000L);

        // Session cleanup task (every 5 minutes)
        timer.scheduleAtFixedRate(new TimerTask() {
            @Override
            public void run() {
                int cleaned = sessionManager.cleanExpiredSessions();
                if (cleaned > 0) {
                    LOG.info("Cleaned " + cleaned + " expired sessions");
                }
            }
        }, 300_000L, 300_000L);

        LOG.info("Storage monitor started (interval=" + intervalSeconds + "s)");
    }

    /** Stop the monitor. */
    public void stop() {
        timer.cancel();
    }

    /** Log current statistics. */
    public void logStats() {
        int uploads = sessionManager.getActiveUploadCount();
        int downloads = sessionManager.getActiveDownloadCount();

        StringBuilder sb = new StringBuilder();
        sb.append("\n┌─── Storage Node Stats ───────────────────────┐\n");
        sb.append("│ Active uploads  : ").append(uploads).append("\n");
        sb.append("│ Active downloads: ").append(downloads).append("\n");
        sb.append("│ Dedup entries   : ").append(dedupStore.size()).append("\n");
        sb.append("│ Total chunks rx : ").append(totalChunksReceived).append("\n");
        sb.append("│ Chunk errors    : ").append(totalChunkErrors).append("\n");
        sb.append("│ Uploads done    : ").append(totalUploadsCompleted).append("\n");
        sb.append("│ Downloads done  : ").append(totalDownloadsCompleted).append("\n");

        // Disk usage
        try {
            Path dataDir = fileStore.getDataDir();
            if (Files.exists(dataDir)) {
                long usedBytes = calculateDirSize(dataDir);
                sb.append("│ Disk used (data): ").append(formatBytes(usedBytes)).append("\n");
            }
        } catch (IOException e) {
            sb.append("│ Disk used: (error)\n");
        }

        // Per-session progress
        for (UploadSession s : sessionManager.getAllUploadSessions()) {
            sb.append("│  ↑ ").append(s.getSessionId().substring(0, 8)).append("... ")
              .append(s.getReceivedCount()).append("/").append(s.getTotalChunks())
              .append(" (").append(s.getProgressPercent()).append("%)")
              .append(" [").append(s.getStatus()).append("]\n");
        }
        for (DownloadSession s : sessionManager.getAllDownloadSessions()) {
            sb.append("│  ↓ ").append(s.getSessionId().substring(0, 8)).append("... ")
              .append(s.getSentCount()).append("/").append(s.getTotalChunks())
              .append(" (").append(s.getProgressPercent()).append("%)")
              .append(" [").append(s.getStatus()).append("]\n");
        }

        sb.append("└───────────────────────────────────────────────┘");
        LOG.info(sb.toString());
    }

    // ── Counters (called from ClientHandler) ──

    public void recordChunkReceived(int bytes) {
        totalChunksReceived++;
        totalBytesReceived += bytes;
    }

    public void recordChunkError() {
        totalChunkErrors++;
    }

    public void recordUploadComplete() {
        totalUploadsCompleted++;
    }

    public void recordDownloadComplete() {
        totalDownloadsCompleted++;
    }

    public void recordBytesServed(int bytes) {
        totalBytesServed += bytes;
    }

    // ── Helpers ──

    private long calculateDirSize(Path dir) throws IOException {
        return Files.walk(dir)
                .filter(Files::isRegularFile)
                .mapToLong(p -> {
                    try { return Files.size(p); }
                    catch (IOException e) { return 0; }
                })
                .sum();
    }

    private String formatBytes(long bytes) {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return String.format("%.1f KB", bytes / 1024.0);
        if (bytes < 1024 * 1024 * 1024) return String.format("%.1f MB", bytes / (1024.0 * 1024));
        return String.format("%.2f GB", bytes / (1024.0 * 1024 * 1024));
    }
}
