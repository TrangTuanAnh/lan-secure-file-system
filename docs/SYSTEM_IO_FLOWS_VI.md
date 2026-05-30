# BÁO CÁO LUỒNG DỮ LIỆU VÀ XỬ LÝ I/O — `lan-secure-file-system`

Tài liệu trình bày toàn bộ luồng nhập/xuất của hệ thống chia sẻ tệp an toàn trong mạng LAN. Bố cục mỗi luồng: *Mô tả nhanh → Vị trí cụ thể trên các máy → Logic hoạt động & lý do thiết kế → Lợi ích*.

Trình tự các mục lớn theo vòng đời của một phiên làm việc phía máy khách: khung giao tiếp → xác thực → quản lý phòng và tệp → tải lên / tải xuống → vận hành cụm storage node → kênh đẩy sự kiện → kiểm toán và giám sát → dọn dẹp nền.

---

# I. KHUNG GIAO TIẾP I/O

## I.1. Frame codec — đóng gói và giải gói thông điệp

**Mô tả nhanh.** Mọi thông điệp TCP được đóng gói theo định dạng `[4 byte độ dài big-endian][payload]`. Bộ codec dùng chung cho cả Coordinator (Python) lẫn Storage Node (Java), giới hạn 10 MB cho mỗi khung.

**Vị trí cụ thể.**
- Python: `coordinator-server/protocol/frame_codec.py` (`encode`, `decode_header`, `decode_frame`).
- Java: `storage-node/src/main/java/storagenode/protocol/FrameCodec.java`, `ControlPlaneFrameCodec.java`.
- Danh mục kiểu thông điệp: `coordinator-server/protocol/message_types.py`, `storage-node/.../protocol/MessageType.java`.

**Logic và lý do thiết kế.** 4 byte big-endian (`!I` trong Python) tuân theo thứ tự byte mạng, dễ kiểm tra trực quan. Giới hạn 10 MB mỗi khung vừa ngăn cạn bộ nhớ, vừa phản ánh kích thước chunk tối đa hợp lý.

**Lợi ích.** Mã hoá đa ngôn ngữ có tính tất định; phòng ngừa khung không trọn vẹn; ngưỡng kích thước an toàn.

## I.2. BaseSocketServer — luồng accept và pool worker

**Mô tả nhanh.** Một lớp socket server trừu tượng dùng chung: một luồng acceptor chạy `selector.select()`, đẩy mỗi thông điệp vào `ThreadPoolExecutor` để worker xử lý song song. Cả `ClientSocketServer` (cổng 8080), `StorageNodeServer` (cổng 8081) và `NotificationServer` (kênh đẩy) đều kế thừa lớp này.

**Vị trí cụ thể.**
- `coordinator-server/protocol/socket_server.py:102` `BaseSocketServer`.
- Luồng acceptor: dòng 186 `_server_thread = Thread(target=_run_loop, ...)`.
- Pool worker: dòng 180 `ThreadPoolExecutor(max_workers, thread_name_prefix=...)`.
- Phân phối thông điệp: dòng 319 `_dispatch_message` → submit vào pool.
- Xử lý tín hiệu tắt đa nền tảng: `coordinator-server/main.py:34` `shutdown_handler` sử dụng `threading.Event().wait(timeout)` thay cho `signal.pause()` để chạy đồng nhất trên Windows / Linux / macOS.

**Logic và lý do thiết kế.**
1. Acceptor theo mô hình selector: một luồng quản N kết nối thay vì spawn một luồng cho mỗi kết nối.
2. Mô hình producer-consumer: acceptor chỉ làm I/O (đọc khung); pool worker chạy nghiệp vụ — N máy khách gửi đồng thời thì N worker chạy song song.
3. `ThreadPoolExecutor` giới hạn số worker (mặc định 8 cho `ClientSocketServer`, 4 cho `StorageNodeServer`), ngăn bùng nổ luồng.
4. `_connections_lock` bảo vệ ánh xạ `socket → SocketConnection` khi nhiều luồng cùng đọc/ghi.

**Lợi ích.** Cùng một khung phục vụ ba server trên các cổng khác nhau; không phải viết lại tầng I/O; số luồng có chặn trên.

## I.3. Middleware xác thực — kiểm tra token cho mọi yêu cầu cần quyền

**Mô tả nhanh.** Mọi handler có yêu cầu xác thực đều được bao bọc qua `_handle_authenticated_request`, gọi `auth_middleware.validate_request` để lấy phiên từ Redis trước khi chuyển sang nghiệp vụ.

**Vị trí cụ thể.**
- `coordinator-server/auth/auth_middleware.py` `AuthMiddleware.validate_request`.
- Wrapper: `coordinator-server/client_socket_server.py:455` `_handle_authenticated_request`.
- Kho phiên: `coordinator-server/redis_client.py` (`set_session`, `get_session`, `delete_session`).

**Logic và lý do thiết kế.** Token UUID gửi kèm thông điệp → middleware tra Redis → trả `context={userId, globalRole}` cho handler. Nếu lỗi, phản hồi `INVALID_TOKEN`.

**Lợi ích.** Mọi kiểm tra quyền tập trung tại một điểm; thay đổi định dạng token không phải sửa từng handler.

---

# II. LUỒNG XÁC THỰC NGƯỜI DÙNG

## II.1. SIGNUP — đăng ký tài khoản

**Mô tả nhanh.** Máy khách gửi `{username, email, password}` → Coordinator kiểm tra hợp lệ → kiểm tra trùng lặp → băm mật khẩu → INSERT bản ghi `users` → ghi nhật ký kiểm toán.

**Vị trí cụ thể.**
- Handler: `client_socket_server.py:142` `_handle_signup`.
- Service: `auth/auth_service.py:39` `signup`.
- Bộ băm mật khẩu: `auth/password_hasher.py` (bcrypt).

**Logic và lý do thiết kế.**
1. Kiểm tra hợp lệ đầu vào (ba trường không rỗng).
2. Kiểm tra trùng `username` rồi đến `email` qua hai truy vấn riêng → mã lỗi rõ ràng: `DUPLICATE_USERNAME` / `DUPLICATE_EMAIL`.
3. Băm mật khẩu trước khi INSERT — không bao giờ lưu nguyên văn.
4. Sinh `user_id = uuid4()`, `global_role = 'USER'` mặc định.
5. Ghi nhật ký kiểm toán cả trạng thái SUCCESS lẫn FAILED (lý do `duplicate_username` / `duplicate_email`) → phát hiện hành vi liệt kê tài khoản.

**Lợi ích.** Phân biệt rõ mã lỗi cho giao diện; có dấu vết để phát hiện hành vi dò email/username; mật khẩu không bao giờ xuất hiện trong log.

