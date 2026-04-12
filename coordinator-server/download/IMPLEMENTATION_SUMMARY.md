# Download Control Module - Implementation Summary

## Overview

The download control module implements the control plane for file downloads in the distributed file storage system. It handles download authorization via direct permissions (access tokens) and share tokens, generates download tickets for Storage Node verification, and manages share token lifecycle.

## Implementation Status

**Task 10: Implement download control module** - ✅ COMPLETED

### Subtasks Completed

- **10.1 Implement INIT_DOWNLOAD with direct permission** - ✅ COMPLETED
  - Verifies user is member of file's room or ADMIN
  - Selects file version (highest if not specified)
  - Generates download ticket with 15-minute expiration
  - Stores ticket metadata in Redis (fileId, storedName, sha256Whole, totalChunks, chunkSize, expiresAt)
  - Returns DOWNLOAD_PLAN with ticket, storageAddress, fileName, fileSize, sha256Whole, totalChunks, chunkSize
  - Writes audit log entry
  - Requirements: 5.1, 5.2, 5.3, 5.4, 11.3, 18.5

- **10.2 Implement share token creation** - ✅ COMPLETED
  - Verifies user is ADMIN, OWNER, or MEMBER of file's room
  - Generates 32 random bytes and encodes as hexadecimal (64-character token)
  - Inserts record into share_tokens table
  - Returns token string
  - Writes audit log entry
  - Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 11.4

- **10.3 Implement INIT_DOWNLOAD with share token** - ✅ COMPLETED
  - Executes atomic UPDATE on share_tokens incrementing download_count
  - Verifies download_count < max_downloads and expires_at > NOW()
  - Returns SHARE_TOKEN_EXPIRED or SHARE_TOKEN_EXHAUSTED error if validation fails
  - Generates download ticket
  - Returns DOWNLOAD_PLAN without requiring access token
  - Writes audit log entry
  - Requirements: 5.5, 5.6, 5.7, 5.8, 11.4

## Architecture

### Module Structure

```
coordinator-server/download/
├── __init__.py                 # Module initialization
├── download_service.py         # Core download service logic
├── download_handlers.py        # Socket message handlers
└── IMPLEMENTATION_SUMMARY.md   # This file
```

### Key Components

#### DownloadService

**Location:** `download/download_service.py`

**Responsibilities:**
- Download authorization with direct permissions
- Download authorization with share tokens
- Share token creation and management
- Download ticket generation
- Audit logging for download operations

**Key Methods:**

1. `handle_init_download_direct(user_id, global_role, file_id, version)` → `(success, download_plan, error_code)`
   - Verifies user has DOWNLOAD_FILE permission in file's room
   - Retrieves file details from database
   - Generates UUID download ticket
   - Stores ticket metadata in Redis with 15-minute TTL
   - Returns DOWNLOAD_PLAN with ticket and file information
   - Writes audit log entry

2. `create_share_token(user_id, global_role, file_id, max_downloads, expires_at)` → `(success, token_string, error_code)`
   - Verifies user has CREATE_SHARE_TOKEN permission
   - Generates 32 random bytes using `secrets.token_bytes(32)`
   - Encodes as hexadecimal (64 characters)
   - Inserts record into share_tokens table
   - Returns token string
   - Writes audit log entry

3. `handle_init_download_share(share_token, file_id)` → `(success, download_plan, error_code)`
   - Executes atomic UPDATE query with validation:
     ```sql
     UPDATE share_tokens
     SET download_count = download_count + 1
     WHERE token = %s
       AND file_id = %s
       AND download_count < max_downloads
       AND expires_at > NOW()
     RETURNING *
     ```
   - If UPDATE returns no rows, determines specific error (expired, exhausted, invalid)
   - Generates download ticket
   - Returns DOWNLOAD_PLAN
   - Writes audit log entry with USE_SHARE_TOKEN action

4. `select_file_version(room_id, original_name, version)` → `(success, file_data, error_code)`
   - Helper method to select specific version or latest version
   - Used for version-aware downloads

#### DownloadHandlers

