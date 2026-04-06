# Chunk & Storage Format

## Quy ước Chunk

| Parameter     | Value                       |
|---------------|-----------------------------|
| Chunk size    | 524288 bytes (512 KB)       |
| Chunk index   | 0-based (0, 1, 2, ...)     |
| Hash per chunk| SHA-256, lowercase hex      |
| Hash toàn file| SHA-256, lowercase hex      |
| Last chunk    | Có thể nhỏ hơn chunk size  |

### Cách tính số chunk

```
totalChunks = ceil(fileSize / chunkSize)
```

Ví dụ: File 3 MB = 3145728 bytes
- chunkSize = 524288
- totalChunks = ceil(3145728 / 524288) = 6
- Chunk 0-4: 524288 bytes mỗi chunk
- Chunk 5 (cuối): 3145728 - 5*524288 = 524288 bytes

### Cách tính hash chunk

```java
// Hash tính trên raw bytes (chưa mã hóa)
MessageDigest md = MessageDigest.getInstance("SHA-256");
byte[] hash = md.digest(chunkData);
String hexHash = bytesToHex(hash); // lowercase, 64 chars
```

### Cách tính hash toàn file

```java
// Đọc toàn bộ file sau khi ghép chunk
MessageDigest md = MessageDigest.getInstance("SHA-256");
for (int i = 0; i < totalChunks; i++) {
    byte[] chunk = readChunk(i);
    md.update(chunk);
}
String sha256Whole = bytesToHex(md.digest());
```

## Cấu trúc thư mục lưu trữ

```
data/
├── temp/                           # Upload đang dở
│   └── {sessionId}/
│       ├── meta.properties         # Session metadata (crash recovery)
│       ├── chunk_0                 # Chunk file thô
│       ├── chunk_1
│       └── ...
│
├── store/                          # File hoàn tất (content-addressed)
│   ├── ab/
│   │   └── abc123def456...         # File lưu theo SHA-256 hash
│   ├── ff/
│   │   └── ff0a1b2c3d...
│   └── ...
│
└── meta/
    └── dedup_registry.json         # Hash → path mapping
```

### Content-Addressed Storage

File hoàn tất được lưu theo SHA-256 hash:
- **Prefix 2 ký tự đầu** của hash làm subdirectory (tránh quá nhiều file trong 1 thư mục)
- **Tên file** = toàn bộ SHA-256 hash

Ví dụ: SHA-256 = `ab3f7c2d...` → Lưu tại `data/store/ab/ab3f7c2d...`

### Session Metadata (meta.properties)

```properties
sessionId=550e8400-e29b-41d4-a716-446655440000
fileId=file-123
fileName=report.pdf
sha256Whole=abc123def456...
fileSize=3145728
totalChunks=6
chunkSize=524288
uploaderId=user-1
status=UPLOADING
createdAt=2026-04-06T10:30:00Z
```

## Dedup Registry (dedup_registry.json)

```json
{
  "abc123def456...": "data/store/ab/abc123def456...",
  "ff0a1b2c3d...": "data/store/ff/ff0a1b2c3d..."
}
```

## Mã hóa đường truyền

### RSA + AES Key Exchange

```
Client                              Node
  │                                  │
  │  1. Node có sẵn RSA key pair      │
  │                                  │
  │── KEY_EXCHANGE (requestPublicKey)│
  │──────────────────────────────────>│
  │<────────── KEY_EXCHANGE_RESP ─────│
  │     (data: Node RSA public key)   │
  │                                  │
  │  2. Client tạo AES-256 key        │
  │  3. Encrypt AES key bằng          │
  │     RSA public key của Node       │
  │                                  │
  │── KEY_EXCHANGE ─────────────────>│
  │   (data: RSA-encrypted AES key) │
  │                                  │
  │<──────────── KEY_EXCHANGE_RESP ──│
  │      (status=OK, encrypted=true) │
  │                                  │
  │  Từ đây mọi chunk data được     │
  │  encrypt bằng AES-256-CBC       │
  │                                  │
```

### AES-256-CBC Format

Mỗi chunk data được encrypt:
```
[16 bytes IV][encrypted chunk data]
```

- IV (Initialization Vector): random 16 bytes, sinh mới cho mỗi chunk
- Padding: PKCS5

**Lưu ý:** Hash chunk tính trên **raw bytes** (trước khi encrypt).
Node decrypt trước, rồi mới verify hash.

## Validation khi nhận chunk upload

- `chunkIndex` phải trong `[0, totalChunks - 1]`
- Non-last chunk phải đúng `chunkSize`
- Last chunk phải đúng kích thước còn lại của file (`fileSize - (totalChunks - 1) * chunkSize`)
- Sai index trả `ACK_CHUNK.status = INVALID_CHUNK_INDEX`
- Sai size trả `ACK_CHUNK.status = INVALID_CHUNK_SIZE`

## Upload Session Status

```
INIT ──> UPLOADING ──> FINALIZING ──> COMPLETED
  │          │              │
  │          ▼              ▼
  │        PAUSED        FAILED
  │          │
  └──────────┘ (resume)
```

| Status     | Ý nghĩa                                      |
|------------|-----------------------------------------------|
| INIT       | Session vừa tạo, chưa nhận chunk nào          |
| UPLOADING  | Đang nhận chunk                               |
| PAUSED     | Client mất kết nối, session chờ resume        |
| FINALIZING | Đang ghép file và verify hash                 |
| COMPLETED  | File đã lưu thành công                        |
| FAILED     | Hash toàn file sai hoặc lỗi nghiêm trọng     |

## Ticket Verification

Ticket do Coordinator cấp, xác thực bằng HMAC-SHA256:

```
payload = sessionId + "|" + fileId + "|" + nodeId + "|" + expiry
signature = HMAC-SHA256(shared_secret, payload)
```

Node verify:
1. Kiểm tra `nodeId` đúng node này
2. Kiểm tra `expiry` chưa hết hạn
3. Tính lại HMAC, so sánh với `signature`
