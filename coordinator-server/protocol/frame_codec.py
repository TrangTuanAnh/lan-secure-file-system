"""Frame codec for length-prefixed message encoding/decoding."""
import struct
from typing import Optional, Tuple
from logging_config import get_logger

logger = get_logger(__name__)


class FrameCodec:
    """
    Codec for length-prefixed frame format.
    
    Frame format: [4 bytes: message length (big-endian)] [N bytes: message payload]
    """
    
    # Frame header is 4 bytes (32-bit unsigned integer)
    HEADER_SIZE = 4
    HEADER_FORMAT = '!I'  # Network byte order (big-endian), unsigned int
    
    # Maximum message size (10 MB to prevent memory exhaustion)
    MAX_MESSAGE_SIZE = 10 * 1024 * 1024
    
    @staticmethod
    def encode(message: bytes) -> bytes:
        """
        Encode a message with length prefix.
        
        Args:
            message: Raw message bytes
        
        Returns:
            Encoded frame (length prefix + message)
        
        Raises:
            ValueError: If message exceeds maximum size
        """
        message_length = len(message)
        
        if message_length > FrameCodec.MAX_MESSAGE_SIZE:
            raise ValueError(
                f"Message size {message_length} exceeds maximum {FrameCodec.MAX_MESSAGE_SIZE}"
            )
        
        # Pack length as 4-byte big-endian unsigned integer
        header = struct.pack(FrameCodec.HEADER_FORMAT, message_length)
        
        return header + message
    
    @staticmethod
    def decode_header(data: bytes) -> Optional[int]:
        """
        Decode the length from frame header.
        
        Args:
            data: At least 4 bytes of data
        
        Returns:
            Message length, or None if insufficient data
        
        Raises:
            ValueError: If decoded length exceeds maximum size
        """
        if len(data) < FrameCodec.HEADER_SIZE:
            return None
        
        # Unpack 4-byte big-endian unsigned integer
        message_length = struct.unpack(FrameCodec.HEADER_FORMAT, data[:FrameCodec.HEADER_SIZE])[0]
        
        if message_length > FrameCodec.MAX_MESSAGE_SIZE:
            raise ValueError(
                f"Message length {message_length} exceeds maximum {FrameCodec.MAX_MESSAGE_SIZE}"
            )
        
        return message_length
    
    @staticmethod
    def decode_frame(data: bytes) -> Tuple[Optional[bytes], int]:
        """
        Attempt to decode a complete frame from buffer.
        
        Args:
            data: Buffer containing frame data
        
        Returns:
            Tuple of (message bytes, bytes consumed)
            - If frame is incomplete: (None, 0)
            - If frame is complete: (message, total_bytes_consumed)
        
        Raises:
            ValueError: If frame header indicates invalid length
        """
        # Need at least header to proceed
        if len(data) < FrameCodec.HEADER_SIZE:
            return None, 0
        
        # Decode message length from header
        message_length = FrameCodec.decode_header(data)
        if message_length is None:
            return None, 0
        
        # Calculate total frame size
        total_frame_size = FrameCodec.HEADER_SIZE + message_length
        
        # Check if we have the complete frame
        if len(data) < total_frame_size:
            # Incomplete frame
            return None, 0
        
        # Extract message (skip header)
        message = data[FrameCodec.HEADER_SIZE:total_frame_size]
        
        return message, total_frame_size


class FrameBuffer:
    """
    Buffer for accumulating incoming data and extracting complete frames.
    
    This class handles the common pattern of receiving partial data over a socket
    and assembling it into complete frames.
    """
    
    def __init__(self):
        """Initialize empty buffer."""
        self._buffer = bytearray()
    
    def append(self, data: bytes) -> None:
        """
        Append data to buffer.
        
        Args:
            data: Incoming data bytes
        """
        self._buffer.extend(data)
    
    def extract_frame(self) -> Optional[bytes]:
        """
        Extract one complete frame from buffer.
        
        Returns:
            Complete message bytes, or None if no complete frame available
        
        Raises:
            ValueError: If frame header indicates invalid length
        """
        if len(self._buffer) < FrameCodec.HEADER_SIZE:
            return None
        
        message, bytes_consumed = FrameCodec.decode_frame(bytes(self._buffer))
        
        if message is not None:
            # Remove consumed bytes from buffer
            del self._buffer[:bytes_consumed]
            logger.debug(f"Extracted frame: {len(message)} bytes, buffer remaining: {len(self._buffer)}")
        
        return message
    
    def clear(self) -> None:
        """Clear the buffer."""
        self._buffer.clear()
    
    def __len__(self) -> int:
        """Return current buffer size."""
        return len(self._buffer)
