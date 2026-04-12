"""Example integration of ticket service with upload/download flows."""
import uuid
from datetime import datetime, timezone, timedelta
from config import load_config
from database import Database
from redis_client import RedisClient
from ticket.ticket_service import TicketService
from ticket.ticket_handlers import TicketHandlers
from protocol.message import Message
from protocol.message_types import MessageType
from logging_config import get_logger

logger = get_logger(__name__)


def example_upload_flow():
    """
    Example: Upload flow with ticket generation and verification.
    
    This demonstrates:
    1. Coordinator generates upload ticket
    2. Storage Node verifies ticket via VERIFY_TICKET
    3. Storage Node receives ticket metadata
    """
    print("\n=== Upload Flow Example ===\n")
    
    # Initialize services
    config = load_config()
    redis_client = RedisClient(config.redis)
    redis_client.connect()
    
    ticket_service = TicketService(
        redis_client=redis_client,
        upload_ticket_ttl_seconds=config.server.upload_ticket_ttl_seconds,
        download_ticket_ttl_seconds=config.server.download_ticket_ttl_seconds
    )
    
    ticket_handlers = TicketHandlers(ticket_service=ticket_service)
    
    # Step 1: Coordinator generates upload ticket (during INIT_UPLOAD)
    file_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    room_id = str(uuid.uuid4())
    
    print("1. Coordinator generates upload ticket...")
    ticket_id = ticket_service.generate_upload_ticket(
        file_id=file_id,
        user_id=user_id,
        room_id=room_id,
        total_chunks=10,
        chunk_size=524288,
        sha256_whole="a" * 64,
        stored_name=f"{room_id}/{file_id}"
    )
    print(f"   Generated ticket: {ticket_id}")
    print(f"   TTL: {config.server.upload_ticket_ttl_seconds} seconds (30 minutes)")
    
    # Step 2: Storage Node receives ticket from Client and verifies it
    print("\n2. Storage Node verifies ticket with Coordinator...")
    verify_request = Message.create_request(
        message_type=MessageType.VERIFY_TICKET,
        payload={'ticketId': ticket_id}
    )
    
    verify_response = ticket_handlers.handle_verify_ticket(verify_request)
    
    if verify_response.type == MessageType.TICKET_VALID:
        print("   ✓ Ticket is valid!")
        metadata = verify_response.payload['metadata']
        print(f"   Ticket type: {metadata['type']}")
        print(f"   File ID: {metadata['fileId']}")
        print(f"   Total chunks: {metadata['totalChunks']}")
        print(f"   Chunk size: {metadata['chunkSize']}")
        print(f"   SHA256: {metadata['sha256Whole'][:16]}...")
        print(f"   Stored name: {metadata['storedName']}")
    else:
        print("   ✗ Ticket verification failed!")
        print(f"   Error: {verify_response.payload['error']}")
    
    # Step 3: Verify expired ticket
    print("\n3. Testing expired ticket verification...")
    
    # Wait a moment and verify again (ticket should still be valid)
    verify_response_2 = ticket_handlers.handle_verify_ticket(verify_request)
    print(f"   Second verification: {verify_response_2.type.value}")
    
    # Clean up
    redis_client.close()
    print("\n=== Upload Flow Complete ===\n")


