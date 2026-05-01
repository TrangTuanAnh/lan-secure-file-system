# Ticket Management Module - Implementation Summary

## Overview

The ticket management module provides centralized ticket generation and verification for upload/download authorization. Storage Nodes verify tickets by calling the Coordinator via the VERIFY_TICKET message.

## Components

### 1. TicketService (`ticket_service.py`)

Core service for ticket lifecycle management.

**Key Methods:**
- `generate_upload_ticket()`: Creates upload ticket with 30-minute TTL
- `generate_download_ticket()`: Creates download ticket with 15-minute TTL
- `verify_ticket()`: Validates ticket existence and expiration
- `delete_ticket()`: Manual cleanup for consumed tickets (optional)

**Storage:**
- Tickets stored in Redis with automatic TTL expiration
- Key format: `ticket:{uuid}`
- Upload tickets: 30 minutes (1800 seconds)
- Download tickets: 15 minutes (900 seconds)

**Ticket Metadata:**

Upload ticket:
```json
{
  "type": "upload",
  "fileId": "uuid",
  "userId": "uuid",
  "roomId": "uuid",
  "totalChunks": 10,
  "chunkSize": 524288,
  "sha256Whole": "hash",
  "storedName": "path",
  "expiresAt": "ISO-8601-timestamp"
}
```

Download ticket:
```json
{
  "type": "download",
  "fileId": "uuid",
  "storedName": "path",
  "sha256Whole": "hash",
  "totalChunks": 20,
  "chunkSize": 524288,
  "expiresAt": "ISO-8601-timestamp"
}
```

### 2. TicketHandlers (`ticket_handlers.py`)

Protocol handlers for Storage Node communication.

**Key Methods:**
- `handle_verify_ticket()`: Processes VERIFY_TICKET requests from Storage Nodes

**Message Flow:**

Request (from Storage Node):
```json
{
  "type": "VERIFY_TICKET",
  "requestId": "uuid",
  "payload": {
    "ticketId": "uuid"
  }
}
```

Success Response:
```json
{
  "type": "TICKET_VALID",
  "requestId": "uuid",
  "payload": {
    "ticketId": "uuid",
    "metadata": { ... }
  }
}
```

Error Response:
```json
{
  "type": "TICKET_INVALID",
  "requestId": "uuid",
  "payload": {
    "ticketId": "uuid",
    "error": {
      "code": "TICKET_NOT_FOUND" | "TICKET_EXPIRED",
      "message": "..."
    }
  }
}
```

## Integration with Upload/Download Services

### Upload Flow

1. **INIT_UPLOAD** (Client → Coordinator)
   - Upload service validates permissions and file metadata
   - Calls `ticket_service.generate_upload_ticket()`
   - Returns UPLOAD_PLAN with ticket to client

2. **OPEN_UPLOAD** (Client → Storage Node)
   - Client sends ticket to Storage Node
   - Storage Node sends VERIFY_TICKET to Coordinator
   - Coordinator validates and returns ticket metadata
   - Storage Node accepts upload session

3. **Upload chunks** (Client → Storage Node)
   - Direct data transfer, no Coordinator involvement

4. **UPLOAD_COMPLETE** (Storage Node → Coordinator)
   - Storage Node notifies Coordinator
   - Coordinator updates file status to READY

### Download Flow

1. **INIT_DOWNLOAD** (Client → Coordinator)
   - Download service validates permissions or share token
   - Calls `ticket_service.generate_download_ticket()`
   - Returns DOWNLOAD_PLAN with ticket to client

2. **OPEN_DOWNLOAD** (Client → Storage Node)
   - Client sends ticket to Storage Node
   - Storage Node sends VERIFY_TICKET to Coordinator
   - Coordinator validates and returns ticket metadata
   - Storage Node accepts download session

3. **Download chunks** (Client → Storage Node)
   - Direct data transfer, no Coordinator involvement

## Requirements Coverage

### Requirement 6.1: Generate unique ticket string
✓ Implemented using UUID generation in `generate_upload_ticket()` and `generate_download_ticket()`

### Requirement 6.2: Create UUID or random string as ticket identifier
✓ Implemented using `str(uuid.uuid4())` for ticket IDs

### Requirement 6.3: Store upload ticket metadata in Redis
✓ Implemented in `generate_upload_ticket()` with metadata including fileId, userId, roomId, totalChunks, chunkSize, sha256Whole, storedName, expiresAt

### Requirement 6.4: Store download ticket metadata in Redis
✓ Implemented in `generate_download_ticket()` with metadata including fileId, storedName, sha256Whole, totalChunks, chunkSize, expiresAt

### Requirement 6.5: Set ticket expiration (30 min upload, 15 min download)
✓ Implemented with configurable TTL:
- Upload tickets: 1800 seconds (30 minutes)
- Download tickets: 900 seconds (15 minutes)