## II.2. LOGIN — xác thực và cấp phiên

**Mô tả nhanh.** Máy khách gửi `{username, password}` → xác minh băm → sinh token UUID kèm TTL → lưu Redis → trả về token, thời điểm hết hạn và hồ sơ người dùng.

**Vị trí cụ thể.**
- Handler: `client_socket_server.py:156` `_handle_login`.
- Service: `auth/auth_service.py:218` `login` / `:239` `login_with_profile`.
- Logic lõi: `:133` `_authenticate_and_create_session`.
- Nạp hồ sơ: `:252` `_load_user_profile`.

**Logic và lý do thiết kế.**
1. Tra cứu người dùng theo `username` để lấy `password_hash`.
2. `password_hasher.verify(password, hash)` — so sánh thời gian hằng để chống tấn công theo thời gian.
3. Sinh `token = uuid4()`, `expires_at = now + session_ttl`, `session_data = {userId, globalRole, createdAt}`.
4. `redis.set_session(token, session_data, ttl)` — Redis tự thu hồi khi TTL hết, không cần cron dọn dẹp.
5. Trả `{token, expiresAt, userProfile}` cho máy khách. Ghi nhật ký kiểm toán SUCCESS/FAILED kèm lý do (`user_not_found`, `invalid_password`).

**Lợi ích.** Phiên ngắn hạn tự thu hồi; token stateless với server (chỉ cần tra Redis); có nhật ký để truy vết các lần đăng nhập thất bại.

## II.3. LOGOUT — huỷ phiên

**Mô tả nhanh.** Máy khách gửi token → Coordinator gọi `delete_session(token)` trên Redis.

**Vị trí cụ thể.**
- Handler: `client_socket_server.py:170` `_handle_logout`.
- Service: `auth/auth_service.py:310` `logout`.

**Logic và lý do thiết kế.** Idempotent: token đã hết hạn hoặc không tồn tại vẫn trả thành công "đã đăng xuất" (không tiết lộ thông tin trạng thái). Ghi nhật ký kiểm toán LOGOUT.

**Lợi ích.** Cho phép đăng xuất từ thiết bị khác; không phải đợi TTL hết hạn.

## II.4. VALIDATE_TOKEN — kiểm tra token tại middleware

**Mô tả nhanh.** Gọi cho mỗi yêu cầu cần xác thực. Đọc trường `token` → tra Redis → trả `(userId, globalRole)` cho handler.

**Vị trí cụ thể.** `auth/auth_service.py:274` `validate_token`.

**Logic và lý do thiết kế.** Phiên được lưu cache trên Redis với TTL → độ trễ kiểm tra thấp hơn nhiều so với truy vấn bảng `users` mỗi lần.

**Lợi ích.** Thời gian kiểm tra xác thực dưới mili-giây; có thể mở rộng theo chiều ngang nếu thêm Coordinator chung Redis.

## II.5. KIỂM TRA QUYỀN — ma trận phân quyền theo vai trò

**Mô tả nhanh.** Mỗi hành động có một ma trận quyền cố định: `ADMIN` (toàn cục), `OWNER` / `MEMBER` / `VIEWER` (theo từng phòng). Mọi service nghiệp vụ gọi `check_permission` trước khi thao tác.

**Vị trí cụ thể.**
- `auth/authorization_service.py:69` `check_permission`.
- Ma trận: `:120` `_check_permission_matrix`.
- Vai trò theo phòng: `:144` `get_user_role_in_room`.

**Logic và lý do thiết kế.**
1. `ADMIN` toàn cục ⇒ có toàn bộ quyền (vượt qua mọi giới hạn phòng).
2. Ngoài ra tra bảng `room_members` để lấy vai trò trong phòng → đối chiếu với ma trận `{hành động → tập hợp vai trò được phép}`.
3. Ma trận khai báo cứng trong mã nguồn (không nạp từ cấu hình ngoài) — thuận tiện cho phân tích tĩnh và kiểm toán.

**Lợi ích.** Quy tắc tập trung tại một nơi; giao diện biết trước hành động nào được phép thay vì thử rồi nhận lỗi.

---

# III. LUỒNG QUẢN LÝ PHÒNG VÀ THÀNH VIÊN

## III.1. CREATE_ROOM — tạo phòng mới

**Mô tả nhanh.** Chỉ người dùng có `global_role = 'ADMIN'` mới được tạo phòng. Tạo bản ghi `rooms` đồng thời gán người tạo là `OWNER` trong `room_members`.

**Vị trí cụ thể.**
- Handler: `client_socket_server.py:186` `_handle_create_room`.
- Service: `room/room_service.py:34` `create_room`.

**Logic và lý do thiết kế.**
1. Xác minh `global_role == 'ADMIN'` (chỉ ADMIN mới tạo được phòng, người dùng thông thường không).
2. INSERT `rooms(id, name, created_by, created_at)`.
3. INSERT `room_members(room_id, user_id, role='OWNER', added_at)` — người tạo tự động là OWNER.
4. Ghi nhật ký kiểm toán `CREATE_ROOM` SUCCESS với `target_id=room_id, room_id=room_id`.

**Lợi ích.** Quyền tạo phòng tập trung ở ADMIN → tránh sinh phòng dư thừa; người tạo có toàn quyền quản lý ngay từ đầu.

## III.2. ADD_MEMBER — thêm thành viên vào phòng

**Mô tả nhanh.** Chỉ `ADMIN` hoặc `OWNER` của phòng mới được thêm thành viên. Kiểm tra hợp lệ vai trò (`OWNER` / `MEMBER` / `VIEWER`), INSERT `room_members`, phát sự kiện `MEMBER_ADDED`.

**Vị trí cụ thể.**
- Handler: `client_socket_server.py:196` `_handle_add_member`.
- Service: `room/room_service.py:107` `add_member`.
- Kiểm tra quyền quản lý: `room_service.py:471` `_can_manage_members`.
- Phát sự kiện: `notification_service.py:121` `broadcast_member_added`.

**Logic và lý do thiết kế.**
1. `_can_manage_members` (ADMIN toàn cục hoặc OWNER của phòng).
2. Kiểm tra vai trò thuộc tập hợp `{OWNER, MEMBER, VIEWER}` → ngăn injection vai trò không hợp lệ.
3. Kiểm tra người dùng tồn tại và chưa là thành viên → trả `ALREADY_MEMBER` nếu trùng.
4. INSERT → ghi nhật ký kiểm toán `ADD_MEMBER` → phát sự kiện `MEMBER_ADDED` thời gian thực.

