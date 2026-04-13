# Data Plane Protocol — Storage Node

## Tổng quan

Giao thức data plane dùng TCP socket thuần, sử dụng binary framing để tránh dính gói.
Mỗi message gồm **JSON header** (metadata) + **binary data** (tùy chọn, chứa chunk bytes).

## Frame Format

```
┌──────────────────┬─────────────────┬──────────────────┬──────────────┐
│ headerLen (4 B)  │ headerJson (N)  │ dataLen (4 B)    │ data (M)     │
└──────────────────┴─────────────────┴──────────────────┴──────────────┘
```

| Field       | Size           | Description                               |
|-------------|----------------|-------------------------------------------|
| headerLen   | 4 bytes (int)  | Độ dài header JSON (big-endian)           |
| headerJson  | N bytes        | JSON UTF-8 chứa "type" + các field metadata |
| dataLen     | 4 bytes (int)  | Độ dài binary data (0 nếu không có)       |
| data        | M bytes        | Binary payload (chunk data, encrypted key) |

- Max header: 16 KB
- Max data: 2 MB

## Quy ước chung

| Item              | Convention                        |
|-------------------|-----------------------------------|
| Chunk size        | 524288 bytes (512 KB)             |
| Chunk index       | Bắt đầu từ 0                     |
| Hash algorithm    | SHA-256                           |
| Hash format       | Lowercase hex (64 chars)          |
| Session ID        | UUID v4 string                    |
| Encoding          | UTF-8                             |
| Byte order        | Big-endian                        |

## Message Types

### 1. KEY_EXCHANGE (Client → Node)

Thiết lập encrypted session bằng RSA + AES.

**Bước 1 (bootstrap public key):**

```json
{ "type": "KEY_EXCHANGE", "requestPublicKey": true, "action": "GET_PUBLIC_KEY" }
```

**Data:** rỗng

**Response: KEY_EXCHANGE_RESP**

```json
{
  "type": "KEY_EXCHANGE_RESP",
  "status": "PUBLIC_KEY",
  "encrypted": false,
  "bootstrap": true
}
```

**Data:** Node's RSA public key (X.509 encoded)

**Bước 2 (gửi AES key đã mã hóa):**

```json
{ "type": "KEY_EXCHANGE" }
```

**Data:** RSA-encrypted AES-256 session key

**Response: KEY_EXCHANGE_RESP**

```json
{
  "type": "KEY_EXCHANGE_RESP",
  "status": "OK",
  "encrypted": true,
  "bootstrap": false
}
```

> Tương thích ngược: nếu gửi `KEY_EXCHANGE` không có data, node vẫn trả public key để bootstrap.

---

### 2. OPEN_UPLOAD (Client → Node)

Mở phiên upload mới hoặc resume phiên cũ.

**Header:**

```json
{
  "type": "OPEN_UPLOAD",
  "sessionId": "uuid-string",
  "fileId": "uuid-string",
  "fileName": "document.pdf",
  "sha256Whole": "abc123...64chars",
  "fileSize": 3145728,
  "totalChunks": 6,
  "uploaderId": "user-id",
  "ticketNodeId": "node-1",
  "ticketExpiry": 1700000000,
  "ticketSignature": "hmac-hex-string"
}
```

**Response: OPEN_UPLOAD_RESP**

```json
{
  "type": "OPEN_UPLOAD_RESP",
  "status": "OK",
  "sessionId": "uuid-string",
  "resumed": false,
  "totalChunks": 6,
  "chunkSize": 524288
}
```

Nếu resume:

```json
{
  "type": "OPEN_UPLOAD_RESP",
  "status": "OK",
  "sessionId": "uuid-string",
  "resumed": true,
  "receivedChunks": 3,
  "totalChunks": 6,
  "missingChunks": [3, 4, 5],
  "chunkSize": 524288
}
```

Nếu dedup (file đã tồn tại cùng hash):

```json
{
  "type": "OPEN_UPLOAD_RESP",
  "status": "OK",
  "sessionId": "uuid-string",
  "dedup": true,
  "message": "File already exists (dedup match)"
}
```

---

### 3. UPLOAD_CHUNK (Client → Node)

Gửi 1 chunk lên node.

**Header:**

```json
{
  "type": "UPLOAD_CHUNK",
  "sessionId": "uuid-string",
  "chunkIndex": 0,
  "chunkHash": "sha256-hex-64chars"
}
```

