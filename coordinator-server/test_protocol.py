"""Tests for socket protocol implementation."""
import unittest
import socket
import time
import threading
from protocol.message_types import MessageType
from protocol.message import Message
from protocol.frame_codec import FrameCodec, FrameBuffer
from protocol.socket_server import BaseSocketServer, SocketConnection


class TestFrameCodec(unittest.TestCase):
    """Test frame codec encoding and decoding."""
    
    def test_encode_message(self):
        """Test encoding a message with length prefix."""
        message = b"Hello, World!"
        frame = FrameCodec.encode(message)
        
        # Frame should be 4 bytes (length) + message length
        self.assertEqual(len(frame), 4 + len(message))
        
        # First 4 bytes should encode the message length
        length = int.from_bytes(frame[:4], byteorder='big')
        self.assertEqual(length, len(message))
        
        # Remaining bytes should be the message
        self.assertEqual(frame[4:], message)
    
    def test_decode_header(self):
        """Test decoding length from header."""
        message = b"Test message"
        frame = FrameCodec.encode(message)
        
        length = FrameCodec.decode_header(frame)
        self.assertEqual(length, len(message))
    
    def test_decode_header_insufficient_data(self):
        """Test decode_header with insufficient data."""
        data = b"ABC"  # Less than 4 bytes
        length = FrameCodec.decode_header(data)
        self.assertIsNone(length)
    
    def test_decode_complete_frame(self):
        """Test decoding a complete frame."""
        message = b"Complete frame test"
        frame = FrameCodec.encode(message)
        
        decoded_message, bytes_consumed = FrameCodec.decode_frame(frame)
        
        self.assertEqual(decoded_message, message)
        self.assertEqual(bytes_consumed, len(frame))
    
    def test_decode_incomplete_frame(self):
        """Test decoding an incomplete frame."""
        message = b"Incomplete frame"
        frame = FrameCodec.encode(message)
        
        # Only provide partial frame
        partial = frame[:10]
        decoded_message, bytes_consumed = FrameCodec.decode_frame(partial)
        
        self.assertIsNone(decoded_message)
        self.assertEqual(bytes_consumed, 0)
    
    def test_max_message_size(self):
        """Test that oversized messages are rejected."""
        # Create a message larger than MAX_MESSAGE_SIZE
        large_message = b"X" * (FrameCodec.MAX_MESSAGE_SIZE + 1)
        
        with self.assertRaises(ValueError):
            FrameCodec.encode(large_message)


class TestFrameBuffer(unittest.TestCase):
    """Test frame buffer for accumulating data."""
    
    def test_extract_single_frame(self):
        """Test extracting a single complete frame."""
        buffer = FrameBuffer()
        message = b"Single frame"
        frame = FrameCodec.encode(message)
        
        buffer.append(frame)
        extracted = buffer.extract_frame()
        
        self.assertEqual(extracted, message)
        self.assertEqual(len(buffer), 0)
    
    def test_extract_multiple_frames(self):
        """Test extracting multiple frames from buffer."""
        buffer = FrameBuffer()
        
        messages = [b"First", b"Second", b"Third"]
        for msg in messages:
            frame = FrameCodec.encode(msg)
            buffer.append(frame)
        
        # Extract all frames
        extracted = []
        while True:
            frame = buffer.extract_frame()
            if frame is None:
                break
            extracted.append(frame)
        
        self.assertEqual(extracted, messages)
        self.assertEqual(len(buffer), 0)
    
    def test_partial_frame_accumulation(self):
        """Test accumulating partial frames."""
        buffer = FrameBuffer()
        message = b"Partial frame test"
        frame = FrameCodec.encode(message)
        
        # Add frame in chunks
        chunk_size = 5
        for i in range(0, len(frame), chunk_size):
            chunk = frame[i:i+chunk_size]
            buffer.append(chunk)
            
            # Try to extract (should only succeed on last chunk)
            extracted = buffer.extract_frame()
            if i + chunk_size >= len(frame):
                self.assertEqual(extracted, message)
            else:
                self.assertIsNone(extracted)


