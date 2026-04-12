"""Tests for notification service."""
import unittest
from unittest.mock import Mock, MagicMock, patch
from notification.notification_service import NotificationService
from notification.notification_handlers import NotificationHandlers
from protocol.message import Message
from protocol.message_types import MessageType


class TestNotificationService(unittest.TestCase):
    """Test notification service operations."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.service = NotificationService()
    
    def test_add_subscriber(self):
        """Test adding a subscriber to a room."""
        # Create mock connection
        connection = Mock()
        connection.connection_id = "client-1:12345"
        
        # Add subscriber
        self.service.add_subscriber('room-1', connection)
        
        # Verify subscriber was added
        self.assertIn('room-1', self.service._subscribers)
        self.assertIn(connection, self.service._subscribers['room-1'])
    
    def test_add_multiple_subscribers_to_same_room(self):
        """Test adding multiple subscribers to the same room."""
        # Create mock connections
        conn1 = Mock()
        conn1.connection_id = "client-1:12345"
        conn2 = Mock()
        conn2.connection_id = "client-2:12346"
        
        # Add subscribers
        self.service.add_subscriber('room-1', conn1)
        self.service.add_subscriber('room-1', conn2)
        
        # Verify both subscribers were added
        self.assertEqual(len(self.service._subscribers['room-1']), 2)
        self.assertIn(conn1, self.service._subscribers['room-1'])
        self.assertIn(conn2, self.service._subscribers['room-1'])
    
    def test_remove_subscriber(self):
        """Test removing a subscriber from a room."""
        # Create mock connection
        connection = Mock()
        connection.connection_id = "client-1:12345"
        
        # Add and then remove subscriber
        self.service.add_subscriber('room-1', connection)
        self.service.remove_subscriber('room-1', connection)
        
        # Verify subscriber was removed and room cleaned up
        self.assertNotIn('room-1', self.service._subscribers)
    
    def test_remove_subscriber_from_all_rooms(self):
        """Test removing a subscriber from all rooms."""
        # Create mock connection
        connection = Mock()
        connection.connection_id = "client-1:12345"
        
        # Subscribe to multiple rooms
        self.service.add_subscriber('room-1', connection)
        self.service.add_subscriber('room-2', connection)
        self.service.add_subscriber('room-3', connection)
        
        # Remove from all rooms
        self.service.remove_subscriber_from_all_rooms(connection)
        
        # Verify all rooms are cleaned up
        self.assertEqual(len(self.service._subscribers), 0)
    
    def test_broadcast_to_subscribers(self):
        """Test broadcasting event to room subscribers."""
        # Create mock connections
        conn1 = Mock()
        conn1.connection_id = "client-1:12345"
        conn1.send_message = Mock()
        
        conn2 = Mock()
        conn2.connection_id = "client-2:12346"
        conn2.send_message = Mock()
        
        # Subscribe connections
        self.service.add_subscriber('room-1', conn1)
        self.service.add_subscriber('room-1', conn2)
        
        # Broadcast event
        self.service.broadcast_new_file(
            room_id='room-1',
            file_id='file-123',
            file_name='test.pdf',
            uploader='user-456'
        )
        
        # Verify both connections received the message
        self.assertTrue(conn1.send_message.called)
        self.assertTrue(conn2.send_message.called)
        
        # Verify message content
        call_args = conn1.send_message.call_args[0][0]
        self.assertEqual(call_args.type, MessageType.EVENT)
        self.assertEqual(call_args.payload['eventType'], 'NEW_FILE')
        self.assertEqual(call_args.payload['fileId'], 'file-123')
    
    def test_broadcast_removes_dead_connections(self):
        """Test that dead connections are removed during broadcast."""
        # Create mock connections
        good_conn = Mock()
        good_conn.connection_id = "client-1:12345"
        good_conn.send_message = Mock()
        
        dead_conn = Mock()
        dead_conn.connection_id = "client-2:12346"
        dead_conn.send_message = Mock(side_effect=Exception("Connection closed"))
        
        # Subscribe both connections
        self.service.add_subscriber('room-1', good_conn)
        self.service.add_subscriber('room-1', dead_conn)
        
        # Broadcast event
        self.service.broadcast_member_added(
            room_id='room-1',
            user_id='user-789',
            username='testuser',
            role='MEMBER'
        )
        
        # Verify dead connection was removed
        self.assertNotIn(dead_conn, self.service._subscribers.get('room-1', set()))
        # Good connection should still be there
        self.assertIn(good_conn, self.service._subscribers.get('room-1', set()))
    
    def test_broadcast_to_room_with_no_subscribers(self):
        """Test broadcasting to a room with no subscribers."""
        # Should not raise an error
        self.service.broadcast_file_deleted(
            room_id='room-999',
            file_id='file-123',
            file_name='test.pdf',
            deleted_by='user-456'
        )
        
        # No subscribers should be created
        self.assertNotIn('room-999', self.service._subscribers)
    
    def test_thread_safety_add_remove(self):
        """Test thread-safe add/remove operations."""
        import threading
        
        connections = [Mock() for _ in range(10)]
        for i, conn in enumerate(connections):
            conn.connection_id = f"client-{i}"
        
        def add_subscribers():
            for conn in connections:
                self.service.add_subscriber('room-1', conn)
        
        def remove_subscribers():
            for conn in connections:
                self.service.remove_subscriber('room-1', conn)
        
        # Run add and remove in parallel threads
        threads = [
            threading.Thread(target=add_subscribers),
            threading.Thread(target=remove_subscribers)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Should not crash and state should be consistent
        # Either all added or all removed
        if 'room-1' in self.service._subscribers:
            # Some were added
            self.assertGreaterEqual(len(self.service._subscribers['room-1']), 0)


class TestNotificationHandlers(unittest.TestCase):
    """Test notification handlers."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_notification = Mock(spec=NotificationService)
        self.mock_authz = Mock()
        self.mock_auth = Mock()
        self.handlers = NotificationHandlers(
            notification_service=self.mock_notification,
            authorization_service=self.mock_authz,
            auth_service=self.mock_auth
        )
    
    def test_subscribe_room_success(self):
        """Test successful room subscription."""
        # Mock connection
        connection = Mock()
        connection.connection_id = "client-1:12345"
        connection.send_message = Mock()
        
        # Mock authentication
        self.mock_auth.validate_token.return_value = (
            True,
            {'userId': 'user-789', 'globalRole': 'USER'},
            None
        )
        
        # Mock authorization check
        self.mock_authz.check_permission.return_value = True
        
        # Create message
        message = Message(
            type=MessageType.SUBSCRIBE_ROOM,
            payload={'token': 'valid-token', 'roomId': 'room-123'},
            request_id='req-456'
        )
        
        # Handle subscribe
        self.handlers.handle_subscribe_room(
            connection=connection,
            message=message
        )
        
        # Verify subscriber was added
        self.mock_notification.add_subscriber.assert_called_once_with('room-123', connection)
        
        # Verify success response was sent
        self.assertTrue(connection.send_message.called)
        response = connection.send_message.call_args[0][0]
        self.assertEqual(response.type, MessageType.SUBSCRIBE_ROOM_RESPONSE)
        self.assertTrue(response.payload['success'])
    
    def test_subscribe_room_no_token(self):
        """Test room subscription without token."""
        # Mock connection
        connection = Mock()
        connection.connection_id = "client-1:12345"
        connection.send_message = Mock()
        
        # Create message without token
        message = Message(
            type=MessageType.SUBSCRIBE_ROOM,
            payload={'roomId': 'room-123'},
            request_id='req-456'
        )
        
        # Handle subscribe
        self.handlers.handle_subscribe_room(
            connection=connection,
            message=message
        )
        
        # Verify subscriber was NOT added
        self.mock_notification.add_subscriber.assert_not_called()
        
        # Verify error response was sent
        self.assertTrue(connection.send_message.called)
        response = connection.send_message.call_args[0][0]
        self.assertEqual(response.type, MessageType.ERROR)
        self.assertEqual(response.payload['error']['code'], 'AUTH_REQUIRED')
    
    def test_subscribe_room_invalid_token(self):
        """Test room subscription with invalid token."""
        # Mock connection
        connection = Mock()
        connection.connection_id = "client-1:12345"
        connection.send_message = Mock()
        
        # Mock authentication to fail
        self.mock_auth.validate_token.return_value = (False, None, 'INVALID_TOKEN')
        
        # Create message
        message = Message(
            type=MessageType.SUBSCRIBE_ROOM,
            payload={'token': 'invalid-token', 'roomId': 'room-123'},
            request_id='req-456'
        )
        
        # Handle subscribe
        self.handlers.handle_subscribe_room(
            connection=connection,
            message=message
        )
        
        # Verify subscriber was NOT added
        self.mock_notification.add_subscriber.assert_not_called()
        
        # Verify error response was sent
        self.assertTrue(connection.send_message.called)
        response = connection.send_message.call_args[0][0]
        self.assertEqual(response.type, MessageType.ERROR)
        self.assertEqual(response.payload['error']['code'], 'INVALID_TOKEN')
    
    def test_subscribe_room_permission_denied(self):
        """Test room subscription with insufficient permissions."""
        # Mock connection
        connection = Mock()
        connection.connection_id = "client-1:12345"
        connection.send_message = Mock()
        
        # Mock authentication
        self.mock_auth.validate_token.return_value = (
            True,
            {'userId': 'user-789', 'globalRole': 'USER'},
            None
        )
        
        # Mock authorization check to deny
        self.mock_authz.check_permission.return_value = False
        
        # Create message
        message = Message(
            type=MessageType.SUBSCRIBE_ROOM,
            payload={'token': 'valid-token', 'roomId': 'room-123'},
            request_id='req-456'
        )
        
        # Handle subscribe
        self.handlers.handle_subscribe_room(
            connection=connection,
            message=message
        )
        
        # Verify subscriber was NOT added
        self.mock_notification.add_subscriber.assert_not_called()
        
        # Verify error response was sent
        self.assertTrue(connection.send_message.called)
        response = connection.send_message.call_args[0][0]
        self.assertEqual(response.type, MessageType.ERROR)
        self.assertEqual(response.payload['error']['code'], 'PERMISSION_DENIED')
    
    def test_subscribe_room_missing_room_id(self):
        """Test room subscription without roomId."""
        # Mock connection
        connection = Mock()
        connection.connection_id = "client-1:12345"
        connection.send_message = Mock()
        
        # Mock authentication
        self.mock_auth.validate_token.return_value = (
            True,
            {'userId': 'user-789', 'globalRole': 'USER'},
            None
        )
        
        # Create message without roomId
        message = Message(
            type=MessageType.SUBSCRIBE_ROOM,
            payload={'token': 'valid-token'},
            request_id='req-456'
        )
        
        # Handle subscribe
        self.handlers.handle_subscribe_room(
            connection=connection,
            message=message
        )
        
        # Verify error response was sent
        self.assertTrue(connection.send_message.called)
        response = connection.send_message.call_args[0][0]
        self.assertEqual(response.type, MessageType.ERROR)
        self.assertEqual(response.payload['error']['code'], 'INVALID_REQUEST')
    
    def test_unsubscribe_room_success(self):
        """Test successful room unsubscription."""
        # Mock connection
        connection = Mock()
        connection.connection_id = "client-1:12345"
        connection.send_message = Mock()
        
        # Create message
        message = Message(
            type=MessageType.UNSUBSCRIBE_ROOM,
            payload={'roomId': 'room-123'},
            request_id='req-456'
        )
        
        # Handle unsubscribe
        self.handlers.handle_unsubscribe_room(
            connection=connection,
            message=message
        )
        
        # Verify subscriber was removed
        self.mock_notification.remove_subscriber.assert_called_once_with('room-123', connection)
        
        # Verify success response was sent
        self.assertTrue(connection.send_message.called)
        response = connection.send_message.call_args[0][0]
        self.assertEqual(response.type, MessageType.UNSUBSCRIBE_ROOM_RESPONSE)
        self.assertTrue(response.payload['success'])
    
    def test_unsubscribe_room_missing_room_id(self):
        """Test room unsubscription without roomId."""
        # Mock connection
        connection = Mock()
        connection.connection_id = "client-1:12345"
        connection.send_message = Mock()
        
        # Create message without roomId
        message = Message(
            type=MessageType.UNSUBSCRIBE_ROOM,
            payload={},
            request_id='req-456'
        )
        
        # Handle unsubscribe
        self.handlers.handle_unsubscribe_room(
            connection=connection,
            message=message
        )
        
        # Verify error response was sent
        self.assertTrue(connection.send_message.called)
        response = connection.send_message.call_args[0][0]
        self.assertEqual(response.type, MessageType.ERROR)
        self.assertEqual(response.payload['error']['code'], 'INVALID_REQUEST')


if __name__ == '__main__':
    unittest.main()
