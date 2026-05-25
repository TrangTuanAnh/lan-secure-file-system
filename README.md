```text
 _     ____  _        ____  _____ ____ _     ____  _____   _____ _  _     _____   ____ ___  _ ____ _____ _____ _     
/ \   /  _ \/ \  /|  / ___\/  __//   _Y \ /\/  __\/  __/  /    // \/ \   /  __/  / ___\\  \/// ___Y__ __Y  __// \__/|
| |   | / \|| |\ ||  |    \|  \  |  / | | |||  \/||  \    |  __\| || |   |  \    |    \ \  / |    \ / \ |  \  | |\/||
| |_/\| |-||| | \||  \___ ||  /_ |  \_| \_/||    /|  /_   | |   | || |_/\|  /_   \___ | / /  \___ | | | |  /_ | |  ||
\____/\_/ \|\_/  \|  \____/\____\\____|____/\_/\_\\____\  \_/   \_/\____/\____\  \____//_/   \____/ \_/ \____\\_/  \|
                                                                                                                     
```


# LAN Secure File System

Repository này chứa một hệ thống chia sẻ file an toàn trong mạng LAN với kiến trúc tách thành control plane và data plane. Mục tiêu của repo là quản lý phòng chia sẻ file, cấp quyền thành viên, khởi tạo upload/download qua Coordinator, và truyền file chunked đến Storage Node với cơ chế xác thực, kiểm tra toàn vẹn, dedup và quét virus.

## Tổng quan hệ thống

Hệ thống gồm 3 khối nghiệp vụ chính:

- `coordinator-node`: desktop client viết bằng Python + PySide6.
- `coordinator-server`: backend control plane viết bằng Python, dùng PostgreSQL + Redis.
- `storage-node`: data plane viết bằng Java, nhận/ghép chunk, scan file và lưu trữ.

Ngoài ra repo còn có:

- `docker-compose.yml`: dùng để dựng nhanh toàn bộ stack.
- `docs/`: tài liệu phân tích, topology, docker, manual test.
- `test-data/`: file mẫu để test upload/download.
- `run_client.bat`: script mở desktop client trên Windows.

## Kiến trúc và luồng chạy

Lượt upload:

1. Client đăng nhập vào `coordinator-server`.
2. Client gọi `INIT_UPLOAD` để xin upload plan.
3. Coordinator chọn `storage-node` khỏe nhất, tạo ticket và trả về `storageAddress`.
4. Client kết nối trực tiếp đến `storage-node` để gửi chunk.
5. Storage Node verify chunk/hash, finalize file, scan virus, commit file vào store.
6. Storage Node báo `UPLOAD_COMPLETE` về Coordinator.
7. Coordinator cập nhật metadata, audit log và phát sự kiện realtime.

Lượt download:

1. Client gọi `INIT_DOWNLOAD` lên Coordinator.
2. Coordinator kiểm tra quyền, tạo ticket download và trả về thông tin file.
3. Client kết nối trực tiếp đến `storage-node`.
4. Storage Node phục vụ chunk, client ghi file streaming và verify SHA-256.

## Cấu trúc repo

```text
.
|-- coordinator-node/        # Desktop client
|   |-- main.py
|   |-- config.py
|   |-- network/
|   |-- services/
|   |-- ui/
|   `-- assets/
|-- coordinator-server/      # Control plane backend
|   |-- main.py
|   |-- auth/
|   |-- room/
|   |-- file/
|   |-- upload/
|   |-- download/
|   |-- notification/
|   |-- storage_node/
|   |-- protocol/
|   `-- alembic/
|-- storage-node/            # Data plane storage service
|   |-- src/main/java/storagenode/
|   |-- antivirus/
|   `-- docs/
|-- docs/                    # Tài liệu tổng hợp cấp repo
|-- test-data/               # Dữ liệu test
|-- docker-compose.yml
|-- run_client.bat
`-- test-integration.sh
```

## Mô tả nhanh từng thành phần

### 1. `coordinator-node`

Client desktop cho người dùng cuối:

- Đăng nhập, đăng ký.
- Xem overview và danh sách room.
- Tạo room nếu có quyền `ADMIN`.
- Xem thành viên, thêm/xóa/sửa role trong room.
- Upload/download file.
- Xem metadata file, version, trạng thái scan.
- Chỉnh một số setting giao diện và hành vi an toàn local.

### 2. `coordinator-server`

Backend trung tâm:

- Xác thực người dùng, quản lý session.
- Quản lý room, member, role.
- Quản lý metadata file và version.
- Khởi tạo upload/download plan.
- Chọn storage node cho upload.
- Tạo và verify ticket.
- Broadcast sự kiện realtime.
- Ghi audit log.
- Theo dõi heartbeat storage node.

### 3. `storage-node`

Nơi xử lý data plane:

- Nhận file theo chunk qua TCP socket.
- Resume upload.
- Verify hash từng chunk và toàn file.
- Quét virus với ClamAV/clamd.
- Lưu file vào store và hỗ trợ dedup.
- Phục vụ download theo chunk.
- Kết nối control plane để auth, ping, gửi manifest và thông báo kết quả upload.

## Cách sử dụng

### Chạy bằng Docker Compose

Tại thư mục gốc:

```bash
docker compose up --build
```

Mặc định stack sẽ khởi tạo:

- `postgres` trên port `5432`
- `redis` trên port `6379`
- `coordinator-server` trên port `8080`, `8081`, `8082`
- `storage-node-1` trên port `9001`
- `clamd-storage-node-1`

Nếu muốn mở thêm storage node thứ hai:

```bash
docker compose --profile multi-node up --build
```

### Chạy desktop client

Trên Windows:

```bat
run_client.bat
```

Script này sẽ chuyển vào `coordinator-node/` và chạy:

```bat
pythonw main.py
```

### Chạy riêng từng thành phần

#### Coordinator Server

```bash
cd coordinator-server
python main.py
```

Cần cấu hình PostgreSQL và Redis phù hợp qua `.env` hoặc environment variables.

#### Storage Node

```bash
cd storage-node
mvn clean package
java -jar target/storage-node-1.0.0.jar storage-node.properties
```

#### Coordinator Node

```bash
cd coordinator-node
python main.py
```

## Công nghệ chính

- Frontend desktop: Python, PySide6
- Backend control plane: Python
- Data plane: Java
- Database: PostgreSQL
- Cache/ticket/session: Redis
- Antivirus: ClamAV / clamd
- Đồng bộ và truyền thông: TCP socket protocol tự định nghĩa

## Tài liệu bổ sung

- `REPORT.md`: báo cáo chi tiết về tất cả node, giao tiếp và giao diện.
- `docs/SYSTEM_TOPOLOGY_AND_DATA_FLOW_VI.md`: topology và data flow.
- `docs/DOCKER_SETUP.md`: hướng dẫn dựng Docker.
- `docs/MANUAL_TEST_GUIDE.md`: kiểm thử thủ công.
- `storage-node/docs/DATA_PLANE_PROTOCOL.md`: protocol data plane.

## Ghi chú hiện trạng

- Repo hiện tập trung rất rõ vào luồng upload/download an toàn trong LAN.
- `coordinator-server` là nơi quyết định metadata, phân quyền và phân bổ node.
- `storage-node` là nơi xử lý file thực tế.
- `coordinator-node` đã có giao diện desktop khá đầy đủ cho demo và vận hành cơ bản.
