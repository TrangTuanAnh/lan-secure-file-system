```text
    __    ___    _   __   _____ ______________  ______  ______   ____________    ______
   / /   /   |  / | / /  / ___// ____/ ____/ / / / __ \/ ____/  / ____/  _/ /   / ____/
  / /   / /| | /  |/ /   \__ \/ __/ / /   / / / / /_/ / __/    / /_   / // /   / __/
 / /___/ ___ |/ /|  /   ___/ / /___/ /___/ /_/ / _, _/ /___   / __/ _/ // /___/ /___
/_____/_/  |_/_/ |_/   /____/_____/\____/\____/_/ |_/_____/  /_/   /___/_____/_____/
```

# LAN Secure File System

Hệ thống chia sẻ và lưu trữ file an toàn trong mạng LAN của doanh nghiệp, xây dựng trên
nền **Socket** với kiến trúc tách **control plane** và **data plane**. Hệ thống hỗ trợ
đăng nhập + phân quyền theo phòng, truyền file theo **chunk có resume**, **kiểm tra toàn
vẹn (SHA-256)**, **mã hóa đường truyền (AES + RSA)**, **chống trùng nội dung (dedup)** và
**quét virus** trước khi lưu.

## Tổng quan

Hệ thống gồm 3 thành phần chạy độc lập, ghép với nhau qua một bộ message/protocol thống nhất:

| Thành phần | Vai trò | Ngôn ngữ |
|------------|---------|----------|
| `coordinator-server` | **Control plane** — xác thực, phòng/role, metadata file, cấp ticket, notification, audit log | Python + PostgreSQL + Redis |
| `storage-node` | **Data plane** — nhận/ghép chunk, verify hash, mã hóa, dedup, lưu trữ, quét virus | Java |
| `coordinator-node` | **Client** desktop — đăng nhập, xem phòng/file, upload/download, theo dõi tiến trình | Python + PySide6 |

## Kiến trúc & luồng chạy

Hai kênh giao tiếp được tách riêng để mỗi bên làm đúng việc của mình:

- **Control Plane** (Client <-> Coordinator): các lệnh quản trị dạng JSON — login, room, quyền, khởi tạo upload/download, subscribe notification.
- **Data Plane** (Client <-> Storage Node): truyền dữ liệu file thật theo chunk.

**Luồng upload**

1. Client đăng nhập vào `coordinator-server`.
2. Client gọi `INIT_UPLOAD` để xin upload plan (kèm scan report).
3. Coordinator kiểm tra quyền, kiểm tra dedup, chọn `storage-node`, cấp **HMAC ticket** và trả `storageAddress`.
4. Client kết nối trực tiếp đến `storage-node`, gửi từng chunk.
5. Storage Node verify hash từng chunk + toàn file, ghép file, quét virus, commit vào store.
6. Storage Node báo `UPLOAD_COMPLETE` về Coordinator.
7. Coordinator cập nhật metadata, ghi audit log, phát sự kiện realtime `NEW_FILE`.

**Luồng download**

1. Client gọi `INIT_DOWNLOAD` lên Coordinator.
2. Coordinator kiểm tra quyền (hoặc share token), cấp ticket download, trả thông tin file.
3. Client kết nối trực tiếp đến `storage-node`, nhận chunk theo plan.
4. Client ghi file streaming và verify SHA-256 sau khi tải xong.

## Cấu trúc repo

