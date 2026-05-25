package storagenode.network;

import storagenode.protocol.ControlPlaneFrameCodec;
import storagenode.protocol.Message;
import storagenode.protocol.MessageType;
import storagenode.storage.FileStore;

import java.io.*;
import java.net.Socket;
import java.util.Collection;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.*;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Persistent socket connection to Coordinator Server control plane.
 * 
 * Handles:
 * - Authentication (STORAGE_AUTH)
 * - Heartbeat (PING/PONG)
 * - Upload notifications (UPLOAD_COMPLETE, UPLOAD_FAILED)
 * - Optional ticket verification (VERIFY_TICKET)
 * 
 * This client maintains a persistent connection and automatically
 * sends heartbeat pings every 30 seconds to keep the connection alive.
 */
public class ControlPlaneClient {
    private static final Logger LOG = Logger.getLogger(ControlPlaneClient.class.getName());
    
    private static final int HEARTBEAT_INTERVAL_SECONDS = 30;
    private static final int CONNECT_TIMEOUT_MS = 10000;
    private static final int RESPONSE_TIMEOUT_MS = 5000;
    
    private final String coordinatorHost;
    private final int coordinatorPort;
    private final String sharedSecret;
    private final String nodeId;
    private final String dataHost;
    private final int dataPort;
    private final String storageAddress;
    private final FileStore fileStore;
    
    private Socket socket;
    private InputStream in;
    private OutputStream out;
    private volatile boolean running = false;
    private volatile boolean authenticated = false;
    
    private ScheduledExecutorService heartbeatExecutor;
    private Thread receiverThread;
    
    private final BlockingQueue<Message> responseQueue = new LinkedBlockingQueue<>();
    
    public ControlPlaneClient(String coordinatorHost, int coordinatorPort,
                              String sharedSecret, String nodeId,
                              String dataHost, int dataPort, String storageAddress) {
        this(coordinatorHost, coordinatorPort, sharedSecret, nodeId,
             dataHost, dataPort, storageAddress, null);
    }

    public ControlPlaneClient(String coordinatorHost, int coordinatorPort,
                              String sharedSecret, String nodeId,
                              String dataHost, int dataPort, String storageAddress,
                              FileStore fileStore) {
        this.coordinatorHost = coordinatorHost;
        this.coordinatorPort = coordinatorPort;
        this.sharedSecret = sharedSecret;
        this.nodeId = nodeId;
        this.dataHost = dataHost;
        this.dataPort = dataPort;
        this.storageAddress = storageAddress;
        this.fileStore = fileStore;
    }
    
    /**
     * Connect to Coordinator and authenticate.
     * 
     * @throws IOException if connection or authentication fails
     */
    public void connect() throws IOException {
        LOG.info("Connecting to Coordinator: " + coordinatorHost + ":" + coordinatorPort);
        
        try {
            socket = new Socket();
            socket.connect(new java.net.InetSocketAddress(coordinatorHost, coordinatorPort), 
                          CONNECT_TIMEOUT_MS);
            socket.setSoTimeout(0); // No timeout for blocking reads
            
            in = new BufferedInputStream(socket.getInputStream());
            out = new BufferedOutputStream(socket.getOutputStream());
            running = true;
            
            // Start message receiver thread
            receiverThread = new Thread(this::receiveLoop, "ControlPlane-Receiver");
            receiverThread.setDaemon(true);
            receiverThread.start();
            
            // Send STORAGE_AUTH
            authenticate();
            
            // Start heartbeat thread
            startHeartbeat();
            
            LOG.info("Connected to Coordinator successfully");
            
        } catch (IOException e) {
            cleanup();
            throw new IOException("Failed to connect to Coordinator: " + e.getMessage(), e);
        }
    }
    
    /**
     * Authenticate with Coordinator using shared secret.
     * 
     * @throws IOException if authentication fails
     */
    private void authenticate() throws IOException {
        List<String> manifest = collectManifest();

        Message authMsg = new Message(MessageType.STORAGE_AUTH)
            .set("secret", sharedSecret)
            .set("nodeId", nodeId)
            .set("dataHost", dataHost)
            .set("dataPort", dataPort)
            .set("storageAddress", storageAddress)
            .set("manifest", manifest);

        LOG.info("Sending STORAGE_AUTH with manifest: " + manifest.size() + " file(s)");

        sendMessage(authMsg);
        
        // Wait for STORAGE_AUTH_RESPONSE
        Message response = waitForResponse(RESPONSE_TIMEOUT_MS);
        
        if (response == null) {
            throw new IOException("Authentication timeout - no response from Coordinator");
        }
        
        if (response.getType() == MessageType.ERROR) {
            String errorMsg = response.getString("message");
            throw new IOException("Authentication failed: " + errorMsg);
        }
        
        if (response.getType() != MessageType.STORAGE_AUTH_RESPONSE) {
            throw new IOException("Unexpected response type: " + response.getType());
        }
        
        String status = response.getString("status");
        if (!"authenticated".equals(status)) {
            throw new IOException("Authentication rejected: " + status);
        }
        
        authenticated = true;
        LOG.info("Authenticated with Coordinator");
    }
    
