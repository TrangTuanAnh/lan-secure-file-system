"""Example integration of notification module.

This example demonstrates how to integrate the notification module
into the main coordinator server.
"""
from database import Database
from auth.auth_service import AuthService
from auth.authorization_service import AuthorizationService
from audit.audit_service import AuditService
from notification.notification_service import NotificationService
from notification.notification_handlers import NotificationHandlers
from protocol.socket_server import BaseSocketServer, SocketConnection
from protocol.message_types import MessageType
from redis_client import RedisClient
from config import load_config


def setup_notification_module():
    """
    Set up notification module with all dependencies.
    
    Returns:
        Tuple of (NotificationService, NotificationHandlers)
    """
    # Load configuration
    config = load_config()
    
    # Initialize database
    database = Database(config.database)
    database.connect()
    
    # Initialize Redis
    redis_client = RedisClient(config.redis)
    redis_client.connect()
    
    # Initialize services
    audit_service = AuditService(database)
    auth_service = AuthService(database, redis_client, config.server.session_ttl_seconds, audit_service)
    authorization_service = AuthorizationService(database)
    notification_service = NotificationService()
    
    # Initialize notification handlers
    notification_handlers = NotificationHandlers(
        notification_service=notification_service,
        authorization_service=authorization_service,
        auth_service=auth_service
    )
    
    return notification_service, notification_handlers


def setup_notification_server():
    """
    Set up notification socket server with handlers.
    
    Returns:
        BaseSocketServer configured for notifications
    """
    # Load configuration
    config = load_config()
    
    # Set up notification module
    notification_service, notification_handlers = setup_notification_module()
    
    # Create socket server
    server = BaseSocketServer(
        host=config.server.host,
        port=config.server.notification_port,
        name="NotificationServer"
    )
    
    # Register handlers
    server.register_handler(
        MessageType.SUBSCRIBE_ROOM,
        notification_handlers.handle_subscribe_room
    )
    
    server.register_handler(
        MessageType.UNSUBSCRIBE_ROOM,
        notification_handlers.handle_unsubscribe_room
    )
    
    # Override connection closed callback to clean up subscriptions
    original_on_closed = server._on_connection_closed
    
    def on_connection_closed(connection: SocketConnection) -> None:
        # Remove connection from all subscribed rooms
        notification_service.remove_subscriber_from_all_rooms(connection)
        # Call original callback
        original_on_closed(connection)
    
    server._on_connection_closed = on_connection_closed
    
    return server


def example_subscribe_flow():
    """
    Example: Handle SUBSCRIBE_ROOM request from client.
    """
    from protocol.message import Message
    from protocol.message_types import MessageType
    
    # Set up module
    notification_service, notification_handlers = setup_notification_module()
    
    # Simulate authenticated connection
    from unittest.mock import Mock
    connection = Mock()
    connection.connection_id = "client-1:12345"
    
    # Simulate SUBSCRIBE_ROOM message
    message = Message(
        type=MessageType.SUBSCRIBE_ROOM,
        payload={
            'roomId': 'room-123'
        },
        request_id='req-456'
    )
    
    # Simulate authenticated user (would come from auth middleware)
    user_id = 'user-789'
    global_role = 'USER'
    
    # Handle the message
    notification_handlers.handle_subscribe_room(
        connection=connection,
        message=message,
        user_id=user_id,
        global_role=global_role
    )
    
    print(f"Connection subscribed to room-123")
    print(f"Active subscribers: {len(notification_service._subscribers.get('room-123', set()))}")


def example_broadcast_flow():
    """
    Example: Broadcast event to room subscribers.
    """
    from unittest.mock import Mock
    
    # Set up module
    notification_service, _ = setup_notification_module()
    
    # Create mock connections
    connection1 = Mock()
    connection1.connection_id = "client-1:12345"
    connection1.send_message = Mock()
    
    connection2 = Mock()
    connection2.connection_id = "client-2:12346"
    connection2.send_message = Mock()
    
    # Subscribe connections to room
    notification_service.add_subscriber('room-123', connection1)
    notification_service.add_subscriber('room-123', connection2)
    
    print(f"Subscribers before broadcast: {len(notification_service._subscribers.get('room-123', set()))}")
    
    # Broadcast NEW_FILE event
    notification_service.broadcast_new_file(
        room_id='room-123',
        file_id='file-456',
        file_name='document.pdf',
        uploader='user-789'
    )
    
    # Verify both connections received the message
    print(f"Connection 1 send_message called: {connection1.send_message.called}")
    print(f"Connection 2 send_message called: {connection2.send_message.called}")


def example_connection_cleanup():
    """
    Example: Clean up subscriptions when connection closes.
    """
    from unittest.mock import Mock
    
    # Set up module
    notification_service, _ = setup_notification_module()
    
    # Create mock connection
    connection = Mock()
    connection.connection_id = "client-1:12345"
    
    # Subscribe to multiple rooms
    notification_service.add_subscriber('room-1', connection)
    notification_service.add_subscriber('room-2', connection)
    notification_service.add_subscriber('room-3', connection)
    
    print(f"Subscribed to rooms: room-1, room-2, room-3")
    print(f"Total rooms with subscribers: {len(notification_service._subscribers)}")
    
    # Simulate connection close
    notification_service.remove_subscriber_from_all_rooms(connection)
    
    print(f"After cleanup - Total rooms with subscribers: {len(notification_service._subscribers)}")


def example_dead_connection_handling():
    """
    Example: Handle dead connections during broadcast.
    """
    from unittest.mock import Mock
    
    # Set up module
    notification_service, _ = setup_notification_module()
    
    # Create mock connections
    good_connection = Mock()
    good_connection.connection_id = "client-1:12345"
    good_connection.send_message = Mock()
    
    dead_connection = Mock()
    dead_connection.connection_id = "client-2:12346"
    dead_connection.send_message = Mock(side_effect=Exception("Connection closed"))
    
    # Subscribe both connections
    notification_service.add_subscriber('room-123', good_connection)
    notification_service.add_subscriber('room-123', dead_connection)
    
    print(f"Subscribers before broadcast: {len(notification_service._subscribers.get('room-123', set()))}")
    
    # Broadcast event (dead connection will fail)
    notification_service.broadcast_member_added(
        room_id='room-123',
        user_id='user-999',
        username='newuser',
        role='MEMBER'
    )
    
    print(f"Subscribers after broadcast: {len(notification_service._subscribers.get('room-123', set()))}")
    print("Dead connection should be removed automatically")


if __name__ == '__main__':
    print("=== Notification Module Integration Examples ===\n")
    
    print("1. SUBSCRIBE_ROOM Flow:")
    print("-" * 50)
    # example_subscribe_flow()  # Uncomment to run with real database
    
    print("\n2. Broadcast Event Flow:")
    print("-" * 50)
    # example_broadcast_flow()  # Uncomment to run
    
    print("\n3. Connection Cleanup:")
    print("-" * 50)
    # example_connection_cleanup()  # Uncomment to run
    
    print("\n4. Dead Connection Handling:")
    print("-" * 50)
    # example_dead_connection_handling()  # Uncomment to run
    
    print("\nNote: Uncomment function calls to run examples.")