**Data:** Raw chunk bytes (hoặc AES-encrypted nếu đã KEY_EXCHANGE)

**Response: ACK_CHUNK**

Thành công:

```json
{
  "type": "ACK_CHUNK",
  "status": "OK",
  "sessionId": "uuid-string",
  "chunkIndex": 0,
  "received": 1,
  "total": 6,
  "progress": 16
}
```

Hash sai:

```json
{
  "type": "ACK_CHUNK",
  "sessionId": "uuid-string",
  "chunkIndex": 0,
  "status": "HASH_MISMATCH",
  "expectedHash": "...",
  "actualHash": "..."
}
```

Chunk trùng (idempotent):

```json
{
  "type": "ACK_CHUNK",
  "status": "OK",
  "sessionId": "uuid-string",
  "chunkIndex": 0,
  "duplicate": true
}
```

Chunk index không hợp lệ:

```json
{
  "type": "ACK_CHUNK",
  "sessionId": "uuid-string",
  "chunkIndex": -1,
  "status": "INVALID_CHUNK_INDEX",
  "totalChunks": 6,
  "message": "chunkIndex out of range"
}
```

Chunk size không hợp lệ:

```json
{
  "type": "ACK_CHUNK",
  "sessionId": "uuid-string",
  "chunkIndex": 0,
  "status": "INVALID_CHUNK_SIZE",
  "expectedSize": 524288,
  "actualSize": 524100,
  "message": "Chunk size does not match expected size"
}
```

---

### 4. QUERY_MISSING (Client → Node)

Hỏi danh sách chunk còn thiếu (dùng cho resume).

**Header:**

```json
{
  "type": "QUERY_MISSING",
  "sessionId": "uuid-string"
}
```

**Response: MISSING_RESP**

```json
{
  "type": "MISSING_RESP",
  "sessionId": "uuid-string",
  "missingChunks": [2, 4, 5],
  "missingCount": 3,
  "received": 3,
  "total": 6
}
```

---

### 5. FINALIZE_UPLOAD (Client → Node)

Yêu cầu node ghép file và verify hash tổng.

**Header:**

```json
{
  "type": "FINALIZE_UPLOAD",
  "sessionId": "uuid-string"
}
```

**Response: FINALIZE_RESP**

Thành công:

```json
{
  "type": "FINALIZE_RESP",
  "status": "COMPLETED",
  "sessionId": "uuid-string",
  "sha256Whole": "...",
  "storedPath": "data/store/ab/abc123...",
  "message": "File stored successfully"
}
```

Chưa đủ chunk:

```json
{
  "type": "FINALIZE_RESP",
  "status": "INCOMPLETE",
  "sessionId": "uuid-string",
  "missingChunks": [4, 5],
  "message": "Missing 2 chunks"
}
```

Hash file tổng sai:

```json
{
  "type": "FINALIZE_RESP",
  "status": "HASH_MISMATCH",
  "sessionId": "uuid-string",
  "message": "Whole-file hash verification failed"
}
```

Lỗi I/O khi finalize:

```json
{
  "type": "FINALIZE_RESP",
  "status": "FINALIZE_IO_ERROR",
  "sessionId": "uuid-string",
  "message": "I/O error while finalizing upload"
}
```

---

### 6. OPEN_DOWNLOAD (Client → Node)

Mở phiên download.

**Header:**

```json
{
  "type": "OPEN_DOWNLOAD",
  "sessionId": "uuid-string",
  "fileId": "uuid-string",
  "sha256Whole": "abc123...",
  "downloaderId": "user-id",
  "ticketNodeId": "node-1",
  "ticketExpiry": 1700000000,
  "ticketSignature": "hmac-hex"
}
```

**Response: OPEN_DOWNLOAD_RESP**

```json
{
  "type": "OPEN_DOWNLOAD_RESP",
  "status": "OK",
  "sessionId": "uuid-string",
  "fileSize": 3145728,
  "totalChunks": 6,
  "chunkSize": 524288,
  "sha256Whole": "abc123..."
}
```

---

### 7. REQUEST_CHUNK (Client → Node)

Yêu cầu 1 chunk cụ thể.

**Header:**

```json
{
  "type": "REQUEST_CHUNK",
  "sessionId": "uuid-string",
  "chunkIndex": 0
}
```

**Response: DOWNLOAD_CHUNK**

```json
{
  "type": "DOWNLOAD_CHUNK",
  "sessionId": "uuid-string",
  "chunkIndex": 0,
  "chunkHash": "sha256-hex",
  "chunkSize": 524288,
  "totalChunks": 6
}
```

