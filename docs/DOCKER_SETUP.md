# Docker Setup và Testing Guide

## Tổng quan

Hệ thống bao gồm 5 services chính:
1. **PostgreSQL** - Database
2. **Redis** - Cache và session storage
3. **Coordinator Server** (Python) - Control plane
4. **Storage Node 1** (Java) - Data plane
5. **Storage Node 2** (Java) - Optional second node

## Cấu trúc Docker

```
.
├── docker-compose.yml              # Main compose file
├── coordinator-server/
│   ├── Dockerfile                  # Coordinator image
│   ├── entrypoint.sh              # Startup script với migrations
│   └── ...
├── storage-node/
│   ├── Dockerfile                  # Storage Node image (multi-stage)
│   ├── storage-node.docker.properties  # Docker-specific config
│   ├── .dockerignore
│   └── ...
└── test-integration.sh             # Automated test script
```

## Quick Start

### 1. Build và Start tất cả services

```bash
# Start với 1 storage node
docker-compose up -d --build

# Hoặc start với 2 storage nodes
docker-compose --profile multi-node up -d --build
```

### 2. Chạy automated test

```bash
./test-integration.sh
```

Script này sẽ:
- ✓ Kiểm tra Docker đang chạy
- ✓ Clean up containers cũ
- ✓ Build và start services
- ✓ Đợi PostgreSQL healthy
- ✓ Đợi Redis healthy
- ✓ Đợi Coordinator ready
- ✓ Đợi Storage Node connect
- ✓ Kiểm tra authentication
- ✓ Kiểm tra heartbeat (PING/PONG)
- ✓ Hiển thị logs

### 3. Xem logs

```bash
# Tất cả services
docker-compose logs -f

# Coordinator only
docker-compose logs -f coordinator

# Storage Node only
docker-compose logs -f storage-node-1

# Với timestamps
docker-compose logs -f --timestamps coordinator
```

### 4. Stop services

```bash
# Stop nhưng giữ data
docker-compose stop

# Stop và xóa containers (giữ volumes)
docker-compose down

# Stop và xóa tất cả (bao gồm volumes)
docker-compose down -v
```

## Kiểm tra thủ công

### 1. Kiểm tra services đang chạy

```bash
docker-compose ps
```

Expected output:
```
NAME                  STATUS              PORTS
coordinator-postgres  Up (healthy)        0.0.0.0:5432->5432/tcp
coordinator-redis     Up (healthy)        0.0.0.0:6379->6379/tcp
coordinator-server    Up (healthy)        0.0.0.0:8080-8082->8080-8082/tcp
storage-node-1        Up (healthy)        0.0.0.0:9001->9001/tcp
```

### 2. Kiểm tra Coordinator logs

```bash
docker-compose logs coordinator | grep -i "storage"
```

Expected output:
```
[INFO] Storage node server started on port 8081
[INFO] Storage Node connection established: <id>
[INFO] Storage Node authenticated: <id>
[INFO] PING received from <id>
```

### 3. Kiểm tra Storage Node logs

```bash
docker-compose logs storage-node-1 | grep -i "coordinator"
```

Expected output:
```
[INFO] Connecting to Coordinator: coordinator:8081
[INFO] Authenticated with Coordinator
[INFO] Connected to Coordinator successfully
[INFO] Heartbeat started (interval: 30s)
[INFO] PING sent to Coordinator
```

### 4. Kiểm tra database

```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U coordinator_user -d coordinator

# Check tables
\dt

# Check files table
SELECT * FROM files LIMIT 5;

# Exit
\q
```

### 5. Kiểm tra Redis

```bash
# Connect to Redis
docker-compose exec redis redis-cli

# Check keys
KEYS *

# Exit
exit
```

### 6. Test connectivity

```bash
# Test Coordinator client port
nc -zv localhost 8080

# Test Coordinator storage port
nc -zv localhost 8081

# Test Storage Node data port
nc -zv localhost 9001
```

## Troubleshooting

### Problem: Coordinator không start

**Check logs:**
```bash
docker-compose logs coordinator
```

**Common issues:**
- Database migration failed → Check PostgreSQL connection
- Redis connection failed → Check Redis is running
- Port already in use → Change ports in docker-compose.yml

**Solution:**
```bash
# Restart coordinator
docker-compose restart coordinator

# Rebuild if needed
docker-compose up -d --build coordinator
```

### Problem: Storage Node không connect

**Check logs:**
```bash
docker-compose logs storage-node-1
```

**Common issues:**
- Authentication failed → Check TICKET_SECRET matches
- Connection refused → Check Coordinator is running
- Wrong port → Should be 8081, not 8080

