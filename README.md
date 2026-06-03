```text
 __     __   __ _    ____  ____  ___  _  _  ____  ____    ____  __  __    ____    ____  _  _  ____  ____  ____  _  _ 
(  )   / _\ (  ( \  / ___)(  __)/ __)/ )( \(  _ \(  __)  (  __)(  )(  )  (  __)  / ___)( \/ )/ ___)(_  _)(  __)( \/ )
/ (_/\/    \/    /  \___ \ ) _)( (__ ) \/ ( )   / ) _)    ) _)  )( / (_/\ ) _)   \___ \ )  / \___ \  )(   ) _) / \/ \
\____/\_/\_/\_)__)  (____/(____)\___)\____/(__\_)(____)  (__)  (__)\____/(____)  (____/(__/  (____/ (__) (____)\_)(_/
```

Hệ thống chia sẻ và lưu trữ file an toàn trong mạng LAN của doanh nghiệp, xây dựng trên
Socket/TCP với kiến trúc tách rời **control plane** và **data plane**. Hệ thống hỗ trợ đăng
nhập và phân quyền theo phòng, truyền file theo chunk có resume, kiểm tra toàn vẹn SHA-256,
mã hóa đường truyền AES-256-GCM (trao khóa lai ECDH P-256 + ML-KEM-768), chống trùng nội dung (dedup) và quét virus trước khi lưu.

Công nghệ: Python, Java 17, PySide6, PostgreSQL, Redis, ClamAV, Socket/TCP, Docker.

## Mục lục

