# Authorization Module

## Overview

The authorization module provides permission checking functionality for the Coordinator Server. It implements role-based access control (RBAC) based on room membership and global roles.

## Components

### AuthorizationService

The main service class that handles permission checking.

**Key Methods:**

- `check_permission(user_id, global_role, room_id, action)`: Check if a user has permission to perform an action
- `get_user_role_in_room(user_id, room_id)`: Get a user's role in a specific room
- `_check_permission_matrix(role, action)`: Internal method to look up permissions in the matrix

## Permission Matrix

The authorization system uses a permission matrix that defines which roles can perform which actions:

| Action | ADMIN | OWNER | MEMBER | VIEWER |
|--------|-------|-------|--------|--------|
| Create Room | ✓ | ✗ | ✗ | ✗ |
| Add Member | ✓ | ✓ | ✗ | ✗ |
| Remove Member | ✓ | ✓ | ✗ | ✗ |
| Change Role | ✓ | ✓ | ✗ | ✗ |
| Upload File | ✓ | ✓ | ✓ | ✗ |
| Download File | ✓ | ✓ | ✓ | ✓ |
| View Files | ✓ | ✓ | ✓ | ✓ |
| Create Share Token | ✓ | ✓ | ✓ | ✗ |
| Delete File | ✓ | ✓ | ✗ | ✗ |

## Roles

### Global Roles

- **ADMIN**: Has full permissions across all rooms without needing explicit membership
- **USER**: Regular user with no special global privileges

### Room Roles

- **OWNER**: Full control over the room (can manage members, upload, delete files)
- **MEMBER**: Can upload files and create share tokens, but cannot manage members
- **VIEWER**: Read-only access (can view and download files only)

## Usage

### Basic Permission Check

```python
from auth.authorization_service import AuthorizationService
from database import Database

# Initialize
db = Database(config.database)
auth_service = AuthorizationService(db)

# Check permission
has_permission = auth_service.check_permission(
    user_id='user-123',
    global_role='USER',
    room_id='room-456',
    action='UPLOAD_FILE'
)

if not has_permission:
    return error_response('PERMISSION_DENIED')
```

### Integration with Request Handlers

```python
def upload_handler(message, context, auth_service):
    """Handler that checks upload permission."""
    user_id = context['userId']
    global_role = context['globalRole']
    room_id = message.payload.get('roomId')
    
    # Check permission
    if not auth_service.check_permission(user_id, global_role, room_id, 'UPLOAD_FILE'):
        return error_response('PERMISSION_DENIED')
    
    # Proceed with upload...
```

### Get User Role

```python
# Get user's role in a room
role = auth_service.get_user_role_in_room('user-123', 'room-456')

if role == 'OWNER':
    # User is owner
elif role == 'MEMBER':
    # User is member
elif role == 'VIEWER':
    # User is viewer
else:
    # User is not a member (role is None)
```

## Actions

The following actions are supported:

- `CREATE_ROOM`: Create a new room (ADMIN only)
- `ADD_MEMBER`: Add a member to a room
- `REMOVE_MEMBER`: Remove a member from a room
- `CHANGE_ROLE`: Change a member's role
- `UPLOAD_FILE`: Upload a file to a room
- `DOWNLOAD_FILE`: Download a file from a room
- `VIEW_FILES`: View file list in a room
- `CREATE_SHARE_TOKEN`: Create a share token for a file
- `DELETE_FILE`: Delete a file from a room

## Permission Logic

1. **ADMIN Override**: Users with `global_role='ADMIN'` have permission for all actions in all rooms
2. **Room Membership**: For room-specific actions, the user must be a member of the room
3. **Role-Based**: Permissions are determined by the user's role in the room (OWNER, MEMBER, VIEWER)
4. **No Caching**: Permissions are checked on every request by querying PostgreSQL

## Database Schema

The authorization service queries the `room_members` table:

```sql
CREATE TABLE room_members (
    room_id UUID NOT NULL,
    user_id UUID NOT NULL,
    role VARCHAR(10) NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (room_id, user_id)
);
```

## Error Handling

When permission is denied, handlers should return:

```python
{
    'error': {
        'code': 'PERMISSION_DENIED',
        'message': 'User does not have permission to perform this action',
        'details': {
            'userId': user_id,
            'roomId': room_id,
            'action': action,
            'requiredRole': 'OWNER',
            'actualRole': 'VIEWER'
        }
    }
}
```

## Testing

The authorization module includes comprehensive unit tests covering:

- All permission matrix combinations
- ADMIN override behavior
- Non-member access denial
- Edge cases (missing room_id, unknown roles/actions)

Run tests with:

```bash
python -m pytest test_authorization.py -v
```

## Design Decisions

### No Permission Caching

**Choice**: Query PostgreSQL on every permission check

**Rationale**: 
- Avoids cache invalidation complexity
- Ensures permissions are always up-to-date
- Index on (room_id, user_id) makes queries fast enough

**Trade-off**: Slightly higher database load vs. always-correct permissions

### Permission Matrix in Code

**Choice**: Define permission matrix as a Python dictionary

**Rationale**:
- Easy to understand and modify
- No database queries needed for matrix lookup
- Changes require code deployment (intentional - permissions are core business logic)

**Alternative**: Store permissions in database (more flexible, but adds complexity)

## Future Enhancements

Potential improvements for future versions:

1. **Custom Permissions**: Allow room-specific permission overrides
2. **Permission Groups**: Define reusable permission sets
3. **Audit Trail**: Log all permission checks for compliance
4. **Permission Caching**: Add Redis-based caching with invalidation
5. **Fine-Grained Permissions**: Add more granular actions (e.g., EDIT_FILE, RENAME_FILE)
