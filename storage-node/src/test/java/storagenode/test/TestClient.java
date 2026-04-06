package storagenode.test;

import storagenode.crypto.AESCrypto;
import storagenode.crypto.HashUtil;
import storagenode.crypto.RSAKeyExchange;
import storagenode.protocol.FrameCodec;
import storagenode.protocol.Message;
import storagenode.protocol.MessageType;

import javax.crypto.SecretKey;
import java.io.*;
import java.net.Socket;
import java.security.PublicKey;
import java.time.Instant;

/**
 * Base test client for communicating with the Storage Node.
 * Provides helper methods used by all test scripts.
 */
public class TestClient implements AutoCloseable {

    private final Socket socket;
    private final InputStream in;
    private final OutputStream out;
    private final String nodeId;
    private final String ticketSecret;
    private SecretKey aesKey;

    public TestClient(String host, int port, String nodeId, String ticketSecret) throws IOException {
        this.socket = new Socket(host, port);
        this.socket.setTcpNoDelay(true);
        this.in = new BufferedInputStream(socket.getInputStream());
        this.out = new BufferedOutputStream(socket.getOutputStream());
        this.nodeId = nodeId;
        this.ticketSecret = ticketSecret;
    }

    /** Send a message to the storage node. */
    public void send(Message msg) throws IOException {
        FrameCodec.writeFrame(out, msg);
    }

    /** Receive a message from the storage node. */
    public Message receive() throws IOException {
        return FrameCodec.readFrame(in);
    }

    /** Generate a valid ticket signature for testing. */
    public String generateTicketSignature(String sessionId, String fileId, long expiry) {
        try {
            String payload = sessionId + "|" + fileId + "|" + nodeId + "|" + expiry;
            javax.crypto.Mac mac = javax.crypto.Mac.getInstance("HmacSHA256");
            javax.crypto.spec.SecretKeySpec keySpec = new javax.crypto.spec.SecretKeySpec(
                ticketSecret.getBytes(java.nio.charset.StandardCharsets.UTF_8), "HmacSHA256");
            mac.init(keySpec);
            byte[] hmacBytes = mac.doFinal(payload.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            return HashUtil.bytesToHex(hmacBytes);
        } catch (Exception e) {
            throw new RuntimeException("Failed to generate ticket", e);
        }
    }

    /** Create a ticket expiry timestamp (seconds from now). */
    public long ticketExpiry(int secondsFromNow) {
        return Instant.now().getEpochSecond() + secondsFromNow;
    }

    /** Perform AES/RSA key exchange with the node. */
    public byte[] requestNodePublicKey() throws IOException {
        Message req = new Message(MessageType.KEY_EXCHANGE)
                .set("requestPublicKey", true)
                .set("action", "GET_PUBLIC_KEY");
        send(req);

        Message resp = receive();
        if (resp == null || resp.getType() != MessageType.KEY_EXCHANGE_RESP || resp.getData() == null) {
            throw new RuntimeException("Failed to get node public key");
        }
        return resp.getData();
    }

    /** Perform AES/RSA key exchange with bootstrap public-key request. */
    public void setupEncryption() throws Exception {
        setupEncryption(requestNodePublicKey());
    }

    /** Perform AES/RSA key exchange with the node using a known public key. */
    public void setupEncryption(byte[] nodePublicKeyBytes) throws Exception {
        PublicKey nodePublicKey = RSAKeyExchange.loadPublicKey(nodePublicKeyBytes);
        this.aesKey = AESCrypto.generateKey();
        byte[] encryptedAesKey = RSAKeyExchange.encryptSessionKey(nodePublicKey, aesKey);

        Message keyExMsg = new Message(MessageType.KEY_EXCHANGE);
        keyExMsg.setData(encryptedAesKey);
        send(keyExMsg);

        Message resp = receive();
        if (resp.getType() != MessageType.KEY_EXCHANGE_RESP) {
            throw new RuntimeException("Key exchange failed: " + resp);
        }
    }

    /** Encrypt data if encryption is active. */
    public byte[] encryptIfNeeded(byte[] data) throws Exception {
        if (aesKey != null) {
            return AESCrypto.encrypt(aesKey, data);
        }
        return data;
    }

    /** Decrypt data if encryption is active. */
    public byte[] decryptIfNeeded(byte[] data) throws Exception {
        if (aesKey != null) {
            return AESCrypto.decrypt(aesKey, data);
        }
        return data;
    }

    public boolean isEncrypted() { return aesKey != null; }

    public void setReadTimeoutMillis(int timeoutMs) throws IOException {
        socket.setSoTimeout(timeoutMs);
    }

    @Override
    public void close() throws IOException {
        socket.close();
    }

    // ── Utility ──

    public static void printHeader(String title) {
        String line = "============================================================";
        System.out.println("\n" + line);
        System.out.println("  " + title);
        System.out.println(line);
    }

    public static void printOk(String msg) {
        System.out.println("  [OK] " + msg);
    }

    public static void printFail(String msg) {
        System.out.println("  [FAIL] " + msg);
    }

    public static void printInfo(String msg) {
        System.out.println("  [INFO] " + msg);
    }
}
