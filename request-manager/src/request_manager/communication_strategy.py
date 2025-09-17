"""Communication strategy abstraction for eventing vs direct HTTP modes."""

import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog
from shared_db import get_enum_value
from shared_db.models import RequestLog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .direct_client import get_agent_client, get_integration_client
from .events import get_event_publisher
from .normalizer import RequestNormalizer
from .routing import detect_and_validate_agent_routing
from .schemas import AgentResponse, NormalizedRequest

logger = structlog.get_logger()


class CommunicationStrategy(ABC):
    """Abstract base class for communication strategies."""

    @abstractmethod
    async def send_request(self, normalized_request: NormalizedRequest) -> bool:
        """Send a request to the agent service."""
        pass

    @abstractmethod
    async def wait_for_response(
        self, request_id: str, timeout: int, db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """Wait for and retrieve the agent response."""
        pass

    @abstractmethod
    async def deliver_response(self, agent_response: AgentResponse) -> bool:
        """Deliver the response to the integration dispatcher."""
        pass


class EventingStrategy(CommunicationStrategy):
    """Communication strategy using Knative eventing."""

    def __init__(self):
        self.event_publisher = get_event_publisher()

    async def send_request(self, normalized_request: NormalizedRequest) -> bool:
        """Send request via CloudEvent."""
        from .events import EventTypes

        success = await self.event_publisher.publish_request_event(
            normalized_request, EventTypes.REQUEST_CREATED
        )

        if not success:
            logger.error("Failed to publish request event")
            return False

        logger.info(
            "Request sent via eventing",
            request_id=normalized_request.request_id,
            session_id=normalized_request.session_id,
        )
        return True

    async def wait_for_response(
        self, request_id: str, timeout: int, db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """Wait for response by polling database (eventing mode)."""
        from datetime import datetime, timedelta

        start_time = datetime.now()
        end_time = start_time + timedelta(seconds=timeout)

        while datetime.now() < end_time:
            await db.rollback()  # Clear any pending transaction

            stmt = select(RequestLog).where(RequestLog.request_id == request_id)
            result = await db.execute(stmt)
            request_log = result.scalar_one_or_none()

            if request_log and request_log.response_content:
                logger.info(
                    "Response received via eventing",
                    request_id=request_id,
                    elapsed_seconds=(datetime.now() - start_time).total_seconds(),
                )
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

            # Wait before next poll
            import asyncio

            await asyncio.sleep(0.5)

        logger.warning(
            "Timeout waiting for response via eventing", request_id=request_id
        )
        return None

    async def deliver_response(self, agent_response: AgentResponse) -> bool:
        """Deliver response via CloudEvent."""
        from .events import EventTypes

        success = await self.event_publisher.publish_response_event(
            agent_response, EventTypes.AGENT_RESPONSE_READY
        )

        if not success:
            logger.error("Failed to publish response event")
            return False

        logger.info(
            "Response delivered via eventing",
            request_id=agent_response.request_id,
            session_id=agent_response.session_id,
        )
        return True


class DirectHttpStrategy(CommunicationStrategy):
    """Communication strategy using direct HTTP calls."""

    def __init__(self):
        self.agent_client = get_agent_client()
        self.integration_client = get_integration_client()

    async def send_request(self, normalized_request: NormalizedRequest) -> bool:
        """Send request via direct HTTP."""
        if not self.agent_client:
            logger.error("Agent client not initialized")
            return False

        logger.info(
            "Request sent via direct HTTP",
            request_id=normalized_request.request_id,
            session_id=normalized_request.session_id,
        )
        return True  # Request will be processed synchronously

    async def wait_for_response(
        self, request_id: str, timeout: int, db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """Process request synchronously and return response."""
        # This method should not be called in direct HTTP mode
        # as the request is processed synchronously in the main flow
        logger.warning(
            "wait_for_response called in direct HTTP mode - this should not happen"
        )
        return None

    async def deliver_response(self, agent_response: AgentResponse) -> bool:
        """Deliver response via direct HTTP."""
        if not self.integration_client:
            logger.error("Integration client not initialized")
            return False

        success = await self.integration_client.deliver_response(agent_response)

        if not success:
            logger.error("Failed to deliver response via direct HTTP")
            return False

        logger.info(
            "Response delivered via direct HTTP",
            request_id=agent_response.request_id,
            session_id=agent_response.session_id,
        )
        return True


def get_communication_strategy() -> CommunicationStrategy:
    """Get the appropriate communication strategy based on configuration."""
    eventing_enabled = os.getenv("EVENTING_ENABLED", "true").lower() == "true"

    if eventing_enabled:
        return EventingStrategy()
    else:
        return DirectHttpStrategy()


class UnifiedRequestProcessor:
    """Unified request processor that works with any communication strategy."""

    def __init__(self, strategy: CommunicationStrategy):
        self.strategy = strategy

    async def _handle_agent_routing(
        self, agent_response, normalized_request, agent_client, db: AsyncSession
    ):
        """Handle agent routing detection and processing."""
        routed_agent = await detect_and_validate_agent_routing(
            agent_response.content, agent_response.agent_id
        )

        if routed_agent:
            logger.info(
                "Agent routing detected",
                from_agent=agent_response.agent_id,
                to_agent=routed_agent,
                request_id=normalized_request.request_id,
            )

            # Create a new request to the routed agent
            routed_request = normalized_request.model_copy()
            routed_request.target_agent_id = routed_agent
            routed_request.content = normalized_request.content  # Keep original content

            # Process the routed request
            routed_response = await agent_client.process_request(routed_request)
            logger.info(
                "Routed request processed",
                target_agent=routed_agent,
                request_id=normalized_request.request_id,
                routed_response_exists=routed_response is not None,
                routed_response_content=(
                    routed_response.content[:100] if routed_response else "None"
                ),
            )
            if routed_response:
                # Use the routed agent's response
                agent_response = routed_response

                # Update session with the target agent ID so subsequent requests continue with this agent
                from .session_manager import SessionManager

                session_manager = SessionManager(db)
                await session_manager.update_session(
                    session_id=normalized_request.session_id,
                    agent_id=routed_agent,
                )

                logger.info(
                    "Successfully routed to target agent",
                    target_agent=routed_agent,
                    request_id=normalized_request.request_id,
                    final_agent_id=agent_response.agent_id,
                    final_content=agent_response.content[:100],
                )
            else:
                logger.warning(
                    "Routed request returned no response",
                    target_agent=routed_agent,
                    request_id=normalized_request.request_id,
                )

        return agent_response

    async def process_request_async(self, request, db: AsyncSession) -> Dict[str, Any]:
        """Process a request asynchronously (eventing mode)."""
        from .session_manager import SessionManager

        session_manager = SessionManager(db)
        normalizer = RequestNormalizer()

        # Find or create session
        session = await session_manager.find_or_create_session(
            user_id=request.user_id,
            integration_type=request.integration_type,
            channel_id=getattr(request, "channel_id", None),
            thread_id=getattr(request, "thread_id", None),
            integration_metadata=request.metadata,
        )

        # Normalize the request
        normalized_request = normalizer.normalize_request(
            request, session.session_id, session.current_agent_id
        )

        # Log the request
        request_log = RequestLog(
            request_id=normalized_request.request_id,
            session_id=session.session_id,
            request_type=request.request_type,
            request_content=request.content,
            normalized_request=normalized_request.model_dump(mode="json"),
            agent_id=normalized_request.target_agent_id,
        )

        db.add(request_log)
        await db.commit()

        await session_manager.increment_request_count(
            session.session_id, normalized_request.request_id
        )

        # Send request using strategy
        success = await self.strategy.send_request(normalized_request)

        if not success:
            raise Exception("Failed to send request")

        logger.info(
            "Request processed asynchronously",
            request_id=normalized_request.request_id,
            session_id=session.session_id,
            user_id=request.user_id,
            integration_type=get_enum_value(request.integration_type),
        )

        return {
            "request_id": normalized_request.request_id,
            "session_id": session.session_id,
            "status": "accepted",
            "message": "Request has been queued for processing",
        }

    async def process_request_async_with_delivery(
        self, request, db: AsyncSession, timeout: int = 120
    ) -> Dict[str, Any]:
        """Process a request asynchronously but deliver response in direct HTTP mode."""
        from .session_manager import SessionManager

        session_manager = SessionManager(db)
        normalizer = RequestNormalizer()

        # Find or create session
        session = await session_manager.find_or_create_session(
            user_id=request.user_id,
            integration_type=request.integration_type,
            channel_id=getattr(request, "channel_id", None),
            thread_id=getattr(request, "thread_id", None),
            integration_metadata=request.metadata,
        )

        # Normalize the request
        normalized_request = normalizer.normalize_request(
            request, session.session_id, session.current_agent_id
        )

        # Log the request
        request_log = RequestLog(
            request_id=normalized_request.request_id,
            session_id=session.session_id,
            request_type=request.request_type,
            request_content=request.content,
            normalized_request=normalized_request.model_dump(mode="json"),
            agent_id=normalized_request.target_agent_id,
        )

        db.add(request_log)
        await db.commit()

        await session_manager.increment_request_count(
            session.session_id, normalized_request.request_id
        )

        # In direct HTTP mode, process synchronously but return immediately to avoid timeout
        if isinstance(self.strategy, DirectHttpStrategy):
            # Process the request in the background
            import asyncio

            asyncio.create_task(
                self._process_and_deliver_background(
                    normalized_request, request_log, db
                )
            )

            logger.info(
                "Request queued for background processing",
                request_id=normalized_request.request_id,
                session_id=session.session_id,
                user_id=request.user_id,
                integration_type=get_enum_value(request.integration_type),
            )

            return {
                "request_id": normalized_request.request_id,
                "session_id": session.session_id,
                "status": "accepted",
                "message": "Request has been queued for processing",
            }
        else:
            # Eventing mode - use standard async processing
            success = await self.strategy.send_request(normalized_request)

            if not success:
                raise Exception("Failed to send request")

            logger.info(
                "Request processed asynchronously",
                request_id=normalized_request.request_id,
                session_id=session.session_id,
                user_id=request.user_id,
                integration_type=get_enum_value(request.integration_type),
            )

            return {
                "request_id": normalized_request.request_id,
                "session_id": session.session_id,
                "status": "accepted",
                "message": "Request has been queued for processing",
            }

    async def _process_and_deliver_background(
        self, normalized_request, request_log, db
    ):
        """Process request in background and deliver response."""
        try:
            # Process the request
            agent_client = get_agent_client()
            if not agent_client:
                logger.error("Agent client not initialized for background processing")
                return

            agent_response = await agent_client.process_request(normalized_request)
            if not agent_response:
                logger.error("Agent service failed to process request in background")
                return

            # Handle agent routing
            agent_response = await self._handle_agent_routing(
                agent_response, normalized_request, agent_client, db
            )

            # Update request log with response
            request_log.response_content = agent_response.content
            request_log.response_metadata = agent_response.metadata
            request_log.agent_id = agent_response.agent_id
            request_log.processing_time_ms = agent_response.processing_time_ms
            request_log.completed_at = datetime.now(timezone.utc)

            # Update session with current agent (if not already set)
            from .session_manager import SessionManager

            session_manager = SessionManager(db)
            current_session = await session_manager.get_session(
                normalized_request.session_id
            )
            if current_session and not current_session.current_agent_id:
                # Convert agent UUID to agent name for session storage
                from .main import _get_available_agents

                available_agents = await _get_available_agents()
                agent_name = None
                for name, uuid in available_agents.items():
                    if uuid == agent_response.agent_id:
                        agent_name = name
                        break

                if agent_name:
                    await session_manager.update_session(
                        session_id=normalized_request.session_id,
                        agent_id=agent_name,
                    )
                    logger.info(
                        "Updated session with current agent",
                        session_id=normalized_request.session_id,
                        agent_name=agent_name,
                        agent_uuid=agent_response.agent_id,
                    )

            await db.commit()

            # Deliver response via integration dispatcher
            delivery_success = await self.strategy.deliver_response(agent_response)
            if not delivery_success:
                logger.warning("Failed to deliver response in background")

            logger.info(
                "Background request processing completed",
                request_id=normalized_request.request_id,
                session_id=normalized_request.session_id,
                user_id=normalized_request.user_id,
            )

        except Exception as e:
            logger.error(
                "Error in background request processing",
                request_id=normalized_request.request_id,
                error=str(e),
            )

    async def process_request_sync(
        self, request, db: AsyncSession, timeout: int = 120
    ) -> Dict[str, Any]:
        """Process a request synchronously and wait for response."""
        from datetime import datetime, timezone

        from .session_manager import SessionManager

        session_manager = SessionManager(db)
        normalizer = RequestNormalizer()

        # Find or create session
        session = await session_manager.find_or_create_session(
            user_id=request.user_id,
            integration_type=request.integration_type,
            channel_id=getattr(request, "channel_id", None),
            thread_id=getattr(request, "thread_id", None),
            integration_metadata=request.metadata,
        )

        # Normalize the request
        normalized_request = normalizer.normalize_request(
            request, session.session_id, session.current_agent_id
        )

        # Log the request
        request_log = RequestLog(
            request_id=normalized_request.request_id,
            session_id=session.session_id,
            request_type=request.request_type,
            request_content=request.content,
            normalized_request=normalized_request.model_dump(mode="json"),
            agent_id=normalized_request.target_agent_id,
        )

        db.add(request_log)
        await db.commit()

        await session_manager.increment_request_count(
            session.session_id, normalized_request.request_id
        )

        # Handle different strategies
        if isinstance(self.strategy, EventingStrategy):
            # Eventing mode: send event and wait for response
            success = await self.strategy.send_request(normalized_request)
            if not success:
                raise Exception("Failed to send request event")

            response_data = await self.strategy.wait_for_response(
                normalized_request.request_id, timeout, db
            )

            if not response_data:
                raise Exception("Timeout waiting for response")

        elif isinstance(self.strategy, DirectHttpStrategy):
            # Direct HTTP mode: process synchronously
            agent_client = get_agent_client()
            if not agent_client:
                raise Exception("Agent client not initialized")

            agent_response = await agent_client.process_request(normalized_request)
            if not agent_response:
                raise Exception("Agent service failed to process request")

            # Handle agent routing
            agent_response = await self._handle_agent_routing(
                agent_response, normalized_request, agent_client, db
            )

            # Update request log with response
            request_log.response_content = agent_response.content
            request_log.response_metadata = agent_response.metadata
            request_log.agent_id = agent_response.agent_id
            request_log.processing_time_ms = agent_response.processing_time_ms
            request_log.completed_at = datetime.now(timezone.utc)

            await db.commit()

            # For sync requests, return response directly; for async requests, deliver via integration dispatcher
            if normalized_request.request_type.upper() != "SYNC":
                # Deliver response for async requests (Slack, email, etc.)
                delivery_success = await self.strategy.deliver_response(agent_response)
                if not delivery_success:
                    logger.warning("Failed to deliver response")

            # Prepare response data (always returned for sync requests)
            response_data = {
                "content": agent_response.content,
                "agent_id": agent_response.agent_id,
                "metadata": agent_response.metadata,
                "processing_time_ms": agent_response.processing_time_ms,
                "requires_followup": agent_response.requires_followup,
                "followup_actions": agent_response.followup_actions,
            }

        else:
            raise Exception("Unknown communication strategy")

        logger.info(
            "Request processed synchronously",
            request_id=normalized_request.request_id,
            session_id=session.session_id,
            user_id=request.user_id,
        )

        return {
            "request_id": normalized_request.request_id,
            "session_id": session.session_id,
            "status": "completed",
            "response": response_data,
        }
