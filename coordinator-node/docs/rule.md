# Role 1 — Coordinator Server: Task & Mô tả hệ thống (v3 — Option A)

## Tổng quan

Coordinator là **control plane** — quản lý ai được làm gì, file nào ở đâu, ghi log. Coordinator **không** lưu data file thật và **không** theo dõi quá trình upload từng chunk.

Theo Option A, vai trò Coordinator trong luồng upload thu gọn thành:
- **Đầu:** nhận yêu cầu upload → check quyền, check scan → sinh ticket → trả cho client.
- **Giữa:** không làm gì. Client upload chunk thẳng lên Storage Node.
- **Cuối:** nhận thông báo từ Storage Node (thành công/thất bại) → cập nhật DB → broadcast notification.

Giao tiếp giữa tất cả các bên (Client ↔ Coordinator, Client ↔ Storage Node, Storage Node ↔ Coordinator) đều qua **socket** để tối ưu tốc độ.

---

## Kiến trúc lưu trữ: PostgreSQL + Redis

### Nguyên tắc phân chia

- **PostgreSQL:** dữ liệu không được mất, cần query phức tạp, cần join, cần ACID.
- **Redis:** dữ liệu tạm, truy cập cực thường xuyên, có TTL, mất khi restart thì chấp nhận được.

### Bảng phân bổ dữ liệu (đã cập nhật theo Option A)

| Dữ liệu | Lưu ở đâu | Lý do |
|----------|-----------|-------|
| users, rooms, room_members | PostgreSQL | Dữ liệu lâu dài, cần join, cần unique |
| files | PostgreSQL | Metadata file, cần query theo room, theo hash |
| share_tokens | PostgreSQL | Cần atomic update download_count, cần persist |
| scan_reports | PostgreSQL | Lưu lâu dài cho audit |
| audit_logs | PostgreSQL | Không được mất |
| access_tokens (session login) | Redis | Tạm, TTL, check mỗi request, mất thì login lại |
| notification subscriber map | In-memory (application) | Chỉ 1 instance Coordinator, mất thì client reconnect |
| ~~upload sessions~~ | ~~Redis~~ → **Storage Node tự lo** | Option A: Coordinator không track |
| ~~chunk tracking~~ | ~~Redis~~ → **Storage Node tự lo** | Option A: Coordinator không track |
| ~~download sessions~~ | Không cần lưu | Dùng HMAC ticket, tự verify, không cần session |

**So với bản v2:** Redis nhẹ hơn rất nhiều. Chỉ còn lưu access token. Upload session, chunk tracking, download session đều bỏ khỏi Redis.

---

## A. Thiết kế Database (PostgreSQL)

### A.1 Bảng `users`

| Cột | Kiểu | Ghi chú |
|-----|------|---------|
| id | UUID | Khóa chính |
| username | VARCHAR(50) | Unique |
| email | VARCHAR(255) | Unique |
| password_hash | VARCHAR(255) | bcrypt hoặc argon2, salt nhúng trong hash |
| global_role | VARCHAR(10) | 'USER' hoặc 'ADMIN' |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

**Lựa chọn & trade-off:**

**id — UUID vs auto-increment:**
- UUID: không đoán được, an toàn khi expose ra API, merge DB dễ. Nhược: 16 bytes, index B-tree phân tán, insert chậm hơn ~10–15%.
- Auto-increment: nhỏ gọn, insert nhanh. Nhược: lộ số lượng user, đoán được ID.
- **Chọn UUID** vì id xuất hiện trong API response, token, audit log — cần không đoán được.

**password_hash — bcrypt vs argon2:**
- bcrypt: thư viện ổn định, dùng rộng rãi, salt tự nhúng trong output. Nhược: chỉ chống GPU, không chống ASIC.
- argon2id: chống cả GPU lẫn ASIC, tune được memory + time cost. Nhược: thư viện ít phổ biến, config phức tạp hơn.
- **Chọn bcrypt** nếu muốn đơn giản. Cả 2 đều không cần cột salt riêng.

**global_role — VARCHAR vs DB ENUM:**
- DB ENUM: DB enforce giá trị, không insert sai. Nhược: thêm role phải ALTER TYPE, migration phiền.
- VARCHAR + check application: linh hoạt, thêm role không cần migration. Nhược: DB không enforce.
- **Chọn VARCHAR** vì role có thể thay đổi, tránh migration chỉ để thêm 1 giá trị.

### A.2 Bảng `rooms`

| Cột | Kiểu | Ghi chú |
|-----|------|---------|
| id | UUID | Khóa chính |
| name | VARCHAR(100) | |
| created_by | UUID FK → users | |
| created_at | TIMESTAMPTZ | |

**Không có soft delete cho room.** Thêm soft delete sẽ cần check status ở mọi query liên quan. Nếu cần sau này, thêm cột `deleted_at TIMESTAMPTZ NULL`.

### A.3 Bảng `room_members`