**Lợi ích.** Giao diện của các thành viên khác cập nhật ngay khi có người mới (không cần làm mới thủ công); có dấu vết kiểm toán cho mọi thay đổi danh sách.

## III.3. REMOVE_MEMBER — gỡ thành viên

**Mô tả nhanh.** Tương tự ADD_MEMBER nhưng DELETE bản ghi. Phát sự kiện `MEMBER_REMOVED`.

**Vị trí cụ thể.**
- Handler: `client_socket_server.py:206` `_handle_remove_member`.
- Service: `room/room_service.py:195` `remove_member`.

**Logic và lý do thiết kế.**
1. Quyền tương tự ADD.
2. Không cho phép xoá OWNER cuối cùng — kiểm tra trong service.
3. DELETE bản ghi, ghi nhật ký kiểm toán, phát sự kiện.

**Lợi ích.** Quản lý sạch danh sách thành viên; giao diện cập nhật thời gian thực.

## III.4. SET_ROLE — thay đổi vai trò thành viên

**Mô tả nhanh.** OWNER / ADMIN đổi vai trò của một thành viên hiện có. UPDATE `room_members.role`, phát sự kiện `ROLE_UPDATED`.

**Vị trí cụ thể.**
- Handler: `client_socket_server.py:216` `_handle_set_role`.
- Service: `room/room_service.py:274` `set_role`.

**Logic và lý do thiết kế.** Kiểm tra quyền, kiểm tra hợp lệ vai trò, UPDATE, ghi nhật ký kiểm toán `SET_ROLE`, phát sự kiện `ROLE_UPDATED`.

**Lợi ích.** Thăng giáng vai trò không cần xoá rồi thêm lại; nhật ký kiểm toán ghi rõ ai thay đổi vai trò của ai.

## III.5. LIST_ROOMS / LIST_MEMBERS — truy vấn metadata

**Mô tả nhanh.** Luồng chỉ đọc. `LIST_ROOMS` trả các phòng mà người dùng là thành viên (hoặc toàn bộ nếu là ADMIN). `LIST_MEMBERS` trả danh sách thành viên và vai trò trong một phòng cụ thể.

**Vị trí cụ thể.**
- Handlers: `client_socket_server.py:226` `_handle_list_rooms`, `:236` `_handle_list_members`.
- Services: `room/room_service.py:353` `list_rooms`, `:416` `list_members`.

**Logic và lý do thiết kế.** ADMIN thấy mọi phòng; người dùng khác chỉ thấy phòng mình là thành viên. JOIN với `users` để lấy `username` phục vụ hiển thị.

**Lợi ích.** Một truy vấn cung cấp đủ thông tin cho giao diện, giảm số lần round-trip.

---

# IV. LUỒNG QUẢN LÝ METADATA TỆP

## IV.1. LIST_FILES — liệt kê tệp trong phòng

**Mô tả nhanh.** Trả các tệp có trạng thái `READY` trong một phòng, kèm `username` của người tải lên. Loại bỏ các trạng thái `UPLOADING`, `DELETED`, `MISSING`.

**Vị trí cụ thể.**
- Handler: `client_socket_server.py:248` `_handle_list_files`.
- Service: `file/file_service.py:32` `list_files`.

**Logic và lý do thiết kế.**
1. `_has_room_access` (ADMIN hoặc thành viên của phòng).
2. JOIN `files` với `users` để lấy `uploader_username` trong một truy vấn duy nhất.
3. Lọc `status = 'READY'` → người dùng không thấy tệp đang tải dở của người khác hoặc tệp bị cách ly do nhiễm virus.

**Lợi ích.** Giao diện hiển thị sạch (chỉ tệp khả dụng); một truy vấn cung cấp đủ dữ liệu.

## IV.2. FILE_DETAIL — chi tiết một tệp

**Mô tả nhanh.** Trả thông tin đầy đủ của một `file_id`: tên, kích thước, SHA-256, tổng số chunk, phiên bản, người tải lên, trạng thái.

**Vị trí cụ thể.** `file/file_service.py:98` `get_file_detail`.

**Logic và lý do thiết kế.** Tách khỏi LIST để máy khách gọi theo yêu cầu khi mở chi tiết — tiết kiệm payload cho khung nhìn danh sách.

**Lợi ích.** Payload danh sách nhẹ; tải chi tiết theo yêu cầu.

## IV.3. FILE_VERSIONS — lịch sử phiên bản

**Mô tả nhanh.** Trả mọi phiên bản của một tệp theo cặp `(original_name, room_id)`. Mỗi lần tải lên cùng tên trong phòng làm phiên bản tăng thêm một bậc.

**Vị trí cụ thể.**
- Service: `file/file_service.py:167` `get_file_versions`.
- Tính phiên bản kế tiếp: `file_service.py:336` `calculate_next_version` (gọi từ luồng tải lên).

**Logic và lý do thiết kế.** Phiên bản hoá theo `(room_id, original_name)`. Mỗi lần tải lên trùng tên tạo bản ghi mới với `version = max(existing) + 1` → không ghi đè, lịch sử được bảo toàn.

**Lợi ích.** Quay lại phiên bản cũ mà không cần sao lưu thủ công; người dùng thấy đầy đủ lịch sử trong giao diện.

## IV.4. DELETE_FILE — xoá mềm

**Mô tả nhanh.** Chuyển `status = 'DELETED'`, phát sự kiện `FILE_DELETED`. Không xoá dữ liệu vật lý trên storage node ngay (tệp có thể vẫn được khử trùng lặp khi người dùng khác tải lên cùng SHA-256).

**Vị trí cụ thể.**
- Handler: `client_socket_server.py:278` `_handle_delete_file`.
- Service: `file/file_service.py:235` `delete_file`.
- Kiểm tra quyền xoá: `file_service.py:403` `_can_delete_file` (ADMIN / OWNER của phòng / người tải lên).

**Logic và lý do thiết kế.**
1. ADMIN, OWNER của phòng hoặc chính người tải lên đều được xoá.
2. Xoá mềm bằng UPDATE trạng thái → metadata vẫn còn để kiểm toán, tệp biến mất khỏi LIST_FILES.
3. Phát sự kiện `FILE_DELETED` → giao diện của các máy khách khác cập nhật ngay.
4. Ghi nhật ký kiểm toán `DELETE_FILE` SUCCESS.

**Lợi ích.** Có thể khôi phục (quản trị viên thực hiện UPDATE để khôi phục); có dấu vết kiểm toán; cơ chế khử trùng lặp vẫn dùng được tệp nếu người dùng khác tải lên cùng SHA-256.

---

# V. LUỒNG TẢI LÊN (UPLOAD)

## V.1. INIT_UPLOAD — khởi tạo phiên tải lên và đặt trước slot (Control Plane)

