# 📡 Backend API Reference - TCP Socket Protocol

**Version:** 1.0  
**Protocol:** TCP Socket + JSON Message + Length-prefix Frame (4-byte big-endian)  
**Base Port:** 8080  
**Default Host:** localhost

## Protocol Overview

### Frame Format
```
[4 bytes: message length (big-endian)] [N bytes: UTF-8 JSON message]
```

Example:
```
00 00 00 7B                          (123 bytes in big-endian)
{"type":"LOGIN","requestId":"...",   (123 bytes of JSON)
 "payload":{"username":"test"...}}
```

### Message Structure
```json
{
  "type": "MESSAGE_TYPE",
  "requestId": "uuid-1234-5678",     // Optional, auto-generated for requests
  "payload": {
    // Message-specific fields
  }
}
```

### Response Success Format
```json
{
  "type": "MESSAGE_TYPE_RESPONSE",
  "requestId": "uuid-1234-5678",     // Matches request
  "payload": {
    // Response-specific fields
  }
}
```

### Error Response Format
```json
{
  "type": "ERROR",
  "requestId": "uuid-1234-5678",     // Matches request
  "payload": {
    "error": {
      "code": "ERROR_CODE",
      "message": "Human readable message",
      "details": {                     // Optional
        "field": "additional info"
      }
    }
  }
}
```

---

## API Endpoints

### 🔐 AUTHENTICATION (No Token Required)

#### 1. SIGNUP
Register a new user account.

**Message Type:** `SIGNUP`

**Request Payload:**
```json
{
  "username": "string",           // 3-50 chars, alphanumeric + underscore
  "email": "string",              // Valid email format
  "password": "string"            // Min 6 characters
}
```

**Response (SIGNUP_RESPONSE):**
```json
{
  "userId": "550e8400-e29b-41d4-a716-446655440000",
  "username": "john_doe",
  "email": "john@example.com"
}
```

**Error Codes:**
- `INVALID_INPUT` - Missing required fields or format invalid
- `DUPLICATE_USERNAME` - Username already registered
- `DUPLICATE_EMAIL` - Email already registered
- `INTERNAL_ERROR` - Server error

**Example Request:**
```python
{
  "type": "SIGNUP",
  "requestId": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "payload": {
    "username": "alice",
    "email": "alice@example.com",
    "password": "securePass123"
  }
}
```

**Example Response:**
```python
{
  "type": "SIGNUP_RESPONSE",
  "requestId": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "payload": {
    "userId": "550e8400-e29b-41d4-a716-446655440000",
    "username": "alice",
    "email": "alice@example.com"
  }
}
```

---

#### 2. LOGIN
Authenticate user and get session token.

**Message Type:** `LOGIN`

**Request Payload:**
```json
{
  "username": "string",
  "password": "string"
}
```

**Response (LOGIN_RESPONSE):**
```json
{
  "token": "550e8400-e29b-41d4-a716-446655440000",
  "expiresAt": 1620000000             // Unix timestamp (seconds)
}
```

**Error Codes:**
- `INVALID_INPUT` - Missing username or password
- `USER_NOT_FOUND` - Username doesn't exist
- `INVALID_PASSWORD` - Password is incorrect
- `INTERNAL_ERROR` - Server error

**Example Request:**
```python
{
  "type": "LOGIN",
  "requestId": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "payload": {
    "username": "alice",
    "password": "securePass123"
  }
}
```

**Example Response:**
```python
{
  "type": "LOGIN_RESPONSE",
  "requestId": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "payload": {
    "token": "550e8400-e29b-41d4-a716-446655440000",
    "expiresAt": 1725000000
  }
}
```

---

#### 3. LOGOUT
Invalidate session token.

**Message Type:** `LOGOUT`

**Request Payload:**
```json
{
  "token": "string"          // Session token from LOGIN
}
```

**Response (LOGOUT_RESPONSE):**
```json
{
  "success": true
}
```

**Error Codes:**
- `INVALID_INPUT` - Missing token
- `INVALID_TOKEN` - Token invalid or expired
- `INTERNAL_ERROR` - Server error

---

### 🏢 ROOM MANAGEMENT (Token Required)

All room requests require `"token"` in payload.

#### 4. CREATE_ROOM
Create a new room (ADMIN only).

**Message Type:** `CREATE_ROOM`

**Request Payload:**
```json
{
  "token": "string",
  "name": "string"           // 1-100 chars
}
```