**Location:** `download/download_handlers.py`

**Responsibilities:**
- Process socket messages for download operations
- Convert between socket message format and service calls
- Format response messages

**Key Methods:**

1. `handle_init_download(user_id, global_role, payload)` → `response_message`
   - Processes INIT_DOWNLOAD message with access token
   - Extracts fileId and optional version from payload
   - Calls `download_service.handle_init_download_direct()`
   - Returns DOWNLOAD_PLAN or ERROR message

2. `handle_init_download_share(payload)` → `response_message`
   - Processes INIT_DOWNLOAD message with share token
   - Extracts shareToken and fileId from payload
   - Calls `download_service.handle_init_download_share()`
   - Returns DOWNLOAD_PLAN or ERROR message

3. `handle_create_share_token(user_id, global_role, payload)` → `response_message`
   - Processes CREATE_SHARE_TOKEN message
   - Extracts fileId, maxDownloads, expiresAt from payload
   - Parses ISO 8601 timestamp
   - Calls `download_service.create_share_token()`
   - Returns SHARE_TOKEN_CREATED or ERROR message

## Data Flow

### Direct Download Flow

```
Client → INIT_DOWNLOAD (token, fileId, version?)
  ↓
DownloadHandlers.handle_init_download()
  ↓
DownloadService.handle_init_download_direct()
  ↓
1. Check permission (AuthorizationService)
2. Query file from PostgreSQL
3. Generate ticket (UUID)
4. Store ticket in Redis (15-min TTL)
5. Write audit log
  ↓
Client ← DOWNLOAD_PLAN (ticket, storageAddress, fileName, fileSize, sha256Whole, totalChunks, chunkSize)
```

### Share Token Creation Flow

```
Client → CREATE_SHARE_TOKEN (token, fileId, maxDownloads, expiresAt)
  ↓
DownloadHandlers.handle_create_share_token()
  ↓
DownloadService.create_share_token()
  ↓
1. Check permission (AuthorizationService)
2. Generate token (32 random bytes → hex)
3. Insert into share_tokens table
4. Write audit log
  ↓
Client ← SHARE_TOKEN_CREATED (token, fileId, maxDownloads, expiresAt)
```

### Share Token Download Flow

```
Client → INIT_DOWNLOAD (shareToken, fileId)
  ↓
DownloadHandlers.handle_init_download_share()
  ↓
DownloadService.handle_init_download_share()
  ↓
1. Atomic UPDATE share_tokens (increment download_count with validation)
2. If failed: determine error (expired, exhausted, invalid)
3. Query file from PostgreSQL
4. Generate ticket (UUID)
5. Store ticket in Redis (15-min TTL)
6. Write audit log (USE_SHARE_TOKEN)
  ↓
Client ← DOWNLOAD_PLAN (ticket, storageAddress, fileName, fileSize, sha256Whole, totalChunks, chunkSize)
```

## Database Schema

### share_tokens Table

```sql
CREATE TABLE share_tokens (
    id UUID PRIMARY KEY,
    token CHAR(64) UNIQUE NOT NULL,
    file_id UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES users(id),
    max_downloads INT NOT NULL,
    download_count INT NOT NULL DEFAULT 0,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_share_tokens_token ON share_tokens(token);
CREATE INDEX idx_share_tokens_file_id ON share_tokens(file_id);
```

**Key Design Decisions:**

1. **Atomic Counter Increment**: Uses PostgreSQL's atomic UPDATE with WHERE clause to ensure thread-safe token consumption
2. **Token Format**: 64-character hexadecimal string (32 random bytes) for security
3. **Expiration**: Stored as TIMESTAMPTZ, validated in SQL query for accuracy
4. **Cascade Delete**: Share tokens are deleted when file is deleted

## Redis Data Structures

### Download Tickets

**Key Format:** `ticket:{ticket_uuid}`

**Value:** JSON string
```json
{
  "type": "download",
  "fileId": "file-uuid",
  "storedName": "room-id/file-id",
  "sha256Whole": "hex-string",
  "totalChunks": 20,
  "chunkSize": 524288,
  "expiresAt": "2025-01-15T10:15:00Z"
}
```

