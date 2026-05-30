# Báo cáo các vị trí đa luồng trong Coordinator Server

Tài liệu này liệt kê toàn bộ chỗ Coordinator dùng thread / lock / event, kèm lý do ngắn gọn. Mỗi mục có file:line để mở thẳng trong VS Code.

> Mọi tham chiếu `file:line` bên dưới đều là **markdown link** trỏ vào dòng tương ứng. Trong VS Code: **Ctrl + Click** (Cmd + Click trên macOS) là nhảy thẳng tới vị trí đó.

## 1. Bản đồ thread đang chạy

Khi server khởi động đầy đủ, Coordinator có các thread sau cùng tồn tại:

```
MainThread                       ← chạy main(), đợi shutdown_event
├── ClientSocketServer-Acceptor  ← selector loop, nhận client
├── ClientSocketServer-Worker_0..7   (8 thread, ThreadPoolExecutor)
├── StorageNodeServer-Acceptor   ← selector loop, nhận storage node
├── StorageNodeServer-Worker_0..3   (4 thread, ThreadPoolExecutor)
├── CleanupService               ← dọn upload mồ côi mỗi 10 phút
└── StorageHealthCheck           ← ping storage node định kỳ
```

Tổng ~16 thread. Số worker cấu hình qua biến môi trường `CLIENT_MAX_WORKERS` (mặc định 8) và `STORAGE_MAX_WORKERS` (mặc định 4).

---

## 2. Thread được tạo ở đâu

### 2.1. Acceptor thread — [`protocol/socket_server.py:186`](../coordinator-server/protocol/socket_server.py#L186)

```python
self._server_thread = threading.Thread(
    target=self._run_loop, name=f"{self.name}-Acceptor", daemon=True
)
```

**Vì sao**: cần 1 thread riêng chạy vòng lặp `selector.select()` để **không block main thread** (main thread cần đứng đợi `shutdown_event` để xử lý Ctrl+C). Mỗi server (Client / StorageNode) có 1 acceptor riêng vì lắng nghe trên 2 port khác nhau (8080 và 8081).

Daemon=True để khi main thread thoát thì thread này tự tắt theo.

### 2.2. Worker pool (ThreadPoolExecutor) — [`protocol/socket_server.py:180`](../coordinator-server/protocol/socket_server.py#L180)

```python
self._executor = ThreadPoolExecutor(
    max_workers=self.max_workers,
    thread_name_prefix=f"{self.name}-Worker",
)
```

**Vì sao**: đây là điểm chốt của Cách 1 (đa luồng). Acceptor chỉ chịu trách nhiệm I/O (đọc frame). Mọi handler (LOGIN, LIST_FILES, INIT_UPLOAD, broadcast event…) đẩy vào pool để chạy song song. N client cùng gửi request → N worker xử lý cùng lúc, không xếp hàng.

Dùng `ThreadPoolExecutor` thay vì spawn-thread-per-request để **giới hạn số thread**, tránh "thread bomb" khi có nhiều client.

### 2.3. Background CleanupService — [`cleanup/cleanup_service.py:39`](../coordinator-server/cleanup/cleanup_service.py#L39)

```python
self._thread = threading.Thread(
    target=self._run_cleanup_loop, name="CleanupService", daemon=True
)
```

**Vì sao**: việc dọn upload mồ côi (file ở trạng thái UPLOADING quá 35 phút) phải chạy **định kỳ song song với các request khác**, không thể nhồi vào request flow. Đặt riêng 1 thread, dùng `Event.wait(600s)` thay vì `time.sleep(600)` để có thể graceful shutdown.

### 2.4. Background StorageHealthCheck — [`storage_node/storage_node_server.py:96`](../coordinator-server/storage_node/storage_node_server.py#L96)

```python
self._health_check_thread = threading.Thread(
    target=self._health_check_loop,
    name="StorageHealthCheck",
    daemon=True,
)
```

**Vì sao**: cần thread riêng để **kiểm tra heartbeat của storage node** định kỳ, đánh dấu node nào timeout. Không gắn vào request flow vì không có request nào "tự nhiên" kích hoạt việc check timeout.

---

## 3. Điểm bất đồng bộ chính — chỗ "đẩy việc"

### 3.1. `executor.submit(...)` — [`protocol/socket_server.py:350`](../coordinator-server/protocol/socket_server.py#L350)

```python
self._executor.submit(self._run_handler, handler, connection, message)
```

**Đây là dòng quan trọng nhất** của toàn bộ thiết kế đa luồng. Acceptor đọc xong 1 message → gọi `submit` để **đẩy việc vào hàng đợi của pool** → return ngay, quay lại loop nhận message kế tiếp. Worker rảnh nào lấy được message thì xử lý.