**Solution:**
```bash
# Check coordinator is ready
docker-compose logs coordinator | grep "Storage node server started"

# Restart storage node
docker-compose restart storage-node-1

# Check network
docker-compose exec storage-node-1 nc -zv coordinator 8081
```

### Problem: Heartbeat không hoạt động

**Check:**
```bash
# Wait 35 seconds then check
sleep 35
docker-compose logs coordinator | grep -i "ping"
docker-compose logs storage-node-1 | grep -i "ping"
```

**Expected:**
- Coordinator: "PING received from <id>"
- Storage Node: "PING sent to Coordinator"

### Problem: Build failed

**Java build error:**
```bash
# Check Maven version in container
docker run --rm maven:3.9-eclipse-temurin-17 mvn --version

# Manual build test
cd storage-node
mvn clean package
```

**Python build error:**
```bash
# Check requirements
cd coordinator-server
pip install -r requirements.txt
```

## Configuration

### Environment Variables

**Coordinator Server:**
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- `REDIS_HOST`, `REDIS_PORT`
- `SERVER_CLIENT_PORT=8080`
- `SERVER_STORAGE_PORT=8081`
- `STORAGE_NODE_SECRET=test-secret-12345` ← Must match Storage Node

**Storage Node:**
- `NODE_ID=storage-node-1`
- `NODE_PORT=9001`
- `COORDINATOR_HOST=coordinator`
- `COORDINATOR_PORT=8081`
- `TICKET_SECRET=test-secret-12345` ← Must match Coordinator

### Ports

| Service | Port | Description |
|---------|------|-------------|
| PostgreSQL | 5432 | Database |
| Redis | 6379 | Cache |
| Coordinator | 8080 | Client connections |
| Coordinator | 8081 | Storage node control plane |
| Coordinator | 8082 | Notification service |
| Storage Node 1 | 9001 | Data plane |
| Storage Node 2 | 9002 | Data plane (optional) |

### Volumes

- `postgres_data` - PostgreSQL data
- `redis_data` - Redis data
- `coordinator_logs` - Coordinator logs
- `storage_node_1_data` - Storage Node 1 data
- `storage_node_1_logs` - Storage Node 1 logs

## Advanced Usage

### Scale Storage Nodes

```bash
# Start with 2 nodes
docker-compose --profile multi-node up -d

# Check both nodes
docker-compose logs storage-node-1 | grep "Connected"
docker-compose logs storage-node-2 | grep "Connected"
```

### Custom Configuration

**Override coordinator config:**
```bash
# Create .env file
cat > coordinator-server/.env << EOF
STORAGE_NODE_SECRET=my-custom-secret
STORAGE_NODE_TIMEOUT=120
EOF

# Restart
docker-compose up -d coordinator
```

**Override storage node config:**
```bash
# Edit storage-node.docker.properties
vim storage-node/storage-node.docker.properties

# Rebuild
docker-compose up -d --build storage-node-1
```

### Development Mode

```bash
# Mount source code for live reload
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up
```

### Production Mode

```bash
# Use production secrets
export STORAGE_NODE_SECRET=$(openssl rand -hex 32)

# Start with restart policy
docker-compose up -d --restart=always
```

## Health Checks

All services have health checks:

```bash
# Check health status
docker-compose ps

# Manual health check
docker-compose exec coordinator python -c "import socket; s=socket.socket(); s.connect(('localhost', 8080)); s.close()"
docker-compose exec storage-node-1 nc -z localhost 9001
```

## Monitoring

### View resource usage

```bash
docker stats
```

### View network

```bash
docker network inspect lan-secure-file-system_ltm-network
```

### Inspect containers

```bash
docker-compose exec coordinator env
docker-compose exec storage-node-1 env
```

## Cleanup

```bash
# Stop all services
docker-compose down

# Remove volumes (WARNING: deletes all data)
docker-compose down -v

# Remove images
docker-compose down --rmi all

# Full cleanup
docker-compose down -v --rmi all --remove-orphans
docker system prune -a
```

## Next Steps

After successful integration test:

1. **Test upload flow** - Use example_upload_integration.py
2. **Test download flow** - Use example client
3. **Test failover** - Stop storage node and check coordinator logs
4. **Load testing** - Use multiple clients
5. **Security audit** - Review secrets and TLS configuration

## Support

If you encounter issues:

1. Check logs: `docker-compose logs -f`
2. Check health: `docker-compose ps`
3. Check network: `docker network inspect`
4. Restart services: `docker-compose restart`
5. Rebuild: `docker-compose up -d --build`

For more details, see:
- `STORAGE_NODE_INTEGRATION_FIX.md` - Implementation details
- `FIX_SUMMARY_VI.md` - Vietnamese summary
