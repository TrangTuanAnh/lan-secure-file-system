package storagenode.network;

import storagenode.antivirus.AntivirusScanner;
import storagenode.antivirus.ScanResult;
import storagenode.antivirus.ScanStatus;
import storagenode.crypto.AESCrypto;
import storagenode.crypto.HashUtil;
import storagenode.crypto.ModernKeyExchange;
import storagenode.crypto.RSAKeyExchange;
import storagenode.protocol.FrameCodec;
import storagenode.protocol.Message;
import storagenode.protocol.MessageType;
import storagenode.session.DownloadSession;
import storagenode.session.SessionManager;
import storagenode.session.UploadSession;
import storagenode.storage.DedupStore;
import storagenode.storage.FileStore;

import javax.crypto.SecretKey;
import java.io.*;
import java.net.Socket;
import java.net.SocketException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Xử lý một kết nối TCP từ máy khách tới nút lưu trữ.
 *
 * Mỗi kết nối có thể thực hiện một hoặc nhiều thao tác tải lên/tải xuống.
 * Dữ liệu có thể được mã hóa bằng AES sau bước bắt tay khóa.
 */
public class ClientHandler implements Runnable {

    private static final Logger LOG = Logger.getLogger(ClientHandler.class.getName());

    // Socket TCP đại diện cho 1 máy khách đang kết nối tới nút lưu trữ.
    private final Socket socket;
    // Quản lý trạng thái các phiên tải lên/tải xuống đang diễn ra.
    private final SessionManager sessionManager;
    // Lớp thao tác nhập/xuất file thật trên ổ đĩa: ghi khối, đọc khối, ghép file.
    private final FileStore fileStore;
    // Kiểm tra file đã tồn tại theo hash hay chưa để tránh lưu trùng nội dung.
    private final DedupStore dedupStore;
    // Thành phần dùng để báo kết quả tải lên thành công/thất bại về bộ điều phối.
    private final CoordinatorClient coordinator;
    // Đường mã hóa cũ: máy khách gửi khóa phiên AES đã mã hóa bằng RSA.
    private final RSAKeyExchange rsaKeyExchange;
    // Kích thước mỗi khối dữ liệu, mặc định thường là 512KB.
    private final int chunkSize;
    // Bộ quét virus được truyền vào từ lúc khởi động nút lưu trữ.
    private final AntivirusScanner antivirusScanner;
    private final boolean antivirusFailClosed;
    private final long antivirusMaxScanBytes;

    // Luồng đọc/ghi byte trực tiếp từ TCP socket.
    private InputStream in;
    private OutputStream out;
    // Khóa phiên AES sau khi bắt tay mã hóa; null nghĩa là chưa bật mã hóa.
    private SecretKey aesSessionKey;
    private String aesCipherMode = "NONE";
    // Gói thông tin tạm thời cho bắt tay ECDH/ML-KEM trước khi sinh khóa phiên AES.
    private ModernKeyExchange.HandshakeOffer modernOffer;
    private volatile boolean running = true;

    public ClientHandler(Socket socket, SessionManager sessionManager,
                         FileStore fileStore, DedupStore dedupStore,
                         CoordinatorClient coordinator, RSAKeyExchange rsaKeyExchange,
                         int chunkSize, AntivirusScanner antivirusScanner,
                         boolean antivirusFailClosed, long antivirusMaxScanBytes) {
        this.socket = socket;
        this.sessionManager = sessionManager;
        this.fileStore = fileStore;
        this.dedupStore = dedupStore;
        this.coordinator = coordinator;
        this.rsaKeyExchange = rsaKeyExchange;
        this.chunkSize = chunkSize;
        this.antivirusScanner = antivirusScanner;
        this.antivirusFailClosed = antivirusFailClosed;
        this.antivirusMaxScanBytes = antivirusMaxScanBytes;
    }

    @Override
    public void run() {
        String clientAddr = socket.getRemoteSocketAddress().toString();
        LOG.info("Client connected: " + clientAddr);

        try {
            // Lấy luồng nhập/xuất từ TCP socket để đọc yêu cầu và gửi phản hồi.
            in = new BufferedInputStream(socket.getInputStream());
            out = new BufferedOutputStream(socket.getOutputStream());

            while (running && !socket.isClosed()) {
                // Mỗi lần đọc 1 khung dữ liệu hoàn chỉnh từ TCP rồi chuyển thành Message.
                Message msg = FrameCodec.readFrame(in);
                if (msg == null) {
                    break; // Máy khách đã ngắt kết nối.
                }

                LOG.fine("Received: " + msg);
                // Phân loại message để gọi đúng logic: mã hóa, tải lên, tải xuống, chống trùng lặp.
                dispatch(msg);
            }
        } catch (SocketException e) {
            LOG.info("Client disconnected: " + clientAddr + " (" + e.getMessage() + ")");
        } catch (IOException e) {
            LOG.log(Level.WARNING, "I/O error with client " + clientAddr, e);
        } catch (Exception e) {
            LOG.log(Level.SEVERE, "Unexpected error with client " + clientAddr, e);
        } finally {
            close();
            LOG.info("Client handler finished: " + clientAddr);
        }
    }