| Cột | Kiểu | Ghi chú |
|-----|------|---------|
| room_id | UUID FK → rooms | Composite PK phần 1 |
| user_id | UUID FK → users | Composite PK phần 2 |
| role | VARCHAR(10) | 'OWNER', 'MEMBER', 'VIEWER' |
| added_at | TIMESTAMPTZ | |

**PK — composite (room_id, user_id) vs id riêng:**
- Composite: enforce unique tự nhiên, 1 index thay vì 2. Nhược: FK từ bảng khác cần 2 cột.
- Id riêng + unique constraint: FK đơn giản hơn. Nhược: thêm 1 index.
- **Chọn composite PK** vì không bảng nào FK vào room_members.

**Index bổ sung:** `user_id` — vì query "user này thuộc room nào" (LIST_ROOMS) cần index ngược.

### A.4 Bảng `files`

| Cột | Kiểu | Ghi chú |
|-----|------|---------|
| id | UUID | Khóa chính |
| room_id | UUID FK → rooms | |
| original_name | VARCHAR(255) | Tên gốc |
| stored_name | VARCHAR(255) | Tên/path trên Storage Node |
| version | INT | Bắt đầu từ 1 |
| uploader_id | UUID FK → users | |
| size_bytes | BIGINT | |
| mime_type | VARCHAR(100) | |
| sha256_whole | CHAR(64) | Hex string, 64 ký tự cố định |
| total_chunks | INT | |
| chunk_size | INT | Bytes per chunk, lưu để download plan không cần tính lại |
| status | VARCHAR(15) | 'UPLOADING', 'READY', 'DELETED' |
| created_at | TIMESTAMPTZ | |

**sha256_whole — CHAR(64) vs BYTEA(32):**
- CHAR(64): đọc được trong query/log, so sánh trực tiếp với giá trị client gửi (hex). Nhược: 64 bytes thay vì 32.
- BYTEA(32): tiết kiệm, index nhỏ hơn. Nhược: phải encode/decode, debug khó.
- **Chọn CHAR(64)** vì tiện debug, file metadata không nhiều row.

**chunk_size — lưu vs tính lại:**
- Lưu: download plan trả ngay, file cũ vẫn đúng khi config thay đổi. Nhược: 4 bytes/row.
- Không lưu: phải giả định chunk_size cố định mãi mãi.
- **Chọn lưu** vì chi phí thấp, đảm bảo đúng khi config thay đổi.

**version — number vs stored_name theo hash:**
- Version number: user đọc được, xem lịch sử trực quan. Nhược: cần logic auto-increment per (room_id, original_name).
- stored_name theo hash: tự unique. Nhược: không có khái niệm lịch sử.
- **Chọn version number** vì proposal yêu cầu lịch sử version.

**Index:** `room_id`, `sha256_whole`, `(room_id, original_name)`.

### A.5 Bảng `share_tokens`

| Cột | Kiểu | Ghi chú |
|-----|------|---------|
| id | UUID | Khóa chính |
| token | CHAR(64) | Random 32 bytes → hex, unique |
| file_id | UUID FK → files | |
| created_by | UUID FK → users | |
| max_downloads | INT | |
| download_count | INT | Mặc định 0 |
| expires_at | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ | |

**Tại sao PostgreSQL thay vì Redis?**
- PG: atomic `UPDATE ... SET download_count = download_count + 1 WHERE download_count < max_downloads` — chống race condition bằng 1 câu SQL. Persist qua restart.
- Redis: INCR nhanh hơn nhưng check max cần Lua script, mất khi restart.
- **Chọn PG** vì atomic update đơn giản hơn, share token không phải high-frequency.

### A.6 Bảng `scan_reports`

| Cột | Kiểu | Ghi chú |
|-----|------|---------|
| id | SERIAL | Khóa chính |
| file_id | UUID FK → files | |
| tool | VARCHAR(50) | |
| tool_version | VARCHAR(20) | |
| scanned_at | TIMESTAMPTZ | |
| result | VARCHAR(10) | 'CLEAN' hoặc 'INFECTED' |
| file_sha256 | CHAR(64) | Đối chiếu với sha256_whole |

**id — SERIAL vs UUID:** internal record, không expose ra API → SERIAL đủ và hiệu quả hơn.

### A.7 Bảng `audit_logs`

| Cột | Kiểu | Ghi chú |
|-----|------|---------|
| id | BIGSERIAL | Khóa chính |
| actor_id | UUID (nullable) | Null nếu anonymous |
| action | VARCHAR(30) | |
| target_type | VARCHAR(20) | |
| target_id | VARCHAR(36) | UUID string |
| room_id | UUID (nullable) | |
| detail | JSONB (nullable) | |
| status | VARCHAR(10) | 'SUCCESS' hoặc 'FAILED' |
| created_at | TIMESTAMPTZ | |

**id — BIGSERIAL:** audit log nhiều row, sequential insert nhanh, không cần expose ra ngoài.

**detail — JSONB vs TEXT:**
- JSONB: query được nội dung, index được. Nhược: insert chậm hơn TEXT nếu JSON lớn.
- TEXT: nhanh insert, không query được.
- **Chọn JSONB** vì detail thường nhỏ, có thể cần query sau.

