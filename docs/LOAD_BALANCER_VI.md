# Báo cáo Load Balancer của Coordinator Server

Tài liệu này giải thích **toàn bộ luồng chạy end-to-end** của khâu chọn storage node cho mỗi lần upload, sau khi đã nâng cấp 3 cải tiến:

1. **Power of Two Choices** (P2C) — thuật toán chọn node.
2. **Slot reservation TTL** — giữ chỗ atomic, tự hết hạn.
3. **Weighted by free_bytes** — tính dung lượng còn trống vào quyết định.

Mỗi mục được trình bày theo bố cục: *Mô tả nhanh → Vị trí cụ thể nằm đâu trên các máy → Logic hoạt động ra sao và vì sao → Lợi ích*.

> Mọi tham chiếu `file:line` bên dưới đều là **markdown link** trỏ vào dòng tương ứng. Trong VS Code: **Ctrl + Click** (hoặc Cmd + Click trên macOS) là nhảy thẳng tới vị trí đó.

---

## 0. Bối cảnh 3 node tham gia

Một upload "đi qua tay" 3 node:

| Node | Vai trò | Ngôn ngữ |
|---|---|---|
| **Client desktop** | Người dùng cuối, gửi INIT_UPLOAD, đẩy byte file. | Python + PySide6 (thư mục `coordinator-node/`) |
| **Coordinator server** | Bộ não điều phối, chọn storage node, cấp ticket. | Python (thư mục `coordinator-server/`) |
| **Storage node** | Nơi thực sự cầm byte, nhận chunk từ client. | Java (thư mục `storage-node/`) |

**Quan trọng**: byte file đi **trực tiếp** client ↔ storage-node. Coordinator chỉ điều phối, không bao giờ chạm byte. Toàn bộ load balancer nằm ở Coordinator.

---

## 1. Power of Two Choices (P2C)

### 1.1. Mô tả nhanh

Thay vì luôn chọn node "ít việc nhất" toàn cục, lấy **ngẫu nhiên 2 node** trong số node healthy rồi so sánh, lấy node nào ít việc hơn.

### 1.2. Vị trí cụ thể

