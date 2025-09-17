"""CloudEvent-driven Agent Service."""

import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
import structlog
from cloudevents.http import CloudEvent, to_structured
from fastapi import FastAPI, HTTPException, Request, status
from llama_stack_client import LlamaStackClient
from shared_db import AgentMapping, create_agent_mapping

# BaseModel no longer needed since NormalizedRequest is imported from shared_db
from shared_db.models import AgentResponse, NormalizedRequest

from . import __version__

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


class AgentConfig:
    """Configuration for agent service."""

    def __init__(self) -> None:
        self.llama_stack_url = os.getenv("LLAMA_STACK_URL", "http://llamastack:8321")
        self.broker_url = os.getenv("BROKER_URL")
        self.eventing_enabled = os.getenv("EVENTING_ENABLED", "true").lower() == "true"

        # If eventing is disabled, we don't need a broker URL
        if self.eventing_enabled and not self.broker_url:
            raise ValueError(
                "BROKER_URL environment variable is required when eventing is enabled. "
                "Set EVENTING_ENABLED=false to disable eventing or configure BROKER_URL."
            )

        self.default_agent_id = os.getenv("DEFAULT_AGENT_ID", "routing-agent")
        self.timeout = float(os.getenv("AGENT_TIMEOUT", "120"))


# NormalizedRequest is now imported from shared_db.models


