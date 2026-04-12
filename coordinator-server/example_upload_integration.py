"""Example integration of upload control module.

This example demonstrates how to integrate the upload control module
into the main coordinator server.
"""
from database import Database
from redis_client import RedisClient
from auth.authorization_service import AuthorizationService
from audit.audit_service import AuditService
from notification.notification_service import NotificationService
from upload.upload_service import UploadService
from upload.upload_handlers import UploadHandlers
from config import load_config


def setup_upload_module():
    """
    Set up upload control module with all dependencies.
    
    Returns:
        Tuple of (UploadService, UploadHandlers)
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
    authorization_service = AuthorizationService(database)
    audit_service = AuditService(database)
    notification_service = NotificationService()
    
    # Initialize upload service
    upload_service = UploadService(
        database=database,
        redis_client=redis_client,
        authorization_service=authorization_service,
        audit_service=audit_service,
        notification_service=notification_service,
        chunk_size=config.server.upload_chunk_size,
        ticket_ttl_seconds=config.server.upload_ticket_ttl_seconds
    )
    
    # Initialize upload handlers
    upload_handlers = UploadHandlers(upload_service)
    
    return upload_service, upload_handlers


def example_init_upload_flow():
    """
    Example: Handle INIT_UPLOAD request from client.
    """
    from protocol.message import Message
    from protocol.message_types import MessageType
    from datetime import datetime, timezone
    
    # Set up module
    upload_service, upload_handlers = setup_upload_module()
    
    # Simulate INIT_UPLOAD message from client
    message = Message(
        message_type=MessageType.INIT_UPLOAD,
        payload={
            'roomId': 'room-123',
            'fileInfo': {
                'originalName': 'document.pdf',
                'sizeBytes': 2097152,  # 2MB
                'mimeType': 'application/pdf',
                'sha256Whole': 'a' * 64
            },
            'scanReport': {
                'result': 'CLEAN',
                'fileSha256': 'a' * 64,
                'scannedAt': datetime.now(timezone.utc).isoformat(),
                'tool': 'ClamAV',
                'toolVersion': '1.0.0'
            },
            'storageAddress': 'storage-node-1:9000'
        },
        request_id='req-456'
    )
    
    # Simulate authenticated user
    user_id = 'user-789'
    global_role = 'USER'
    
    # Handle the message
    response = upload_handlers.handle_init_upload(message, user_id, global_role)
    
    print(f"Response type: {response.message_type}")
    print(f"Response payload: {response.payload}")
    
    # Expected response:
    # - If authorized and valid: UPLOAD_PLAN with ticket or deduplicated flag
    # - If unauthorized: ERROR with PERMISSION_DENIED
    # - If invalid scan: ERROR with SCAN_FAILED/SCAN_EXPIRED/SCAN_HASH_MISMATCH


def example_upload_complete_flow():
    """
    Example: Handle UPLOAD_COMPLETE message from Storage Node.
    """
    from protocol.message import Message
    from protocol.message_types import MessageType
    
    # Set up module
    upload_service, upload_handlers = setup_upload_module()
    
    # Simulate UPLOAD_COMPLETE message from Storage Node
    message = Message(
        message_type=MessageType.UPLOAD_COMPLETE,
        payload={
            'fileId': 'file-123',
            'sha256Whole': 'a' * 64,
            'storedName': 'room-123/file-123',
            'finalSize': 2097152
        },
        request_id='req-789'
    )
    
    # Handle the message
    response = upload_handlers.handle_upload_complete(message)
    
    print(f"Response type: {response.message_type}")
    print(f"Response payload: {response.payload}")
    
    # Expected response:
    # - If successful: ACK with success=true
    # - If file not found: ERROR with FILE_NOT_FOUND
    # - If hash mismatch: ERROR with HASH_MISMATCH


def example_upload_failed_flow():
    """
    Example: Handle UPLOAD_FAILED message from Storage Node.
    """
    from protocol.message import Message
    from protocol.message_types import MessageType
    
    # Set up module
    upload_service, upload_handlers = setup_upload_module()
    
    # Simulate UPLOAD_FAILED message from Storage Node
    message = Message(
        message_type=MessageType.UPLOAD_FAILED,
        payload={
            'fileId': 'file-456',
            'reason': 'Disk full'
        },
        request_id='req-999'
    )
    
    # Handle the message
    response = upload_handlers.handle_upload_failed(message)
    
    print(f"Response type: {response.message_type}")
    print(f"Response payload: {response.payload}")
    
    # Expected response:
    # - If successful: ACK with success=true
    # - If file not found: ERROR with FILE_NOT_FOUND


def example_deduplication_scenario():
    """
    Example: Upload file that already exists (deduplication).
    """
    from datetime import datetime, timezone
    
    # Set up module
    upload_service, _ = setup_upload_module()
    
    # First upload - new file
    file_info_1 = {
        'originalName': 'report.pdf',
        'sizeBytes': 1048576,
        'mimeType': 'application/pdf',
        'sha256Whole': 'abc123' * 10 + 'abcd'  # 64 chars
    }
    
    scan_report = {
        'result': 'CLEAN',
        'fileSha256': file_info_1['sha256Whole'],
        'scannedAt': datetime.now(timezone.utc).isoformat(),
        'tool': 'ClamAV',
        'toolVersion': '1.0.0'
    }
    
    success_1, plan_1, error_1 = upload_service.handle_init_upload(
        user_id='user-1',
        global_role='USER',
        room_id='room-1',
        file_info=file_info_1,
        scan_report=scan_report
    )
    
    print(f"First upload - Deduplicated: {plan_1.get('deduplicated') if plan_1 else None}")
    # Expected: deduplicated=False, ticket present
    
    # Simulate upload completion
    if plan_1 and not plan_1.get('deduplicated'):
        upload_service.handle_upload_complete(
            file_id=plan_1['fileId'],
            sha256_whole=file_info_1['sha256Whole'],
            stored_name=f"room-1/{plan_1['fileId']}",
            final_size=file_info_1['sizeBytes']
        )
    
    # Second upload - same content, different room
    file_info_2 = file_info_1.copy()
    file_info_2['originalName'] = 'copy_of_report.pdf'
    
    success_2, plan_2, error_2 = upload_service.handle_init_upload(
        user_id='user-2',
        global_role='USER',
        room_id='room-2',
        file_info=file_info_2,
        scan_report=scan_report
    )
    
    print(f"Second upload - Deduplicated: {plan_2.get('deduplicated') if plan_2 else None}")
    # Expected: deduplicated=True, no ticket, file immediately READY


if __name__ == '__main__':
    print("=== Upload Control Module Integration Examples ===\n")
    
    print("1. INIT_UPLOAD Flow:")
    print("-" * 50)
    # example_init_upload_flow()  # Uncomment to run with real database
    
    print("\n2. UPLOAD_COMPLETE Flow:")
    print("-" * 50)
    # example_upload_complete_flow()  # Uncomment to run with real database
    
    print("\n3. UPLOAD_FAILED Flow:")
    print("-" * 50)
    # example_upload_failed_flow()  # Uncomment to run with real database
    
    print("\n4. Deduplication Scenario:")
    print("-" * 50)
    # example_deduplication_scenario()  # Uncomment to run with real database
    
    print("\nNote: Uncomment function calls to run with real database connection.")
