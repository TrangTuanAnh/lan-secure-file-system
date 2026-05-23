# COORDINATOR SERVER - NỘI DUNG THUYẾT TRÌNH

## 1. TỔNG QUAN HỆ THỐNG

### 1.1 Vai trò của Coordinator Server
- **Control Plane** của hệ thống truyền file LAN phân tán
- Quản lý xác thực, phân quyền, metadata file
- Điều phối giữa Client và Storage Node
- **KHÔNG** lưu trữ dữ liệu file thực tế
- **KHÔNG** theo dõi quá trình upload từng chunk

### 1.2 Kiến trúc tổng thể
```
┌─────────────┐         ┌──────────────────┐         ┌──────────────┐
│   Client    │◄───────►│   Coordinator    │◄───────►│ Storage Node │
│  (Frontend) │  Socket │     Server       │  Socket │  (Data Plane)│
└─────────────┘         └──────────────────┘         └──────────────┘
                              │      │
                              ▼      ▼
                        ┌──────┐  ┌───────┐
                        │ Redis│  │ PG DB │
                        └──────┘  └───────┘
```

### 1.3 Công nghệ sử dụng
- **Ngôn ngữ**: Python 3.9+
- **Database**: PostgreSQL 12+ (metadata, audit logs)
- **Cache**: Redis 6+ (session tokens)
- **Protocol**: Socket-based với frame encoding
- **Security**: bcrypt password hashing, HMAC ticket signing

---

## 2. KIẾN TRÚC DATABASE

### 2.1 Nguyên tắc phân chia dữ liệu

| Loại dữ liệu | Lưu trữ | Lý do |
|--------------|---------|-------|
| Users, Rooms, Files | PostgreSQL | Dữ liệu lâu dài, cần ACID, cần join |
| Access Tokens | Redis | Tần suất truy cập cao, có TTL, tự động expire |
| Upload Sessions | Storage Node | Coordinator không track chunk |
| Notification Subscriptions | In-memory | Chỉ 1 instance, client reconnect khi mất |

### 2.2 Schema PostgreSQL (7 bảng)

#### Bảng `users`
```sql
- id: UUID (PK)
- username: VARCHAR(50) UNIQUE
- email: VARCHAR(255) UNIQUE  
- password_hash: VARCHAR(255) -- bcrypt cost 12
- global_role: VARCHAR(10) -- 'USER' hoặc 'ADMIN'
- created_at, updated_at: TIMESTAMPTZ
```

#### Bảng `rooms`
```sql
- id: UUID (PK)
- name: VARCHAR(100)
- created_by: UUID FK → users
- created_at: TIMESTAMPTZ
```

#### Bảng `room_members`
```sql
- room_id: UUID FK → rooms (Composite PK)
- user_id: UUID FK → users (Composite PK)
- role: VARCHAR(10) -- 'OWNER', 'MEMBER', 'VIEWER'
- added_at: TIMESTAMPTZ
- INDEX: user_id (cho query ngược)
```

#### Bảng `files`
```sql
- id: UUID (PK)
- room_id: UUID FK → rooms
- original_name: VARCHAR(255)
- stored_name: VARCHAR(255) -- path trên Storage Node
- version: INT -- auto-increment per file name
- uploader_id: UUID FK → users
- size_bytes: BIGINT
- mime_type: VARCHAR(100)
- sha256_whole: CHAR(64) -- hex string
- total_chunks: INT
- chunk_size: INT
- status: VARCHAR(15) -- 'UPLOADING', 'READY', 'DELETED'
- created_at: TIMESTAMPTZ
- INDEX: room_id, sha256_whole, (room_id, original_name)
```

#### Bảng `share_tokens`
```sql
- id: UUID (PK)
- token: CHAR(64) UNIQUE -- random hex
- file_id: UUID FK → files
- created_by: UUID FK → users
- max_downloads: INT
- download_count: INT DEFAULT 0
- expires_at: TIMESTAMPTZ
- created_at: TIMESTAMPTZ
```

#### Bảng `scan_reports`
```sql
- id: SERIAL (PK)
- file_id: UUID FK → files
- tool: VARCHAR(50)
- tool_version: VARCHAR(20)
- scanned_at: TIMESTAMPTZ
- result: VARCHAR(10) -- 'CLEAN' hoặc 'INFECTED'
- file_sha256: CHAR(64)
```

