# Storage Node Communication Module - Implementation Summary

## Overview

The Storage Node communication module provides persistent socket connections between the Coordinator Server and Storage Nodes. It handles authentication, heartbeat monitoring, ticket verification, and upload completion notifications.

**Requirements Implemented:** 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7

## Architecture

```
Storage Node → Coordinator (persistent connection)
    ↓
1. STORAGE_AUTH (shared secret)
2. PING/PONG (every 30s)
3. VERIFY_TICKET (on upload/download start)
4. UPLOAD_COMPLETE / UPLOAD_FAILED (on upload finish)
```

## Components

### 1. StorageNodeServer (`storage_node_server.py`)

Main socket server for Storage Node communication.

**Key Features:**
- Extends `BaseSocketServer` for connection management
- Authenticates Storage Nodes using shared secret
- Tracks node health via heartbeat timestamps
- Routes messages to appropriate services
- Automatic cleanup of unhealthy connections

**Configuration:**
- `host`: Bind address (default: '0.0.0.0')
- `port`: Listen port (from `config.server.storage_port`)
- `shared_secret`: Authentication secret (from `config.server.storage_node_secret`)
- `timeout_seconds`: Heartbeat timeout (from `config.server.storage_node_timeout`)

**Key Methods:**
- `start()`: Start server and health check thread
- `stop()`: Stop server and cleanup connections
- `get_connected_nodes()`: Get list of authenticated nodes

### 2. StorageNodeInfo

Tracks information about a connected Storage Node.

**Attributes:**
- `connection`: Socket connection
- `node_id`: Unique identifier
- `last_ping_time`: Timestamp of last PING
- `authenticated`: Authentication status
- `connected_at`: Connection timestamp

**Methods:**
- `update_ping_time()`: Update last ping timestamp
- `is_healthy(timeout_seconds)`: Check if node is healthy

## Message Handlers

### STORAGE_AUTH (Requirement 10.2)

Authenticates Storage Node connection using shared secret.

**Request Payload:**
```json
{
  "secret": "shared-secret-string"
}
```

**Success Response:**
```json
{
  "type": "STORAGE_AUTH_RESPONSE",
  "payload": {
    "status": "authenticated"
  }
}
```

**Error Responses:**
- `MISSING_SECRET`: Secret not provided
- `INVALID_SECRET`: Secret doesn't match

### PING/PONG (Requirements 10.3, 10.4)

Heartbeat mechanism to detect node availability.

**Request:** `PING` (empty payload)

**Response:**
```json
{
  "type": "PONG",
  "payload": {
    "timestamp": "2024-01-15T10:30:00Z"
  }
}
```

**Health Check:**
- Runs every 30 seconds in background thread
- Marks nodes unavailable if no PING for 90 seconds (configurable)
- Automatically closes unhealthy connections

### VERIFY_TICKET (Requirement 10.5)

Validates upload/download tickets for Storage Node.

**Request Payload:**
```json
{
  "ticket": "ticket-uuid"
}
```

**Success Response:**
```json
{
  "type": "TICKET_VALID",
  "payload": {
    "type": "upload",
    "fileId": "file-uuid",
    "userId": "user-uuid",
    "roomId": "room-uuid",
    "totalChunks": 20,
    "chunkSize": 524288,
    "sha256Whole": "hex-string",
    "storedName": "room/file",
    "expiresAt": "2024-01-15T11:00:00Z"
  }
}
```

**Error Response:**
```json
{
  "type": "TICKET_INVALID",
  "payload": {
    "error": "TICKET_NOT_FOUND"
  }
}
```

**Error Codes:**
- `TICKET_NOT_FOUND`: Ticket doesn't exist
- `TICKET_EXPIRED`: Ticket has expired
- `INTERNAL_ERROR`: Server error

### UPLOAD_COMPLETE (Requirement 10.6)

Notifies Coordinator that upload succeeded.

**Request Payload:**
```json
{
  "fileId": "file-uuid",
  "sha256Whole": "hex-string",
  "storedName": "room/file",
  "finalSize": 12345
}
```

**Success Response:**
```json
{
  "type": "ACK",
  "payload": {
    "status": "success"
  }
}
```

**Processing:**
1. Routes to `upload_service.handle_upload_complete()`
2. Updates file status to 'READY'
3. Broadcasts NEW_FILE notification
4. Writes audit log

**Error Responses:**
- `INVALID_PAYLOAD`: Missing required fields
- `FILE_NOT_FOUND`: File doesn't exist
- `HASH_MISMATCH`: SHA256 doesn't match expected
- `DATABASE_ERROR`: Database operation failed

