"""Message serialization and deserialization."""
import json
import uuid
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict
from protocol.message_types import MessageType
from logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class Message:
    """
    Represents a protocol message.
    
    All messages follow this structure:
    {
        "type": "MESSAGE_TYPE",
        "requestId": "optional-uuid",
        "payload": { ... }
    }
    """
    
    type: MessageType
    payload: Dict[str, Any]
    request_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert message to dictionary.
        
        Returns:
            Dictionary representation
        """
        result = {
            "type": self.type.value,
            "payload": self.payload
        }
        
        if self.request_id:
            result["requestId"] = self.request_id
        
        return result
    
    def to_json(self) -> str:
        """
        Serialize message to JSON string.
        
        Returns:
            JSON string
        """
        return json.dumps(self.to_dict())
    
    def to_bytes(self) -> bytes:
        """
        Serialize message to UTF-8 encoded bytes.
        
        Returns:
            UTF-8 encoded JSON bytes
        """
        return self.to_json().encode('utf-8')
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Message':
        """
        Create message from dictionary.
        
        Args:
            data: Dictionary with type, payload, and optional requestId
        
        Returns:
            Message instance
        
        Raises:
            ValueError: If required fields are missing or invalid
        """
        if 'type' not in data:
            raise ValueError("Message missing required field: type")
        
        if 'payload' not in data:
            raise ValueError("Message missing required field: payload")
        
        try:
            message_type = MessageType(data['type'])
        except ValueError:
            raise ValueError(f"Invalid message type: {data['type']}")
        
        return Message(
            type=message_type,
            payload=data['payload'],
            request_id=data.get('requestId')
        )
    
    @staticmethod
    def from_json(json_str: str) -> 'Message':
        """
        Deserialize message from JSON string.
        
        Args:
            json_str: JSON string
        
        Returns:
            Message instance
        
        Raises:
            ValueError: If JSON is invalid or message structure is incorrect
            json.JSONDecodeError: If JSON parsing fails
        """
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
        
        return Message.from_dict(data)
    
    @staticmethod
    def from_bytes(data: bytes) -> 'Message':
        """
        Deserialize message from UTF-8 encoded bytes.
        
        Args:
            data: UTF-8 encoded JSON bytes
        
        Returns:
            Message instance
        
        Raises:
            ValueError: If decoding or parsing fails
        """
        try:
            json_str = data.decode('utf-8')
        except UnicodeDecodeError as e:
            raise ValueError(f"Invalid UTF-8 encoding: {e}")
        
        return Message.from_json(json_str)
    
    @staticmethod
    def create_request(message_type: MessageType, payload: Dict[str, Any]) -> 'Message':
        """
        Create a request message with auto-generated request ID.
        
        Args:
            message_type: Type of message
            payload: Message payload
        
        Returns:
            Message with generated request ID
        """
        return Message(
            type=message_type,
            payload=payload,
            request_id=str(uuid.uuid4())
        )
    
    @staticmethod
    def create_response(
        message_type: MessageType,
        payload: Dict[str, Any],
        request_id: Optional[str] = None
    ) -> 'Message':
        """
        Create a response message.
        
        Args:
            message_type: Type of response message
            payload: Response payload
            request_id: Request ID to match with original request
        
        Returns:
            Response message
        """
        return Message(
            type=message_type,
            payload=payload,
            request_id=request_id
        )
    
    @staticmethod
    def create_error(
        error_code: str,
        error_message: str,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None
    ) -> 'Message':
        """
        Create an error response message.
        
        Args:
            error_code: Error code (e.g., "INVALID_TOKEN")
            error_message: Human-readable error message
            details: Optional additional error details
            request_id: Request ID to match with original request
        
        Returns:
            Error message
        """
        payload = {
            "error": {
                "code": error_code,
                "message": error_message
            }
        }
        
        if details:
            payload["error"]["details"] = details
        
        return Message(
            type=MessageType.ERROR,
            payload=payload,
            request_id=request_id
        )
    
    def is_error(self) -> bool:
        """
        Check if this is an error message.
        
        Returns:
            True if message type is ERROR
        """
        return self.type == MessageType.ERROR
    
    def get_error_code(self) -> Optional[str]:
        """
        Extract error code from error message.
        
        Returns:
            Error code string, or None if not an error message
        """
        if not self.is_error():
            return None
        
        return self.payload.get("error", {}).get("code")
    
    def get_error_message(self) -> Optional[str]:
        """
        Extract error message from error message.
        
        Returns:
            Error message string, or None if not an error message
        """
        if not self.is_error():
            return None
        
        return self.payload.get("error", {}).get("message")
