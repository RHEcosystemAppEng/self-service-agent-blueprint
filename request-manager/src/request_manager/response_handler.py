"""Shared response handling logic for both eventing and direct HTTP modes."""

from typing import Any, Dict, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class UnifiedResponseHandler:
    """Unified response handler that works for both communication modes."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def process_agent_response(
        self,
        request_id: str,
        session_id: str,
        user_id: Optional[str],
        agent_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        processing_time_ms: Optional[int] = None,
        requires_followup: bool = False,
        followup_actions: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Process an agent response and update the database."""

        logger.debug(
            "Response processed - routing handled by Agent Service",
            session_id=session_id,
            agent_id=agent_id,
        )

        # Send database update event to Agent Service
        await self._send_database_update_event(
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            agent_id=agent_id,
            content=content,
            metadata=metadata,
            processing_time_ms=processing_time_ms,
        )

        logger.info(
            "Agent response processed successfully",
            request_id=request_id,
            session_id=session_id,
            agent_id=agent_id,
            content_length=len(content),
            processing_time_ms=processing_time_ms,
        )

        return {
            "status": "processed",
            "request_id": request_id,
            "session_id": session_id,
            "agent_id": agent_id,
            "requires_followup": requires_followup,
            "followup_actions": followup_actions or [],
        }

    async def _send_database_update_event(
        self,
        request_id: str,
        session_id: str,
        user_id: Optional[str],
        agent_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        processing_time_ms: Optional[int] = None,
    ) -> None:
        """Send database update event to Agent Service."""
        try:
            from .events import get_event_publisher

            event_publisher = get_event_publisher()
            if not event_publisher:
                logger.error("Event publisher not available for database update event")
                return

            event_data = {
                "request_id": request_id,
                "session_id": session_id,
                "user_id": user_id,
                "agent_id": agent_id,
                "content": content,
                "metadata": metadata or {},
                "processing_time_ms": processing_time_ms,
            }

            await event_publisher.publish_database_update_event(event_data)

            logger.info(
                "Database update event sent to Agent Service",
                request_id=request_id,
                session_id=session_id,
                agent_id=agent_id,
            )

        except Exception as e:
            logger.error(
                "Failed to send database update event",
                request_id=request_id,
                error=str(e),
            )