    private void dispatch(Message msg) throws Exception {
        // Bộ điều phối chính: máy khách gửi type nào thì gọi hàm xử lý tương ứng.
        switch (msg.getType()) {
            case KEY_EXCHANGE:     handleKeyExchange(msg); break;
            case OPEN_UPLOAD:      handleOpenUpload(msg); break;
            case UPLOAD_CHUNK:     handleUploadChunk(msg); break;
            case QUERY_MISSING:    handleQueryMissing(msg); break;
            case FINALIZE_UPLOAD:  handleFinalizeUpload(msg); break;
            case OPEN_DOWNLOAD:    handleOpenDownload(msg); break;
            case REQUEST_CHUNK:    handleRequestChunk(msg); break;
            case CHECK_OBJECT:     handleCheckObject(msg); break;
            default: sendError("UNKNOWN_TYPE", "Unknown message type: " + msg.getType()); break;
        }
    }

    // ═══════════════════════ BẮT TAY MÃ HÓA ═══════════════════════

    private void handleKeyExchange(Message msg) throws Exception {
        byte[] encryptedSessionKey = msg.getData();
        String action = msg.getString("action");

        // Nhánh mã hóa hiện đại: máy khách xin public key ECDH + ML-KEM từ máy chủ.
        if ("GET_HYBRID_PUBLIC_KEY".equalsIgnoreCase(action) ||
                "GET_MODERN_PUBLIC_KEY".equalsIgnoreCase(action) ||
                "GET_ECDH_PUBLIC_KEY".equalsIgnoreCase(action)) {
            handleModernKeyBootstrap();
            return;
        }
        if ("HYBRID_INIT".equalsIgnoreCase(action)) {
            handleHybridKeyInit(msg);
            return;
        }
        if ("ECDH_INIT".equalsIgnoreCase(action)) {
            handleEcdhKeyInit(msg);
            return;
        }

        boolean requestPublicKey = msg.getBool("requestPublicKey") ||
                "GET_PUBLIC_KEY".equalsIgnoreCase(action);

        // Nhánh cũ: máy khách xin public key RSA trước, sau đó gửi khóa AES đã mã hóa.
        if (encryptedSessionKey == null || encryptedSessionKey.length == 0) {
            Message resp = Message.ok(MessageType.KEY_EXCHANGE_RESP)
                    .set("status", "PUBLIC_KEY")
                    .set("encrypted", false)
                    .set("bootstrap", true)
                    .set("message", requestPublicKey
                            ? "Node public key returned"
                            : "Provide encrypted AES key in next KEY_EXCHANGE");
            resp.setData(rsaKeyExchange.getPublicKeyBytes());
            send(resp);
            LOG.info("Returned node public key to " + socket.getRemoteSocketAddress());
            return;
        }

        try {
            // Giải mã khóa phiên AES do máy khách gửi lên bằng private key RSA của nút.
            aesSessionKey = rsaKeyExchange.decryptSessionKey(encryptedSessionKey);
            aesCipherMode = "AES-256-CBC";
        } catch (Exception e) {
            sendError("INVALID_SESSION_KEY", "Failed to decrypt AES session key");
            LOG.warning("Key exchange failed: " + e.getMessage());
            return;
        }

        // Gửi phản hồi xác nhận cho nhánh mã hóa cũ.
        Message resp = Message.ok(MessageType.KEY_EXCHANGE_RESP)
                .set("encrypted", true)
                .set("bootstrap", false);
        send(resp);

        LOG.info("Legacy AES-CBC session established with " + socket.getRemoteSocketAddress());
    }

    private void handleModernKeyBootstrap() throws Exception {
        try {
            // Sinh khóa tạm thời cho phiên hiện tại, không dùng khóa cố định.
            modernOffer = ModernKeyExchange.createOffer();
        } catch (Exception e) {
            sendError("MODERN_KEY_EXCHANGE_UNAVAILABLE", "Modern key exchange is unavailable");
            LOG.log(Level.WARNING, "Failed to create modern key exchange offer", e);
            return;
        }

        Message resp = Message.ok(MessageType.KEY_EXCHANGE_RESP)
                .set("status", "PUBLIC_KEY")
                .set("encrypted", false)
                .set("bootstrap", true)
                .set("algorithm", ModernKeyExchange.HYBRID_PROTOCOL)
                .set("ecdhCurve", "secp256r1")
                .set("pqKem", "ML-KEM-768")
                .set("postQuantum", true)
                .set("cipher", ModernKeyExchange.CIPHER)
                .set("serverNonceB64", b64(modernOffer.getServerNonce()))
                .set("mlKemPublicKeyB64", b64(modernOffer.getMlKemPublicKeyBytes()))
                .set("message", "Hybrid ECDH/ML-KEM public keys returned");
        resp.setData(modernOffer.getEcdhPublicKeyBytes());
        send(resp);
        LOG.info("Returned hybrid ECDH/ML-KEM key material to " + socket.getRemoteSocketAddress());
    }

