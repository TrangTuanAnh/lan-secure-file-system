"""Helpers for data-plane HMAC ticket fields.

The Java Storage Node validates upload/download opens with:
sessionId|fileId|nodeId|expiry signed by the shared storage-node secret.
"""
import hashlib
import hmac
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any


def create_hmac_ticket_fields(
    file_id: str,
    node_id: str,
    secret: str,
    ttl_seconds: int
) -> Dict[str, Any]:
    """Create fields consumed by the Storage Node data-plane protocol."""
    session_id = str(uuid.uuid4())
    expiry = int((datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).timestamp())
    payload = f"{session_id}|{file_id}|{node_id}|{expiry}"
    signature = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return {
        "sessionId": session_id,
        "ticketNodeId": node_id,
        "ticketExpiry": expiry,
        "ticketSignature": signature,
    }