class TestMessage(unittest.TestCase):
    """Test message serialization and deserialization."""
    
    def test_message_to_dict(self):
        """Test converting message to dictionary."""
        msg = Message(
            type=MessageType.LOGIN,
            payload={"username": "test", "password": "secret"},
            request_id="123"
        )
        
        d = msg.to_dict()
        
        self.assertEqual(d["type"], "LOGIN")
        self.assertEqual(d["payload"]["username"], "test")
        self.assertEqual(d["requestId"], "123")
    
    def test_message_to_json(self):
        """Test serializing message to JSON."""
        msg = Message(
            type=MessageType.PING,
            payload={}
        )
        
        json_str = msg.to_json()
        self.assertIn('"type": "PING"', json_str)
        self.assertIn('"payload"', json_str)
    
    def test_message_from_dict(self):
        """Test creating message from dictionary."""
        data = {
            "type": "PONG",
            "payload": {"timestamp": 12345},
            "requestId": "456"
        }
        
        msg = Message.from_dict(data)
        
        self.assertEqual(msg.type, MessageType.PONG)
        self.assertEqual(msg.payload["timestamp"], 12345)
        self.assertEqual(msg.request_id, "456")
    
    def test_message_from_json(self):
        """Test deserializing message from JSON."""
        json_str = '{"type": "SIGNUP", "payload": {"username": "alice"}, "requestId": "789"}'
        
        msg = Message.from_json(json_str)
        
        self.assertEqual(msg.type, MessageType.SIGNUP)
        self.assertEqual(msg.payload["username"], "alice")
        self.assertEqual(msg.request_id, "789")
    
    def test_message_roundtrip(self):
        """Test message serialization roundtrip."""
        original = Message(
            type=MessageType.CREATE_ROOM,
            payload={"name": "Test Room"},
            request_id="abc-123"
        )
        
        # Serialize and deserialize
        json_str = original.to_json()
        restored = Message.from_json(json_str)
        
        self.assertEqual(restored.type, original.type)
        self.assertEqual(restored.payload, original.payload)
        self.assertEqual(restored.request_id, original.request_id)
    
    def test_create_error_message(self):
        """Test creating error message."""
        error = Message.create_error(
            "INVALID_TOKEN",
            "Token is invalid or expired",
            details={"token": "abc123"},
            request_id="req-1"
        )
        
        self.assertEqual(error.type, MessageType.ERROR)
        self.assertTrue(error.is_error())
        self.assertEqual(error.get_error_code(), "INVALID_TOKEN")
        self.assertEqual(error.get_error_message(), "Token is invalid or expired")
        self.assertEqual(error.request_id, "req-1")
    
    def test_invalid_message_type(self):
        """Test that invalid message type raises error."""
        data = {
            "type": "INVALID_TYPE",
            "payload": {}
        }
        
        with self.assertRaises(ValueError):
            Message.from_dict(data)
    
    def test_missing_required_fields(self):
        """Test that missing required fields raise errors."""
        # Missing type
        with self.assertRaises(ValueError):
            Message.from_dict({"payload": {}})
        
        # Missing payload
        with self.assertRaises(ValueError):
            Message.from_dict({"type": "PING"})


class TestBaseSocketServer(unittest.TestCase):
    """Test base socket server functionality."""
    
    def setUp(self):
        """Set up test server."""
        self.server = BaseSocketServer("127.0.0.1", 0, name="TestServer")
        
        # Register a simple PING handler
        def ping_handler(conn: SocketConnection, msg: Message):
            response = Message.create_response(
                MessageType.PONG,
                {"timestamp": time.time()},
                request_id=msg.request_id
            )
            conn.send_message(response)
        
        self.server.register_handler(MessageType.PING, ping_handler)
        self.server.start()
        
        # Get actual port (since we used 0)
        self.port = self.server._server_socket.getsockname()[1]
    
    def tearDown(self):
        """Stop test server."""
        self.server.stop()
    
    def test_server_starts_and_stops(self):
        """Test that server starts and stops cleanly."""
        self.assertTrue(self.server._running)
        self.server.stop()
        self.assertFalse(self.server._running)
    
    def test_client_connection(self):
        """Test that client can connect to server."""
        # Connect client
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(("127.0.0.1", self.port))
        
        # Wait for connection to be registered
        time.sleep(0.1)
        
        self.assertEqual(self.server.get_connection_count(), 1)
        
        client.close()
        time.sleep(0.1)
        
        self.assertEqual(self.server.get_connection_count(), 0)
    
    def test_ping_pong_exchange(self):
        """Test PING/PONG message exchange."""
        # Connect client
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(("127.0.0.1", self.port))
        
        # Send PING message
        ping_msg = Message.create_request(MessageType.PING, {})
        frame = FrameCodec.encode(ping_msg.to_bytes())
        client.sendall(frame)
        
        # Receive PONG response
        buffer = FrameBuffer()
        while True:
            data = client.recv(4096)
            if not data:
                break
            buffer.append(data)
            
            response_bytes = buffer.extract_frame()
            if response_bytes:
                response = Message.from_bytes(response_bytes)
                break
        
        self.assertEqual(response.type, MessageType.PONG)
        self.assertEqual(response.request_id, ping_msg.request_id)
        self.assertIn("timestamp", response.payload)
        
        client.close()


if __name__ == '__main__':
    unittest.main()