- [Tổng quan](#tổng-quan)
- [Kiến trúc và luồng chạy](#kiến-trúc-và-luồng-chạy)
- [Tính năng chính](#tính-năng-chính)
- [Cấu trúc repo](#cấu-trúc-repo)
- [Yêu cầu môi trường](#yêu-cầu-môi-trường)
- [Cách chạy](#cách-chạy)
- [Kiểm thử](#kiểm-thử)
- [Tài liệu](#tài-liệu)
- [Phân chia công việc](#phân-chia-công-việc)

## Tổng quan

Hệ thống gồm ba thành phần chạy độc lập, ghép với nhau qua một bộ message/protocol thống nhất:

| Thành phần | Vai trò | Công nghệ |
|------------|---------|-----------|
| `coordinator-server` | Control plane: xác thực, phòng và role, metadata file, cấp ticket, notification, audit log | Python, PostgreSQL, Redis |
| `storage-node` | Data plane: nhận/ghép chunk, verify hash, mã hóa, dedup, quét virus, lưu trữ | Java 17 |
| `coordinator-node` | Client desktop: đăng nhập, xem phòng/file, upload/download, theo dõi tiến trình | Python, PySide6 |

## Kiến trúc và luồng chạy

Hai kênh giao tiếp được tách riêng để mỗi bên làm đúng việc của mình:

- Control plane (giữa Client và Coordinator): các lệnh quản trị dạng JSON như login, room,
  quyền, khởi tạo upload/download, subscribe notification.
- Data plane (giữa Client và Storage Node): truyền dữ liệu file thật theo chunk, không đi qua
  Coordinator.

```text
  Client (PySide6)
    |
    |  control plane (JSON, cổng 8080)
    +------------------------------>  Coordinator Server (Python, PostgreSQL, Redis)
    |                                   - auth, phòng, phân quyền, metadata file
    |                                   - cấp HMAC ticket, chọn storage node phù hợp
    |                                   - notification realtime, audit log
    |
    |  data plane (chunk, cổng 9001)
    +------------------------------>  Storage Node (Java)
                                        - nhận/ghép chunk, verify hash, mã hóa, dedup
                                        - quét virus (ClamAV), commit vào content store

  Coordinator <----> Storage Node : đăng ký node, verify ticket, báo upload hoàn tất (8081)
```

**Luồng upload**

1. Client đăng nhập vào `coordinator-server`.
2. Client gọi `INIT_UPLOAD` để xin upload plan (gửi metadata: tên, kích thước, MIME, SHA-256 toàn file).
3. Coordinator kiểm tra quyền, kiểm tra dedup, chọn `storage-node`, cấp HMAC ticket và trả `storageAddress`.
4. Client kết nối trực tiếp đến `storage-node`, gửi từng chunk.
5. Storage Node verify hash từng chunk và toàn file, ghép file, quét virus, commit vào store.
6. Storage Node báo `UPLOAD_COMPLETE` về Coordinator.
7. Coordinator cập nhật metadata, ghi audit log, phát sự kiện realtime `NEW_FILE`.

**Luồng download**

1. Client gọi `INIT_DOWNLOAD` lên Coordinator.
2. Coordinator kiểm tra quyền (hoặc share token), cấp ticket download, trả thông tin file.
3. Client kết nối trực tiếp đến `storage-node`, nhận chunk theo plan.
4. Client ghi file dạng streaming và verify SHA-256 sau khi tải xong.

## Tính năng chính

- Đăng ký và đăng nhập, mật khẩu lưu dạng bcrypt (hash + salt), session token qua Redis.
- Phân quyền toàn cục `ADMIN` và theo phòng `OWNER` / `MEMBER` / `VIEWER`.
- Upload/download qua socket, truyền theo chunk 512KB có resume khi rớt mạng.
- Toàn vẹn dữ liệu: SHA-256 từng chunk và toàn file.
- Mã hóa đường truyền: **AES-256-GCM**; khóa phiên thiết lập qua trao khóa lai **ECDH P-256 + ML-KEM-768** (hậu lượng tử) rồi dẫn xuất bằng HKDF-SHA256, tự hạ về ECDH-only khi client thiếu ML-KEM. (RSA + AES-CBC chỉ còn là nhánh legacy trong Java, client thực tế không dùng.)
- Ticket HMAC-SHA256 do Coordinator cấp, Storage Node tự verify (không cần round-trip mỗi chunk).
- Dedup theo nội dung (content-addressed storage theo SHA-256).
- Quét virus trước khi commit (ClamAV / clamd).
- Thông báo realtime khi có file mới, share token có thời hạn, audit log đầy đủ.

## Cấu trúc repo

```text
.
├── coordinator-server/     # Control plane (Python): auth, room, file, upload, download,
│                           #   notification, ticket, protocol, audit, alembic migrations
├── storage-node/           # Data plane (Java): network, protocol, crypto, session,
│                           #   storage (content-addressed + dedup), antivirus, monitor
├── coordinator-node/       # Desktop client (Python + PySide6)
├── docs/                   # Tài liệu kiến trúc và vận hành cấp hệ thống
├── test-data/              # Dữ liệu mẫu để test upload/download
├── docker-compose.yml      # Dựng nhanh toàn bộ stack
├── run_client.bat / .sh    # Mở desktop client
└── test-integration.sh     # Test tích hợp end-to-end
```

## Yêu cầu môi trường

- Java 17+ và Maven (cho `storage-node`)
- Python 3.11+ (cho `coordinator-server` và `coordinator-node`)
- PostgreSQL 14+ và Redis 6+
- ClamAV / clamd để quét virus (hoặc dùng `NoOpAntivirusScanner` khi demo)
- Docker và Docker Compose (tùy chọn, để dựng nhanh cả stack)

## Cách chạy

### Dựng nhanh bằng Docker Compose

```bash
docker compose up --build
```

Stack mặc định gồm: `postgres` (5432), `redis` (6379), `coordinator` (8080, 8081),
`storage-node-1` (9001) và `clamd`. Mở thêm node thứ hai:

```bash
docker compose --profile multi-node up --build
```

### Chạy riêng từng thành phần

**Coordinator Server** (control plane)

```bash
cd coordinator-server
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                               # chỉnh PostgreSQL/Redis cho phù hợp
python main.py
```

**Storage Node** (data plane)

```bash
cd storage-node
mvn clean package
java -jar target/storage-node-1.0.0.jar storage-node.properties
```

**Desktop Client**

```bash
# Windows
run_client.bat
# Linux/macOS
./run_client.sh
```

## Kiểm thử

- Unit test (Python): `cd coordinator-server && python -m pytest`
- Test tích hợp end-to-end: `./test-integration.sh`
- Kiểm thử thủ công: xem [docs/MANUAL_TEST_GUIDE.md](docs/MANUAL_TEST_GUIDE.md)
- Dữ liệu mẫu để upload/download nằm trong [test-data/](test-data/).

## Tài liệu

**Hệ thống**

- [docs/SYSTEM_TOPOLOGY_AND_DATA_FLOW_VI.md](docs/SYSTEM_TOPOLOGY_AND_DATA_FLOW_VI.md) - topology và data flow tổng thể
- [docs/SYSTEM_IO_FLOWS_VI.md](docs/SYSTEM_IO_FLOWS_VI.md) - luồng I/O chi tiết
- [docs/MULTITHREADING_VI.md](docs/MULTITHREADING_VI.md) - mô hình đa luồng
- [docs/LOAD_BALANCER_VI.md](docs/LOAD_BALANCER_VI.md) - cân bằng tải giữa các storage node
- [docs/DOCKER_SETUP.md](docs/DOCKER_SETUP.md) - hướng dẫn dựng bằng Docker
- [docs/MANUAL_TEST_GUIDE.md](docs/MANUAL_TEST_GUIDE.md) - kịch bản kiểm thử thủ công

**Storage Node (data plane)**

- [storage-node/docs/DATA_PLANE_PROTOCOL.md](storage-node/docs/DATA_PLANE_PROTOCOL.md) - giao thức data plane
- [storage-node/docs/CHUNK_FORMAT.md](storage-node/docs/CHUNK_FORMAT.md) - định dạng chunk và lưu trữ
- [storage-node/docs/STORAGE_NODE_ARCHITECTURE_REPORT.md](storage-node/docs/STORAGE_NODE_ARCHITECTURE_REPORT.md) - kiến trúc storage node

**Coordinator Server (control plane)**

- [coordinator-server/README.md](coordinator-server/README.md) - tổng quan và cấu hình server
- [coordinator-server/SETUP.md](coordinator-server/SETUP.md) - cài đặt chi tiết
- [coordinator-server/protocol/README.md](coordinator-server/protocol/README.md) - đặc tả message/protocol
- [coordinator-server/auth/AUTHORIZATION_README.md](coordinator-server/auth/AUTHORIZATION_README.md) - mô hình phân quyền

**Client (coordinator-node)**

- [coordinator-node/docs/BACKEND_API_REFERENCE.md](coordinator-node/docs/BACKEND_API_REFERENCE.md) - API reference cho client

## Phân chia công việc

Hệ thống được chia thành ba khối dọc khá độc lập, nối với nhau qua contract message/protocol đã thống nhất:

- Coordinator Server: control plane, database, auth và phân quyền, metadata, notification, share token, audit.
- Storage Node: data plane, truyền chunk, resume, hash, mã hóa, dedup, lưu trữ.
- Client: giao diện người dùng, luồng upload/download, mã hóa data plane phía client, hiển thị trạng thái quét virus, realtime.
