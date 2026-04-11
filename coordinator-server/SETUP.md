# Coordinator Server Setup Guide

This guide walks you through setting up the Coordinator Server from scratch.

## Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.9 or higher**
- **PostgreSQL 12 or higher**
- **Redis 6 or higher**

## Quick Start

### 1. Automated Setup

Run the setup script:

```bash
cd coordinator-server
./setup.sh
```

This will:
- Create a Python virtual environment
- Install all dependencies
- Create a `.env` file from the template

### 2. Configure Environment

Edit the `.env` file with your database and Redis credentials:

```bash
nano .env  # or use your preferred editor
```

Key settings to configure:
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD` (if Redis has authentication)

### 3. Prepare Database

Create the PostgreSQL database:

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database and user
CREATE DATABASE coordinator;
CREATE USER coordinator_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE coordinator TO coordinator_user;
\q
```

### 4. Run Migrations

Apply database schema migrations:

```bash
source venv/bin/activate  # Activate virtual environment
alembic upgrade head
```

This will create all required tables:
- users
- rooms
- room_members
- files
- share_tokens
- scan_reports
- audit_logs

### 5. Test Setup

Verify that everything is configured correctly:

```bash
python test_setup.py
```

This will test:
- Configuration loading
- Database connectivity
- Redis connectivity
- Session storage operations

### 6. Start Server

```bash
python main.py
```

## Manual Setup

If you prefer to set up manually:

### 1. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

### 4. Run Migrations

```bash
alembic upgrade head
```

### 5. Test and Run

```bash
python test_setup.py
python main.py
```

## Using Makefile

The project includes a Makefile for common tasks:

```bash
make help       # Show available commands
make setup      # Run automated setup
make install    # Install dependencies
make migrate    # Run database migrations
make test       # Test connections
make run        # Start server
make clean      # Clean up generated files
```

## Project Structure

```
coordinator-server/
├── alembic/                    # Database migrations
│   ├── versions/               # Migration scripts
│   │   ├── 001_create_users_table.py
│   │   ├── 002_create_rooms_table.py
│   │   ├── 003_create_room_members_table.py
│   │   ├── 004_create_files_table.py
│   │   ├── 005_create_share_tokens_table.py
│   │   ├── 006_create_scan_reports_table.py
│   │   └── 007_create_audit_logs_table.py
│   ├── env.py                  # Alembic environment
│   └── script.py.mako          # Migration template
├── config.py                   # Configuration loader
├── database.py                 # PostgreSQL connection
├── redis_client.py             # Redis client
├── logging_config.py           # Structured logging
├── main.py                     # Main entry point
├── test_setup.py               # Setup verification
├── requirements.txt            # Python dependencies
├── alembic.ini                 # Alembic configuration
├── .env.example                # Environment template
├── .env                        # Your configuration (not in git)
├── setup.sh                    # Setup script
├── Makefile                    # Common commands
└── README.md                   # Project documentation
```

## Configuration Reference

### Database Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| DB_HOST | localhost | PostgreSQL host |
| DB_PORT | 5432 | PostgreSQL port |
| DB_NAME | coordinator | Database name |
| DB_USER | coordinator_user | Database user |
| DB_PASSWORD | secure_password | Database password |
| DB_POOL_SIZE | 20 | Connection pool size |

### Redis Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| REDIS_HOST | localhost | Redis host |
| REDIS_PORT | 6379 | Redis port |
| REDIS_PASSWORD | (empty) | Redis password |
| REDIS_POOL_SIZE | 10 | Connection pool size |

### Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| SERVER_CLIENT_PORT | 8080 | Client connection port |
| SERVER_STORAGE_PORT | 8081 | Storage node port |
| SERVER_NOTIFICATION_PORT | 8082 | Notification port |
| SESSION_TTL_SECONDS | 86400 | Session expiration (24h) |
| UPLOAD_TICKET_TTL_SECONDS | 1800 | Upload ticket TTL (30m) |
| DOWNLOAD_TICKET_TTL_SECONDS | 900 | Download ticket TTL (15m) |
| UPLOAD_CHUNK_SIZE | 524288 | Chunk size (512KB) |
| STORAGE_NODE_HEARTBEAT_INTERVAL | 30 | Heartbeat interval (30s) |
| STORAGE_NODE_TIMEOUT | 90 | Node timeout (90s) |

## Troubleshooting

### Database Connection Failed

- Verify PostgreSQL is running: `systemctl status postgresql` or `pg_ctl status`
- Check database exists: `psql -U postgres -l`
- Verify credentials in `.env` match database user
- Check PostgreSQL allows connections from your host (pg_hba.conf)

### Redis Connection Failed

- Verify Redis is running: `redis-cli ping`
- Check Redis configuration: `redis-cli CONFIG GET bind`
- If Redis requires password, set REDIS_PASSWORD in `.env`

### Migration Failed

- Ensure database exists and user has permissions
- Check Alembic configuration in `alembic.ini`
- View migration history: `alembic history`
- Check current version: `alembic current`

### Import Errors

- Ensure virtual environment is activated: `source venv/bin/activate`
- Reinstall dependencies: `pip install -r requirements.txt`

## Next Steps

After successful setup:

1. Review the requirements document: `.kiro/specs/coordinator-server/requirements.md`
2. Review the design document: `.kiro/specs/coordinator-server/design.md`
3. Implement socket protocol and message handling (Task 2)
4. Implement authentication module (Task 3)
5. Continue with remaining tasks in the implementation plan

## Support

For issues or questions:
- Check the design document for architecture details
- Review the requirements document for specifications
- Examine logs for error details (structured JSON format)
