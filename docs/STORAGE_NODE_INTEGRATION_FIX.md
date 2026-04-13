# Storage Node - Coordinator Integration Fix

## Tóm tắt vấn đề

Sau khi phân tích báo cáo `STORAGE_NODE_COORDINATOR_INTEGRATION_ANALYSIS.md`, đã xác định được **3 vấn đề nghiêm trọng** ảnh hưởng xấu đến hệ thống:

### 1. ⚠️ Upload Complete/Failed không được thông báo (NGHIÊM TRỌNG)
**Vấn đề:**
- Storage Node hoàn thành upload nhưng KHÔNG thông báo cho Coordinator
- Coordinator không cập nhật status file từ PENDING → READY
- Client không nhận được notification NEW_FILE

**Hậu quả:**
- File đã upload xong nhưng không thể download được
- Database không đồng bộ với trạng thái thực tế
- User experience bị ảnh hưởng nghiêm trọng

### 2. ⚠️ Không có heartbeat/health check (NGHIÊM TRỌNG)
**Vấn đề:**
- Storage Node không kết nối persistent với Coordinator
- Coordinator không biết Storage Node còn sống hay đã chết

**Hậu quả:**
- Coordinator có thể route traffic đến node đã chết
- Không có cơ chế failover
- Hệ thống không reliable

### 3. ⚠️ Không có authentication giữa Storage Node và Coordinator (BẢO MẬT)
**Vấn đề:**
- Bất kỳ ai cũng có thể giả mạo Storage Node
- Không có xác thực khi kết nối

**Hậu quả:**
- Lỗ hổng bảo mật nghiêm trọng
- Có thể bị tấn công giả mạo node

---

## Các thay đổi đã triển khai

### 1. Storage Node (Java)

#### 1.1. Thêm Control Plane Message Types
**File:** `storage-node/src/main/java/storagenode/protocol/MessageType.java`

Đã thêm các message types cho control plane:
- `STORAGE_AUTH` - Xác thực Storage Node
- `STORAGE_AUTH_RESPONSE` - Phản hồi xác thực
- `PING` / `PONG` - Heartbeat
- `VERIFY_TICKET` / `TICKET_VALID` / `TICKET_INVALID` - Verify ticket từ xa
- `UPLOAD_COMPLETE` / `UPLOAD_FAILED` - Thông báo upload status
- `ACK` - Acknowledgment

#### 1.2. Tạo ControlPlaneClient.java (MỚI)
**File:** `storage-node/src/main/java/storagenode/network/ControlPlaneClient.java`

**Chức năng:**
- Kết nối persistent đến Coordinator Server (port 8081)
- Xác thực bằng shared secret
- Gửi PING mỗi 30 giây để duy trì kết nối
- Gửi UPLOAD_COMPLETE / UPLOAD_FAILED notifications
- (Optional) Verify ticket từ xa qua VERIFY_TICKET

**Đặc điểm:**
- Thread-safe với synchronized methods
- Background receiver thread để nhận responses
- Background heartbeat thread
- Graceful shutdown với cleanup
- Timeout handling cho responses

#### 1.3. Cập nhật CoordinatorClient.java
**File:** `storage-node/src/main/java/storagenode/network/CoordinatorClient.java`

**Thay đổi:**
- Thêm `ControlPlaneClient` instance
- Thêm methods `connect()`, `disconnect()`, `isConnected()`
- Delegate `notifyUploadComplete()` và `notifyUploadFailed()` đến control plane client
- Giữ nguyên local HMAC verification (backward compatible)

#### 1.4. Cập nhật StorageNodeMain.java
**File:** `storage-node/src/main/java/storagenode/StorageNodeMain.java`

**Thay đổi:**
- Gọi `coordinator.connect()` khi khởi động
- Gọi `coordinator.disconnect()` trong shutdown hook
- Graceful degradation: nếu không kết nối được, vẫn chạy ở standalone mode

#### 1.5. Cập nhật Configuration
**File:** `storage-node/storage-node.properties`

**Thay đổi:**
- Cập nhật `coordinator.port=8081` (từ 8000)
- Thêm comment giải thích port 8000 vs 8081

### 2. Coordinator Server (Python)

#### 2.1. Cập nhật main.py
**File:** `coordinator-server/main.py`

**Thay đổi:**
- Import `StorageNodeServer`
- Khởi động `StorageNodeServer` trên port 8081
- Thêm cleanup cho storage node server trong shutdown handler
- Thêm global reference `storage_node_server`

**Lưu ý:** Đây là fix QUAN TRỌNG - trước đây StorageNodeServer đã được implement nhưng KHÔNG được khởi động!

