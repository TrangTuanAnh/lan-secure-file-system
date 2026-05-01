package storagenode.network;

import storagenode.antivirus.AntivirusScanner;
import storagenode.antivirus.ScanResult;
import storagenode.antivirus.ScanStatus;
import storagenode.crypto.AESCrypto;
import storagenode.crypto.HashUtil;
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
import java.nio.file.Path;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Handles a single client TCP connection on the data plane.
 *
 * Each connection can perform one or more upload/download operations.
 * Optionally encrypted with AES after RSA key exchange.
 */
public class ClientHandler implements Runnable {

    private static final Logger LOG = Logger.getLogger(ClientHandler.class.getName());

    private final Socket socket;
    private final SessionManager sessionManager;
    private final FileStore fileStore;
    private final DedupStore dedupStore;
    private final CoordinatorClient coordinator;
    private final RSAKeyExchange rsaKeyExchange;
    private final int chunkSize;
    private final AntivirusScanner antivirusScanner;
    private final boolean antivirusFailClosed;

    private InputStream in;
    private OutputStream out;
    private SecretKey aesSessionKey;  // null if encryption not negotiated
    private volatile boolean running = true;

    public ClientHandler(Socket socket, SessionManager sessionManager,
                         FileStore fileStore, DedupStore dedupStore,
                         CoordinatorClient coordinator, RSAKeyExchange rsaKeyExchange,
                         int chunkSize, AntivirusScanner antivirusScanner,
                         boolean antivirusFailClosed) {
        this.socket = socket;
        this.sessionManager = sessionManager;
        this.fileStore = fileStore;
        this.dedupStore = dedupStore;
        this.coordinator = coordinator;
        this.rsaKeyExchange = rsaKeyExchange;
        this.chunkSize = chunkSize;
        this.antivirusScanner = antivirusScanner;
        this.antivirusFailClosed = antivirusFailClosed;
    }

