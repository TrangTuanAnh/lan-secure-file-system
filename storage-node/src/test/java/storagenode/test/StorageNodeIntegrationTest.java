package storagenode.test;

import org.junit.*;
import storagenode.antivirus.AntivirusScanner;
import storagenode.antivirus.ClamAvClient;
import storagenode.antivirus.NoOpAntivirusScanner;
import storagenode.config.NodeConfig;
import storagenode.crypto.HashUtil;
import storagenode.crypto.RSAKeyExchange;
import storagenode.network.CoordinatorClient;
import storagenode.network.StorageServer;
import storagenode.protocol.Message;
import storagenode.protocol.MessageType;
import storagenode.session.SessionManager;
import storagenode.storage.DedupStore;
import storagenode.storage.FileStore;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.SecureRandom;
import java.util.*;
import java.util.concurrent.TimeUnit;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.Logger;

import static org.junit.Assert.*;

public class StorageNodeIntegrationTest {

    private static TestHarness harness;
    private static final SecureRandom RNG = new SecureRandom();

    @BeforeClass
    public static void setUpClass() throws Exception {
        harness = new TestHarness();
        harness.start();
    }

    @AfterClass
    public static void tearDownClass() throws Exception {
        if (harness != null) {
            harness.close();
        }
    }

    @Test
    public void uploadSmallFileShouldComplete() throws Exception {
        byte[] fileData = randomBytes(100 * 1024);
        String sessionId = UUID.randomUUID().toString();
        String fileId = UUID.randomUUID().toString();

        try (TestClient client = harness.newClient()) {
            Message openResp = openUpload(client, sessionId, fileId, "small.bin", fileData);
            assertEquals(MessageType.OPEN_UPLOAD_RESP, openResp.getType());
            assertFalse(openResp.getBool("dedup"));

            Message ack = sendUploadChunk(client, sessionId, 0, fileData);
            assertEquals(MessageType.ACK_CHUNK, ack.getType());
            assertEquals("OK", ack.getString("status"));

            Message finalizeResp = finalizeUpload(client, sessionId);
            assertEquals(MessageType.FINALIZE_RESP, finalizeResp.getType());
            assertEquals("COMPLETED", finalizeResp.getString("status"));
            assertEquals(HashUtil.sha256(fileData), finalizeResp.getString("sha256Whole"));
        }
    }

    @Test
    public void uploadLargeFileShouldComplete() throws Exception {
        byte[] fileData = randomBytes(3 * 1024 * 1024);
        String sessionId = UUID.randomUUID().toString();
        String fileId = UUID.randomUUID().toString();

        try (TestClient client = harness.newClient()) {
            Message openResp = openUpload(client, sessionId, fileId, "large.bin", fileData);
            assertEquals(MessageType.OPEN_UPLOAD_RESP, openResp.getType());
            assertFalse(openResp.getBool("dedup"));

            int totalChunks = totalChunks(fileData.length);
            for (int i = 0; i < totalChunks; i++) {
                byte[] chunk = extractChunk(fileData, i, harness.chunkSize);
                Message ack = sendUploadChunk(client, sessionId, i, chunk);
                assertEquals("OK", ack.getString("status"));
            }

            Message finalizeResp = finalizeUpload(client, sessionId);
            assertEquals("COMPLETED", finalizeResp.getString("status"));
        }
    }

    @Test
    public void uploadResumeShouldWorkAfterDisconnect() throws Exception {
        byte[] fileData = randomBytes((int) (2.5 * 1024 * 1024));
        String sessionId = UUID.randomUUID().toString();
        String fileId = UUID.randomUUID().toString();
        int totalChunks = totalChunks(fileData.length);

        try (TestClient client1 = harness.newClient()) {
            Message openResp = openUpload(client1, sessionId, fileId, "resume.bin", fileData);
            assertEquals(MessageType.OPEN_UPLOAD_RESP, openResp.getType());

            for (int i = 0; i < 2; i++) {
                byte[] chunk = extractChunk(fileData, i, harness.chunkSize);
                Message ack = sendUploadChunk(client1, sessionId, i, chunk);
                assertEquals("OK", ack.getString("status"));
            }
        }

        try (TestClient client2 = harness.newClient()) {
            Message openResp = openUpload(client2, sessionId, fileId, "resume.bin", fileData);
            assertTrue(openResp.getBool("resumed"));

            Message query = new Message(MessageType.QUERY_MISSING).set("sessionId", sessionId);
            client2.send(query);
            Message missingResp = client2.receive();
            assertEquals(MessageType.MISSING_RESP, missingResp.getType());

            List<Integer> missing = toIntList(missingResp.getNumberList("missingChunks"));
            assertEquals(totalChunks - 2, missing.size());

            for (int idx : missing) {
                byte[] chunk = extractChunk(fileData, idx, harness.chunkSize);
                Message ack = sendUploadChunk(client2, sessionId, idx, chunk);
                assertEquals("OK", ack.getString("status"));
            }

            Message finalizeResp = finalizeUpload(client2, sessionId);
            assertEquals("COMPLETED", finalizeResp.getString("status"));
        }
    }

