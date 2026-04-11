# Socket Protocol Implementation

This module implements the socket-based communication protocol for the Coordinator Server.

## Components

### 1. Message Types (`message_types.py`)

Defines all message types used in the protocol as an enum:
- Authentication: SIGNUP, LOGIN, LOGOUT
- Room Management: CREATE_ROOM, ADD_MEMBER, etc.
- File Operations: LIST_FILES, FILE_DETAIL, etc.
- Upload/Download: INIT_UPLOAD, INIT_DOWNLOAD
- Storage Node Communication: VERIFY_TICKET, UPLOAD_COMPLETE, etc.
- Notifications: SUBSCRIBE_ROOM, EVENT
- Health Check: PING, PONG, STATUS
- Error: ERROR

### 2. Frame Codec (`frame_codec.py`)

Implements length-prefixed frame encoding/decoding:

**Frame Format:**
```
[4 bytes: message length (big-endian)] [N bytes: JSON payload]
```

**Classes:**
- `FrameCodec`: Static methods for encoding/decoding frames
- `FrameBuffer`: Buffer for accumulating partial frames from socket reads

**Example:**
```python
from protocol.frame_codec import FrameCodec, FrameBuffer

# Encoding
message = b'{"type": "PING", "payload": {}}'
frame = FrameCodec.encode(message)
socket.sendall(frame)

# Decoding with buffer
buffer = FrameBuffer()
while True:
    data = socket.recv(4096)
    buffer.append(data)
    
    message = buffer.extract_frame()
    if message:
        # Process complete message
        break
```

### 3. Message (`message.py`)

Message serialization and deserialization:

**Message Structure:**
```json
{
  "type": "MESSAGE_TYPE",
  "requestId": "optional-uuid",
  "payload": {
    // Message-specific fields
  }
}
```

**Example:**
```python
from protocol.message import Message
from protocol.message_types import MessageType

# Create request
msg = Message.create_request(
    MessageType.LOGIN,
    {"username": "alice", "password": "secret"}
)

# Serialize
json_str = msg.to_json()
bytes_data = msg.to_bytes()

# Deserialize
msg = Message.from_json(json_str)
msg = Message.from_bytes(bytes_data)

# Create error response
error = Message.create_error(
    "INVALID_TOKEN",
    "Token is invalid or expired",
    request_id=msg.request_id
)
```

### 4. Base Socket Server (`socket_server.py`)

Base class for socket servers with connection management:

**Features:**
- Accept incoming connections
- Manage multiple concurrent connections
- Frame-based message encoding/decoding
- Message routing to handlers
- Request-response matching using requestId

**Example:**
```python
from protocol.socket_server import BaseSocketServer, SocketConnection
from protocol.message import Message
from protocol.message_types import MessageType

# Create server
server = BaseSocketServer("0.0.0.0", 8080, name="ClientServer")

# Register message handler
def handle_login(conn: SocketConnection, msg: Message):
    username = msg.payload.get("username")
    password = msg.payload.get("password")
    
    # Validate credentials...
    
    # Send response
    response = Message.create_response(
        MessageType.LOGIN_RESPONSE,
        {"token": "abc123", "userId": "user-uuid"},
        request_id=msg.request_id
    )
    conn.send_message(response)

server.register_handler(MessageType.LOGIN, handle_login)

# Start server
server.start()

# Server runs in background thread
# ...

# Stop server
server.stop()
```

## Request-Response Pattern

The protocol supports request-response matching using `requestId`:

1. Client sends request with auto-generated `requestId`
2. Server processes request
3. Server sends response with same `requestId`
4. Client matches response to original request

**Example:**
```python
# Client side
request = Message.create_request(
    MessageType.LIST_FILES,
    {"roomId": "room-123"}
)
# request.request_id is auto-generated UUID

# Server side
def handle_list_files(conn: SocketConnection, msg: Message):
    files = get_files(msg.payload["roomId"])
    
    response = Message.create_response(
        MessageType.LIST_FILES_RESPONSE,
        {"files": files},
        request_id=msg.request_id  # Match request ID
    )
    conn.send_message(response)
```

## Error Handling

Errors are sent as ERROR messages:

```python
error = Message.create_error(
    "PERMISSION_DENIED",
    "User does not have permission to perform this action",
    details={"userId": "user-123", "action": "DELETE_FILE"},
    request_id=msg.request_id
)
conn.send_message(error)
```

## Testing

Run tests with:
```bash
python -m pytest coordinator-server/test_protocol.py -v
```

Tests cover:
- Frame encoding/decoding
- Frame buffer accumulation
- Message serialization/deserialization
- Socket server connection management
- PING/PONG message exchange
