# Recommended Project Structure for Python Frontend

```
frontend/                          # Root of frontend application
│
├── main.py                        # Entry point - starts GUI app
│
├── config.py                      # Configuration (host, port, timeouts, etc.)
├── constants.py                   # App constants (sizes, colors, defaults)
├── logger.py                      # Logging setup
│
├── network/                       # Network layer
│   ├── __init__.py
│   ├── backend_client_sdk.py     # TCP socket client (from backend_client_sdk.py)
│   ├── frame_codec.py            # Frame encoding/decoding
│   └── exceptions.py             # Custom exceptions
│
├── services/                      # Service layer (business logic)
│   ├── __init__.py
│   ├── base.py                   # Base service class
│   ├── auth_service.py           # AuthService
│   ├── room_service.py           # RoomService
│   ├── file_service.py           # FileService
│   ├── upload_service.py         # UploadService
│   ├── download_service.py       # DownloadService
│   ├── notification_service.py   # NotificationService
│   └── backend_service.py        # Main service facade
│
├── models/                        # Data models
│   ├── __init__.py
│   ├── user.py                   # User model
│   ├── room.py                   # Room model
│   ├── file.py                   # File model
│   └── event.py                  # Event types
│
├── ui/                            # UI layer
│   ├── __init__.py
│   ├── main_window.py            # Main application window
│   ├── dialogs/                  # Modal dialogs
│   │   ├── __init__.py
│   │   ├── login_dialog.py
│   │   ├── signup_dialog.py
│   │   ├── create_room_dialog.py
│   │   └── share_dialog.py
│   ├── widgets/                  # Reusable custom widgets
│   │   ├── __init__.py
│   │   ├── room_list_widget.py
│   │   ├── file_list_widget.py
│   │   ├── member_list_widget.py
│   │   └── status_bar.py
│   ├── pages/                    # Main UI pages
│   │   ├── __init__.py
│   │   ├── login_page.py
│   │   ├── dashboard_page.py
│   │   ├── room_page.py
│   │   └── file_detail_page.py
│   └── styles.py                 # CSS/theme styles (for PyQt/PySide)
│
├── workers/                       # Background worker threads
│   ├── __init__.py
│   ├── async_worker.py           # AsyncWorker class
│   ├── login_worker.py           # Login background task
│   ├── file_sync_worker.py       # File list sync
│   └── notification_worker.py    # Event listener
│
├── managers/                      # State/context managers
│   ├── __init__.py
│   ├── session_manager.py        # Current user session
│   ├── room_manager.py           # Current room context
│   ├── file_manager.py           # File operations context
│   └── cache_manager.py          # Local data caching
│
├── utils/                         # Utility functions
│   ├── __init__.py
│   ├── validators.py             # Input validation
│   ├── formatters.py             # Data formatting (dates, sizes)
│   ├── crypto.py                 # Crypto helpers (hashing, etc.)
│   └── file_utils.py             # File operations helpers
│
├── assets/                        # Static resources
│   ├── icons/                    # Application icons
│   ├── images/                   # Images
│   ├── themes/                   # Theme files
│   └── fonts/                    # Custom fonts
│
├── tests/                         # Unit and integration tests
│   ├── __init__.py
│   ├── test_network.py           # Test backend client
│   ├── test_services.py          # Test service layer
│   ├── test_models.py            # Test data models
│   ├── test_utils.py             # Test utilities
│   └── fixtures.py               # Test fixtures/mocks
│
├── .env.example                   # Example environment variables
├── .gitignore                     # Git ignore rules
├── requirements.txt               # Python dependencies
├── README.md                      # Project documentation
└── DEVELOPMENT.md                # Development guide

```

## Detailed File Descriptions

### Root Level

**main.py**
```python
#!/usr/bin/env python3
import sys
from ui.main_window import MainWindow
from config import Config
from logger import setup_logging

if __name__ == "__main__":
    setup_logging()
    config = Config.load()
    app = MainWindow(config)
    sys.exit(app.run())
```

**config.py** - Configuration management
```python
from dataclasses import dataclass
import os

@dataclass
class BackendConfig:
    host: str
    port: int
    timeout: int
    socket_timeout: int
    
@dataclass
class Config:
    backend: BackendConfig
    # ... other config
    
    @classmethod
    def load(cls):
        host = os.getenv("BACKEND_HOST", "localhost")
        port = int(os.getenv("BACKEND_PORT", "8080"))
        return cls(
            backend=BackendConfig(host=host, port=port, ...)
        )
```

**logger.py** - Centralized logging
```python
import logging
import sys

def setup_logging(level=logging.INFO):
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('app.log')
        ]
    )
```

### network/ - Network communication

Isolates all backend communication logic. Imports:
- `backend_client_sdk.py` - Raw TCP client
- `frame_codec.py` - Protocol encoding
- Custom exceptions

### services/ - Business logic layer

High-level operations that wrap network calls.
```python
# services/__init__.py
from .auth_service import AuthService
from .room_service import RoomService
from .backend_service import BackendService

__all__ = ["AuthService", "RoomService", "BackendService"]
```

### models/ - Data classes

```python
# models/user.py
from dataclasses import dataclass

@dataclass
class User:
    user_id: str
    username: str
    email: str
    global_role: str

# models/room.py
@dataclass
class Room:
    room_id: str
    name: str
    member_count: int
    my_role: str
    created_at: int
```

### ui/ - GUI components

Separated into pages and reusable widgets.

```python
# ui/pages/dashboard_page.py
class DashboardPage:
    def __init__(self, service):
        self.service = service
        self.create_widgets()
    
    def create_widgets(self):
        # Create UI elements
        pass
    
    def refresh_rooms(self):
        # Load rooms from service
        pass

# ui/widgets/room_list_widget.py
class RoomListWidget:
    def __init__(self, on_room_click=None):
        self.on_room_click = on_room_click
        self.create_widgets()
    
    def set_rooms(self, rooms):
        # Update list
        pass
```

