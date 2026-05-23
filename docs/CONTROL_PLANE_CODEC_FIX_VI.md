# Báo cáo: Sửa Control-Plane giữa Storage Node (Java) và Coordinator (Python)

## 1. Bối cảnh

Hệ thống tách hai mặt phẳng truyền tin:

- **Data plane**: Client ↔ Storage Node (Java). Truyền nội dung file theo
  chunk, có hỗ trợ đính kèm payload nhị phân.
- **Control plane**: Storage Node ↔ Coordinator. Trao đổi thông điệp điều khiển
  thuần JSON: xác thực node, đồng bộ manifest, báo upload xong, heartbeat.

Hai mặt phẳng tuy cùng dùng TCP nhưng **khung tin (wire frame) khác nhau** vì
mục đích sử dụng khác nhau.

## 2. Vấn đề

### 2.1 Lệch định dạng khung tin trên control plane

Coordinator (Python) và Storage Node (Java) ngầm dùng hai định dạng đóng gói
khác nhau cho cùng một kênh control plane:

- **Python kỳ vọng**: gói tin = độ-dài + một khối JSON duy nhất chứa
  `{type, payload, requestId}`.
- **Java đang gửi**: gói tin = phần "header" JSON phẳng + phần "data" nhị phân
  (giống hệt format data plane).

Hệ quả: ngay từ bước STORAGE_AUTH, Coordinator không parse nổi khung tin của
Java; mọi thông điệp tiếp theo (UPLOAD_COMPLETE, MANIFEST_DELTA, PING/PONG)
đều không lan truyền được.

### 2.2 Lỗi tên phương thức khi dọn dẹp kết nối client

Khi một kết nối client đóng (cả khi client thật ngắt lẫn khi healthcheck của
Docker mở rồi đóng socket), Coordinator gọi nhầm một phương thức không tồn tại
trong dịch vụ thông báo (`NotificationService`). Mỗi lần như vậy log đều bắn
exception, gây nhiễu và che các sự cố thật.

## 3. Giải pháp ở tầng khái niệm

### 3.1 Codec riêng cho control plane

Thêm một bộ codec mới phía Java **chuyên cho control plane**, nói đúng "ngôn
ngữ" mà Python kỳ vọng:

- Khi gửi: dồn toàn bộ trường nghiệp vụ vào `payload`, nâng `requestId` lên
  cấp envelope, viết duy nhất một khối JSON kèm độ dài.
- Khi nhận: gỡ ngược lại để các tầng phía trên (đã viết theo mô hình "header
  phẳng") không phải sửa.

Có hai trường hợp đặc biệt cần xử lý tinh:

1. **Envelope lỗi** của Python (`error: {code, message}`) được trải phẳng
   thành `code`/`message` để code Java cũ đọc được như trước.
2. **Lỗi dạng chuỗi đơn** (ví dụ TICKET_INVALID có `error: "..."`) được giữ
   nguyên ở dạng chuỗi, không bị nhầm sang envelope.

Data-plane codec cũ **giữ nguyên** vì kênh client ↔ storage node không thay
đổi — tránh tạo lỗi phụ phía client.

### 3.2 Gọi đúng phương thức dọn dẹp subscription

Đổi điểm gọi nhầm sang đúng API của `NotificationService` (gỡ kết nối khỏi mọi
phòng nó đang subscribe). Vì Dockerfile của coordinator copy mã nguồn lúc
build, fix yêu cầu **rebuild image** chứ không chỉ restart.

## 4. Ảnh hưởng

| Khả năng                                | Trước fix                       | Sau fix                |
| --------------------------------------- | ------------------------------- | ---------------------- |
| Storage Node xác thực với Coordinator   | Thất bại ngay                   | OK                     |
| Coordinator nhận manifest ban đầu       | Không nhận                      | Nhận, dùng đối soát    |
| Đối soát DB ↔ disk (reconciliation)     | Không chạy                      | Chạy đúng              |
| Heartbeat PING/PONG                     | Không thông                     | Thông; vượt mốc 90s    |
| Báo upload xong → file chuyển READY     | Không xảy ra                    | Xảy ra tức thì         |
| Đồng bộ manifest delta sau mỗi upload   | Không xảy ra                    | Xảy ra                 |
| Log Coordinator khi đóng kết nối client | Exception lặp ở mỗi healthcheck | Sạch                   |

## 5. Xác minh

Đã chạy stack thật bằng `docker compose`:

1. Sau khởi động: Node xác thực thành công, manifest về tới Coordinator,
   reconciliation chạy không lỗi, heartbeat sống ổn định.
2. Mô phỏng một upload đầy đủ qua data plane:
   client → `OPEN_UPLOAD` → `UPLOAD_CHUNK` → `FINALIZE_UPLOAD` trên port
   data plane của storage node. Sau đó node tự động gửi `UPLOAD_COMPLETE` và
   `MANIFEST_DELTA` lên Coordinator qua codec mới.
   - Coordinator log: `UPLOAD_COMPLETE received`, `Upload completed`,
     `Broadcasting NEW_FILE`, `MANIFEST_DELTA applied: +1 -0`.
   - DB chuyển trạng thái file: `UPLOADING → READY`.
3. Sau fix dọn dẹp subscription: không còn exception trong log
   coordinator qua nhiều chu kỳ healthcheck.

Trường hợp `VERIFY_TICKET` (Storage Node yêu cầu Coordinator xác minh ticket
qua mạng) **không được kích hoạt trong luồng hiện tại** — xác minh ticket đang
chạy cục bộ bằng HMAC. Đây là thiết kế hiện hữu, không phải hệ quả của fix;
khi nào bật chế độ xác minh từ xa, codec mới đã sẵn sàng phục vụ.

## 6. Bài học rút ra

- Khi cùng một kênh TCP phục vụ hai mục đích khác nhau (điều khiển vs dữ
  liệu), **tách codec rõ ràng** giúp tránh "vô tình tái sử dụng" làm lệch
  giao thức.
- Hợp đồng giao tiếp (envelope shape) cần là tài liệu **bắt buộc đọc** ở cả
  hai phía; ở đây hai bên cùng dùng JSON khiến lỗi không lộ ra cho đến lúc
  parse.
- Healthcheck Docker mở/đóng socket liên tục là một "stress test miễn phí"
  cho code đường-đóng-kết-nối; nên dùng nó như chỉ báo regression.
