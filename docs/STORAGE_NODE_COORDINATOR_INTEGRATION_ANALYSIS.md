# Phân tích liên kết giữa Storage Node và Coordinator Server

## Tổng quan

Hệ thống có 2 node chính:
- **Storage Node** (Java): Xử lý data plane - nhận/gửi file chunks từ client
- **Coordinator Server** (Python): Xử lý control plane - quản lý metadata, authentication, authorization

## 1. Các liên kết logic đã được triển khai

### 1.1. Ticket Verification (HMAC-based)

**Storage Node → Coordinator**

**Mục đích**: Xác thực upload/download ticket

**Cơ chế hiện tại**:
- Storage Node verify ticket **locally** bằng HMAC-SHA256
- Sử dụng shared secret được cấu hình ở cả 2 bên
- Ticket format: `HMAC(sessionId|fileId|nodeId|expiry, secret)`

**Code đã có**:

**Storage Node** (`CoordinatorClient.java`):
```java
public boolean verifyTicket(String sessionId, String fileId,
                             String ticketNodeId, long expiry, String signature) {
    // 1. Check node ID matches
    // 2. Check expiry
    // 3. Verify HMAC signature
    String payload = sessionId + "|" + fileId + "|" + ticketNodeId + "|" + expiry;
    String expectedSig = computeHmac(payload);
    return expectedSig.equals(signature);
}
```

**Coordinator Server** (`ticket_service.py`):
```python
def generate_upload_ticket(self, file_id, user_id, room_id, ...):
    ticket_id = str(uuid.uuid4())
    ticket_data = {
        'type': 'upload',
        'fileId': file_id,
        'userId': user_id,
        'roomId': room_id,
        'totalChunks': total_chunks,
        'chunkSize': chunk_size,
        'sha256Whole': sha256_whole,
        'storedName': stored_name,
        'expiresAt': expires_at.isoformat()
    }
    self.redis.set_ticket(ticket_id, ticket_data, self.upload_ticket_ttl)
    return ticket_id
```

**Trạng thái**: ✅ Đã triển khai (local verification)

---

### 1.2. Upload Complete Notification

**Storage Node → Coordinator**

**Mục đích**: Thông báo upload thành công để Coordinator cập nhật database

**Cơ chế hiện tại**:
- Storage Node gọi `coordinator.notifyUploadComplete()` sau khi finalize
- **CHƯA** gửi thực tế qua socket/HTTP - chỉ log

**Code đã có**:

**Storage Node** (`ClientHandler.java`):
```java
private void handleFinalizeUpload(Message msg) throws Exception {
    // ... assemble file, verify hash ...
    
    // Notify coordinator
    coordinator.notifyUploadComplete(
        session.getFileId(), 
        session.getSha256Whole(), 
        session.getFileSize()
    );
}
```

**Storage Node** (`CoordinatorClient.java`):
```java
public void notifyUploadComplete(String fileId, String sha256Whole, long fileSize) {
    // TODO: Send COMMIT_UPLOAD notification to Coordinator via socket/HTTP
    LOG.info("NOTIFY_COORDINATOR: Upload complete fileId=" + fileId +
             " sha256=" + sha256Whole + " size=" + fileSize);
}
```

**Coordinator Server** (`storage_node_server.py`):
```python
def _handle_upload_complete(self, connection, message):
    # Extract payload
    file_id = message.payload.get('fileId')
    sha256_whole = message.payload.get('sha256Whole')
    stored_name = message.payload.get('storedName')
    final_size = message.payload.get('finalSize')
    
    # Route to upload service
    success, error_code = self.upload_service.handle_upload_complete(
        file_id=file_id,
        sha256_whole=sha256_whole,
        stored_name=stored_name,
        final_size=final_size
    )
```

**Coordinator Server** (`upload_service.py`):
```python
def handle_upload_complete(self, file_id, sha256_whole, stored_name, final_size):
    # 1. Update file status to 'READY' in PostgreSQL
    # 2. Broadcast NEW_FILE notification to room subscribers
    # 3. Write audit log entry
    self.db.execute_update(
        "UPDATE files SET status = %s WHERE id = %s",
        ('READY', file_id)
    )
```

