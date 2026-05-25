# REPORT

## 1. Mục tiêu báo cáo

File này mô tả chi tiết các node và thành phần chính trong repo:

- mỗi node làm gì
- giao tiếp với nhau như thế nào
- luồng upload/download đi qua đâu
- những tính năng chính đang có trên giao diện desktop

Báo cáo được viết dựa trên code hiện có trong repo, đặc biệt là:

- `coordinator-node/main.py`
- `coordinator-node/network/*`
- `coordinator-node/ui/pages/*`
- `coordinator-server/main.py`
- `coordinator-server/client_socket_server.py`
- `coordinator-server/storage_node/storage_node_server.py`
- `coordinator-server/upload/upload_service.py`
- `coordinator-server/storage_node/registry.py`
- `storage-node/src/main/java/storagenode/StorageNodeMain.java`

## 2. Bức tranh tổng thể

Hệ thống gồm 5 node/dịch vụ mức cao:

1. `coordinator-node`
2. `coordinator-server`
3. `storage-node`
4. `postgres`
5. `redis`

Trong đó:

- `coordinator-node` là desktop app cho người dùng.
- `coordinator-server` là control plane.
- `storage-node` là data plane.
- `postgres` lưu metadata, user, room, file, audit.
- `redis` lưu ticket và session tạm thời.

## 3. Chi tiết từng node

### 3.1. Coordinator Node

Thư mục: `coordinator-node/`

Vai trò:

- giao diện desktop cho user
- gọi backend control plane
- kết nối trực tiếp đến storage node khi upload/download
- quản lý state giao diện, recent rooms, local settings

#### Thành phần chính

`main.py`

- entrypoint của desktop app
- dùng `AppController` để điều hướng giữa `LoginWindow`, `SignupWindow` và `DashboardWindow`

`config.py`

- đọc biến môi trường từ `.env`
- quy định host/port cho backend, notification, storage
- resolve global role cho user theo config admin local nếu cần

`network/backend_client_sdk.py`

- SDK TCP client để nối với `coordinator-server`
- dùng frame codec `4-byte length prefix + JSON`
- có reconnect, pending request map, background listener
- gọi được các API như `LOGIN`, `LIST_ROOMS`, `INIT_UPLOAD`, `INIT_DOWNLOAD`, `CREATE_SHARE_TOKEN`

`network/storage_node_data_plane.py`

- client data plane để nối trực tiếp `storage-node`
- upload/download theo streaming, không load cả file vào RAM
- thương lượng key exchange hiện đại
- mã hóa AES-256-GCM
- verify hash chunk và hash toàn file

`services/services.py`

- tạo facade cho UI sử dụng
- gồm `AuthService`, `RoomService`, `FileService`, `UploadService`, `DownloadService`, `NotificationService`

`ui/`

- chứa toàn bộ page, widget, settings store, recent room store, dashboard shell

#### Các màn hình chính

`ui/pages/login_page.py`

- form đăng nhập
- check trạng thái server lúc startup
- đăng nhập bằng worker thread để không block UI

`ui/pages/signup_page.py`

- form đăng ký
- validate username/email/password
- tạo tài khoản qua backend

`ui/dashboard.py`

- khung dashboard chính
- sidebar route sang `Overview`, `My Rooms`, `Settings`, và `RoomPage`

`ui/pages/overview_page.py`

- hiện thống kê tổng quan
- số room, số file, số thành viên
- room gần đây
- activity ticker
- server status

`ui/pages/my_rooms_page.py`

- load danh sách room có thể truy cập
- tìm kiếm room
- tạo room nếu user có role `ADMIN`

`ui/pages/room_page.py`

- page nghiệp vụ quan trọng nhất
- hiện danh sách file trong room
- xem chi tiết file
- upload file
- download file
- xem version
- thêm/xóa member
- đổi role member
- xóa file
- hiện sidebar/drawer cho room members và action state

`ui/pages/settings_page.py`

- tùy chỉnh giao diện local
- reduce glow, reduce animation, compact layout
- confirm before deleting files
- warn before downloading unscanned files
- hide user id by default
- xem thông tin account và runtime connection
- logout

#### Các tính năng chính trên giao diện

