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
 * Máy chủ TCP của nút lưu trữ.
 *
 * File này là điểm bắt đầu của luồng nhập/xuất qua mạng:
 * mở cổng TCP, chờ máy khách kết nối, rồi giao socket cho ClientHandler xử lý.
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

    // ServerSocket là cổng TCP mà nút lưu trữ mở ra để máy khách kết nối tải lên/tải xuống.
    private ServerSocket serverSocket;
    // Nhóm luồng giúp nhiều máy khách có thể gửi/nhận dữ liệu cùng lúc.
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

    /** Bắt đầu lắng nghe kết nối TCP từ máy khách. */
    public void start() throws IOException {
        // Tạo số luồng xử lý cố định để xử lý nhiều kết nối máy khách song song.
        threadPool = Executors.newFixedThreadPool(config.getThreadPoolSize());
        // Mở cổng TCP của nút lưu trữ; đây là nơi máy khách kết nối vào để truyền dữ liệu file.
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
                // Chặn tại đây cho đến khi có máy khách mới kết nối vào nút lưu trữ.
                Socket clientSocket = serverSocket.accept();
                // Tắt Nagle để dữ liệu yêu cầu/ACK nhỏ được gửi ngay, giảm độ trễ.
                clientSocket.setTcpNoDelay(true);
                // Không đặt timeout đọc vì tải lên file lớn có thể mất nhiều thời gian.
                clientSocket.setSoTimeout(0);

                // Mỗi kết nối máy khách được bọc thành một ClientHandler.
                ClientHandler handler = new ClientHandler(
                    clientSocket, sessionManager, fileStore, dedupStore,
                    coordinator, rsaKeyExchange, config.getChunkSize(),
                    antivirusScanner, config.isAntivirusFailClosed(),
                    config.getAntivirusMaxScanBytes()
                );
                // Đưa ClientHandler vào nhóm luồng để xử lý nhập/xuất socket ở luồng riêng.
                threadPool.execute(handler);
            } catch (IOException e) {
                if (running) {
                    LOG.log(Level.WARNING, "Error accepting connection", e);
                }
            }
        }
    }

    /** Dừng máy chủ và giải phóng tài nguyên mạng/luồng. */
    public void stop() {
        running = false;
        LOG.info("Shutting down Storage Node...");

        try {
            if (serverSocket != null && !serverSocket.isClosed()) {
                // Đóng cổng TCP để không nhận thêm máy khách mới.
                serverSocket.close();
            }
        } catch (IOException e) {
            LOG.warning("Error closing server socket: " + e.getMessage());
        }

        if (threadPool != null) {
            // Dừng nhận tác vụ mới và chờ các ClientHandler đang chạy kết thúc.
            threadPool.shutdown();
            try {
                if (!threadPool.awaitTermination(10, TimeUnit.SECONDS)) {
                    // Nếu chờ quá lâu thì ép dừng các luồng xử lý còn lại.
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
