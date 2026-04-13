# Báo Cáo Kiến Trúc Storage Node

## 1. Mục tiêu và phạm vi

Tài liệu này mô tả kiến trúc triển khai hiện tại của thành phần **Storage Node** trong hệ thống truyền file LAN an toàn, dựa trên code thực tế tại `storage-node/src/main/java/storagenode`.

Phạm vi bao gồm:

- Data plane TCP cho upload/download theo chunk.
- Quản lý phiên upload/download và resume sau ngắt kết nối.
- Lưu trữ dạng content-addressed + dedup theo hash.
- Bảo mật kênh truyền bằng ticket HMAC + RSA/AES.
- Quan sát vận hành cơ bản và cơ chế recovery.

Không thuộc phạm vi:

- Control plane đầy đủ giữa Node và Coordinator (hiện mới ở mức stub log).
- Cơ chế replication đa node.
- TLS end-to-end ở tầng transport.

## 2. Tổng quan kiến trúc

Storage Node là một tiến trình Java độc lập, khởi chạy từ `StorageNodeMain`, mở TCP server và xử lý mỗi kết nối client bằng `ClientHandler` trong thread pool.

### 2.1 Sơ đồ thành phần mức cao

```text
Client
  │
  │ TCP (FrameCodec: header JSON + binary payload)
  ▼
StorageServer
  └── ClientHandler (per connection)
        ├── CoordinatorClient  (verify ticket HMAC, notify stub)
        ├── SessionManager     (upload/download sessions, expiry, recovery)
        ├── FileStore          (chunk temp, assemble, permanent store)
        ├── DedupStore         (sha256 -> path registry)
        ├── RSAKeyExchange     (public key + decrypt AES key)
        └── AESCrypto/HashUtil (encrypt/decrypt, integrity verify)
```

### 2.2 Vai trò các lớp chính

- `StorageNodeMain`:
  - Nạp cấu hình từ `storage-node.properties`.
  - Khởi tạo storage, session manager, crypto, monitor.
  - Phục hồi session dang dở và chạy `StorageServer`.
- `StorageServer`:
  - Lắng nghe TCP và phân phối socket cho thread pool.
- `ClientHandler`:
  - Thực thi state machine protocol (`OPEN_UPLOAD`, `UPLOAD_CHUNK`, `FINALIZE_UPLOAD`, `OPEN_DOWNLOAD`, ...).
  - Là điểm phối hợp chính giữa session, storage, security.
- `SessionManager`:
  - Quản lý session trong bộ nhớ (`ConcurrentHashMap`).
  - Dọn session hết hạn, phục hồi upload từ metadata + chunk trên disk.
- `FileStore`:
  - Quản lý I/O vật lý: chunk tạm, ghép file, xác minh hash tổng, lưu vĩnh viễn.
- `DedupStore`:
  - Registry JSON lưu map `sha256 -> path` phục vụ dedup.
- `CoordinatorClient`:
  - Xác thực ticket cục bộ bằng HMAC-SHA256.
  - Thông báo `upload complete/failed` hiện tại mới log, chưa gửi control plane thật.

## 3. Kiến trúc dữ liệu và lưu trữ

### 3.1 Cấu trúc thư mục

```text
data/
├── temp/
│   └── {sessionId}/
│       ├── meta.properties
│       ├── chunk_0
│       ├── chunk_1
│       └── ...
├── store/
│   └── {sha256_prefix_2chars}/
│       └── {sha256_full}
└── meta/
    └── dedup_registry.json
```

### 3.2 Nguyên tắc lưu trữ

- Chunk size mặc định: `524288` bytes (512 KB), có thể cấu hình.
- Hash chunk và hash toàn file dùng SHA-256 dạng hex thường.
- File hoàn tất lưu theo content-addressed path:
  - Prefix 2 ký tự đầu hash làm thư mục con.
  - Tên file là toàn bộ hash.
- Dedup:
  - Trước khi nhận upload, nếu `sha256Whole` đã có trong `DedupStore`, node trả `dedup=true` và bỏ qua truyền chunk.

## 4. Protocol và luồng xử lý chính