#### Bảng `audit_logs`
```sql
- id: BIGSERIAL (PK)
- actor_id: UUID (nullable)
- action: VARCHAR(30)
- target_type: VARCHAR(20)
- target_id: VARCHAR(36)
- room_id: UUID (nullable)
- detail: JSONB (nullable)
- status: VARCHAR(10) -- 'SUCCESS' hoặc 'FAILED'
- created_at: TIMESTAMPTZ
- INDEX: created_at, room_id, actor_id
```

### 2.3 Redis Schema

**Access Tokens**
```
Key: session:{token_uuid}
Value: JSON {
  "userId": "user-uuid",
  "globalRole": "USER",
  "createdAt": "2025-01-15T10:00:00Z"
}
TTL: 24 giờ (86400 seconds)
```

---

## 3. GIAO THỨC SOCKET

### 3.1 Frame-Based Protocol

**Format**: Length-Prefixed Frames
```
┌────────────┬──────────────────┐
│ 4 bytes    │ N bytes          │
│ Length (BE)│ JSON Message     │
└────────────┴──────────────────┘
```

- **Max message size**: 10 MB
- **Encoding**: UTF-8 JSON
- **Xử lý**: FrameBuffer tích lũy partial frames

### 3.2 Message Format

```json
{
  "type": "MESSAGE_TYPE",
  "requestId": "uuid",
  "payload": {
    // message-specific data
  }
}
```

### 3.3 Các loại Socket

| Socket | Port | Mục đích | Kết nối |
|--------|------|----------|---------|
| Client Socket | 8080 | Client ↔ Coordinator | Nhiều connections |
| Storage Socket | 8081 | Storage Node ↔ Coordinator | Persistent connection |
| Notification Socket | 8082 | Client ↔ Coordinator | Long-lived connections |

---

## 4. CÁC MODULE CHÍNH

### 4.1 Authentication Module

**Chức năng**:
- Đăng ký user (SIGNUP)
- Đăng nhập (LOGIN)
- Xác thực token (middleware)
- Đăng xuất (LOGOUT)

**Luồng đăng nhập**:
```
Client → SIGNUP → validate → bcrypt hash → INSERT users → OK
Client → LOGIN → verify password → gen UUID token → SET Redis → return token
Client → REQUEST (kèm token) → GET Redis → validate → proceed
Client → LOGOUT → DEL Redis → OK
```

**Bảo mật**:
- bcrypt cost factor 12 (4096 iterations)
- UUID tokens (128-bit random)
- Session TTL 24 giờ tự động expire
- Generic error messages (không lộ username tồn tại)

### 4.2 Authorization Module

**Ma trận phân quyền**:

| Hành động | ADMIN | OWNER | MEMBER | VIEWER |
|-----------|-------|-------|--------|--------|
| Tạo phòng | ✓ | — | — | — |
| Thêm/xóa member | ✓ | ✓ | ✗ | ✗ |
| Đổi role | ✓ | ✓ | ✗ | ✗ |
| Upload file | ✓ | ✓ | ✓ | ✗ |
| Download file | ✓ | ✓ | ✓ | ✓ |
| Xem file list | ✓ | ✓ | ✓ | ✓ |
| Tạo share token | ✓ | ✓ | ✓ | ✗ |
| Xóa file | ✓ | ✓ | ✗ | ✗ |

**Quy tắc**:
- ADMIN có full quyền mọi phòng
- Người tạo phòng tự động thành OWNER
- Không tự đổi role chính mình
- Phòng phải luôn có ít nhất 1 OWNER

### 4.3 Room Management Module

**API**:
- `CREATE_ROOM` - Tạo phòng mới (chỉ ADMIN)
- `ADD_MEMBER` - Thêm thành viên (ADMIN/OWNER)
- `REMOVE_MEMBER` - Xóa thành viên (ADMIN/OWNER)
- `SET_ROLE` - Đổi role (ADMIN/OWNER)
- `LIST_ROOMS` - Danh sách phòng của user
- `LIST_MEMBERS` - Danh sách thành viên phòng

### 4.4 File Management Module

**API**:
- `LIST_FILES` - Danh sách file trong phòng
- `FILE_DETAIL` - Chi tiết file
- `FILE_VERSIONS` - Lịch sử version
- `DELETE_FILE` - Xóa file (soft delete)

**Versioning**:
- Upload trùng tên → version + 1
- Query: `SELECT MAX(version) WHERE room_id AND original_name`
- Không ghi đè file cũ

---

## 5. LUỒNG UPLOAD (OPTION A)

### 5.1 Tổng quan