```text
.
|-- coordinator-server/     # Control plane (Python): auth, room, file, upload,
|                           #   download, notification, ticket, protocol, alembic
|-- storage-node/           # Data plane (Java): network, protocol, crypto,
|                           #   session, storage, antivirus, monitor
|-- coordinator-node/       # Desktop client (Python + PySide6)
|-- docs/                   # Tài liệu kiến trúc & vận hành cấp hệ thống
|-- test-data/              # Dữ liệu mẫu để test upload/download
|-- docker-compose.yml      # Dựng nhanh toàn bộ stack
|-- run_client.bat / .sh    # Mở desktop client
|-- test-integration.sh     # Test tích hợp end-to-end
`-- REPORT.md               # Báo cáo chi tiết toàn hệ thống
```

## Yêu cầu môi trường

- **Java** 17+ và **Maven** (cho `storage-node`)
- **Python** 3.11+ (cho `coordinator-server` và `coordinator-node`)
- **PostgreSQL** 14+ và **Redis** 6+
- **ClamAV / clamd** (quét virus) — hoặc dùng `NoOpAntivirusScanner` khi demo
- **Docker** + **Docker Compose** (tùy chọn, để dựng nhanh)

## Cách chạy

### Dựng nhanh bằng Docker Compose

```bash
docker compose up --build
```

Stack mặc định gồm: `postgres` (5432), `redis` (6379), `coordinator-server`
(8080-8082), `storage-node-1` (9001) và `clamd`. Mở thêm node thứ hai:

```bash
docker compose --profile multi-node up --build
```

### Chạy riêng từng thành phần

**Coordinator Server**

```bash
cd coordinator-server
pip install -r requirements.txt
# cấu hình PostgreSQL/Redis qua .env (xem .env.example)
python main.py
```

**Storage Node**

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

## Tính năng chính

- Đăng ký / đăng nhập, password lưu dạng **hash + salt**, session token.
- Phân quyền toàn cục `ADMIN` và theo phòng `OWNER | MEMBER | VIEWER`.
- Upload/download qua socket, truyền theo **chunk 512KB** có **resume** khi rớt mạng.
- **Toàn vẹn**: SHA-256 từng chunk và toàn file.
- **Mã hóa đường truyền**: AES-256-CBC cho data, trao khóa bằng RSA (mã hóa lai).
- **Ticket HMAC-SHA256** do Coordinator cấp, Storage Node tự verify.
- **Dedup** theo nội dung (content-addressed storage theo SHA-256).
- **Quét virus** trước khi lưu (ClamAV).
- **Thông báo realtime** khi có file mới, **share token** có thời hạn, **audit log**.

## Tài liệu

**Hệ thống**

- [`REPORT.md`](REPORT.md) — báo cáo chi tiết toàn hệ thống
- [`docs/SYSTEM_TOPOLOGY_AND_DATA_FLOW_VI.md`](docs/SYSTEM_TOPOLOGY_AND_DATA_FLOW_VI.md) — topology & data flow
- [`docs/SYSTEM_IO_FLOWS_VI.md`](docs/SYSTEM_IO_FLOWS_VI.md) — luồng I/O chi tiết
- [`docs/MULTITHREADING_VI.md`](docs/MULTITHREADING_VI.md) — mô hình đa luồng
- [`docs/LOAD_BALANCER_VI.md`](docs/LOAD_BALANCER_VI.md) — cân bằng tải storage node
- [`docs/DOCKER_SETUP.md`](docs/DOCKER_SETUP.md) — hướng dẫn dựng Docker
- [`docs/MANUAL_TEST_GUIDE.md`](docs/MANUAL_TEST_GUIDE.md) — kiểm thử thủ công

**Storage Node (data plane)**

- [`storage-node/docs/DATA_PLANE_PROTOCOL.md`](storage-node/docs/DATA_PLANE_PROTOCOL.md) — giao thức data plane
- [`storage-node/docs/CHUNK_FORMAT.md`](storage-node/docs/CHUNK_FORMAT.md) — định dạng chunk & lưu trữ
- [`storage-node/docs/STORAGE_NODE_ARCHITECTURE_REPORT.md`](storage-node/docs/STORAGE_NODE_ARCHITECTURE_REPORT.md) — kiến trúc storage node

**Coordinator Server & Client**

- [`coordinator-server/README.md`](coordinator-server/README.md) - [`coordinator-server/SETUP.md`](coordinator-server/SETUP.md)
- [`coordinator-node/docs/BACKEND_API_REFERENCE.md`](coordinator-node/docs/BACKEND_API_REFERENCE.md) — API reference
- [`coordinator-node/docs/FRONTEND_INTEGRATION_GUIDE.md`](coordinator-node/docs/FRONTEND_INTEGRATION_GUIDE.md) — tích hợp client

## Phân chia công việc

Hệ thống được chia thành ba khối dọc khá độc lập, nối với nhau qua contract message/protocol đã thống nhất:

- **Coordinator Server** — control plane, database, auth & phân quyền, metadata, notification, share token, audit.
- **Storage Node** — data plane, truyền chunk, resume, hash, mã hóa, dedup, lưu trữ.
- **Client** — giao diện người dùng, luồng upload/download, virus scan local, realtime.

## Công nghệ

Python · PySide6 · Java · PostgreSQL · Redis · ClamAV · TCP socket protocol tự định nghĩa · Docker