    private void handleHybridKeyInit(Message msg) throws Exception {
        if (modernOffer == null) {
            sendError("MISSING_KEY_BOOTSTRAP", "Request modern public keys before HYBRID_INIT");
            return;
        }
        try {
            // Máy khách gửi public key ECDH, nonce và ciphertext ML-KEM để hai bên sinh cùng khóa AES.
            byte[] clientEcdhPublicKey = msg.getData();
            byte[] clientNonce = b64decode(msg.getString("clientNonceB64"));
            byte[] mlKemCiphertext = b64decode(msg.getString("mlKemCiphertextB64"));
            aesSessionKey = ModernKeyExchange.deriveHybridSessionKey(
                    modernOffer, clientEcdhPublicKey, clientNonce, mlKemCiphertext);
            aesCipherMode = ModernKeyExchange.CIPHER;
        } catch (Exception e) {
            sendError("INVALID_HYBRID_KEY", "Failed to derive hybrid session key");
            LOG.warning("Hybrid key exchange failed: " + e.getMessage());
            return;
        }

        Message resp = Message.ok(MessageType.KEY_EXCHANGE_RESP)
                .set("encrypted", true)
                .set("bootstrap", false)
                .set("algorithm", ModernKeyExchange.HYBRID_PROTOCOL)
                .set("postQuantum", true)
                .set("cipher", aesCipherMode);
        send(resp);
        LOG.info("Hybrid post-quantum session established with " + socket.getRemoteSocketAddress());
    }

    private void handleEcdhKeyInit(Message msg) throws Exception {
        if (modernOffer == null) {
            sendError("MISSING_KEY_BOOTSTRAP", "Request modern public keys before ECDH_INIT");
            return;
        }
        try {
            // Dự phòng khi không dùng được ML-KEM: chỉ dùng ECDH + HKDF để sinh khóa AES-GCM.
            byte[] clientEcdhPublicKey = msg.getData();
            byte[] clientNonce = b64decode(msg.getString("clientNonceB64"));
            aesSessionKey = ModernKeyExchange.deriveEcdhSessionKey(
                    modernOffer, clientEcdhPublicKey, clientNonce);
            aesCipherMode = ModernKeyExchange.CIPHER;
        } catch (Exception e) {
            sendError("INVALID_ECDH_KEY", "Failed to derive ECDH session key");
            LOG.warning("ECDH key exchange failed: " + e.getMessage());
            return;
        }

        Message resp = Message.ok(MessageType.KEY_EXCHANGE_RESP)
                .set("encrypted", true)
                .set("bootstrap", false)
                .set("algorithm", ModernKeyExchange.ECDH_PROTOCOL)
                .set("postQuantum", false)
                .set("cipher", aesCipherMode);
        send(resp);
        LOG.info("ECDH AES-GCM session established with " + socket.getRemoteSocketAddress());
    }

    // ═══════════════════════ TẢI LÊN ═══════════════════════

    private void handleOpenUpload(Message msg) throws Exception {
        // Bước 1 của tải lên: máy khách mở phiên tải lên và gửi siêu dữ liệu của file.
        String sessionId  = msg.getString("sessionId");
        String fileId     = msg.getString("fileId");
        String fileName   = msg.getString("fileName");
        String sha256Whole = msg.getString("sha256Whole");
        long   fileSize   = msg.getLong("fileSize");
        int    totalChunks = msg.getInt("totalChunks");
        String uploaderId = msg.getString("uploaderId");

        // Lấy thông tin vé để xác thực quyền tải lên.
        String ticketNodeId = msg.getString("ticketNodeId");
        long   ticketExpiry = msg.getLong("ticketExpiry");
        String ticketSig    = msg.getString("ticketSignature");

        // Nút lưu trữ không tin trực tiếp yêu cầu từ máy khách; phải xác thực vé do bộ điều phối cấp.
        if (!coordinator.verifyTicket(sessionId, fileId, ticketNodeId, ticketExpiry, ticketSig)) {
            sendError("INVALID_TICKET", "Upload ticket verification failed");
            return;
        }

        // Nếu hash file đã có trong kho thì bỏ qua truyền dữ liệu, báo chống trùng lặp thành công.
        if (dedupStore.exists(sha256Whole)) {
            Message resp = Message.ok(MessageType.OPEN_UPLOAD_RESP)
                    .set("sessionId", sessionId)
                    .set("dedup", true)
                    .set("message", "File already exists (dedup match)");
            send(resp);
            coordinator.notifyUploadComplete(fileId, sha256Whole, fileSize);
            LOG.info("Dedup hit for " + sha256Whole + ", skipping upload");
            return;
        }

        // Nếu phiên đã tồn tại, đây là tải lên tiếp sau khi mất kết nối.
        UploadSession existing = sessionManager.getUploadSession(sessionId);
        if (existing != null) {
            // Trả cho máy khách danh sách khối còn thiếu để chỉ gửi lại phần thiếu.
            List<Integer> missing = existing.getMissingChunks();
            Message resp = Message.ok(MessageType.OPEN_UPLOAD_RESP)
                    .set("sessionId", sessionId)
                    .set("resumed", true)
                    .set("receivedChunks", existing.getReceivedCount())
                    .set("totalChunks", existing.getTotalChunks())
                    .set("missingChunks", missing)
                    .set("chunkSize", chunkSize);
            send(resp);
            LOG.info("Resumed upload session: " + sessionId +
                     " received=" + existing.getReceivedCount() + "/" + totalChunks);
            return;
        }

        // Tạo phiên tải lên mới, lưu thông tin tổng file và số lượng khối cần nhận.
        UploadSession session = sessionManager.createUploadSession(
            sessionId, fileId, fileName, sha256Whole,
            fileSize, totalChunks, chunkSize, uploaderId
        );

        Message resp = Message.ok(MessageType.OPEN_UPLOAD_RESP)
                .set("sessionId", sessionId)
                .set("resumed", false)
                .set("totalChunks", totalChunks)
                .set("chunkSize", chunkSize);
        send(resp);
    }