**TTL:** 15 minutes (900 seconds)

## Error Handling

### Error Codes

| Code | Description | When |
|------|-------------|------|
| FILE_NOT_FOUND | File does not exist | File ID not found in database |
| FILE_NOT_READY | File not ready for download | File status is not 'READY' |
| PERMISSION_DENIED | Insufficient permissions | User not member of file's room and not ADMIN |
| INVALID_SHARE_TOKEN | Token invalid or mismatch | Token not found or file_id doesn't match |
| SHARE_TOKEN_EXPIRED | Token has expired | expires_at <= NOW() |
| SHARE_TOKEN_EXHAUSTED | No downloads remaining | download_count >= max_downloads |
| DATABASE_ERROR | Database operation failed | PostgreSQL query error |
| INVALID_INPUT | Missing required fields | Required parameters not provided |

### Error Response Format

```json
{
  "type": "ERROR",
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description"
  }
}
```

## Security Considerations

### Share Token Security

1. **Cryptographically Secure Random Generation**: Uses `secrets.token_bytes(32)` for token generation
2. **Atomic Counter**: Prevents race conditions in token consumption
3. **Expiration Validation**: Checked in SQL query for accuracy
4. **No Token Reuse**: Once exhausted, token cannot be reused

### Permission Checks

1. **Direct Download**: Requires user to be member of file's room or ADMIN
2. **Share Token Creation**: Requires ADMIN, OWNER, or MEMBER role
3. **Share Token Download**: No authentication required (token is the authorization)

### Ticket Security

1. **Short TTL**: 15-minute expiration reduces window for ticket theft
2. **UUID Format**: Non-guessable ticket identifiers
3. **Redis Storage**: Automatic expiration via TTL
4. **Single Use**: Storage Node should delete ticket after use (optional)

## Audit Logging

### Logged Actions

1. **DOWNLOAD** (Direct)
   - actor_id: User performing download
   - action: 'DOWNLOAD'
   - target_type: 'file'
   - target_id: File ID
   - room_id: File's room
   - detail: {original_name, version, method: 'direct'}
   - status: 'SUCCESS'

2. **CREATE_SHARE_TOKEN**
   - actor_id: User creating token
   - action: 'CREATE_SHARE_TOKEN'
   - target_type: 'share_token'
   - target_id: Token ID
   - room_id: File's room
   - detail: {file_id, original_name, max_downloads, expires_at}
   - status: 'SUCCESS'

3. **USE_SHARE_TOKEN**
   - actor_id: Token creator (not downloader)
   - action: 'USE_SHARE_TOKEN'
   - target_type: 'share_token'
   - target_id: Token ID
   - room_id: File's room
   - detail: {file_id, original_name, download_count, max_downloads}
   - status: 'SUCCESS'

## Testing

### Test Coverage

**Location:** `coordinator-server/test_download.py`

**Test Classes:**

1. **TestDownloadDirect**: Tests for direct download with access token
   - `test_init_download_success`: Successful download initialization
   - `test_init_download_permission_denied`: Permission denied for non-member
   - `test_init_download_admin_access`: ADMIN can download any file
   - `test_init_download_file_not_found`: Non-existent file handling

2. **TestShareToken**: Tests for share token creation and usage
   - `test_create_share_token_success`: Successful token creation
   - `test_create_share_token_permission_denied`: Permission denied for non-member
   - `test_init_download_with_share_token`: Download with valid token
   - `test_share_token_exhaustion`: Token exhaustion after max downloads
   - `test_share_token_expiration`: Expired token handling
   - `test_invalid_share_token`: Invalid token handling

3. **TestTicketGeneration**: Tests for ticket generation
   - `test_ticket_stored_in_redis`: Verify ticket stored in Redis with correct metadata

4. **TestAuditLogging**: Tests for audit logging
   - `test_download_audit_log`: Verify DOWNLOAD audit log
   - `test_share_token_creation_audit_log`: Verify CREATE_SHARE_TOKEN audit log
   - `test_share_token_usage_audit_log`: Verify USE_SHARE_TOKEN audit log

