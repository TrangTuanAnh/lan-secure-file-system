package storagenode.protocol;

/**
 * All message types for the data plane protocol.
 *
 * Convention:
 *   - Client -> Node requests have no suffix
 *   - Node -> Client responses end with _RESP
 */
public enum MessageType {

    // ── Encryption handshake ──
    KEY_EXCHANGE,           // Client sends RSA-encrypted AES key
    KEY_EXCHANGE_RESP,      // Node confirms encrypted session ready

    // ── Upload ──
    OPEN_UPLOAD,            // Client opens upload session with ticket
    OPEN_UPLOAD_RESP,       // Node returns session info
    UPLOAD_CHUNK,           // Client sends one chunk (header + binary data)
    ACK_CHUNK,              // Node acknowledges chunk receipt
    QUERY_MISSING,          // Client asks which chunks are missing
    MISSING_RESP,           // Node returns list of missing chunk indices
    FINALIZE_UPLOAD,        // Client signals all chunks sent
    FINALIZE_RESP,          // Node returns finalization result (hash match, etc.)

    // ── Download ──
    OPEN_DOWNLOAD,          // Client opens download session with ticket
    OPEN_DOWNLOAD_RESP,     // Node returns file info (size, totalChunks, etc.)
    REQUEST_CHUNK,          // Client requests a specific chunk by index
    DOWNLOAD_CHUNK,         // Node sends a chunk (header + binary data)
    DOWNLOAD_COMPLETE,      // Node signals all requested chunks sent

    // ── Dedup (internal, Coordinator -> Node) ──
    CHECK_OBJECT,           // Check if object exists by sha256
    CHECK_OBJECT_RESP,      // Response: exists or not

    // ── General ──
    ERROR;                  // Error response

    public static MessageType fromString(String s) {
        try {
            return valueOf(s);
        } catch (IllegalArgumentException e) {
            return null;
        }
    }
}