- **Coordinator server** — [`storage_node/registry.py:197`](../coordinator-server/storage_node/registry.py#L197) (`select_for_upload`), [dòng 237](../coordinator-server/storage_node/registry.py#L237) gọi `random.sample(healthy, 2)` rồi chọn min theo `_upload_score`.
- Trên **client** và **storage node**: không có code liên quan. Đây là quyết định nội bộ của coordinator.

Trích đoạn (xem trực tiếp tại [`storage_node/registry.py:234-237`](../coordinator-server/storage_node/registry.py#L234-L237)):

```python
if len(healthy) == 1:
    pick = healthy[0]
else:
    two = random.sample(healthy, 2)
    pick = min(two, key=self._upload_score)
```

### 1.3. Logic hoạt động ra sao và vì sao

Logic ngắn gọn:
1. Lọc các node `healthy` (heartbeat trong hạn) + có địa chỉ data plane + đủ dung lượng (mục 3).
2. Nếu chỉ còn 1 node → trả luôn.
3. Nếu ≥ 2 node → lấy ngẫu nhiên 2 → so sánh điểm → chọn node có điểm thấp hơn.

**Vì sao không dùng "least-loaded" toàn cục?**
Hiện tượng kinh điển là **herd**: ở thời điểm T, mọi worker thread đồng thời xử lý INIT_UPLOAD đều nhìn vào registry, cùng thấy node X là ít việc nhất (vì `active_uploads` chưa được cập nhật cho các quyết định đang trong tiến trình). Hậu quả: tất cả đổ về X cùng lúc, X quá tải, các node khác rảnh.

P2C giải quyết bằng thông tin xác suất: ngay cả khi node X là tốt nhất, chỉ một phần các worker chọn đúng X trong cặp ngẫu nhiên. Lý thuyết chỉ ra phân bố tải đạt mức **gần tối ưu** mà không cần đồng bộ trạng thái toàn cục đắt đỏ.

### 1.4. Lợi ích

- Tránh herd: 10 INIT_UPLOAD song song không còn rơi cùng 1 node.
- Không cần dữ liệu toàn cục → vẫn rẻ, atomic dưới 1 lần khoá lock.
- Là kỹ thuật chuẩn của Nginx, HAProxy, các hệ phân tán — chứng minh sự hiểu biết về thuật toán phân tán trong báo cáo môn học.

---

## 2. Slot reservation với TTL

### 2.1. Mô tả nhanh

Khi coordinator chọn xong node cho 1 upload, **đồng thời** tạo 1 "phiếu giữ chỗ" có hạn (60s mặc định). Hết hạn mà chưa thấy UPLOAD_COMPLETE/UPLOAD_FAILED → phiếu tự huỷ, slot trả lại pool. `reservation_id` chính là `file_id`.

### 2.2. Vị trí cụ thể

- **Coordinator server**
  - [`storage_node/registry.py:20`](../coordinator-server/storage_node/registry.py#L20) — dataclass `_Reservation(id, node_id, expires_at)`.
  - [`storage_node/registry.py:95`](../coordinator-server/storage_node/registry.py#L95) — `self._reservations: Dict[str, _Reservation]`.
  - [`storage_node/registry.py:197`](../coordinator-server/storage_node/registry.py#L197) — `select_for_upload(reservation_id, ttl_seconds)` tạo reservation atomic.
  - [`storage_node/registry.py:254`](../coordinator-server/storage_node/registry.py#L254) — `release_reservation(id)` (idempotent).
  - [`storage_node/registry.py:304`](../coordinator-server/storage_node/registry.py#L304) — `_reap_expired_locked()` quét expired ở đầu mỗi lần select.
  - [`upload/upload_service.py:300`](../coordinator-server/upload/upload_service.py#L300) — sinh `file_id` trước rồi truyền vào select.
  - [`upload/upload_service.py:142`](../coordinator-server/upload/upload_service.py#L142) — `_release_slot(file_id)`.
  - Các điểm gọi release khi UPLOAD_COMPLETE / UPLOAD_FAILED về:
    [`upload_service.py:452`](../coordinator-server/upload/upload_service.py#L452),
    [`:481`](../coordinator-server/upload/upload_service.py#L481),
    [`:650`](../coordinator-server/upload/upload_service.py#L650),
    [`:676`](../coordinator-server/upload/upload_service.py#L676).
  - [`cleanup/cleanup_service.py:109`](../coordinator-server/cleanup/cleanup_service.py#L109) — fallback release trong job dọn 35 phút (idempotent → an toàn).
  - Config `UPLOAD_SLOT_TTL_SECONDS` (default 60s):
    [`config.py:46`](../coordinator-server/config.py#L46),
    [`config.py:93`](../coordinator-server/config.py#L93),
    [`main.py:134`](../coordinator-server/main.py#L134).
- **Client**: không cần biết gì về reservation.
- **Storage node**: không cần biết gì. Chỉ cần gửi UPLOAD_COMPLETE/UPLOAD_FAILED với `file_id` như cũ.

### 2.3. Logic hoạt động ra sao và vì sao

Trích đoạn (xem trực tiếp tại [`upload/upload_service.py:300`](../coordinator-server/upload/upload_service.py#L300)):

```python
# INIT_UPLOAD path
file_id = str(uuid.uuid4())
selected_node = self._select_storage_node(storage_address, reservation_id=file_id)
# ↑ atomic: chọn node + tạo reservation trong cùng 1 lần khoá lock
```

Bên trong registry (xem [`storage_node/registry.py:241-249`](../coordinator-server/storage_node/registry.py#L241-L249)):

```python
self._reservations[reservation_id] = _Reservation(
    id=reservation_id,
    node_id=pick.node_id,
    expires_at=time.time() + ttl_seconds,
)
pick.active_uploads += 1
# ↑ counter và reservation luôn cùng nhịp
```

Khi UPLOAD_COMPLETE/UPLOAD_FAILED về (`handle_upload_complete`, `handle_upload_failed`), coordinator gọi `release_reservation(file_id)` → counter giảm 1, reservation bị xoá.

Nếu **không bao giờ** có tin nào về: lần kế tiếp một worker khác gọi `select_for_upload`, [`_reap_expired_locked()`](../coordinator-server/storage_node/registry.py#L304) quét trước, thấy reservation đã quá hạn → giảm counter, xoá reservation. **Lazy reap** = không cần thread nền riêng.

**Vì sao chọn cách này?**
- Atomic select + reserve: tránh race "2 worker cùng nhìn thấy cùng node ít việc nhất rồi cùng increment" — một classic data race kể cả với P2C.
- TTL ngắn (60s) trong khi *ticket upload* có TTL dài (30 phút): nếu client biến mất giữa chừng, slot **không phải đợi** cleanup 35 phút mới trả lại.
- `reservation_id = file_id`: storage node gửi UPLOAD_COMPLETE chỉ kèm `file_id`, coordinator dùng đúng id đó để release → không cần đổi giao thức trên dây.

### 2.4. Lợi ích

- Sửa bug thực tế: trước đây slot có thể kẹt 35 phút nếu client không hoàn thành. Sau khi sửa: tối đa 60s.
- Không cần thread nền chuyên cho reap — lazy.
- Atomic chống race condition select-then-reserve.
- Idempotent: gọi `release_reservation` 2 lần cũng OK; UPLOAD_COMPLETE đến rồi cleanup vẫn chạy về sau cũng không lỗi.

---

## 3. Weighted by free_bytes

### 3.1. Mô tả nhanh

Đưa **dung lượng còn trống** của storage node vào quyết định: (a) node sắp đầy bị **loại** khỏi pool, (b) trong 2 node được P2C chọn cùng `active_uploads`, node nào **nhiều dung lượng hơn** thắng.

### 3.2. Vị trí cụ thể

- **Coordinator server**
  - [`storage_node/registry.py:53`](../coordinator-server/storage_node/registry.py#L53) — field `free_bytes: Optional[int] = None` trên `StorageNodeInfo`.
  - [`storage_node/registry.py:79`](../coordinator-server/storage_node/registry.py#L79) — serialize `freeBytes` ra `to_dict` (cho endpoint health).
  - [`storage_node/registry.py:86`](../coordinator-server/storage_node/registry.py#L86) — constructor nhận `min_free_bytes=0`.
  - [`storage_node/registry.py:148`](../coordinator-server/storage_node/registry.py#L148) — `heartbeat(connection, free_bytes=None)` nhận thêm capacity update.
  - [`storage_node/registry.py:161`](../coordinator-server/storage_node/registry.py#L161) — `update_capacity(connection, free_bytes)`.
  - [`storage_node/registry.py:277`](../coordinator-server/storage_node/registry.py#L277) — `_has_enough_capacity` (filter rule).
  - [`storage_node/registry.py:292`](../coordinator-server/storage_node/registry.py#L292) — `_upload_score` — order key `(active_uploads, -free_or_inf, node_id)`.
  - [`storage_node/storage_node_server.py:305`](../coordinator-server/storage_node/storage_node_server.py#L305) — `_handle_storage_auth` đọc `freeBytes` từ payload AUTH.
  - [`storage_node/storage_node_server.py:393`](../coordinator-server/storage_node/storage_node_server.py#L393) — `_handle_ping` đọc `freeBytes` từ payload PING.
  - Config `STORAGE_MIN_FREE_BYTES` (default 0):
    [`config.py:47`](../coordinator-server/config.py#L47),
    [`config.py:94`](../coordinator-server/config.py#L94),
    [`main.py:116`](../coordinator-server/main.py#L116).
- **Storage node (Java)** *(mở rộng giao thức — backward compat)*:
  - Nếu muốn được weighted, gửi thêm `"freeBytes": <long>` trong payload PING (mỗi heartbeat) và/hoặc STORAGE_AUTH (báo cáo lần đầu).
  - Không gửi cũng OK: coordinator coi như "vô cực" (không phạt, không filter).

### 3.3. Logic hoạt động ra sao và vì sao

**Phía storage node (Java)** — mỗi lần heartbeat tính `getFreeSpace()` của ổ data, nhét vào field `freeBytes` của PING JSON.

**Phía coordinator** — handler PING (xem [`storage_node_server.py:393`](../coordinator-server/storage_node/storage_node_server.py#L393)):

```python
free_bytes = message.payload.get("freeBytes") if message.payload else None
parsed = int(free_bytes) if free_bytes is not None else None
self.registry.heartbeat(connection, free_bytes=parsed)
```

Lần `select_for_upload` kế tiếp (xem [`registry.py:225-232`](../coordinator-server/storage_node/registry.py#L225-L232)):

```python
healthy = [
    node for node in self._nodes_by_id.values()
    if node.is_healthy(self.timeout_seconds)
    and node.storage_address
    and self._has_enough_capacity(node)   # ← filter mục 3
]
```

Order key (xem [`registry.py:292-303`](../coordinator-server/storage_node/registry.py#L292-L303)):

```python
@staticmethod
def _upload_score(node):
    free_for_sort = node.free_bytes if node.free_bytes is not None else float("inf")
    return (node.active_uploads, -free_for_sort, node.node_id)
```

**Vì sao thiết kế 2 tầng (filter + tiebreaker)?**
- **Filter (`min_free_bytes`)**: là "safety floor" rõ ràng. Operator đặt `STORAGE_MIN_FREE_BYTES=1073741824` (1 GiB) → node dưới ngưỡng **không bao giờ** nhận thêm upload nữa, tránh tình huống "the last straw" đẩy node đến full disk.
- **Tiebreaker (free_bytes desc)**: không hung hăng tới mức "luôn chọn node rỗng nhất" (sẽ phá tính cân bằng tải) — chỉ áp dụng khi `active_uploads` bằng nhau. Đây là cách dung lượng định hướng tải mềm.

**Vì sao `None` được coi là vô cực?**
- Storage node Java cũ chưa update để báo cáo `freeBytes` cũng vẫn phải hoạt động.
- Trộn giữa node "đã báo" và "chưa báo" mà coi None là 0 thì sẽ làm các node legacy bị tránh né — sai phạt phải.
- Coi None là infinity = "không biết → giả định là dư dả, không can thiệp" = an toàn nhất cho rollout từng giai đoạn.

### 3.4. Lợi ích

- **Tránh ghi đến node đã gần đầy**: filter cứng.
- **Cân bằng dung lượng dần dần**: tiebreaker mềm kéo upload về node có nhiều chỗ hơn khi tải ngang nhau, dần dần đồng đều mức sử dụng đĩa giữa các node.
- **Backward-compat**: không cần đổi gì ở Java vẫn chạy được. Java có thể cập nhật từng node một mà không gián đoạn dịch vụ.
- **Operator kiểm soát được**: đổi `STORAGE_MIN_FREE_BYTES` qua env var, không cần đụng code.
- **Quan sát được**: `freeBytes` xuất hiện trong `STATUS` response qua `to_dict()` → dùng cho dashboard / debug.

---

## 4. Luồng end-to-end của 1 upload có cả 3 cải tiến

Bối cảnh: 3 storage node A, B, C đang chạy. Mỗi node heartbeat 30s/lần kèm `freeBytes`. Có 2 client (Alice, Bob) đồng thời gửi INIT_UPLOAD cho 2 file khác nhau.

```
Storage nodes hiện trạng (sau heartbeat gần nhất):
  A: healthy, active_uploads=2, free_bytes= 8 GiB
  B: healthy, active_uploads=2, free_bytes=50 GiB
  C: healthy, active_uploads=1, free_bytes= 0.5 GiB  ← gần đầy
```

Giả sử `STORAGE_MIN_FREE_BYTES = 1 GiB`.

### Bước 1 — Alice gửi INIT_UPLOAD (file_id sẽ là `F-alice`)
| Nơi xảy ra | Việc |
|---|---|
| Client (Alice) | Soạn message INIT_UPLOAD, gửi qua socket tới coordinator port 8080. |
| Coordinator: Acceptor thread | Đọc frame, đẩy vào ThreadPoolExecutor. |
| Coordinator: Worker thread `ClientSocketServer-Worker_3` | Vào [`UploadService.handle_init_upload`](../coordinator-server/upload/upload_service.py#L157). Sinh `file_id = "F-alice"`. Gọi [`_select_storage_node(reservation_id="F-alice")`](../coordinator-server/upload/upload_service.py#L301). |
| Coordinator: Registry (dưới lock) | [`_reap_expired_locked()`](../coordinator-server/storage_node/registry.py#L304) — không có gì. Filter healthy: A ✅, B ✅, **C ❌** (0.5 GiB < 1 GiB). Còn lại [A, B]. `random.sample([A,B], 2)` = [A, B]. Score A=(2, -8GiB, "A"), score B=(2, -50GiB, "B"). B điểm thấp hơn (vì -50 < -8). **Chọn B**. Tạo reservation `"F-alice" → B`, `B.active_uploads = 3`. Trả về B. |
| Coordinator: Worker thread (tiếp) | DB INSERT file row với `storage_node_id=B`. Sinh ticket, lưu Redis. Gửi UPLOAD_PLAN response chứa địa chỉ data plane của B. |

### Bước 2 — Bob gửi INIT_UPLOAD song song (file_id `F-bob`)
| Nơi xảy ra | Việc |
|---|---|
| Coordinator: Worker thread `ClientSocketServer-Worker_5` | Vào `handle_init_upload` cùng lúc với Alice. Sinh `file_id="F-bob"`. Gọi select. |
| Coordinator: Registry (lock) | Filter: [A, B] (C vẫn bị loại). Lúc này B đã có `active_uploads=3` (do bước 1 vừa reserve). P2C lấy [A, B] (chỉ có 2). Score A=(2, -8GiB, "A"), B=(3, -50GiB, "B"). A thấp hơn (2 < 3). **Chọn A**. Tạo reservation `"F-bob" → A`, `A.active_uploads = 3`. |
| Coordinator: Worker (tiếp) | INSERT file row với `storage_node_id=A`. Trả plan. |

**Quan trắc**: tải đã được phân ra giữa 2 worker song song (Alice→B, Bob→A) nhờ atomic select+reserve. Không có race condition kiểu "cả hai cùng nhìn B và đè lên nhau".

### Bước 3 — Alice push byte tới storage node B (data plane)
| Nơi | Việc |
|---|---|
| Client | Mở kết nối tới `B.storage_address`, đẩy chunk qua đó. **Coordinator không tham gia bước này.** |
| Storage B (Java) | Nhận chunk, tích lũy, kiểm tra hash, virus scan. |

### Bước 4 — Storage B gửi UPLOAD_COMPLETE về coordinator
| Nơi | Việc |
|---|---|
| Storage B | Sau khi finalize file `F-alice`, gửi UPLOAD_COMPLETE qua port storage (8081). |
| Coordinator: StorageNodeServer Acceptor → Worker `StorageNodeServer-Worker_1` | [`handle_upload_complete(file_id="F-alice", ...)`](../coordinator-server/upload/upload_service.py#L411). |
| Coordinator (worker) | Update DB status = READY. Gọi [`_release_slot("F-alice")`](../coordinator-server/upload/upload_service.py#L481). |
| Coordinator: Registry (lock) | Tra `_reservations["F-alice"]` → tìm thấy → giảm `B.active_uploads` về 2, xoá reservation. |
| Coordinator (worker) | Broadcast NEW_FILE qua NotificationService. |

### Bước 5 — Bob mất kết nối, không gửi gì
| Thời điểm | Việc |
|---|---|
| T = 0s | Bob nhận plan, định push tới A, nhưng mạng Bob die. |
| T = 60s | Reservation `"F-bob"` hết hạn. Counter A vẫn = 3 (chưa ai trigger reap). |
| T = 65s | Một client thứ ba (Charlie) gửi INIT_UPLOAD. |
| Coordinator: Registry (lock) | [`_reap_expired_locked()`](../coordinator-server/storage_node/registry.py#L304) quét, thấy `"F-bob"` đã quá hạn → release. **A.active_uploads = 2**. Quyết định cho Charlie dùng số `active_uploads` đã chính xác. |

**Quan trắc**: không cần đợi job cleanup 35 phút. Slot trả lại sau **60s + lần truy cập kế tiếp** (thường là tức thì vì server đang chạy).

### Bước 6 — Heartbeat từ storage node về cập nhật free_bytes
| Thời điểm | Việc |
|---|---|
| Mỗi 30s | A, B, C gửi PING kèm `freeBytes` mới. |
| Coordinator: Worker xử lý PING | [`update_ping_time()`](../coordinator-server/storage_node/registry.py#L42) + `node_info.free_bytes = <giá trị mới>`. |
| Lần `select_for_upload` kế | [`_has_enough_capacity`](../coordinator-server/storage_node/registry.py#L277) và [`_upload_score`](../coordinator-server/storage_node/registry.py#L292) dùng giá trị mới nhất → quyết định luôn dựa trên trạng thái real-time. |

---

## 5. Bảng tham chiếu nhanh (cho slide)

| # | Tính năng | Nơi | File:Line |
|---|---|---|---|
| 1 | P2C selection | Coordinator | [`storage_node/registry.py:234-237`](../coordinator-server/storage_node/registry.py#L234-L237) |
| 2 | Reservation dataclass | Coordinator | [`storage_node/registry.py:20`](../coordinator-server/storage_node/registry.py#L20) |
| 3 | Atomic select+reserve | Coordinator | [`storage_node/registry.py:241-249`](../coordinator-server/storage_node/registry.py#L241-L249) |
| 4 | `release_reservation` | Coordinator | [`storage_node/registry.py:254`](../coordinator-server/storage_node/registry.py#L254) |
| 5 | Lazy reap expired | Coordinator | [`storage_node/registry.py:221`](../coordinator-server/storage_node/registry.py#L221), [`:304`](../coordinator-server/storage_node/registry.py#L304) |
| 6 | `free_bytes` field | Coordinator | [`storage_node/registry.py:53`](../coordinator-server/storage_node/registry.py#L53) |
| 7 | `_has_enough_capacity` filter | Coordinator | [`storage_node/registry.py:277`](../coordinator-server/storage_node/registry.py#L277) |
| 8 | `_upload_score` weighted | Coordinator | [`storage_node/registry.py:292`](../coordinator-server/storage_node/registry.py#L292) |
| 9 | freeBytes từ PING | Coordinator | [`storage_node/storage_node_server.py:393`](../coordinator-server/storage_node/storage_node_server.py#L393) |
| 10 | freeBytes từ STORAGE_AUTH | Coordinator | [`storage_node/storage_node_server.py:305`](../coordinator-server/storage_node/storage_node_server.py#L305) |
| 11 | Sinh file_id trước select | Coordinator | [`upload/upload_service.py:300`](../coordinator-server/upload/upload_service.py#L300) |
| 12 | Release slot ở UPLOAD_COMPLETE | Coordinator | [`upload/upload_service.py:481`](../coordinator-server/upload/upload_service.py#L481) |
| 13 | Release slot ở UPLOAD_FAILED | Coordinator | [`upload/upload_service.py:676`](../coordinator-server/upload/upload_service.py#L676) |
| 14 | Fallback release cleanup 35min | Coordinator | [`cleanup/cleanup_service.py:109`](../coordinator-server/cleanup/cleanup_service.py#L109) |
| 15 | Config `UPLOAD_SLOT_TTL_SECONDS` | Coordinator | [`config.py:93`](../coordinator-server/config.py#L93), [`main.py:134`](../coordinator-server/main.py#L134) |
| 16 | Config `STORAGE_MIN_FREE_BYTES` | Coordinator | [`config.py:94`](../coordinator-server/config.py#L94), [`main.py:116`](../coordinator-server/main.py#L116) |

---

## 6. Tổng kết lợi ích

| Cải tiến | Vấn đề cũ | Lợi ích |
|---|---|---|
| Power of Two Choices | Herd effect — mọi quyết định cùng đổ về 1 node "ít việc nhất" toàn cục | Phân bố gần tối ưu, không cần đồng bộ trạng thái global |
| Slot reservation TTL | Slot kẹt 35 phút nếu client biến mất; có race "select rồi mới reserve" | Slot tự release sau 60s; atomic select+reserve dưới 1 lock |
| Weighted by free_bytes | Có thể đẩy upload vào node sắp đầy; chia tải lệch dung lượng | Filter cứng node sắp full; tiebreaker mềm kéo dữ liệu về node nhiều chỗ hơn |

3 cải tiến này độc lập nhưng cùng tác động lên 1 hàm `select_for_upload`, tạo thành 1 load balancer **thread-safe, self-healing, capacity-aware** — đủ để minh chứng hiểu biết hệ phân tán trong báo cáo môn học.

---

## 7. Cách kiểm chứng

- **Unit tests**: `python -m pytest test_storage_node_registry.py -v` → 24/24 pass (bao phủ cả 3 cải tiến).
- **Smoke test load**: `python -m scripts.demo_load --clients 20` để xem coordinator xử lý song song.
- **Quan sát runtime**: gọi STATUS từ client, payload trả về có:
  - `threads.byPrefix` — biểu đồ thread đang chạy.
  - `storageNodes.connectedNodes` mỗi node có field `activeUploads` và `freeBytes` → xem realtime phân bố tải và dung lượng.