```
Client              Coordinator           Storage Node
  |                      |                      |
  |-- INIT_UPLOAD ------>|                      |
  |  (file info + scan)  |                      |
  |                      |-- check quyền        |
  |                      |-- validate scan      |
  |                      |-- check dedup        |
  |                      |-- INSERT file (PG)   |
  |                      |-- sinh HMAC ticket   |
  |<-- UPLOAD_PLAN ------|                      |
  |  (ticket, address)   |                      |
  |                      |                      |
  |========== UPLOAD CHUNKS ==================>|
  |  (trực tiếp, không qua Coordinator)        |
  |                      |                      |
  |                      |<-- UPLOAD_COMPLETE --|
  |                      |-- UPDATE file READY  |
  |                      |-- broadcast event    |
```

### 5.2 INIT_UPLOAD Request

```json
{
  "type": "INIT_UPLOAD",
  "token": "access-token",
  "roomId": "room-uuid",
  "fileName": "report.pdf",
  "fileSize": 10485760,
  "mimeType": "application/pdf",
  "sha256Whole": "a1b2c3...64 hex",
  "scanReport": {
    "tool": "ClamAV",
    "toolVersion": "1.0.0",
    "scannedAt": "2025-01-15T10:00:00Z",
    "result": "CLEAN",
    "fileSha256": "a1b2c3...phải khớp sha256Whole"
  }
}
```

### 5.3 Xử lý INIT_UPLOAD

1. **Check token** (Redis) → lấy userId
2. **Check quyền** upload trong room (PG)
3. **Validate scan report**:
   - result == "CLEAN" (reject nếu INFECTED)
   - fileSha256 == sha256Whole
   - scannedAt không quá 10 phút
4. **Check dedup**: Query file cùng sha256_whole
   - Nếu có → tạo record mới trỏ cùng stored_name
   - Nếu không → tiếp tục
5. **Tính chunks**: totalChunks = ceil(fileSize / chunkSize)
6. **INSERT file** (status = UPLOADING)
7. **INSERT scan_report**
8. **Sinh HMAC ticket**
9. **Ghi audit log**
10. **Trả UPLOAD_PLAN**

### 5.4 HMAC Ticket

**Tại sao HMAC?**
- Storage Node tự verify, không cần gọi Coordinator
- Zero round-trip, không phụ thuộc Coordinator khi upload
- Ticket tự hết hạn (30 phút)

**Format**:
```
base64url(JSON payload) + "." + base64url(HMAC-SHA256)
```

**Payload**:
```json
{
  "fileId": "file-uuid",
  "userId": "user-uuid",
  "roomId": "room-uuid",
  "totalChunks": 20,
  "chunkSize": 524288,
  "sha256Whole": "a1b2c3...",
  "expiresAt": "2025-01-15T10:30:00Z"
}
```

**Secret key**: Chia sẻ qua environment variable

### 5.5 UPLOAD_PLAN Response

```json
{
  "type": "UPLOAD_PLAN",
  "fileId": "file-uuid",
  "ticket": "base64.base64",
  "storageAddress": "host:port",
  "chunkSize": 524288,
  "totalChunks": 20,
  "deduplicated": false
}
```

### 5.6 UPLOAD_COMPLETE (Storage Node → Coordinator)

```json
{
  "type": "UPLOAD_COMPLETE",
  "fileId": "file-uuid",
  "sha256Whole": "a1b2c3...",
  "storedName": "path/on/storage",
  "finalSize": 10485760
}
```

**Coordinator xử lý**:
1. UPDATE files SET status = 'READY'
2. Ghi audit log
3. Broadcast NEW_FILE event
4. Trả ACK cho Storage Node

### 5.7 Deduplication

**Cơ chế**:
- Check `sha256_whole` trước khi upload
- Nếu trùng → tạo file record mới trỏ cùng `stored_name`
- Tiết kiệm storage, upload nhanh

**Xóa file với dedup**:
- Check `COUNT(*) WHERE sha256_whole AND status = 'READY'`
- Nếu > 0 → không xóa data vật lý

---

## 6. LUỒNG DOWNLOAD

### 6.1 Tổng quan

```
Client              Coordinator           Storage Node
  |                      |                      |
  |-- INIT_DOWNLOAD ---->|                      |
  |  (fileId hoặc token) |                      |
  |                      |-- check quyền/token  |
  |                      |-- sinh HMAC ticket   |
  |<-- DOWNLOAD_PLAN ----|                      |
  |  (ticket, address)   |                      |
  |                      |                      |
  |========== DOWNLOAD CHUNKS =================>|
  |  (trực tiếp, không qua Coordinator)        |
```

