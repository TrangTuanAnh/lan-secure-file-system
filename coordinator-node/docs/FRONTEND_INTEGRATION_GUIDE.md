# FRONTEND INTEGRATION GUIDE

**Goal:** Migrate Python frontend from mock data to real backend API

---

## Phase 1: Setup (1-2 hours)

### Step 1.1: Copy Backend Client SDK
```bash
# Copy these files to your frontend project:
cp backend_client_sdk.py frontend/network/
cp BACKEND_API_REFERENCE.md frontend/docs/
cp ASYNC_THREADING_ARCHITECTURE.md frontend/docs/
```

### Step 1.2: Install Dependencies
```bash
# Create requirements.txt
python-dotenv==0.20.0
pydantic==1.10.0  # For type-safe models

# If using PyQt5
PyQt5==5.15.7

# For testing
pytest==7.2.0
```

### Step 1.3: Create Project Structure
```bash
frontend/
├── network/
│   ├── __init__.py
│   └── backend_client_sdk.py
├── services/
│   ├── __init__.py
│   ├── base.py
│   ├── auth_service.py
│   ├── room_service.py
│   ├── file_service.py
│   └── backend_service.py
├── models/
│   ├── __init__.py
│   ├── user.py
│   ├── room.py
│   └── file.py
├── ui/
│   ├── __init__.py
│   ├── main_window.py
│   └── ... (existing UI files)
├── config.py
├── logger.py
└── main.py
```

---

## Phase 2: Data Models (1-2 hours)

### Step 2.1: Define Data Classes
Create `models/user.py`:
```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class User:
    user_id: str
    username: str
    email: str
    global_role: str
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)
```

Create `models/room.py`:
```python
from dataclasses import dataclass

@dataclass
class Room:
    room_id: str
    name: str
    member_count: int
    my_role: str  # OWNER, MEMBER, VIEWER
    created_at: int
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)

@dataclass
class Member:
    user_id: str
    username: str
    email: str
    role: str
    joined_at: int
```

Create `models/file.py`:
```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class File:
    file_id: str
    name: str
    size: int
    sha256_hash: str
    status: str  # UPLOADING, READY, DELETED
    uploaded_by: str
    uploaded_at: int
    version: int
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)
```

### Step 2.2: Create Enums
```python
# models/__init__.py
from enum import Enum

class UserRole(str, Enum):
    ADMIN = "ADMIN"
    USER = "USER"

class MemberRole(str, Enum):
    OWNER = "OWNER"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"

class FileStatus(str, Enum):
    UPLOADING = "UPLOADING"
    READY = "READY"
    DELETED = "DELETED"
```

---

## Phase 3: Service Layer (2-3 hours)

### Step 3.1: Create Base Service
Create `services/base.py`:
```python
from network.backend_client_sdk import BackendClient

class BaseService:
    def __init__(self, client: BackendClient):
        self.client = client
```

### Step 3.2: Implement Auth Service
Create `services/auth_service.py`:
```python
from services.base import BaseService
from models.user import User
import logging

logger = logging.getLogger(__name__)

class AuthService(BaseService):
    def signup(self, username: str, email: str, password: str) -> bool:
        try:
            result = self.client.signup(username, email, password)
            logger.info(f"Signup successful: {result['username']}")
            return True
        except Exception as e:
            logger.error(f"Signup failed: {e}")
            return False
    
    def login(self, username: str, password: str) -> bool:
        try:
            result = self.client.login(username, password)
            logger.info("Login successful")
            return True
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False
    
    def logout(self) -> bool:
        try:
            self.client.logout()
            return True
        except Exception as e:
            logger.error(f"Logout failed: {e}")
            return False
    
    def is_authenticated(self) -> bool:
        return self.client.get_token() is not None
```

### Step 3.3: Implement Room Service
Create `services/room_service.py`:
```python
from services.base import BaseService
from models.room import Room, Member
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

class RoomService(BaseService):
    def get_rooms(self) -> List[Room]:
        try:
            result = self.client.list_rooms()
            rooms = [Room.from_dict(r) for r in result.get("rooms", [])]
            logger.info(f"Retrieved {len(rooms)} rooms")
            return rooms
        except Exception as e:
            logger.error(f"Failed to get rooms: {e}")
            return []
    
    def create_room(self, name: str) -> Optional[Room]:
        try:
            result = self.client.create_room(name)
            room = Room.from_dict(result)
            logger.info(f"Created room: {room.room_id}")
            return room
        except Exception as e:
            logger.error(f"Failed to create room: {e}")
            return None
    
    def get_members(self, room_id: str) -> List[Member]:
        try:
            result = self.client.list_members(room_id)
            members = [Member.from_dict(m) for m in result.get("members", [])]
            return members
        except Exception as e:
            logger.error(f"Failed to get members: {e}")
            return []
    
    # ... add_member, remove_member, set_role, etc.
```