### 4.1 Framing data plane

Mỗi message truyền theo binary frame:

- `headerLen (4 bytes)`
- `headerJson (UTF-8)`
- `dataLen (4 bytes)`
- `data (binary tùy chọn)`

Giới hạn hiện tại trong `FrameCodec`:

- Header tối đa 16 KB.
- Data tối đa 2 MB.

### 4.2 Luồng upload

1. Client gửi `OPEN_UPLOAD` kèm ticket.
2. Node verify ticket qua `CoordinatorClient.verifyTicket`.
3. Node kiểm tra dedup:
   - Nếu trùng hash -> trả `OPEN_UPLOAD_RESP` với `dedup=true`.
4. Nếu có session cũ cùng `sessionId` -> trả `resumed=true` + missing chunks.
5. Nếu mới -> tạo `UploadSession`, tạo thư mục temp, lưu `meta.properties`.
6. Mỗi `UPLOAD_CHUNK`:
   - Giải mã AES (nếu đã key exchange).
   - Verify `chunkIndex`, `expectedChunkSize`, `chunkHash`.
   - Ghi `chunk_i` vào disk.
   - Đánh dấu received và trả `ACK_CHUNK`.
7. `FINALIZE_UPLOAD`:
   - Kiểm tra đủ chunk.
   - Ghép file theo thứ tự chunk.
   - Verify SHA-256 toàn file.
   - Move vào `data/store/{prefix}/{sha}`.
   - Đăng ký dedup, xóa session temp, trả `FINALIZE_RESP`.

### 4.3 Luồng download

1. Client gửi `OPEN_DOWNLOAD` kèm ticket.
2. Node verify ticket + kiểm tra object tồn tại.
3. Tạo `DownloadSession`, trả thông tin file/chunk.
4. Mỗi `REQUEST_CHUNK`:
   - Đọc đoạn byte theo offset từ file stored.
   - Tính hash chunk.
   - Mã hóa AES nếu có session key.
   - Trả `DOWNLOAD_CHUNK`.
5. Khi tập chunk đã gửi đủ toàn bộ, node gửi `DOWNLOAD_COMPLETE` và xóa session download.

### 4.4 Resume và recovery

- Resume trong runtime:
  - Cùng `sessionId` sẽ nối lại session upload cũ.
- Recovery sau restart:
  - `SessionManager.recoverSessions()` quét `data/temp/*`.
  - Nạp metadata session.
  - Quét các `chunk_*` trên disk, tính hash, dựng lại trạng thái.
  - Đặt status `PAUSED` để client tiếp tục resume.

## 5. Bảo mật và toàn vẹn dữ liệu

### 5.1 Ticket gate

- Ticket upload/download được verify bằng HMAC-SHA256 với shared secret.
- Payload ký: `sessionId|fileId|nodeId|expiry`.
- Node kiểm tra:
  - `nodeId` khớp node hiện tại.
  - Chưa hết hạn.
  - Chữ ký đúng.

### 5.2 Mã hóa dữ liệu truyền

- Bootstrap:
  - Client yêu cầu public key RSA (`KEY_EXCHANGE`).
  - Client sinh AES key, mã hóa bằng RSA public key và gửi lại.
- Sau handshake:
  - Payload chunk truyền bằng AES-256-CBC (`[IV 16 bytes][ciphertext]`).
- Hash chunk tính trên dữ liệu raw trước mã hóa để đảm bảo integrity dữ liệu nội dung.

### 5.3 Integrity

- Mỗi chunk verify SHA-256 trước khi ghi.
- Finalize verify SHA-256 toàn file sau khi assemble.
- Sai hash -> trả lỗi phù hợp (`HASH_MISMATCH`) và không commit object.

## 6. Đặc tính phi chức năng

### 6.1 Concurrency

- Mô hình `thread-per-connection` thông qua fixed thread pool (`server.thread.pool.size`, mặc định 50).
- Session maps dùng `ConcurrentHashMap`.
- Một số thao tác state trong session dùng `synchronized` để tránh race khi cùng session bị thao tác song song.

### 6.2 Khả năng chịu lỗi