### workers/ - Background threads

Each worker handles one type of background task.

```python
# workers/login_worker.py
from workers.async_worker import AsyncWorker

class LoginWorker(AsyncWorker):
    def __init__(self, service, username, password):
        super().__init__()
        self.service = service
        self.username = username
        self.password = password
    
    def run(self):
        try:
            result = self.service.auth.login(
                self.username, 
                self.password
            )
            self.success.emit(result)
        except Exception as e:
            self.error.emit(str(e))
```

### managers/ - State management

Keep track of current user, room, etc.

```python
# managers/session_manager.py
class SessionManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        self.current_user = None
        self.token = None
    
    def set_user(self, user, token):
        self.current_user = user
        self.token = token
    
    def is_authenticated(self):
        return self.token is not None
```

### utils/ - Helper functions

```python
# utils/validators.py
def validate_username(username):
    if not username or len(username) < 3:
        return False, "Username must be at least 3 chars"
    if len(username) > 50:
        return False, "Username too long"
    return True, ""

# utils/formatters.py
def format_file_size(bytes):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024
    return f"{bytes:.1f} TB"

def format_timestamp(unix_ts):
    from datetime import datetime
    return datetime.fromtimestamp(unix_ts).strftime("%Y-%m-%d %H:%M:%S")
```

## Dependency Flow

```
main.py
  ├── ui/main_window.py
  │   ├── ui/pages/
  │   └── workers/
  │       └── network/backend_client_sdk.py
  │
  ├── managers/
  │   └── services/
  │       ├── models/
  │       └── network/backend_client_sdk.py
  │
  └── config.py
      └── logger.py
```

## Frontend-to-Backend Communication Flow

```
User clicks button in UI
    ↓
Page/Widget event handler
    ↓
Service method call (e.g., auth_service.login())
    ↓
Network request (backend_client_sdk)
    ↓
Background worker thread
    ↓
Response callback
    ↓
Update Manager / Cache
    ↓
Emit UI update signal
    ↓
Update widgets / redraw
```

## File Organization by Feature

```
Feature: User Authentication
├── network/backend_client_sdk.py       (raw login() call)
├── services/auth_service.py            (high-level login())
├── models/user.py                      (User dataclass)
├── ui/pages/login_page.py              (UI)
├── ui/dialogs/login_dialog.py          (Modal)
├── workers/login_worker.py             (Background task)
├── managers/session_manager.py         (Store token)
└── utils/validators.py                 (Validate input)

Feature: Room Management
├── services/room_service.py
├── models/room.py
├── ui/pages/dashboard_page.py
├── ui/widgets/room_list_widget.py
├── workers/room_sync_worker.py
├── managers/room_manager.py
└── utils/formatters.py
```

## Environment Variables (.env)

```
# Backend connection
BACKEND_HOST=localhost
BACKEND_PORT=8080
BACKEND_TIMEOUT=30

# UI
UI_THEME=dark  # dark | light
WINDOW_WIDTH=1200
WINDOW_HEIGHT=800

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/app.log

# Features
ENABLE_NOTIFICATIONS=true
ENABLE_AUTO_REFRESH=true
AUTO_REFRESH_INTERVAL=5  # seconds
```

## Python Dependency Tree

```
requirements.txt:

# GUI frameworks (choose one)
# PyQt5==5.15.7        # Professional, full-featured
# PySide6==6.4.0       # Qt bindings, similar to PyQt
# tkinter              # Built-in (no install needed)

# Backend client
requests==2.28.0       # For REST calls (if using REST instead of socket)

# Data models
pydantic==1.10.0       # Data validation

# Configuration
python-dotenv==0.20.0  # Load .env files

# Logging
python-json-logger==2.0.0  # Structured logging

# Testing
pytest==7.2.0
pytest-cov==4.0.0
pytest-asyncio==0.20.0

# Code quality
black==22.12.0
pylint==2.15.0
mypy==0.990
```

## Module Initialization Files

```python
# ui/__init__.py
from .main_window import MainWindow
from .pages import LoginPage, DashboardPage
from .widgets import RoomListWidget, FileListWidget

__all__ = ["MainWindow", "LoginPage", "DashboardPage", "RoomListWidget", "FileListWidget"]

# services/__init__.py
from .auth_service import AuthService
from .room_service import RoomService
from .file_service import FileService
from .backend_service import BackendService

__all__ = ["AuthService", "RoomService", "FileService", "BackendService"]

# models/__init__.py
from .user import User
from .room import Room
from .file import File
from .event import Event

__all__ = ["User", "Room", "File", "Event"]
```

## Development Workflow

1. **Add new feature:**
   - Create model in `models/`
   - Add service method in `services/`
   - Add UI widget in `ui/widgets/`
   - Create UI page in `ui/pages/`
   - Add worker if needed in `workers/`
   - Wire up in main window

2. **Test:**
   ```bash
   pytest tests/ -v
   pytest --cov=. tests/
   ```

3. **Code quality:**
   ```bash
   black .
   pylint network/ services/ ui/
   mypy .
   ```

4. **Run app:**
   ```bash
   python main.py
   ```

## Benefits of This Structure

✅ **Separation of Concerns** - Each layer has clear responsibility  
✅ **Testability** - Easy to mock services and test UI logic  
✅ **Reusability** - Services, models, widgets can be reused  
✅ **Maintainability** - Find code quickly, understand relationships  
✅ **Scalability** - Easy to add new features without touching existing code  
✅ **Threading Safety** - Clear boundaries for background operations  
✅ **Code Organization** - Logical grouping by responsibility, not by file type  