    @Test
    public void corruptChunkShouldBeRejectedAndRetryShouldPass() throws Exception {
        byte[] fileData = randomBytes((int) (1.2 * 1024 * 1024));
        String sessionId = UUID.randomUUID().toString();
        String fileId = UUID.randomUUID().toString();

        try (TestClient client = harness.newClient()) {
            Message openResp = openUpload(client, sessionId, fileId, "corrupt.bin", fileData);
            assertEquals(MessageType.OPEN_UPLOAD_RESP, openResp.getType());

            byte[] chunk0 = extractChunk(fileData, 0, harness.chunkSize);
            Message ack0 = sendUploadChunk(client, sessionId, 0, chunk0);
            assertEquals("OK", ack0.getString("status"));

            byte[] chunk1 = extractChunk(fileData, 1, harness.chunkSize);
            Message badChunk = new Message(MessageType.UPLOAD_CHUNK)
                    .set("sessionId", sessionId)
                    .set("chunkIndex", 1)
                    .set("chunkHash", "0000000000000000000000000000000000000000000000000000000000000000");
            badChunk.setData(chunk1);
            client.send(badChunk);
            Message badResp = client.receive();
            assertEquals(MessageType.ACK_CHUNK, badResp.getType());
            assertEquals("HASH_MISMATCH", badResp.getString("status"));

            Message ack1 = sendUploadChunk(client, sessionId, 1, chunk1);
            assertEquals("OK", ack1.getString("status"));

            byte[] chunk2 = extractChunk(fileData, 2, harness.chunkSize);
            Message ack2 = sendUploadChunk(client, sessionId, 2, chunk2);
            assertEquals("OK", ack2.getString("status"));

            Message finalizeResp = finalizeUpload(client, sessionId);
            assertEquals("COMPLETED", finalizeResp.getString("status"));
        }
    }

    @Test
    public void invalidChunkIndexAndSizeShouldNotDropConnection() throws Exception {
        int fileSize = harness.chunkSize + 16;
        byte[] fileData = randomBytes(fileSize);
        String sessionId = UUID.randomUUID().toString();
        String fileId = UUID.randomUUID().toString();

        try (TestClient client = harness.newClient()) {
            Message openResp = openUpload(client, sessionId, fileId, "invalid-index-size.bin", fileData);
            assertEquals(MessageType.OPEN_UPLOAD_RESP, openResp.getType());

            byte[] validChunk0 = extractChunk(fileData, 0, harness.chunkSize);

            Message negativeIdx = new Message(MessageType.UPLOAD_CHUNK)
                    .set("sessionId", sessionId)
                    .set("chunkIndex", -1)
                    .set("chunkHash", HashUtil.sha256(validChunk0));
            negativeIdx.setData(validChunk0);
            client.send(negativeIdx);
            Message negResp = client.receive();
            assertEquals(MessageType.ACK_CHUNK, negResp.getType());
            assertEquals("INVALID_CHUNK_INDEX", negResp.getString("status"));

            Message outOfRange = new Message(MessageType.UPLOAD_CHUNK)
                    .set("sessionId", sessionId)
                    .set("chunkIndex", 3)
                    .set("chunkHash", HashUtil.sha256(validChunk0));
            outOfRange.setData(validChunk0);
            client.send(outOfRange);
            Message outResp = client.receive();
            assertEquals(MessageType.ACK_CHUNK, outResp.getType());
            assertEquals("INVALID_CHUNK_INDEX", outResp.getString("status"));

            byte[] wrongSize = Arrays.copyOf(validChunk0, validChunk0.length - 1);
            Message invalidSize = new Message(MessageType.UPLOAD_CHUNK)
                    .set("sessionId", sessionId)
                    .set("chunkIndex", 0)
                    .set("chunkHash", HashUtil.sha256(wrongSize));
            invalidSize.setData(wrongSize);
            client.send(invalidSize);
            Message sizeResp = client.receive();
            assertEquals(MessageType.ACK_CHUNK, sizeResp.getType());
            assertEquals("INVALID_CHUNK_SIZE", sizeResp.getString("status"));

            Message ack0 = sendUploadChunk(client, sessionId, 0, validChunk0);
            assertEquals("OK", ack0.getString("status"));

            byte[] chunk1 = extractChunk(fileData, 1, harness.chunkSize);
            Message ack1 = sendUploadChunk(client, sessionId, 1, chunk1);
            assertEquals("OK", ack1.getString("status"));

            Message finalizeResp = finalizeUpload(client, sessionId);
            assertEquals("COMPLETED", finalizeResp.getString("status"));
        }
    }