### 6.2 INIT_DOWNLOAD (2 cách)

**Cách 1 - Bằng quyền trực tiếp**:
```json
{
  "type": "INIT_DOWNLOAD",
  "token": "access-token",
  "fileId": "file-uuid",
  "version": 2  // optional, mặc định latest
}
```

**Cách 2 - Bằng share token**:
```json
{
  "type": "INIT_DOWNLOAD",
  "shareToken": "random-hex-token",
  "fileId": "file-uuid"
}
```

### 6.3 Xử lý Share Token

**Atomic SQL**:
```sql
UPDATE share_tokens 
SET download_count = download_count + 1 
WHERE token = $1 
  AND download_count < max_downloads 
  AND expires_at > NOW() 
RETURNING *
```

- Trả row → OK
- Không trả row → hết lượt hoặc hết hạn
- Trừ lượt lúc INIT_DOWNLOAD (không phải lúc download xong)

### 6.4 DOWNLOAD_PLAN Response

```json
{
  "type": "DOWNLOAD_PLAN",
  "fileId": "file-uuid",
  "fileName": "report.pdf",
  "fileSize": 10485760,
  "sha256Whole": "a1b2c3...",
  "totalChunks": 20,
  "chunkSize": 524288,
  "ticket": "base64.base64",
  "storageAddress": "host:port"
}
```

---

## 7. NOTIFICATION SYSTEM

### 7.1 Cơ chế

- Client mở socket tới Coordinator
- Gửi token xác thực
- `SUBSCRIBE_ROOM` → nhận events
- Subscriber map lưu **in-memory** (không Redis)

### 7.2 Các loại Event

| Event | Trigger | Payload |
|-------|---------|---------|
| NEW_FILE | Upload complete | fileId, fileName, uploader, roomId |
| FILE_DELETED | Delete file | fileId, fileName, deletedBy, roomId |
| MEMBER_ADDED | Add member | userId, username, role, roomId |
| MEMBER_REMOVED | Remove member | userId, username, roomId |
| ROLE_UPDATED | Set role | userId, username, newRole, roomId |

### 7.3 API

- `SUBSCRIBE_ROOM` - Đăng ký nhận event
- `UNSUBSCRIBE_ROOM` - Hủy đăng ký
- `EVENT` - Server push event tới client

---

## 8. STORAGE NODE COMMUNICATION

### 8.1 Persistent Socket

- Storage Node connect tới Coordinator khi khởi động
- 1 socket persistent, không per-request
- Coordinator biết Storage Node đang sống

### 8.2 Heartbeat

- Storage Node gửi `PING` mỗi 30 giây
- Coordinator trả `PONG`
- Không nhận PING trong 90 giây → coi dead
- Socket đứt → reconnect với backoff (1s, 2s, 4s, max 30s)

### 8.3 Messages

| Message | Hướng | Mục đích |
|---------|-------|----------|
| PING/PONG | Storage → Coordinator | Heartbeat |
| UPLOAD_COMPLETE | Storage → Coordinator | Upload thành công |
| UPLOAD_FAILED | Storage → Coordinator | Upload thất bại |
| ACK | Coordinator → Storage | Xác nhận |

---

## 9. AUDIT LOGGING

### 9.1 Các Action được log

| Action | Target Type | Khi nào |
|--------|-------------|---------|
| SIGNUP | user | Đăng ký |
| LOGIN | user | Đăng nhập |
| CREATE_ROOM | room | Tạo phòng |
| ADD_MEMBER | room_member | Thêm thành viên |
| REMOVE_MEMBER | room_member | Xóa thành viên |
| SET_ROLE | room_member | Đổi role |
| UPLOAD | file | Upload complete |
| DOWNLOAD | file | Init download |
| DELETE_FILE | file | Xóa file |
| CREATE_SHARE_TOKEN | share_token | Tạo token |
| USE_SHARE_TOKEN | share_token | Dùng token |

### 9.2 Ghi log

- **Đồng bộ**: INSERT ngay trong transaction
- **Không mất log**: Quan trọng hơn performance
- **JSONB detail**: Lưu thông tin bổ sung

---

## 10. MÃ LỖI