**Response (CREATE_ROOM_RESPONSE):**
```json
{
  "roomId": "550e8400-e29b-41d4-a716-446655440001",
  "name": "Project Alpha",
  "createdAt": 1620000000,
  "createdBy": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Error Codes:**
- `AUTH_REQUIRED` - Missing or invalid token
- `PERMISSION_DENIED` - User not ADMIN
- `INVALID_INPUT` - Invalid room name
- `DATABASE_ERROR` - Database error

---

#### 5. LIST_ROOMS
Get all rooms user is member of.

**Message Type:** `LIST_ROOMS`

**Request Payload:**
```json
{
  "token": "string"
}
```

**Response (LIST_ROOMS_RESPONSE):**
```json
{
  "rooms": [
    {
      "roomId": "550e8400-e29b-41d4-a716-446655440001",
      "name": "Project Alpha",
      "memberCount": 5,
      "myRole": "OWNER",              // OWNER, MEMBER, VIEWER
      "createdAt": 1620000000
    },
    {
      "roomId": "550e8400-e29b-41d4-a716-446655440002",
      "name": "Team Beta",
      "memberCount": 3,
      "myRole": "MEMBER",
      "createdAt": 1620000100
    }
  ]
}
```

**Error Codes:**
- `AUTH_REQUIRED` - Missing or invalid token
- `DATABASE_ERROR` - Database error

---

#### 6. LIST_MEMBERS
Get all members of a room.

**Message Type:** `LIST_MEMBERS`

**Request Payload:**
```json
{
  "token": "string",
  "roomId": "uuid"
}
```

**Response (LIST_MEMBERS_RESPONSE):**
```json
{
  "roomId": "550e8400-e29b-41d4-a716-446655440001",
  "members": [
    {
      "userId": "550e8400-e29b-41d4-a716-446655440000",
      "username": "alice",
      "email": "alice@example.com",
      "role": "OWNER",                // OWNER, MEMBER, VIEWER
      "joinedAt": 1620000000
    },
    {
      "userId": "550e8400-e29b-41d4-a716-446655440003",
      "username": "bob",
      "email": "bob@example.com",
      "role": "MEMBER",
      "joinedAt": 1620000050
    }
  ]
}
```

**Error Codes:**
- `AUTH_REQUIRED` - Missing or invalid token
- `ROOM_NOT_FOUND` - Room doesn't exist
- `PERMISSION_DENIED` - Not member of room
- `DATABASE_ERROR` - Database error

---

#### 7. ADD_MEMBER
Add user to room (OWNER only).

**Message Type:** `ADD_MEMBER`

**Request Payload:**
```json
{
  "token": "string",
  "roomId": "uuid",
  "userId": "uuid",
  "role": "string"           // OWNER, MEMBER, VIEWER
}
```

**Response (ADD_MEMBER_RESPONSE):**
```json
{
  "success": true,
  "roomId": "uuid",
  "userId": "uuid",
  "role": "MEMBER"
}
```

**Error Codes:**
- `AUTH_REQUIRED` - Missing or invalid token
- `ROOM_NOT_FOUND` - Room doesn't exist
- `USER_NOT_FOUND` - User doesn't exist
- `PERMISSION_DENIED` - Not room OWNER
- `INVALID_ROLE` - Invalid role value
- `ALREADY_MEMBER` - User already member
- `DATABASE_ERROR` - Database error

---

#### 8. REMOVE_MEMBER
Remove user from room (OWNER only).

**Message Type:** `REMOVE_MEMBER`

**Request Payload:**
```json
{
  "token": "string",
  "roomId": "uuid",
  "userId": "uuid"
}
```

**Response (REMOVE_MEMBER_RESPONSE):**
```json
{
  "success": true,
  "roomId": "uuid",
  "userId": "uuid"
}
```

**Error Codes:**
- `AUTH_REQUIRED` - Missing or invalid token
- `ROOM_NOT_FOUND` - Room doesn't exist
- `USER_NOT_FOUND` - User doesn't exist
- `PERMISSION_DENIED` - Not room OWNER
- `NOT_MEMBER` - User not member of room
- `DATABASE_ERROR` - Database error

---

#### 9. SET_ROLE
Change member role (OWNER only).

**Message Type:** `SET_ROLE`

**Request Payload:**
```json
{
  "token": "string",
  "roomId": "uuid",
  "userId": "uuid",
  "newRole": "string"       // OWNER, MEMBER, VIEWER
}
```

**Response (SET_ROLE_RESPONSE):**
```json
{
  "success": true,
  "roomId": "uuid",
  "userId": "uuid",
  "newRole": "MEMBER"
}
```

**Error Codes:**
- `AUTH_REQUIRED` - Missing or invalid token
- `ROOM_NOT_FOUND` - Room doesn't exist
- `USER_NOT_FOUND` - User doesn't exist
- `PERMISSION_DENIED` - Not room OWNER
- `INVALID_ROLE` - Invalid role value
- `NOT_MEMBER` - User not member of room
- `DATABASE_ERROR` - Database error

---

### 📁 FILE OPERATIONS (Token Required)

#### 10. LIST_FILES
Get all files in a room.

**Message Type:** `LIST_FILES`

**Request Payload:**
```json
{
  "token": "string",
  "roomId": "uuid"
}
```

**Response (LIST_FILES_RESPONSE):**
```json
{
  "roomId": "uuid",
  "files": [
    {
      "fileId": "550e8400-e29b-41d4-a716-446655440010",
      "name": "document.pdf",
      "size": 1048576,                // Bytes
      "sha256Hash": "abc123def456...",
      "status": "READY",              // UPLOADING, READY, DELETED
      "uploadedBy": "alice",
      "uploadedAt": 1620000000,
      "version": 1
    }
  ]
}
```

**Error Codes:**
- `AUTH_REQUIRED` - Missing or invalid token
- `ROOM_NOT_FOUND` - Room doesn't exist
- `PERMISSION_DENIED` - Not member of room
- `DATABASE_ERROR` - Database error

---

#### 11. FILE_DETAIL
Get detailed info about a file.

**Message Type:** `FILE_DETAIL`

**Request Payload:**
```json
{
  "token": "string",
  "fileId": "uuid"
}
```

**Response (FILE_DETAIL_RESPONSE):**
```json
{
  "fileId": "550e8400-e29b-41d4-a716-446655440010",
  "roomId": "550e8400-e29b-41d4-a716-446655440001",
  "name": "document.pdf",
  "size": 1048576,
  "sha256Hash": "abc123def456...",
  "status": "READY",
  "uploadedBy": "550e8400-e29b-41d4-a716-446655440000",
  "uploadedAt": 1620000000,
  "currentVersion": 1,
  "scanStatus": "CLEAN",              // CLEAN, INFECTED, UNKNOWN
  "scanTime": 1620000005,
  "mimeType": "application/pdf"
}
```

**Error Codes:**
- `AUTH_REQUIRED` - Missing or invalid token
- `FILE_NOT_FOUND` - File doesn't exist
- `PERMISSION_DENIED` - Not member of file's room
- `DATABASE_ERROR` - Database error

---

#### 12. FILE_VERSIONS
Get all versions of a file.

**Message Type:** `FILE_VERSIONS`

**Request Payload:**
```json
{
  "token": "string",
  "fileId": "uuid"
}
```

**Response (FILE_VERSIONS_RESPONSE):**
```json
{
  "fileId": "uuid",
  "versions": [
    {
      "version": 1,
      "sha256Hash": "abc123...",
      "uploadedBy": "alice",
      "uploadedAt": 1620000000
    },
    {
      "version": 2,
      "sha256Hash": "def456...",
      "uploadedBy": "bob",
      "uploadedAt": 1620000100
    }
  ]
}
```

**Error Codes:**
- `AUTH_REQUIRED` - Missing or invalid token
- `FILE_NOT_FOUND` - File doesn't exist
- `PERMISSION_DENIED` - Not member of file's room
- `DATABASE_ERROR` - Database error

---

#### 13. DELETE_FILE
Delete a file (OWNER/MEMBER only).

**Message Type:** `DELETE_FILE`

**Request Payload:**
```json
{
  "token": "string",
  "fileId": "uuid"
}
```

**Response (DELETE_FILE_RESPONSE):**
```json
{
  "success": true,
  "fileId": "uuid"
}
```

**Error Codes:**
- `AUTH_REQUIRED` - Missing or invalid token
- `FILE_NOT_FOUND` - File doesn't exist
- `PERMISSION_DENIED` - Not member of file's room
- `DATABASE_ERROR` - Database error

---

### 📤 UPLOAD CONTROL (Token Required)

#### 14. INIT_UPLOAD
Initialize file upload.

**Message Type:** `INIT_UPLOAD`

**Request Payload:**
```json
{
  "token": "string",
  "roomId": "uuid",
  "fileInfo": {
    "name": "document.pdf",
    "size": 10485760,               // Total file size in bytes
    "sha256Whole": "abc123...",     // SHA-256 of entire file
    "chunkCount": 20,               // Number of chunks
    "chunkSize": 524288             // Bytes per chunk (usually 512KB)
  },
  "storageAddress": "localhost:8888" // Optional, defaults to first healthy node
}
```

**Response (UPLOAD_PLAN):**
```json
{
  "uploadId": "550e8400-e29b-41d4-a716-446655440020",
  "fileId": "550e8400-e29b-41d4-a716-446655440021",
  "storageNodeId": "node-1",
  "storageNodeIp": "192.168.1.100",
  "storageNodePort": 8888,
  "deduplicated": false,            // true if file already exists (no upload needed)
  "ticket": {
    "sessionId": "550e8400-e29b-41d4-a716-446655440022",
    "fileId": "550e8400-e29b-41d4-a716-446655440021",
    "ticketNodeId": "node-1",
    "ticketExpiry": 1620001800,     // Unix timestamp (30 min TTL)
    "ticketSignature": "hmac_sig_here"
  },
  "chunkSize": 524288
}
```

**For Deduplicated Files:**
```json
{
  "deduplicated": true,
  "message": "File already exists with this hash"
  // File is immediately READY, no need to upload chunks
}
```

**Error Codes:**
- `AUTH_REQUIRED` - Missing or invalid token
- `ROOM_NOT_FOUND` - Room doesn't exist
- `PERMISSION_DENIED` - Not member of room or not MEMBER/OWNER
- `INVALID_INPUT` - Missing fileInfo fields
- `STORAGE_NODE_UNAVAILABLE` - No healthy storage node
- `DATABASE_ERROR` - Database error

---

### 📥 DOWNLOAD CONTROL (Token or Share Token Required)

#### 15. INIT_DOWNLOAD (with auth token)
Initialize file download using authentication token.

**Message Type:** `INIT_DOWNLOAD`

**Request Payload:**
```json
{
  "token": "string",
  "fileId": "uuid",
  "version": 1                       // Optional, defaults to latest
}
```

**Response (DOWNLOAD_PLAN):**
```json
{
  "downloadId": "550e8400-e29b-41d4-a716-446655440030",
  "storageNodeId": "node-1",
  "storageNodeIp": "192.168.1.100",
  "storageNodePort": 8888,
  "ticket": {
    "sessionId": "550e8400-e29b-41d4-a716-446655440031",
    "fileId": "550e8400-e29b-41d4-a716-446655440010",
    "ticketNodeId": "node-1",
    "ticketExpiry": 1620001800,
    "ticketSignature": "hmac_sig_here"
  },
  "fileInfo": {
    "name": "document.pdf",
    "size": 10485760,
    "sha256Whole": "abc123...",
    "chunkCount": 20,
    "chunkSize": 524288
  }
}
```

#### 15b. INIT_DOWNLOAD (with share token)
Initialize file download using public share token (no auth required).

**Message Type:** `INIT_DOWNLOAD`

**Request Payload:**
```json
{
  "shareToken": "string",
  "fileId": "uuid"
}
```

**Response:** Same as above (DOWNLOAD_PLAN)

**Error Codes:**
- `AUTH_REQUIRED` - Missing token/shareToken
- `FILE_NOT_FOUND` - File doesn't exist
- `PERMISSION_DENIED` - User not member of file's room (only for auth token)
- `INVALID_TOKEN` - Token invalid or expired (only for auth token)
- `INVALID_SHARE_TOKEN` - Share token invalid or expired
- `STORAGE_NODE_UNAVAILABLE` - No healthy storage node
- `DATABASE_ERROR` - Database error

---

### 🔗 SHARE TOKENS (Token Required)

#### 16. CREATE_SHARE_TOKEN
Create public download link.

**Message Type:** `CREATE_SHARE_TOKEN`

**Request Payload:**
```json
{
  "token": "string",
  "fileId": "uuid",
  "expirySeconds": 86400            // Optional, 24h default
}
```

**Response (CREATE_SHARE_TOKEN_RESPONSE):**
```json
{
  "shareToken": "550e8400-e29b-41d4-a716-446655440040",
  "fileId": "uuid",
  "expiresAt": 1620086400,
  "downloadUrl": "http://localhost:8080/download?token=550e8400..."
}
```

**Error Codes:**
- `AUTH_REQUIRED` - Missing or invalid token
- `FILE_NOT_FOUND` - File doesn't exist
- `PERMISSION_DENIED` - Not member of file's room
- `DATABASE_ERROR` - Database error

---

### 🔔 NOTIFICATIONS (Token Required, Persistent)

#### 17. SUBSCRIBE_ROOM
Subscribe to real-time events in a room.

**Message Type:** `SUBSCRIBE_ROOM`

**Request Payload:**
```json
{
  "token": "string",
  "roomId": "uuid"
}
```

**Response (SUBSCRIBE_ROOM_RESPONSE):**
```json
{
  "success": true,
  "roomId": "uuid"
}
```

**After subscription, server sends EVENT messages:**
```json
{
  "type": "EVENT",
  "payload": {
    "eventType": "NEW_FILE",
    "roomId": "uuid",
    "fileId": "uuid",
    "fileName": "document.pdf",
    "uploadedBy": "alice",
    "uploadedAt": 1620000000,
    "fileSize": 1048576,
    "sha256Hash": "abc123..."
  }
}
```

**Event Types:**
- `NEW_FILE` - File uploaded to room
- `FILE_DELETED` - File deleted from room
- `MEMBER_ADDED` - New member joined room
- `MEMBER_REMOVED` - Member left room
- `MEMBER_ROLE_CHANGED` - Member role updated

**Error Codes:**
- `AUTH_REQUIRED` - Missing or invalid token
- `ROOM_NOT_FOUND` - Room doesn't exist
- `PERMISSION_DENIED` - Not member of room
- `INTERNAL_ERROR` - Server error

---

#### 18. UNSUBSCRIBE_ROOM
Unsubscribe from room events.

**Message Type:** `UNSUBSCRIBE_ROOM`

**Request Payload:**
```json
{
  "roomId": "uuid"
}
```

**Response (UNSUBSCRIBE_ROOM_RESPONSE):**
```json
{
  "success": true,
  "roomId": "uuid"
}
```

**Error Codes:**
- `ROOM_NOT_FOUND` - Room doesn't exist
- `INTERNAL_ERROR` - Server error

---

### ❤️ HEALTH & DIAGNOSTICS (No Token Required)

#### 19. PING
Health check.

**Message Type:** `PING`

**Request Payload:**
```json
{}
```

**Response (PONG):**
```json
{
  "timestamp": 1620000000
}
```

---

#### 20. STATUS
Server status.

**Message Type:** `STATUS`

**Request Payload:**
```json
{}
```

**Response (STATUS_RESPONSE):**
```json
{
  "status": "running",
  "serverTime": 1620000000,
  "databaseConnected": true,
  "redisConnected": true,
  "version": "1.0.0"
}
```

---

## Common Error Codes

| Code | HTTP Equiv | Meaning |
|------|-----------|---------|
| `INVALID_INPUT` | 400 | Missing or invalid fields |
| `AUTH_REQUIRED` | 401 | Token missing |
| `INVALID_TOKEN` | 401 | Token invalid or expired |
| `PERMISSION_DENIED` | 403 | User lacks permission |
| `NOT_FOUND` | 404 | Resource not found |
| `DUPLICATE_USERNAME` | 409 | Username already taken |
| `DUPLICATE_EMAIL` | 409 | Email already registered |
| `STORAGE_NODE_UNAVAILABLE` | 503 | No storage node available |
| `INTERNAL_ERROR` | 500 | Server error |
| `DATABASE_ERROR` | 500 | Database error |

---

## Implementation Notes

### Token Handling
- Token format: UUID string (36 chars)
- TTL: 24 hours (86400 seconds)
- Always include token in `payload.token` for authenticated requests

### File Metadata
- All timestamps: Unix timestamps (seconds since epoch)
- All sizes: Bytes
- SHA-256 hash: Hex string (64 chars)

### Connection Lifecycle
1. Client connects to server:8080
2. Send LOGIN request → receive token
3. For subscriptions: Send SUBSCRIBE_ROOM → receive events continuously
4. For non-subscription: Each request is independent
5. Close connection or send LOGOUT

### Chunked Upload
- File divided into chunks (default 512KB)
- INIT_UPLOAD returns Storage Node address and ticket
- Client connects to Storage Node:8888 for chunk transfer (separate protocol)
- Ticket is required for Storage Node authentication

### Real-time Events
- After SUBSCRIBE_ROOM succeeds, connection stays open
- Server sends EVENT messages asynchronously
- Keep connection alive for continuous updates
- Send UNSUBSCRIBE_ROOM to stop receiving events

---

## Implementation Checklist for Frontend

- [ ] TCP socket connection to localhost:8080
- [ ] Frame codec: read 4-byte big-endian length prefix
- [ ] JSON serialization/deserialization
- [ ] UUID generation for requestId
- [ ] Token storage (localStorage or equivalent)
- [ ] Request-response matching using requestId
- [ ] Error handling for all error codes
- [ ] Connection keep-alive for subscriptions
- [ ] Timeout handling (recommend 30s per request)
- [ ] Reconnection logic on socket close

