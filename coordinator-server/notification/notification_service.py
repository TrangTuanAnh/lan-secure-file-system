"""Notification service for broadcasting events to room subscribers."""
from typing import Dict, Any, Set
import threading
from logging_config import get_logger

logger = get_logger(__name__)


class NotificationService:
    """Handles real-time event broadcasting to room subscribers."""
    
    def __init__(self):
        """Initialize notification service."""
        # In-memory subscriber map: roomId -> Set[connection]
        # Thread-safe with lock for concurrent access
        self._subscribers: Dict[str, Set[Any]] = {}
        self._lock = threading.RLock()  # Reentrant lock for nested operations
    
    def add_subscriber(self, room_id: str, connection: Any) -> None:
        """
        Add a connection to the subscriber map for a room.
        Thread-safe operation.
        
        Args:
            room_id: Room identifier
            connection: Socket connection to add
        """
        with self._lock:
            if room_id not in self._subscribers:
                self._subscribers[room_id] = set()
            self._subscribers[room_id].add(connection)
            logger.info(f"Added subscriber to room {room_id}: {connection.connection_id}")
    
    def remove_subscriber(self, room_id: str, connection: Any) -> None:
        """
        Remove a connection from the subscriber map for a room.
        Thread-safe operation.
        
        Args:
            room_id: Room identifier
            connection: Socket connection to remove
        """
        with self._lock:
            if room_id in self._subscribers:
                self._subscribers[room_id].discard(connection)
                logger.info(f"Removed subscriber from room {room_id}: {connection.connection_id}")
                
                # Clean up empty sets
                if not self._subscribers[room_id]:
                    del self._subscribers[room_id]
    
    def remove_subscriber_from_all_rooms(self, connection: Any) -> None:
        """
        Remove a connection from all rooms it's subscribed to.
        Thread-safe operation. Used for connection cleanup on disconnect.
        
        Args:
            connection: Socket connection to remove
        """
        with self._lock:
            rooms_to_clean = []
            for room_id, subscribers in self._subscribers.items():
                if connection in subscribers:
                    subscribers.discard(connection)
                    logger.info(f"Removed subscriber from room {room_id} on disconnect: {connection.connection_id}")
                    
                    # Mark empty sets for cleanup
                    if not subscribers:
                        rooms_to_clean.append(room_id)
            
            # Clean up empty sets
            for room_id in rooms_to_clean:
                del self._subscribers[room_id]
    
    def _broadcast_event(self, room_id: str, event_data: Dict[str, Any]) -> None:
        """
        Broadcast an event to all subscribers of a room.
        Handles connection errors gracefully by removing dead connections.
        Thread-safe operation.
        
        Args:
            room_id: Room identifier
            event_data: Event payload to broadcast
        """
        from protocol.message import Message
        from protocol.message_types import MessageType
        
        with self._lock:
            # Get subscribers for this room (copy to avoid modification during iteration)
            subscribers = self._subscribers.get(room_id, set()).copy()
        
        if not subscribers:
            logger.debug(f"No subscribers for room {room_id}, skipping broadcast")
            return
        
        # Create event message
        event_message = Message(
            type=MessageType.EVENT,
            payload=event_data
        )
        
        # Track dead connections to remove
        dead_connections = []
        
        # Send to all subscribers
        for connection in subscribers:
            try:
                connection.send_message(event_message)
                logger.debug(f"Sent event to {connection.connection_id}: {event_data['eventType']}")
            except Exception as e:
                logger.warning(f"Failed to send event to {connection.connection_id}: {e}")
                dead_connections.append(connection)
        
        # Remove dead connections
        if dead_connections:
            with self._lock:
                for connection in dead_connections:
                    self.remove_subscriber_from_all_rooms(connection)
                    logger.info(f"Removed dead connection: {connection.connection_id}")
    
    def broadcast_member_added(
        self,
        room_id: str,
        user_id: str,
        username: str,
        role: str
    ) -> None:
        """
        Broadcast MEMBER_ADDED event to room subscribers.
        
        Args:
            room_id: Room identifier
            user_id: Added user ID
            username: Added user's username
            role: Assigned role
        """
        event_data = {
            "eventType": "MEMBER_ADDED",
            "roomId": room_id,
            "userId": user_id,
            "username": username,
            "role": role
        }
        
        logger.info(f"Broadcasting MEMBER_ADDED event for room {room_id}: user {user_id}")
        self._broadcast_event(room_id, event_data)
    
    def broadcast_member_removed(
        self,
        room_id: str,
        user_id: str,
        username: str
    ) -> None:
        """
        Broadcast MEMBER_REMOVED event to room subscribers.
        
        Args:
            room_id: Room identifier
            user_id: Removed user ID
            username: Removed user's username
        """
        event_data = {
            "eventType": "MEMBER_REMOVED",
            "roomId": room_id,
            "userId": user_id,
            "username": username
        }
        
        logger.info(f"Broadcasting MEMBER_REMOVED event for room {room_id}: user {user_id}")
        self._broadcast_event(room_id, event_data)
    
    def broadcast_role_updated(
        self,
        room_id: str,
        user_id: str,
        username: str,
        new_role: str
    ) -> None:
        """
        Broadcast ROLE_UPDATED event to room subscribers.
        
        Args:
            room_id: Room identifier
            user_id: User whose role changed
            username: User's username
            new_role: New role
        """
        event_data = {
            "eventType": "ROLE_UPDATED",
            "roomId": room_id,
            "userId": user_id,
            "username": username,
            "newRole": new_role
        }
        
        logger.info(f"Broadcasting ROLE_UPDATED event for room {room_id}: user {user_id} -> {new_role}")
        self._broadcast_event(room_id, event_data)
    
    def broadcast_file_deleted(
        self,
        room_id: str,
        file_id: str,
        file_name: str,
        deleted_by: str
    ) -> None:
        """
        Broadcast FILE_DELETED event to room subscribers.
        
        Args:
            room_id: Room identifier
            file_id: Deleted file ID
            file_name: Deleted file's name
            deleted_by: User who deleted the file
        """
        event_data = {
            "eventType": "FILE_DELETED",
            "roomId": room_id,
            "fileId": file_id,
            "fileName": file_name,
            "deletedBy": deleted_by
        }
        
        logger.info(f"Broadcasting FILE_DELETED event for room {room_id}: file {file_id}")
        self._broadcast_event(room_id, event_data)
    
    def broadcast_new_file(
        self,
        room_id: str,
        file_id: str,
        file_name: str,
        uploader: str
    ) -> None:
        """
        Broadcast NEW_FILE event to room subscribers.
        
        Args:
            room_id: Room identifier
            file_id: New file ID
            file_name: New file's name
            uploader: User who uploaded the file
        """
        event_data = {
            "eventType": "NEW_FILE",
            "roomId": room_id,
            "fileId": file_id,
            "fileName": file_name,
            "uploader": uploader
        }
        
        logger.info(f"Broadcasting NEW_FILE event for room {room_id}: file {file_id}")
        self._broadcast_event(room_id, event_data)