    @Test
    public void finalizeIoErrorShouldReturnFinalizeResponse() throws Exception {
        byte[] fileData = randomBytes(128 * 1024);
        String sessionId = UUID.randomUUID().toString();
        String fileId = UUID.randomUUID().toString();

        try (TestClient client = harness.newClient()) {
            Message openResp = openUpload(client, sessionId, fileId, "finalize-io.bin", fileData);
            assertEquals(MessageType.OPEN_UPLOAD_RESP, openResp.getType());

            Message ack = sendUploadChunk(client, sessionId, 0, fileData);
            assertEquals("OK", ack.getString("status"));

            Path chunkPath = harness.tempDir.resolve(sessionId).resolve("chunk_0");
            Files.deleteIfExists(chunkPath);

            Message finalizeResp = finalizeUpload(client, sessionId);
            assertEquals(MessageType.FINALIZE_RESP, finalizeResp.getType());
            assertEquals("FINALIZE_IO_ERROR", finalizeResp.getString("status"));
        }
    }

    @Test
    public void downloadOutOfOrderShouldNotCompleteEarly() throws Exception {
        byte[] fileData = randomBytes((int) (1.5 * 1024 * 1024));
        UploadResult uploaded = uploadWholeFile("download-order.bin", fileData);

        try (TestClient client = harness.newClient()) {
            String downloadSessionId = UUID.randomUUID().toString();
            long expiry = client.ticketExpiry(3600);
            String sig = client.generateTicketSignature(downloadSessionId, uploaded.fileId, expiry);

            Message openDownload = new Message(MessageType.OPEN_DOWNLOAD)
                    .set("sessionId", downloadSessionId)
                    .set("fileId", uploaded.fileId)
                    .set("sha256Whole", uploaded.sha256Whole)
                    .set("downloaderId", "downloader-test")
                    .set("ticketNodeId", harness.nodeId)
                    .set("ticketExpiry", expiry)
                    .set("ticketSignature", sig);
            client.send(openDownload);
            Message openResp = client.receive();
            assertEquals(MessageType.OPEN_DOWNLOAD_RESP, openResp.getType());

            int lastChunk = openResp.getInt("totalChunks") - 1;

            Message reqLast = new Message(MessageType.REQUEST_CHUNK)
                    .set("sessionId", downloadSessionId)
                    .set("chunkIndex", lastChunk);
            client.send(reqLast);
            Message chunkLastResp = client.receive();
            assertEquals(MessageType.DOWNLOAD_CHUNK, chunkLastResp.getType());

            client.setReadTimeoutMillis(300);
            try {
                client.receive();
                fail("DOWNLOAD_COMPLETE must not be sent before all chunks are delivered");
            } catch (SocketTimeoutException expected) {
                // expected
            } finally {
                client.setReadTimeoutMillis(0);
            }

            Message req0 = new Message(MessageType.REQUEST_CHUNK)
                    .set("sessionId", downloadSessionId)
                    .set("chunkIndex", 0);
            client.send(req0);
            Message chunk0Resp = client.receive();
            assertEquals(MessageType.DOWNLOAD_CHUNK, chunk0Resp.getType());

            client.setReadTimeoutMillis(300);
            try {
                client.receive();
                fail("DOWNLOAD_COMPLETE must not be sent before missing chunks are delivered");
            } catch (SocketTimeoutException expected) {
                // expected
            } finally {
                client.setReadTimeoutMillis(0);
            }

            Message req1 = new Message(MessageType.REQUEST_CHUNK)
                    .set("sessionId", downloadSessionId)
                    .set("chunkIndex", 1);
            client.send(req1);
            Message chunk1Resp = client.receive();
            assertEquals(MessageType.DOWNLOAD_CHUNK, chunk1Resp.getType());

            Message completeResp = client.receive();
            assertEquals(MessageType.DOWNLOAD_COMPLETE, completeResp.getType());
            assertEquals(uploaded.sha256Whole, completeResp.getString("sha256Whole"));
        }
    }

