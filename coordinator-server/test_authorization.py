"""Unit tests for authorization service."""
import pytest
from unittest.mock import Mock, MagicMock
from auth.authorization_service import AuthorizationService


class TestAuthorizationService:
    """Test suite for AuthorizationService."""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        return Mock()
    
    @pytest.fixture
    def auth_service(self, mock_db):
        """Create an AuthorizationService instance with mock database."""
        return AuthorizationService(mock_db)
    
    # Test ADMIN permissions
    
    def test_admin_has_permission_for_all_actions(self, auth_service, mock_db):
        """ADMIN should have permission for all actions in all rooms."""
        actions = [
            'CREATE_ROOM', 'ADD_MEMBER', 'REMOVE_MEMBER', 'CHANGE_ROLE',
            'UPLOAD_FILE', 'DOWNLOAD_FILE', 'VIEW_FILES', 'CREATE_SHARE_TOKEN', 'DELETE_FILE'
        ]
        
        for action in actions:
            result = auth_service.check_permission(
                user_id='admin-user-id',
                global_role='ADMIN',
                room_id='room-123',
                action=action
            )
            assert result is True, f"ADMIN should have permission for {action}"
    
    def test_admin_can_create_room(self, auth_service, mock_db):
        """ADMIN should be able to create rooms."""
        result = auth_service.check_permission(
            user_id='admin-user-id',
            global_role='ADMIN',
            room_id=None,
            action='CREATE_ROOM'
        )
        assert result is True
    
    # Test CREATE_ROOM permission
    
    def test_user_cannot_create_room(self, auth_service, mock_db):
        """Regular USER should not be able to create rooms."""
        result = auth_service.check_permission(
            user_id='user-id',
            global_role='USER',
            room_id=None,
            action='CREATE_ROOM'
        )
        assert result is False
    
    # Test OWNER permissions
    
    def test_owner_can_add_member(self, auth_service, mock_db):
        """OWNER should be able to add members."""
        mock_db.execute_query.return_value = [{'role': 'OWNER'}]
        
        result = auth_service.check_permission(
            user_id='owner-id',
            global_role='USER',
            room_id='room-123',
            action='ADD_MEMBER'
        )
        
        assert result is True
        mock_db.execute_query.assert_called_once()
    
    def test_owner_can_remove_member(self, auth_service, mock_db):
        """OWNER should be able to remove members."""
        mock_db.execute_query.return_value = [{'role': 'OWNER'}]
        
        result = auth_service.check_permission(
            user_id='owner-id',
            global_role='USER',
            room_id='room-123',
            action='REMOVE_MEMBER'
        )
        
        assert result is True
    
    def test_owner_can_change_role(self, auth_service, mock_db):
        """OWNER should be able to change member roles."""
        mock_db.execute_query.return_value = [{'role': 'OWNER'}]
        
        result = auth_service.check_permission(
            user_id='owner-id',
            global_role='USER',
            room_id='room-123',
            action='CHANGE_ROLE'
        )
        
        assert result is True
    
    def test_owner_can_upload_file(self, auth_service, mock_db):
        """OWNER should be able to upload files."""
        mock_db.execute_query.return_value = [{'role': 'OWNER'}]
        
        result = auth_service.check_permission(
            user_id='owner-id',
            global_role='USER',
            room_id='room-123',
            action='UPLOAD_FILE'
        )
        
        assert result is True
    
    def test_owner_can_delete_file(self, auth_service, mock_db):
        """OWNER should be able to delete files."""
        mock_db.execute_query.return_value = [{'role': 'OWNER'}]
        
        result = auth_service.check_permission(
            user_id='owner-id',
            global_role='USER',
            room_id='room-123',
            action='DELETE_FILE'
        )
        
        assert result is True
    
    def test_owner_can_create_share_token(self, auth_service, mock_db):
        """OWNER should be able to create share tokens."""
        mock_db.execute_query.return_value = [{'role': 'OWNER'}]
        
        result = auth_service.check_permission(
            user_id='owner-id',
            global_role='USER',
            room_id='room-123',
            action='CREATE_SHARE_TOKEN'
        )
        
        assert result is True
    
    def test_owner_can_download_file(self, auth_service, mock_db):
        """OWNER should be able to download files."""
        mock_db.execute_query.return_value = [{'role': 'OWNER'}]
        
        result = auth_service.check_permission(
            user_id='owner-id',
            global_role='USER',
            room_id='room-123',
            action='DOWNLOAD_FILE'
        )
        
        assert result is True
    
    def test_owner_can_view_files(self, auth_service, mock_db):
        """OWNER should be able to view files."""
        mock_db.execute_query.return_value = [{'role': 'OWNER'}]
        
        result = auth_service.check_permission(
            user_id='owner-id',
            global_role='USER',
            room_id='room-123',
            action='VIEW_FILES'
        )
        
        assert result is True
    
    # Test MEMBER permissions
    
    def test_member_cannot_add_member(self, auth_service, mock_db):
        """MEMBER should not be able to add members."""
        mock_db.execute_query.return_value = [{'role': 'MEMBER'}]
        
        result = auth_service.check_permission(
            user_id='member-id',
            global_role='USER',
            room_id='room-123',
            action='ADD_MEMBER'
        )
        
        assert result is False
    
    def test_member_cannot_remove_member(self, auth_service, mock_db):
        """MEMBER should not be able to remove members."""
        mock_db.execute_query.return_value = [{'role': 'MEMBER'}]
        
        result = auth_service.check_permission(
            user_id='member-id',
            global_role='USER',
            room_id='room-123',
            action='REMOVE_MEMBER'
        )
        
        assert result is False
    
    def test_member_cannot_change_role(self, auth_service, mock_db):
        """MEMBER should not be able to change roles."""
        mock_db.execute_query.return_value = [{'role': 'MEMBER'}]
        
        result = auth_service.check_permission(
            user_id='member-id',
            global_role='USER',
            room_id='room-123',
            action='CHANGE_ROLE'
        )
        
        assert result is False
    
    def test_member_can_upload_file(self, auth_service, mock_db):
        """MEMBER should be able to upload files."""
        mock_db.execute_query.return_value = [{'role': 'MEMBER'}]
        
        result = auth_service.check_permission(
            user_id='member-id',
            global_role='USER',
            room_id='room-123',
            action='UPLOAD_FILE'
        )
        
        assert result is True
    
    def test_member_can_download_file(self, auth_service, mock_db):
        """MEMBER should be able to download files."""
        mock_db.execute_query.return_value = [{'role': 'MEMBER'}]
        
        result = auth_service.check_permission(
            user_id='member-id',
            global_role='USER',
            room_id='room-123',
            action='DOWNLOAD_FILE'
        )
        
        assert result is True
    
    def test_member_can_view_files(self, auth_service, mock_db):
        """MEMBER should be able to view files."""
        mock_db.execute_query.return_value = [{'role': 'MEMBER'}]
        
        result = auth_service.check_permission(
            user_id='member-id',
            global_role='USER',
            room_id='room-123',
            action='VIEW_FILES'
        )
        
        assert result is True
    
    def test_member_can_create_share_token(self, auth_service, mock_db):
        """MEMBER should be able to create share tokens."""
        mock_db.execute_query.return_value = [{'role': 'MEMBER'}]
        
        result = auth_service.check_permission(
            user_id='member-id',
            global_role='USER',
            room_id='room-123',
            action='CREATE_SHARE_TOKEN'
        )
        
        assert result is True
    
    def test_member_cannot_delete_file(self, auth_service, mock_db):
        """MEMBER should not be able to delete files."""
        mock_db.execute_query.return_value = [{'role': 'MEMBER'}]
        
        result = auth_service.check_permission(
            user_id='member-id',
            global_role='USER',
            room_id='room-123',
            action='DELETE_FILE'
        )
        
        assert result is False
    
    # Test VIEWER permissions
    
    def test_viewer_cannot_add_member(self, auth_service, mock_db):
        """VIEWER should not be able to add members."""
        mock_db.execute_query.return_value = [{'role': 'VIEWER'}]
        
        result = auth_service.check_permission(
            user_id='viewer-id',
            global_role='USER',
            room_id='room-123',
            action='ADD_MEMBER'
        )
        
        assert result is False
    
    def test_viewer_cannot_upload_file(self, auth_service, mock_db):
        """VIEWER should not be able to upload files."""
        mock_db.execute_query.return_value = [{'role': 'VIEWER'}]
        
        result = auth_service.check_permission(
            user_id='viewer-id',
            global_role='USER',
            room_id='room-123',
            action='UPLOAD_FILE'
        )
        
        assert result is False
    
    def test_viewer_can_download_file(self, auth_service, mock_db):
        """VIEWER should be able to download files."""
        mock_db.execute_query.return_value = [{'role': 'VIEWER'}]
        
        result = auth_service.check_permission(
            user_id='viewer-id',
            global_role='USER',
            room_id='room-123',
            action='DOWNLOAD_FILE'
        )
        
        assert result is True
    
    def test_viewer_can_view_files(self, auth_service, mock_db):
        """VIEWER should be able to view files."""
        mock_db.execute_query.return_value = [{'role': 'VIEWER'}]
        
        result = auth_service.check_permission(
            user_id='viewer-id',
            global_role='USER',
            room_id='room-123',
            action='VIEW_FILES'
        )
        
        assert result is True
    
    def test_viewer_cannot_create_share_token(self, auth_service, mock_db):
        """VIEWER should not be able to create share tokens."""
        mock_db.execute_query.return_value = [{'role': 'VIEWER'}]
        
        result = auth_service.check_permission(
            user_id='viewer-id',
            global_role='USER',
            room_id='room-123',
            action='CREATE_SHARE_TOKEN'
        )
        
        assert result is False
    
    def test_viewer_cannot_delete_file(self, auth_service, mock_db):
        """VIEWER should not be able to delete files."""
        mock_db.execute_query.return_value = [{'role': 'VIEWER'}]
        
        result = auth_service.check_permission(
            user_id='viewer-id',
            global_role='USER',
            room_id='room-123',
            action='DELETE_FILE'
        )
        
        assert result is False
    
    # Test non-member access
    
    def test_non_member_cannot_access_room(self, auth_service, mock_db):
        """User who is not a member should not have access."""
        mock_db.execute_query.return_value = []  # No membership found
        
        result = auth_service.check_permission(
            user_id='non-member-id',
            global_role='USER',
            room_id='room-123',
            action='VIEW_FILES'
        )
        
        assert result is False
    
    # Test edge cases
    
    def test_permission_check_with_no_room_id_for_room_action(self, auth_service, mock_db):
        """Permission check should fail if room_id is None for room-specific action."""
        result = auth_service.check_permission(
            user_id='user-id',
            global_role='USER',
            room_id=None,
            action='UPLOAD_FILE'
        )
        
        assert result is False
    
    def test_get_user_role_in_room_returns_role(self, auth_service, mock_db):
        """get_user_role_in_room should return the user's role."""
        mock_db.execute_query.return_value = [{'role': 'MEMBER'}]
        
        role = auth_service.get_user_role_in_room('user-id', 'room-123')
        
        assert role == 'MEMBER'
        mock_db.execute_query.assert_called_once_with(
            "SELECT role FROM room_members WHERE room_id = %s AND user_id = %s",
            ('room-123', 'user-id')
        )
    
    def test_get_user_role_in_room_returns_none_for_non_member(self, auth_service, mock_db):
        """get_user_role_in_room should return None if user is not a member."""
        mock_db.execute_query.return_value = []
        
        role = auth_service.get_user_role_in_room('user-id', 'room-123')
        
        assert role is None
    
    def test_check_permission_matrix_with_unknown_role(self, auth_service):
        """_check_permission_matrix should return False for unknown role."""
        result = auth_service._check_permission_matrix('UNKNOWN_ROLE', 'UPLOAD_FILE')
        assert result is False
    
    def test_check_permission_matrix_with_unknown_action(self, auth_service):
        """_check_permission_matrix should return False for unknown action."""
        result = auth_service._check_permission_matrix('MEMBER', 'UNKNOWN_ACTION')
        assert result is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