- Mất kết nối giữa chừng không mất dữ liệu chunk đã ghi.
- Có recovery upload session khi node restart.
- Finalize có xử lý lỗi I/O riêng và trả `FINALIZE_IO_ERROR` thay vì làm rớt kết nối.

### 6.3 Quan sát vận hành

- `StorageMonitor` log định kỳ:
  - Số session active.
  - Tiến độ từng session.
  - Số dedup entries.
  - Dung lượng data dir.
- Có cleanup session hết hạn định kỳ.

## 7. Đánh giá kiến trúc hiện tại

### 7.1 Điểm mạnh

- Luồng upload/download rõ ràng, tách lớp tốt giữa network/session/storage.
- Dữ liệu được kiểm chứng integrity ở cả mức chunk và whole-file.
- Có resume + recovery thực dụng, phù hợp mạng LAN không ổn định.
- Dedup content-addressed giúp tiết kiệm dung lượng.
- Có integration test cho nhiều tình huống lỗi quan trọng.

### 7.2 Giới hạn và rủi ro kỹ thuật

1. `CoordinatorClient.notifyUploadComplete/notifyUploadFailed` chưa tích hợp control plane thật.
2. RSA key pair được generate mỗi lần node khởi động, không persist lâu dài.
3. AES-CBC không có cơ chế authenticated encryption (chưa có tag như GCM).
4. `StorageServer` hiện bind theo port, chưa dùng `node.host` để bind interface cụ thể.
5. `FrameCodec` giới hạn payload 2 MB; nếu tăng `chunk.size` quá mức có thể vi phạm protocol.
6. `DedupStore` lưu JSON toàn bộ map mỗi lần cập nhật, có thể thành điểm nghẽn khi scale lớn.
7. Counters trong `StorageMonitor` chưa được nối đầy đủ từ `ClientHandler` nên số liệu chưa phản ánh hết traffic thực.
8. Chưa có tầng replication/erasure coding, nên 1 node lỗi có thể mất availability dữ liệu nếu không có backup ngoài.

## 8. Khuyến nghị kiến trúc (ưu tiên)

### Ưu tiên cao

1. Tích hợp callback control plane thật cho commit/fail upload.
2. Persist RSA key pair (hoặc chuyển sang mTLS/TLS) để ổn định trust model.
3. Chuyển AES-CBC sang AES-GCM để có mã hóa + xác thực payload.

### Ưu tiên trung bình

1. Hoàn thiện metrics pipeline (Prometheus/JMX) thay cho log-only monitor.
2. Tách dedup registry sang KV store bền vững hơn (RocksDB/SQLite) nếu số object lớn.
3. Bổ sung giới hạn tài nguyên theo session (rate limit, max concurrent sessions).

### Ưu tiên dài hạn

1. Thiết kế replication đa node + cơ chế heal.
2. Xây dựng checksum/audit job nền để phát hiện bit-rot.
3. Chuẩn hóa versioning protocol để rollout backward compatibility an toàn.

## 9. Trạng thái kiểm thử

Bộ test tích hợp hiện có cover:

- Upload small/large file.
- Resume upload sau disconnect.
- Corrupt chunk + retry.
- Invalid chunk index/size nhưng kết nối vẫn sống.
- Finalize I/O error trả đúng response.
- Download out-of-order không complete sớm.
- Bootstrap KEY_EXCHANGE và upload mã hóa.

=> Mức sẵn sàng hiện tại phù hợp cho môi trường dev/integration; trước production cần bổ sung test tải cao, soak test dài giờ và kiểm thử fault-injection theo node/process/disk/network.

## 10. Kết luận

Kiến trúc Storage Node hiện tại đã đạt một nền tảng data-plane tương đối vững: có sessioning, resume, integrity kiểm chứng đầy đủ, dedup và bảo mật mức ứng dụng. Điểm cần ưu tiên tiếp theo là hoàn thiện tích hợp control plane thật, nâng mô hình bảo mật lên authenticated encryption/TLS, và tăng khả năng quan sát để sẵn sàng vận hành ở quy mô lớn hơn.