**Ghi đồng bộ vs bất đồng bộ:**
- Đồng bộ: không mất log. Nhược: mỗi action chậm thêm 1 insert.
- Bất đồng bộ: nhanh. Nhược: crash → mất log.
- **Chọn đồng bộ** vì audit log là bắt buộc, mất log nghiêm trọng hơn chậm vài ms.

**Index:** `created_at`, `room_id`, `actor_id`.

### Task DB

- T-A1: Vẽ ERD.
- T-A2: Viết migration script tạo tất cả bảng, constraint, index.
- T-A3: Viết seed data (2–3 user, 1–2 room, vài file record).
- T-A4: Chạy DB, insert/query thử verify.

---

## B. Redis (chỉ còn access token)

### B.1 Access tokens

**Key:** `session:{token_uuid}`
**Value:** JSON string
```json
{
  "userId": "user-uuid",
  "globalRole": "USER",
  "createdAt": "2025-01-15T10:00:00Z"
}
```
**TTL:** 24 giờ.

**Tại sao Redis thay vì PostgreSQL?**
- Mỗi request đều check token → tần suất cực cao. Redis GET O(1) nhanh hơn PG SELECT.
- Token có TTL → Redis tự xóa, không cần job dọn.
- Mất khi restart → user login lại, chấp nhận được.
- Revoke = DEL key, tức thì.

**Trade-off so với PG:**
- Mất: không query "user X có bao nhiêu session" dễ dàng. Nếu cần, thêm Set `user_sessions:{user_id}`.
- Được: giảm tải PG đáng kể.

### B.2 Những thứ đã bỏ khỏi Redis (theo Option A)

| Thứ đã bỏ | Lý do bỏ | Ai lo thay |
|-----------|---------|-----------|
| Upload session | Storage Node tự quản lý trong memory + disk | Người 2 |
| Chunk tracking | Storage Node tự đếm chunk đã nhận | Người 2 |
| Download session | Dùng HMAC ticket, tự verify, không cần session | Không ai cần lo |

### Task Redis

- T-B1: Setup Redis, test connection.
- T-B2: Implement SET/GET/DEL cho access token (dùng trong auth).

---

## C. Auth

### Luồng

```
SIGNUP:  client → socket → Coordinator → validate → hash password → INSERT users (PG) → trả ok
LOGIN:   client → socket → Coordinator → verify password (PG) → tạo token → SET session (Redis) → trả token
REQUEST: client gửi kèm token → middleware GET session (Redis) → có → tiếp / không → reject
LOGOUT:  client → socket → Coordinator → DEL session (Redis) → trả ok
```

### Task

- T-C1: `SIGNUP` — validate input → bcrypt hash (cost 12) → INSERT users (PG) → ghi audit → trả kết quả.
- T-C2: `LOGIN` — query user by username (PG) → verify password → tạo UUID token → SET Redis TTL 24h → ghi audit → trả token + expiresAt.
- T-C3: Middleware check token — GET session:{token} (Redis) → parse → gắn userId + globalRole vào context. Không tồn tại → trả lỗi.
- T-C4: `LOGOUT` — DEL session:{token} (Redis).
- T-C5: (Tùy chọn) Logout all sessions — lưu thêm Set `user_sessions:{user_id}`, DEL hết.
- T-C6: Test: sai password, token hết hạn, token không tồn tại, signup trùng email/username.

---

## D. Quản lý phòng và phân quyền

### Ma trận quyền

| Hành động | ADMIN | OWNER | MEMBER | VIEWER |
|-----------|-------|-------|--------|--------|
| Tạo phòng | ✓ | — | — | — |
| Thêm member | ✓ | ✓ | ✗ | ✗ |
| Xóa member | ✓ | ✓ | ✗ | ✗ |
| Đổi role | ✓ | ✓ | ✗ | ✗ |
| Upload file | ✓ | ✓ | ✓ | ✗ |
| Download file | ✓ | ✓ | ✓ | ✓ |
| Xem file list | ✓ | ✓ | ✓ | ✓ |
| Tạo share token | ✓ | ✓ | ✓ | ✗ |
| Xóa file | ✓ | ✓ | ✗ | ✗ |

### Quy tắc

- ADMIN có full quyền mọi phòng, không cần add vào room_members.
- Người tạo phòng tự động thành OWNER.
- Không tự đổi role chính mình.
- Phòng phải luôn có ít nhất 1 OWNER.

### Cache quyền trong Redis hay không?

- Cache: tránh query PG mỗi request. Nhược: phải invalidate khi đổi role, dễ stale.
- Không cache: luôn chính xác. Nhược: mỗi request 1 query PG.
- **Chọn không cache.** Query PG trên index (room_id, user_id) đủ nhanh. Cache tạo vấn đề invalidation.

### Task

