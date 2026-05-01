package storagenode.config;

import java.io.FileInputStream;
import java.io.IOException;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Properties;

public class NodeConfig {

    private final Properties props;

    // Network
    private final String host;
    private final int port;
    private final String nodeId;
    private final String advertisedHost;
    private final int advertisedPort;
    private final String storageAddress;

    // Storage paths
    private final Path dataDir;
    private final Path tempDir;
    private final Path metaDir;
    private final Path quarantineDir;

    // Chunk
    private final int chunkSize;

    // Coordinator
    private final String coordinatorHost;
    private final int coordinatorPort;

    // Security
    private final String ticketSecret;
    private final int rsaKeySize;
    private final int aesKeySize;

    // Sessions
    private final int uploadTimeoutMinutes;
    private final int downloadTimeoutMinutes;

    // Thread pool
    private final int threadPoolSize;

    // Logging
    private final String logLevel;
    private final Path logDir;

    // Antivirus
    private final boolean antivirusEnabled;
    private final String antivirusHost;
    private final int antivirusPort;
    private final int antivirusTimeoutMs;
    private final boolean antivirusFailClosed;

    public NodeConfig(String configFile) throws IOException {
        props = new Properties();
        try (FileInputStream fis = new FileInputStream(configFile)) {
            props.load(fis);
        }

        this.host = getString("node.host", "0.0.0.0", "NODE_HOST");
        this.port = getInt("node.port", 9001, "NODE_PORT");
        this.nodeId = getString("node.id", "node-1", "NODE_ID");
        this.advertisedHost = getString("node.advertised.host", this.nodeId, "NODE_ADVERTISED_HOST");
        this.advertisedPort = getInt("node.advertised.port", this.port, "NODE_ADVERTISED_PORT");
        this.storageAddress = getString(
                "node.storage.address",
                this.advertisedHost + ":" + this.advertisedPort,
                "NODE_STORAGE_ADDRESS"
        );

        this.dataDir = Paths.get(getString("storage.data.dir", "data/store", "STORAGE_DATA_DIR"));
        this.tempDir = Paths.get(getString("storage.temp.dir", "data/temp", "STORAGE_TEMP_DIR"));
        this.metaDir = Paths.get(getString("storage.meta.dir", "data/meta", "STORAGE_META_DIR"));
        this.quarantineDir = Paths.get(getString(
                "antivirus.quarantine.dir", "data/quarantine", "ANTIVIRUS_QUARANTINE_DIR"
        ));

        this.chunkSize = getInt("chunk.size", 524288, "CHUNK_SIZE");

        this.coordinatorHost = getString("coordinator.host", "127.0.0.1", "COORDINATOR_HOST");
        this.coordinatorPort = getInt("coordinator.port", 8000, "COORDINATOR_PORT");

        this.ticketSecret = getString("ticket.secret", "default_secret", "TICKET_SECRET");
        this.rsaKeySize = getInt("rsa.keysize", 2048, "RSA_KEY_SIZE");
        this.aesKeySize = getInt("aes.keysize", 256, "AES_KEY_SIZE");

        this.uploadTimeoutMinutes = getInt("session.upload.timeout.minutes", 60, "UPLOAD_TIMEOUT_MINUTES");
        this.downloadTimeoutMinutes = getInt("session.download.timeout.minutes", 30, "DOWNLOAD_TIMEOUT_MINUTES");

        this.threadPoolSize = getInt("server.thread.pool.size", 50, "SERVER_THREAD_POOL_SIZE");

        this.logLevel = getString("log.level", "INFO", "LOG_LEVEL");
        this.logDir = Paths.get(getString("log.dir", "logs", "LOG_DIR"));

        this.antivirusEnabled = getBoolean("antivirus.enabled", true, "ANTIVIRUS_ENABLED");
        this.antivirusHost = getString("antivirus.host", "127.0.0.1", "ANTIVIRUS_HOST");
        this.antivirusPort = getInt("antivirus.port", 3310, "ANTIVIRUS_PORT");
        this.antivirusTimeoutMs = getInt("antivirus.timeout.ms", 30000, "ANTIVIRUS_TIMEOUT_MS");
        this.antivirusFailClosed = getBoolean("antivirus.fail.closed", true, "ANTIVIRUS_FAIL_CLOSED");
    }

    private String getString(String key, String defaultValue, String envKey) {
        String envValue = System.getenv(envKey);
        if (envValue != null && !envValue.trim().isEmpty()) {
            return envValue.trim();
        }
        return props.getProperty(key, defaultValue);
    }

    private int getInt(String key, int defaultValue, String envKey) {
        return Integer.parseInt(getString(key, String.valueOf(defaultValue), envKey));
    }

    private boolean getBoolean(String key, boolean defaultValue, String envKey) {
        return Boolean.parseBoolean(getString(key, String.valueOf(defaultValue), envKey));
    }

    public String getHost() { return host; }
    public int getPort() { return port; }
    public String getNodeId() { return nodeId; }
    public String getAdvertisedHost() { return advertisedHost; }
    public int getAdvertisedPort() { return advertisedPort; }
    public String getStorageAddress() { return storageAddress; }
    public Path getDataDir() { return dataDir; }
    public Path getTempDir() { return tempDir; }
    public Path getMetaDir() { return metaDir; }
    public Path getQuarantineDir() { return quarantineDir; }
    public int getChunkSize() { return chunkSize; }
    public String getCoordinatorHost() { return coordinatorHost; }
    public int getCoordinatorPort() { return coordinatorPort; }
    public String getTicketSecret() { return ticketSecret; }
    public int getRsaKeySize() { return rsaKeySize; }
    public int getAesKeySize() { return aesKeySize; }
    public int getUploadTimeoutMinutes() { return uploadTimeoutMinutes; }
    public int getDownloadTimeoutMinutes() { return downloadTimeoutMinutes; }
    public int getThreadPoolSize() { return threadPoolSize; }
    public String getLogLevel() { return logLevel; }
    public Path getLogDir() { return logDir; }
    public boolean isAntivirusEnabled() { return antivirusEnabled; }
    public String getAntivirusHost() { return antivirusHost; }
    public int getAntivirusPort() { return antivirusPort; }
    public int getAntivirusTimeoutMs() { return antivirusTimeoutMs; }
    public boolean isAntivirusFailClosed() { return antivirusFailClosed; }
}