    @Test
    public void keyExchangeBootstrapShouldAllowEncryptedUpload() throws Exception {
        byte[] fileData = randomBytes(64 * 1024);
        String sessionId = UUID.randomUUID().toString();
        String fileId = UUID.randomUUID().toString();

        try (TestClient client = harness.newClient()) {
            client.setupEncryption();

            Message openResp = openUpload(client, sessionId, fileId, "encrypted.bin", fileData);
            assertEquals(MessageType.OPEN_UPLOAD_RESP, openResp.getType());

            Message chunkMsg = new Message(MessageType.UPLOAD_CHUNK)
                    .set("sessionId", sessionId)
                    .set("chunkIndex", 0)
                    .set("chunkHash", HashUtil.sha256(fileData));
            chunkMsg.setData(client.encryptIfNeeded(fileData));
            client.send(chunkMsg);
            Message ack = client.receive();
            assertEquals(MessageType.ACK_CHUNK, ack.getType());
            assertEquals("OK", ack.getString("status"));

            Message finalizeResp = finalizeUpload(client, sessionId);
            assertEquals("COMPLETED", finalizeResp.getString("status"));
        }
    }

    @Test
    public void antivirusCleanScanShouldAllowCommit() throws Exception {
        byte[] fileData = randomBytes(64 * 1024);

        try (FakeClamdServer clamd = FakeClamdServer.clean()) {
            clamd.start();
            try (TestHarness scanHarness = new TestHarness(true, "127.0.0.1", clamd.getPort(), 1000)) {
                scanHarness.start();

                UploadResult uploaded = uploadWholeFile(scanHarness, "clean-scan.bin", fileData);

                assertTrue(scanHarness.fileStore.fileExists(uploaded.sha256Whole));
                assertTrue(scanHarness.dedupStore.exists(uploaded.sha256Whole));
                assertEquals(0, countFiles(scanHarness.quarantineDir));
            }
        }
    }

    @Test
    public void antivirusInfectedScanShouldQuarantineAndRejectCommit() throws Exception {
        byte[] fileData = "EICAR placeholder bytes".getBytes(StandardCharsets.UTF_8);
        String sessionId = UUID.randomUUID().toString();
        String fileId = UUID.randomUUID().toString();
        String sha256Whole = HashUtil.sha256(fileData);

        try (FakeClamdServer clamd = FakeClamdServer.infected("Eicar-Test-Signature")) {
            clamd.start();
            try (TestHarness scanHarness = new TestHarness(true, "127.0.0.1", clamd.getPort(), 1000)) {
                scanHarness.start();

                try (TestClient client = scanHarness.newClient()) {
                    Message openResp = openUpload(scanHarness, client, sessionId, fileId, "infected.txt", fileData);
                    assertEquals(MessageType.OPEN_UPLOAD_RESP, openResp.getType());

                    Message ack = sendUploadChunk(client, sessionId, 0, fileData);
                    assertEquals("OK", ack.getString("status"));

                    Message finalizeResp = finalizeUpload(client, sessionId);
                    assertEquals(MessageType.FINALIZE_RESP, finalizeResp.getType());
                    assertEquals("VIRUS_DETECTED", finalizeResp.getString("status"));
                    assertEquals("INFECTED", finalizeResp.getString("scanStatus"));
                    assertEquals("Eicar-Test-Signature", finalizeResp.getString("threatName"));
                }

                assertFalse(scanHarness.fileStore.fileExists(sha256Whole));
                assertFalse(scanHarness.dedupStore.exists(sha256Whole));
                assertEquals(2, countFiles(scanHarness.quarantineDir));
                assertFalse(Files.exists(scanHarness.tempDir.resolve(sessionId)));
            }
        }
    }

    @Test
    public void antivirusUnavailableShouldRejectCommitFailClosed() throws Exception {
        byte[] fileData = randomBytes(32 * 1024);
        String sessionId = UUID.randomUUID().toString();
        String fileId = UUID.randomUUID().toString();
        String sha256Whole = HashUtil.sha256(fileData);
        int unusedPort = pickFreePortForTest();

        try (TestHarness scanHarness = new TestHarness(true, "127.0.0.1", unusedPort, 300)) {
            scanHarness.start();

            try (TestClient client = scanHarness.newClient()) {
                Message openResp = openUpload(scanHarness, client, sessionId, fileId, "clamd-down.bin", fileData);
                assertEquals(MessageType.OPEN_UPLOAD_RESP, openResp.getType());

                Message ack = sendUploadChunk(client, sessionId, 0, fileData);
                assertEquals("OK", ack.getString("status"));

                Message finalizeResp = finalizeUpload(client, sessionId);
                assertEquals(MessageType.FINALIZE_RESP, finalizeResp.getType());
                assertEquals("SCAN_UNAVAILABLE", finalizeResp.getString("status"));
                assertEquals("UNAVAILABLE", finalizeResp.getString("scanStatus"));
            }

            assertFalse(scanHarness.fileStore.fileExists(sha256Whole));
            assertFalse(scanHarness.dedupStore.exists(sha256Whole));
            assertEquals(0, countFiles(scanHarness.quarantineDir));
            assertFalse(Files.exists(scanHarness.tempDir.resolve(sessionId)));
        }
    }

