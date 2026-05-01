package storagenode.network;

import storagenode.antivirus.AntivirusScanner;
import storagenode.config.NodeConfig;
import storagenode.crypto.RSAKeyExchange;
import storagenode.session.SessionManager;
import storagenode.storage.DedupStore;
import storagenode.storage.FileStore;

import java.io.IOException;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * TCP server that listens for data-plane connections from clients.
 *
 * Each incoming connection is handed off to a ClientHandler running
 * in a thread pool.
 */
public class StorageServer {

    private static final Logger LOG = Logger.getLogger(StorageServer.class.getName());

    private final NodeConfig config;
    private final SessionManager sessionManager;
    private final FileStore fileStore;
    private final DedupStore dedupStore;
    private final CoordinatorClient coordinator;
    private final RSAKeyExchange rsaKeyExchange;
    private final AntivirusScanner antivirusScanner;

    private ServerSocket serverSocket;
    private ExecutorService threadPool;
    private volatile boolean running = false;

    public StorageServer(NodeConfig config, SessionManager sessionManager,
                         FileStore fileStore, DedupStore dedupStore,
                         CoordinatorClient coordinator, RSAKeyExchange rsaKeyExchange,
                         AntivirusScanner antivirusScanner) {
        this.config = config;
        this.sessionManager = sessionManager;
        this.fileStore = fileStore;
        this.dedupStore = dedupStore;
        this.coordinator = coordinator;
        this.rsaKeyExchange = rsaKeyExchange;
        this.antivirusScanner = antivirusScanner;
    }

    /** Start listening for connections. Blocks the calling thread. */
    public void start() throws IOException {
        threadPool = Executors.newFixedThreadPool(config.getThreadPoolSize());
        serverSocket = new ServerSocket(config.getPort());
        running = true;

        LOG.info("╔══════════════════════════════════════════════════╗");
        LOG.info("║  Storage Node [" + config.getNodeId() + "] started on port " + config.getPort() + "     ║");
        LOG.info("║  Data dir : " + padRight(config.getDataDir().toString(), 37) + "║");
        LOG.info("║  Temp dir : " + padRight(config.getTempDir().toString(), 37) + "║");
        LOG.info("║  Chunk size: " + padRight(config.getChunkSize() + " bytes", 36) + "║");
        LOG.info("╚══════════════════════════════════════════════════╝");

        while (running) {
            try {
                Socket clientSocket = serverSocket.accept();
                clientSocket.setTcpNoDelay(true);
                clientSocket.setSoTimeout(0); // no read timeout for long uploads

                ClientHandler handler = new ClientHandler(
                    clientSocket, sessionManager, fileStore, dedupStore,
                    coordinator, rsaKeyExchange, config.getChunkSize(),
                    antivirusScanner, config.isAntivirusFailClosed()
                );
                threadPool.execute(handler);
            } catch (IOException e) {
                if (running) {
                    LOG.log(Level.WARNING, "Error accepting connection", e);
                }
            }
        }
    }

    /** Stop the server and clean up resources. */
    public void stop() {
        running = false;
        LOG.info("Shutting down Storage Node...");

        try {
            if (serverSocket != null && !serverSocket.isClosed()) {
                serverSocket.close();
            }
        } catch (IOException e) {
            LOG.warning("Error closing server socket: " + e.getMessage());
        }

        if (threadPool != null) {
            threadPool.shutdown();
            try {
                if (!threadPool.awaitTermination(10, TimeUnit.SECONDS)) {
                    threadPool.shutdownNow();
                }
            } catch (InterruptedException e) {
                threadPool.shutdownNow();
            }
        }

        LOG.info("Storage Node stopped.");
    }

    public boolean isRunning() {
        return running;
    }

    private static String padRight(String s, int width) {
        if (s.length() >= width) return s.substring(0, width);
        StringBuilder sb = new StringBuilder(s);
        for (int i = s.length(); i < width; i++) sb.append(' ');
        return sb.toString();
    }
}