Đây là pattern **producer-consumer** kinh điển: acceptor = producer, worker pool = consumer, queue nội bộ của `ThreadPoolExecutor` là kênh giao tiếp.

### 3.2. `_run_loop` (acceptor) — [`protocol/socket_server.py:228`](../coordinator-server/protocol/socket_server.py#L228)

Vòng lặp đọc socket, không xử lý handler trực tiếp. Đảm bảo acceptor **không bao giờ bị block bởi business logic**.

### 3.3. `_run_handler` (worker) — [`protocol/socket_server.py:352`](../coordinator-server/protocol/socket_server.py#L352)

Hàm bao quanh handler, chạy trên worker thread. Có try/except để 1 handler crash không kéo theo crash worker khác.

---

## 4. Sync primitive — Lock / RLock / Event

### 4.1. `_send_lock` — [`protocol/socket_server.py:38`](../coordinator-server/protocol/socket_server.py#L38), [`:59`](../coordinator-server/protocol/socket_server.py#L59), [`:91`](../coordinator-server/protocol/socket_server.py#L91)

```python
self._send_lock = threading.Lock()
...
with self._send_lock:
    self.socket.sendall(frame)
```

**Vì sao**: 2 worker thread khác nhau có thể cùng gọi `connection.send_message()` trên cùng 1 socket (ví dụ: worker A đang trả response LIST_FILES cho client X, worker B đang broadcast event NEW_FILE cũng tới client X). `socket.sendall()` giải phóng GIL giữa các syscall `send()`, nên bytes của 2 frame **có thể trộn lẫn** → client parse sai → protocol vỡ.

Lock đảm bảo mỗi lần chỉ 1 thread ghi vào socket, gửi nguyên 1 frame xong mới đến frame kế.

### 4.2. `_connections_lock` — [`protocol/socket_server.py:138`](../coordinator-server/protocol/socket_server.py#L138), [`:202`](../coordinator-server/protocol/socket_server.py#L202), [`:257`](../coordinator-server/protocol/socket_server.py#L257), [`:278`](../coordinator-server/protocol/socket_server.py#L278), [`:383`](../coordinator-server/protocol/socket_server.py#L383), [`:427`](../coordinator-server/protocol/socket_server.py#L427)

```python
self._connections_lock = threading.Lock()
```

