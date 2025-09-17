"""Direct HTTP client for services when eventing is disabled."""

from datetime import datetime
from typing import Optional

import httpx
import structlog
from shared_db import get_enum_value
from shared_db.models import AgentResponse

from .schemas import NormalizedRequest

logger = structlog.get_logger()


class DirectAgentClient:
    """Direct HTTP client for agent service when eventing is disabled."""

    def __init__(self, agent_service_url: str, timeout: float = 120.0):
        self.agent_service_url = agent_service_url
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def process_request(
        self, normalized_request: NormalizedRequest
    ) -> Optional[AgentResponse]:
        """Process a request directly with the agent service."""
        try:
            logger.info(
                "Processing request directly with agent service",
                request_id=normalized_request.request_id,
                session_id=normalized_request.session_id,
                agent_service_url=self.agent_service_url,
            )

            # Prepare the request payload
            request_payload = {
                "request_id": normalized_request.request_id,
                "session_id": normalized_request.session_id,
                "user_id": normalized_request.user_id,
                "integration_type": get_enum_value(normalized_request.integration_type),
                "request_type": normalized_request.request_type,
                "content": normalized_request.content,
                "integration_context": normalized_request.integration_context,
                "user_context": normalized_request.user_context,
                "target_agent_id": normalized_request.target_agent_id,
                "requires_routing": normalized_request.requires_routing,
                "created_at": normalized_request.created_at.isoformat(),
            }

            # Send request to agent service
            response = await self.client.post(
                f"{self.agent_service_url}/process",
                json=request_payload,
                headers={"Content-Type": "application/json"},
            )

            response.raise_for_status()
            response_data = response.json()

            # Convert response to AgentResponse
            agent_response = AgentResponse(
                request_id=response_data["request_id"],
                session_id=response_data["session_id"],
                user_id=response_data["user_id"],
                agent_id=response_data.get("agent_id"),
                content=response_data["content"],
                response_type=response_data.get("response_type", "message"),
                metadata=response_data.get("metadata", {}),
                processing_time_ms=response_data.get("processing_time_ms"),
                requires_followup=response_data.get("requires_followup", False),
                followup_actions=response_data.get("followup_actions", []),
                created_at=datetime.fromisoformat(
                    response_data["created_at"].replace("Z", "+00:00")
                ),
            )

            logger.info(
                "Request processed successfully by agent service",
                request_id=normalized_request.request_id,
                session_id=normalized_request.session_id,
                processing_time_ms=agent_response.processing_time_ms,
            )

            return agent_response

        except httpx.HTTPStatusError as e:
            logger.error(
                "Agent service returned error",
                request_id=normalized_request.request_id,
                status_code=e.response.status_code,
                response_text=e.response.text,
            )
            return None

        except httpx.TimeoutException:
            logger.error(
                "Timeout waiting for agent service response",
                request_id=normalized_request.request_id,
                timeout=self.timeout,
            )
            return None

        except Exception as e:
            logger.error(
                "Failed to process request with agent service",
                request_id=normalized_request.request_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


class DirectIntegrationClient:
    """Direct HTTP client for integration dispatcher when eventing is disabled."""

    def __init__(self, integration_dispatcher_url: str, timeout: float = 30.0):
        self.integration_dispatcher_url = integration_dispatcher_url
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def deliver_response(self, agent_response: AgentResponse) -> bool:
        """Deliver a response directly to the integration dispatcher."""
        try:
            logger.info(
                "Delivering response directly to integration dispatcher",
                request_id=agent_response.request_id,
                session_id=agent_response.session_id,
                integration_dispatcher_url=self.integration_dispatcher_url,
            )

            # Create delivery request using the proper schema
            from shared_db.models import DeliveryRequest

            delivery_request = DeliveryRequest(
                request_id=agent_response.request_id,
                session_id=agent_response.session_id,
                user_id=agent_response.user_id,
                agent_id=agent_response.agent_id,
                subject=f"Response from {agent_response.agent_id or 'agent'}",
                content=agent_response.content,
                template_variables=agent_response.metadata,
            )

            # Convert to dict for JSON serialization
            delivery_payload = delivery_request.model_dump()

            # Send delivery request to integration dispatcher
            response = await self.client.post(
                f"{self.integration_dispatcher_url}/deliver",
                json=delivery_payload,
                headers={"Content-Type": "application/json"},
            )

            response.raise_for_status()

            logger.info(
                "Response delivered successfully to integration dispatcher",
                request_id=agent_response.request_id,
                session_id=agent_response.session_id,
            )

            return True

        except httpx.HTTPStatusError as e:
            logger.error(
                "Integration dispatcher returned error",
                request_id=agent_response.request_id,
                status_code=e.response.status_code,
                response_text=e.response.text,
            )
            return False

        except httpx.TimeoutException:
            logger.error(
                "Timeout waiting for integration dispatcher response",
                request_id=agent_response.request_id,
                timeout=self.timeout,
            )
            return False

        except Exception as e:
            logger.error(
                "Failed to deliver response to integration dispatcher",
                request_id=agent_response.request_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


# Global client instances
_agent_client: Optional[DirectAgentClient] = None
_integration_client: Optional[DirectIntegrationClient] = None


def get_agent_client() -> Optional[DirectAgentClient]:
    """Get the global agent client instance."""
    return _agent_client


def get_integration_client() -> Optional[DirectIntegrationClient]:
    """Get the global integration client instance."""
    return _integration_client


def initialize_direct_clients(
    agent_service_url: str,
    integration_dispatcher_url: str,
    agent_timeout: float = 120.0,
    integration_timeout: float = 30.0,
):
    """Initialize the direct client instances."""
    global _agent_client, _integration_client

    _agent_client = DirectAgentClient(agent_service_url, agent_timeout)
    _integration_client = DirectIntegrationClient(
        integration_dispatcher_url, integration_timeout
    )

    logger.info(
        "Initialized direct clients",
        agent_service_url=agent_service_url,
        integration_dispatcher_url=integration_dispatcher_url,
    )


async def cleanup_direct_clients():
    """Clean up the direct client instances."""
    global _agent_client, _integration_client

    if _agent_client:
        await _agent_client.close()
        _agent_client = None

    if _integration_client:
        await _integration_client.close()
        _integration_client = None

    logger.info("Cleaned up direct clients")