**Trạng thái**: ⚠️ Đã có handler ở Coordinator, CHƯA gửi từ Storage Node

---

### 1.3. Upload Failed Notification

**Storage Node → Coordinator**

**Mục đích**: Thông báo upload thất bại để Coordinator đánh dấu file là DELETED

**Cơ chế hiện tại**:
- Storage Node gọi `coordinator.notifyUploadFailed()` khi có lỗi
- **CHƯA** gửi thực tế qua socket/HTTP - chỉ log

**Code đã có**:

**Storage Node** (`ClientHandler.java`):
```java
private void handleFinalizeUpload(Message msg) throws Exception {
    // ... if hash mismatch or I/O error ...
    coordinator.notifyUploadFailed(
        session.getFileId(), 
        "Hash mismatch after assembly"
    );
}
```

**Storage Node** (`CoordinatorClient.java`):
```java
public void notifyUploadFailed(String fileId, String reason) {
    // TODO: Send failure notification to Coordinator
    LOG.info("NOTIFY_COORDINATOR: Upload failed fileId=" + fileId +
             " reason=" + reason);
}
```

**Coordinator Server** (`storage_node_server.py`):
```python
def _handle_upload_failed(self, connection, message):
    file_id = message.payload.get('fileId')
    reason = message.payload.get('reason', 'Unknown error')
    
    success, error_code = self.upload_service.handle_upload_failed(
        file_id=file_id,
        reason=reason
    )
```

**Coordinator Server** (`upload_service.py`):
```python
def handle_upload_failed(self, file_id, reason):
    # 1. Update file status to 'DELETED'
    # 2. Write audit log entry
    self.db.execute_update(
        "UPDATE files SET status = %s WHERE id = %s",
        ('DELETED', file_id)
    )
```

**Trạng thái**: ⚠️ Đã có handler ở Coordinator, CHƯA gửi từ Storage Node

---

### 1.4. Storage Node Authentication & Heartbeat

**Storage Node → Coordinator**

**Mục đích**: Xác thực Storage Node và duy trì kết nối persistent

**Cơ chế**:
- Storage Node kết nối đến Coordinator qua TCP socket
- Gửi `STORAGE_AUTH` với shared secret
- Gửi `PING` mỗi 30 giây
- Coordinator theo dõi health và tự động ngắt kết nối nếu timeout

**Code đã có**:

**Coordinator Server** (`storage_node_server.py`):
```python
def _handle_storage_auth(self, connection, message):
    secret = message.payload.get('secret')
    if secret != self.shared_secret:
        # Send error
        return
    
    # Mark node as authenticated
    node_info.authenticated = True
    
def _handle_ping(self, connection, message):
    # Update last ping time
    node_info.update_ping_time()
    
    # Respond with PONG
    pong = Message.create_response(MessageType.PONG, ...)
    connection.send_message(pong)
```

**Trạng thái**: ✅ Đã triển khai ở Coordinator, CHƯA triển khai ở Storage Node

---

### 1.5. Ticket Verification via Socket (Optional)

**Storage Node → Coordinator**

**Mục đích**: Verify ticket qua socket thay vì local HMAC

**Cơ chế**:
- Storage Node gửi `VERIFY_TICKET` message
- Coordinator kiểm tra Redis và trả về `TICKET_VALID` hoặc `TICKET_INVALID`

**Code đã có**:

**Coordinator Server** (`storage_node_server.py`):
```python
def _handle_verify_ticket(self, connection, message):
    ticket_id = message.payload.get('ticket')
    
    # Verify ticket using ticket service
    is_valid, ticket_data, error_code = self.ticket_service.verify_ticket(ticket_id)
    
    if is_valid:
        response = Message.create_response(MessageType.TICKET_VALID, ticket_data, ...)
    else:
        response = Message.create_response(MessageType.TICKET_INVALID, {"error": error_code}, ...)
```

**Trạng thái**: ✅ Đã triển khai ở Coordinator, CHƯA triển khai ở Storage Node

---

## 2. Code còn thiếu để liên kết 2 node

### 2.1. Storage Node cần thêm: Control Plane Socket Client

**File cần tạo**: `storagenode/network/ControlPlaneClient.java`