    @Test
    public void antivirusTimeoutShouldRejectCommitFailClosed() throws Exception {
        byte[] fileData = randomBytes(32 * 1024);
        String sessionId = UUID.randomUUID().toString();
        String fileId = UUID.randomUUID().toString();
        String sha256Whole = HashUtil.sha256(fileData);

        try (FakeClamdServer clamd = FakeClamdServer.timeout(1000)) {
            clamd.start();
            try (TestHarness scanHarness = new TestHarness(true, "127.0.0.1", clamd.getPort(), 150)) {
                scanHarness.start();

                try (TestClient client = scanHarness.newClient()) {
                    Message openResp = openUpload(scanHarness, client, sessionId, fileId, "clamd-timeout.bin", fileData);
                    assertEquals(MessageType.OPEN_UPLOAD_RESP, openResp.getType());

                    Message ack = sendUploadChunk(client, sessionId, 0, fileData);
                    assertEquals("OK", ack.getString("status"));

                    Message finalizeResp = finalizeUpload(client, sessionId);
                    assertEquals(MessageType.FINALIZE_RESP, finalizeResp.getType());
                    assertEquals("SCAN_TIMEOUT", finalizeResp.getString("status"));
                    assertEquals("TIMEOUT", finalizeResp.getString("scanStatus"));
                }

                assertFalse(scanHarness.fileStore.fileExists(sha256Whole));
                assertFalse(scanHarness.dedupStore.exists(sha256Whole));
                assertEquals(0, countFiles(scanHarness.quarantineDir));
            }
        }
    }

    @Test
    public void antivirusScanLimitShouldRejectBeforeCommit() throws Exception {
        byte[] fileData = randomBytes(2 * 1024);
        String sessionId = UUID.randomUUID().toString();
        String fileId = UUID.randomUUID().toString();
        String sha256Whole = HashUtil.sha256(fileData);

        try (FakeClamdServer clamd = FakeClamdServer.clean()) {
            clamd.start();
            try (TestHarness scanHarness = new TestHarness(
                    true, "127.0.0.1", clamd.getPort(), 1000, 1024L
            )) {
                scanHarness.start();

                try (TestClient client = scanHarness.newClient()) {
                    Message openResp = openUpload(scanHarness, client, sessionId, fileId, "too-large.bin", fileData);
                    assertEquals(MessageType.OPEN_UPLOAD_RESP, openResp.getType());

                    Message ack = sendUploadChunk(client, sessionId, 0, fileData);
                    assertEquals("OK", ack.getString("status"));

                    Message finalizeResp = finalizeUpload(client, sessionId);
                    assertEquals(MessageType.FINALIZE_RESP, finalizeResp.getType());
                    assertEquals("SCAN_LIMIT_EXCEEDED", finalizeResp.getString("status"));
                    assertEquals("LIMIT_EXCEEDED", finalizeResp.getString("scanStatus"));
                }

                assertFalse(scanHarness.fileStore.fileExists(sha256Whole));
                assertFalse(scanHarness.dedupStore.exists(sha256Whole));
                assertEquals(0, countFiles(scanHarness.quarantineDir));
                assertFalse(Files.exists(scanHarness.tempDir.resolve(sessionId)));
            }
        }
    }

    private UploadResult uploadWholeFile(String fileName, byte[] fileData) throws Exception {
        return uploadWholeFile(harness, fileName, fileData);
    }