### UPLOAD_FAILED (Requirement 10.7)

Notifies Coordinator that upload failed.

**Request Payload:**
```json
{
  "fileId": "file-uuid",
  "reason": "Disk full"
}
```

**Success Response:**
```json
{
  "type": "ACK",
  "payload": {
    "status": "success"
  }
}
```

**Processing:**
1. Routes to `upload_service.handle_upload_failed()`
2. Updates file status to 'DELETED'
3. Writes audit log

**Error Responses:**
- `INVALID_PAYLOAD`: Missing fileId
- `FILE_NOT_FOUND`: File doesn't exist
- `DATABASE_ERROR`: Database operation failed

## Configuration

### Environment Variables

Add to `.env` file:

```bash
# Storage Node Configuration
STORAGE_NODE_SECRET=change-this-secret-in-production
STORAGE_NODE_HEARTBEAT_INTERVAL=30
STORAGE_NODE_TIMEOUT=90
SERVER_STORAGE_PORT=8081
```

### Config Structure

```python
@dataclass
class ServerConfig:
    storage_port: int                    # Port for Storage Node connections
    storage_node_secret: str             # Shared secret for authentication
    storage_node_heartbeat_interval: int # PING interval (seconds)
    storage_node_timeout: int            # Timeout threshold (seconds)
```

## Usage Example

```python
from config import load_config
from database import Database
from redis_client import RedisClient
from ticket.ticket_service import TicketService
from upload.upload_service import UploadService
from storage_node.storage_node_server import StorageNodeServer

# Load configuration
config = load_config()

# Initialize dependencies
database = Database(config.database)
redis_client = RedisClient(config.redis)
ticket_service = TicketService(redis_client)
upload_service = UploadService(database, redis_client, ...)

# Create and start Storage Node server
storage_server = StorageNodeServer(
    host='0.0.0.0',
    port=config.server.storage_port,
    shared_secret=config.server.storage_node_secret,
    ticket_service=ticket_service,
    upload_service=upload_service,
    timeout_seconds=config.server.storage_node_timeout
)

storage_server.start()

# Server runs in background thread
# Get connected nodes
nodes = storage_server.get_connected_nodes()
print(f"Connected nodes: {len(nodes)}")

# Stop server
storage_server.stop()
```

## Security Considerations

1. **Shared Secret Authentication**
   - Storage Nodes must authenticate with shared secret
   - Secret should be strong and kept confidential
   - Change default secret in production

2. **Connection Validation**
   - All messages require authentication first
   - Unauthenticated connections cannot send PING, VERIFY_TICKET, etc.

3. **Heartbeat Monitoring**
   - Automatic detection of dead connections
   - Configurable timeout threshold
   - Prevents resource leaks from abandoned connections

## Testing

Comprehensive test suite in `test_storage_node.py`:

- **Connection Tests**: Authentication success/failure
- **Heartbeat Tests**: PING/PONG, timeout detection
- **Ticket Tests**: Valid/invalid ticket verification
- **Upload Tests**: UPLOAD_COMPLETE and UPLOAD_FAILED handling
- **Health Tests**: Node health tracking

Run tests:
```bash
pytest test_storage_node.py -v
```

## Integration Points

### Dependencies
- `protocol.socket_server.BaseSocketServer`: Base socket server
- `protocol.message.Message`: Message serialization
- `protocol.message_types.MessageType`: Message type definitions
- `ticket.ticket_service.TicketService`: Ticket verification
- `upload.upload_service.UploadService`: Upload completion handling

### Used By
- Main server application
- Integration examples
- System monitoring tools

## Performance Characteristics

- **Connection Overhead**: Minimal, persistent connections
- **Heartbeat Overhead**: One PING/PONG every 30 seconds per node
- **Ticket Verification**: Fast Redis lookup
- **Upload Notifications**: Synchronous database update + async broadcast

## Future Enhancements

1. **Multiple Storage Nodes**: Load balancing and failover
2. **Node Metrics**: Track upload counts, bandwidth, errors
3. **Dynamic Configuration**: Hot-reload of timeout settings
4. **TLS Support**: Encrypted connections for production
5. **Node Discovery**: Automatic registration and discovery

## Files Created

1. `storage_node/__init__.py` - Module initialization
2. `storage_node/storage_node_server.py` - Main server implementation
3. `storage_node/IMPLEMENTATION_SUMMARY.md` - This document
4. `example_storage_node_integration.py` - Usage example
5. `test_storage_node.py` - Test suite

## Configuration Updates

1. `config.py` - Added `storage_node_secret` to `ServerConfig`
2. `.env.example` - Added `STORAGE_NODE_SECRET` variable