**Chức năng**:
- Kết nối persistent đến Coordinator Server (port 8081)
- Xác thực bằng shared secret
- Gửi PING mỗi 30 giây
- Gửi UPLOAD_COMPLETE / UPLOAD_FAILED notifications
- (Optional) Gửi VERIFY_TICKET requests

**Code cần viết**:

```java
package storagenode.network;

import storagenode.protocol.Message;
import storagenode.protocol.MessageType;
import java.io.*;
import java.net.Socket;
import java.util.concurrent.*;
import java.util.logging.Logger;

/**
 * Persistent socket connection to Coordinator Server control plane.
 * 
 * Handles:
 * - Authentication (STORAGE_AUTH)
 * - Heartbeat (PING/PONG)
 * - Upload notifications (UPLOAD_COMPLETE, UPLOAD_FAILED)
 * - Optional ticket verification (VERIFY_TICKET)
 */
public class ControlPlaneClient {
    private static final Logger LOG = Logger.getLogger(ControlPlaneClient.class.getName());
    
    private final String coordinatorHost;
    private final int coordinatorPort;
    private final String sharedSecret;
    private final String nodeId;
    
    private Socket socket;
    private InputStream in;
    private OutputStream out;
    private volatile boolean running = false;
    
    private ScheduledExecutorService heartbeatExecutor;
    
    public ControlPlaneClient(String coordinatorHost, int coordinatorPort,
                              String sharedSecret, String nodeId) {
        this.coordinatorHost = coordinatorHost;
        this.coordinatorPort = coordinatorPort;
        this.sharedSecret = sharedSecret;
        this.nodeId = nodeId;
    }
    
    /**
     * Connect to Coordinator and authenticate.
     */
    public void connect() throws IOException {
        LOG.info("Connecting to Coordinator: " + coordinatorHost + ":" + coordinatorPort);
        
        socket = new Socket(coordinatorHost, coordinatorPort);
        in = new BufferedInputStream(socket.getInputStream());
        out = new BufferedOutputStream(socket.getOutputStream());
        running = true;
        
        // Send STORAGE_AUTH
        authenticate();
        
        // Start heartbeat thread
        startHeartbeat();
        
        // Start message receiver thread
        new Thread(this::receiveLoop, "ControlPlane-Receiver").start();
        
        LOG.info("Connected to Coordinator successfully");
    }
    
    private void authenticate() throws IOException {
        Message authMsg = new Message(MessageType.STORAGE_AUTH)
            .set("secret", sharedSecret)
            .set("nodeId", nodeId);
        
        sendMessage(authMsg);
        
        // Wait for STORAGE_AUTH_RESPONSE
        Message response = receiveMessage();
        if (response == null || !response.getType().equals(MessageType.STORAGE_AUTH_RESPONSE)) {
            throw new IOException("Authentication failed");
        }
        
        String status = response.getString("status");
        if (!"authenticated".equals(status)) {
            throw new IOException("Authentication rejected: " + status);
        }
        
        LOG.info("Authenticated with Coordinator");
    }
    
    private void startHeartbeat() {
        heartbeatExecutor = Executors.newSingleThreadScheduledExecutor();
        heartbeatExecutor.scheduleAtFixedRate(() -> {
            try {
                sendPing();
            } catch (Exception e) {
                LOG.warning("Heartbeat failed: " + e.getMessage());
            }
        }, 30, 30, TimeUnit.SECONDS);
    }
    
    private void sendPing() throws IOException {
        Message ping = new Message(MessageType.PING);
        sendMessage(ping);
        LOG.fine("PING sent to Coordinator");
    }
    
    /**
     * Notify Coordinator that upload completed successfully.
     */
    public void notifyUploadComplete(String fileId, String sha256Whole, 
                                      String storedName, long finalSize) {
        try {
            Message msg = new Message(MessageType.UPLOAD_COMPLETE)
                .set("fileId", fileId)
                .set("sha256Whole", sha256Whole)
                .set("storedName", storedName)
                .set("finalSize", finalSize);
            
            sendMessage(msg);
            LOG.info("UPLOAD_COMPLETE sent: fileId=" + fileId);
            
        } catch (IOException e) {
            LOG.severe("Failed to send UPLOAD_COMPLETE: " + e.getMessage());
        }
    }
    
    /**
     * Notify Coordinator that upload failed.
     */
    public void notifyUploadFailed(String fileId, String reason) {
        try {
            Message msg = new Message(MessageType.UPLOAD_FAILED)
                .set("fileId", fileId)
                .set("reason", reason);
            
            sendMessage(msg);
            LOG.info("UPLOAD_FAILED sent: fileId=" + fileId);
            
        } catch (IOException e) {
            LOG.severe("Failed to send UPLOAD_FAILED: " + e.getMessage());
        }
    }
    
    /**
     * Verify ticket via Coordinator (optional, alternative to local HMAC).
     */
    public boolean verifyTicketRemote(String ticketId) {
        try {
            Message msg = new Message(MessageType.VERIFY_TICKET)
                .set("ticket", ticketId);
            
            sendMessage(msg);
            
            // Wait for response (with timeout)
            Message response = receiveMessageWithTimeout(5000);
            
            if (response == null) {
                LOG.warning("Ticket verification timeout");
                return false;
            }
            
            if (response.getType().equals(MessageType.TICKET_VALID)) {
                LOG.info("Ticket verified: " + ticketId);
                return true;
            } else {
                LOG.warning("Ticket invalid: " + ticketId);
                return false;
            }
            
        } catch (Exception e) {
            LOG.severe("Failed to verify ticket: " + e.getMessage());
            return false;
        }
    }
    
    private void receiveLoop() {
        while (running) {
            try {
                Message msg = receiveMessage();
                if (msg == null) break;
                
                handleMessage(msg);
                
            } catch (IOException e) {
                if (running) {
                    LOG.warning("Connection lost: " + e.getMessage());
                }
                break;
            }
        }
    }
    
    private void handleMessage(Message msg) {
        switch (msg.getType()) {
            case PONG:
                LOG.fine("PONG received");
                break;
            case ACK:
                LOG.fine("ACK received");
                break;
            case ERROR:
                LOG.warning("ERROR from Coordinator: " + msg.getString("message"));
                break;
            default:
                LOG.fine("Received: " + msg.getType());
        }
    }
    
    private synchronized void sendMessage(Message msg) throws IOException {
        FrameCodec.writeFrame(out, msg);
    }
    
    private Message receiveMessage() throws IOException {
        return FrameCodec.readFrame(in);
    }
    
    private Message receiveMessageWithTimeout(long timeoutMs) throws IOException {
        // TODO: Implement timeout logic
        return receiveMessage();
    }
    
    public void disconnect() {
        running = false;
        
        if (heartbeatExecutor != null) {
            heartbeatExecutor.shutdown();
        }
        
        try {
            if (socket != null) socket.close();
        } catch (IOException ignored) {}
        
        LOG.info("Disconnected from Coordinator");
    }
}
```

