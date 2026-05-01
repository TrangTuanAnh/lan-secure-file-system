package storagenode;

import storagenode.antivirus.AntivirusScanner;
import storagenode.antivirus.ClamAvClient;
import storagenode.antivirus.NoOpAntivirusScanner;
import storagenode.config.NodeConfig;
import storagenode.crypto.RSAKeyExchange;
import storagenode.monitor.StorageMonitor;
import storagenode.network.CoordinatorClient;
import storagenode.network.StorageServer;
import storagenode.session.SessionManager;
import storagenode.storage.DedupStore;
import storagenode.storage.FileStore;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.*;

/**
 * Storage Node — Data Plane Entry Point
 *
 * Responsibilities:
 *   - Receive file chunks via TCP socket
 *   - Store chunks to disk, verify integrity (SHA-256)
 *   - Support upload resume (query missing chunks)
 *   - Assemble and verify completed files
 *   - Serve file chunks for download
 *   - Content-addressed dedup
 *   - AES/RSA encrypted transport
 *
 * Usage:
 *   java -jar storage-node.jar [config-file]
 *   Default config: storage-node.properties
 */
public class StorageNodeMain {

    private static final Logger LOG = Logger.getLogger(StorageNodeMain.class.getName());

    public static void main(String[] args) {
        String configFile = args.length > 0 ? args[0] : "storage-node.properties";

        try {
            // 1. Load configuration
            LOG.info("Loading configuration from: " + configFile);
            NodeConfig config = new NodeConfig(configFile);

            // 2. Setup logging
            setupLogging(config);

            // 3. Initialize storage
            LOG.info("Initializing storage directories...");
            FileStore fileStore = new FileStore(
                config.getDataDir(), config.getTempDir(), config.getQuarantineDir(), config.getChunkSize()
            );
            DedupStore dedupStore = new DedupStore(config.getMetaDir());

            AntivirusScanner antivirusScanner;
            if (config.isAntivirusEnabled()) {
                antivirusScanner = new ClamAvClient(
                    config.getAntivirusHost(),
                    config.getAntivirusPort(),
                    config.getAntivirusTimeoutMs()
                );
                LOG.info("Antivirus enabled: clamd at " + config.getAntivirusHost() +
                        ":" + config.getAntivirusPort() +
                        ", timeout=" + config.getAntivirusTimeoutMs() + "ms" +
                        ", failClosed=" + config.isAntivirusFailClosed());
            } else {
                antivirusScanner = new NoOpAntivirusScanner();
                LOG.warning("Antivirus scanning is disabled");
            }

            // 4. Initialize session manager
            SessionManager sessionManager = new SessionManager(
                fileStore, config.getUploadTimeoutMinutes(), config.getDownloadTimeoutMinutes()
            );

            // 5. Recover interrupted sessions
            int recovered = sessionManager.recoverSessions();
            if (recovered > 0) {
                LOG.info("Recovered " + recovered + " interrupted upload sessions");
            }

            // 6. Initialize security
            LOG.info("Generating RSA key pair (" + config.getRsaKeySize() + " bits)...");
            RSAKeyExchange rsaKeyExchange = new RSAKeyExchange(config.getRsaKeySize());

            // 7. Initialize coordinator client
            CoordinatorClient coordinator = new CoordinatorClient(
                config.getTicketSecret(), config.getNodeId(),
                config.getCoordinatorHost(), config.getCoordinatorPort(),
                config.getAdvertisedHost(), config.getAdvertisedPort(),
                config.getStorageAddress()
            );
            
            // Connect to Coordinator control plane
            try {
                LOG.info("Connecting to Coordinator control plane...");
                coordinator.connect();
                LOG.info("Connected to Coordinator: " + config.getCoordinatorHost() + 
                        ":" + config.getCoordinatorPort());
            } catch (IOException e) {
                LOG.warning("Failed to connect to Coordinator: " + e.getMessage());
                LOG.warning("Running in standalone mode (local ticket verification only)");
                LOG.warning("Upload/download will work, but Coordinator won't receive notifications");
            }

            // 8. Start monitoring
            StorageMonitor monitor = new StorageMonitor(sessionManager, fileStore, dedupStore);
            monitor.start(60); // log stats every 60 seconds

            // 9. Shutdown hook
            StorageServer server = new StorageServer(
                config, sessionManager, fileStore, dedupStore, coordinator, rsaKeyExchange, antivirusScanner
            );

            Runtime.getRuntime().addShutdownHook(new Thread(() -> {
                LOG.info("Shutdown signal received");
                server.stop();
                monitor.stop();
                coordinator.disconnect();
            }));

            // 10. Start server (blocking)
            server.start();

        } catch (IOException e) {
            LOG.severe("Failed to start Storage Node: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        } catch (Exception e) {
            LOG.severe("Unexpected error: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        }
    }

    private static void setupLogging(NodeConfig config) throws IOException {
        Path logDir = config.getLogDir();
        Files.createDirectories(logDir);

        Logger rootLogger = Logger.getLogger("");

        // Console handler
        for (Handler h : rootLogger.getHandlers()) {
            rootLogger.removeHandler(h);
        }
        ConsoleHandler consoleHandler = new ConsoleHandler();
        consoleHandler.setLevel(Level.parse(config.getLogLevel()));
        consoleHandler.setFormatter(new SimpleFormatter() {
            @Override
            public String format(LogRecord record) {
                return String.format("[%1$tF %1$tT] [%2$-7s] [%3$s] %4$s%n",
                    record.getMillis(),
                    record.getLevel().getName(),
                    record.getLoggerName().substring(
                        Math.max(0, record.getLoggerName().lastIndexOf('.') + 1)),
                    record.getMessage()
                );
            }
        });
        rootLogger.addHandler(consoleHandler);

        // File handler
        FileHandler fileHandler = new FileHandler(
            logDir.resolve("storage-node.log").toString(), 10_000_000, 5, true
        );
        fileHandler.setLevel(Level.ALL);
        fileHandler.setFormatter(new SimpleFormatter());
        rootLogger.addHandler(fileHandler);

        rootLogger.setLevel(Level.parse(config.getLogLevel()));
    }
}