**Mô tả nhanh.** Máy khách gửi metadata tệp → Coordinator chọn node và đặt trước slot trong cùng một lock, sinh thẻ HMAC, trả về `UPLOAD_PLAN`. Bước này chỉ trao đổi JSON metadata, không truyền nội dung tệp.

**Vị trí cụ thể.**
- Cổng `8080`: `coordinator-server/main.py:171` → `client_socket_server.py:290` `_handle_init_upload`.
- Lõi xử lý: `coordinator-server/upload/upload_service.py:157` `handle_init_upload`. `file_id` được sinh trước để làm `reservation_id` (dòng 300).
- Chọn node và đặt trước slot: `storage_node/registry.py:197` `select_for_upload`.
- Sinh thẻ HMAC: `ticket/hmac_ticket.py:13` `create_hmac_ticket_fields`.
- Tận dụng tệp đã có (khử trùng lặp): `upload_service.py:112` `_pick_reusable_dedup`.

**Logic và lý do thiết kế.**
1. Xác thực quyền `UPLOAD_FILE`, ngăn trùng tệp trong cùng phòng qua `find_same_room_duplicate`.
2. Tìm bản đã có toàn hệ thống → nếu node giữ bản gốc còn hoạt động → tạo bản ghi `READY` ảo, không truyền dữ liệu.
3. Sinh `file_id` trước rồi dùng làm `reservation_id` để khi nhận `UPLOAD_COMPLETE` / `UPLOAD_FAILED` chỉ cần `file_id` là đóng đúng slot.
4. `select_for_upload(reservation_id, ttl_seconds=60)`: thực hiện P2C + tăng `active_uploads` + ghi `_reservations` trong cùng một lock.
5. Insert bản ghi với trạng thái `UPLOADING`; nếu DB lỗi → gọi `_release_slot(file_id)` để giải phóng ngay.
6. Thẻ HMAC định dạng `sessionId|fileId|nodeId|expiry` ký bằng SHA-256, TTL 30 phút.

**Lợi ích.** Một round-trip metadata; slot đặt trước tức thì kèm TTL → bộ cân bằng tải không bị sai lệch thông tin về tải hiện hành.

## V.2. UPLOAD CHUNK — truyền dữ liệu (Data Plane)

**Mô tả nhanh.** Máy khách mở kết nối TCP trực tiếp tới Storage Node trên cổng `9001`, thực hiện bắt tay khoá → sinh khoá phiên AES, truyền theo dòng từng chunk 512 KB kèm SHA-256 mỗi chunk và mã hoá. Đây là luồng I/O có lưu lượng lớn nhất của hệ thống.

**Vị trí cụ thể.**
- Phía máy khách: `coordinator-node/network/storage_node_data_plane.py:314` `upload_file` (vòng gửi: dòng 378–404). Bắt tay khoá: dòng 210 `_negotiate_crypto`; lớp `_CryptoSession` dòng 186.
- Phía storage node: `storage-node/.../network/ClientHandler.java:324` `handleUploadChunk`. Ghi chunk: `storage/FileStore.java:91` `writeChunk`.
- Bắt tay khoá phía Java: `storage-node/.../network/ClientHandler.java:178` `handleModernKeyBootstrap`, `:204` `handleHybridKeyInit`, `:232` `handleEcdhKeyInit`. Hỗ trợ mật mã: `storage-node/.../crypto/ModernKeyExchange.java`, `crypto/AESCrypto.java`.
- Xác minh thẻ HMAC tại chỗ: `.../CoordinatorClient.java:75` `verifyTicket`.

**Logic và lý do thiết kế.**

*(a) Bắt tay khoá phiên.* Hỗ trợ ba nhánh, máy khách và máy chủ tự thương lượng nhánh tốt nhất mà cả hai đều hỗ trợ:

1. **Nhánh kế thừa**: RSA trao đổi khoá AES + AES-256-CBC cho mỗi chunk. Giữ lại để tương thích với storage node phiên bản cũ chưa được nâng cấp.
2. **Nhánh ECDH-only**: ECDH trên đường cong P-256 + HKDF-SHA256 dẫn xuất khoá → AES-256-GCM. Định danh giao thức `ECDH-P256-HKDF-SHA256`.
3. **Nhánh lai (hybrid, mặc định nếu hai bên đều hỗ trợ)**: kết hợp ECDH P-256 với ML-KEM-768 (cơ chế đóng gói khoá hậu lượng tử do NIST chuẩn hoá) — HKDF trộn cả hai bí mật chung thành khoá phiên duy nhất, sau đó dùng AES-256-GCM. Định danh giao thức `HYBRID-ECDH-P256-ML-KEM-768`. Kẻ tấn công phải bẻ được **cả hai** mới thu được khoá phiên, nên không thuật toán nào riêng lẻ trở thành điểm yếu duy nhất. Thiết kế này dự phòng cho kịch bản "thu thập trước, giải mã sau" khi máy tính lượng tử trở nên khả thi.

Để phân biệt CBC và GCM ở mức payload, payload GCM được tiền tố bằng mã định danh `GCM1`; `decryptPayload` ở Java và `_CryptoSession.decrypt` ở Python tự nhận diện. AES-GCM cung cấp mã hoá có xác thực (AEAD), gộp cả tính bảo mật và tính toàn vẹn trong một thuật toán, loại bỏ rủi ro padding-oracle vốn có ở CBC + MAC riêng.

*(b) Truyền chunk.*

1. `OPEN_UPLOAD` mang thẻ HMAC → storage node xác minh tại chỗ (không cần round-trip về Coordinator). Trường hợp trùng nội dung → tắt nhanh, gọi `notifyUploadComplete` với `dedup:true`.
2. Mỗi chunk: giải mã → kiểm tra `index` và kích thước → kiểm tra SHA-256 của chunk → ghi tệp `chunk_<idx>` → phản hồi `ACK_CHUNK`. Băm theo từng chunk cho phép truyền lại chỉ chunk lỗi.
3. Idempotent: chunk đã tồn tại → phản hồi `duplicate=true` → hỗ trợ tiếp tục (resume) một cách tự nhiên.
4. Máy khách mở tệp gốc một lần rồi dùng `seek` cho từng chunk → tận dụng page cache.
5. SHA-256 toàn tệp tính theo dòng (`_stream_file_sha256`) → bộ nhớ hằng số.
6. **Tối ưu I/O ghi metadata phiên (`saveSessionMeta`).** Tệp `meta.properties` không được ghi sau mỗi chunk; thay vào đó chỉ ghi mỗi 16 chunk và bắt buộc ghi tại chunk cuối:
   ```java
   int recvCount = session.getReceivedCount();
   int totalCount = session.getTotalChunks();
   if (recvCount == totalCount || (recvCount % 16) == 0) {
       fileStore.saveSessionMeta(sessionId, session.toProperties());
   }
   ```
   Với tệp 1 GB (khoảng 2048 chunk × 512 KB), số lần ghi metadata giảm từ 2048 xuống còn 128 lần. Nếu storage node ngừng đột ngột, tối đa chỉ mất 15 chunk tiến độ — máy khách tra cứu các chunk còn thiếu rồi gửi lại. Tại bước FINALIZE, metadata luôn được làm mới do điều kiện `recvCount == totalCount` luôn đúng.