---

### 2.2. Cập nhật CoordinatorClient.java

**File**: `storagenode/network/CoordinatorClient.java`

**Thay đổi**:
- Thêm reference đến `ControlPlaneClient`
- Delegate notification calls đến control plane client

```java
public class CoordinatorClient {
    private final String ticketSecret;
    private final String nodeId;
    private final ControlPlaneClient controlPlaneClient;  // NEW
    
    public CoordinatorClient(String ticketSecret, String nodeId,
                             String coordinatorHost, int coordinatorPort) {
        this.ticketSecret = ticketSecret;
        this.nodeId = nodeId;
        
        // Initialize control plane client
        this.controlPlaneClient = new ControlPlaneClient(
            coordinatorHost, coordinatorPort, ticketSecret, nodeId
        );
    }
    
    public void connect() throws IOException {
        controlPlaneClient.connect();
    }
    
    public void disconnect() {
        controlPlaneClient.disconnect();
    }
    
    // Keep local HMAC verification for backward compatibility
    public boolean verifyTicket(String sessionId, String fileId,
                                 String ticketNodeId, long expiry, String signature) {
        // ... existing HMAC logic ...
    }
    
    // NEW: Delegate to control plane client
    public void notifyUploadComplete(String fileId, String sha256Whole, long fileSize) {
        String storedName = "data/store/" + sha256Whole.substring(0, 2) + "/" + sha256Whole;
        controlPlaneClient.notifyUploadComplete(fileId, sha256Whole, storedName, fileSize);
    }
    
    // NEW: Delegate to control plane client
    public void notifyUploadFailed(String fileId, String reason) {
        controlPlaneClient.notifyUploadFailed(fileId, reason);
    }
}
```