**Data:** Raw chunk bytes (hoặc AES-encrypted)

---

### 8. DOWNLOAD_COMPLETE (Node → Client)

Tự động gửi sau khi node đã gửi **đủ toàn bộ tập chunk** của session (không phụ thuộc thứ tự request).

```json
{
  "type": "DOWNLOAD_COMPLETE",
  "status": "OK",
  "sessionId": "uuid-string",
  "sha256Whole": "abc123..."
}
```

---

### 9. CHECK_OBJECT (Internal)

Kiểm tra file tồn tại theo hash (dùng cho dedup).

```json
{ "type": "CHECK_OBJECT", "sha256Whole": "abc123..." }
```

**Response:**

```json
{ "type": "CHECK_OBJECT_RESP", "sha256Whole": "abc123...", "exists": true }
```

---

### 10. ERROR

```json
{
  "type": "ERROR",
  "code": "INVALID_TICKET",
  "message": "Upload ticket verification failed"
}
```

**Error codes:**

| Code             | Description                         |
|------------------|-------------------------------------|
| INVALID_TICKET   | Ticket hết hạn / sai chữ ký        |
| INVALID_SESSION  | Session không tồn tại               |
| INVALID_SESSION_KEY | Không giải mã được AES key      |
| FILE_NOT_FOUND   | File không có trên storage          |
| HASH_MISMATCH    | Hash chunk/file không khớp          |
| INVALID_CHUNK_INDEX | chunkIndex không hợp lệ         |
| INVALID_CHUNK_SIZE | Kích thước chunk không hợp lệ     |
| FINALIZE_IO_ERROR | Lỗi I/O khi ghép/đọc file finalize |
| READ_CHUNK_ERROR | Lỗi đọc chunk khi download          |
| DECRYPT_FAILED   | Không giải mã được payload chunk    |
| MISSING_DATA     | Thiếu data trong message            |
| UNKNOWN_TYPE     | Message type không hợp lệ           |

## Ticket Format

Upload/download ticket do Coordinator cấp, verify bằng HMAC-SHA256:

```
signature = HMAC-SHA256(
    key = shared_secret,
    data = sessionId + "|" + fileId + "|" + nodeId + "|" + expiry
)
```

## Luồng Upload hoàn chỉnh

```
Client                          Storage Node
  │                                  │
  │── OPEN_UPLOAD ──────────────────>│  (verify ticket)
  │<──────────── OPEN_UPLOAD_RESP ───│
  │                                  │
  │── UPLOAD_CHUNK (idx=0) ─────────>│  (verify hash, write disk)
  │<──────────────────── ACK_CHUNK ──│
  │                                  │
  │── UPLOAD_CHUNK (idx=1) ─────────>│
  │<──────────────────── ACK_CHUNK ──│
  │                                  │
  │   ... (network disconnect) ...   │
  │                                  │
  │── OPEN_UPLOAD (same sessionId) ─>│  (detect resume)
  │<──────────── OPEN_UPLOAD_RESP ───│  (resumed=true, missingChunks)
  │                                  │
  │── QUERY_MISSING ────────────────>│
  │<──────────────── MISSING_RESP ───│
  │                                  │
  │── UPLOAD_CHUNK (missing only) ──>│
  │<──────────────────── ACK_CHUNK ──│
  │                                  │
  │── FINALIZE_UPLOAD ──────────────>│  (assemble, verify sha256)
  │<──────────────── FINALIZE_RESP ──│  (COMPLETED)
```

## Luồng Download hoàn chỉnh

```
Client                          Storage Node
  │                                  │
  │── OPEN_DOWNLOAD ────────────────>│  (verify ticket, check file)
  │<─────────── OPEN_DOWNLOAD_RESP ──│  (fileSize, totalChunks)
  │                                  │
  │── REQUEST_CHUNK (idx=0) ────────>│
  │<──────────── DOWNLOAD_CHUNK ─────│  (data + hash)
  │                                  │
  │── REQUEST_CHUNK (idx=1) ────────>│
  │<──────────── DOWNLOAD_CHUNK ─────│
  │                                  │
  │   ... request all chunks ...     │
  │                                  │
  │── REQUEST_CHUNK (idx=N-1) ──────>│
  │<──────────── DOWNLOAD_CHUNK ─────│
  │<─────────── DOWNLOAD_COMPLETE ───│
```