**Lợi ích.** Bộ nhớ hằng số ở cả hai đầu; hỗ trợ tiếp tục; mã hoá theo từng chunk có xác thực; sẵn sàng cho thời kỳ hậu lượng tử; lỗi cục bộ không lan ra toàn bộ luồng; giảm đáng kể số lần fsync trên đĩa cho tệp lớn.

## V.3. FINALIZE — ghép tệp, xác minh băm, commit

**Mô tả nhanh.** Storage node ghép các tệp `chunk_*` thành `assembled`, xác minh SHA-256 trên toàn tệp, gọi quét anti-virus (V.4), atomic-move sang kho lưu trữ theo nội dung.

**Vị trí cụ thể.**
- `ClientHandler.java:443` `handleFinalizeUpload`.
- Ghép tệp: `FileStore.java:155` `assembleTempFile`.
- Xác minh băm: `FileStore.java:173` `verifyAssembledHash`.
- Commit: `FileStore.java:187` `commitAssembledFile` (`moveWithAtomicFallback` dòng 200) → `data/<sha[0..1]>/<sha[2..3]>/<sha>`.

**Logic và lý do thiết kế.**
1. Đảm bảo đơn luồng: `session.tryBeginFinalizing()` ngăn finalize song song.
2. Băm sai → xoá tệp tạm + phản hồi `HASH_MISMATCH` + thông báo `UPLOAD_FAILED`. Không commit tệp bị hỏng.
3. Bắt buộc đi qua cổng anti-virus (V.4).
4. Atomic-move có cơ chế dự phòng: trên Windows giữa hai ổ đĩa D:/C: hoặc giữa các volume khác hệ tệp → quay về move thường hoặc copy+delete.
5. Nếu tệp cùng băm đã tồn tại trong kho → bỏ bản assembled (khử trùng lặp nội bộ node).

**Lợi ích.** Toàn vẹn theo SHA-256; bắt buộc qua anti-virus; lưu trữ theo nội dung kèm khử trùng lặp; commit nguyên tử.

## V.4. CLAMAV SCAN — quét virus (Storage Node ↔ clamd)

**Mô tả nhanh.** Storage node mở kết nối TCP tới container `clamd` cổng `3310`, gửi lệnh `zSCAN <đường_dẫn_tuyệt_đối>\0`, đọc phản hồi một dòng, phân loại → commit / cách ly / từ chối.

**Vị trí cụ thể.**
- Máy khách clamd: `storage-node/.../antivirus/ClamAvClient.java:36` `scan(Path)`.
- Đọc phản hồi (giới hạn 8 KB): `ClamAvClient.java:111` `readResponse`.
- Phân tích phản hồi: `ClamAvClient.java:72` `parseResponse`.
- Tiền-kiểm tra kích thước: `ClientHandler.java:726` `validateScanSize` (sử dụng cấu hình `antivirus.max.scan.bytes`, mặc định 100 MB).
- Khởi tạo bộ quét: `StorageNodeMain.java:58`.
- Cấu hình: `storage-node.properties:15-21` / `.docker.properties:15-21`. Biến môi trường `ANTIVIRUS_*`.
- Container: `docker-compose.yml:113-156`. Cấu hình clamd: `storage-node/antivirus/clamd.conf`.
- Cách ly: `FileStore.java:231` `quarantineFile`. Xử lý kết quả từ chối: `ClientHandler.java:662` `handleScanRejectedUpload`.

**Logic và lý do thiết kế.**
1. Tiền-kiểm tra kích thước: nếu `Files.size() > antivirus.max.scan.bytes` (mặc định 100 MB) → phản hồi `LIMIT_EXCEEDED`, không gọi clamd, tránh chiếm dụng socket lâu khi `MaxThreads` của clamd chỉ là 12.
2. Giao thức `zSCAN` (tiền tố `z` báo hiệu chuỗi kết thúc bằng null): một lệnh đổi lấy một dòng phản hồi, giới hạn 8 KB để ngăn cạn bộ nhớ.
3. Phân loại phản hồi: `CLEAN` → commit; `INFECTED` → cách ly và phản hồi `UPLOAD_FAILED`; `LIMIT_EXCEEDED` / `TIMEOUT` / `UNAVAILABLE` / `ERROR` xử lý theo chính sách.
4. Chính sách fail-closed (`antivirus.fail.closed=true` mặc định): mọi trạng thái khác `CLEAN` đều bị từ chối. Khi clamd ngừng hoạt động, hệ thống không trở thành lỗ hổng anti-virus.
5. Cách ly: tệp được chuyển sang `data/quarantine/<sessionId>_<sha>.blocked` kèm `.metadata.json` ghi đầy đủ vật chứng.
6. Phản hồi cho máy khách: `FINALIZE_RESP{status = VIRUS_DETECTED / SCAN_LIMIT_EXCEEDED / SCAN_TIMEOUT / SCAN_UNAVAILABLE / SCAN_ERROR}`.
7. Storage node và clamd chia sẻ volume vì `zSCAN` truyền đường dẫn → clamd quét trực tiếp inode, tiết kiệm hơn so với chế độ `INSTREAM`.

**Lợi ích.** Cổng anti-virus đặt trước bước commit; tiền-kiểm tra ngăn tấn công từ chối dịch vụ bằng tệp quá lớn; bản cách ly có thể kiểm toán; fail-closed mặc định.

## V.5. UPLOAD_COMPLETE / UPLOAD_FAILED — kênh phản hồi qua socket bền vững (cổng `8081`)

**Mô tả nhanh.** Storage Node duy trì một kết nối TCP bền vững tới Coordinator để báo cáo kết quả tải lên.

**Vị trí cụ thể.**
- Phía storage node: `.../network/CoordinatorClient.java:138` `notifyUploadComplete`, `:159` `notifyUploadFailed`. Socket: `ControlPlaneClient`.
- Phía Coordinator: `storage_node_server.py:32`. Handler dòng 81–88.
- Xử lý DB: `upload_service.py:411` `handle_upload_complete` / `:617` `handle_upload_failed`.