- T-D1: Hàm `checkPermission(userId, roomId, action)` dùng chung — query room_members + check globalRole ADMIN → trả boolean. Mọi API đều gọi qua hàm này.
- T-D2: `CREATE_ROOM` — check ADMIN → INSERT rooms + INSERT room_members (OWNER) → ghi audit.
- T-D3: `ADD_MEMBER` — check ADMIN/OWNER → validate user tồn tại + chưa member → INSERT room_members → ghi audit → broadcast MEMBER_ADDED.
- T-D4: `REMOVE_MEMBER` — check quyền + check không xóa OWNER cuối cùng → DELETE → ghi audit → broadcast MEMBER_REMOVED.
- T-D5: `SET_ROLE` — check quyền + check không tự đổi role mình → UPDATE → ghi audit → broadcast ROLE_UPDATED.
- T-D6: `LIST_ROOMS` — query rooms mà user là member (hoặc tất cả nếu ADMIN), kèm role.
- T-D7: `LIST_MEMBERS` — check user là member hoặc ADMIN → query room_members join users.
- T-D8: Test toàn bộ ma trận quyền.

---

## E. Metadata file

### Quy tắc

- Upload trùng tên trong cùng phòng → version + 1, không ghi đè.
- Xóa: soft delete (status → DELETED), chỉ ADMIN/OWNER.

### Task

- T-E1: `LIST_FILES` — query files WHERE room_id AND status = 'READY'. Check quyền.
- T-E2: `FILE_DETAIL` — query file by id. Check quyền.
- T-E3: `FILE_VERSIONS` — query files WHERE room_id AND original_name, ORDER BY version DESC.
- T-E4: `DELETE_FILE` — check ADMIN/OWNER → UPDATE status = 'DELETED' → ghi audit → broadcast FILE_DELETED.
- T-E5: Logic auto-version — `SELECT MAX(version) FROM files WHERE room_id = ? AND original_name = ?` → version = max + 1.

---

## F. Upload control plane (đã cập nhật theo Option A)

### Luồng tổng thể

```
Client                    Coordinator                   Storage Node
  |                           |                              |
  |== socket 1 (control) ====|                               |
  |                           |== socket (internal) =========|
  |                           |                              |
  |-- INIT_UPLOAD ----------->|                              |
  |   (file info + scanReport)|                              |
  |                           |-- check quyền (PG)           |
  |                           |-- validate scan report        |
  |                           |-- check dedup (PG)            |
  |                           |-- INSERT file (PG, UPLOADING) |
  |                           |-- sinh HMAC ticket            |
  |<-- UPLOAD_PLAN -----------|                              |
  |   (ticket, storage addr)  |                              |
  |                           |                              |
  |== socket 2 (data) =======================================|
  |                           |                              |
  |-- OPEN_UPLOAD ------------------------------------------>|
  |   (kèm ticket)           |                              |-- verify HMAC
  |<-- OPEN_UPLOAD_RESP ------------------------------------ |-- tạo session (memory+disk)
  |                           |                              |
  |-- UPLOAD_CHUNK ----------------------------------------->|
  |<-- ACK_CHUNK ------------------------------------------- |-- ghi chunk vào disk
  |   (lặp lại cho mỗi chunk)|                              |
  |                           |                              |
  |-- FINALIZE_UPLOAD -------------------------------------->|
  |                           |                              |-- assemble file
  |                           |                              |-- verify sha256
  |                           |<-- UPLOAD_COMPLETE --------- |  (socket internal)
  |                           |-- UPDATE file READY (PG)     |
  |                           |-- ghi audit                  |
  |                           |-- broadcast NEW_FILE         |
  |                           |-- ACK ------------------->   |
  |<-- FINALIZE_RESP ------------------------------------ ---|
```

**Điểm khác biệt so với bản cũ:**
- Coordinator KHÔNG track từng chunk. Không có callback per chunk.
- Coordinator chỉ xuất hiện ở đầu (INIT_UPLOAD) và cuối (nhận UPLOAD_COMPLETE).
- Phần giữa (upload chunk) diễn ra hoàn toàn giữa Client ↔ Storage Node.

### INIT_UPLOAD — Coordinator nhận từ client

```json
{
  "type": "INIT_UPLOAD",
  "token": "access-token",
  "roomId": "room-uuid",
  "fileName": "report.pdf",
  "fileSize": 10485760,
  "mimeType": "application/pdf",
  "sha256Whole": "a1b2c3...64 hex chars",
  "scanReport": {
    "tool": "ClamAV",
    "toolVersion": "1.0.0",
    "scannedAt": "2025-01-15T10:00:00Z",
    "result": "CLEAN",
    "fileSha256": "a1b2c3...phải khớp sha256Whole"
  }
}
```

Coordinator xử lý:
1. Check token (Redis) → lấy userId.
2. Check quyền upload trong room (PG) — ADMIN/OWNER/MEMBER.
3. Validate scan report:
   - `result == "CLEAN"` → nếu INFECTED, reject.
   - `fileSha256 == sha256Whole` → không khớp, reject (client gửi report file khác).
   - `scannedAt` không quá 10 phút → tránh dùng lại report cũ.