| Mã | Ý nghĩa |
|----|----------|
| AUTH_REQUIRED | Thiếu token |
| INVALID_TOKEN | Token sai hoặc hết hạn |
| PERMISSION_DENIED | Không đủ quyền |
| ROOM_NOT_FOUND | Phòng không tồn tại |
| FILE_NOT_FOUND | File không tồn tại |
| USER_NOT_FOUND | User không tồn tại |
| DUPLICATE_EMAIL | Email đã tồn tại |
| DUPLICATE_USERNAME | Username đã tồn tại |
| ALREADY_MEMBER | User đã là member |
| SCAN_FAILED | Scan report không clean |
| SCAN_EXPIRED | Scan report quá cũ |
| SCAN_HASH_MISMATCH | Hash không khớp |
| UPLOAD_SESSION_EXPIRED | Ticket hết hạn |
| HASH_MISMATCH | Hash file không khớp |
| SHARE_TOKEN_EXPIRED | Share token hết hạn |
| SHARE_TOKEN_EXHAUSTED | Hết lượt tải |
| INVALID_SHARE_TOKEN | Token không tồn tại |
| CANNOT_REMOVE_LAST_OWNER | Phải có ít nhất 1 OWNER |
| CANNOT_CHANGE_OWN_ROLE | Không tự đổi role |
| STORAGE_NODE_UNAVAILABLE | Storage Node không kết nối |

---

## 11. TRẠNG THÁI TRIỂN KHAI

### 11.1 Đã hoàn thành ✅

- ✅ Database schema (7 bảng + migrations)
- ✅ Redis connection + session storage
- ✅ Socket protocol (frame codec, message format)
- ✅ Authentication module (signup, login, logout)
- ✅ Authorization module (permission checking)
- ✅ Room management (create, add/remove member, set role)
- ✅ File management (list, detail, versions, delete)
- ✅ Upload control plane (init, ticket, complete)
- ✅ Download control plane (init, share token)
- ✅ Notification system (subscribe, broadcast)
- ✅ Storage Node communication (heartbeat, callbacks)
- ✅ Audit logging
- ✅ Health check
- ✅ Comprehensive test suite

### 11.2 Test Coverage

**Total Tests**: 100+ tests
- Protocol tests: 20 tests
- Auth tests: 21 tests
- Authorization tests: 15 tests
- Room tests: 18 tests
- File tests: 12 tests
- Upload tests: 10 tests
- Download tests: 8 tests
- Notification tests: 6 tests

**All tests passing** ✅

---

## 12. DEPLOYMENT

### 12.1 Docker Setup

**docker-compose.yml**:
```yaml
services:
  postgres:
    image: postgres:14
    environment:
      POSTGRES_DB: coordinator
      POSTGRES_USER: coordinator
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
  
  redis:
    image: redis:7
    ports:
      - "6379:6379"
  
  coordinator:
    build: .
    depends_on:
      - postgres
      - redis
    ports:
      - "8080:8080"  # Client socket
      - "8081:8081"  # Storage socket
      - "8082:8082"  # Notification socket
    environment:
      DB_HOST: postgres
      REDIS_HOST: redis
```

### 12.2 Configuration

**Environment Variables**:
```bash
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=coordinator
DB_USER=coordinator
DB_PASSWORD=password

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Server
SERVER_CLIENT_PORT=8080
SERVER_STORAGE_PORT=8081
SERVER_NOTIFICATION_PORT=8082

# Security
HMAC_SECRET_KEY=your-secret-key-here
SESSION_TTL_SECONDS=86400

# Upload
UPLOAD_CHUNK_SIZE=524288
```

### 12.3 Chạy hệ thống

```bash
# Setup
cd coordinator-server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Migrate database
alembic upgrade head

# Run server
python main.py
```

---

## 13. GIỚI HẠN VÀ CÂN NHẮC

### 13.1 Single Point of Failure
- Chỉ 1 Coordinator instance
- Down → không login, không init upload/download
- **Giảm thiểu**: Auto-restart (systemd/Docker)

### 13.2 Redis Crash
- Mất tất cả session → user login lại
- Upload/download đang dở không ảnh hưởng
- **Giảm thiểu**: Redis AOF persistence

### 13.3 HMAC Ticket không tự hủy (Revoke)
- Ticket không thể hủy tức thời sau khi sinh.
- User bị xóa khỏi phòng vẫn upload/download được (trong suốt thời gian Ticket còn hiệu lực).
- **Giảm thiểu hiện tại**: Cài đặt vòng đời Ticket (TTL) ngắn (15-30 phút).
- **Hướng giải pháp nâng cấp (Blacklist qua Socket)**: Tận dụng kênh liên kết Persistent Socket (port 8081) có sẵn. Ngay khi User bị tước quyền, Coordinator đẩy luồng `KILL_SESSION` xuống Storage Node. Storage Node đưa SessionID này vào Danh sách đen (In-memory Blacklist) và lập tức đóng sập kết nối TCP của User, đảm bảo trễ cực thấp và vẫn giữ được kiến trúc truyền file Zero round-trip gốc.