### Requirement 6.6: Storage Node sends VERIFY_TICKET to Coordinator
✓ Implemented in `handle_verify_ticket()` handler

### Requirement 6.7: Coordinator checks ticket existence and expiration
✓ Implemented in `verify_ticket()` method with Redis lookup and expiration check

### Requirement 6.8: Return ticket metadata if valid
✓ Implemented in `handle_verify_ticket()` returning TICKET_VALID with metadata

### Requirement 6.9: Return error response if invalid
✓ Implemented in `handle_verify_ticket()` returning TICKET_INVALID with error code

### Requirement 6.10: Remove ticket from storage when consumed or expired
✓ Implemented:
- Automatic expiration via Redis TTL
- Manual cleanup via `delete_ticket()` method
- Expired tickets deleted during verification

## Testing

### Unit Tests (`test_ticket.py`)
- ✓ Upload ticket generation
- ✓ Download ticket generation
- ✓ Valid ticket verification
- ✓ Non-existent ticket verification
- ✓ Expired ticket verification
- ✓ Manual ticket deletion
- ✓ TTL configuration
- ✓ Ticket ID uniqueness

### Handler Tests (`test_ticket_handlers.py`)
- ✓ VERIFY_TICKET with valid upload ticket
- ✓ VERIFY_TICKET with valid download ticket
- ✓ VERIFY_TICKET with non-existent ticket
- ✓ VERIFY_TICKET with expired ticket
- ✓ VERIFY_TICKET with missing ticketId field
- ✓ VERIFY_TICKET with internal error
- ✓ Request ID preservation

All tests passing: **17/17**

## Configuration

Ticket TTL values are configurable via environment variables:

```bash
# Upload ticket TTL (default: 1800 seconds = 30 minutes)
UPLOAD_TICKET_TTL_SECONDS=1800

# Download ticket TTL (default: 900 seconds = 15 minutes)
DOWNLOAD_TICKET_TTL_SECONDS=900
```

## Usage Example

```python
from ticket.ticket_service import TicketService
from ticket.ticket_handlers import TicketHandlers

# Initialize service
ticket_service = TicketService(
    redis_client=redis_client,
    upload_ticket_ttl_seconds=1800,
    download_ticket_ttl_seconds=900
)

# Generate upload ticket
ticket_id = ticket_service.generate_upload_ticket(
    file_id=file_id,
    user_id=user_id,
    room_id=room_id,
    total_chunks=10,
    chunk_size=524288,
    sha256_whole=sha256_hash,
    stored_name=stored_path
)

# Verify ticket (called by Storage Node)
is_valid, metadata, error = ticket_service.verify_ticket(ticket_id)

# Handle VERIFY_TICKET message
ticket_handlers = TicketHandlers(ticket_service)
response = ticket_handlers.handle_verify_ticket(verify_request)
```

## Design Decisions

### Redis vs In-Memory Storage
**Choice:** Redis with TTL
**Rationale:** 
- Automatic expiration handling
- Consistent with session storage
- Survives Coordinator restarts (if Redis persists)
- Fast O(1) lookups

**Trade-off:** Requires Redis dependency

### Ticket Format
**Choice:** UUID string
**Rationale:**
- Non-guessable (secure)
- Globally unique
- Standard format

**Alternative:** HMAC-signed tickets (self-verifying, no callback needed, but cannot revoke)

### Verification via Socket Callback
**Choice:** Storage Node calls Coordinator via VERIFY_TICKET
**Rationale:**
- Simple implementation
- Coordinator maintains full control
- Can revoke tickets

**Trade-off:** Adds one round-trip at session start

### Manual Cleanup
**Choice:** Optional manual cleanup via `delete_ticket()`
**Rationale:**
- Redis TTL handles automatic expiration
- Manual cleanup allows immediate revocation
- Useful for consumed tickets

## Future Enhancements

1. **Ticket Usage Tracking**: Track when tickets are verified (for analytics)
2. **Ticket Revocation**: API to manually revoke tickets before expiration
3. **Ticket Metrics**: Monitor ticket generation/verification rates
4. **Alternative Storage**: Support in-memory storage for simpler deployments
5. **Ticket Renewal**: Allow extending ticket expiration for long uploads

## Files Created

- `coordinator-server/ticket/__init__.py`
- `coordinator-server/ticket/ticket_service.py`
- `coordinator-server/ticket/ticket_handlers.py`
- `coordinator-server/ticket/IMPLEMENTATION_SUMMARY.md`
- `coordinator-server/test_ticket.py`
- `coordinator-server/test_ticket_handlers.py`
- `coordinator-server/example_ticket_integration.py`
