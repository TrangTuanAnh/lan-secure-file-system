package storagenode.network;

import storagenode.crypto.HashUtil;
import storagenode.storage.FileStore;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Collections;
import java.util.logging.Logger;

/**
 * Handles communication with the Coordinator server.
 *
 * In the current implementation, ticket verification is done locally using
 * HMAC-SHA256 with a shared secret (configured in both Coordinator and Node).
 *
 * Ticket format (JSON fields from Coordinator):
 *   sessionId  : unique session identifier
 *   fileId     : file identifier
 *   nodeId     : target node ID
 *   expiry     : Unix timestamp (seconds) when ticket expires
 *   signature  : HMAC-SHA256(sessionId|fileId|nodeId|expiry, secret)
 *
 * During integration with Person 1's Coordinator, this can be extended
 * to make HTTP/socket calls for richer verification.
 */
public class CoordinatorClient {

    private static final Logger LOG = Logger.getLogger(CoordinatorClient.class.getName());
    private static final String HMAC_ALGO = "HmacSHA256";

    private final String ticketSecret;
    private final String nodeId;
    private final String coordinatorHost;
    private final int coordinatorPort;
    private final String dataHost;
    private final int dataPort;
    private final String storageAddress;
    private final ControlPlaneClient controlPlaneClient;

    public CoordinatorClient(String ticketSecret, String nodeId,
                             String coordinatorHost, int coordinatorPort,
                             String dataHost, int dataPort, String storageAddress) {
        this(ticketSecret, nodeId, coordinatorHost, coordinatorPort,
             dataHost, dataPort, storageAddress, null);
    }

    public CoordinatorClient(String ticketSecret, String nodeId,
                             String coordinatorHost, int coordinatorPort,
                             String dataHost, int dataPort, String storageAddress,
                             FileStore fileStore) {
        this.ticketSecret = ticketSecret;
        this.nodeId = nodeId;
        this.coordinatorHost = coordinatorHost;
        this.coordinatorPort = coordinatorPort;
        this.dataHost = dataHost;
        this.dataPort = dataPort;
        this.storageAddress = storageAddress;

        // Initialize control plane client for persistent connection.
        // FileStore is passed so STORAGE_AUTH carries the current manifest.
        this.controlPlaneClient = new ControlPlaneClient(
            coordinatorHost, coordinatorPort, ticketSecret, nodeId,
            dataHost, dataPort, storageAddress, fileStore
        );
    }

    /**
     * Verify an upload/download ticket locally using HMAC.
     *
     * @return true if the ticket is valid and not expired
     */
    public boolean verifyTicket(String sessionId, String fileId,
                                 String ticketNodeId, long expiry, String signature) {
        // 1. Check node ID matches
        if (!nodeId.equals(ticketNodeId)) {
            LOG.warning("Ticket node mismatch: expected=" + nodeId + " got=" + ticketNodeId);
            return false;
        }

        // 2. Check expiry
        long now = Instant.now().getEpochSecond();
        if (now > expiry) {
            LOG.warning("Ticket expired: expiry=" + expiry + " now=" + now);
            return false;
        }

        // 3. Verify HMAC signature
        String payload = sessionId + "|" + fileId + "|" + ticketNodeId + "|" + expiry;
        String expectedSig = computeHmac(payload);
        if (expectedSig == null || !expectedSig.equals(signature)) {
            LOG.warning("Ticket signature mismatch for session " + sessionId);
            return false;
        }

        LOG.info("Ticket verified: session=" + sessionId);
        return true;
    }

    /**
     * Generate a ticket signature (used for testing / by Coordinator).
     */
    public String generateTicketSignature(String sessionId, String fileId,
                                           String ticketNodeId, long expiry) {
        String payload = sessionId + "|" + fileId + "|" + ticketNodeId + "|" + expiry;
        return computeHmac(payload);
    }

    /**
     * Connect to Coordinator control plane.
     * Should be called during Storage Node startup.
     */
    public void connect() throws java.io.IOException {
        controlPlaneClient.connect();
    }
    
    /**
     * Disconnect from Coordinator control plane.
     * Should be called during Storage Node shutdown.
     */
    public void disconnect() {
        controlPlaneClient.disconnect();
    }
    
    /**
     * Check if connected to Coordinator.
     */
    public boolean isConnected() {
        return controlPlaneClient.isConnected();
    }

    /**
     * Notify the Coordinator that an upload has been finalized.
     * Sends UPLOAD_COMPLETE message via control plane connection.
     */
    public void notifyUploadComplete(String fileId, String sha256Whole, long fileSize) {
        // Generate stored name based on hash (first 2 chars as subdirectory)
        String storedName = "data/store/" + sha256Whole.substring(0, 2) + "/" + sha256Whole;

        // Delegate to control plane client
        controlPlaneClient.notifyUploadComplete(fileId, sha256Whole, storedName, fileSize);

        // Keep the Coordinator's per-node manifest in sync. The Coordinator
        // also adds this sha implicitly on UPLOAD_COMPLETE; this delta covers
        // dedup-hit cases where notifyUploadComplete runs without a real new
        // file having been just stored on disk (sha was already present).
        controlPlaneClient.sendManifestDelta(
            Collections.singletonList(sha256Whole),
            Collections.emptyList()
        );
    }

    /**
     * Notify the Coordinator that an upload has failed.
     * Sends UPLOAD_FAILED message via control plane connection.
     */
    public void notifyUploadFailed(String fileId, String reason) {
        // Delegate to control plane client
        controlPlaneClient.notifyUploadFailed(fileId, reason);
    }

    private String computeHmac(String payload) {
        try {
            Mac mac = Mac.getInstance(HMAC_ALGO);
            SecretKeySpec keySpec = new SecretKeySpec(
                ticketSecret.getBytes(StandardCharsets.UTF_8), HMAC_ALGO);
            mac.init(keySpec);
            byte[] hmacBytes = mac.doFinal(payload.getBytes(StandardCharsets.UTF_8));
            return HashUtil.bytesToHex(hmacBytes);
        } catch (Exception e) {
            LOG.severe("HMAC computation failed: " + e.getMessage());
            return null;
        }
    }
}
