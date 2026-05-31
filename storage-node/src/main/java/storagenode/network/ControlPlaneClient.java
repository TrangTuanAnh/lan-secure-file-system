package storagenode.network;

import storagenode.protocol.ControlPlaneFrameCodec;
import storagenode.protocol.Message;
import storagenode.protocol.MessageType;
import storagenode.storage.FileStore;

import java.io.*;
import java.net.Socket;
import java.security.KeyStore;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.util.Collection;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.*;
import java.util.logging.Level;
import java.util.logging.Logger;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

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
    private static final long RECONNECT_MIN_BACKOFF_MS = 2000;
    private static final long RECONNECT_MAX_BACKOFF_MS = 30000;
    private static final long SUPERVISOR_POLL_MS = 2000;
    
    private final String coordinatorHost;
    private final int coordinatorPort;
    private final String sharedSecret;
    private final String nodeId;
    private final String dataHost;
    private final int dataPort;
    private final String storageAddress;
    private final FileStore fileStore;
    private final TlsConfig tls;

    private Socket socket;
    private InputStream in;
    private OutputStream out;
    private volatile boolean running = false;
    private volatile boolean authenticated = false;
    
    private ScheduledExecutorService heartbeatExecutor;
    private Thread receiverThread;
    private Thread supervisorThread;
    // Set once disconnect() is called so the supervisor stops reconnecting.
    private volatile boolean shuttingDown = false;
    
    private final BlockingQueue<Message> responseQueue = new LinkedBlockingQueue<>();
    
    public ControlPlaneClient(String coordinatorHost, int coordinatorPort,
                              String sharedSecret, String nodeId,
                              String dataHost, int dataPort, String storageAddress) {
        this(coordinatorHost, coordinatorPort, sharedSecret, nodeId,
             dataHost, dataPort, storageAddress, null, null);
    }

    public ControlPlaneClient(String coordinatorHost, int coordinatorPort,
                              String sharedSecret, String nodeId,
                              String dataHost, int dataPort, String storageAddress,
                              FileStore fileStore) {
        this(coordinatorHost, coordinatorPort, sharedSecret, nodeId,
             dataHost, dataPort, storageAddress, fileStore, null);
    }

    public ControlPlaneClient(String coordinatorHost, int coordinatorPort,
                              String sharedSecret, String nodeId,
                              String dataHost, int dataPort, String storageAddress,
                              FileStore fileStore, TlsConfig tls) {
        this.coordinatorHost = coordinatorHost;
        this.coordinatorPort = coordinatorPort;
        this.sharedSecret = sharedSecret;
        this.nodeId = nodeId;
        this.dataHost = dataHost;
        this.dataPort = dataPort;
        this.storageAddress = storageAddress;
        this.fileStore = fileStore;
        this.tls = (tls != null) ? tls : TlsConfig.disabled();
    }
    
    /**
     * Connect to Coordinator and authenticate, then start a supervisor that
     * automatically reconnects if the connection later drops (e.g. the
     * Coordinator restarts). The initial connect is synchronous and throws on
     * failure, preserving startup semantics.
     *
     * @throws IOException if the initial connection or authentication fails
     */
    public void connect() throws IOException {
        shuttingDown = false;
        doConnect();
        startSupervisor();
    }

    /**
     * Establish a single connection + authentication. Used by both the initial
     * {@link #connect()} and the supervisor's reconnect attempts.
     */
    private void doConnect() throws IOException {
        LOG.info("Connecting to Coordinator: " + coordinatorHost + ":" + coordinatorPort);

        try {
            socket = createSocket();
            socket.connect(new java.net.InetSocketAddress(coordinatorHost, coordinatorPort),
                          CONNECT_TIMEOUT_MS);
            if (socket instanceof SSLSocket) {
                // Drive the mutual-TLS handshake now so failures surface here.
                ((SSLSocket) socket).startHandshake();
                LOG.info("Control-plane mTLS established (" +
                        ((SSLSocket) socket).getSession().getProtocol() + ")");
            }
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
     * Start the supervisor thread that keeps the control-plane connection up.
     * When the connection drops (and we are not shutting down) it re-establishes
     * it with exponential backoff.
     */
    private void startSupervisor() {
        if (supervisorThread != null && supervisorThread.isAlive()) {
            return;
        }
        supervisorThread = new Thread(this::superviseLoop, "ControlPlane-Supervisor");
        supervisorThread.setDaemon(true);
        supervisorThread.start();
    }

    private void superviseLoop() {
        LOG.info("Control plane supervisor started");
        while (!shuttingDown) {
            if (isConnected()) {
                sleepQuietly(SUPERVISOR_POLL_MS);
                continue;
            }
            if (shuttingDown) {
                break;
            }
            LOG.warning("Control-plane connection is down; attempting to reconnect...");
            long backoff = RECONNECT_MIN_BACKOFF_MS;
            while (!shuttingDown && !isConnected()) {
                cleanup(); // ensure a clean slate before a fresh socket
                try {
                    doConnect();
                    LOG.info("Reconnected to Coordinator");
                } catch (Exception e) {
                    LOG.warning("Reconnect attempt failed: " + e.getMessage()
                            + "; retrying in " + (backoff / 1000) + "s");
                    sleepQuietly(backoff);
                    backoff = Math.min(backoff * 2, RECONNECT_MAX_BACKOFF_MS);
                }
            }
        }
        LOG.info("Control plane supervisor stopped");
    }

    private void sleepQuietly(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
    
    /**
     * Create the control-plane socket: a plain {@link Socket} when TLS is off,
     * or an unconnected {@link SSLSocket} (client cert + CA verification, with
     * server hostname checking) when mutual TLS is enabled.
     */
    private Socket createSocket() throws IOException {
        if (!tls.enabled) {
            return new Socket();
        }
        try {
            KeyStore ks = KeyStore.getInstance("PKCS12");
            try (InputStream ksIn = new FileInputStream(tls.keystorePath)) {
                ks.load(ksIn, tls.keystorePassword.toCharArray());
            }
            KeyManagerFactory kmf =
                    KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm());
            kmf.init(ks, tls.keystorePassword.toCharArray());

            // Build the truststore in-memory from the CA PEM. (A cert-only
            // PKCS12 is not reliably recognised as a trust anchor by the JDK.)
            KeyStore ts = KeyStore.getInstance(KeyStore.getDefaultType());
            ts.load(null, null);
            CertificateFactory cf = CertificateFactory.getInstance("X.509");
            try (InputStream caIn = new FileInputStream(tls.caCertPath)) {
                int i = 0;
                for (Certificate ca : cf.generateCertificates(caIn)) {
                    ts.setCertificateEntry("ca-" + (i++), ca);
                }
            }
            TrustManagerFactory tmf =
                    TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
            tmf.init(ts);

            SSLContext ctx = SSLContext.getInstance("TLS");
            ctx.init(kmf.getKeyManagers(), tmf.getTrustManagers(), null);

            SSLSocket s = (SSLSocket) ctx.getSocketFactory().createSocket();
            s.setEnabledProtocols(new String[] {"TLSv1.3", "TLSv1.2"});
            // Verify the coordinator's server cert hostname (SAN) against the
            // host we dial (the "coordinator" service name).
            SSLParameters params = s.getSSLParameters();
            params.setEndpointIdentificationAlgorithm("HTTPS");
            s.setSSLParameters(params);
            return s;
        } catch (IOException e) {
            throw e;
        } catch (Exception e) {
            throw new IOException("Failed to build TLS socket: " + e.getMessage(), e);
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
        
        // BUGFIX M21: bound consecutive soft errors so a corrupt-frame
        // storm can't spin this thread forever. After N non-IO failures
        // in a row we break out and let the cleanup/reconnect logic try
        // a fresh socket.
        int consecutiveSoftErrors = 0;
        final int maxSoftErrors = 10;
        while (running) {
            try {
                Message msg = ControlPlaneFrameCodec.readFrame(in);

                if (msg == null) {
                    LOG.info("Connection closed by Coordinator");
                    break;
                }

                handleMessage(msg);
                consecutiveSoftErrors = 0;

            } catch (IOException e) {
                if (running) {
                    LOG.warning("Connection lost: " + e.getMessage());
                }
                break;
            } catch (Exception e) {
                LOG.severe("Error in receive loop: " + e.getMessage());
                consecutiveSoftErrors++;
                if (consecutiveSoftErrors >= maxSoftErrors) {
                    LOG.severe("Too many consecutive frame errors (" +
                               consecutiveSoftErrors + "); aborting receive loop");
                    break;
                }
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
        shuttingDown = true;
        running = false;
        authenticated = false;
        if (supervisorThread != null) {
            supervisorThread.interrupt();
        }
        cleanup();
    }

    /**
     * Cleanup resources. Idempotent and safe to call from multiple threads
     * (the receiver thread on disconnect, and the supervisor before a reconnect).
     */
    private synchronized void cleanup() {
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
        
        // Wait for receiver thread (skip if cleanup() is being called from the
        // receiver thread itself, to avoid a pointless self-join).
        if (receiverThread != null && receiverThread.isAlive()
                && Thread.currentThread() != receiverThread) {
            try {
                receiverThread.join(2000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }

        LOG.info("Disconnected from Coordinator");
    }
}