---

### 2.3. Cập nhật StorageNodeMain.java

**File**: `storagenode/StorageNodeMain.java`

**Thay đổi**:
- Kết nối đến Coordinator khi khởi động
- Ngắt kết nối khi shutdown

```java
public static void main(String[] args) {
    // ... existing initialization ...
    
    // 7. Initialize coordinator client
    CoordinatorClient coordinator = new CoordinatorClient(
        config.getTicketSecret(), config.getNodeId(),
        config.getCoordinatorHost(), config.getCoordinatorPort()
    );
    
    // NEW: Connect to Coordinator control plane
    try {
        coordinator.connect();
        LOG.info("Connected to Coordinator control plane");
    } catch (IOException e) {
        LOG.warning("Failed to connect to Coordinator: " + e.getMessage());
        LOG.warning("Running in standalone mode (local ticket verification only)");
    }
    
    // ... existing code ...
    
    // 9. Shutdown hook
    Runtime.getRuntime().addShutdownHook(new Thread(() -> {
        LOG.info("Shutdown signal received");
        server.stop();
        monitor.stop();
        coordinator.disconnect();  // NEW
    }));
    
    // 10. Start server (blocking)
    server.start();
}
```

---

### 2.4. Cập nhật Protocol Message Types

**Storage Node cần thêm**: `storagenode/protocol/MessageType.java`

```java
package storagenode.protocol;

public enum MessageType {
    // ... existing data plane types ...
    
    // Control plane types (for Coordinator communication)
    STORAGE_AUTH,
    STORAGE_AUTH_RESPONSE,
    PING,
    PONG,
    VERIFY_TICKET,
    TICKET_VALID,
    TICKET_INVALID,
    UPLOAD_COMPLETE,
    UPLOAD_FAILED,
    ACK,
    ERROR
}
```

---

### 2.5. Configuration Updates

**Storage Node** (`storage-node.properties`):

```properties
# Coordinator Control Plane
coordinator.host=127.0.0.1
coordinator.port=8081
coordinator.secret=change-this-secret-in-production

# Node Identity
node.id=storage-node-1
```

**Coordinator Server** (`.env`):

```bash
# Storage Node Configuration
STORAGE_NODE_SECRET=change-this-secret-in-production
SERVER_STORAGE_PORT=8081
STORAGE_NODE_TIMEOUT=90
```

---

## 3. Luồng hoạt động hoàn chỉnh

### 3.1. Khởi động hệ thống

```
1. Coordinator Server starts
   - Listen on port 8000 (client socket)
   - Listen on port 8081 (storage node socket)

2. Storage Node starts
   - Listen on port 9000 (data plane)
   - Connect to Coordinator:8081 (control plane)
   - Send STORAGE_AUTH
   - Start PING heartbeat (every 30s)
```

### 3.2. Upload flow

```
Client                  Coordinator              Storage Node
  │                          │                         │
  │─ INIT_UPLOAD ───────────>│                         │
  │                          │ (check permission)      │
  │                          │ (validate scan)         │
  │                          │ (check dedup)           │
  │                          │ (generate ticket)       │
  │<─ UPLOAD_PLAN ───────────│                         │
  │   (ticket, address)      │                         │
  │                          │                         │
  │─ OPEN_UPLOAD ───────────────────────────────────>│
  │   (ticket)               │                         │ (verify ticket locally)
  │<─ OPEN_UPLOAD_RESP ──────────────────────────────│
  │                          │                         │
  │─ UPLOAD_CHUNK ──────────────────────────────────>│
  │<─ ACK_CHUNK ─────────────────────────────────────│
  │                          │                         │
  │─ FINALIZE_UPLOAD ───────────────────────────────>│
  │                          │                         │ (assemble, verify hash)
  │                          │<─ UPLOAD_COMPLETE ──────│
  │                          │   (fileId, sha256)      │
  │                          │ (update status=READY)   │
  │                          │ (broadcast NEW_FILE)    │
  │                          │─ ACK ──────────────────>│
  │<─ FINALIZE_RESP ─────────────────────────────────│
```

