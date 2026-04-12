"""Example integration of authorization service with request handlers."""
from auth.authorization_service import AuthorizationService
from database import Database
from config import load_config


def example_upload_handler(message, context, auth_service: AuthorizationService):
    """
    Example handler for file upload that checks permissions.
    
    Args:
        message: Request message
        context: Authentication context with userId and globalRole
        auth_service: Authorization service instance
    """
    user_id = context['userId']
    global_role = context['globalRole']
    room_id = message.payload.get('roomId')
    
    # Check if user has permission to upload files in this room
    has_permission = auth_service.check_permission(
        user_id=user_id,
        global_role=global_role,
        room_id=room_id,
        action='UPLOAD_FILE'
    )
    
    if not has_permission:
        return {
            'error': {
                'code': 'PERMISSION_DENIED',
                'message': 'User does not have permission to upload files in this room'
            }
        }
    
    # Proceed with upload logic...
    return {'success': True}


def example_add_member_handler(message, context, auth_service: AuthorizationService):
    """
    Example handler for adding a member that checks permissions.
    
    Args:
        message: Request message
        context: Authentication context with userId and globalRole
        auth_service: Authorization service instance
    """
    user_id = context['userId']
    global_role = context['globalRole']
    room_id = message.payload.get('roomId')
    
    # Check if user has permission to add members to this room
    has_permission = auth_service.check_permission(
        user_id=user_id,
        global_role=global_role,
        room_id=room_id,
        action='ADD_MEMBER'
    )
    
    if not has_permission:
        return {
            'error': {
                'code': 'PERMISSION_DENIED',
                'message': 'User does not have permission to add members to this room'
            }
        }
    
    # Proceed with add member logic...
    return {'success': True}


def example_create_room_handler(message, context, auth_service: AuthorizationService):
    """
    Example handler for creating a room that checks permissions.
    
    Args:
        message: Request message
        context: Authentication context with userId and globalRole
        auth_service: Authorization service instance
    """
    user_id = context['userId']
    global_role = context['globalRole']
    
    # Check if user has permission to create rooms (only ADMIN)
    has_permission = auth_service.check_permission(
        user_id=user_id,
        global_role=global_role,
        room_id=None,
        action='CREATE_ROOM'
    )
    
    if not has_permission:
        return {
            'error': {
                'code': 'PERMISSION_DENIED',
                'message': 'Only administrators can create rooms'
            }
        }
    
    # Proceed with create room logic...
    return {'success': True}


def main():
    """Example usage of authorization service."""
    # Load configuration
    config = load_config()
    
    # Initialize database
    db = Database(config.database)
    db.connect()
    
    # Initialize authorization service
    auth_service = AuthorizationService(db)
    
    # Example: Check if a user can upload to a room
    can_upload = auth_service.check_permission(
        user_id='user-123',
        global_role='USER',
        room_id='room-456',
        action='UPLOAD_FILE'
    )
    
    print(f"User can upload: {can_upload}")
    
    # Example: Check if an admin can create a room
    can_create_room = auth_service.check_permission(
        user_id='admin-123',
        global_role='ADMIN',
        room_id=None,
        action='CREATE_ROOM'
    )
    
    print(f"Admin can create room: {can_create_room}")
    
    # Example: Get user's role in a room
    role = auth_service.get_user_role_in_room('user-123', 'room-456')
    print(f"User role in room: {role}")
    
    # Clean up
    db.close()


if __name__ == '__main__':
    main()
