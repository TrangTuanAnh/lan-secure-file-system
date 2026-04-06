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

    // Storage paths
    private final Path dataDir;
    private final Path tempDir;
    private final Path metaDir;

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

    public NodeConfig(String configFile) throws IOException {
        props = new Properties();
        try (FileInputStream fis = new FileInputStream(configFile)) {
            props.load(fis);
        }

        this.host = props.getProperty("node.host", "0.0.0.0");
        this.port = Integer.parseInt(props.getProperty("node.port", "9001"));
        this.nodeId = props.getProperty("node.id", "node-1");

        this.dataDir = Paths.get(props.getProperty("storage.data.dir", "data/store"));
        this.tempDir = Paths.get(props.getProperty("storage.temp.dir", "data/temp"));
        this.metaDir = Paths.get(props.getProperty("storage.meta.dir", "data/meta"));

        this.chunkSize = Integer.parseInt(props.getProperty("chunk.size", "524288"));

        this.coordinatorHost = props.getProperty("coordinator.host", "127.0.0.1");
        this.coordinatorPort = Integer.parseInt(props.getProperty("coordinator.port", "8000"));

        this.ticketSecret = props.getProperty("ticket.secret", "default_secret");
        this.rsaKeySize = Integer.parseInt(props.getProperty("rsa.keysize", "2048"));
        this.aesKeySize = Integer.parseInt(props.getProperty("aes.keysize", "256"));

        this.uploadTimeoutMinutes = Integer.parseInt(props.getProperty("session.upload.timeout.minutes", "60"));
        this.downloadTimeoutMinutes = Integer.parseInt(props.getProperty("session.download.timeout.minutes", "30"));

        this.threadPoolSize = Integer.parseInt(props.getProperty("server.thread.pool.size", "50"));

        this.logLevel = props.getProperty("log.level", "INFO");
        this.logDir = Paths.get(props.getProperty("log.dir", "logs"));
    }

    public String getHost() { return host; }
    public int getPort() { return port; }
    public String getNodeId() { return nodeId; }
    public Path getDataDir() { return dataDir; }
    public Path getTempDir() { return tempDir; }
    public Path getMetaDir() { return metaDir; }
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
}