4. Check dedup: `SELECT id, stored_name FROM files WHERE sha256_whole = ? AND status = 'READY' LIMIT 1`.
   - Nếu có → tạo file record mới trỏ cùng stored_name, trả `deduplicated: true`, xong.
   - Nếu không → tiếp tục.
5. Tính chunk: totalChunks = ceil(fileSize / chunkSize), chunkSize lấy từ config (ví dụ 512KB).
6. INSERT file record (PG, status = UPLOADING).
7. INSERT scan_report (PG).
8. Sinh HMAC ticket (xem phần ticket bên dưới).
9. Ghi audit log.
10. Trả UPLOAD_PLAN:

```json
{
  "type": "UPLOAD_PLAN",
  "fileId": "file-uuid",
  "ticket": "base64(payload).base64(hmac)",
  "storageAddress": "host:port",
  "chunkSize": 524288,
  "totalChunks": 20,
  "deduplicated": false
}
```

### HMAC Ticket — cách sinh và verify

**Tại sao dùng HMAC thay vì Storage Node gọi Coordinator verify?**
- HMAC: Storage Node tự verify chữ ký, không cần gọi Coordinator → không phụ thuộc Coordinator lúc upload, zero round-trip.
- Gọi Coordinator verify: đơn giản nhưng mỗi phiên upload tốn 1 round-trip, Coordinator down → upload chết.
- **Chọn HMAC** vì phù hợp tinh thần Option A: Storage Node hoạt động độc lập.
- Nhược điểm: không revoke ticket được. Nhưng ticket có expiresAt (30 phút) nên tự hết hạn.

**Format ticket:**
```
base64url(JSON payload) + "." + base64url(HMAC-SHA256 signature)
```

**Payload:**
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

**Secret key:** chia sẻ qua environment variable, cả Coordinator và Storage Node giữ giống nhau.

**Coordinator sinh:** tạo payload JSON → HMAC-SHA256 bằng secret key → ghép thành ticket.
**Storage Node verify:** tách payload + signature → tính lại HMAC → so sánh → check expiresAt.

### UPLOAD_COMPLETE / UPLOAD_FAILED — Storage Node báo Coordinator qua socket

Khi Storage Node assemble file xong:

```json
{
  "type": "UPLOAD_COMPLETE",
  "fileId": "file-uuid",
  "sha256Whole": "a1b2c3...",
  "storedName": "path/on/storage",
  "finalSize": 10485760
}
```

Coordinator nhận → UPDATE files SET status = 'READY', stored_name = storedName (PG) → ghi audit → broadcast NEW_FILE → trả ACK cho Storage Node.

Nếu thất bại:

```json
{
  "type": "UPLOAD_FAILED",
  "fileId": "file-uuid",
  "reason": "HASH_MISMATCH"
}
```

Coordinator nhận → UPDATE files SET status = 'DELETED' (PG) → ghi audit → trả ACK.

### Dedup

**Có dedup hay không?**
- Có: tiết kiệm storage, upload nhanh khi file trùng. Nhược: xóa file phải check reference count.
- Không: mỗi file 1 bản, xóa thoải mái. Nhược: tốn disk.
- **Gợi ý:** dedup đơn giản — chỉ skip upload nếu cùng sha256_whole. Khi xóa file, check `SELECT COUNT(*) FROM files WHERE sha256_whole = ? AND status = 'READY'` — nếu > 0 → không báo Storage Node xóa data.

### Task

- T-F1: Implement `INIT_UPLOAD` — validate token, check quyền, validate scan report, check dedup, tạo file record, sinh HMAC ticket, lưu scan report, ghi audit, trả UPLOAD_PLAN.
- T-F2: Implement hàm sinh HMAC ticket — tạo payload + ký bằng secret key. **Chốt format với Người 2.**
- T-F3: Implement handler nhận `UPLOAD_COMPLETE` từ Storage Node qua socket → UPDATE file status READY → ghi audit → broadcast NEW_FILE → trả ACK.
- T-F4: Implement handler nhận `UPLOAD_FAILED` từ Storage Node qua socket → UPDATE file status DELETED → ghi audit → trả ACK.
- T-F5: Implement dedup — nếu sha256_whole đã tồn tại, tạo file record mới trỏ cùng stored_name, trả deduplicated: true.
- T-F6: Job dọn file UPLOADING quá lâu — chạy định kỳ (ví dụ mỗi 10 phút), query `SELECT FROM files WHERE status = 'UPLOADING' AND created_at < now() - interval '1 hour'` → UPDATE status = 'DELETED'. Lý do: nếu client bỏ upload giữa chừng mà không FINALIZE, file record treo mãi.

---

## G. Download control plane (đã cập nhật theo Option A)

### Luồng

```
Client                    Coordinator                   Storage Node
  |                           |                              |
  |-- INIT_DOWNLOAD --------->|                              |
  |                           |-- check quyền / share token  |
  |                           |-- sinh HMAC download ticket   |
  |<-- DOWNLOAD_PLAN ---------|                              |
  |                           |                              |
  |-- OPEN_DOWNLOAD --------------------------------------------->|
  |   (kèm ticket)           |                              |-- verify HMAC
  |<-- chunk data ------------------------------------------------|
```

