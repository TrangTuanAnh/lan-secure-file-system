"""Scan report validation for upload control."""
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple
from logging_config import get_logger

logger = get_logger(__name__)


class ScanValidator:
    """Validates antivirus scan reports for file uploads."""
    
    # Maximum age for scan reports (10 minutes)
    MAX_SCAN_AGE_MINUTES = 10
    
    def validate_scan_report(
        self,
        scan_report: Dict[str, Any],
        sha256_whole: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate scan report for upload authorization.
        
        Validates:
        - result field equals 'CLEAN'
        - fileSha256 matches sha256Whole from request
        - scannedAt is not older than 10 minutes
        
        Args:
            scan_report: Scan report dictionary with fields:
                - result: 'CLEAN' or 'INFECTED'
                - fileSha256: SHA256 hash from scanner
                - scannedAt: ISO-8601 timestamp
                - tool: Scanner tool name
                - toolVersion: Scanner version
            sha256_whole: Expected SHA256 hash from request
        
        Returns:
            Tuple of (is_valid, error_code)
            - (True, None) if valid
            - (False, error_code) if invalid with specific error:
                - SCAN_FAILED: result is not CLEAN
                - SCAN_HASH_MISMATCH: fileSha256 doesn't match
                - SCAN_EXPIRED: scannedAt is too old
        """
        # Verify result field equals 'CLEAN'
        result = scan_report.get('result')
        if result != 'CLEAN':
            logger.warning(f"Scan validation failed: result={result} (expected CLEAN)")
            return False, "SCAN_FAILED"
        
        # Verify fileSha256 matches sha256Whole from request
        file_sha256 = scan_report.get('fileSha256')
        if file_sha256 != sha256_whole:
            logger.warning(
                f"Scan validation failed: hash mismatch "
                f"(scan={file_sha256}, request={sha256_whole})"
            )
            return False, "SCAN_HASH_MISMATCH"
        
        # Verify scannedAt is not older than 10 minutes
        scanned_at_str = scan_report.get('scannedAt')
        if not scanned_at_str:
            logger.warning("Scan validation failed: scannedAt field missing")
            return False, "SCAN_EXPIRED"
        
        try:
            # Parse ISO-8601 timestamp
            scanned_at = datetime.fromisoformat(scanned_at_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            age = now - scanned_at
            
            if age > timedelta(minutes=self.MAX_SCAN_AGE_MINUTES):
                logger.warning(
                    f"Scan validation failed: scan too old "
                    f"(age={age.total_seconds():.0f}s, max={self.MAX_SCAN_AGE_MINUTES * 60}s)"
                )
                return False, "SCAN_EXPIRED"
            
        except (ValueError, AttributeError) as e:
            logger.warning(f"Scan validation failed: invalid scannedAt format: {e}")
            return False, "SCAN_EXPIRED"
        
        logger.debug(f"Scan validation passed for hash {sha256_whole[:16]}...")
        return True, None
