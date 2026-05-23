"""
Service layer for frontend integration.

Provides high-level services that wrap the BackendClient,
making it easy for UI code to interact with backend.
"""

from typing import Optional, Dict, Any, Callable, List
from backend_client_sdk import BackendClient, BackendConfig
import logging

logger = logging.getLogger(__name__)


class BaseService:
    """Base service class."""
    
    def __init__(self, client: BackendClient):
        self.client = client


class AuthService(BaseService):
    """Authentication and authorization service."""
    
    def signup(
        self,
        username: str,
        email: str,
        password: str
    ) -> bool:
        """
        Register new account.
        
        Args:
            username: Username
            email: Email address
            password: Password
        
        Returns:
            True if successful
        """
        try:
            result = self.client.signup(username, email, password)
            logger.info(f"Signup successful for user {result.get('username')}")
            return True
        except Exception as e:
            logger.error(f"Signup failed: {e}")
            return False
    
    def login(self, username: str, password: str) -> bool:
        """
        Authenticate user.
        
        Args:
            username: Username
            password: Password
        
        Returns:
            True if successful
        """
        try:
            result = self.client.login(username, password)
            logger.info(f"Login successful, token expires at {result.get('expiresAt')}")
            return True
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False
    
    def logout(self) -> bool:
        """Logout user."""
        try:
            self.client.logout()
            logger.info("Logout successful")
            return True
        except Exception as e:
            logger.error(f"Logout failed: {e}")
            return False
    
    def is_authenticated(self) -> bool:
        """Check if user is authenticated."""
        return self.client.get_token() is not None