    private void handleUploadChunk(Message msg) throws Exception {
        // Bước 2 của tải lên: máy khách gửi từng phần nhỏ của file theo chỉ số khối.
        String sessionId = msg.getString("sessionId");
        int chunkIndex   = msg.getInt("chunkIndex");
        String chunkHash = msg.getString("chunkHash");
        byte[] chunkData = msg.getData();

        // Nếu đã bắt tay mã hóa, khối từ máy khách đang là bản mã nên phải giải mã trước.
        if (aesSessionKey != null && chunkData != null) {
            try {
                chunkData = decryptPayload(chunkData);
            } catch (Exception e) {
                sendError("DECRYPT_FAILED", "Failed to decrypt chunk payload");
                return;
            }
        }

        // Kiểm tra phiên tải lên còn tồn tại trong bộ quản lý phiên không.
        UploadSession session = sessionManager.getUploadSession(sessionId);
        if (session == null) {
            sendError("INVALID_SESSION", "Upload session not found: " + sessionId);
            return;
        }

        if (chunkData == null || chunkData.length == 0) {
            sendError("MISSING_DATA", "Chunk data is empty");
            return;
        }

        // Chặn index âm hoặc index vượt quá tổng số khối của file.
        if (!session.isValidChunkIndex(chunkIndex)) {
            Message nack = new Message(MessageType.ACK_CHUNK)
                    .set("sessionId", sessionId)
                    .set("chunkIndex", chunkIndex)
                    .set("status", "INVALID_CHUNK_INDEX")
                    .set("totalChunks", session.getTotalChunks())
                    .set("message", "chunkIndex out of range");
            send(nack);
            return;
        }

        // Khối thường phải đúng kích thước cấu hình; riêng khối cuối có thể nhỏ hơn.
        int expectedSize = session.expectedChunkSize(chunkIndex);
        if (chunkData.length != expectedSize) {
            Message nack = new Message(MessageType.ACK_CHUNK)
                    .set("sessionId", sessionId)
                    .set("chunkIndex", chunkIndex)
                    .set("status", "INVALID_CHUNK_SIZE")
                    .set("expectedSize", expectedSize)
                    .set("actualSize", chunkData.length)
                    .set("message", "Chunk size does not match expected size");
            send(nack);
            return;
        }

        // Nếu máy khách gửi lại khối đã nhận rồi thì trả ACK trùng lặp, không ghi đè lại.
        if (session.hasChunk(chunkIndex)) {
            Message ack = Message.ok(MessageType.ACK_CHUNK)
                    .set("sessionId", sessionId)
                    .set("chunkIndex", chunkIndex)
                    .set("duplicate", true);
            send(ack);
            return;
        }

        // Tính SHA-256 của dữ liệu khối để kiểm tra khối có bị lỗi khi truyền không.
        String actualHash = HashUtil.sha256(chunkData);
        if (!actualHash.equalsIgnoreCase(chunkHash)) {
            LOG.warning("Chunk hash mismatch: session=" + sessionId +
                        " chunk=" + chunkIndex +
                        " expected=" + chunkHash + " actual=" + actualHash);
            Message nack = new Message(MessageType.ACK_CHUNK)
                    .set("sessionId", sessionId)
                    .set("chunkIndex", chunkIndex)
                    .set("status", "HASH_MISMATCH")
                    .set("expectedHash", chunkHash)
                    .set("actualHash", actualHash);
            send(nack);
            return;
        }

        // Ghi khối xuống thư mục tạm theo dạng data/temp/{sessionId}/chunk_{index}.
        fileStore.writeChunk(sessionId, chunkIndex, chunkData);
        // Đánh dấu khối đã nhận để tính tiến độ và hỗ trợ tiếp tục tải lên.
        session.markChunkReceived(chunkIndex, actualHash);

        // Không lưu siêu dữ liệu sau từng khối để tránh ghi đĩa quá nhiều.
        // Cứ mỗi 16 khối mới lưu một lần, và luôn lưu ở khối cuối để bước hoàn tất có siêu dữ liệu mới nhất.
        int recvCount = session.getReceivedCount();
        int totalCount = session.getTotalChunks();
        if (recvCount == totalCount || (recvCount % 16) == 0) {
            // Lưu siêu dữ liệu định kỳ để nếu nút lưu trữ khởi động lại vẫn có thể phục hồi tải lên.
            fileStore.saveSessionMeta(sessionId, session.toProperties());
        }

        // Trả ACK cho máy khách để biết khối này đã được nhận hợp lệ.
        Message ack = Message.ok(MessageType.ACK_CHUNK)
                .set("sessionId", sessionId)
                .set("chunkIndex", chunkIndex)
                .set("received", session.getReceivedCount())
                .set("total", session.getTotalChunks())
                .set("progress", session.getProgressPercent());
        send(ack);

        LOG.fine("Chunk received: session=" + sessionId + " chunk=" + chunkIndex +
                 " [" + session.getReceivedCount() + "/" + session.getTotalChunks() + "]");
    }