**Test Requirements:**
- PostgreSQL database running on localhost:5432
- Redis running on localhost:6379
- Database schema initialized (all migrations applied)

**Running Tests:**
```bash
cd coordinator-server
python -m pytest test_download.py -v
```

## Integration Points

### Dependencies

1. **Database**: PostgreSQL for file and share token storage
2. **RedisClient**: Redis for ticket storage
3. **AuthorizationService**: Permission checking
4. **AuditService**: Audit logging
5. **FileService**: File metadata queries (indirect via database)

### Integration with Other Modules

1. **Socket Server**: DownloadHandlers will be integrated into main socket server message routing
2. **Storage Node**: Storage Node will verify tickets by calling Coordinator via VERIFY_TICKET message
3. **Notification Module**: No direct integration (downloads don't trigger notifications)

## Configuration

### Environment Variables

```env
# Download ticket TTL (seconds)
DOWNLOAD_TICKET_TTL_SECONDS=900

# Storage node address
STORAGE_NODE_ADDRESS=localhost:9000
```

### Service Initialization

```python
from download.download_service import DownloadService

download_service = DownloadService(
    database=database,
    redis_client=redis_client,
    authorization_service=authorization_service,
    audit_service=audit_service,
    ticket_ttl_seconds=config.server.download_ticket_ttl_seconds,
    storage_address="localhost:9000"
)
```

## Future Enhancements

1. **Download Analytics**: Track download counts per file
2. **Bandwidth Throttling**: Limit download speed per user
3. **Download Resume**: Support partial downloads with Range headers
4. **Token Revocation**: Manual token revocation before expiration
5. **Token Usage History**: Track which IPs used each token
6. **Multi-File Tokens**: Single token for multiple files (zip download)

## Known Limitations

1. **No Download Progress Tracking**: Coordinator doesn't track chunk-level progress
2. **No Download Cancellation**: Once ticket is issued, download cannot be cancelled from Coordinator
3. **Token Creator Attribution**: USE_SHARE_TOKEN audit log attributes action to token creator, not actual downloader
4. **No Token Refresh**: Expired tokens cannot be refreshed, must create new token

## Compliance with Requirements

### Requirement 5: Download Control Plane

- ✅ 5.1: Verify user is member of file's room or ADMIN
- ✅ 5.2: Select file version (highest if not specified)
- ✅ 5.3: Generate download ticket with 15-minute expiration
- ✅ 5.4: Return DOWNLOAD_PLAN with ticket and file metadata
- ✅ 5.5: Execute atomic UPDATE on share_tokens
- ✅ 5.6: Verify download_count < max_downloads and expires_at > NOW()
- ✅ 5.7: Return SHARE_TOKEN_EXPIRED or SHARE_TOKEN_EXHAUSTED error
- ✅ 5.8: Generate download ticket without requiring access token

### Requirement 8: Share Token Management

- ✅ 8.1: Verify user is ADMIN, OWNER, or MEMBER
- ✅ 8.2: Generate 32 random bytes and encode as hexadecimal
- ✅ 8.3: Insert record into share_tokens table
- ✅ 8.4: Return token string
- ✅ 8.5: Write audit log entry for share token usage

### Requirement 11: Audit Logging

- ✅ 11.3: Write audit log for file operations (DOWNLOAD)
- ✅ 11.4: Write audit log for share token actions (CREATE_SHARE_TOKEN, USE_SHARE_TOKEN)

### Requirement 18: File Versioning

- ✅ 18.5: Select highest version when version not specified

## Conclusion

The download control module is fully implemented and ready for integration with the socket server. All three subtasks are complete:

1. ✅ Direct download with permission checking
2. ✅ Share token creation with secure random generation
3. ✅ Share token-based downloads with atomic counter management

The implementation follows the existing patterns in the codebase (auth, room, file, upload modules) and uses Python with PostgreSQL for persistent data and Redis for ticket storage.