**Vì sao**: dict `_connections` (map socket → SocketConnection) bị nhiều thread đụng:
- Acceptor: thêm entry khi accept ([`:202`](../coordinator-server/protocol/socket_server.py#L202)).
- Acceptor: tra cứu khi đọc data ([`:257`](../coordinator-server/protocol/socket_server.py#L257)).
- Worker: gọi `_close_connection` khi connection lỗi ([`:383`](../coordinator-server/protocol/socket_server.py#L383)).
- HealthService: gọi `get_connection_count()` ([`:427`](../coordinator-server/protocol/socket_server.py#L427)).

Không có lock → có thể gặp `RuntimeError: dictionary changed size during iteration` hoặc lookup lỗi nửa-đường.

### 4.3. `NotificationService._lock` (RLock) — [`notification/notification_service.py:17`](../coordinator-server/notification/notification_service.py#L17)

```python
self._lock = threading.RLock()
```

**Vì sao**: subscriber map (room → set of connections) bị nhiều thread đụng cùng lúc:
- Worker xử lý `SUBSCRIBE_ROOM` → `add_subscriber`.
- Worker xử lý `UNSUBSCRIBE_ROOM` → `remove_subscriber`.
- Worker khác đang broadcast event → iterate set.
- `_on_connection_closed` (worker hoặc acceptor) → `remove_subscriber_from_all_rooms`.

Dùng `RLock` (reentrant) vì `_broadcast_event` đã giữ lock, bên trong gọi `remove_subscriber_from_all_rooms` lại acquire lock một lần nữa **trên cùng thread** — `RLock` cho phép, `Lock` thường sẽ deadlock.

### 4.4. `StorageNodeRegistry._lock` — [`storage_node/registry.py:62`](../coordinator-server/storage_node/registry.py#L62)

```python
self._lock = threading.Lock()
```

**Vì sao**: registry chia sẻ giữa `ClientSocketServer` và `StorageNodeServer` (truyền vào cả 2 trong `main.py`) → có ~13 worker thread tiềm tàng đụng vào:
- Worker client gọi `select_for_upload()`, `mark_upload_started()` khi INIT_UPLOAD.
- Worker storage gọi `add_connection`, `authenticate`, `heartbeat`, `remove_connection`.
- HealthCheck thread iterate `get_all_nodes()`.
- CleanupService gọi `mark_upload_finished()`.

Đặc biệt: `active_uploads += 1` **không phải atomic** dù có GIL (3 bytecode: LOAD/ADD/STORE, GIL có thể switch giữa các bytecode) → bắt buộc lock.

### 4.5. `CleanupService._stop_event` — [`cleanup/cleanup_service.py:28`](../coordinator-server/cleanup/cleanup_service.py#L28)

```python
self._stop_event = threading.Event()
...
self._stop_event.wait(self.interval_seconds)
```

**Vì sao**: cần cách "ngủ 10 phút nhưng có thể wake-up sớm khi shutdown". `time.sleep(600)` thì khi Ctrl+C phải đợi đủ 10 phút. `Event.wait(600)` thì khi gọi `stop_event.set()`, thread bừng dậy ngay → **graceful shutdown**.

### 4.6. `main.shutdown_event` — [`main.py:31`](../coordinator-server/main.py#L31)

```python
shutdown_event = threading.Event()
```

**Vì sao**: main thread cần đứng đợi tín hiệu SIGINT/SIGTERM nhưng phải làm việc đó **cross-platform** (Unix có `signal.pause()`, Windows không). Dùng `Event.wait(timeout=1.0)` trong loop để main thread vừa đợi shutdown vừa kiểm tra định kỳ.

---

## 5. Bảng tóm tắt cho slide

| # | File:Line | Loại | Mục đích |
|---|---|---|---|
| 1 | [`protocol/socket_server.py:186`](../coordinator-server/protocol/socket_server.py#L186) | `Thread` | Acceptor loop (selector) |
| 2 | [`protocol/socket_server.py:180`](../coordinator-server/protocol/socket_server.py#L180) | `ThreadPoolExecutor(8)` | Worker pool xử lý request |
| 3 | [`protocol/socket_server.py:350`](../coordinator-server/protocol/socket_server.py#L350) | `executor.submit()` | **Điểm bất đồng bộ chính** |
| 4 | [`cleanup/cleanup_service.py:39`](../coordinator-server/cleanup/cleanup_service.py#L39) | `Thread` | Định kỳ dọn upload mồ côi |
| 5 | [`storage_node/storage_node_server.py:96`](../coordinator-server/storage_node/storage_node_server.py#L96) | `Thread` | Định kỳ check storage node |
| 6 | [`protocol/socket_server.py:38`](../coordinator-server/protocol/socket_server.py#L38) | `Lock` | Bảo vệ `socket.sendall` |
| 7 | [`protocol/socket_server.py:138`](../coordinator-server/protocol/socket_server.py#L138) | `Lock` | Bảo vệ dict `_connections` |
| 8 | [`notification/notification_service.py:17`](../coordinator-server/notification/notification_service.py#L17) | `RLock` | Bảo vệ subscriber map |
| 9 | [`storage_node/registry.py:62`](../coordinator-server/storage_node/registry.py#L62) | `Lock` | Bảo vệ registry (counter + dict) |
| 10 | [`cleanup/cleanup_service.py:28`](../coordinator-server/cleanup/cleanup_service.py#L28) | `Event` | Graceful shutdown của cleanup |
| 11 | [`main.py:31`](../coordinator-server/main.py#L31) | `Event` | Graceful shutdown của main |

---

## 6. Vì sao chia thành nhiều loại lock?

| Loại | Khi nào dùng | Ví dụ ở đây |
|---|---|---|
| `Lock` | Khi không gọi đệ quy, không nested | `_send_lock`, `_connections_lock`, registry |
| `RLock` | Khi method giữ lock có thể gọi method khác cũng giữ lock | `NotificationService._lock` (broadcast gọi remove_subscriber) |
| `Event` | Khi cần báo hiệu giữa thread (vd shutdown) | `CleanupService._stop_event`, `shutdown_event` |

---

## 7. Pattern thread đã áp dụng

1. **Acceptor + selector** — 1 thread cho I/O non-blocking.
2. **Worker pool (Producer-Consumer)** — pool có giới hạn, acceptor là producer, worker là consumer.
3. **Periodic background thread** — chạy định kỳ, dùng Event để có thể dừng sớm.

Đây là 3 pattern kinh điển dùng đồng thời trong cùng 1 hệ thống — đủ cho 1 báo cáo môn học về concurrent programming.

---

## 8. Cách kiểm chứng

Chạy `python -m scripts.demo_load --clients 20 --msg STATUS` trong `coordinator-server/` để:

- Mở 20 client TCP song song.
- Mỗi client gọi STATUS.
- In ra latency từng client, tổng wall-clock, và snapshot thread server-side.

So với code single-threaded (set `CLIENT_MAX_WORKERS=1` trong `.env`), thời gian tổng cộng giảm gần bằng số lần ứng với số worker pool.