### 13.4 Scan Report có thể giả
- Client tự scan, có thể gửi report giả
- **Giảm thiểu**: Check hash + timestamp, nhưng không 100%
- **Giải pháp đúng**: Scan trên server (ngoài scope)

### 13.5 Không có Rate Limiting
- User có thể spam requests
- **Giảm thiểu**: Implement Redis counter (nếu có thời gian)

### 13.6 Notification không đảm bảo delivery
- Fire-and-forget, mất kết nối → mất event
- **Giảm thiểu**: Client sync lại bằng LIST_FILES

---

## 14. ĐIỂM MẠNH

### 14.1 Kiến trúc rõ ràng
- Tách biệt control plane / data plane
- Module hóa tốt (auth, room, file, upload, download)
- Dễ maintain và mở rộng

### 14.2 Bảo mật
- bcrypt password hashing
- Session-based authentication
- HMAC ticket signing
- Permission checking đầy đủ
- Audit logging toàn diện

### 14.3 Performance
- Redis cho session (high-frequency reads)
- PostgreSQL connection pooling
- Frame-based protocol (efficient)
- Deduplication tiết kiệm storage

### 14.4 Reliability
- Database migrations (Alembic)
- Comprehensive test suite
- Error handling đầy đủ
- Audit trail cho mọi action

### 14.5 Developer Experience
- Structured logging (JSON)
- Clear error messages
- Comprehensive documentation
- Example integration code

---

## 15. KẾT LUẬN

### 15.1 Tóm tắt
Coordinator Server là **control plane** hoàn chỉnh cho hệ thống truyền file LAN phân tán:
- Quản lý user, phòng, quyền
- Điều phối upload/download
- Audit logging đầy đủ
- Real-time notifications
- Bảo mật tốt

### 15.2 Thành tựu
- **1,500+ lines** production code
- **100+ tests** passing
- **7 bảng** database với migrations
- **15+ modules** được triển khai
- **3 socket servers** (client, storage, notification)

### 15.3 Sẵn sàng production
- ✅ Database schema hoàn chỉnh
- ✅ All core features implemented
- ✅ Comprehensive test coverage
- ✅ Docker deployment ready
- ✅ Documentation đầy đủ

---

## PHỤ LỤC: DEMO FLOW

### A. User Signup & Login
```
1. Client → SIGNUP (username, email, password)
2. Coordinator → hash password → INSERT users → OK
3. Client → LOGIN (username, password)
4. Coordinator → verify → gen token → SET Redis → return token
```

### B. Create Room & Add Member
```
1. Client → CREATE_ROOM (token, name)
2. Coordinator → check ADMIN → INSERT room + room_member → OK
3. Client → ADD_MEMBER (token, roomId, userId, role)
4. Coordinator → check OWNER → INSERT room_member → broadcast
```

### C. Upload File
```
1. Client → scan file locally → gen sha256
2. Client → INIT_UPLOAD (token, roomId, fileInfo, scanReport)
3. Coordinator → validate → check dedup → gen ticket → UPLOAD_PLAN
4. Client → connect Storage Node → OPEN_UPLOAD (ticket)
5. Client → UPLOAD_CHUNK × N → Storage Node
6. Client → FINALIZE_UPLOAD → Storage Node
7. Storage Node → UPLOAD_COMPLETE → Coordinator
8. Coordinator → UPDATE file READY → broadcast NEW_FILE
```

### D. Download File
```
1. Client → INIT_DOWNLOAD (token, fileId)
2. Coordinator → check permission → gen ticket → DOWNLOAD_PLAN
3. Client → connect Storage Node → OPEN_DOWNLOAD (ticket)
4. Client → REQUEST_CHUNK × N → Storage Node
5. Storage Node → send chunks → Client
```

### E. Share File
```
1. Client → CREATE_SHARE_TOKEN (token, fileId, maxDownloads, expiresAt)
2. Coordinator → check permission → gen random token → INSERT → return
3. Share token → other user
4. Other user → INIT_DOWNLOAD (shareToken, fileId)
5. Coordinator → atomic decrement → gen ticket → DOWNLOAD_PLAN
```
