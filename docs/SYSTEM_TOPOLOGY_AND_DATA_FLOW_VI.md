# TỔNG QUAN KIẾN TRÚC (TOPOLOGY) VÀ LUỒNG DỮ LIỆU (DATA FLOW)

Tài liệu này tổng hợp cấu trúc mạng luân chuyển dữ liệu chính (Topology) và các luồng tương tác quan trọng (Data flow) của toàn bộ hệ thống "LAN Secure File System".

---

## 1. KIẾN TRÚC TỔNG THỂ (SYSTEM TOPOLOGY)

Hệ thống được thiết kế theo mô hình phân tách **Control Plane** (Điều khiển) và **Data Plane** (Dữ liệu) nhằm tối ưu hóa đường truyền file có dung lượng lớn và giảm tải cho máy chủ điều phối.

### Sơ đồ Topology

- **Client Tier**: Bao gồm Client / Frontend. Giao tiếp qua các luồng độc lập:
  - Kết nối đến Coordinator qua Cổng 8080 (Auth, File Meta, Init) và 8082 (Notifications/Events).
  - Kết nối trực tiếp đến Storage Nodes qua Cổng 9001, 9002... để lấy và đẩy trực tiếp (Upload/Download) Data Chunks.
- **Control Plane**: Bao gồm Coordinator Server (Python).
  - Tương tác với PostgreSQL (lưu Metadata, Users, Rooms) và Redis Cache (lưu Tokens, Sessions).
  - Lắng nghe Storage Nodes duy trì "Persistent Socket" qua Cổng 8081 (Heartbeat và luồng trạng thái).
- **Data Plane (Storage Nodes)**: Nhiều trình nền viết bằng Java phân tán, phụ trách đọc ghi trực tiếp File System dạng Chunks và Metas.
  - Lắng nghe Client qua port 9001...
  - Giao tiếp ngược báo cáo cho Coordinator qua Cổng 8081.

### Các thành phần chính

1.  **Coordinator Server (Control Plane - Python):**
    *   Cổng giao tiếp mặc định: `:8080` (Client), `:8081` (Storage Node), `:8082` (Notifications).
    *   Nhiệm vụ: Quản lý Authentication (Redis token), Authorization (Quyền truy cập phòng, chia sẻ file bằng share token), Metadata file (PostgreSQL).
    *   **Không** lưu trữ nội dung file thực tế, chỉ cấp "Sổ thông hành" (HMAC Ticket) cho Client tiếp cận Data Plane.
2.  **Storage Node (Data Plane - Java):**
    *   Cổng giao tiếp mặc định: `:9001`, `:9002`...
    *   Nhiệm vụ: Lắng nghe kết nối TCP Socket trực tiếp từ Client để xử lý UPLOAD / DOWNLOAD từng Chunk (Mã hoá RSA + AES, toàn vẹn SHA-256).
    *   Duy trì `Persistent Socket` thông qua `:8081` tới Coordinator để cập nhật trạng thái (UPLOAD_COMPLETE, UPLOAD_FAILED) một cách bất đồng bộ.
3.  **Hạ tầng bổ trợ:**
    *   **PostgreSQL:** Nơi chứa thông tin lâu dài (Users, Rooms, Roles, File Metadata, Audit logs).
    *   **Redis:** Bộ đệm tốc độ cao cho Session Tokens, Share Tokens có giới hạn thời gian (TTL).

---

## 2. MAIN DATA FLOW: KHỞI TẠO & UPLOAD FILE

Quá trình tải lên sử dụng cơ chế **Zero Round-Trip Verification**, Client tải file lên Storage Node bằng Ticket được kí điện tử từ Coordinator (Storage Node có thể tự kiểm chứng Ticket thông qua shared secret thay vì hỏi lại Coordinator liên tục).

### Sơ đồ Upload Flow

