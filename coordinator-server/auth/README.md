# Authentication Module

This module implements user authentication for the Coordinator Server, including signup, login, logout, and token validation.

## Components

### 1. PasswordHasher (`password_hasher.py`)

Handles password hashing and verification using bcrypt with cost factor 12.

**Methods:**
- `hash(password: str) -> str`: Hash a password using bcrypt
- `verify(password: str, password_hash: str) -> bool`: Verify a password against a hash

**Example:**
```python
from auth.password_hasher import PasswordHasher

# Hash a password
hashed = PasswordHasher.hash("my_password")

# Verify a password
is_valid = PasswordHasher.verify("my_password", hashed)
```

### 2. AuthService (`auth_service.py`)

Core authentication service that handles user signup, login, logout, and token validation.

**Methods:**
- `signup(username, email, password)`: Register a new user
- `login(username, password)`: Authenticate user and create session
- `validate_token(token)`: Validate session token and retrieve user info
- `logout(token)`: Delete session and logout user

**Example:**
```python
from auth.auth_service import AuthService

auth_service = AuthService(database, redis_client, session_ttl=86400)

# Signup
success, user_id, error_code = auth_service.signup("john", "john@example.com", "password123")

# Login
success, token, expires_at, error_code = auth_service.login("john", "password123")

# Validate token
valid, session_data, error_code = auth_service.validate_token(token)

# Logout
success, error_code = auth_service.logout(token)
```

### 3. AuthHandlers (`auth_handlers.py`)

Message handlers that integrate authentication with the socket protocol.

**Methods:**
- `handle_signup(message)`: Handle SIGNUP message
- `handle_login(message)`: Handle LOGIN message
- `handle_logout(message)`: Handle LOGOUT message

**Example:**
```python
from auth.auth_handlers import AuthHandlers
from protocol.message import Message
from protocol.message_types import MessageType

handlers = AuthHandlers(auth_service)

# Handle signup
signup_msg = Message.create_request(
    message_type=MessageType.SIGNUP,
    payload={"username": "john", "email": "john@example.com", "password": "password123"}
)
response = handlers.handle_signup(signup_msg)
```

### 4. AuthMiddleware (`auth_middleware.py`)

Middleware for validating authentication tokens on protected requests.

**Methods:**
- `validate_request(message)`: Validate token from message payload
- `require_auth(handler)`: Decorator to require authentication for handlers

**Example:**
```python
from auth.auth_middleware import AuthMiddleware

middleware = AuthMiddleware(auth_service)

# Validate a request
valid, context, error_msg = middleware.validate_request(message)

if valid:
    # context contains userId and globalRole
    user_id = context['userId']
    global_role = context['globalRole']
```

## Data Storage

### PostgreSQL (users table)

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    global_role VARCHAR(10) NOT NULL DEFAULT 'USER',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Redis (session storage)

**Key format:** `session:{token_uuid}`

**Value (JSON):**
```json
{
  "userId": "user-uuid",
  "globalRole": "USER",
  "createdAt": "2025-01-15T10:00:00Z"
}
```

**TTL:** 24 hours (86400 seconds)

## Error Codes

| Code | Description |
|------|-------------|
| `DUPLICATE_USERNAME` | Username already exists |
| `DUPLICATE_EMAIL` | Email address already exists |
| `INVALID_CREDENTIALS` | Invalid username or password |
| `INVALID_TOKEN` | Token is invalid or expired |
| `AUTH_REQUIRED` | Authentication token is required |
| `INVALID_INPUT` | Invalid input parameters |
| `DATABASE_ERROR` | Database operation failed |
| `REDIS_ERROR` | Session storage operation failed |

## Message Protocol

### SIGNUP

**Request:**
```json
{
  "type": "SIGNUP",
  "requestId": "uuid",
  "payload": {
    "username": "john",
    "email": "john@example.com",
    "password": "password123"
  }
}
```

**Response (Success):**
```json
{
  "type": "SIGNUP_RESPONSE",
  "requestId": "uuid",
  "payload": {
    "userId": "user-uuid",
    "username": "john",
    "email": "john@example.com"
  }
}
```

**Response (Error):**
```json
{
  "type": "ERROR",
  "requestId": "uuid",
  "payload": {
    "error": {
      "code": "DUPLICATE_USERNAME",
      "message": "Username already exists"
    }
  }
}
```

### LOGIN

**Request:**
```json
{
  "type": "LOGIN",
  "requestId": "uuid",
  "payload": {
    "username": "john",
    "password": "password123"
  }
}
```

**Response (Success):**
```json
{
  "type": "LOGIN_RESPONSE",
  "requestId": "uuid",
  "payload": {
    "token": "session-token-uuid",
    "expiresAt": 1705324800
  }
}
```

### LOGOUT

**Request:**
```json
{
  "type": "LOGOUT",
  "requestId": "uuid",
  "payload": {
    "token": "session-token-uuid"
  }
}
```

**Response (Success):**
```json
{
  "type": "LOGOUT_RESPONSE",
  "requestId": "uuid",
  "payload": {
    "success": true
  }
}
```

## Testing

Run the authentication tests:

```bash
cd coordinator-server
python -m pytest test_auth.py -v
```

Run the integration example:

```bash
cd coordinator-server
python example_auth_integration.py
```

## Requirements

The authentication module implements the following requirements from the spec:

- **Requirement 1.1**: Validate username and email uniqueness
- **Requirement 1.2**: Return DUPLICATE_USERNAME or DUPLICATE_EMAIL errors
- **Requirement 1.3**: Hash password using bcrypt with cost factor 12
- **Requirement 1.4**: Insert user record into PostgreSQL
- **Requirement 1.5**: Query users table by username
- **Requirement 1.6**: Generate UUID access token
- **Requirement 1.7**: Store session in Redis with 24-hour TTL
- **Requirement 1.8**: Delete session from Redis on logout
- **Requirement 1.9**: Verify access token exists in Redis
- **Requirement 2.1**: Retrieve session data from Redis
- **Requirement 2.2**: Return INVALID_TOKEN error if not found
- **Requirement 2.3**: Extract userId and globalRole from session
- **Requirement 15.1**: Store access token in Redis with key format `session:{token}`
- **Requirement 15.2**: Set TTL to 24 hours
- **Requirement 15.3**: Store session value as JSON with userId, globalRole, createdAt
- **Requirement 15.5**: Delete access token from Redis on logout

## Security Considerations

1. **Password Hashing**: Uses bcrypt with cost factor 12 (2^12 iterations)
2. **Session Tokens**: UUID v4 tokens (128-bit random, non-guessable)
3. **Session Expiration**: Automatic expiration after 24 hours via Redis TTL
4. **Password Storage**: Never store plain text passwords, only bcrypt hashes
5. **Error Messages**: Generic error messages for authentication failures (don't reveal if username exists)
