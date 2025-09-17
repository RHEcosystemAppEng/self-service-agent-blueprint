"""Shared response handling logic for both eventing and direct HTTP modes."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog
from shared_db.models import RequestLog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .routing import detect_and_validate_agent_routing
from .session_manager import SessionManager

logger = structlog.get_logger()


class UnifiedResponseHandler:
    """Unified response handler that works for both communication modes."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.session_manager = SessionManager(db)

    async def process_agent_response(
        self,
        request_id: str,
        session_id: str,
        agent_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        processing_time_ms: Optional[int] = None,
        requires_followup: bool = False,
        followup_actions: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Process an agent response and update the database."""

        # Check if this request already has a response (deduplication)
        existing_response = await self._check_existing_response(request_id)
        if existing_response:
            logger.info(
                "Request already has response - skipping duplicate processing",
                request_id=request_id,
                session_id=session_id,
                agent_id=agent_id,
            )
            return {
                "status": "skipped",
                "reason": "response already processed",
                "request_id": request_id,
            }

        # Check if this is a routing response that should switch agents
        routed_agent = await self._detect_and_validate_agent_routing(content, agent_id)

        if routed_agent:
            # Update session to use the routed agent
            await self.session_manager.update_session(
                session_id,
                agent_id=routed_agent,
                status="ACTIVE",
            )
            logger.info(
                "Agent routing detected",
                request_id=request_id,
                session_id=session_id,
                from_agent=agent_id,
                to_agent=routed_agent,
            )

        # Update request log with response
        await self._update_request_log(
            request_id=request_id,
            agent_id=agent_id,
            content=content,
            metadata=metadata,
            processing_time_ms=processing_time_ms,
        )

        # Update session with response metadata
        await self._update_session_context(
            session_id=session_id,
            agent_id=agent_id,
            content=content,
            metadata=metadata,
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

    async def _check_existing_response(self, request_id: str) -> Optional[RequestLog]:
        """Check if a request already has a response."""
        stmt = select(RequestLog).where(
            RequestLog.request_id == request_id,
            RequestLog.response_content.is_not(None),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _update_request_log(
        self,
        request_id: str,
        agent_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        processing_time_ms: Optional[int] = None,
    ) -> None:
        """Update the request log with response information."""
        stmt = select(RequestLog).where(RequestLog.request_id == request_id)
        result = await self.db.execute(stmt)
        request_log = result.scalar_one_or_none()

        if request_log:
            request_log.response_content = content
            request_log.response_metadata = metadata or {}
            request_log.agent_id = agent_id
            request_log.processing_time_ms = processing_time_ms
            request_log.completed_at = datetime.now(timezone.utc)

            await self.db.commit()
        else:
            logger.warning("Request log not found for response", request_id=request_id)

    async def _update_session_context(
        self,
        session_id: str,
        agent_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update session context with response information."""
        # This could include updating conversation context, user context, etc.
        # For now, we'll just log the update
        logger.debug(
            "Session context updated with response",
            session_id=session_id,
            agent_id=agent_id,
            has_metadata=bool(metadata),
        )

    async def _detect_and_validate_agent_routing(
        self, content: str, current_agent_id: str
    ) -> Optional[str]:
        """Detect if the response indicates agent routing should occur."""
        # Use the routing detection logic
        return await detect_and_validate_agent_routing(content, current_agent_id)

    async def get_response_data(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Get response data for a request."""
        stmt = select(RequestLog).where(RequestLog.request_id == request_id)
        result = await self.db.execute(stmt)
        request_log = result.scalar_one_or_none()

        if not request_log or not request_log.response_content:
            return None

        return {
            "agent_id": request_log.agent_id,
            "content": request_log.response_content,
            "metadata": request_log.response_metadata or {},
            "processing_time_ms": request_log.processing_time_ms,
            "completed_at": (
                request_log.completed_at.isoformat()
                if request_log.completed_at
                else None
            ),
        }
