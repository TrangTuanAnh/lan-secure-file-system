package storagenode.network;

import storagenode.crypto.HashUtil;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
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

    public CoordinatorClient(String ticketSecret, String nodeId,
                             String coordinatorHost, int coordinatorPort) {
        this.ticketSecret = ticketSecret;
        this.nodeId = nodeId;
        this.coordinatorHost = coordinatorHost;
        this.coordinatorPort = coordinatorPort;
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
     * Notify the Coordinator that an upload has been finalized.
     * In a full integration, this sends a message to the Coordinator's control plane.
     * Currently logs the event for integration later.
     */
    public void notifyUploadComplete(String fileId, String sha256Whole, long fileSize) {
        // TODO: Send COMMIT_UPLOAD notification to Coordinator via socket/HTTP
        LOG.info("NOTIFY_COORDINATOR: Upload complete fileId=" + fileId +
                 " sha256=" + sha256Whole + " size=" + fileSize);
    }

    /**
     * Notify the Coordinator that an upload has failed.
     */
    public void notifyUploadFailed(String fileId, String reason) {
        // TODO: Send failure notification to Coordinator
        LOG.info("NOTIFY_COORDINATOR: Upload failed fileId=" + fileId +
                 " reason=" + reason);
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
