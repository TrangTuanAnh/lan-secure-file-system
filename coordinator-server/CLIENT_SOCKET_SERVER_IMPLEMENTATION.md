# Client Socket Server Implementation

## Overview

The Client Socket Server is the main entry point for client connections to the Coordinator Server. It handles all client-facing operations including authentication, room management, file operations, uploads, downloads, and notifications.

## Architecture

### Components

1. **ClientSocketServer** (`client_socket_server.py`)
   - Extends `BaseSocketServer` from `protocol/socket_server.py`
   - Manages client connections and message routing
   - Integrates all service modules

2. **Message Routing**
   - Routes incoming messages to appropriate handlers based on message type
   - Applies authentication middleware to protected endpoints
   - Returns consistent error responses

3. **Error Handling**
   - Maps exceptions to error codes from the error catalog
   - Returns consistent error response format
   - Logs errors with appropriate context

## Supported Message Types

### Authentication (No Auth Required)
- `SIGNUP` - User registration
- `LOGIN` - User login
- `LOGOUT` - User logout

### Room Management (Auth Required)
- `CREATE_ROOM` - Create a new room
- `ADD_MEMBER` - Add member to room
- `REMOVE_MEMBER` - Remove member from room
- `SET_ROLE` - Change member role
- `LIST_ROOMS` - List user's rooms
- `LIST_MEMBERS` - List room members

### File Operations (Auth Required)
- `LIST_FILES` - List files in room
- `FILE_DETAIL` - Get file details
- `FILE_VERSIONS` - Get file version history
- `DELETE_FILE` - Delete a file

### Upload/Download (Auth Required)
- `INIT_UPLOAD` - Initialize file upload
- `INIT_DOWNLOAD` - Initialize file download (supports both auth token and share token)
- `CREATE_SHARE_TOKEN` - Create share token for file

### Notifications (Auth Required)
- `SUBSCRIBE_ROOM` - Subscribe to room events
- `UNSUBSCRIBE_ROOM` - Unsubscribe from room events

### Health Checks (No Auth Required)
- `PING` - Simple health check
- `STATUS` - Detailed system status

## Authentication Middleware

The server uses `AuthMiddleware` to validate access tokens on protected endpoints:

1. Extract token from message payload
2. Validate token with Redis
3. Attach user context (userId, globalRole) to request
4. Return error if token is invalid or missing

## Error Handling

All errors follow a consistent format:

```json
{
  "type": "ERROR",
  "requestId": "uuid",
  "payload": {
    "error": {
      "code": "ERROR_CODE",
      "message": "Human-readable message"
    }
  }
}
```

### Error Codes

- **AUTH_REQUIRED** - Authentication token missing
- **INVALID_TOKEN** - Token invalid or expired
- **PERMISSION_DENIED** - Insufficient permissions
- **INVALID_INPUT** - Invalid request parameters
- **INTERNAL_ERROR** - Unexpected server error
- (See design.md for complete error catalog)

## Connection Lifecycle

1. **Connection Established**
   - Client connects to server
   - Connection added to connection pool

2. **Message Processing**
   - Receive frame-encoded messages
   - Deserialize JSON payload
   - Route to appropriate handler
   - Apply authentication if required
   - Execute business logic
   - Return response

3. **Connection Closed**
   - Remove from connection pool
   - Clean up notification subscriptions
   - Log disconnection

## Integration with Main Server

The client socket server is initialized in `main.py`:

```python
client_server = ClientSocketServer(
    host='0.0.0.0',
    port=config.server.client_port,
    auth_service=auth_service,
    authorization_service=authorization_service,
    room_service=room_service,
    file_service=file_service,
    upload_service=upload_service,
    download_service=download_service,
    notification_service=notification_service,
    health_service=health_service
)
client_server.start()
```

## Testing

Tests are located in `test_client_socket_server.py`:

- Handler registration tests
- Authentication flow tests
- Message routing tests
- Error handling tests
- Connection cleanup tests

Run tests with:
```bash
python -m pytest coordinator-server/test_client_socket_server.py -v
```

## Requirements Satisfied

This implementation satisfies the following requirements from the spec:

### Task 18.1: Create socket server for client connections
- ✅ Listens on configured CLIENT_PORT
- ✅ Handles multiple concurrent connections
- ✅ Implements connection lifecycle management
- ✅ Requirement 10.1 satisfied

### Task 18.2: Implement message routing
- ✅ Routes messages to appropriate service handlers based on message type
- ✅ Applies authentication middleware to protected endpoints
- ✅ Handles errors and returns error responses
- ✅ Requirements 2.1, 2.2, 2.3 satisfied

### Task 18.3: Implement error handling
- ✅ Maps exceptions to error codes
- ✅ Returns consistent error response format
- ✅ Logs errors appropriately
- ✅ Requirements 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7 satisfied

## Future Enhancements

1. **Rate Limiting** - Add per-user rate limiting to prevent abuse
2. **Metrics** - Add Prometheus metrics for monitoring
3. **Connection Pooling** - Optimize connection management
4. **TLS Support** - Add encrypted connections
5. **Load Balancing** - Support multiple server instances
