# Frontend Overview & API Requirements

## 1. Hiện trạng frontend

Frontend hiện đã làm xong phần giao diện và flow cơ bản, gồm:

### Authentication

* Login
* Signup
* Reset password

Các chức năng này hiện đang chạy bằng mock (FakeApiService), nhưng đã có sẵn logic để chuyển sang API thật.

---

### Dashboard

* Sidebar (Home, Recent, Log)
* Hiển thị avatar + thời gian
* Panel Recent Tasks (bind data động)

---

### Home (quan trọng nhất)

* Hiển thị danh sách room
* Mỗi room gồm:

  * Tên phòng
  * Số file
  * Số thành viên

Danh sách này đang bind từ ViewModel → khi có API chỉ cần thay nguồn data là xong.

---

### Data flow

Frontend đang đi theo hướng:

* Service → gọi API
* ViewModel → giữ data
* View → hiển thị

Hiện tại dùng FakeApiService, sau này thay bằng RealApiService.

---

## 2. Model dữ liệu cần match

### Room

```json
{
  "name": "string",
  "fileCount": 0,
  "memberCount": 0
}
```

---

### Recent Tasks

```json
{
  "fileName": "string",
  "roomName": "string",
  "time": "string"
}
```

---

### Login response

```json
{
  "token": "string",
  "username": "string"
}
```

---

## 3. API cần có

### Auth

* POST /api/auth/login
* POST /api/auth/signup
* POST /api/auth/reset-password

---

### Data

* GET /api/rooms
* GET /api/tasks/recent

---

## 4. Những thứ cần chú ý khi viết API

### Naming

Frontend bind trực tiếp theo key, nên phải giữ đúng:

* name
* fileCount
* memberCount
* fileName
* roomName
* time

Sai key là UI không hiện.

---

### Format JSON

* Trả thẳng list, không bọc thêm object lạ
* Không đổi tên field
* Không đổi kiểu dữ liệu

---

### Status code

* 200: thành công
* 400/401: lỗi
* Trả message rõ ràng khi fail

---

### Password

* Không lưu plain text
* Hash bằng bcrypt hoặc tương tự

---

### Token

* Nên dùng JWT
* Không trả thông tin nhạy cảm

---

### Time

Nên dùng format:

```
2026-04-13T10:00:00
```

Frontend sẽ tự xử lý hiển thị.

---

## 5. Khi nối API

Frontend sẽ:

* gọi API bằng HttpClient
* nhận JSON
* map vào model
* bind lên UI

Chỉ cần API trả đúng format là dùng được ngay, không cần sửa UI.

---

## 6. Quy trình làm

1. Backend làm API theo spec
2. Test bằng Postman
3. Frontend đổi FakeApiService → RealApiService
4. chạy thử và kiểm tra UI
