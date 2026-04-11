# Coordinator Server

The Coordinator Server is the control plane for a distributed file storage system. It manages authentication, authorization, room membership, file metadata, audit logging, and real-time notifications.

## Features

- User authentication with bcrypt password hashing
- Session management using Redis
- PostgreSQL database for persistent storage
- Database migrations using Alembic
- Structured JSON logging
- Configuration via environment variables

## Prerequisites

- Python 3.9+
- PostgreSQL 12+
- Redis 6+

## Setup

### 1. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Copy the example environment file and edit it:

```bash
cp .env.example .env
# Edit .env with your database and Redis credentials
```

### 4. Run Database Migrations

```bash
# Make sure PostgreSQL is running and the database exists
alembic upgrade head
```

### 5. Start the Server

```bash
python main.py
```

## Database Schema

The system uses the following tables:

- **users**: User accounts with authentication credentials
- **rooms**: File storage rooms/containers
- **room_members**: Room membership and roles
- **files**: File metadata and versioning
- **share_tokens**: Shareable download links
- **scan_reports**: Antivirus scan results
- **audit_logs**: Audit trail for all actions

## Configuration

All configuration is done via environment variables. See `.env.example` for available options.

Key configuration options:

- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`: PostgreSQL connection
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`: Redis connection
- `SERVER_CLIENT_PORT`, `SERVER_STORAGE_PORT`, `SERVER_NOTIFICATION_PORT`: Server ports
- `SESSION_TTL_SECONDS`: Session expiration time (default: 24 hours)
- `UPLOAD_CHUNK_SIZE`: Chunk size for file uploads (default: 512KB)

## Development

### Running Migrations

Create a new migration:

```bash
alembic revision -m "description of changes"
```

Apply migrations:

```bash
alembic upgrade head
```

Rollback last migration:

```bash
alembic downgrade -1
```

### Testing Connections

The main.py script tests database and Redis connections on startup.

## Architecture

- **Database Layer**: PostgreSQL with connection pooling
- **Cache Layer**: Redis for sessions and tickets
- **Configuration**: Environment-based configuration
- **Logging**: Structured JSON logging to stdout

## Next Steps

- Implement socket protocol and message handling
- Implement authentication module
- Implement authorization and permission checking
- Implement room management
- Implement file operations
- Implement real-time notifications