class RoomService(BaseService):
    """Room management service."""
    
    def create_room(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Create new room.
        
        Args:
            name: Room name
        
        Returns:
            Room data or None if failed
        """
        try:
            result = self.client.create_room(name)
            logger.info(f"Created room: {result.get('roomId')}")
            return result
        except Exception as e:
            logger.error(f"Failed to create room: {e}")
            return None
    
    def get_rooms(self) -> List[Dict[str, Any]]:
        """
        Get all rooms user is member of.
        
        Returns:
            List of room objects
        """
        try:
            result = self.client.list_rooms()
            rooms = result.get("rooms", [])
            logger.info(f"Retrieved {len(rooms)} rooms")
            return rooms
        except Exception as e:
            logger.error(f"Failed to get rooms: {e}")
            return []
    
    def get_room_members(self, room_id: str) -> List[Dict[str, Any]]:
        """
        Get all members in a room.
        
        Args:
            room_id: Room ID
        
        Returns:
            List of member objects
        """
        try:
            result = self.client.list_members(room_id)
            members = result.get("members", [])
            logger.info(f"Retrieved {len(members)} members from room {room_id}")
            return members
        except Exception as e:
            logger.error(f"Failed to get room members: {e}")
            return []
    
    def add_member(self, room_id: str, user_id: str, role: str = "MEMBER") -> bool:
        """
        Add user to room.
        
        Args:
            room_id: Room ID
            user_id: User ID to add
            role: Member role (OWNER, MEMBER, VIEWER)
        
        Returns:
            True if successful
        """
        try:
            self.client.add_member(room_id, user_id, role)
            logger.info(f"Added user {user_id} to room {room_id} with role {role}")
            return True
        except Exception as e:
            logger.error(f"Failed to add member: {e}")
            return False
    
    def remove_member(self, room_id: str, user_id: str) -> bool:
        """
        Remove user from room.
        
        Args:
            room_id: Room ID
            user_id: User ID to remove
        
        Returns:
            True if successful
        """
        try:
            self.client.remove_member(room_id, user_id)
            logger.info(f"Removed user {user_id} from room {room_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove member: {e}")
            return False
    
    def set_member_role(self, room_id: str, user_id: str, new_role: str) -> bool:
        """
        Change member role.
        
        Args:
            room_id: Room ID
            user_id: User ID
            new_role: New role (OWNER, MEMBER, VIEWER)
        
        Returns:
            True if successful
        """
        try:
            self.client.set_role(room_id, user_id, new_role)
            logger.info(f"Changed role for user {user_id} in room {room_id} to {new_role}")
            return True
        except Exception as e:
            logger.error(f"Failed to set member role: {e}")
            return False


class FileService(BaseService):
    """File management service."""
    
    def get_files(self, room_id: str) -> List[Dict[str, Any]]:
        """
        Get all files in room.
        
        Args:
            room_id: Room ID
        
        Returns:
            List of file objects
        """
        try:
            files = self.client.list_files(room_id)
            logger.info(f"Retrieved {len(files)} files from room {room_id}")
            return files
        except Exception as e:
            logger.error(f"Failed to get files: {e}")
            return []
    
    def get_file_detail(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed file information.
        
        Args:
            file_id: File ID
        
        Returns:
            File detail object or None if failed
        """
        try:
            result = self.client.file_detail(file_id)
            logger.info(f"Retrieved detail for file {file_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to get file detail: {e}")
            return None
    
    def get_file_versions(self, file_id: str) -> List[Dict[str, Any]]:
        """
        Get all versions of a file.
        
        Args:
            file_id: File ID
        
        Returns:
            List of version objects
        """
        try:
            result = self.client.file_versions(file_id)
            logger.info(f"Retrieved {len(result)} versions for file {file_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to get file versions: {e}")
            return []
    
    def delete_file(self, file_id: str) -> bool:
        """
        Delete a file.
        
        Args:
            file_id: File ID
        
        Returns:
            True if successful
        """
        try:
            self.client.delete_file(file_id)
            logger.info(f"Deleted file {file_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete file: {e}")
            return False


class UploadService(BaseService):
    """File upload service."""
    
    def init_upload(
        self,
        room_id: str,
        file_name: str,
        file_size: int,
        sha256_whole: str,
        chunk_count: int,
        chunk_size: int = 524288
    ) -> Optional[Dict[str, Any]]:
        """
        Initialize file upload.
        
        Args:
            room_id: Target room
            file_name: File name
            file_size: Total file size in bytes
            sha256_whole: SHA-256 hash of entire file
            chunk_count: Number of chunks
            chunk_size: Bytes per chunk
        
        Returns:
            Upload plan with ticket and storage node info, or None if failed
        """
        try:
            file_info = {
                "name": file_name,
                "size": file_size,
                "sha256Whole": sha256_whole,
                "chunkCount": chunk_count,
                "chunkSize": chunk_size
            }
            
            result = self.client.init_upload(room_id, file_info)
            
            if result.get("deduplicated"):
                logger.info(f"File {file_name} already exists (deduplicated)")
            else:
                logger.info(f"Initialized upload for {file_name} to {result.get('storageNodeId')}")
            
            return result
        except Exception as e:
            logger.error(f"Failed to initialize upload: {e}")
            return None


class DownloadService(BaseService):
    """File download service."""
    
    def init_download(
        self,
        file_id: str,
        version: int = None
    ) -> Optional[Dict[str, Any]]:
        """
        Initialize file download.
        
        Args:
            file_id: File to download
            version: Optional specific version
        
        Returns:
            Download plan with ticket and storage node info, or None if failed
        """
        try:
            result = self.client.init_download(file_id, version=version)
            logger.info(f"Initialized download for file {file_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to initialize download: {e}")
            return None
    
    def init_download_share(
        self,
        file_id: str,
        share_token: str
    ) -> Optional[Dict[str, Any]]:
        """
        Download file using public share token.
        
        Args:
            file_id: File to download
            share_token: Public share token
        
        Returns:
            Download plan or None if failed
        """
        try:
            result = self.client.init_download(
                file_id,
                share_token=share_token
            )
            logger.info(f"Initialized share download for file {file_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to initialize share download: {e}")
            return None
    
    def create_share_link(
        self,
        file_id: str,
        expiry_seconds: int = 86400
    ) -> Optional[str]:
        """
        Create public download link.
        
        Args:
            file_id: File to share
            expiry_seconds: Link expiration time
        
        Returns:
            Share token or None if failed
        """
        try:
            result = self.client.create_share_token(file_id, expiry_seconds)
            share_token = result.get("shareToken")
            logger.info(f"Created share token for file {file_id}")
            return share_token
        except Exception as e:
            logger.error(f"Failed to create share link: {e}")
            return None


class NotificationService(BaseService):
    """Real-time notification service."""
    
    def __init__(self, client: BackendClient):
        super().__init__(client)
        self._subscribed_rooms = set()
    
    def subscribe_room(self, room_id: str) -> bool:
        """
        Subscribe to room events.
        
        Args:
            room_id: Room ID
        
        Returns:
            True if successful
        """
        try:
            self.client.subscribe_room(room_id)
            self._subscribed_rooms.add(room_id)
            logger.info(f"Subscribed to room {room_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to subscribe to room: {e}")
            return False
    
    def unsubscribe_room(self, room_id: str) -> bool:
        """
        Unsubscribe from room events.
        
        Args:
            room_id: Room ID
        
        Returns:
            True if successful
        """
        try:
            self.client.unsubscribe_room(room_id)
            self._subscribed_rooms.discard(room_id)
            logger.info(f"Unsubscribed from room {room_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to unsubscribe from room: {e}")
            return False
    
    def on_new_file(self, callback: Callable) -> None:
        """Register callback for NEW_FILE events."""
        self.client.on_event("NEW_FILE", callback)
    
    def on_file_deleted(self, callback: Callable) -> None:
        """Register callback for FILE_DELETED events."""
        self.client.on_event("FILE_DELETED", callback)
    
    def on_member_added(self, callback: Callable) -> None:
        """Register callback for MEMBER_ADDED events."""
        self.client.on_event("MEMBER_ADDED", callback)
    
    def on_member_removed(self, callback: Callable) -> None:
        """Register callback for MEMBER_REMOVED events."""
        self.client.on_event("MEMBER_REMOVED", callback)
    
    def on_member_role_changed(self, callback: Callable) -> None:
        """Register callback for MEMBER_ROLE_CHANGED events."""
        self.client.on_event("MEMBER_ROLE_CHANGED", callback)
    
    def get_subscribed_rooms(self) -> set:
        """Get currently subscribed rooms."""
        return self._subscribed_rooms.copy()


class BackendService:
    """
    Main service facade that coordinates all backend interactions.
    
    Usage:
        service = BackendService()
        service.auth.login("user", "pass")
        rooms = service.rooms.get_rooms()
        files = service.files.get_files(room_id)
    """
    
    def __init__(self, config: BackendConfig = None):
        """
        Initialize backend service.
        
        Args:
            config: BackendConfig instance
        """
        self._client = BackendClient(config)
        
        # Initialize service layers
        self.auth = AuthService(self._client)
        self.rooms = RoomService(self._client)
        self.files = FileService(self._client)
        self.upload = UploadService(self._client)
        self.download = DownloadService(self._client)
        self.notifications = NotificationService(self._client)
    
    def connect(self) -> bool:
        """Connect to backend server."""
        try:
            self._client.connect()
            return True
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False
    
    def disconnect(self) -> None:
        """Disconnect from backend server."""
        self._client.disconnect()
    
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._client.is_connected()
    
    def reconnect(self) -> bool:
        """Reconnect to backend server."""
        return self._client.reconnect()
    
    def health_check(self) -> bool:
        """
        Perform health check.
        
        Returns:
            True if server is healthy
        """
        try:
            self._client.ping()
            return True
        except Exception:
            return False


# Example usage
if __name__ == "__main__":
    import time
    
    # Initialize service
    service = BackendService()
    
    try:
        # Connect
        if not service.connect():
            print("Failed to connect")
            exit(1)
        
        print("Connected to backend!")
        
        # Login
        if not service.auth.login("testuser", "password123"):
            print("Login failed")
            exit(1)
        
        print("Logged in!")
        
        # Get rooms
        rooms = service.rooms.get_rooms()
        print(f"Rooms: {len(rooms)}")
        
        for room in rooms:
            print(f"  - {room['name']} ({room['memberCount']} members)")
            
            # Get files in room
            files = service.files.get_files(room['roomId'])
            print(f"    Files: {len(files)}")
            
            for file in files[:3]:  # Show first 3 files
                print(f"      - {file['name']} ({file['size']} bytes)")
        
        # Subscribe to first room
        if rooms:
            room_id = rooms[0]['roomId']
            
            # Register event handlers
            service.notifications.on_new_file(
                lambda payload: print(f"New file: {payload['fileName']}")
            )
            service.notifications.on_member_added(
                lambda payload: print(f"Member added: {payload['username']}")
            )
            
            # Subscribe
            service.notifications.subscribe_room(room_id)
            print(f"Subscribed to room {room_id}")
            
            # Listen for 10 seconds
            print("Listening for events for 10 seconds...")
            time.sleep(10)
        
    finally:
        service.disconnect()
        print("Disconnected")