---

## Kiểm tra các file đã có sẵn

### Coordinator Server - Đã có sẵn ✅

1. **storage_node/storage_node_server.py** - Socket server cho Storage Node
   - Handlers: STORAGE_AUTH, PING, VERIFY_TICKET, UPLOAD_COMPLETE, UPLOAD_FAILED
   - Health check loop (30s interval)
   - Authentication với shared secret
   - Timeout detection (90s default)

2. **upload/upload_service.py** - Upload service
   - `handle_upload_complete()` - Cập nhật file status → READY, broadcast NEW_FILE
   - `handle_upload_failed()` - Cập nhật file status → DELETED

3. **ticket/ticket_service.py** - Ticket service
   - Generate upload/download tickets
   - Verify tickets từ Redis

4. **config.py** - Configuration
   - `SERVER_STORAGE_PORT=8081`
   - `STORAGE_NODE_SECRET`
   - `STORAGE_NODE_TIMEOUT=90`

5. **.env.example** - Environment variables template
   - Đã có tất cả config cần thiết

---

## Luồng hoạt động sau khi fix

### 1. Khởi động hệ thống

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Coordinator Server starts                                │
│    - Listen on port 8080 (client socket)                    │
│    - Listen on port 8081 (storage node socket) ← FIX        │
│                                                              │
│ 2. Storage Node starts                                      │
│    - Listen on port 9001 (data plane)                       │
│    - Connect to Coordinator:8081 (control plane) ← FIX      │
│    - Send STORAGE_AUTH ← FIX                                │
│    - Start PING heartbeat (every 30s) ← FIX                 │
└─────────────────────────────────────────────────────────────┘
```

### 2. Upload flow (FIXED)

```
Client                  Coordinator              Storage Node
  │                          │                         │
  │─ INIT_UPLOAD ───────────>│                         │
  │                          │ (check permission)      │
  │                          │ (generate ticket)       │
  │<─ UPLOAD_PLAN ───────────│                         │
  │   (ticket, address)      │                         │
  │                          │                         │
  │─ OPEN_UPLOAD ───────────────────────────────────>│
  │   (ticket)               │                         │ (verify ticket)
  │<─ OPEN_UPLOAD_RESP ──────────────────────────────│
  │                          │                         │
  │─ UPLOAD_CHUNK ──────────────────────────────────>│
  │<─ ACK_CHUNK ─────────────────────────────────────│
  │                          │                         │
  │─ FINALIZE_UPLOAD ───────────────────────────────>│
  │                          │                         │ (assemble, verify)
  │                          │<─ UPLOAD_COMPLETE ──────│ ← FIX
  │                          │   (fileId, sha256)      │
  │                          │ (update status=READY)   │ ← FIX
  │                          │ (broadcast NEW_FILE)    │ ← FIX
  │                          │─ ACK ──────────────────>│
  │<─ FINALIZE_RESP ─────────────────────────────────│
```

### 3. Heartbeat (NEW)

```
Storage Node                Coordinator
     │                           │
     │─ PING ───────────────────>│
     │                           │ (update last_ping_time)
     │<─ PONG ───────────────────│
     │                           │
     │   ... (30 seconds) ...    │
     │                           │
     │─ PING ───────────────────>│
     │<─ PONG ───────────────────│
```

### 4. Health Check (NEW)

```
Coordinator (background thread, every 30s):
  - Check all connected Storage Nodes
  - If (now - last_ping_time) > 90s:
      → Mark node as unhealthy
      → Close connection
      → Log warning
```

---

## Cách test

### 1. Setup môi trường

#### Coordinator Server:
```bash
cd coordinator-server

# Tạo .env từ .env.example
cp .env.example .env

# Chỉnh sửa .env:
# - STORAGE_NODE_SECRET=your-secret-here (phải khớp với Storage Node)
# - SERVER_STORAGE_PORT=8081

# Cài đặt dependencies
pip install -r requirements.txt

# Khởi động database (nếu dùng Docker)
docker-compose up -d postgres redis

# Chạy migrations
alembic upgrade head

# Khởi động server
python main.py
```

#### Storage Node:
```bash
cd storage-node

# Chỉnh sửa storage-node.properties:
# - coordinator.host=127.0.0.1
# - coordinator.port=8081
# - ticket.secret=your-secret-here (phải khớp với Coordinator)

# Build
mvn clean package