### Step 3.4: Implement File Service
Create `services/file_service.py`:
```python
from services.base import BaseService
from models.file import File
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

class FileService(BaseService):
    def get_files(self, room_id: str) -> List[File]:
        try:
            files = self.client.list_files(room_id)
            return [File.from_dict(f) for f in files]
        except Exception as e:
            logger.error(f"Failed to get files: {e}")
            return []
    
    def get_file_detail(self, file_id: str) -> Optional[File]:
        try:
            result = self.client.file_detail(file_id)
            return File.from_dict(result)
        except Exception as e:
            logger.error(f"Failed to get file detail: {e}")
            return None
    
    def delete_file(self, file_id: str) -> bool:
        try:
            self.client.delete_file(file_id)
            return True
        except Exception as e:
            logger.error(f"Failed to delete file: {e}")
            return False
    
    # ... get_versions, etc.
```

### Step 3.5: Main Service Facade
Create `services/backend_service.py`:
```python
from network.backend_client_sdk import BackendClient, BackendConfig
from services.auth_service import AuthService
from services.room_service import RoomService
from services.file_service import FileService
import logging

logger = logging.getLogger(__name__)

class BackendService:
    def __init__(self, host="localhost", port=8080):
        config = BackendConfig(host=host, port=port)
        self._client = BackendClient(config)
        
        self.auth = AuthService(self._client)
        self.rooms = RoomService(self._client)
        self.files = FileService(self._client)
    
    def connect(self) -> bool:
        try:
            self._client.connect()
            logger.info("Connected to backend")
            return True
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False
    
    def disconnect(self) -> None:
        self._client.disconnect()
    
    def is_connected(self) -> bool:
        return self._client.is_connected()
```

---

## Phase 4: UI Integration (4-6 hours)

### Step 4.1: Replace Mock Data
**Before (Mock):**
```python
def get_rooms(self):
    return MOCK_ROOMS  # Hard-coded list
```

**After (Real):**
```python
def get_rooms(self):
    self.worker.queue_task(
        func=self.service.rooms.get_rooms,
        on_success=self.on_rooms_loaded,
        on_error=self.on_rooms_error
    )

def on_rooms_loaded(self, rooms):
    self.room_list.set_rooms(rooms)
    self.status_label.setText(f"Loaded {len(rooms)} rooms")

def on_rooms_error(self, error):
    self.status_label.setText(f"Error: {error}")
    messagebox.showerror("Error", str(error))
```

### Step 4.2: Background Worker Setup
```python
# In your main window __init__:
from workers.async_worker import AsyncWorker

self.worker = AsyncWorker()
self.worker.start()

# In your main window __del__:
self.worker.stop()
```

### Step 4.3: Update Widget Event Handlers
Replace all mock data calls with service layer:

```python
# Old (Mock)
def on_create_room_click(self):
    name = self.room_name_input.text()
    new_room = create_mock_room(name)
    self.rooms_list.append(new_room)

# New (Real)
def on_create_room_click(self):
    name = self.room_name_input.text()
    self.worker.queue_task(
        func=self.service.rooms.create_room,
        args=(name,),
        on_success=self.on_room_created,
        on_error=self.on_create_room_error
    )

def on_room_created(self, room):
    messagebox.showinfo("Success", f"Created room: {room.name}")
    self.refresh_rooms()  # Reload list
```

---

## Phase 5: Real-time Events (1-2 hours)

### Step 5.1: Subscribe to Room Events
```python
# After room selection
def on_room_selected(self, room_id: str):
    self.current_room_id = room_id
    
    # Subscribe to events
    self.worker.queue_task(
        func=self.service.notifications.subscribe_room,
        args=(room_id,),
        on_success=lambda r: self.setup_event_handlers(),
        on_error=self.on_subscribe_error
    )

def setup_event_handlers(self):
    # Register callbacks
    self.service.notifications.on_new_file(
        lambda payload: self.on_file_uploaded(payload)
    )
    self.service.notifications.on_member_added(
        lambda payload: self.on_member_joined(payload)
    )

def on_file_uploaded(self, payload):
    # Update UI in real-time
    messagebox.showinfo(
        "New File",
        f"{payload['fileName']} uploaded by {payload['uploadedBy']}"
    )
    self.refresh_files()
```

---

## Phase 6: Testing (2-3 hours)