    @Override
    public void run() {
        String clientAddr = socket.getRemoteSocketAddress().toString();
        LOG.info("Client connected: " + clientAddr);

        try {
            in = new BufferedInputStream(socket.getInputStream());
            out = new BufferedOutputStream(socket.getOutputStream());

            while (running && !socket.isClosed()) {
                Message msg = FrameCodec.readFrame(in);
                if (msg == null) {
                    break; // client disconnected
                }

                LOG.fine("Received: " + msg);
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

    // ═══════════════════════ KEY EXCHANGE ═══════════════════════

    private void handleKeyExchange(Message msg) throws Exception {
        byte[] encryptedSessionKey = msg.getData();
        boolean requestPublicKey = msg.getBool("requestPublicKey") ||
                "GET_PUBLIC_KEY".equalsIgnoreCase(msg.getString("action"));

        // Bootstrap step: client asks for node public key before sending AES key.
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
            // Client sent RSA-encrypted AES key
            aesSessionKey = rsaKeyExchange.decryptSessionKey(encryptedSessionKey);
        } catch (Exception e) {
            sendError("INVALID_SESSION_KEY", "Failed to decrypt AES session key");
            LOG.warning("Key exchange failed: " + e.getMessage());
            return;
        }

        // Backward-compatible confirmation
        Message resp = Message.ok(MessageType.KEY_EXCHANGE_RESP)
                .set("encrypted", true)
                .set("bootstrap", false);
        send(resp);

        LOG.info("Encryption session established with " + socket.getRemoteSocketAddress());
    }

    // ═══════════════════════ UPLOAD ═══════════════════════

    private void handleOpenUpload(Message msg) throws Exception {
        String sessionId  = msg.getString("sessionId");
        String fileId     = msg.getString("fileId");
        String fileName   = msg.getString("fileName");
        String sha256Whole = msg.getString("sha256Whole");
        long   fileSize   = msg.getLong("fileSize");
        int    totalChunks = msg.getInt("totalChunks");
        String uploaderId = msg.getString("uploaderId");

        // Ticket verification
        String ticketNodeId = msg.getString("ticketNodeId");
        long   ticketExpiry = msg.getLong("ticketExpiry");
        String ticketSig    = msg.getString("ticketSignature");

        if (!coordinator.verifyTicket(sessionId, fileId, ticketNodeId, ticketExpiry, ticketSig)) {
            sendError("INVALID_TICKET", "Upload ticket verification failed");
            return;
        }

        // Check dedup: file might already exist
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

        // Check if this is a resumed session
        UploadSession existing = sessionManager.getUploadSession(sessionId);
        if (existing != null) {
            // Resume: return current state
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

        // Create new session
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
        String sessionId = msg.getString("sessionId");
        int chunkIndex   = msg.getInt("chunkIndex");
        String chunkHash = msg.getString("chunkHash");
        byte[] chunkData = msg.getData();

        // Decrypt if encrypted session
        if (aesSessionKey != null && chunkData != null) {
            try {
                chunkData = AESCrypto.decrypt(aesSessionKey, chunkData);
            } catch (Exception e) {
                sendError("DECRYPT_FAILED", "Failed to decrypt chunk payload");
                return;
            }
        }

        UploadSession session = sessionManager.getUploadSession(sessionId);
        if (session == null) {
            sendError("INVALID_SESSION", "Upload session not found: " + sessionId);
            return;
        }

        if (chunkData == null || chunkData.length == 0) {
            sendError("MISSING_DATA", "Chunk data is empty");
            return;
        }

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

        // Skip if already received (idempotent for retransmission)
        if (session.hasChunk(chunkIndex)) {
            Message ack = Message.ok(MessageType.ACK_CHUNK)
                    .set("sessionId", sessionId)
                    .set("chunkIndex", chunkIndex)
                    .set("duplicate", true);
            send(ack);
            return;
        }

        // Verify chunk hash
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

        // Write chunk to disk
        fileStore.writeChunk(sessionId, chunkIndex, chunkData);
        session.markChunkReceived(chunkIndex, actualHash);

        // Persist session state
        fileStore.saveSessionMeta(sessionId, session.toProperties());

        // Send ACK
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
        String sessionId = msg.getString("sessionId");

        UploadSession session = sessionManager.getUploadSession(sessionId);
        if (session == null) {
            sendError("INVALID_SESSION", "Upload session not found: " + sessionId);
            return;
        }

        // Check all chunks received
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

        session.setStatus(UploadSession.Status.FINALIZING);

        Path assembledPath;
        Path storedPath;
        ScanResult scanResult = null;
        try {
            // Assemble file, verify hash, scan, then commit to permanent storage.
            assembledPath = fileStore.assembleTempFile(sessionId, session.getTotalChunks());
            if (!fileStore.verifyAssembledHash(assembledPath, session.getSha256Whole(), sessionId)) {
                session.setStatus(UploadSession.Status.FAILED);
                Message resp = new Message(MessageType.FINALIZE_RESP)
                        .set("sessionId", sessionId)
                        .set("status", "HASH_MISMATCH")
                        .set("message", "Whole-file hash verification failed");
                send(resp);
                coordinator.notifyUploadFailed(session.getFileId(), "Hash mismatch after assembly");
                return;
            }

            scanResult = antivirusScanner.scan(assembledPath);
            if (!scanResult.isClean() &&
                    (scanResult.getStatus() == ScanStatus.INFECTED || antivirusFailClosed)) {
                handleScanRejectedUpload(session, assembledPath, scanResult);
                return;
            }

            if (!scanResult.isClean()) {
                LOG.warning("Antivirus scan failed open for session=" + sessionId +
                        " status=" + scanResult.getStatus() +
                        " message=" + scanResult.getMessage());
            }

            storedPath = fileStore.commitAssembledFile(assembledPath, session.getSha256Whole());
            fileStore.cleanSessionDir(sessionId);
        } catch (IOException e) {
            session.setStatus(UploadSession.Status.FAILED);
            Message resp = new Message(MessageType.FINALIZE_RESP)
                    .set("sessionId", sessionId)
                    .set("status", "FINALIZE_IO_ERROR")
                    .set("message", "I/O error while finalizing upload");
            send(resp);
            coordinator.notifyUploadFailed(session.getFileId(), "Finalize I/O error: " + e.getMessage());
            LOG.warning("Finalize I/O error for session " + sessionId + ": " + e.getMessage());
            return;
        }

        // Register in dedup store
        dedupStore.register(session.getSha256Whole(), storedPath);

        session.setStatus(UploadSession.Status.COMPLETED);
        sessionManager.removeUploadSession(sessionId);

        // Notify coordinator
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

    // ═══════════════════════ DOWNLOAD ═══════════════════════

    private void handleOpenDownload(Message msg) throws Exception {
        String sessionId  = msg.getString("sessionId");
        String fileId     = msg.getString("fileId");
        String sha256Whole = msg.getString("sha256Whole");
        String downloaderId = msg.getString("downloaderId");

        // Ticket verification
        String ticketNodeId = msg.getString("ticketNodeId");
        long   ticketExpiry = msg.getLong("ticketExpiry");
        String ticketSig    = msg.getString("ticketSignature");

        if (!coordinator.verifyTicket(sessionId, fileId, ticketNodeId, ticketExpiry, ticketSig)) {
            sendError("INVALID_TICKET", "Download ticket verification failed");
            return;
        }

        // Check file exists
        if (!fileStore.fileExists(sha256Whole)) {
            sendError("FILE_NOT_FOUND", "File not found: " + sha256Whole);
            return;
        }

        long fileSize = fileStore.getFileSize(sha256Whole);
        int totalChunks = fileStore.calculateTotalChunks(fileSize);

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
        String sessionId = msg.getString("sessionId");
        int chunkIndex   = msg.getInt("chunkIndex");

        DownloadSession session = sessionManager.getDownloadSession(sessionId);
        if (session == null) {
            sendError("INVALID_SESSION", "Download session not found: " + sessionId);
            return;
        }

        if (!session.isValidChunkIndex(chunkIndex)) {
            sendError("INVALID_CHUNK_INDEX", "chunkIndex out of range: " + chunkIndex);
            return;
        }

        byte[] chunkData;
        try {
            chunkData = fileStore.readStoredChunk(
                session.getSha256Whole(), chunkIndex, chunkSize
            );
        } catch (IOException e) {
            sendError("READ_CHUNK_ERROR", "Failed to read chunk " + chunkIndex);
            return;
        }

        String chunkHash = HashUtil.sha256(chunkData);

        // Encrypt if encrypted session
        byte[] payload = chunkData;
        if (aesSessionKey != null) {
            payload = AESCrypto.encrypt(aesSessionKey, chunkData);
        }

        Message resp = new Message(MessageType.DOWNLOAD_CHUNK)
                .set("sessionId", sessionId)
                .set("chunkIndex", chunkIndex)
                .set("chunkHash", chunkHash)
                .set("chunkSize", chunkData.length)
                .set("totalChunks", session.getTotalChunks());
        resp.setData(payload);
        send(resp);

        boolean wasComplete = session.isComplete();
        session.markChunkSent(chunkIndex);

        // Check if download is complete
        if (!wasComplete && session.isComplete()) {
            Message complete = Message.ok(MessageType.DOWNLOAD_COMPLETE)
                    .set("sessionId", sessionId)
                    .set("sha256Whole", session.getSha256Whole());
            send(complete);
            sessionManager.removeDownloadSession(sessionId);
        }
    }

    // ═══════════════════════ DEDUP CHECK ═══════════════════════

    private void handleCheckObject(Message msg) throws Exception {
        String sha256 = msg.getString("sha256Whole");
        boolean exists = dedupStore.exists(sha256);

        Message resp = new Message(MessageType.CHECK_OBJECT_RESP)
                .set("sha256Whole", sha256)
                .set("exists", exists);
        send(resp);
    }

    private void handleScanRejectedUpload(UploadSession session, Path assembledPath,
                                          ScanResult scanResult) throws IOException {
        session.setStatus(UploadSession.Status.FAILED);

        String sessionId = session.getSessionId();
        String status = finalizeStatusForScan(scanResult.getStatus());
        String message = finalizeMessageForScan(scanResult);

        if (scanResult.getStatus() == ScanStatus.INFECTED) {
            try {
                Path quarantinePath = fileStore.quarantineFile(session, assembledPath, scanResult);
                LOG.warning("Infected upload quarantined: session=" + sessionId +
                        " path=" + quarantinePath);
            } catch (IOException e) {
                LOG.warning("Failed to quarantine infected upload session=" + sessionId +
                        ": " + e.getMessage());
            }
        }

        try {
            fileStore.cleanSessionDir(sessionId);
        } catch (IOException e) {
            LOG.warning("Failed to clean rejected upload session=" + sessionId + ": " + e.getMessage());
        }

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
        if (scanResult.getMessage() != null && !scanResult.getMessage().isEmpty()) {
            return "Antivirus scan failed: " + scanResult.getMessage();
        }
        return "Antivirus scan failed: " + scanResult.getStatus();
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

    // ═══════════════════════ HELPERS ═══════════════════════

    private synchronized void send(Message msg) throws IOException {
        FrameCodec.writeFrame(out, msg);
    }

    private void sendError(String code, String message) throws IOException {
        send(Message.error(code, message));
        LOG.warning("Error sent to client: [" + code + "] " + message);
    }

    public void close() {
        running = false;
        try {
            socket.close();
        } catch (IOException ignored) {}
    }
}
