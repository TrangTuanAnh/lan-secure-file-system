# Hướng dẫn Test Manual

## Bước 1: Build và Start Services

```bash
# Sử dụng docker compose v2
docker compose up -d --build

# Hoặc docker-compose v1
docker-compose up -d --build
```

## Bước 2: Kiểm tra Services đang chạy

```bash
docker compose ps
# hoặc
docker-compose ps
```

**Expected output:**
```
NAME                  STATUS              PORTS
coordinator-postgres  Up (healthy)        0.0.0.0:5432->5432/tcp
coordinator-redis     Up (healthy)        0.0.0.0:6379->6379/tcp
coordinator-server    Up (healthy)        0.0.0.0:8080-8082->8080-8082/tcp
storage-node-1        Up (healthy)        0.0.0.0:9001->9001/tcp
```

## Bước 3: Kiểm tra Coordinator Logs

```bash
docker compose logs coordinator | grep -i "storage"
```

**Expected output:**
```
[INFO] Storage node server started on port 8081
[INFO] Storage Node connection established: <connection_id>
[INFO] Storage Node authenticated: <connection_id>
[INFO] PING received from <connection_id>
```

## Bước 4: Kiểm tra Storage Node Logs

```bash
docker compose logs storage-node-1 | grep -i "coordinator"
```

**Expected output:**
```
[INFO] Connecting to Coordinator: coordinator:8081
[INFO] Authenticated with Coordinator
[INFO] Connected to Coordinator successfully
[INFO] Heartbeat started (interval: 30s)
[INFO] PING sent to Coordinator
```

## Bước 5: Kiểm tra Heartbeat (đợi 35 giây)

```bash
# Đợi heartbeat
sleep 35

# Kiểm tra PING/PONG
docker compose logs coordinator | grep -i "ping"
docker compose logs storage-node-1 | grep -i "ping"
```

**Expected:**
- Coordinator: "PING received from <id>"
- Storage Node: "PING sent to Coordinator", "PONG received"

## Bước 6: Xem Full Logs

```bash
# Coordinator
docker compose logs -f coordinator

# Storage Node
docker compose logs -f storage-node-1

# All services
docker compose logs -f
```

## Checklist Verification

- [ ] PostgreSQL healthy
- [ ] Redis healthy
- [ ] Coordinator started on port 8081
- [ ] Storage Node connected
- [ ] Storage Node authenticated
- [ ] Heartbeat working (PING/PONG)

## Troubleshooting

### Nếu Coordinator không start:

```bash
# Xem logs chi tiết
docker compose logs coordinator

# Kiểm tra database
docker compose exec postgres psql -U coordinator_user -d coordinator -c "SELECT 1"

# Restart
docker compose restart coordinator
```

### Nếu Storage Node không connect:

```bash
# Xem logs chi tiết
docker compose logs storage-node-1

# Kiểm tra network
docker compose exec storage-node-1 nc -zv coordinator 8081

# Kiểm tra secret có khớp không
docker compose exec coordinator env | grep STORAGE_NODE_SECRET
# So sánh với storage-node.docker.properties

# Restart
docker compose restart storage-node-1
```

### Nếu Authentication failed:

**Kiểm tra secret:**
- Coordinator: `STORAGE_NODE_SECRET=test-secret-12345` trong docker-compose.yml
- Storage Node: `ticket.secret=test-secret-12345` trong storage-node.docker.properties

**Phải khớp nhau!**

## Stop Services

```bash
# Stop nhưng giữ data
docker compose stop

# Stop và xóa containers
docker compose down

# Stop và xóa tất cả (bao gồm volumes)
docker compose down -v
```

## Kết quả mong đợi

Nếu tất cả OK, bạn sẽ thấy:

1. ✅ Coordinator Server khởi động thành công
2. ✅ Storage Node Server khởi động thành công
3. ✅ Storage Node kết nối đến Coordinator
4. ✅ Storage Node xác thực thành công
5. ✅ Heartbeat hoạt động (PING/PONG mỗi 30 giây)

**Hệ thống đã sẵn sàng để test upload/download!**