    private UploadResult uploadWholeFile(TestHarness targetHarness, String fileName, byte[] fileData) throws Exception {
        String sessionId = UUID.randomUUID().toString();
        String fileId = UUID.randomUUID().toString();
        String sha256Whole = HashUtil.sha256(fileData);
        int totalChunks = totalChunks(fileData.length, targetHarness);

        try (TestClient client = targetHarness.newClient()) {
            Message openResp = openUpload(targetHarness, client, sessionId, fileId, fileName, fileData);
            assertEquals(MessageType.OPEN_UPLOAD_RESP, openResp.getType());
            assertFalse(openResp.getBool("dedup"));

            for (int i = 0; i < totalChunks; i++) {
                byte[] chunk = extractChunk(fileData, i, targetHarness.chunkSize);
                Message ack = sendUploadChunk(client, sessionId, i, chunk);
                assertEquals("OK", ack.getString("status"));
            }

            Message finalizeResp = finalizeUpload(client, sessionId);
            assertEquals("COMPLETED", finalizeResp.getString("status"));
        }

        return new UploadResult(fileId, sha256Whole);
    }

    private Message openUpload(TestClient client, String sessionId, String fileId, String fileName, byte[] fileData) throws Exception {
        return openUpload(harness, client, sessionId, fileId, fileName, fileData);
    }

    private Message openUpload(TestHarness targetHarness, TestClient client, String sessionId,
                               String fileId, String fileName, byte[] fileData) throws Exception {
        long expiry = client.ticketExpiry(3600);
        String sig = client.generateTicketSignature(sessionId, fileId, expiry);

        Message openMsg = new Message(MessageType.OPEN_UPLOAD)
                .set("sessionId", sessionId)
                .set("fileId", fileId)
                .set("fileName", fileName)
                .set("sha256Whole", HashUtil.sha256(fileData))
                .set("fileSize", fileData.length)
                .set("totalChunks", totalChunks(fileData.length, targetHarness))
                .set("uploaderId", "uploader-test")
                .set("ticketNodeId", targetHarness.nodeId)
                .set("ticketExpiry", expiry)
                .set("ticketSignature", sig);

        client.send(openMsg);
        return client.receive();
    }

    private Message sendUploadChunk(TestClient client, String sessionId, int chunkIndex, byte[] chunkData) throws Exception {
        Message chunkMsg = new Message(MessageType.UPLOAD_CHUNK)
                .set("sessionId", sessionId)
                .set("chunkIndex", chunkIndex)
                .set("chunkHash", HashUtil.sha256(chunkData));
        chunkMsg.setData(client.encryptIfNeeded(chunkData));
        client.send(chunkMsg);
        return client.receive();
    }

    private Message finalizeUpload(TestClient client, String sessionId) throws Exception {
        Message finalizeMsg = new Message(MessageType.FINALIZE_UPLOAD).set("sessionId", sessionId);
        client.send(finalizeMsg);
        return client.receive();
    }

    private static byte[] extractChunk(byte[] data, int chunkIndex, int chunkSize) {
        int offset = chunkIndex * chunkSize;
        int len = Math.min(chunkSize, data.length - offset);
        byte[] chunk = new byte[len];
        System.arraycopy(data, offset, chunk, 0, len);
        return chunk;
    }

    private static int totalChunks(int fileSize) {
        return (int) Math.ceil((double) fileSize / harness.chunkSize);
    }

    private static int totalChunks(int fileSize, TestHarness targetHarness) {
        return (int) Math.ceil((double) fileSize / targetHarness.chunkSize);
    }

    private static byte[] randomBytes(int size) {
        byte[] data = new byte[size];
        RNG.nextBytes(data);
        return data;
    }

    private static int pickFreePortForTest() throws IOException {
        try (ServerSocket socket = new ServerSocket(0)) {
            return socket.getLocalPort();
        }
    }