def example_download_flow():
    """
    Example: Download flow with ticket generation and verification.
    
    This demonstrates:
    1. Coordinator generates download ticket
    2. Storage Node verifies ticket via VERIFY_TICKET
    3. Storage Node receives ticket metadata
    """
    print("\n=== Download Flow Example ===\n")
    
    # Initialize services
    config = load_config()
    redis_client = RedisClient(config.redis)
    redis_client.connect()
    
    ticket_service = TicketService(
        redis_client=redis_client,
        upload_ticket_ttl_seconds=config.server.upload_ticket_ttl_seconds,
        download_ticket_ttl_seconds=config.server.download_ticket_ttl_seconds
    )
    
    ticket_handlers = TicketHandlers(ticket_service=ticket_service)
    
    # Step 1: Coordinator generates download ticket (during INIT_DOWNLOAD)
    file_id = str(uuid.uuid4())
    room_id = str(uuid.uuid4())
    
    print("1. Coordinator generates download ticket...")
    ticket_id = ticket_service.generate_download_ticket(
        file_id=file_id,
        stored_name=f"{room_id}/{file_id}",
        sha256_whole="b" * 64,
        total_chunks=20,
        chunk_size=524288
    )
    print(f"   Generated ticket: {ticket_id}")
    print(f"   TTL: {config.server.download_ticket_ttl_seconds} seconds (15 minutes)")
    
    # Step 2: Storage Node verifies ticket
    print("\n2. Storage Node verifies ticket with Coordinator...")
    verify_request = Message.create_request(
        message_type=MessageType.VERIFY_TICKET,
        payload={'ticketId': ticket_id}
    )
    
    verify_response = ticket_handlers.handle_verify_ticket(verify_request)
    
    if verify_response.type == MessageType.TICKET_VALID:
        print("   ✓ Ticket is valid!")
        metadata = verify_response.payload['metadata']
        print(f"   Ticket type: {metadata['type']}")
        print(f"   File ID: {metadata['fileId']}")
        print(f"   Total chunks: {metadata['totalChunks']}")
        print(f"   Chunk size: {metadata['chunkSize']}")
        print(f"   SHA256: {metadata['sha256Whole'][:16]}...")
        print(f"   Stored name: {metadata['storedName']}")
    else:
        print("   ✗ Ticket verification failed!")
        print(f"   Error: {verify_response.payload['error']}")
    
    # Step 3: Manual ticket cleanup (optional)
    print("\n3. Manual ticket cleanup...")
    deleted = ticket_service.delete_ticket(ticket_id)
    print(f"   Ticket deleted: {deleted}")
    
    # Step 4: Verify deleted ticket
    print("\n4. Verifying deleted ticket...")
    verify_response_3 = ticket_handlers.handle_verify_ticket(verify_request)
    print(f"   Verification result: {verify_response_3.type.value}")
    if verify_response_3.type == MessageType.TICKET_INVALID:
        print(f"   Error code: {verify_response_3.payload['error']['code']}")
    
    # Clean up
    redis_client.close()
    print("\n=== Download Flow Complete ===\n")


def example_invalid_ticket():
    """
    Example: Attempting to verify an invalid ticket.
    
    This demonstrates error handling for:
    1. Non-existent ticket
    2. Expired ticket
    """
    print("\n=== Invalid Ticket Example ===\n")
    
    # Initialize services
    config = load_config()
    redis_client = RedisClient(config.redis)
    redis_client.connect()
    
    ticket_service = TicketService(
        redis_client=redis_client,
        upload_ticket_ttl_seconds=config.server.upload_ticket_ttl_seconds,
        download_ticket_ttl_seconds=config.server.download_ticket_ttl_seconds
    )
    
    ticket_handlers = TicketHandlers(ticket_service=ticket_service)
    
    # Test 1: Non-existent ticket
    print("1. Verifying non-existent ticket...")
    fake_ticket_id = str(uuid.uuid4())
    
    verify_request = Message.create_request(
        message_type=MessageType.VERIFY_TICKET,
        payload={'ticketId': fake_ticket_id}
    )
    
    verify_response = ticket_handlers.handle_verify_ticket(verify_request)
    
    print(f"   Response type: {verify_response.type.value}")
    if verify_response.type == MessageType.TICKET_INVALID:
        print(f"   Error code: {verify_response.payload['error']['code']}")
        print(f"   Error message: {verify_response.payload['error']['message']}")
    
    # Test 2: Missing ticketId field
    print("\n2. Verifying with missing ticketId field...")
    invalid_request = Message.create_request(
        message_type=MessageType.VERIFY_TICKET,
        payload={}  # Missing ticketId
    )
    
    verify_response_2 = ticket_handlers.handle_verify_ticket(invalid_request)
    
    print(f"   Response type: {verify_response_2.type.value}")
    if verify_response_2.type == MessageType.ERROR:
        print(f"   Error code: {verify_response_2.payload['error']['code']}")
        print(f"   Error message: {verify_response_2.payload['error']['message']}")
    
    # Clean up
    redis_client.close()
    print("\n=== Invalid Ticket Example Complete ===\n")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Ticket Service Integration Examples")
    print("="*60)
    
    try:
        example_upload_flow()
        example_download_flow()
        example_invalid_ticket()
        
        print("\n" + "="*60)
        print("All examples completed successfully!")
        print("="*60 + "\n")
        
    except Exception as e:
        logger.error(f"Example failed: {e}", exc_info=True)
        print(f"\n✗ Example failed: {e}\n")
