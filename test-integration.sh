#!/bin/bash
set -e

echo "=========================================="
echo "LTM System Integration Test"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

# Detect docker compose command
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    print_error "Docker Compose is not installed"
    exit 1
fi

print_success "Using: $DOCKER_COMPOSE"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    print_error "Docker is not running. Please start Docker first."
    exit 1
fi

print_success "Docker is running"

# Clean up previous containers
print_info "Cleaning up previous containers..."
$DOCKER_COMPOSE down -v 2>/dev/null || true

# Build and start services
print_info "Building and starting services..."
$DOCKER_COMPOSE up -d --build

# Wait for services to be healthy
print_info "Waiting for services to be healthy..."
sleep 5

# Check PostgreSQL
print_info "Checking PostgreSQL..."
if $DOCKER_COMPOSE exec -T postgres pg_isready -U coordinator_user -d coordinator > /dev/null 2>&1; then
    print_success "PostgreSQL is healthy"
else
    print_error "PostgreSQL is not healthy"
    $DOCKER_COMPOSE logs postgres
    exit 1
fi

# Check Redis
print_info "Checking Redis..."
if $DOCKER_COMPOSE exec -T redis redis-cli ping > /dev/null 2>&1; then
    print_success "Redis is healthy"
else
    print_error "Redis is not healthy"
    $DOCKER_COMPOSE logs redis
    exit 1
fi

# Wait for Coordinator to be ready
print_info "Waiting for Coordinator Server to be ready..."
for i in {1..30}; do
    if $DOCKER_COMPOSE logs coordinator 2>&1 | grep -q "Server is ready to accept connections"; then
        print_success "Coordinator Server is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        print_error "Coordinator Server failed to start"
        $DOCKER_COMPOSE logs coordinator
        exit 1
    fi
    sleep 2
done

# Wait for Storage Node to connect
print_info "Waiting for Storage Node to connect..."
for i in {1..30}; do
    if $DOCKER_COMPOSE logs storage-node-1 2>&1 | grep -q "Connected to Coordinator successfully"; then
        print_success "Storage Node 1 connected to Coordinator"
        break
    fi
    if [ $i -eq 30 ]; then
        print_error "Storage Node 1 failed to connect"
        $DOCKER_COMPOSE logs storage-node-1
        exit 1
    fi
    sleep 2
done

# Check authentication
print_info "Checking Storage Node authentication..."
if $DOCKER_COMPOSE logs coordinator 2>&1 | grep -q "Storage Node authenticated"; then
    print_success "Storage Node authenticated successfully"
else
    print_error "Storage Node authentication failed"
    $DOCKER_COMPOSE logs coordinator | grep -i "storage"
    exit 1
fi

# Check heartbeat
print_info "Waiting for heartbeat (PING/PONG)..."
sleep 35  # Wait for first heartbeat (30s interval + buffer)
if $DOCKER_COMPOSE logs coordinator 2>&1 | grep -q "PING received"; then
    print_success "Heartbeat is working (PING received)"
else
    print_error "Heartbeat not detected"
    $DOCKER_COMPOSE logs coordinator | grep -i "ping"
    exit 1
fi

# Show service status
echo ""
echo "=========================================="
echo "Service Status"
echo "=========================================="
$DOCKER_COMPOSE ps

# Show recent logs
echo ""
echo "=========================================="
echo "Recent Coordinator Logs"
echo "=========================================="
$DOCKER_COMPOSE logs --tail=20 coordinator

echo ""
echo "=========================================="
echo "Recent Storage Node Logs"
echo "=========================================="
$DOCKER_COMPOSE logs --tail=20 storage-node-1

echo ""
echo "=========================================="
print_success "Integration test completed successfully!"
echo "=========================================="
echo ""
echo "Services are running:"
echo "  - Coordinator Server: http://localhost:8080 (client)"
echo "  - Coordinator Server: http://localhost:8081 (storage nodes)"
echo "  - Storage Node 1: localhost:9001"
echo "  - PostgreSQL: localhost:5432"
echo "  - Redis: localhost:6379"
echo ""
echo "To view logs:"
echo "  $DOCKER_COMPOSE logs -f coordinator"
echo "  $DOCKER_COMPOSE logs -f storage-node-1"
echo ""
echo "To stop services:"
echo "  $DOCKER_COMPOSE down"
echo ""
