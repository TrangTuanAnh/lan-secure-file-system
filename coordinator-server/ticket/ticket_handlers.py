"""Handlers for ticket verification requests from Storage Nodes."""
from typing import Dict, Any
from protocol.message import Message
from protocol.message_types import MessageType
from ticket.ticket_service import TicketService
from logging_config import get_logger

logger = get_logger(__name__)


class TicketHandlers:
    """Handles ticket verification requests from Storage Nodes."""
    
    def __init__(self, ticket_service: TicketService):
        """
        Initialize ticket handlers.
        
        Args:
            ticket_service: Ticket service instance
        """
        self.ticket_service = ticket_service
    
    def handle_verify_ticket(self, message: Message) -> Message:
        """
        Handle VERIFY_TICKET request from Storage Node.
        
        Requirements: 6.6, 6.7, 6.8, 6.9
        
        Request payload:
        {
            "ticketId": "uuid-string"
        }
        
        Success response (TICKET_VALID):
        {
            "ticketId": "uuid-string",
            "metadata": {
                "type": "upload" | "download",
                "fileId": "uuid",
                "storedName": "path",
                "sha256Whole": "hash",
                "totalChunks": 10,
                "chunkSize": 524288,
                ... (additional fields based on ticket type)
            }
        }
        
        Error response (TICKET_INVALID):
        {
            "error": {
                "code": "TICKET_NOT_FOUND" | "TICKET_EXPIRED",
                "message": "..."
            }
        }
        
        Args:
            message: VERIFY_TICKET request message
        
        Returns:
            TICKET_VALID or TICKET_INVALID response message
        """
        payload = message.payload
        ticket_id = payload.get('ticketId')
        
        if not ticket_id:
            logger.warning("VERIFY_TICKET request missing ticketId")
            return Message.create_error(
                error_code="INVALID_REQUEST",
                error_message="Missing required field: ticketId",
                request_id=message.request_id
            )
        
        # Verify ticket
        is_valid, ticket_metadata, error_code = self.ticket_service.verify_ticket(ticket_id)
        
        if is_valid:
            # Return TICKET_VALID with metadata
            logger.info(f"VERIFY_TICKET success: ticket={ticket_id}")
            
            return Message.create_response(
                message_type=MessageType.TICKET_VALID,
                payload={
                    'ticketId': ticket_id,
                    'metadata': ticket_metadata
                },
                request_id=message.request_id
            )
        else:
            # Return TICKET_INVALID with error
            logger.info(f"VERIFY_TICKET failed: ticket={ticket_id}, error={error_code}")
            
            error_messages = {
                'TICKET_NOT_FOUND': 'Ticket does not exist',
                'TICKET_EXPIRED': 'Ticket has expired',
                'INTERNAL_ERROR': 'Internal server error'
            }
            
            return Message.create_response(
                message_type=MessageType.TICKET_INVALID,
                payload={
                    'ticketId': ticket_id,
                    'error': {
                        'code': error_code,
                        'message': error_messages.get(error_code, 'Unknown error')
                    }
                },
                request_id=message.request_id
            )