- Đăng nhập / đăng ký
- Theo dõi backend online/offline ngay trên login
- Overview thống kê room, file, member, server
- Xem room gần đây
- Tìm kiếm room
- Tạo room mới
- Xem danh sách file trong room
- Xem metadata file: size, uploader, version, hash, mime, scan status
- Upload file
- Download file
- Xem lịch sử version
- Thêm member bằng user ID
- Xóa member
- Đổi role `OWNER/MEMBER/VIEWER`
- Xóa file
- Quản lý setting local của dashboard

### 3.2. Coordinator Server

Thư mục: `coordinator-server/`

Vai trò:

- backend control plane trung tâm
- tiếp nhận request từ client
- phân quyền user
- quản lý room và metadata file
- cấp ticket upload/download
- chọn storage node
- xử lý notification và audit
- giao tiếp control plane với storage node

#### Entry point

`main.py`

- load config
- kết nối PostgreSQL và Redis
- khởi tạo service:
  - `AuthService`
  - `AuthorizationService`
  - `RoomService`
  - `FileService`
  - `UploadService`
  - `DownloadService`
  - `NotificationService`
  - `HealthService`
  - `AuditService`
  - `TicketService`
  - `StorageNodeRegistry`
  - `ReconciliationService`
- start 2 socket server:
  - `ClientSocketServer` trên client port
  - `StorageNodeServer` trên storage port

#### Node con/phân hệ quan trọng

`client_socket_server.py`

- phục vụ desktop client
- map message type sang handler
- áp auth middleware cho API cần đăng nhập

Nhóm message chính:

- auth: `SIGNUP`, `LOGIN`, `LOGOUT`
- room: `CREATE_ROOM`, `ADD_MEMBER`, `REMOVE_MEMBER`, `SET_ROLE`, `LIST_ROOMS`, `LIST_MEMBERS`
- file: `LIST_FILES`, `FILE_DETAIL`, `FILE_VERSIONS`, `DELETE_FILE`
- upload: `INIT_UPLOAD`
- download: `INIT_DOWNLOAD`
- share: `CREATE_SHARE_TOKEN`
- notification: `SUBSCRIBE_ROOM`, `UNSUBSCRIBE_ROOM`
- health: `PING`, `STATUS`

`storage_node/storage_node_server.py`

- phục vụ storage node kết nối vào coordinator
- xử lý:
  - `STORAGE_AUTH`
  - `PING`
  - `VERIFY_TICKET`
  - `UPLOAD_COMPLETE`
  - `UPLOAD_FAILED`
  - `MANIFEST_DELTA`

`storage_node/registry.py`

- theo dõi storage node đã auth
- lưu heartbeat, `active_uploads`, `storageAddress`, manifest file
- chọn node để upload theo node khỏe và ít upload nhất
- kiểm tra node có đang giữ file nào không

`upload/upload_service.py`

- kiểm tra quyền upload
- chống duplicate file trong cùng room
- tìm khả năng dedup
- chọn storage node
- tạo file record metadata trong DB
- tạo ticket và lưu Redis
- khi nhận `UPLOAD_COMPLETE` thì đổi status sang `READY`
- khi nhận `UPLOAD_FAILED` hoặc mismatch thì đánh dấu `DELETED`

`download/download_service.py`

- khởi tạo kế hoạch download
- check quyền theo room hoặc share token
- trả thông tin storage node, file metadata, ticket

`notification/*`

- quản lý subscriber theo room
- broadcast sự kiện `NEW_FILE`, `FILE_DELETED`, thay đổi member

`auth/*`

- đăng ký, đăng nhập, session, middleware auth, authorization

`audit/*`

- ghi audit log cho các action quan trọng

`protocol/*`

- protocol message, frame codec và socket abstractions cho coordinator

#### Chức năng của coordinator-server trong hệ thống

- Trung gian kiểm soát mọi request nghiệp vụ
- Giữ metadata nhất quán
- Ra quyết định storage node nào được dùng
- Sinh ticket ngắn hạn để client và storage node tin nhau
- Giúp hệ thống tách control plane và data plane rõ ràng

### 3.3. Storage Node

Thư mục: `storage-node/`

Vai trò:

- nhận/truyền file thực tế
- xử lý chunk
- lưu dữ liệu
- quét virus
- thông báo kết quả về coordinator

#### Entry point

`src/main/java/storagenode/StorageNodeMain.java`

Khi chạy sẽ:

1. đọc `storage-node.properties`
2. setup logging
3. khởi tạo `FileStore`, `DedupStore`
4. bật/tắt antivirus scanner
5. khởi tạo `SessionManager`
6. recover các session upload đang dở
7. tạo RSA key exchange
8. kết nối đến coordinator control plane
9. bật monitor
10. start `StorageServer`

