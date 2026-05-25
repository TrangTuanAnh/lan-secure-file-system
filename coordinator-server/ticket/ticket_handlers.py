"""Handlers for ticket verification requests from Storage Nodes.

NOTE: The PRODUCTION path for VERIFY_TICKET is implemented in
`storage_node.storage_node_server._handle_verify_ticket`. That handler is
what's wired to the live storage-node socket (port 8081).

This module is kept for legacy tests and example integrations. The response
format has been aligned with the production handler so both produce the same
payload shape — preventing the contract mismatch that was previously present
(production used flat ticket_data, this module used {ticketId, metadata}).
"""
from typing import Dict, Any
from protocol.message import Message
from protocol.message_types import MessageType
from ticket.ticket_service import TicketService
from logging_config import get_logger

logger = get_logger(__name__)


class TicketHandlers:
    """Handles ticket verification requests from Storage Nodes (legacy)."""

    def __init__(self, ticket_service: TicketService):
        self.ticket_service = ticket_service

    def handle_verify_ticket(self, message: Message) -> Message:
        """Handle VERIFY_TICKET request — aligned with production format.

        Request payload (Java sends `.set("ticket", ticketId)`):
            {"ticket": "uuid-string"}

        Success response (TICKET_VALID) — flat ticket_data, matching
        ``storage_node_server._handle_verify_ticket``:
            {"type": "upload"|"download", "fileId": ..., "sha256Whole": ...,
             "totalChunks": ..., "chunkSize": ...}

        Error response (TICKET_INVALID):
            {"error": "TICKET_NOT_FOUND" | "TICKET_EXPIRED"}
        """
        payload = message.payload
        # Accept both 'ticket' (production / Java client) and 'ticketId' (legacy)
        ticket_id = payload.get('ticket') or payload.get('ticketId')

        if not ticket_id:
            logger.warning("VERIFY_TICKET request missing ticket id field")
            return Message.create_error(
                error_code="INVALID_REQUEST",
                error_message="Missing required field: ticket",
                request_id=message.request_id
            )

        is_valid, ticket_metadata, error_code = self.ticket_service.verify_ticket(ticket_id)

        if is_valid:
            logger.info(f"VERIFY_TICKET success: ticket={ticket_id}")
            # Flat payload to match production storage_node_server format
            return Message.create_response(
                message_type=MessageType.TICKET_VALID,
                payload=ticket_metadata,
                request_id=message.request_id
            )

        logger.info(f"VERIFY_TICKET failed: ticket={ticket_id}, error={error_code}")
        return Message.create_response(
            message_type=MessageType.TICKET_INVALID,
            payload={"error": error_code},
            request_id=message.request_id
        )
