# Đồ án LTM - Storage Node

Repository này hiện tập trung vào phần **Storage Node / Data Plane** của hệ thống truyền file LAN an toàn:

- Upload/download theo chunk qua TCP socket
- Resume upload
- Verify SHA-256 theo chunk và whole file
- Quét virus tại Storage Node trước khi commit file vào ổ
- Coordinator cân bằng upload theo storage node khỏe có ít upload active nhất
- Dedup theo nội dung
- Mã hóa truyền bằng RSA + AES

## 1) Tổng quan thành phần trong repo

- `storage-node/src/main/java/storagenode`: mã nguồn storage node
- `storage-node/docs/DATA_PLANE_PROTOCOL.md`: đặc tả message/frame data plane
- `storage-node/docs/CHUNK_FORMAT.md`: format chunk, lưu trữ, mã hóa
- `storage-node/src/test/java/storagenode/test/StorageNodeIntegrationTest.java`: test tích hợp JUnit

## 2) Trạng thái tính năng

| Nhóm tính năng | Trạng thái |
|---|---|
| Cấu trúc lưu trữ (`temp/store/meta`, session meta, dedup registry) | Đã làm |
| Giao thức socket data plane (frame + message type + field chuẩn) | Đã làm |
| Upload chunk + verify ticket/hash/index/size + ACK | Đã làm |
| Resume upload (`OPEN_UPLOAD` resume + `QUERY_MISSING`) | Đã làm |
| Finalize upload + verify whole hash + lưu store | Đã làm |
| Download theo chunk, hỗ trợ request out-of-order | Đã làm |
| Bảo mật truyền (RSA/AES key exchange, ticket gate) | Đã làm |
| Toàn vẹn dữ liệu SHA-256 chunk/file | Đã làm |
| Dedup mức dữ liệu theo hash | Đã làm |
| Quét virus local ở Storage Node bằng ClamAV/clamd | Đã làm |
| Load balancing upload qua nhiều Storage Node | Đã làm |
| Monitoring/log | Làm một phần |
| Tài liệu + test tự động | Đã làm |

## 3) Các bug critical đã xử lý

- Chặn `chunkIndex` âm/out-of-range khi upload (`INVALID_CHUNK_INDEX`)
- Chặn `chunkSize` sai chuẩn (`INVALID_CHUNK_SIZE`)
- Finalize không còn làm rớt socket khi lỗi I/O, trả `FINALIZE_IO_ERROR`
- Download không còn gửi `DOWNLOAD_COMPLETE` sớm khi client request chunk sai thứ tự
- Bổ sung bước bootstrap public key cho `KEY_EXCHANGE` (giữ tương thích ngược)

## 4) Chạy hệ thống

Yêu cầu:

- Java 8
- Maven 3.8+
- ClamAV `clamd` nếu bật `antivirus.enabled=true`

Build:

```bash
cd storage-node
mvn clean package
```

Run node:

```bash
cd storage-node
java -jar target/storage-node-1.0.0-shaded.jar storage-node.properties
```

### Quét virus khi upload

Storage Node scan file bằng ClamAV trong bước `FINALIZE_UPLOAD`, sau khi ghép chunk và verify SHA-256, trước khi move sang `data/store`. Client không cần gửi scan report.

Các cấu hình chính trong `storage-node.properties`:

```properties
antivirus.enabled=true
antivirus.host=127.0.0.1
antivirus.port=3310
antivirus.timeout.ms=30000
antivirus.quarantine.dir=data/quarantine
antivirus.fail.closed=true
```

Với Docker Compose, service `clamd-storage-node-1` chạy sidecar và mount cùng volume `/app/data` ở chế độ read-only để scan file staging.

## 5) Chạy test tự động

```bash
cd storage-node
mvn test
```

Test tích hợp hiện cover các luồng bắt buộc:

- Upload small/large
- Resume upload sau disconnect
- Corrupt chunk + retry
- Invalid chunk index/size nhưng connection vẫn sống
- Finalize I/O error trả frame chuẩn
- Download out-of-order không complete sớm
- KEY_EXCHANGE bootstrap + upload mã hóa

## 6) Cập nhật protocol đáng chú ý

- Upload chunk có thêm status:
  - `INVALID_CHUNK_INDEX`
  - `INVALID_CHUNK_SIZE`
- Finalize có thêm status:
  - `FINALIZE_IO_ERROR`
  - `VIRUS_DETECTED`
  - `SCAN_TIMEOUT`
  - `SCAN_UNAVAILABLE`
  - `SCAN_ERROR`
- `DOWNLOAD_COMPLETE` chỉ gửi khi đã phục vụ đủ toàn bộ tập chunk của session
- `KEY_EXCHANGE` có bootstrap:
  - Request public key trước
  - Sau đó gửi AES key đã mã hóa RSA

## 7) Giới hạn hiện tại

- `CoordinatorClient.notifyUploadComplete/notifyUploadFailed` mới là stub log nội bộ, chưa gọi control plane thật
- Monitoring counters nâng cao (throughput chính xác theo request) chưa được wire đầy đủ
- Chưa triển khai TLS (đang dùng AES session key + RSA key exchange)