**Các bước diễn ra:**
1. **Khởi tạo Upload (Control Plane)**: Client gửi `INIT_UPLOAD` (gồm RoomID, Kích thước, Hash, Token) tới Coordinator (Socket 8080).
2. **Kiểm tra và Cấp vé**: Coordinator kiểm tra quyền hạn, không gian trống, thực hiện check-trùng-lặp (Deduplication) và chuyển file trong DB sang trạng thái `UPLOADING`. Coordinator trả về `UPLOAD_PLAN` gồm một vé HMAC Ticket đã tự kí số, và IP/Port của Storage Node mục tiêu.
3. **Mở luồng Tải (Data Plane)**: Client mở kết nối thẳng tới Storage Node chỉ định (Socket 9001), gửi `OPEN_UPLOAD` có kèm HMAC Ticket. Storage Node dùng Shared Secret để tự xác thực bé bị giả mạo hay thâm hụt (local verify) mà không cần hỏi lại Coordinator, và phản hồi `OPEN_UPLOAD_RESP`.
4. **Luân chuyển Chunks**: Client lặp lại quá trình băm file và gửi từng packet `UPLOAD_CHUNK` mã hóa (cùng Index chunk). Storage Node liên tục phản hồi `ACK_CHUNK`.
5. **Chốt hạ file (Finalize)**: Sau khi đủ, Client gửi `FINALIZE_UPLOAD`. Storage Node tiến hành ráp file, kiểm tra SHA-256 tổng thể. Nếu an toàn, nó báo về `FINALIZE_RESP` với cờ hiệu 'Thành công' (hoặc 'IO Error', 'Hash Mismatch').
6. **Đồng bộ hóa với Coordinator**: (Sự kiện bất đồng bộ) Thông qua Socket 8081 Persistent, Storage Node gọi ngầm `UPLOAD_COMPLETE` hoặc `FAILED` báo Coordinator biết đường cập nhật trạng thái Database thành `READY` hay `DELETED`.
7. **Truyền bá Server Events**: Coordinator broadcast sự kiện `NEW_FILE` đến cộng đồng thành viên room qua thông báo Socket nhánh 8082.

---

## 3. MAIN DATA FLOW: TẢI FILE (DOWNLOAD)

Tuơng tự Upload, quy trình tải xuống cũng được thực hiện trực tiếp giữa Client và Storage Node nhằm truyền file kích cỡ lớn nhanh nhất, không làm nghẽn cổ chai tại máy chủ Coordinator.

### Sơ đồ Download Flow

**Các bước diễn ra:**
1. **Khởi tạo Download (Control Plane)**: Client yêu cầu tải bằng lệnh `INIT_DOWNLOAD` (mang theo FileID và Auth Token hoặc Share Token) tới Coordinator (Socket 8080).
2. **Xét quyền và Cấp vé**: Coordinator kiểm tra quyền truy vấn, nếu Client xài Share Token nó sẽ tự trừ quota đi 1 lượt. Sau đó Coordinator cấp `DOWNLOAD_PLAN` giao Ticket bảo mật HMAC, kích cỡ tổng, chunk size và báo tên Storage Node đang cầm data đó.
3. **Mở luồng Nhận (Data Plane)**: Client đâm chốt cửa thẳng vào Storage Node được thả link, dùng `OPEN_DOWNLOAD` đi vào nộp Ticket. Storage cũng tự thẩm định lại mã HMAC và trả lại `OPEN_DOWNLOAD_RESP`.
4. **Kéo Chunks về**: Xong thủ tục, Client liên tục dội bom `REQUEST_CHUNK` cho tuỳ ý số Index của file (được quyền tuỳ biến thứ tự lấy - tải out-of-order). Storage node chỉ phục vụ bằng các lệnh `DOWNLOAD_CHUNK` trút về.
5. **Hoạch định Hoàn thành**: Khi Storage Node nhận thấy nó đã trút đủ tổng số khối cho ID Phiên đó, tự động tuôn `DOWNLOAD_COMPLETE` bế mạc kết nối, chấm dứt việc chiếm dụng Data Plane.

---

## 4. TÓM TẮT ĐẶC TÍNH BẢO MẬT & ĐIỀU PHỐI

1. **Kháng nghẽn thắt cổ chai (Decentralized Bottleneck):** Coordinator không bao giờ chạm vào Byte thực của file. 100% băng thông nặng được gánh bởi giao tiếp phân tán từ Client -> Nhiều Storage Nodes.
2. **Xác thực phi tập trung (Decentralized Auth with HMAC):** Storage node không cần "gọi điện" hỏi Coordinator với mỗi chunk upload, tự nó thẩm định bằng Ticket nội bộ.
3. **Mã hoá (E2E / Transport Level Encryption):**
    * Bootstrapping Public Key bằng RSA để trao đổi AES Session Key.
    * Mọi chunk transfer đều được mã hoá bảo mật qua mạng LAN.
4. **Deduplication toàn vẹn (File deduplication):** Nếu file `.mp4` 2GB được người thứ 2 tải lên với cùng SHA256, Coordinator lập tức trả về file ảo trỏ cùng meta, không tốn thêm byte lưu trữ vật lý hay lưu lượng mạng.
