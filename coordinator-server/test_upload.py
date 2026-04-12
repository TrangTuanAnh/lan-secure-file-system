"""Unit tests for upload control module."""
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock, patch
from upload.scan_validator import ScanValidator
from upload.dedup_checker import DeduplicationChecker
from upload.upload_service import UploadService


class TestScanValidator(unittest.TestCase):
    """Test scan report validation."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.validator = ScanValidator()
        self.sha256_hash = "a" * 64
    
    def test_validate_scan_report_success(self):
        """Test successful scan report validation."""
        scan_report = {
            'result': 'CLEAN',
            'fileSha256': self.sha256_hash,
            'scannedAt': datetime.now(timezone.utc).isoformat(),
            'tool': 'ClamAV',
            'toolVersion': '1.0.0'
        }
        
        is_valid, error_code = self.validator.validate_scan_report(scan_report, self.sha256_hash)
        
        self.assertTrue(is_valid)
        self.assertIsNone(error_code)
    
    def test_validate_scan_report_infected(self):
        """Test scan report with INFECTED result."""
        scan_report = {
            'result': 'INFECTED',
            'fileSha256': self.sha256_hash,
            'scannedAt': datetime.now(timezone.utc).isoformat(),
            'tool': 'ClamAV',
            'toolVersion': '1.0.0'
        }
        
        is_valid, error_code = self.validator.validate_scan_report(scan_report, self.sha256_hash)
        
        self.assertFalse(is_valid)
        self.assertEqual(error_code, "SCAN_FAILED")
    
    def test_validate_scan_report_hash_mismatch(self):
        """Test scan report with mismatched hash."""
        scan_report = {
            'result': 'CLEAN',
            'fileSha256': "b" * 64,  # Different hash
            'scannedAt': datetime.now(timezone.utc).isoformat(),
            'tool': 'ClamAV',
            'toolVersion': '1.0.0'
        }
        
        is_valid, error_code = self.validator.validate_scan_report(scan_report, self.sha256_hash)
        
        self.assertFalse(is_valid)
        self.assertEqual(error_code, "SCAN_HASH_MISMATCH")
    
    def test_validate_scan_report_expired(self):
        """Test scan report older than 10 minutes."""
        # Create timestamp 11 minutes ago
        old_time = datetime.now(timezone.utc) - timedelta(minutes=11)
        scan_report = {
            'result': 'CLEAN',
            'fileSha256': self.sha256_hash,
            'scannedAt': old_time.isoformat(),
            'tool': 'ClamAV',
            'toolVersion': '1.0.0'
        }
        
        is_valid, error_code = self.validator.validate_scan_report(scan_report, self.sha256_hash)
        
        self.assertFalse(is_valid)
        self.assertEqual(error_code, "SCAN_EXPIRED")
    
    def test_validate_scan_report_missing_scanned_at(self):
        """Test scan report with missing scannedAt field."""
        scan_report = {
            'result': 'CLEAN',
            'fileSha256': self.sha256_hash,
            'tool': 'ClamAV',
            'toolVersion': '1.0.0'
        }
        
        is_valid, error_code = self.validator.validate_scan_report(scan_report, self.sha256_hash)
        
        self.assertFalse(is_valid)
        self.assertEqual(error_code, "SCAN_EXPIRED")
    
    def test_validate_scan_report_invalid_timestamp_format(self):
        """Test scan report with invalid timestamp format."""
        scan_report = {
            'result': 'CLEAN',
            'fileSha256': self.sha256_hash,
            'scannedAt': 'invalid-timestamp',
            'tool': 'ClamAV',
            'toolVersion': '1.0.0'
        }
        
        is_valid, error_code = self.validator.validate_scan_report(scan_report, self.sha256_hash)
        
        self.assertFalse(is_valid)
        self.assertEqual(error_code, "SCAN_EXPIRED")


class TestDeduplicationChecker(unittest.TestCase):
    """Test deduplication checking."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_db = Mock()
        self.checker = DeduplicationChecker(self.mock_db)
        self.sha256_hash = "a" * 64
    
    def test_check_deduplication_found(self):
        """Test deduplication when matching file exists."""
        # Mock database to return existing file
        self.mock_db.execute_query.return_value = [{
            'id': 'file-123',
            'stored_name': 'room-1/file-123',
            'room_id': 'room-1',
            'original_name': 'test.txt',
            'size_bytes': 1024
        }]
        
        result = self.checker.check_deduplication(self.sha256_hash)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['id'], 'file-123')
        self.assertEqual(result['stored_name'], 'room-1/file-123')
        
        # Verify query was called correctly
        self.mock_db.execute_query.assert_called_once()
        call_args = self.mock_db.execute_query.call_args
        self.assertIn('sha256_whole = %s', call_args[0][0])
        self.assertIn("status = %s", call_args[0][0])
        self.assertEqual(call_args[0][1], (self.sha256_hash, 'READY'))
    
    def test_check_deduplication_not_found(self):
        """Test deduplication when no matching file exists."""
        # Mock database to return empty result
        self.mock_db.execute_query.return_value = []
        
        result = self.checker.check_deduplication(self.sha256_hash)
        
        self.assertIsNone(result)
    
    def test_check_deduplication_database_error(self):
        """Test deduplication when database error occurs."""
        # Mock database to raise exception
        self.mock_db.execute_query.side_effect = Exception("Database error")
        
        result = self.checker.check_deduplication(self.sha256_hash)
        
        # Should return None on error to proceed with normal upload
        self.assertIsNone(result)


