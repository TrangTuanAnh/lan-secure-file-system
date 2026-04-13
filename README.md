# Frontend Structure & API Notes

## 1. Cấu trúc thư mục

```
│   App.xaml
│   App.xaml.cs
├───Assets          // ảnh, icon
├───Converters      // converter (ví dụ: BoolToVisibility)
├───Models          // model map trực tiếp từ API
├───Services        // gọi API (AuthServices, FakeAPIServices)
├───ViewModels      // xử lý dữ liệu cho UI
└───Views
    └───Pages       // HomePage, RoomPage, ...
```

---

## 2. Tổng quan hiện tại

Frontend đã có:

* Login / Signup / Reset password
* Dashboard + sidebar
* Home (danh sách room)
* Click room → vào RoomPage
* Recent tasks (panel bên phải)

Data hiện tại đang lấy từ `FakeAPIServices`

Khi có backend:

* thay FakeAPI bằng API thật
* UI không cần sửa

---

## 3. Flow chính

### Login

* nhập username + password
* gọi API
* nếu ok → vào dashboard

---

### Signup

* nhập username, email, password, confirm password
* frontend check:

  * không rỗng
  * password >= 6
  * confirm phải trùng
* gọi API signup

---

### Home

* gọi API lấy danh sách room
* hiển thị:

  * name
  * memberCount

---

### Click room

* lấy room.id
* gọi API lấy chi tiết room
* render RoomPage

RoomPage gồm:

* members
* files
* role (OWNER / USER)

---

### Recent tasks

* gọi API riêng
* hiển thị bên phải dashboard

---

## 4. Data structure (backend cần trả)

### Rooms

GET /api/rooms

```
[
  {
    "id": 1,
    "name": "Security Team",
    "memberCount": 5
  }
]
```

---

### Room detail

GET /api/rooms/{id}

```
{
  "roomId": 1,
  "roomName": "Security Team",
  "role": "OWNER",

  "members": [
    {
      "username": "Khang",
      "role": "OWNER"
    }
  ],

  "files": [
    {
      "name": "report.pdf",
      "size": "2MB",
      "uploader": "Khang",
      "time": "2026-04-13T10:00:00"
    }
  ]
}
```

---

### Recent tasks

GET /api/tasks/recent

```
[
  {
    "fileName": "report.pdf",
    "roomName": "Security Team",
    "time": "2026-04-13T10:00:00"
  }
]
```

---

### Auth

POST /api/auth/login

```
{
  "username": "string",
  "password": "string"
}
```

---

POST /api/auth/signup

```
{
  "username": "string",
  "password": "string",
  "email": "string"
}
```

---

POST /api/auth/reset-password

```
{
  "email": "string"
}
```

---

## 5. Quy tắc

* key phải đúng (name, memberCount, fileName, ...)
* không bọc JSON kiểu `{ data: ... }`
* list trả `[]`, không trả null
* time dùng ISO (yyyy-MM-ddTHH:mm:ss)
* password phải hash
* role chỉ có:

  * OWNER
  * USER

---

## 6. Lưu ý code

* HomePage dùng `Room` (model nhẹ)

* RoomPage dùng `RoomViewModel` (chi tiết)

* không dùng lẫn 2 cái này

* click room chỉ xử lý ở HomePage

* RoomPage chỉ render

---

## 7. Khi nối backend

* bỏ FakeAPIServices
* sửa trong Services để gọi API thật
* giữ nguyên View + ViewModel