#### Thành phần chính

`network/StorageServer.java`

- TCP server cho data plane
- nhận message upload/download từ client

`network/CoordinatorClient.java`

- kết nối coordinator-server control plane
- auth node, ping, gửi upload status, gửi manifest

`network/ClientHandler.java`

- xử lý từng kết nối client data plane
- mở session upload/download
- xử lý request chunk

`session/UploadSession.java`, `session/DownloadSession.java`, `session/SessionManager.java`

- quản lý session upload/download
- resume upload
- timeout session

`storage/FileStore.java`

- lưu chunk tạm, ghép file, move file sang store

`storage/DedupStore.java`

- registry dedup dựa trên hash nội dung

`antivirus/*`

- `ClamAvClient` nối với `clamd`
- scan file trước khi commit
- có `NoOpAntivirusScanner` khi tắt antivirus

`protocol/*`

- frame codec và message type data plane/control plane

`crypto/*`

- AES
- hash util
- RSA key exchange
- modern key exchange

`monitor/StorageMonitor.java`

- log thống kê vận hành node

#### Việc Storage Node giao tiếp với Coordinator

Storage Node kết nối control plane đến `coordinator-server` để:

- auth bằng secret chung
- gửi heartbeat
- gửi manifest lúc startup
- gửi `MANIFEST_DELTA` khi file thay đổi
- gửi `UPLOAD_COMPLETE` / `UPLOAD_FAILED`

#### Việc Storage Node giao tiếp với Client

Client desktop nối trực tiếp đến storage node để:

- `OPEN_UPLOAD`
- `UPLOAD_CHUNK`
- `FINALIZE_UPLOAD`
- `OPEN_DOWNLOAD`
- `REQUEST_CHUNK`

Trong quá trình này:

- dữ liệu được stream theo chunk
- chunk được mã hóa
- hash chunk và hash tổng được verify
- node hỗ trợ resume upload

### 3.4. PostgreSQL

Vai trò:

- lưu user
- lưu room
- lưu room members
- lưu file metadata
- lưu share token metadata nếu có
- lưu scan reports
- lưu audit logs

Dấu vết trong repo:

- `coordinator-server/alembic/versions/*`
- `coordinator-server/database.py`

### 3.5. Redis

Vai trò:

- lưu session
- lưu upload/download ticket
- hỗ trợ dữ liệu tạm thời có TTL

Dấu vết trong repo:

- `coordinator-server/redis_client.py`
- `coordinator-server/ticket/ticket_service.py`
- `coordinator-server/auth/auth_service.py`

## 4. Giao tiếp giữa các node

### 4.1. Coordinator Node <-> Coordinator Server

Kiểu kết nối:

- TCP socket
- frame codec do `backend_client_sdk.py` và `protocol/frame_codec.py` xử lý
- payload JSON có `type`, `requestId`, `payload`

Các nhóm lệnh chính:

- auth: signup/login/logout
- room: create/list/add/remove/set role
- file: list/detail/version/delete
- upload plan: `INIT_UPLOAD`
- download plan: `INIT_DOWNLOAD`
- share token
- notification subscribe
- health check

### 4.2. Coordinator Node <-> Storage Node

Kiểu kết nối:

- TCP socket data plane
- streaming chunk
- key exchange hiện đại
- AES-256-GCM cho payload data plane

Upload:

1. client mở `OPEN_UPLOAD`
2. gửi từng `UPLOAD_CHUNK`
3. nhận `ACK_CHUNK`
4. gọi `FINALIZE_UPLOAD`

Download:

1. client mở `OPEN_DOWNLOAD`
2. gửi `REQUEST_CHUNK`
3. nhận `DOWNLOAD_CHUNK`
4. kết thúc bằng `DOWNLOAD_COMPLETE`

### 4.3. Storage Node <-> Coordinator Server

Kiểu kết nối:

- TCP socket control plane riêng

Message chính:

- `STORAGE_AUTH`
- `PING`
- `VERIFY_TICKET`
- `UPLOAD_COMPLETE`
- `UPLOAD_FAILED`
- `MANIFEST_DELTA`

Mục đích:

- coordinator biết node nào đang sống
- coordinator biết node nào đang giữ file nào
- coordinator có thể giao upload cho node phù hợp
- metadata file được đồng bộ về DB sau khi upload xong

### 4.4. Coordinator Server <-> PostgreSQL