# Chạy
java -jar target/storage-node.jar
```

### 2. Kiểm tra kết nối

**Xem logs Coordinator:**
```
[INFO] Storage node server started on port 8081
[INFO] Storage Node connection established: <connection_id>
[INFO] Storage Node authenticated: <connection_id>
[INFO] PING received from <connection_id>
[INFO] PONG sent to <connection_id>
```

**Xem logs Storage Node:**
```
[INFO] Connecting to Coordinator: 127.0.0.1:8081
[INFO] Authenticated with Coordinator
[INFO] Connected to Coordinator successfully
[INFO] Heartbeat started (interval: 30s)
[INFO] PING sent to Coordinator
[INFO] PONG received
```

### 3. Test upload flow

**Upload file qua client:**
```bash
# Sử dụng example_upload_integration.py hoặc client thực tế
cd coordinator-server
python example_upload_integration.py
```

**Kiểm tra logs Storage Node:**
```
[INFO] Upload finalized: session=<session_id>
[INFO] UPLOAD_COMPLETE sent: fileId=<file_id>, size=<size>
```

**Kiểm tra logs Coordinator:**
```
[INFO] UPLOAD_COMPLETE received: file_id=<file_id>, size=<size>
[INFO] File status updated: <file_id> -> READY
[INFO] Broadcasting NEW_FILE event to room subscribers
```

**Kiểm tra database:**
```sql
SELECT id, filename, status, size FROM files WHERE id = '<file_id>';
-- status phải là 'READY'
```

### 4. Test heartbeat timeout

**Stop Storage Node (Ctrl+C):**

**Xem logs Coordinator (sau ~90 giây):**
```
[WARNING] Storage Node timeout: <node_id>, last_ping=<timestamp>, timeout=90s
[INFO] Storage Node disconnected: <node_id>
```

### 5. Test authentication failure

**Thay đổi secret trong storage-node.properties:**
```properties
ticket.secret=wrong-secret
```

**Restart Storage Node:**

**Xem logs Storage Node:**
```
[SEVERE] Failed to connect to Coordinator: Authentication failed: invalid secret
[WARNING] Running in standalone mode (local ticket verification only)
```

**Xem logs Coordinator:**
```
[WARNING] STORAGE_AUTH invalid secret from <connection_id>
```

---

## Checklist triển khai

### Storage Node ✅
- [x] Thêm control plane message types vào MessageType.java
- [x] Tạo ControlPlaneClient.java
- [x] Cập nhật CoordinatorClient.java
- [x] Cập nhật StorageNodeMain.java
- [x] Cập nhật storage-node.properties

### Coordinator Server ✅
- [x] Cập nhật main.py để khởi động StorageNodeServer
- [x] Verify storage_node_server.py đã có sẵn
- [x] Verify upload_service.py có handle_upload_complete/failed
- [x] Verify config.py có storage node settings

### Testing ⏳
- [ ] Test kết nối và authentication
- [ ] Test heartbeat
- [ ] Test upload complete notification
- [ ] Test upload failed notification
- [ ] Test timeout và reconnection
- [ ] Test authentication failure

---

## Lưu ý quan trọng

### 1. Shared Secret
- **PHẢI** khớp giữa Storage Node và Coordinator
- Storage Node: `ticket.secret` trong `storage-node.properties`
- Coordinator: `STORAGE_NODE_SECRET` trong `.env`
- **KHÔNG** dùng default secret trong production!

### 2. Port Configuration
- Port 8080: Client socket server (end-user clients)
- Port 8081: Storage node control plane (storage nodes)
- Port 8082: Notification server (future use)
- Port 9001: Storage node data plane (file chunks)

### 3. Graceful Degradation
- Nếu Storage Node không kết nối được Coordinator:
  - Vẫn chạy được (standalone mode)
  - Local ticket verification vẫn hoạt động
  - Upload/download vẫn hoạt động
  - **NHƯNG**: Coordinator không nhận được notifications
  - **NHƯNG**: File status không được cập nhật

### 4. Production Considerations
- Sử dụng TLS/SSL cho control plane connection
- Rotate shared secret định kỳ
- Monitor connection health
- Implement reconnection logic với exponential backoff
- Add metrics và alerting

---

## Kết luận

Các vấn đề nghiêm trọng đã được fix:

1. ✅ **Upload notifications** - Storage Node giờ đây gửi UPLOAD_COMPLETE/FAILED đến Coordinator
2. ✅ **Heartbeat/health check** - Coordinator theo dõi health của Storage Nodes
3. ✅ **Authentication** - Storage Node phải xác thực bằng shared secret

Hệ thống giờ đây:
- **Reliable**: Coordinator biết node nào còn sống
- **Consistent**: Database đồng bộ với trạng thái thực tế
- **Secure**: Có authentication giữa nodes
- **Observable**: Có logs và health monitoring

**Trạng thái:** Sẵn sàng để test và deploy!