    private void handleQueryMissing(Message msg) throws Exception {
        // Máy khách gọi hàm này khi muốn biết còn thiếu khối nào để tiếp tục tải lên.
        String sessionId = msg.getString("sessionId");

        UploadSession session = sessionManager.getUploadSession(sessionId);
        if (session == null) {
            sendError("INVALID_SESSION", "Upload session not found: " + sessionId);
            return;
        }

        List<Integer> missing = session.getMissingChunks();
        Message resp = new Message(MessageType.MISSING_RESP)
                .set("sessionId", sessionId)
                .set("missingChunks", missing)
                .set("missingCount", missing.size())
                .set("received", session.getReceivedCount())
                .set("total", session.getTotalChunks());
        send(resp);

        LOG.info("Query missing: session=" + sessionId +
                 " missing=" + missing.size() + "/" + session.getTotalChunks());
    }

    private void handleFinalizeUpload(Message msg) throws Exception {
        // Bước 3 của tải lên: máy khách báo đã gửi xong tất cả khối và yêu cầu ghép file.
        String sessionId = msg.getString("sessionId");

        UploadSession session = sessionManager.getUploadSession(sessionId);
        if (session == null) {
            sendError("INVALID_SESSION", "Upload session not found: " + sessionId);
            return;
        }

        // Chỉ cho hoàn tất khi đã nhận đủ toàn bộ khối.
        if (!session.isComplete()) {
            List<Integer> missing = session.getMissingChunks();
            Message resp = new Message(MessageType.FINALIZE_RESP)
                    .set("sessionId", sessionId)
                    .set("status", "INCOMPLETE")
                    .set("missingChunks", missing)
                    .set("message", "Missing " + missing.size() + " chunks");
            send(resp);
            return;
        }

        // Chặn trường hợp nhiều yêu cầu hoàn tất chạy song song cho cùng một phiên.
        if (!session.tryBeginFinalizing()) {
            Message resp = new Message(MessageType.FINALIZE_RESP)
                    .set("sessionId", sessionId)
                    .set("status", "FINALIZE_IN_PROGRESS")
                    .set("message", "Upload session is already finalizing or finished");
            send(resp);
            return;
        }

        Path assembledPath;
        Path storedPath;
        ScanResult scanResult = null;
        try {
            // Ghép chunk_0, chunk_1, ... thành một file tạm hoàn chỉnh.
            assembledPath = fileStore.assembleTempFile(sessionId, session.getTotalChunks());
            // Kiểm tra hash toàn file sau khi ghép để đảm bảo không sai thứ tự hoặc thiếu dữ liệu.
            if (!fileStore.verifyAssembledHash(assembledPath, session.getSha256Whole(), sessionId)) {
                session.setStatus(UploadSession.Status.FAILED);
                // Dọn thư mục tạm và xóa phiên nếu hash toàn file không khớp.
                safeCleanupFailedSession(sessionId, "hash mismatch");
                Message resp = new Message(MessageType.FINALIZE_RESP)
                        .set("sessionId", sessionId)
                        .set("status", "HASH_MISMATCH")
                        .set("message", "Whole-file hash verification failed");
                send(resp);
                coordinator.notifyUploadFailed(session.getFileId(), "Hash mismatch after assembly");
                return;
            }

            // Kiểm tra giới hạn kích thước trước khi gửi sang antivirus.
            scanResult = validateScanSize(assembledPath);
            if (scanResult == null) {
                // Quét virus trên file đã ghép hoàn chỉnh, không quét từng khối riêng lẻ.
                scanResult = antivirusScanner.scan(assembledPath);
            }
            if (!scanResult.isClean() &&
                    (scanResult.getStatus() == ScanStatus.INFECTED ||
                            scanResult.getStatus() == ScanStatus.LIMIT_EXCEEDED ||
                            antivirusFailClosed)) {
                // Nếu phát hiện virus hoặc cấu hình đóng khi lỗi thì từ chối lưu file.
                handleScanRejectedUpload(session, assembledPath, scanResult);
                return;
            }

            if (!scanResult.isClean()) {
                LOG.warning("Antivirus scan failed open for session=" + sessionId +
                        " status=" + scanResult.getStatus() +
                        " message=" + scanResult.getMessage());
            }

            // File hợp lệ và sạch: chuyển từ vùng tạm sang kho lưu trữ chính theo hash.
            storedPath = fileStore.commitAssembledFile(assembledPath, session.getSha256Whole());
            // Xóa thư mục tạm chứa các khối sau khi lưu chính thức thành công.
            fileStore.cleanSessionDir(sessionId);
        } catch (IOException e) {
            session.setStatus(UploadSession.Status.FAILED);
            // Dọn thư mục tạm và xóa phiên nếu có lỗi nhập/xuất khi hoàn tất.
            safeCleanupFailedSession(sessionId, "I/O error: " + e.getMessage());
            Message resp = new Message(MessageType.FINALIZE_RESP)
                    .set("sessionId", sessionId)
                    .set("status", "FINALIZE_IO_ERROR")
                    .set("message", "I/O error while finalizing upload");
            send(resp);
            coordinator.notifyUploadFailed(session.getFileId(), "Finalize I/O error: " + e.getMessage());
            LOG.warning("Finalize I/O error for session " + sessionId + ": " + e.getMessage());
            return;
        }

        // Ghi nhận hash file vào kho chống trùng lặp để lần sau gặp file giống hệt thì không tải lên lại.
        dedupStore.register(session.getSha256Whole(), storedPath);

        session.setStatus(UploadSession.Status.COMPLETED);
        sessionManager.removeUploadSession(sessionId);

        // Báo cho bộ điều phối cập nhật cơ sở dữ liệu: file tải lên đã hoàn tất.
        coordinator.notifyUploadComplete(
            session.getFileId(), session.getSha256Whole(), session.getFileSize()
        );

        Message resp = Message.ok(MessageType.FINALIZE_RESP)
                .set("sessionId", sessionId)
                .set("status", "COMPLETED")
                .set("sha256Whole", session.getSha256Whole())
                .set("storedPath", storedPath.toString())
                .set("message", "File stored successfully");
        addScanFields(resp, scanResult);
        send(resp);

        LOG.info("Upload finalized: session=" + sessionId +
                 " file=" + session.getFileName() + " sha256=" + session.getSha256Whole());
    }

