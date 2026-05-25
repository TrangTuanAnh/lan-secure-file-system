"""Download handlers for socket message processing."""
from typing import Dict, Any, Optional
from download.download_service import DownloadService
from logging_config import get_logger

logger = get_logger(__name__)


class DownloadHandlers:
    """Handlers for download-related socket messages."""
    
    def __init__(self, download_service: DownloadService):
        """
        Initialize download handlers.
        
        Args:
            download_service: Download service instance
        """
        self.download_service = download_service
    
    def handle_init_download(
        self,
        user_id: str,
        global_role: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle INIT_DOWNLOAD message with access token (direct permission).
        
        Args:
            user_id: Authenticated user ID
            global_role: User's global role
            payload: Message payload containing:
                - fileId: File identifier
                - version: Optional version number
        
        Returns:
            Response message with DOWNLOAD_PLAN or error
        """
        file_id = payload.get('fileId')
        version = payload.get('version')
        
        if not file_id:
            return {
                'type': 'ERROR',
                'error': {
                    'code': 'INVALID_INPUT',
                    'message': 'Missing required field: fileId'
                }
            }
        
        success, download_plan, error_code = self.download_service.handle_init_download_direct(
            user_id=user_id,
            global_role=global_role,
            file_id=file_id,
            version=version
        )
        
        if success:
            return {
                'type': 'DOWNLOAD_PLAN',
                'payload': download_plan
            }
        else:
            return {
                'type': 'ERROR',
                'error': {
                    'code': error_code,
                    'message': self._get_error_message(error_code)
                }
            }
    
    def handle_init_download_share(
        self,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle INIT_DOWNLOAD message with share token (no authentication required).
        
        Args:
            payload: Message payload containing:
                - shareToken: Share token string
                - fileId: File identifier
        
        Returns:
            Response message with DOWNLOAD_PLAN or error
        """
        share_token = payload.get('shareToken')
        file_id = payload.get('fileId')
        
        if not share_token or not file_id:
            return {
                'type': 'ERROR',
                'error': {
                    'code': 'INVALID_INPUT',
                    'message': 'Missing required fields: shareToken and fileId'
                }
            }
        
        success, download_plan, error_code = self.download_service.handle_init_download_share(
            share_token=share_token,
            file_id=file_id
        )
        
        if success:
            return {
                'type': 'DOWNLOAD_PLAN',
                'payload': download_plan
            }
        else:
            return {
                'type': 'ERROR',
                'error': {
                    'code': error_code,
                    'message': self._get_error_message(error_code)
                }
            }
    
    def handle_create_share_token(
        self,
        user_id: str,
        global_role: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle CREATE_SHARE_TOKEN message.
        
        Args:
            user_id: Authenticated user ID
            global_role: User's global role
            payload: Message payload containing:
                - fileId: File identifier
                - maxDownloads: Maximum number of downloads
                - expiresAt: Expiration timestamp (ISO 8601 string)
        
        Returns:
            Response message with token or error
        """
        from datetime import datetime
        
        from datetime import timezone

        file_id = payload.get('fileId')
        max_downloads = payload.get('maxDownloads')
        expires_at_str = payload.get('expiresAt')

        if not all([file_id, max_downloads is not None, expires_at_str]):
            return {
                'type': 'ERROR',
                'error': {
                    'code': 'INVALID_INPUT',
                    'message': 'Missing required fields: fileId, maxDownloads, expiresAt'
                }
            }

        # Validate maxDownloads range (must be a positive integer, capped to a
        # reasonable upper bound to prevent token abuse / mistakes)
        try:
            max_downloads = int(max_downloads)
        except (TypeError, ValueError):
            return {
                'type': 'ERROR',
                'error': {
                    'code': 'INVALID_INPUT',
                    'message': 'maxDownloads must be an integer'
                }
            }
        if max_downloads < 1 or max_downloads > 10000:
            return {
                'type': 'ERROR',
                'error': {
                    'code': 'INVALID_INPUT',
                    'message': 'maxDownloads must be between 1 and 10000'
                }
            }

        # Parse expiration timestamp
        try:
            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
        except ValueError:
            return {
                'type': 'ERROR',
                'error': {
                    'code': 'INVALID_INPUT',
                    'message': 'Invalid expiresAt format (expected ISO 8601)'
                }
            }

        # Reject expires_at in the past
        now = datetime.now(timezone.utc)
        # If naive datetime, assume UTC
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            return {
                'type': 'ERROR',
                'error': {
                    'code': 'INVALID_INPUT',
                    'message': 'expiresAt must be in the future'
                }
            }

        success, token_string, error_code = self.download_service.create_share_token(
            user_id=user_id,
            global_role=global_role,
            file_id=file_id,
            max_downloads=max_downloads,
            expires_at=expires_at
        )

        if success:
            # NOTE: Use CREATE_SHARE_TOKEN_RESPONSE to match MessageType enum.
            # The outer client_socket_server overrides type anyway, but keeping
            # this in sync prevents future drift.
            return {
                'type': 'CREATE_SHARE_TOKEN_RESPONSE',
                'payload': {
                    'token': token_string,
                    'fileId': file_id,
                    'maxDownloads': max_downloads,
                    'expiresAt': expires_at_str
                }
            }
        else:
            return {
                'type': 'ERROR',
                'error': {
                    'code': error_code,
                    'message': self._get_error_message(error_code)
                }
            }
    
    def _get_error_message(self, error_code: str) -> str:
        """
        Get human-readable error message for error code.
        
        Args:
            error_code: Error code
        
        Returns:
            Error message string
        """
        error_messages = {
            'FILE_NOT_FOUND': 'File not found',
            'FILE_NOT_READY': 'File is not ready for download',
            'PERMISSION_DENIED': 'You do not have permission to download this file',
            'INVALID_SHARE_TOKEN': 'Share token is invalid or does not match the file',
            'SHARE_TOKEN_EXPIRED': 'Share token has expired',
            'SHARE_TOKEN_EXHAUSTED': 'Share token has reached maximum downloads',
            'STORAGE_NODE_UNAVAILABLE': 'The storage node that owns this file is unavailable',
            'FILE_NOT_ON_NODE': 'The storage node that owns this file no longer holds it',
            'DATABASE_ERROR': 'Database error occurred',
            'INVALID_INPUT': 'Invalid input parameters'
        }
        return error_messages.get(error_code, 'Unknown error')