Mục đích:

- metadata persistence
- room/member/file versioning
- audit và truy vấn nghiệp vụ

### 4.5. Coordinator Server <-> Redis

Mục đích:

- session và ticket có hạn
- lookup nhanh cho upload/download

## 5. Luồng nghiệp vụ chính

### 5.1. Đăng nhập

1. User nhập username/password trên `LoginWindow`
2. `LoginWorker` tạo `BackendService`
3. GUI gọi `LOGIN` đến coordinator-server
4. backend trả token và thông tin user
5. `AppController` mở `DashboardWindow`

### 5.2. Tạo room

1. User `ADMIN` mở `MyRoomsPage`
2. Nhấn `Create`
3. `CreateRoomWorker` gọi `CREATE_ROOM`
4. Coordinator ghi DB và trả room mới
5. UI reload room list và thêm activity local

### 5.3. Upload file

1. User chọn file trong `RoomPage`
2. `FileUploadWorker` tính hash file
3. GUI gọi `INIT_UPLOAD` lên coordinator-server
4. `UploadService` check quyền, duplicate, dedup, chọn storage node, tạo ticket
5. Client dùng `StorageNodeDataPlaneClient.upload_file()`
6. Storage Node nhận chunk, xác minh, finalize, scan virus
7. Storage Node gửi `UPLOAD_COMPLETE` về Coordinator
8. Coordinator update DB sang `READY` và broadcast `NEW_FILE`
9. UI reload room data

### 5.4. Download file

1. User bấm download tại `RoomPage`
2. `FileDownloadWorker` gọi `INIT_DOWNLOAD`
3. Coordinator check quyền và trả plan
4. Client kết nối storage node và request chunk
5. File được ghi streaming xuống đĩa
6. Client verify SHA-256 tổng

### 5.5. Quản lý thành viên

1. User mở room members drawer
2. Nếu đủ quyền thì có thể:
   - thêm member
   - sửa role
   - xóa member
3. UI gọi backend qua `MemberActionWorker`
4. Coordinator update DB và có thể broadcast event

### 5.6. Xóa file

1. User bấm delete trong `RoomPage`
2. UI có thể yêu cầu xác nhận theo setting local
3. `FileDeleteWorker` gọi `DELETE_FILE`
4. Coordinator cập nhật metadata và broadcast event

## 6. Tính năng UI nổi bật

### 6.1. Login và Signup

- startup health check
- worker thread để tránh treo UI
- validate input
- thông báo lỗi rõ ràng

### 6.2. Dashboard

- sidebar điều hướng
- top bar hiện user, role, server status
- activity feed
- thống kê tổng quan

### 6.3. Room workspace

- danh sách file
- panel chi tiết file
- member drawer
- upload/download
- version dialog
- remove/role confirmation overlay
- toast / status sidebar cho tiến trình

### 6.4. Settings

- các setting này hiện tại là frontend-only
- ảnh hưởng cách UI hiển thị và xác nhận thao tác

## 7. Ưu điểm kiến trúc hiện tại

- Tách control plane và data plane rõ ràng
- Metadata và permission không nằm trong storage node
- Storage node có thể scale ngang
- Upload theo chunk và hỗ trợ resume
- Scan virus tại nơi lưu trữ thay vì tin client
- Dedup giúp tiết kiệm dung lượng
- Registry + heartbeat giúp load balancing upload

## 8. Giới hạn và ghi chú

- Notification port có khai báo nhưng UI hiện tại chủ yếu sử dụng cùng kênh socket backend
- Một số setting ở `SettingsPage` là local preference, chưa đồng bộ lên server
- Repo có nhiều tài liệu nội bộ và file test, nhưng luồng nghiệp vụ chính đã tập trung vào desktop client + coordinator + storage node
- `storage-node/target/` đang có artifact build sẵn trong repo

## 9. Kết luận

Repo này không chỉ là một storage node đơn lẻ mà là một hệ thống LAN secure file system khá đầy đủ:

- `coordinator-node` lo giao diện và trải nghiệm người dùng
- `coordinator-server` lo metadata, permission, orchestration
- `storage-node` lo luồng file thực tế và bảo mật data plane

Đây là kiến trúc hợp lý cho bài toán chia sẻ file an toàn trong mạng nội bộ, đặc biệt khi cần:

- phân quyền theo room
- upload/download file lớn
- scan virus
- scale nhiều storage node
- giảm tải cho backend control plane