class AgentService:
    """Service for handling agent interactions."""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.client: Optional[LlamaStackClient] = None
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.sessions: Dict[str, str] = {}  # session_id -> llama_stack_session_id
        self.agent_mapping: AgentMapping = create_agent_mapping(
            {}
        )  # Type-safe agent mapping

    async def initialize(self) -> None:
        """Initialize the agent service."""
        try:
            # Create HTTP client that forces HTTP without TLS
            import httpx

            http_client = httpx.Client(
                verify=False,  # Disable SSL verification
                timeout=30.0,
                follow_redirects=True,
            )

            # Initialize LlamaStackClient with explicit HTTP client
            self.client = LlamaStackClient(
                base_url=self.config.llama_stack_url, http_client=http_client
            )
            logger.info("Connected to Llama Stack", url=self.config.llama_stack_url)

            # Build initial agent name to ID mapping
            await self._build_agent_mapping()
        except Exception as e:
            logger.error("Failed to connect to Llama Stack", error=str(e))
            raise

    async def _build_agent_mapping(self) -> None:
        """Build mapping from agent names to agent IDs."""
        try:
            logger.info("Building agent name to ID mapping...")
            agents_response = self.client.agents.list()
            raw_mapping = {}

            logger.info(
                "Retrieved agents from LlamaStack", count=len(agents_response.data)
            )

            for agent in agents_response.data:
                # Handle both dict and object formats
                if isinstance(agent, dict):
                    agent_name = agent.get("agent_config", {}).get("name") or agent.get(
                        "name", "unknown"
                    )
                    agent_id = agent.get("agent_id", agent.get("id", "unknown"))
                else:
                    agent_name = (
                        getattr(agent.agent_config, "name", "unknown")
                        if hasattr(agent, "agent_config")
                        else getattr(agent, "name", "unknown")
                    )
                    agent_id = getattr(
                        agent, "agent_id", getattr(agent, "id", "unknown")
                    )

                raw_mapping[agent_name] = agent_id
                logger.info("Mapped agent", name=agent_name, id=agent_id)

            # Create type-safe mapping
            self.agent_mapping = create_agent_mapping(raw_mapping)

            logger.info(
                "Agent mapping completed",
                total_agents=len(self.agent_mapping.get_all_names()),
            )

        except Exception as e:
            logger.error(
                "Failed to build agent mapping",
                error=str(e),
                error_type=type(e).__name__,
            )
            self.agent_mapping = create_agent_mapping({})
            # Continue initialization even if mapping fails

    async def process_request(self, request: NormalizedRequest) -> AgentResponse:
        """Process a normalized request and return agent response."""
        start_time = datetime.now(timezone.utc)

        try:
            # Publish processing started event for user notification
            await self._publish_processing_event(request)

            # Determine which agent to use
            agent_id = await self._determine_agent(request)
            logger.info(
                "Agent determined for request",
                request_id=request.request_id,
                target_agent_id=request.target_agent_id,
                resolved_agent_id=agent_id,
            )

            # Get or create session
            llama_stack_session_id = await self._get_or_create_session(
                request.session_id, agent_id
            )

            # Send message to agent
            messages = [{"role": "user", "content": request.content}]

            # Get full agent configuration to ensure all settings are applied
            agent = self.client.agents.retrieve(agent_id)
            agent_config = agent.agent_config

            # Debug logging for agent configuration
            logger.info(
                "Agent configuration retrieved",
                agent_id=agent_id,
                agent_name=agent.name if hasattr(agent, "name") else "unknown",
                toolgroups=(
                    agent_config.toolgroups
                    if hasattr(agent_config, "toolgroups")
                    else None
                ),
                tool_choice=(
                    getattr(agent_config.tool_config, "tool_choice", None)
                    if hasattr(agent_config, "tool_config") and agent_config.tool_config
                    else None
                ),
            )

            # Use streaming agent turns (required by LlamaStack)
            turn_params = {
                "agent_id": agent_id,
                "session_id": llama_stack_session_id,
                "messages": messages,
                "stream": True,  # Enable streaming
            }

            # Pass only the supported turn.create parameters
            if agent_config.toolgroups:
                logger.info(
                    "Adding toolgroups to turn params",
                    agent_id=agent_id,
                    toolgroups=agent_config.toolgroups,
                )
                turn_params["toolgroups"] = agent_config.toolgroups
            else:
                logger.info(
                    "No toolgroups found for agent",
                    agent_id=agent_id,
                )

            response_stream = self.client.agents.turn.create(**turn_params)

            # Collect streaming response using the same pattern as test/chat.py
            content = ""
            chunk_count = 0
            tool_calls_made = []
            for chunk in response_stream:
                chunk_count += 1
                logger.info(
                    "Processing stream chunk",
                    chunk_type=type(chunk).__name__,
                    chunk_count=chunk_count,
                    chunk_attrs=dir(chunk),
                )

                if hasattr(chunk, "event"):
                    try:
                        # Check if the event has the expected structure
                        if hasattr(chunk.event, "payload"):
                            # Old structure: chunk.event.payload
                            event_payload = chunk.event.payload
                        elif hasattr(chunk.event, "event_type"):
                            # New structure: chunk.event directly
                            event_payload = chunk.event
                        else:
                            logger.warning(
                                "Unknown event structure",
                                event_attrs=dir(chunk.event),
                                chunk_count=chunk_count,
                            )
                            continue

                        # Track tool calls for validation
                        if (
                            hasattr(event_payload, "event_type")
                            and event_payload.event_type == "tool_call"
                        ):
                            tool_name = getattr(event_payload, "tool_name", "unknown")
                            tool_calls_made.append(tool_name)
                            logger.info(f"Tool called: {tool_name}")

                        if (
                            hasattr(event_payload, "event_type")
                            and event_payload.event_type == "turn_complete"
                        ):
                            if hasattr(event_payload, "turn") and hasattr(
                                event_payload.turn, "output_message"
                            ):
                                if (
                                    event_payload.turn.output_message.stop_reason
                                    == "end_of_turn"
                                ):
                                    content += event_payload.turn.output_message.content
                                    logger.info(
                                        "Extracted content from turn_complete",
                                        content_length=len(
                                            event_payload.turn.output_message.content
                                        ),
                                        chunk_count=chunk_count,
                                    )
                                else:
                                    # Handle other stop reasons
                                    stop_reason = (
                                        event_payload.turn.output_message.stop_reason
                                    )
                                    content += f"[Agent stopped: {stop_reason}]"
                                    logger.info(
                                        "Agent stopped with reason",
                                        stop_reason=stop_reason,
                                        chunk_count=chunk_count,
                                    )
                        else:
                            # Log other event types for debugging
                            if hasattr(event_payload, "event_type"):
                                event_type = event_payload.event_type
                                logger.info(
                                    "Other event type",
                                    event_type=event_type,
                                    chunk_count=chunk_count,
                                )
                    except AttributeError as e:
                        # Log structure for debugging if attributes are missing
                        logger.warning(
                            "Chunk structure issue",
                            error=str(e),
                            chunk_attrs=dir(chunk),
                            event_attrs=(
                                dir(chunk.event)
                                if hasattr(chunk, "event")
                                else "no event"
                            ),
                            chunk_count=chunk_count,
                        )
                else:
                    # Log unexpected chunk structure for debugging
                    logger.warning(
                        "Unexpected chunk structure",
                        chunk_attrs=dir(chunk),
                        chunk_type=type(chunk).__name__,
                        chunk_count=chunk_count,
                    )

            # If no content collected, provide error message instead of stream object
            if not content:
                content = f"No response content received from agent (processed {chunk_count} chunks). This may indicate the agent didn't complete its turn or the stream format has changed."
                logger.warning(
                    "No content collected from stream",
                    chunk_count=chunk_count,
                    message="Check if agent completed its turn successfully",
                )

            # Log tool calls for monitoring (Strategy 3 only)
            if tool_calls_made:
                logger.info(
                    "Tools called during agent processing",
                    agent_id=agent_id,
                    tool_calls=tool_calls_made,
                )

            # Calculate processing time
            processing_time = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )

            return AgentResponse(
                request_id=request.request_id,
                session_id=request.session_id,
                user_id=request.user_id,  # Include user_id from the request
                agent_id=agent_id,
                content=content,
                processing_time_ms=processing_time,
                created_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            logger.error(
                "Failed to process request", error=str(e), request_id=request.request_id
            )

            # Return error response
            return AgentResponse(
                request_id=request.request_id,
                session_id=request.session_id,
                user_id=request.user_id,  # Include user_id from the request
                agent_id=None,
                content=f"I apologize, but I encountered an error processing your request: {str(e)}",
                response_type="error",
                created_at=datetime.now(timezone.utc),
            )

    async def _determine_agent(self, request: NormalizedRequest) -> str:
        """Determine which agent should handle the request."""
        if request.target_agent_id:
            # Always refresh agent mapping to ensure we have latest agents
            await self._build_agent_mapping()

            # Use simple conversion
            agent_uuid = self.agent_mapping.convert_to_uuid(request.target_agent_id)
            if agent_uuid:
                logger.info(
                    "Resolved target agent name to ID",
                    agent_name=request.target_agent_id,
                    agent_id=agent_uuid,
                )
                return agent_uuid
            else:
                available_agents = self.agent_mapping.get_all_names()
                logger.error(
                    "Target agent not found in mapping",
                    target_agent_id=request.target_agent_id,
                    available_agents=available_agents,
                )
                raise ValueError(
                    f"Target agent '{request.target_agent_id}' not found in llama-stack. "
                    f"Available agents: {available_agents}. "
                    f"Please check agent configuration."
                )

        # Use routing agent for all requests unless a specific target agent is provided
        agent_name = self.config.default_agent_id

        # Refresh agent mapping if we haven't done it already for this request
        if len(self.agent_mapping.get_all_names()) == 0:
            logger.debug("Refreshing agent mapping for request", agent_name=agent_name)
            await self._build_agent_mapping()

        # Resolve agent name to ID using simple conversion
        logger.debug(
            "Resolving agent name to ID",
            agent_name=agent_name,
            available_agents=self.agent_mapping.get_all_names(),
        )

        agent_uuid = self.agent_mapping.convert_to_uuid(agent_name)
        if agent_uuid:
            logger.info(
                "Resolved agent name to ID", agent_name=agent_name, agent_id=agent_uuid
            )
            return agent_uuid
        else:
            available_agents = self.agent_mapping.get_all_names()
            logger.error(
                "Agent name not found in mapping",
                agent_name=agent_name,
                available_agents=available_agents,
            )
            raise ValueError(
                f"Agent '{agent_name}' not found in llama-stack. "
                f"Available agents: {available_agents}. "
                f"Please check agent configuration or create the agent in llama-stack."
            )

    async def _get_or_create_session(self, session_id: str, agent_id: str) -> str:
        """Get or create a Llama Stack session."""
        # Use agent-specific session key to avoid conflicts between agents
        session_key = f"{session_id}_{agent_id}"
        if session_key in self.sessions:
            return self.sessions[session_key]

        try:
            # Create new session
            session_response = self.client.agents.session.create(
                agent_id=agent_id,
                session_name=f"session-{session_id}",
            )

            llama_stack_session_id = session_response.session_id
            self.sessions[session_key] = llama_stack_session_id

            logger.info(
                "Created new agent session",
                session_id=session_id,
                llama_stack_session_id=llama_stack_session_id,
                agent_id=agent_id,
            )

            return llama_stack_session_id

        except Exception as e:
            logger.error("Failed to create agent session", error=str(e))
            raise

    async def publish_response(self, response: AgentResponse) -> bool:
        """Publish agent response as CloudEvent."""
        try:
            event_data = {
                "request_id": response.request_id,
                "session_id": response.session_id,
                "user_id": response.user_id,  # Include user_id for Integration Dispatcher
                "agent_id": response.agent_id,
                "content": response.content,
                "response_type": response.response_type,
                "metadata": response.metadata,
                "processing_time_ms": response.processing_time_ms,
                "requires_followup": response.requires_followup,
                "followup_actions": response.followup_actions,
                "created_at": response.created_at.isoformat(),
            }

            event = CloudEvent(
                {
                    "specversion": "1.0",
                    "type": "com.self-service-agent.agent.response-ready",
                    "source": "agent-service",
                    "id": str(uuid.uuid4()),
                    "time": datetime.now(timezone.utc).isoformat(),
                    "subject": f"session/{response.session_id}",
                    "datacontenttype": "application/json",
                },
                event_data,
            )

            headers, body = to_structured(event)

            response_http = await self.http_client.post(
                self.config.broker_url,
                headers=headers,
                content=body,
            )

            response_http.raise_for_status()
            return True

        except Exception as e:
            logger.error("Failed to publish response event", error=str(e))
            return False

    async def _publish_processing_event(self, request: NormalizedRequest) -> bool:
        """Publish processing started event for user notification."""
        try:
            event_data = {
                "request_id": request.request_id,
                "session_id": request.session_id,
                "user_id": request.user_id,
                "integration_type": request.integration_type,
                "request_type": request.request_type,
                "content_preview": (
                    request.content[:100] + "..."
                    if len(request.content) > 100
                    else request.content
                ),
                "target_agent_id": request.target_agent_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }

            event = CloudEvent(
                {
                    "specversion": "1.0",
                    "type": "com.self-service-agent.request.processing",
                    "source": "agent-service",
                    "id": str(uuid.uuid4()),
                    "time": datetime.now(timezone.utc).isoformat(),
                    "subject": f"session/{request.session_id}",
                    "datacontenttype": "application/json",
                },
                event_data,
            )

            headers, body = to_structured(event)

            response = await self.http_client.post(
                self.config.broker_url,
                headers=headers,
                content=body,
            )

            response.raise_for_status()

            logger.info(
                "Processing event published",
                request_id=request.request_id,
                session_id=request.session_id,
                user_id=request.user_id,
            )

            return True

        except Exception as e:
            logger.error("Failed to publish processing event", error=str(e))
            return False

    async def _log_agent_config(self, agent_id: str) -> None:
        """Log agent configuration for debugging."""
        try:
            # Get agent details from llama-stack
            response = self.client.get("v1/agents", cast_to=httpx.Response)
            json_string = response.content.decode("utf-8")
            data = json.loads(json_string)

            # Find the agent with matching ID
            for agent in data.get("data", []):
                if isinstance(agent, dict) and agent.get("agent_id") == agent_id:
                    agent_config = agent.get("agent_config", {})
                    logger.info(
                        "Agent configuration in llama-stack",
                        agent_id=agent_id,
                        agent_name=agent.get("name"),
                        toolgroups=agent_config.get("toolgroups"),
                        tool_choice=agent_config.get("tool_config", {}).get(
                            "tool_choice"
                        ),
                        max_infer_iters=agent_config.get("max_infer_iters"),
                        sampling_params=agent_config.get("sampling_params"),
                    )
                    return

            logger.warning(
                "Agent configuration not found in llama-stack", agent_id=agent_id
            )
        except Exception as e:
            logger.error(
                "Failed to get agent configuration", agent_id=agent_id, error=str(e)
            )

    async def close(self) -> None:
        """Close HTTP client."""
        await self.http_client.aclose()


# Global agent service instance
_agent_service: Optional[AgentService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global _agent_service

    # Startup
    logger.info("Starting Agent Service", version=__version__)

    config = AgentConfig()
    _agent_service = AgentService(config)

    try:
        await _agent_service.initialize()
        logger.info("Agent Service initialized")
    except Exception as e:
        logger.error("Failed to initialize Agent Service", error=str(e))
        raise

    yield

    # Shutdown
    logger.info("Shutting down Agent Service")
    if _agent_service:
        await _agent_service.close()


# Create FastAPI application
app = FastAPI(
    title="Self-Service Agent Service",
    description="CloudEvent-driven Agent Service",
    version=__version__,
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": __version__,
        "service": "agent-service",
    }


@app.get("/agents")
async def list_agents() -> Dict[str, Any]:
    """List available agents endpoint."""
    if not _agent_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent service not initialized",
        )

    try:
        # Refresh agent mapping to get latest agents
        await _agent_service._build_agent_mapping()

        return {
            "agents": _agent_service.agent_mapping.to_dict(),
            "count": len(_agent_service.agent_mapping.get_all_names()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error("Failed to get agent list", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve agent list",
        )


@app.post("/process")
async def handle_direct_request(request: Request) -> Dict[str, Any]:
    """Handle direct HTTP requests (for non-eventing mode)."""
    if not _agent_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent service not initialized",
        )

    try:
        body = await request.body()
        request_data = json.loads(body)

        logger.info(
            "Direct request received",
            request_id=request_data.get("request_id"),
            session_id=request_data.get("session_id"),
            user_id=request_data.get("user_id"),
        )

        # Create a mock CloudEvent structure for processing
        mock_headers = {
            "ce-type": "com.self-service-agent.request.created",
            "ce-id": request_data.get("request_id", "direct-request"),
            "ce-source": "request-manager",
        }

        # Convert request data to CloudEvent format
        mock_body = json.dumps(request_data).encode()

        # Process using existing CloudEvent handler
        result = await _handle_request_event(mock_headers, mock_body, _agent_service)

        return result

    except json.JSONDecodeError:
        logger.error("Invalid JSON in direct request")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error("Error handling direct request", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/")
async def handle_cloudevent(request: Request) -> Dict[str, Any]:
    """Handle incoming CloudEvents."""
    if not _agent_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent service not initialized",
        )

    try:
        # Parse CloudEvent
        headers = dict(request.headers)
        body = await request.body()

        # Handle request events
        if headers.get("ce-type") == "com.self-service-agent.request.created":
            return await _handle_request_event(headers, body, _agent_service)

        logger.warning("Unhandled CloudEvent type", event_type=headers.get("ce-type"))
        return {"status": "ignored", "reason": "unhandled event type"}

    except Exception as e:
        logger.error("Failed to handle CloudEvent", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to process CloudEvent",
        )


async def _handle_request_event(
    headers: Dict[str, str], body: bytes, agent_service: AgentService
) -> Dict[str, Any]:
    """Handle request CloudEvent."""
    try:
        event_data = json.loads(body)

        # Parse normalized request with proper error handling
        try:
            request = NormalizedRequest(
                request_id=event_data.get("request_id", "unknown"),
                session_id=event_data.get("session_id", "unknown"),
                user_id=event_data.get("user_id", "unknown"),
                integration_type=event_data.get("integration_type", "cli"),
                request_type=event_data.get("request_type", "general"),
                content=event_data.get("content", ""),
                integration_context=event_data.get("integration_context", {}),
                user_context=event_data.get("user_context", {}),
                target_agent_id=event_data.get("target_agent_id"),
                requires_routing=event_data.get("requires_routing", True),
                created_at=datetime.fromisoformat(
                    event_data.get("created_at", datetime.now().isoformat())
                ),
            )
        except Exception as e:
            logger.error(
                "Failed to parse normalized request",
                error=str(e),
                event_data=event_data,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request data: {str(e)}",
            )

        # Process the request
        response = await agent_service.process_request(request)

        # Publish response event
        success = await agent_service.publish_response(response)

        logger.info(
            "Request processed",
            request_id=request.request_id,
            session_id=request.session_id,
            agent_id=response.agent_id,
            response_published=success,
        )

        return {
            "request_id": response.request_id,
            "session_id": response.session_id,
            "user_id": response.user_id,
            "agent_id": response.agent_id,
            "content": response.content,
            "response_type": response.response_type,
            "metadata": response.metadata,
            "processing_time_ms": response.processing_time_ms,
            "requires_followup": response.requires_followup,
            "followup_actions": response.followup_actions,
            "created_at": response.created_at.isoformat(),
        }

    except Exception as e:
        logger.error("Failed to handle request event", error=str(e))
        raise


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")

    uvicorn.run(
        "agent_service.main:app",
        host=host,
        port=port,
        reload=os.getenv("RELOAD", "false").lower() == "true",
        log_level="info",
    )