**Không cần download session trong Redis.** Coordinator sinh HMAC ticket chứa đủ thông tin (fileId, storedName, sha256_whole, totalChunks, chunkSize, expiresAt). Storage Node verify HMAC → đọc file → trả chunk. Không ai cần lưu session.

### INIT_DOWNLOAD

**Trường hợp 1 — download bằng quyền trực tiếp:**
```json
{
  "type": "INIT_DOWNLOAD",
  "token": "access-token",
  "fileId": "file-uuid",
  "version": 2
}
```
- Check token → check user là member hoặc ADMIN.
- Nếu không chỉ định version → lấy version mới nhất.

**Trường hợp 2 — download bằng share token:**
```json
{
  "type": "INIT_DOWNLOAD",
  "shareToken": "random-hex-token",
  "fileId": "file-uuid"
}
```
- Validate share token (PG): `UPDATE share_tokens SET download_count = download_count + 1 WHERE token = $1 AND download_count < max_downloads AND expires_at > NOW() RETURNING *`
- Nếu trả row → OK. Nếu không → hết lượt hoặc hết hạn.
- Không cần access_token.

**Response chung:**
```json
{
  "type": "DOWNLOAD_PLAN",
  "fileId": "file-uuid",
  "fileName": "report.pdf",
  "fileSize": 10485760,
  "sha256Whole": "a1b2c3...",
  "totalChunks": 20,
  "chunkSize": 524288,
  "ticket": "base64(payload).base64(hmac)",
  "storageAddress": "host:port"
}
```

**Share token — trừ lượt lúc INIT_DOWNLOAD, không phải lúc download xong.**
- Lúc init: đơn giản, chắc chắn. Nhược: download fail → mất 1 lượt.
- Lúc download xong: chính xác hơn. Nhược: client có thể không báo, hoặc download nhiều lần không bị trừ.
- **Chọn trừ lúc init** vì đơn giản hơn, chấp nhận mất lượt khi fail.

### Task

- T-G1: Implement `INIT_DOWNLOAD` bằng quyền trực tiếp — check token, check quyền, tìm file (mặc định version mới nhất), sinh HMAC download ticket, ghi audit, trả plan.
- T-G2: Implement `INIT_DOWNLOAD` bằng share token — validate + atomic increment (PG), sinh ticket, ghi audit, trả plan.
- T-G3: Implement hàm sinh HMAC download ticket — tương tự upload ticket nhưng chứa storedName để Storage Node biết đọc file nào.

---

## H. Notification

### Cơ chế

Client mở socket tới Coordinator → gửi token xác thực → gửi `SUBSCRIBE_ROOM` → nhận event khi có thay đổi.

Subscriber map lưu **in-memory** (Map trong application), không cần Redis. Lý do: chỉ 1 instance Coordinator. Nếu restart, client reconnect + re-subscribe.

### Event

| Event | Trigger | Payload |
|-------|---------|---------|
| NEW_FILE | Nhận UPLOAD_COMPLETE từ Storage Node | fileId, fileName, uploader, roomId |
| FILE_DELETED | DELETE_FILE | fileId, fileName, deletedBy, roomId |
| MEMBER_ADDED | ADD_MEMBER | userId, username, role, roomId |
| MEMBER_REMOVED | REMOVE_MEMBER | userId, username, roomId |
| ROLE_UPDATED | SET_ROLE | userId, username, newRole, roomId |

### Task

- T-H1: Implement socket server cho client. Xác thực token ở message đầu tiên.
- T-H2: `SUBSCRIBE_ROOM` / `UNSUBSCRIBE_ROOM` — check quyền, thêm/xóa connection khỏi map.
- T-H3: Hàm `broadcast(roomId, event)` — duyệt map, gửi cho tất cả connection đang subscribe room.
- T-H4: Gọi broadcast tại mỗi trigger trong bảng trên.
- T-H5: Cleanup khi socket disconnect — xóa connection khỏi tất cả room đang subscribe.

---

## I. Socket nội bộ: Storage Node ↔ Coordinator

### Mô tả

Storage Node khi khởi động mở 1 socket persistent tới Coordinator. Mọi message giữa 2 bên đi qua socket này.

### Tại sao persistent thay vì per-request?

- Persistent: không tốn handshake mỗi lần, Coordinator biết Storage Node đang sống, đơn giản.
- Per-request: mỗi lần mở connection mới, tốn thời gian, không biết Storage Node sống hay chết.
- **Chọn persistent.**

### Ai connect tới ai?

**Storage Node connect tới Coordinator.** Coordinator là server lắng nghe, Storage Node là client kết nối vào.

### Heartbeat

- Storage Node gửi `PING` mỗi 30 giây.
- Coordinator trả `PONG`.
- Nếu Coordinator không nhận PING trong 90 giây → coi Storage Node dead.
- Nếu socket đứt, Storage Node tự reconnect với backoff (1s, 2s, 4s, max 30s).

### Message qua socket này