**Logic và lý do thiết kế.**
1. Giải phóng slot luôn theo `file_id` (`_release_slot(file_id)`); không cần round-trip để tra token.
2. Kiểm tra `storage_node_id` khớp và băm khớp trước khi đánh dấu `READY`. Nếu sai → đánh dấu `DELETED` + ghi nhật ký kiểm toán + phát sự kiện `FILE_DELETED`.
3. Khi đánh dấu `READY` → phát sự kiện `NEW_FILE` (mục VIII).

**Lợi ích.** Một định danh xuyên suốt vòng đời tải lên; không bị lệch slot; tránh trạng thái `UPLOADING` treo vô thời hạn.

## V.6. CREATE_SHARE_TOKEN — sinh liên kết chia sẻ ngoài phòng

**Mô tả nhanh.** Thành viên phòng sinh token chia sẻ có `max_downloads` và `expires_at` để chia sẻ tệp ra ngoài phòng.

**Vị trí cụ thể.**
- Handler: `client_socket_server.py:367` `_handle_create_share_token`.
- Service: `coordinator-server/download/download_service.py:230` `create_share_token`.

**Logic và lý do thiết kế.** Xác minh quyền (thành viên phòng chứa tệp hoặc ADMIN), INSERT bản ghi `share_tokens(token, file_id, max_downloads, expires_at, download_count=0)`. Token chính là liên kết chia sẻ. Việc kiểm tra hợp lệ được thực hiện ở `handle_init_download_share` (VI.1).

**Lợi ích.** Chia sẻ tức thời không cần kết nạp thành viên; hạn ngạch ngăn lạm dụng.

---

# VI. LUỒNG TẢI XUỐNG (DOWNLOAD)

## VI.1. INIT_DOWNLOAD — khởi tạo phiên tải xuống

**Mô tả nhanh.** Có hai đường vào: token xác thực người dùng thông thường, hoặc token chia sẻ có hạn ngạch.

**Vị trí cụ thể.**
- Đường xác thực: `download/download_service.py:81` `handle_init_download_direct`.
- Đường chia sẻ: `:329` `handle_init_download_share` (UPDATE nguyên tử bảng `share_tokens` để tăng biến đếm và kiểm tra hạn ngạch).

**Logic và lý do thiết kế.**
1. Đường xác thực: kiểm tra quyền `DOWNLOAD_FILE`.
2. Đường chia sẻ: UPDATE nguyên tử với điều kiện `download_count < max_downloads AND expires_at > NOW()`. Vượt quá hạn ngạch → từ chối.
3. Phân giải một node ở trạng thái khoẻ; nếu không có → trả `STORAGE_NODE_UNAVAILABLE`.
4. Sinh thẻ HMAC theo cùng định dạng với tải lên.

**Lợi ích.** Tách kênh chia sẻ liên kết khỏi đường xác thực chính; hạn ngạch ngăn lạm dụng.

## VI.2. DOWNLOAD CHUNK — kéo dữ liệu thực

**Mô tả nhanh.** Máy khách gửi `OPEN_DOWNLOAD` kèm thẻ HMAC, sau đó gửi `REQUEST_CHUNK` theo từng index (cho phép không tuần tự). Storage node trả `DOWNLOAD_CHUNK` đọc từ `data/<sha>`. Máy khách ghi theo dòng + SHA-256 luân chuyển, xác minh băm tổng ở cuối.

**Vị trí cụ thể.**
- Phía máy khách: `coordinator-node/network/storage_node_data_plane.py:421` `download_file`.
- Phía storage node: `ClientHandler.java:553` `handleOpenDownload`, `:595` `handleRequestChunk`. Đọc chunk: `FileStore.java:307` `readStoredChunk`.
- Trạng thái phiên tải: `storage-node/.../session/DownloadSession.java`.

**Logic và lý do thiết kế.**
1. Xác minh HMAC tại chỗ → tạo `DownloadSession`.
2. Không tuần tự: `REQUEST_CHUNK` theo index tuỳ ý → sẵn sàng cho kéo song song.
3. Băm theo từng chunk + băm toàn tệp luân chuyển. Băm tổng không khớp → `os.remove(target)`.
4. Phải nhận được `DOWNLOAD_COMPLETE`; nếu không sẽ ghi cảnh báo về một phiên truyền đáng ngờ.
5. **Đảm bảo phát `DOWNLOAD_COMPLETE` đúng một lần.** Trong `handleRequestChunk` (`ClientHandler.java:686`), việc đánh dấu chunk đã gửi và kiểm tra "vừa hoàn tất" được gộp vào một phương thức nguyên tử (đồng bộ hoá) trên `DownloadSession`:
   ```java
   boolean justCompleted = session.markChunkSentAndCheckJustCompleted(chunkIndex);
   if (justCompleted) {
       // gửi DOWNLOAD_COMPLETE
   }
   ```
   `DownloadSession.markChunkSentAndCheckJustCompleted(int)` (`DownloadSession.java:78`) là phương thức `synchronized` — thao tác đánh dấu chunk và kiểm tra vừa-hoàn-tất nằm trong cùng một critical section. Mặc dù hiện tại mỗi kết nối tải xuống xử lý tuần tự, thiết kế cho phép kéo song song nhiều chunk, do đó loại bỏ điều kiện tranh chấp ngay từ đầu.

**Lợi ích.** Không đi qua Coordinator; bộ nhớ hằng số; toàn vẹn hai lớp; sẵn sàng cho kéo song song; máy khách không bao giờ nhận trùng thông điệp `DOWNLOAD_COMPLETE`.

---

# VII. LUỒNG VẬN HÀNH CỤM STORAGE NODE

## VII.1. STORAGE_AUTH, HEARTBEAT và CAPACITY

**Mô tả nhanh.** Storage Node gửi `STORAGE_AUTH` (bí mật chia sẻ + `freeBytes`) khi kết nối, sau đó gửi `PING` mỗi 30 giây kèm `freeBytes` mới.

**Vị trí cụ thể.**
- Phía gửi: `.../network/ControlPlaneClient.java:119` (AUTH), `:191` `sendPing`.
- Phía nhận AUTH: `storage_node_server.py:197` `_handle_storage_auth` (dòng 302–311 `registry.update_capacity`).
- Phía nhận PING: `:365` `_handle_ping` (dòng 390–403 `registry.heartbeat(connection, free_bytes=...)`).
- Theo dõi sức khoẻ: `storage_node_server.py:118` `_health_check_loop`.