    // ═══════════════════════ TẢI XUỐNG ═══════════════════════

    private void handleOpenDownload(Message msg) throws Exception {
        // Bước 1 của tải xuống: máy khách mở phiên tải xuống bằng vé do bộ điều phối cấp.
        String sessionId  = msg.getString("sessionId");
        String fileId     = msg.getString("fileId");
        String sha256Whole = msg.getString("sha256Whole");
        String downloaderId = msg.getString("downloaderId");

        // Lấy thông tin vé để xác thực quyền tải xuống.
        String ticketNodeId = msg.getString("ticketNodeId");
        long   ticketExpiry = msg.getLong("ticketExpiry");
        String ticketSig    = msg.getString("ticketSignature");

        // Kiểm tra vé để đảm bảo máy khách có quyền tải file này từ nút này.
        if (!coordinator.verifyTicket(sessionId, fileId, ticketNodeId, ticketExpiry, ticketSig)) {
            sendError("INVALID_TICKET", "Download ticket verification failed");
            return;
        }

        // File được lưu theo sha256Whole; không có hash này thì nút không có file.
        if (!fileStore.fileExists(sha256Whole)) {
            sendError("FILE_NOT_FOUND", "File not found: " + sha256Whole);
            return;
        }

        // Tính fileSize và totalChunks để máy khách biết cần yêu cầu bao nhiêu khối.
        long fileSize = fileStore.getFileSize(sha256Whole);
        int totalChunks = fileStore.calculateTotalChunks(fileSize);

        // Tạo phiên tải xuống để theo dõi khối nào đã gửi.
        DownloadSession session = sessionManager.createDownloadSession(
            sessionId, fileId, sha256Whole, fileSize,
            totalChunks, chunkSize, downloaderId
        );

        Message resp = Message.ok(MessageType.OPEN_DOWNLOAD_RESP)
                .set("sessionId", sessionId)
                .set("fileSize", fileSize)
                .set("totalChunks", totalChunks)
                .set("chunkSize", chunkSize)
                .set("sha256Whole", sha256Whole);
        send(resp);

        LOG.info("Download session opened: " + sessionId +
                 " sha256=" + sha256Whole + " chunks=" + totalChunks);
    }

