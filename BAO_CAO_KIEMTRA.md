# BÁO CÁO KIỂM TRA & BỔ SUNG THANH TIẾN ĐỘ

## 1. Môi trường kiểm tra

Việc kiểm tra chạy trong sandbox Linux **không có Docker, Maven/javac, PostgreSQL, Redis**. Vì vậy không thể dựng full stack nhiều container hay mở GUI tại đây. Những gì đã chạy được tại chỗ: bộ unit test Python, kiểm tra cú pháp/import toàn bộ mã, đối chiếu các bản vá đã khai báo với mã nguồn thật, kiểm tra cấu trúc Java, và test end-to-end phần truyền dữ liệu của thanh tiến độ. Phần demo end-to-end thật (Docker + GUI) cần chạy trên máy Windows của nhóm — xem mục 6.

## 2. Kết quả kiểm tra

Hệ thống về cơ bản lành mạnh. Cụ thể:

- **114/114 unit test** của coordinator-server PASS (protocol codec, authorization matrix, storage-node registry, ticket handlers, notification, reconciliation, client socket server).
- **Bcrypt (C10)** test runtime PASS: mật khẩu đúng verify được, sai bị từ chối, và va chạm 72-byte đã bị chặn.
- **127 file Python** (server + client) biên dịch sạch, không lỗi cú pháp.
- **29 file Java** cân bằng `{}` và `()`; tất cả các bản vá Java đã khai báo (C6–C9, M13, M19, M20, M22, M23) đều có mặt trong mã.
- Đối chiếu `BAO_CAO_FIX.md`: các fix Critical C1–C5, C10–C12 và các fix Medium M3, M4, M11, M31 đều **có thật** trong mã nguồn.

## 3. Bug MỚI phát hiện và đã sửa

**`coordinator-node/ui/widgets/top_bar.py` — lỗi cú pháp làm sập toàn bộ client (Critical).**
Sau dòng `__all__ = ["TopBar"]` còn sót một đoạn mã thừa (tàn dư của một lần chỉnh sửa hỏng), gây `IndentationError` ngay khi import. Vì `top_bar` được import bởi app shell, **client sẽ không khởi động được**. Đã xóa đoạn rác; file biên dịch sạch trở lại. Đây là bug chặn demo, không nằm trong báo cáo bug cũ.

## 4. Tính năng mới: thanh tiến độ upload/download

Bổ sung thanh trạng thái hiển thị **phần trăm + thanh bar + tốc độ (MB/s) + thời gian còn lại (ETA) + dung lượng đã/tổng**, cho **cả upload và download**.

Cách hoạt động: tầng data-plane (`storage_node_data_plane.py`) phát tiến độ sau mỗi chunk dưới dạng `(chunk hiện tại, tổng chunk, byte đã truyền, tổng byte)`. Ở UI (`room_page.py`), mỗi worker có thêm tín hiệu `progress`; một `_TransferProgressTracker` quy đổi ra phần trăm/tốc độ/ETA, và `_TransferProgressPanel` hiển thị ngay dưới thanh công cụ của phòng. Panel hiện khi bắt đầu, cập nhật theo từng chunk, và ẩn khi hoàn tất hoặc lỗi.

Phần trăm tính theo số chunk (chính xác tuyệt đối); tốc độ và ETA tính từ byte thực và thời gian trôi qua. Trường hợp resume (đã có sẵn chunk trên node) cũng được tính đúng theo tiến độ của cả file.

**Đã kiểm chứng:**

- Test end-to-end với một storage-node giả lập (file ~700 KB, 3 chunk): chuỗi tiến độ upload và download đều đúng `(1,3,…)→(2,3,…)→(3,3, full, full)`, và file tải về khớp SHA-256.
- Test logic: phần trăm `33 → 67 → 100`; định dạng tốc độ `2.3 MB/s`, `47.7 MB/s`; ETA `5s left`, `1m 15s left`, `1h 02m left`.

**File thay đổi:** 3 file, +165 / −18 dòng.

- `network/storage_node_data_plane.py` — callback kèm số byte (upload + download).
- `ui/pages/room_page.py` — tracker, panel, tín hiệu `progress`, và đấu nối vào luồng upload/download.
- `ui/widgets/top_bar.py` — sửa bug mục 3.

Có kèm script test chạy lại được: `coordinator-node/test_data_plane_progress.py`.

## 5. Chưa kiểm tra được tại sandbox (cần làm trên máy thật)

- **Tích hợp đầu-cuối + GUI**: phải chạy trên Windows (Docker + client PySide6).
- **Compile Java cuối cùng**: chạy `mvn clean package` trong `storage-node/`.
- **Test tích hợp DB** (`test_auth`, `test_room`, `test_file`, `test_upload`, `test_download`, …): cần PostgreSQL + Redis đang chạy.
- **Các mục Low/Info** trong `BAO_CAO_BUG.md` (dead code, AES-CBC→GCM, RSA→OAEP, N+1 query…) vẫn để lại — không ảnh hưởng vận hành.

## 6. Cách dựng và test trên máy thật

1. Dựng full stack: trong `Code/` chạy `docker compose up --build` (thêm `--profile multi-node` nếu muốn 2 storage node).
2. Mở client: chạy `run_client.bat`.
3. Đăng nhập → vào một phòng → bấm Upload chọn file, và Download một file: **quan sát thanh tiến độ** hiển thị %, tốc độ, ETA cho cả hai chiều.
4. Test tự động:
   - `storage-node/`: `mvn test`
   - `coordinator-server/`: `pytest` (cần Postgres + Redis; xem `SETUP.md`)
   - Thanh tiến độ (không cần hạ tầng): `python coordinator-node/test_data_plane_progress.py`