| Message | Hướng | Khi nào |
|---------|-------|---------|
| PING / PONG | Storage Node → Coordinator → Storage Node | Mỗi 30 giây |
| UPLOAD_COMPLETE | Storage Node → Coordinator | Upload thành công |
| UPLOAD_FAILED | Storage Node → Coordinator | Upload thất bại |
| ACK | Coordinator → Storage Node | Xác nhận đã xử lý |

### Task

- T-I1: Implement socket server lắng nghe kết nối từ Storage Node. Phân biệt socket từ client (cần auth token) và socket từ Storage Node (cần auth bằng shared secret hoặc key riêng).
- T-I2: Implement handler PING/PONG.
- T-I3: Implement handler UPLOAD_COMPLETE / UPLOAD_FAILED (đã mô tả ở phần F).
- T-I4: Implement logic detect Storage Node dead (không nhận PING quá 90 giây).

---

## J. Share token

### Task

- T-J1: `CREATE_SHARE_TOKEN` — check quyền (ADMIN/OWNER/MEMBER), generate 32 bytes random → hex, INSERT share_tokens (PG), ghi audit, trả token string.
- T-J2: Verify + consume (gọi nội bộ bởi INIT_DOWNLOAD) — atomic SQL: `UPDATE share_tokens SET download_count = download_count + 1 WHERE token = $1 AND download_count < max_downloads AND expires_at > NOW() RETURNING *`.
- T-J3: Ghi audit mỗi lần dùng share token.

---

## K. Audit log

### Danh sách action

| Action | Target type | Khi nào |
|--------|-------------|---------|
| SIGNUP | user | Đăng ký |
| LOGIN | user | Đăng nhập |
| CREATE_ROOM | room | Tạo phòng |
| ADD_MEMBER | room_member | Thêm thành viên |
| REMOVE_MEMBER | room_member | Xóa thành viên |
| SET_ROLE | room_member | Đổi role |
| UPLOAD | file | Nhận UPLOAD_COMPLETE |
| DOWNLOAD | file | INIT_DOWNLOAD thành công |
| DELETE_FILE | file | Xóa file |
| CREATE_SHARE_TOKEN | share_token | Tạo token |
| USE_SHARE_TOKEN | share_token | Dùng token download |

### Task

- T-K1: Hàm `writeAuditLog(actorId, action, targetType, targetId, roomId, detail, status)` — INSERT audit_logs (PG), gọi đồng bộ.
- T-K2: Gọi hàm này tại tất cả trigger trong bảng trên.
- T-K3: (Tùy chọn) `LIST_AUDIT_LOGS` — filter theo room, actor, action, thời gian. Chỉ ADMIN/OWNER.

---

## L. Health check

- T-L1: `PING` → `PONG` + timestamp. Không cần auth.
- T-L2: (Tùy chọn) `STATUS` → PG connected, Redis connected, Storage Node connected, uptime.

---

## M. Tài liệu bàn giao

- T-M1: **Message spec** — tất cả message type, request/response format, mã lỗi. **Ra trước khi code.**
- T-M2: **HMAC ticket spec** — format, fields, secret key config. **Chốt với Người 2 ngày đầu.**
- T-M3: **Socket frame format** — chốt 1 format cho tất cả socket. **Chốt với cả Người 2 và Người 3.**
- T-M4: ERD database.
- T-M5: Seed data SQL.
- T-M6: Bộ test message mẫu.

---

## Danh sách mã lỗi

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
| SCAN_HASH_MISMATCH | Hash report không khớp sha256Whole |
| UPLOAD_SESSION_EXPIRED | Ticket upload hết hạn |
| HASH_MISMATCH | Hash toàn file không khớp |
| SHARE_TOKEN_EXPIRED | Share token hết hạn |
| SHARE_TOKEN_EXHAUSTED | Hết lượt tải |
| INVALID_SHARE_TOKEN | Token không tồn tại |
| CANNOT_REMOVE_LAST_OWNER | Phòng phải có ít nhất 1 OWNER |
| CANNOT_CHANGE_OWN_ROLE | Không tự đổi role |
| STORAGE_NODE_UNAVAILABLE | Storage Node không kết nối |
| FILE_ALREADY_EXISTS | Dedup — file cùng hash đã tồn tại |

---

## Giới hạn và cân nhắc của hệ thống

### 1. Coordinator là single point of failure

Chỉ có 1 Coordinator. Nếu Coordinator down:
- Client không login được, không xin upload/download ticket được.
- Storage Node không gửi UPLOAD_COMPLETE được → file treo ở trạng thái UPLOADING.
- Notification chết.

**Upload đang dở có bị mất không?** Không. Storage Node lưu chunk vào disk. Khi Coordinator lên lại, Storage Node reconnect, gửi lại UPLOAD_COMPLETE. Nhưng cần implement retry ở Storage Node — nếu gửi UPLOAD_COMPLETE mà không nhận ACK, phải gửi lại khi socket nối lại.

**Giảm thiểu:** đảm bảo Coordinator restart nhanh (auto-restart bằng systemd hoặc Docker restart policy). Không cần cluster hay HA cho scope dự án này.