**Logic và lý do thiết kế.**
1. Dung lượng được truyền ngay tại bước AUTH → từ `INIT_UPLOAD` đầu tiên đã có dữ liệu dung lượng đầy đủ.
2. Dung lượng cập nhật mỗi `PING` → làm mới liên tục; nếu thiếu trường → giữ giá trị cũ.
3. Timeout mặc định 90 giây → đánh dấu node là không khoẻ, không chọn cho tải lên.

**Lợi ích.** Bộ cân bằng tải có dữ liệu cập nhật; phát hiện node mất kết nối trong tối đa 90 giây.

## VII.2. CÂN BẰNG TẢI — chọn node (P2C + TTL của reservation + dung lượng)

**Mô tả nhanh.** Thuật toán Power of Two Choices (P2C) + lọc theo `min_free_bytes` + đặt trước slot nguyên tử có TTL.

**Vị trí cụ thể.**
- `storage_node/registry.py:197` `select_for_upload`.
- Lọc dung lượng: `:277` `_has_enough_capacity` (biến môi trường `STORAGE_MIN_FREE_BYTES`).
- Tính điểm: `:292` `_upload_score`.
- Giải phóng idempotent: `:254` `release_reservation`.
- Thu hồi theo TTL: `:304` `_reap_expired_locked`.
- Cấu hình TTL: `config.py:46` `upload_slot_ttl_seconds` (biến môi trường `UPLOAD_SLOT_TTL_SECONDS`, mặc định 60).

**Logic và lý do thiết kế.**
1. Lọc dung lượng: nếu `min_free_bytes > 0` thì node có `free_bytes < threshold` sẽ bị loại. Giá trị `None` được coi là đủ — bảo đảm tương thích ngược.
2. Tính điểm P2C: bộ ba `(active_uploads, -free_bytes, node_id)`. P2C ngăn hiện tượng "herd" — nhiều coordinator hoặc nhiều luồng cùng phát hiện một node ít tải nhất sẽ không đồng thời định tuyến vào node đó.
3. TTL của reservation: nếu máy khách mất kết nối → slot được thu hồi mỗi lần gọi `select_for_upload`.
4. `release_reservation` idempotent → gọi nhiều lần không gây tác động phụ.

**Lợi ích.** Cân tải đồng thời theo tải hiện tại và dung lượng; tự phục hồi khi máy khách lỗi; mở rộng quy mô ổn định.

## VII.3. ĐỐI CHIẾU — DB ↔ manifest

**Mô tả nhanh.** Khi `MANIFEST_DELTA` đến → đối chiếu với DB: tệp `READY` được gán cho node nhưng vắng mặt trong manifest → đánh dấu `MISSING`.

**Vị trí cụ thể.**
- `storage_node/reconciliation_service.py:22` `reconcile_node`.
- Gọi từ `storage_node_server.py:633` `_handle_manifest_delta`.

**Logic và lý do thiết kế.** Manifest là nguồn sự thật trên đĩa. Vắng mặt = tệp đã bị mất → đánh dấu sớm để máy khách không cố tải tệp không tồn tại.

**Lợi ích.** Phát hiện lệch trạng thái giữa control plane và data plane; phát tín hiệu để quản trị viên sao chép lại.

---

# VIII. LUỒNG ĐẨY SỰ KIỆN TỚI MÁY KHÁCH (cổng `8082`)

## VIII.1. SUBSCRIBE_ROOM / UNSUBSCRIBE_ROOM

**Mô tả nhanh.** Máy khách thông báo cho Coordinator về các phòng muốn nhận sự kiện. Coordinator lưu ánh xạ `room_id → {connection}`.

**Vị trí cụ thể.**
- Handler: `client_socket_server.py:399` `_handle_subscribe_room`, `:412` `_handle_unsubscribe_room`.
- Lưu ánh xạ: `notification_service.py:19` `add_subscriber`, `:34` `remove_subscriber`.

**Logic và lý do thiết kế.** Xác minh là thành viên phòng trước khi đăng ký. Dọn dẹp ánh xạ khi kết nối đóng (`_on_connection_closed` → `remove_subscriber_from_all_rooms`).

**Lợi ích.** Đẩy sự kiện chỉ tới người liên quan; không phát tán tới đối tượng không cần thiết.

## VIII.2. PHÁT SỰ KIỆN

**Mô tả nhanh.** Coordinator đẩy sự kiện đa hướng: `NEW_FILE`, `FILE_DELETED`, `MEMBER_ADDED` / `MEMBER_REMOVED`, `ROLE_UPDATED`.

**Vị trí cụ thể.**
- Lõi: `notification/notification_service.py:75` `_broadcast_event`.
- Theo loại: `:121` `broadcast_member_added`, `:148` `broadcast_member_removed`, `:172` `broadcast_role_updated`, `:199` `broadcast_file_deleted`, `:226` `broadcast_new_file`.
- Kích hoạt `NEW_FILE`: `upload_service.py:569`. `FILE_DELETED`: `upload_service.py:544-553`, `file_service.delete_file`.

**Logic và lý do thiết kế.**
1. Ánh xạ sử dụng `threading.Lock` để xử lý đồng thời.
2. Gửi thất bại → gỡ kết nối khỏi mọi phòng → tránh tích tụ socket chết.
3. Tách kênh đẩy khỏi request/response → tránh head-of-line blocking.

**Lợi ích.** Giao diện cập nhật thời gian thực; không phải thăm dò định kỳ cơ sở dữ liệu.

---

# IX. LUỒNG KIỂM TOÁN VÀ GIÁM SÁT

## IX.1. NHẬT KÝ KIỂM TOÁN — ghi nhận mọi hành động

**Mô tả nhanh.** Mọi service trọng yếu đều gọi `write_audit_log` sau khi hoàn thành thao tác: SIGNUP, LOGIN, LOGOUT, CREATE_ROOM, ADD_MEMBER / REMOVE_MEMBER, SET_ROLE, UPLOAD, DOWNLOAD, DELETE_FILE, STORAGE_AUTH (cả thành công, thất bại lẫn ngắt kết nối), STORAGE_NODE_MISMATCH, HASH_MISMATCH, VIRUS_DETECTED. Dữ liệu ghi vào bảng `audit_logs` với trường `detail` kiểu JSONB.

**Vị trí cụ thể.** `audit/audit_service.py:23` `write_audit_log`.