    private void handleRequestChunk(Message msg) throws Exception {
        // Bước 2 của tải xuống: máy khách yêu cầu một khối cụ thể theo chunkIndex.
        String sessionId = msg.getString("sessionId");
        int chunkIndex   = msg.getInt("chunkIndex");

        // Lấy phiên tải xuống đã mở trước đó bằng OPEN_DOWNLOAD.
        DownloadSession session = sessionManager.getDownloadSession(sessionId);
        if (session == null) {
            sendError("INVALID_SESSION", "Download session not found: " + sessionId);
            return;
        }

        // Chặn máy khách yêu cầu khối ngoài phạm vi file.
        if (!session.isValidChunkIndex(chunkIndex)) {
            sendError("INVALID_CHUNK_INDEX", "chunkIndex out of range: " + chunkIndex);
            return;
        }

        byte[] chunkData;
        try {
        // Đọc đúng đoạn file từ ổ đĩa bằng vị trí bắt đầu = chỉ số khối * kích thước khối.
            chunkData = fileStore.readStoredChunk(
                session.getSha256Whole(), chunkIndex, chunkSize
            );
        } catch (IOException e) {
            sendError("READ_CHUNK_ERROR", "Failed to read chunk " + chunkIndex);
            return;
        }

        // Gửi kèm hash khối để máy khách kiểm tra dữ liệu tải về có đúng không.
        String chunkHash = HashUtil.sha256(chunkData);

        // Nếu phiên đã bật mã hóa thì mã hóa khối trước khi trả về máy khách.
        byte[] payload = chunkData;
        if (aesSessionKey != null) {
            payload = encryptPayload(chunkData);
        }

        Message resp = new Message(MessageType.DOWNLOAD_CHUNK)
                .set("sessionId", sessionId)
                .set("chunkIndex", chunkIndex)
                .set("chunkHash", chunkHash)
                .set("chunkSize", chunkData.length)
                .set("totalChunks", session.getTotalChunks());
        resp.setData(payload);
        send(resp);

        // Đánh dấu khối đã gửi; nếu đây là khối cuối cùng thì gửi DOWNLOAD_COMPLETE đúng một lần.
        boolean justCompleted = session.markChunkSentAndCheckJustCompleted(chunkIndex);
        if (justCompleted) {
            Message complete = Message.ok(MessageType.DOWNLOAD_COMPLETE)
                    .set("sessionId", sessionId)
                    .set("sha256Whole", session.getSha256Whole());
            send(complete);
            sessionManager.removeDownloadSession(sessionId);
        }
    }

    // ═══════════════════════ KIỂM TRA TRÙNG LẶP ═══════════════════════

    private void handleCheckObject(Message msg) throws Exception {
        // Máy khách hoặc bộ điều phối có thể hỏi trước hash này đã tồn tại trên nút chưa.
        String sha256 = msg.getString("sha256Whole");
        boolean exists = dedupStore.exists(sha256);

        Message resp = new Message(MessageType.CHECK_OBJECT_RESP)
                .set("sha256Whole", sha256)
                .set("exists", exists);
        send(resp);
    }

    private void handleScanRejectedUpload(UploadSession session, Path assembledPath,
                                          ScanResult scanResult) throws IOException {
        // Xử lý khi file tải lên bị bộ quét virus từ chối.
        session.setStatus(UploadSession.Status.FAILED);

        String sessionId = session.getSessionId();
        String status = finalizeStatusForScan(scanResult.getStatus());
        String message = finalizeMessageForScan(scanResult);

        if (scanResult.getStatus() == ScanStatus.INFECTED) {
            try {
                // File nhiễm virus được chuyển sang khu cách ly để kiểm tra, không lưu vào kho chính.
                Path quarantinePath = fileStore.quarantineFile(session, assembledPath, scanResult);
                LOG.warning("Infected upload quarantined: session=" + sessionId +
                        " path=" + quarantinePath);
            } catch (IOException e) {
                LOG.warning("Failed to quarantine infected upload session=" + sessionId +
                        ": " + e.getMessage());
            }
        }

        try {
            // Dù quét lỗi hay nhiễm virus thì cũng dọn thư mục tạm của phiên.
            fileStore.cleanSessionDir(sessionId);
        } catch (IOException e) {
            LOG.warning("Failed to clean rejected upload session=" + sessionId + ": " + e.getMessage());
        }

        // Xóa phiên khỏi bộ nhớ và báo bộ điều phối cập nhật trạng thái thất bại trong cơ sở dữ liệu.
        sessionManager.removeUploadSession(sessionId);
        coordinator.notifyUploadFailed(session.getFileId(), message);

        Message resp = new Message(MessageType.FINALIZE_RESP)
                .set("sessionId", sessionId)
                .set("status", status)
                .set("message", message);
        addScanFields(resp, scanResult);
        send(resp);
    }