class TestUploadService(unittest.TestCase):
    """Test upload service operations."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_db = Mock()
        self.mock_redis = Mock()
        self.mock_authz = Mock()
        self.mock_audit = Mock()
        
        self.service = UploadService(
            database=self.mock_db,
            redis_client=self.mock_redis,
            authorization_service=self.mock_authz,
            audit_service=self.mock_audit,
            chunk_size=524288,
            ticket_ttl_seconds=1800
        )
        
        self.user_id = "user-123"
        self.room_id = "room-456"
        self.sha256_hash = "a" * 64
        
        self.file_info = {
            'originalName': 'test.txt',
            'sizeBytes': 1048576,  # 1MB
            'mimeType': 'text/plain',
            'sha256Whole': self.sha256_hash
        }
        
        self.scan_report = {
            'result': 'CLEAN',
            'fileSha256': self.sha256_hash,
            'scannedAt': datetime.now(timezone.utc).isoformat(),
            'tool': 'ClamAV',
            'toolVersion': '1.0.0'
        }
    
    def test_init_upload_permission_denied(self):
        """Test INIT_UPLOAD with insufficient permissions."""
        # Mock authorization to deny permission
        self.mock_authz.check_permission.return_value = False
        
        success, upload_plan, error_code = self.service.handle_init_upload(
            user_id=self.user_id,
            global_role='USER',
            room_id=self.room_id,
            file_info=self.file_info,
            scan_report=self.scan_report
        )
        
        self.assertFalse(success)
        self.assertIsNone(upload_plan)
        self.assertEqual(error_code, "PERMISSION_DENIED")
    
    def test_init_upload_invalid_scan_report(self):
        """Test INIT_UPLOAD with invalid scan report."""
        # Mock authorization to allow
        self.mock_authz.check_permission.return_value = True
        
        # Use infected scan report
        infected_scan = self.scan_report.copy()
        infected_scan['result'] = 'INFECTED'
        
        success, upload_plan, error_code = self.service.handle_init_upload(
            user_id=self.user_id,
            global_role='USER',
            room_id=self.room_id,
            file_info=self.file_info,
            scan_report=infected_scan
        )
        
        self.assertFalse(success)
        self.assertIsNone(upload_plan)
        self.assertEqual(error_code, "SCAN_FAILED")
    
    def test_init_upload_deduplicated(self):
        """Test INIT_UPLOAD with deduplication."""
        # Mock authorization to allow
        self.mock_authz.check_permission.return_value = True
        
        # Mock deduplication check to return existing file
        self.mock_db.execute_query.side_effect = [
            # Deduplication check
            [{
                'id': 'existing-file',
                'stored_name': 'room-1/existing-file',
                'room_id': 'room-1',
                'original_name': 'test.txt',
                'size_bytes': 1048576
            }],
            # Version calculation
            [{'max_version': 1}]
        ]
        
        # Mock database insert
        self.mock_db.execute_update.return_value = 1
        
        success, upload_plan, error_code = self.service.handle_init_upload(
            user_id=self.user_id,
            global_role='USER',
            room_id=self.room_id,
            file_info=self.file_info,
            scan_report=self.scan_report
        )
        
        self.assertTrue(success)
        self.assertIsNone(error_code)
        self.assertIsNotNone(upload_plan)
        self.assertTrue(upload_plan['deduplicated'])
        self.assertNotIn('ticket', upload_plan)
        self.assertEqual(upload_plan['totalChunks'], 2)  # 1MB / 512KB = 2 chunks
    
    def test_init_upload_new_file(self):
        """Test INIT_UPLOAD with new file (no deduplication)."""
        # Mock authorization to allow
        self.mock_authz.check_permission.return_value = True
        
        # Mock deduplication check to return no match
        self.mock_db.execute_query.side_effect = [
            # Deduplication check
            [],
            # Version calculation
            [{'max_version': None}]
        ]
        
        # Mock database insert
        self.mock_db.execute_update.return_value = 1
        
        success, upload_plan, error_code = self.service.handle_init_upload(
            user_id=self.user_id,
            global_role='USER',
            room_id=self.room_id,
            file_info=self.file_info,
            scan_report=self.scan_report
        )
        
        self.assertTrue(success)
        self.assertIsNone(error_code)
        self.assertIsNotNone(upload_plan)
        self.assertFalse(upload_plan['deduplicated'])
        self.assertIn('ticket', upload_plan)
        self.assertEqual(upload_plan['totalChunks'], 2)
        
        # Verify ticket was stored in Redis
        self.mock_redis.set_ticket.assert_called_once()
    
    def test_handle_upload_complete_success(self):
        """Test UPLOAD_COMPLETE handler."""
        # Mock database to return file
        self.mock_db.execute_query.return_value = [{
            'id': 'file-123',
            'room_id': self.room_id,
            'original_name': 'test.txt',
            'uploader_id': self.user_id,
            'sha256_whole': self.sha256_hash
        }]
        
        # Mock database update
        self.mock_db.execute_update.return_value = 1
        
        success, error_code = self.service.handle_upload_complete(
            file_id='file-123',
            sha256_whole=self.sha256_hash,
            stored_name='room-456/file-123',
            final_size=1048576
        )
        
        self.assertTrue(success)
        self.assertIsNone(error_code)
        
        # Verify file status was updated
        self.mock_db.execute_update.assert_called_once()
        call_args = self.mock_db.execute_update.call_args
        self.assertIn('UPDATE files SET status', call_args[0][0])
        self.assertEqual(call_args[0][1][0], 'READY')
    
    def test_handle_upload_complete_hash_mismatch(self):
        """Test UPLOAD_COMPLETE with hash mismatch."""
        # Mock database to return file with different hash
        self.mock_db.execute_query.return_value = [{
            'id': 'file-123',
            'room_id': self.room_id,
            'original_name': 'test.txt',
            'uploader_id': self.user_id,
            'sha256_whole': "b" * 64  # Different hash
        }]
        
        # Mock database update
        self.mock_db.execute_update.return_value = 1
        
        success, error_code = self.service.handle_upload_complete(
            file_id='file-123',
            sha256_whole=self.sha256_hash,
            stored_name='room-456/file-123',
            final_size=1048576
        )
        
        self.assertFalse(success)
        self.assertEqual(error_code, "HASH_MISMATCH")
        
        # Verify file was marked as DELETED
        call_args = self.mock_db.execute_update.call_args
        self.assertEqual(call_args[0][1][0], 'DELETED')
    
    def test_handle_upload_failed(self):
        """Test UPLOAD_FAILED handler."""
        # Mock database to return file
        self.mock_db.execute_query.return_value = [{
            'id': 'file-123',
            'room_id': self.room_id,
            'original_name': 'test.txt',
            'uploader_id': self.user_id
        }]
        
        # Mock database update
        self.mock_db.execute_update.return_value = 1
        
        success, error_code = self.service.handle_upload_failed(
            file_id='file-123',
            reason='Storage error'
        )
        
        self.assertTrue(success)
        self.assertIsNone(error_code)
        
        # Verify file status was updated to DELETED
        self.mock_db.execute_update.assert_called_once()
        call_args = self.mock_db.execute_update.call_args
        self.assertIn('UPDATE files SET status', call_args[0][0])
        self.assertEqual(call_args[0][1][0], 'DELETED')
        
        # Verify audit log was written
        self.mock_audit.write_audit_log.assert_called_once()
        audit_call = self.mock_audit.write_audit_log.call_args
        self.assertEqual(audit_call[1]['status'], 'FAILED')


if __name__ == '__main__':
    unittest.main()