**Logic và lý do thiết kế.**
1. Schema: `actor_id, action, target_type, target_id, room_id, detail JSONB, status, created_at`.
2. Trường `detail` kiểu JSONB → linh hoạt (mỗi hành động có cấu trúc riêng) mà vẫn truy vấn được bằng các toán tử JSON của PostgreSQL.
3. INSERT đồng bộ — đảm bảo nhật ký luôn được ghi trước khi trả về (không dùng bất đồng bộ để tránh mất sự kiện khi tiến trình ngừng đột ngột).
4. Ghi cả SUCCESS lẫn FAILED → có dữ liệu truy vết hành vi lạm dụng và lệch trạng thái.
5. Storage Node là thành phần đặc quyền, do đó mọi sự kiện `STORAGE_AUTH` thành công, thất bại và ngắt kết nối đều được ghi lại để có lịch sử kết nối phục vụ điều tra cụm.
6. Lỗi khi ghi nhật ký không làm thất bại nghiệp vụ chính (bọc try/catch).

**Lợi ích.** Phục vụ điều tra sự cố và pháp y bảo mật; quản trị viên truy vết sự cố hệ thống; có dữ liệu phát hiện hành vi bất thường.

## IX.2. SỨC KHOẺ — PING và STATUS

**Mô tả nhanh.** Máy khách hoặc hệ thống giám sát gọi `PING` để kiểm tra trạng thái sống, `STATUS` để lấy chi tiết Postgres + Redis + storage nodes + ảnh chụp các nhóm luồng + thời gian hoạt động.

**Vị trí cụ thể.**
- Handler: `client_socket_server.py:427` `_handle_ping`, `:440` `_handle_status`.
- Service: `health/health_service.py:41` `ping`, `:55` `get_status`.
- Các phép kiểm tra thành phần: `:98` `_check_postgres`, `:128` `_check_redis`, `:155` `_check_storage_nodes`.
- Ảnh chụp nhóm luồng: `:85` `_thread_snapshot` (gộp theo tiền tố tên: acceptor / worker / cleanup / healthcheck).

**Logic và lý do thiết kế.**
1. `ping` nhẹ, phù hợp cho probe của bộ cân bằng tải hoặc kiểm tra sẵn sàng của Kubernetes.
2. `STATUS` đầy đủ cho dashboard: độ trễ Postgres, độ trễ Redis, danh sách storage node kèm trạng thái khoẻ, thời gian hoạt động, số lượng luồng theo nhóm.
3. Mỗi phép kiểm tra có timeout độc lập — Postgres chậm không kéo theo Redis.

**Lợi ích.** Quan sát toàn hệ thống; chẩn đoán sự cố nhanh; tích hợp được với hệ thống giám sát bên ngoài.

---

# X. LUỒNG NỀN (BACKGROUND MAINTENANCE)

## X.1. CLEANUP ORPHANED UPLOADS — dọn các phiên tải lên dang dở

**Mô tả nhanh.** Một luồng nền chạy mỗi 10 phút đánh dấu `DELETED` cho các bản ghi đang ở trạng thái `UPLOADING` quá 35 phút, đồng thời giải phóng slot dựa trên `file_id`. "Orphan" ở đây là phiên tải lên sẽ không bao giờ được hoàn tất (máy khách ngừng hoạt động, thẻ HMAC hết hạn, Storage Node mất kết nối).

**Vị trí cụ thể.**
- `cleanup/cleanup_service.py:68` `cleanup_orphaned_uploads`.
- Khởi tạo: `main.py:156` (`interval_seconds = 600`).

**Logic và lý do thiết kế.**
1. Ngưỡng 35 phút lớn hơn TTL của thẻ HMAC (30 phút) → không chiếm dụng thẻ vẫn còn hạn.
2. Câu truy vấn: `UPDATE files SET status='DELETED' WHERE status='UPLOADING' AND created_at < NOW() - INTERVAL '35 minutes' RETURNING id, storage_node_id`.
3. Phát hiện API có sẵn (`hasattr` tại dòng 104):
   - API mới: `release_reservation(file_id)` idempotent (slot thường đã được thu hồi theo TTL, đây là biện pháp dự phòng kép).
   - API cũ (test fakes): `mark_upload_finished(node_id)`.
4. Không tác động đến tệp vật lý — `FileStore.cleanSessionDir` ở Java đảm nhận việc này.

**Lợi ích.** Cơ sở dữ liệu không bị tồn đọng trạng thái `UPLOADING`; số phiên bản không bị mất; tên tệp trong phòng không bị khoá vĩnh viễn.

---

# PHỤ LỤC: TỔNG KẾT CỔNG I/O

| Cổng | Máy | Hướng | Mục trong báo cáo |
|------|-----|-------|-------------------|
| 8080 | Coordinator | Máy khách → Server | II.1–4, III.1–5, IV.1–4, V.1, V.6, VI.1, VIII.1, IX.2 |
| 8081 | Coordinator | Storage Node ↔ Server (kết nối bền vững) | V.5, VII.1, VII.3 — STORAGE_AUTH + `freeBytes`, PING + `freeBytes`, UPLOAD_COMPLETE / FAILED, MANIFEST_DELTA |
| 8082 | Coordinator | Server → Máy khách (đẩy sự kiện) | VIII.2 — EVENT |
| 9001+ | Storage Node | Máy khách ↔ Storage Node | V.2–3, VI.2 — OPEN / UPLOAD_CHUNK / FINALIZE / DOWNLOAD_CHUNK |
| 3310 | container clamd | Storage Node → clamd | V.4 — `zSCAN <path>\0` |
| 5432 | PostgreSQL | Server → DB | mọi mục — `users, rooms, room_members, files, share_tokens, audit_logs` |
| 6379 | Redis | Server → cache | II.2–4, V.1, VI.1 — phiên token, TTL thẻ HMAC cho tải lên/tải xuống |

**Đặc tính chung của thiết kế I/O.**
- Phân tách rõ control plane (8080 / 8081 / 8082) và data plane (9001+ / 3310): tệp lớn không đi qua Coordinator, tránh nút cổ chai.
- Bộ nhớ hằng số: đọc/ghi theo dòng, SHA-256 luân chuyển ở cả hai đầu.
- Thẻ HMAC không cần round-trip: Storage Node tự xác minh tại chỗ.
- Toàn vẹn dữ liệu hai lớp: băm theo từng chunk + băm toàn tệp.
- Quét anti-virus bắt buộc, fail-closed, bản cách ly có metadata kiểm toán.
- Hỗ trợ tiếp tục và idempotent: chunk trùng → ACK; finalize đơn luồng; `release_reservation` idempotent; logout idempotent.
- Mã hoá theo lai (hybrid) ECDH P-256 + ML-KEM-768 + AES-256-GCM cho dữ liệu data-plane, dự phòng cho thời kỳ hậu lượng tử.
- Nhật ký kiểm toán đồng bộ → không mất sự kiện khi tiến trình ngừng đột ngột; phục vụ điều tra pháp y.
- Phân quyền tập trung trong ma trận của `authorization_service`; mọi handler đều đi qua `auth_middleware`.

---

**Kết thúc tài liệu.**
