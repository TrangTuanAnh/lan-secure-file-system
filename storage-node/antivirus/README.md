# Mục Lục Kiểm Tra Antivirus Của Storage Node

Thư mục này là điểm vào để rà soát luồng quét virus của Storage Node.
Nó được tách thành một cụm nhỏ, dễ tháo lắp: khi cần kiểm tra phần còn lại
của `storage-node` mà không muốn lẫn các file runtime của ClamAV, có thể tạm
di chuyển thư mục này ra ngoài rồi khôi phục lại trước khi chạy Docker Compose.

## Cấu Hình Runtime

- `clamd.conf`: cấu hình ClamAV daemon, được Docker Compose mount vào `/etc/clamav/clamd.conf`.
- `../storage-node.properties`: cấu hình antivirus cho Storage Node khi chạy local.
- `../storage-node.docker.properties`: cấu hình antivirus cho Storage Node khi chạy bằng Docker.
- `../../docker-compose.yml`: định nghĩa các sidecar ClamAV và mount `/app/data` ở chế độ chỉ đọc.

## Code Quét Virus Bằng Java

- `../src/main/java/storagenode/antivirus/`: interface scanner, ClamAV client, no-op scanner, model kết quả/trạng thái quét.
- `../src/main/java/storagenode/network/ClientHandler.java`: luồng `FINALIZE_UPLOAD`: ghép file, kiểm tra hash, kiểm tra giới hạn dung lượng quét, quét virus, rồi quarantine/từ chối/commit.
- `../src/main/java/storagenode/network/StorageServer.java`: truyền cấu hình antivirus vào các client handler.
- `../src/main/java/storagenode/config/NodeConfig.java`: đọc cấu hình `antivirus.*` và các biến môi trường ghi đè.
- `../src/main/java/storagenode/StorageNodeMain.java`: khởi tạo `ClamAvClient` hoặc `NoOpAntivirusScanner`.
- `../src/main/java/storagenode/storage/FileStore.java`: xử lý đường dẫn quarantine và ghi metadata cho upload bị nhiễm.
- `../src/main/java/storagenode/session/UploadSession.java`: chặn các trạng thái finalize không hợp lệ.

## Kiểm Thử

- `../src/test/java/storagenode/test/ClamAvClientTest.java`: kiểm thử parser phản hồi từ ClamAV.
- `../src/test/java/storagenode/test/StorageNodeIntegrationTest.java`: kiểm thử các hành vi upload sạch, nhiễm virus, ClamAV không khả dụng, timeout và vượt giới hạn dung lượng quét.

## Ghi Chú Bảo Mật

- Cơ chế quét dựa trên đường dẫn file local: Storage Node gửi `zSCAN <path>` tới `clamd`; Java client không stream nội dung file ra ngoài.
- Trong Docker, mỗi sidecar ClamAV mount volume dữ liệu của Storage Node tương ứng vào `/app/data` ở chế độ chỉ đọc.
- File lớn hơn `antivirus.max.scan.bytes` sẽ bị từ chối trước khi commit.
- `antivirus.fail.closed=true` giữ upload ở trạng thái bị chặn nếu ClamAV không khả dụng, timeout hoặc trả lỗi.