### 3.3. Download flow

```
Client                  Coordinator              Storage Node
  │                          │                         │
  │─ INIT_DOWNLOAD ─────────>│                         │
  │                          │ (check permission)      │
  │                          │ (generate ticket)       │
  │<─ DOWNLOAD_PLAN ─────────│                         │
  │   (ticket, address)      │                         │
  │                          │                         │
  │─ OPEN_DOWNLOAD ─────────────────────────────────>│
  │   (ticket)               │                         │ (verify ticket locally)
  │<─ OPEN_DOWNLOAD_RESP ────────────────────────────│
  │                          │                         │
  │─ REQUEST_CHUNK ─────────────────────────────────>│
  │<─ DOWNLOAD_CHUNK ────────────────────────────────│
  │                          │                         │
  │   ... (all chunks) ...   │                         │
  │                          │                         │
  │<─ DOWNLOAD_COMPLETE ─────────────────────────────│
```

---

## 4. Tóm tắt code còn thiếu

### ✅ Đã có (Coordinator Server)
1. `storage_node_server.py` - Socket server cho Storage Node
2. `storage_node/IMPLEMENTATION_SUMMARY.md` - Documentation
3. Message handlers: STORAGE_AUTH, PING, VERIFY_TICKET, UPLOAD_COMPLETE, UPLOAD_FAILED
4. `upload_service.py` - Handle upload complete/failed
5. `ticket_service.py` - Generate và verify tickets

### ⚠️ Còn thiếu (Storage Node)
1. **`ControlPlaneClient.java`** - Socket client kết nối đến Coordinator
   - Authentication
   - Heartbeat (PING/PONG)
   - Send UPLOAD_COMPLETE
   - Send UPLOAD_FAILED
   - (Optional) VERIFY_TICKET

2. **Cập nhật `CoordinatorClient.java`**
   - Thêm `ControlPlaneClient` instance
   - Delegate notification calls
   - Add `connect()` và `disconnect()` methods

3. **Cập nhật `StorageNodeMain.java`**
   - Call `coordinator.connect()` khi khởi động
   - Call `coordinator.disconnect()` khi shutdown

4. **Thêm message types** vào `MessageType.java`
   - STORAGE_AUTH, PING, PONG
   - UPLOAD_COMPLETE, UPLOAD_FAILED
   - VERIFY_TICKET, TICKET_VALID, TICKET_INVALID

5. **Configuration**
   - Thêm `coordinator.secret` vào `storage-node.properties`
   - Đảm bảo secret khớp với Coordinator

---

## 5. Ưu tiên triển khai

### Phase 1: Basic Integration (Cao nhất)
1. Tạo `ControlPlaneClient.java` với authentication + heartbeat
2. Implement `notifyUploadComplete()` và `notifyUploadFailed()`
3. Cập nhật `StorageNodeMain.java` để connect khi khởi động
4. Test end-to-end upload flow

### Phase 2: Enhanced Features
1. Implement remote ticket verification (VERIFY_TICKET)
2. Add reconnection logic khi connection bị mất
3. Add metrics và monitoring

### Phase 3: Production Hardening
1. TLS/SSL encryption cho control plane connection
2. Multiple Storage Node support
3. Load balancing và failover

---

## 6. Lưu ý quan trọng

### 6.1. Ticket Verification Strategy
- **Hiện tại**: Local HMAC verification (đơn giản, nhanh)
- **Tương lai**: Remote verification qua socket (linh hoạt hơn, có thể revoke ticket)
- **Khuyến nghị**: Giữ cả 2, dùng local làm primary, remote làm fallback

### 6.2. Error Handling
- Control plane connection có thể bị mất
- Storage Node nên tiếp tục hoạt động (degrade gracefully)
- Queue notifications và retry khi reconnect

### 6.3. Security
- Shared secret phải được bảo mật
- Nên dùng TLS cho production
- Rotate secret định kỳ

### 6.4. Scalability
- Coordinator có thể quản lý nhiều Storage Nodes
- Mỗi Storage Node có unique `node_id`
- Load balancing ở Coordinator level