    /**
     * Start heartbeat thread that sends PING every 30 seconds.
     */
    private void startHeartbeat() {
        heartbeatExecutor = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "ControlPlane-Heartbeat");
            t.setDaemon(true);
            return t;
        });
        
        heartbeatExecutor.scheduleAtFixedRate(() -> {
            try {
                if (authenticated && running) {
                    sendPing();
                }
            } catch (Exception e) {
                // BUGFIX M20: on heartbeat I/O failure, trigger cleanup so
                // the outer reconnect loop can rebuild the connection,
                // instead of spamming this warning every 30s forever.
                LOG.warning("Heartbeat failed: " + e.getMessage() + " — triggering cleanup");
                try {
                    cleanup();
                } catch (Exception ignored) {}
            }
        }, HEARTBEAT_INTERVAL_SECONDS, HEARTBEAT_INTERVAL_SECONDS, TimeUnit.SECONDS);
        
        LOG.info("Heartbeat started (interval: " + HEARTBEAT_INTERVAL_SECONDS + "s)");
    }
    
    /**
     * Send PING to Coordinator.
     */
    private void sendPing() throws IOException {
        Message ping = new Message(MessageType.PING);
        sendMessage(ping);
        LOG.fine("PING sent to Coordinator");
    }
    
    /**
     * Notify Coordinator that upload completed successfully.
     * 
     * @param fileId File identifier
     * @param sha256Whole SHA-256 hash of complete file
     * @param storedName Storage path on this node
     * @param finalSize Final file size in bytes
     */
    public void notifyUploadComplete(String fileId, String sha256Whole, 
                                      String storedName, long finalSize) {
        if (!authenticated || !running) {
            LOG.warning("Cannot send UPLOAD_COMPLETE - not connected/authenticated");
            return;
        }
        
        try {
            Message msg = new Message(MessageType.UPLOAD_COMPLETE)
                .set("fileId", fileId)
                .set("sha256Whole", sha256Whole)
                .set("storedName", storedName)
                .set("finalSize", finalSize);
            
            sendMessage(msg);
            LOG.info("UPLOAD_COMPLETE sent: fileId=" + fileId + ", size=" + finalSize);
            
        } catch (IOException e) {
            LOG.severe("Failed to send UPLOAD_COMPLETE: " + e.getMessage());
        }
    }
    
    /**
     * Read the current set of stored sha256 hashes for the STORAGE_AUTH manifest.
     */
    private List<String> collectManifest() {
        if (fileStore == null) {
            return Collections.emptyList();
        }
        try {
            return fileStore.listStoredFiles();
        } catch (IOException e) {
            LOG.log(Level.WARNING, "Failed to read manifest from FileStore: " + e.getMessage(), e);
            return Collections.emptyList();
        }
    }

    /**
     * Send an incremental manifest update so the Coordinator's view of
     * which files this node holds stays in sync. Best-effort: failures
     * are logged but do not throw.
     */
    public void sendManifestDelta(Collection<String> added, Collection<String> removed) {
        if (!authenticated || !running) {
            LOG.warning("Cannot send MANIFEST_DELTA - not connected/authenticated");
            return;
        }
        try {
            Message msg = new Message(MessageType.MANIFEST_DELTA)
                .set("added", added == null ? Collections.emptyList() : added)
                .set("removed", removed == null ? Collections.emptyList() : removed);
            sendMessage(msg);
            LOG.info("MANIFEST_DELTA sent: +"
                + (added == null ? 0 : added.size())
                + " -" + (removed == null ? 0 : removed.size()));
        } catch (IOException e) {
            LOG.severe("Failed to send MANIFEST_DELTA: " + e.getMessage());
        }
    }

    /**
     * Notify Coordinator that upload failed.
     * 
     * @param fileId File identifier
     * @param reason Failure reason
     */
    public void notifyUploadFailed(String fileId, String reason) {
        if (!authenticated || !running) {
            LOG.warning("Cannot send UPLOAD_FAILED - not connected/authenticated");
            return;
        }
        
        try {
            Message msg = new Message(MessageType.UPLOAD_FAILED)
                .set("fileId", fileId)
                .set("reason", reason);
            
            sendMessage(msg);
            LOG.info("UPLOAD_FAILED sent: fileId=" + fileId + ", reason=" + reason);
            
        } catch (IOException e) {
            LOG.severe("Failed to send UPLOAD_FAILED: " + e.getMessage());
        }
    }
    
    /**
     * Verify ticket via Coordinator (optional, alternative to local HMAC).
     * 
     * @param ticketId Ticket identifier
     * @return true if ticket is valid
     */
    public boolean verifyTicketRemote(String ticketId) {
        if (!authenticated || !running) {
            LOG.warning("Cannot verify ticket - not connected/authenticated");
            return false;
        }
        
        try {
            Message msg = new Message(MessageType.VERIFY_TICKET)
                .set("ticket", ticketId);
            
            sendMessage(msg);
            
            // Wait for response
            Message response = waitForResponse(RESPONSE_TIMEOUT_MS);
            
            if (response == null) {
                LOG.warning("Ticket verification timeout for: " + ticketId);
                return false;
            }
            
            if (response.getType() == MessageType.TICKET_VALID) {
                LOG.info("Ticket verified: " + ticketId);
                return true;
            } else if (response.getType() == MessageType.TICKET_INVALID) {
                String error = response.getString("error");
                LOG.warning("Ticket invalid: " + ticketId + ", error=" + error);
                return false;
            } else {
                LOG.warning("Unexpected response for ticket verification: " + response.getType());
                return false;
            }
            
        } catch (Exception e) {
            LOG.severe("Failed to verify ticket: " + e.getMessage());
            return false;
        }
    }
    
    /**
     * Message receiver loop - runs in background thread.
     */
    private void receiveLoop() {
        LOG.info("Control plane receiver thread started");
        
        while (running) {
            try {
                Message msg = ControlPlaneFrameCodec.readFrame(in);
                
                if (msg == null) {
                    LOG.info("Connection closed by Coordinator");
                    break;
                }
                
                handleMessage(msg);
                
            } catch (IOException e) {
                if (running) {
                    LOG.warning("Connection lost: " + e.getMessage());
                }
                break;
            } catch (Exception e) {
                LOG.severe("Error in receive loop: " + e.getMessage());
            }
        }
        
        LOG.info("Control plane receiver thread stopped");
        cleanup();
    }
    
    /**
     * Handle received message.
     */
    private void handleMessage(Message msg) {
        MessageType type = msg.getType();
        
        switch (type) {
            case PONG:
                LOG.fine("PONG received");
                break;
                
            case ACK:
                LOG.fine("ACK received");
                break;
                
            case ERROR:
                String errorMsg = msg.getString("message");
                LOG.warning("ERROR from Coordinator: " + errorMsg);
                break;
                
            case STORAGE_AUTH_RESPONSE:
            case TICKET_VALID:
            case TICKET_INVALID:
                // These are responses - put in queue for waiting thread
                try {
                    responseQueue.offer(msg, 1, TimeUnit.SECONDS);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
                break;
                
            default:
                LOG.fine("Received: " + type);
        }
    }
    
    /**
     * Send message to Coordinator.
     */
    private synchronized void sendMessage(Message msg) throws IOException {
        if (!running) {
            throw new IOException("Connection is closed");
        }
        ControlPlaneFrameCodec.writeFrame(out, msg);
    }
    
    /**
     * Wait for response message with timeout.
     */
    private Message waitForResponse(long timeoutMs) {
        try {
            return responseQueue.poll(timeoutMs, TimeUnit.MILLISECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return null;
        }
    }
    
    /**
     * Check if connected and authenticated.
     */
    public boolean isConnected() {
        return running && authenticated && socket != null && socket.isConnected();
    }
    
    /**
     * Disconnect from Coordinator.
     */
    public void disconnect() {
        LOG.info("Disconnecting from Coordinator");
        running = false;
        authenticated = false;
        cleanup();
    }
    
    /**
     * Cleanup resources.
     */
    private void cleanup() {
        running = false;
        authenticated = false;
        
        // Stop heartbeat
        if (heartbeatExecutor != null) {
            heartbeatExecutor.shutdown();
            try {
                heartbeatExecutor.awaitTermination(2, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            heartbeatExecutor = null;
        }
        
        // Close socket
        try {
            if (socket != null && !socket.isClosed()) {
                socket.close();
            }
        } catch (IOException e) {
            LOG.fine("Error closing socket: " + e.getMessage());
        }
        
        // Wait for receiver thread
        if (receiverThread != null && receiverThread.isAlive()) {
            try {
                receiverThread.join(2000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
        
        LOG.info("Disconnected from Coordinator");
    }
}