    private static String finalizeStatusForScan(ScanStatus scanStatus) {
        switch (scanStatus) {
            case INFECTED:
                return "VIRUS_DETECTED";
            case LIMIT_EXCEEDED:
                return "SCAN_LIMIT_EXCEEDED";
            case TIMEOUT:
                return "SCAN_TIMEOUT";
            case UNAVAILABLE:
                return "SCAN_UNAVAILABLE";
            default:
                return "SCAN_ERROR";
        }
    }

    private static String finalizeMessageForScan(ScanResult scanResult) {
        if (scanResult.getStatus() == ScanStatus.INFECTED) {
            return "Virus detected: " + scanResult.getThreatName();
        }
        if (scanResult.getStatus() == ScanStatus.LIMIT_EXCEEDED) {
            return "Antivirus scan limit exceeded: " + scanResult.getMessage();
        }
        if (scanResult.getMessage() != null && !scanResult.getMessage().isEmpty()) {
            return "Antivirus scan failed: " + scanResult.getMessage();
        }
        return "Antivirus scan failed: " + scanResult.getStatus();
    }

    private ScanResult validateScanSize(Path assembledPath) throws IOException {
        // Nếu antivirus tắt hoặc không đặt giới hạn thì bỏ qua bước kiểm tra kích thước.
        if (!antivirusScanner.isEnabled() || antivirusMaxScanBytes <= 0) {
            return null;
        }

        long size = Files.size(assembledPath);
        if (size <= antivirusMaxScanBytes) {
            return null;
        }

        String message = "file size " + size +
                " bytes exceeds antivirus.max.scan.bytes " + antivirusMaxScanBytes;
        LOG.warning("Rejecting upload before antivirus scan: " + message);
        return ScanResult.failure(ScanStatus.LIMIT_EXCEEDED, "storage-node", 0L, null, message);
    }

    private void addScanFields(Message msg, ScanResult scanResult) {
        if (scanResult == null || scanResult.getStatus() == ScanStatus.DISABLED) {
            return;
        }
        msg.set("scanStatus", scanResult.getStatus().name())
                .set("scanner", scanResult.getScanner())
                .set("scanDurationMs", scanResult.getDurationMs());
        if (scanResult.getThreatName() != null) {
            msg.set("threatName", scanResult.getThreatName());
        }
    }

    // ═══════════════════════ HÀM HỖ TRỢ ═══════════════════════

    /**
     * Dọn dẹp tốt nhất có thể khi phiên tải lên thất bại.
     * Hàm này xóa các khối tạm, xóa siêu dữ liệu tạm và gỡ phiên khỏi SessionManager
     * để phiên lỗi không bị nạp lại sau khi nút lưu trữ khởi động lại.
     */
    private void safeCleanupFailedSession(String sessionId, String reason) {
        try {
            fileStore.cleanSessionDir(sessionId);
        } catch (IOException e) {
            LOG.warning("Cleanup of temp dir failed for session=" + sessionId
                    + " reason=" + reason + " err=" + e.getMessage());
        }
        try {
            sessionManager.removeUploadSession(sessionId);
        } catch (Exception e) {
            LOG.warning("removeUploadSession failed for session=" + sessionId
                    + " err=" + e.getMessage());
        }
    }

    private synchronized void send(Message msg) throws IOException {
        // Đồng bộ hóa để nhiều nhánh xử lý không ghi chồng khung dữ liệu lên cùng OutputStream.
        FrameCodec.writeFrame(out, msg);
    }

    /** Mã hóa dữ liệu khối gửi ra bằng chế độ mã hóa đã bắt tay. */
    private byte[] encryptPayload(byte[] plaintext) throws Exception {
        // Phiên hiện đại dùng AES-256-GCM; phiên cũ dùng AES-CBC để tương thích.
        if (ModernKeyExchange.CIPHER.equals(aesCipherMode)) {
            return AESCrypto.encryptGcm(aesSessionKey, plaintext);
        }
        // Nhánh cũ hoặc chưa xác định thì dùng CBC để tương thích.
        return AESCrypto.encryptCbc(aesSessionKey, plaintext);
    }

    /** Giải mã dữ liệu khối nhận vào; tự nhận biết GCM theo tiền tố dữ liệu. */
    private byte[] decryptPayload(byte[] ciphertext) throws Exception {
        // Tự nhận biết dữ liệu là GCM hay CBC dựa trên định dạng trong AESCrypto.
        return AESCrypto.decrypt(aesSessionKey, ciphertext);
    }

    private static String b64(byte[] data) {
        return Base64.getEncoder().encodeToString(data);
    }

    private static byte[] b64decode(String value) {
        if (value == null || value.trim().isEmpty()) {
            return new byte[0];
        }
        return Base64.getDecoder().decode(value);
    }

    private void sendError(String code, String message) throws IOException {
        send(Message.error(code, message));
        LOG.warning("Error sent to client: [" + code + "] " + message);
    }

    public void close() {
        // Dừng vòng lặp xử lý và đóng socket TCP của máy khách.
        running = false;
        try {
            socket.close();
        } catch (IOException ignored) {}
    }
}