### 2. Redis crash → mất tất cả session login

Mọi user bị đá ra, phải login lại. Upload/download đang dở không bị ảnh hưởng (vì session upload ở Storage Node, ticket download tự verify bằng HMAC).

**Giảm thiểu:** bật Redis AOF persistence (appendonly yes, appendfsync everysec) — mất tối đa 1 giây data. Hoặc chấp nhận, vì login lại chỉ mất vài giây.

### 3. HMAC ticket không revoke được

Sau khi sinh ticket, Coordinator không thể hủy ticket đó. Ticket chỉ hết hạn tự nhiên (30 phút upload, 15 phút download).

**Kịch bản xấu:** user bị xóa khỏi phòng nhưng đã có ticket → vẫn upload/download được trong thời gian ticket còn sống.

**Giảm thiểu:** giữ TTL ticket ngắn (15–30 phút). Trong scope dự án này, chấp nhận được. Nếu cần revoke, phải chuyển sang cách Storage Node gọi Coordinator verify — nhưng sẽ mất lợi ích của Option A.

### 4. Dedup + xóa file phức tạp

Nếu 2 file có cùng sha256_whole, chúng share cùng data vật lý trên Storage Node. Khi xóa 1 file:
- Nếu không check → xóa data vật lý → file còn lại mất data.
- Phải check `SELECT COUNT(*) FROM files WHERE sha256_whole = ? AND status = 'READY'` trước khi báo Storage Node xóa.

**Giảm thiểu:** nếu không đủ thời gian, bỏ dedup hoàn toàn. Mỗi file 1 bản riêng, xóa thoải mái.

### 5. File UPLOADING treo vô hạn

Nếu client gọi INIT_UPLOAD nhưng không bao giờ upload (bỏ giữa chừng, crash, mất mạng):
- File record trong PG mãi mãi ở status UPLOADING.
- Storage Node có thể có thư mục tạm chứa chunk dở.

**Giảm thiểu:** job dọn chạy định kỳ (task T-F6), query file UPLOADING quá 1 giờ → đánh dấu DELETED. Storage Node cũng cần tự dọn session hết hạn (Người 2 đã implement `cleanExpiredSessions`).

### 6. Scan report có thể bị giả

Client tự scan và tự gửi report. Client độc hại có thể gửi report giả (result = CLEAN cho file có virus).

**Giảm thiểu ở mức hiện tại:**
- Check fileSha256 khớp sha256Whole → client không thể dùng report của file khác.
- Check scannedAt không quá cũ → client không thể dùng lại report cũ.
- Nhưng client vẫn có thể giả report hoàn toàn. Muốn an toàn thật sự phải scan trên server, nằm ngoài scope hiện tại.

### 7. Không có rate limiting

Hiện tại không giới hạn số request per user. Một user có thể spam INIT_UPLOAD, LOGIN, hoặc bất kỳ API nào.

**Giảm thiểu:** implement rate limiting bằng Redis counter nếu còn thời gian (key `ratelimit:{userId}:{action}`, TTL 1 phút, reject nếu vượt ngưỡng). Không phải ưu tiên cho MVP.

### 8. Notification không đảm bảo delivery

Notification qua socket là fire-and-forget. Nếu client mất kết nối đúng lúc broadcast → không nhận được event, không có cơ chế retry.

**Giảm thiểu:** client khi reconnect nên gọi LIST_FILES để sync lại trạng thái mới nhất, không dựa hoàn toàn vào notification.

### 9. Chunk size cố định toàn hệ thống

Hiện tại chunk size là config cố định (512KB). Không adaptive theo tốc độ mạng hay kích thước file.

**Ảnh hưởng:**
- File nhỏ (< 512KB): vẫn tạo 1 chunk, overhead nhỏ.
- File rất lớn (> 1GB): 2000+ chunk, overhead message nhiều.

**Giảm thiểu:** chấp nhận cho MVP. Nếu cần, cho phép INIT_UPLOAD trả chunkSize khác nhau tùy fileSize — nhưng phải sửa cả 3 bên.

### 10. Không encrypt data at rest

File lưu trên Storage Node ở dạng plaintext. Ai có quyền truy cập ổ cứng Storage Node thì đọc được hết.

**Giảm thiểu:** nằm ngoài scope MVP. Nếu cần, encrypt file bằng AES trước khi lưu, key lưu ở Coordinator.

### 11. PostgreSQL là bottleneck tiềm ẩn

Mọi request đều query PG (check quyền, lấy file info, ghi audit log). Nếu số user lớn, PG có thể quá tải.

**Giảm thiểu:** đảm bảo index đúng, connection pooling. Cho scope dự án này (vài chục user), PG dư sức.

### 12. Không có backup / disaster recovery

Không có cơ chế backup DB hoặc file. Mất DB = mất toàn bộ metadata. Mất disk Storage Node = mất toàn bộ file.

**Giảm thiểu:** nằm ngoài scope MVP. Nếu cần, pg_dump định kỳ + rsync file storage.