    private static int countFiles(Path dir) throws IOException {
        if (dir == null || !Files.exists(dir)) return 0;
        int count = 0;
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir)) {
            for (Path ignored : stream) {
                count++;
            }
        }
        return count;
    }

    private static List<Integer> toIntList(List<Double> raw) {
        List<Integer> out = new ArrayList<>();
        if (raw == null) return out;
        for (Double d : raw) {
            out.add(d.intValue());
        }
        return out;
    }

    private static class UploadResult {
        private final String fileId;
        private final String sha256Whole;

        private UploadResult(String fileId, String sha256Whole) {
            this.fileId = fileId;
            this.sha256Whole = sha256Whole;
        }
    }

    private static class FakeClamdServer implements AutoCloseable {

        private enum Mode {
            CLEAN,
            INFECTED,
            TIMEOUT
        }

        private final Mode mode;
        private final String threatName;
        private final long delayMs;

        private ServerSocket serverSocket;
        private Thread thread;
        private volatile boolean running;

        private FakeClamdServer(Mode mode, String threatName, long delayMs) {
            this.mode = mode;
            this.threatName = threatName;
            this.delayMs = delayMs;
        }

        static FakeClamdServer clean() {
            return new FakeClamdServer(Mode.CLEAN, null, 0L);
        }

        static FakeClamdServer infected(String threatName) {
            return new FakeClamdServer(Mode.INFECTED, threatName, 0L);
        }

        static FakeClamdServer timeout(long delayMs) {
            return new FakeClamdServer(Mode.TIMEOUT, null, delayMs);
        }

        void start() throws IOException {
            serverSocket = new ServerSocket(0);
            running = true;
            thread = new Thread(this::serveLoop, "fake-clamd");
            thread.setDaemon(true);
            thread.start();
        }

        int getPort() {
            return serverSocket.getLocalPort();
        }

        private void serveLoop() {
            while (running) {
                try (Socket socket = serverSocket.accept()) {
                    handle(socket);
                } catch (IOException e) {
                    if (running) {
                        e.printStackTrace();
                    }
                }
            }
        }

        private void handle(Socket socket) throws IOException {
            String command = readCommand(socket.getInputStream());
            String path = command.startsWith("zSCAN ")
                    ? command.substring("zSCAN ".length())
                    : "stream";

            if (mode == Mode.TIMEOUT) {
                try {
                    Thread.sleep(delayMs);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
                return;
            }

            String response;
            if (mode == Mode.INFECTED) {
                response = path + ": " + threatName + " FOUND\0";
            } else {
                response = path + ": OK\0";
            }

            socket.getOutputStream().write(response.getBytes(StandardCharsets.UTF_8));
            socket.getOutputStream().flush();
        }

        private static String readCommand(InputStream in) throws IOException {
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            int b;
            while ((b = in.read()) != -1) {
                if (b == 0 || b == '\n') {
                    break;
                }
                buffer.write(b);
            }
            return new String(buffer.toByteArray(), StandardCharsets.UTF_8);
        }

        @Override
        public void close() throws Exception {
            running = false;
            if (serverSocket != null) {
                serverSocket.close();
            }
            if (thread != null) {
                thread.join(TimeUnit.SECONDS.toMillis(2));
            }
        }
    }

    private static class TestHarness implements AutoCloseable {

        private final String nodeId = "node-test";
        private final String ticketSecret = "TEST_shared_secret";
        private final String host = "127.0.0.1";
        private final int chunkSize = 524288;

        private Path rootDir;
        private Path dataDir;
        private Path tempDir;
        private Path metaDir;
        private Path quarantineDir;
        private int port;
        private FileStore fileStore;
        private DedupStore dedupStore;
        private StorageServer server;
        private Thread serverThread;
        private final boolean antivirusEnabled;
        private final String antivirusHost;
        private final int antivirusPort;
        private final int antivirusTimeoutMs;
        private final long antivirusMaxScanBytes;

        private TestHarness() {
            this(false, "127.0.0.1", 3310, 30000);
        }

        private TestHarness(boolean antivirusEnabled, String antivirusHost,
                            int antivirusPort, int antivirusTimeoutMs) {
            this(antivirusEnabled, antivirusHost, antivirusPort, antivirusTimeoutMs, 104857600L);
        }

        private TestHarness(boolean antivirusEnabled, String antivirusHost,
                            int antivirusPort, int antivirusTimeoutMs,
                            long antivirusMaxScanBytes) {
            this.antivirusEnabled = antivirusEnabled;
            this.antivirusHost = antivirusHost;
            this.antivirusPort = antivirusPort;
            this.antivirusTimeoutMs = antivirusTimeoutMs;
            this.antivirusMaxScanBytes = antivirusMaxScanBytes;
        }

        void start() throws Exception {
            Logger rootLogger = Logger.getLogger("");
            rootLogger.setLevel(Level.WARNING);
            for (Handler handler : rootLogger.getHandlers()) {
                handler.setLevel(Level.WARNING);
            }

            rootDir = Files.createTempDirectory("storage-node-it-");
            dataDir = rootDir.resolve("data").resolve("store");
            tempDir = rootDir.resolve("data").resolve("temp");
            metaDir = rootDir.resolve("data").resolve("meta");
            quarantineDir = rootDir.resolve("data").resolve("quarantine");
            Path logDir = rootDir.resolve("logs");

            Files.createDirectories(dataDir);
            Files.createDirectories(tempDir);
            Files.createDirectories(metaDir);
            Files.createDirectories(quarantineDir);
            Files.createDirectories(logDir);

            port = pickFreePort();
            Path propsFile = rootDir.resolve("storage-node.properties");
            writeConfig(propsFile, logDir);

            NodeConfig config = new NodeConfig(propsFile.toString());
            fileStore = new FileStore(
                    config.getDataDir(),
                    config.getTempDir(),
                    config.getQuarantineDir(),
                    config.getChunkSize()
            );
            dedupStore = new DedupStore(config.getMetaDir());
            SessionManager sessionManager = new SessionManager(fileStore, 60, 30);
            RSAKeyExchange rsaKeyExchange = new RSAKeyExchange(config.getRsaKeySize());
            CoordinatorClient coordinator = new CoordinatorClient(
                    config.getTicketSecret(),
                    config.getNodeId(),
                    config.getCoordinatorHost(),
                    config.getCoordinatorPort(),
                    config.getAdvertisedHost(),
                    config.getAdvertisedPort(),
                    config.getStorageAddress()
            );
            AntivirusScanner antivirusScanner = antivirusEnabled
                    ? new ClamAvClient(antivirusHost, antivirusPort, antivirusTimeoutMs)
                    : new NoOpAntivirusScanner();

            server = new StorageServer(
                    config, sessionManager, fileStore, dedupStore,
                    coordinator, rsaKeyExchange, antivirusScanner
            );
            serverThread = new Thread(() -> {
                try {
                    server.start();
                } catch (IOException ignored) {
                    // server is expected to throw when stopped
                }
            }, "storage-node-it-server");
            serverThread.setDaemon(true);
            serverThread.start();

            waitForServer();
        }

        TestClient newClient() throws IOException {
            return new TestClient(host, port, nodeId, ticketSecret);
        }

        @Override
        public void close() throws Exception {
            if (server != null) {
                server.stop();
            }
            if (serverThread != null) {
                serverThread.join(TimeUnit.SECONDS.toMillis(5));
            }
            deleteRecursively(rootDir);
        }

        private void waitForServer() throws Exception {
            long deadline = System.currentTimeMillis() + 5000;
            while (System.currentTimeMillis() < deadline) {
                try (Socket ignored = new Socket(host, port)) {
                    return;
                } catch (IOException e) {
                    Thread.sleep(100);
                }
            }
            throw new IllegalStateException("Storage server did not start in time");
        }

        private void writeConfig(Path propsFile, Path logDir) throws IOException {
            Properties props = new Properties();
            props.setProperty("node.port", String.valueOf(port));
            props.setProperty("node.host", host);
            props.setProperty("node.id", nodeId);
            props.setProperty("node.advertised.host", host);
            props.setProperty("node.advertised.port", String.valueOf(port));
            props.setProperty("node.storage.address", host + ":" + port);

            props.setProperty("storage.data.dir", dataDir.toString());
            props.setProperty("storage.temp.dir", tempDir.toString());
            props.setProperty("storage.meta.dir", metaDir.toString());
            props.setProperty("antivirus.enabled", String.valueOf(antivirusEnabled));
            props.setProperty("antivirus.host", antivirusHost);
            props.setProperty("antivirus.port", String.valueOf(antivirusPort));
            props.setProperty("antivirus.timeout.ms", String.valueOf(antivirusTimeoutMs));
            props.setProperty("antivirus.max.scan.bytes", String.valueOf(antivirusMaxScanBytes));
            props.setProperty("antivirus.quarantine.dir", quarantineDir.toString());
            props.setProperty("antivirus.fail.closed", "true");

            props.setProperty("chunk.size", String.valueOf(chunkSize));
            props.setProperty("coordinator.host", host);
            props.setProperty("coordinator.port", "18000");
            props.setProperty("ticket.secret", ticketSecret);
            props.setProperty("rsa.keysize", "2048");
            props.setProperty("aes.keysize", "256");
            props.setProperty("session.upload.timeout.minutes", "60");
            props.setProperty("session.download.timeout.minutes", "30");
            props.setProperty("server.thread.pool.size", "12");
            props.setProperty("log.level", "WARNING");
            props.setProperty("log.dir", logDir.toString());

            try (java.io.OutputStream os = Files.newOutputStream(propsFile)) {
                props.store(os, "Test config");
            }
        }

        private static int pickFreePort() throws IOException {
            try (ServerSocket socket = new ServerSocket(0)) {
                return socket.getLocalPort();
            }
        }

        private static void deleteRecursively(Path root) throws IOException {
            if (root == null || !Files.exists(root)) return;
            List<Path> paths = new ArrayList<>();
            Files.walk(root).forEach(paths::add);
            Collections.reverse(paths);
            for (Path p : paths) {
                Files.deleteIfExists(p);
            }
        }
    }
}