### Step 6.1: Unit Tests
Create `tests/test_services.py`:
```python
import pytest
from unittest.mock import Mock, patch
from services.auth_service import AuthService

@pytest.fixture
def mock_client():
    client = Mock()
    return client

def test_login_success(mock_client):
    service = AuthService(mock_client)
    mock_client.login.return_value = {
        "token": "test-token",
        "expiresAt": 1234567890
    }
    
    result = service.login("user", "pass")
    assert result is True

def test_login_failure(mock_client):
    service = AuthService(mock_client)
    mock_client.login.side_effect = Exception("Invalid password")
    
    result = service.login("user", "wrong")
    assert result is False
```

### Step 6.2: Integration Tests
```python
def test_full_login_flow():
    service = BackendService()
    assert service.connect()
    
    result = service.auth.login("testuser", "password123")
    assert result is True
    assert service.auth.is_authenticated()
    
    rooms = service.rooms.get_rooms()
    assert isinstance(rooms, list)
    
    service.disconnect()
```

---

## Phase 7: Production Readiness (1-2 hours)

### Checklist

- [ ] Replace all mock data with real service calls
- [ ] Implement error handling (try-except)
- [ ] Add loading indicators (show spinner while loading)
- [ ] Implement timeouts (prevent hanging)
- [ ] Add retry logic for failed requests
- [ ] Store token securely (local storage)
- [ ] Add session validation on app start
- [ ] Implement proper disconnect on exit
- [ ] Add logging to all important operations
- [ ] Test with slow network (use DevTools throttle)
- [ ] Test rapid clicks (no duplicates/errors)
- [ ] Test app close during pending request (no crash)

### Key Features to Implement

1. **Session Persistence**
```python
# Save token on login
with open('.session', 'w') as f:
    f.write(service.client.get_token())

# Load token on startup
if os.path.exists('.session'):
    with open('.session', 'r') as f:
        token = f.read()
        service.client.set_token(token)
```

2. **Error Handling**
```python
def safe_call(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except BackendConnectionException:
        messagebox.showerror("Error", "Lost connection to server")
    except TimeoutError:
        messagebox.showerror("Error", "Request timed out")
    except ValueError as e:
        messagebox.showerror("Error", str(e))
```

3. **Auto-refresh**
```python
def start_auto_refresh(self):
    self.refresh_timer = QTimer()
    self.refresh_timer.timeout.connect(self.refresh_files)
    self.refresh_timer.start(5000)  # Every 5 seconds
```

---

## File Migration Checklist

```
✅ Protocol understanding
  └─ TCP Socket + JSON
  └─ Frame codec (4-byte length prefix)
  └─ Request-response matching (requestId)

✅ Data models created
  └─ User, Room, Member, File classes
  └─ Conversion from dict

✅ Service layer implemented
  └─ AuthService
  └─ RoomService
  └─ FileService
  └─ BackendService facade

✅ UI integration
  └─ Remove all mock data references
  └─ Replace with service calls
  └─ Add loading indicators
  └─ Implement error dialogs

✅ Background threading
  └─ AsyncWorker for non-blocking I/O
  └─ Event handlers / callbacks
  └─ Proper cleanup on exit

✅ Real-time events
  └─ Subscribe to room
  └─ Event callbacks registered
  └─ UI updates on events

✅ Testing
  └─ Unit tests for services
  └─ Integration tests
  └─ Manual UI testing

✅ Production ready
  └─ Session persistence
  └─ Error handling
  └─ Timeout logic
  └─ Logging
  └─ App cleanup
```

---

## Troubleshooting

**Issue: "Connection refused"**
- Check if backend server is running
- Verify host/port in config
- Check firewall settings

**Issue: "Request timeout"**
- Backend might be slow
- Increase timeout in config
- Check network latency

**Issue: "GUI freezes"**
- Not using AsyncWorker
- Calling service.method() directly in event handler
- Use worker.queue_task() instead

**Issue: "Events not received"**
- Not subscribed to room
- Check notification_service.subscribe_room()
- Check event callback registered

**Issue: "Token invalid after restart"**
- Not persisting token
- Save/load token from file
- Check token expiration

---

## Performance Tips

1. **Cache data locally**
   - Don't reload room list every time
   - Invalidate cache on relevant events

2. **Batch requests**
   - Load rooms once, then subscribe for updates
   - Don't LIST_ROOMS every 5 seconds

3. **Lazy loading**
   - Don't load all files immediately
   - Load when user opens room
   - Implement pagination

4. **Connection pooling**
   - Reuse BackendClient instance
   - Keep connection alive
   - One client per app process

---

## Support

Refer to:
- `BACKEND_API_REFERENCE.md` - API details
- `ASYNC_THREADING_ARCHITECTURE.md` - Threading patterns
- `FRONTEND_FOLDER_STRUCTURE.md` - Project layout
- `backend_client_sdk.py` - SDK documentation

