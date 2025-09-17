"""Integration tests to ensure eventing and direct HTTP modes work identically."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from request_manager.communication_strategy import (
    DirectHttpStrategy,
    EventingStrategy,
    UnifiedRequestProcessor,
    get_communication_strategy,
)
from request_manager.response_handler import UnifiedResponseHandler
from request_manager.schemas import (
    AgentResponse,
    BaseRequest,
    IntegrationType,
    NormalizedRequest,
    RequestType,
)


class TestCommunicationModeConsistency:
    """Test that both communication modes produce identical results."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return AsyncMock()

    @pytest.fixture
    def sample_request(self):
        """Sample request for testing."""
        return BaseRequest(
            user_id="test-user",
            content="Hello, please introduce yourself",
            integration_type=IntegrationType.CLI,
            request_type=RequestType.GENERAL,
        )

    @pytest.fixture
    def sample_normalized_request(self):
        """Sample normalized request for testing."""
        return NormalizedRequest(
            request_id="test-request-123",
            session_id="test-session-456",
            user_id="test-user",
            integration_type=IntegrationType.CLI,
            request_type=RequestType.GENERAL,
            content="Hello, please introduce yourself",
            target_agent_id="routing-agent",
            requires_routing=True,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def sample_agent_response(self):
        """Sample agent response for testing."""
        return AgentResponse(
            request_id="test-request-123",
            session_id="test-session-456",
            user_id="test-user",
            agent_id="routing-agent",
            content="Hello! I'm your AI assistant. How can I help you today?",
            response_type="message",
            metadata={"confidence": 0.95},
            processing_time_ms=1500,
            requires_followup=False,
            followup_actions=[],
            created_at=datetime.now(timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_eventing_strategy_request_flow(
        self, sample_normalized_request, mock_db
    ):
        """Test that eventing strategy processes requests correctly."""
        strategy = EventingStrategy()

        with patch.object(
            strategy.event_publisher, "publish_request_event", return_value=True
        ):
            success = await strategy.send_request(sample_normalized_request)
            assert success is True

    @pytest.mark.asyncio
    async def test_direct_http_strategy_request_flow(
        self, sample_normalized_request, mock_db
    ):
        """Test that direct HTTP strategy processes requests correctly."""
        strategy = DirectHttpStrategy()

        # Mock the agent client
        strategy.agent_client = AsyncMock()
        strategy.agent_client.process_request.return_value = AsyncMock()

        success = await strategy.send_request(sample_normalized_request)
        assert success is True

    @pytest.mark.asyncio
    async def test_unified_processor_async_mode(self, sample_request, mock_db):
        """Test unified processor in async mode (eventing)."""
        strategy = EventingStrategy()
        processor = UnifiedRequestProcessor(strategy)

        with patch(
            "request_manager.communication_strategy.SessionManager"
        ) as mock_session_manager, patch(
            "request_manager.communication_strategy.RequestNormalizer"
        ) as mock_normalizer, patch.object(
            strategy, "send_request", return_value=True
        ):

            # Mock session creation
            mock_session = MagicMock()
            mock_session.session_id = "test-session-456"
            mock_session.current_agent_id = "routing-agent"
            mock_session_manager.return_value.find_or_create_session.return_value = (
                mock_session
            )

            # Mock request normalization
            mock_normalized_request = MagicMock()
            mock_normalized_request.request_id = "test-request-123"
            mock_normalized_request.session_id = "test-session-456"
            mock_normalizer.return_value.normalize_request.return_value = (
                mock_normalized_request
            )

            result = await processor.process_request_async(sample_request, mock_db)

            assert result["status"] == "accepted"
            assert result["request_id"] == "test-request-123"
            assert result["session_id"] == "test-session-456"

    @pytest.mark.asyncio
    async def test_unified_processor_sync_mode(self, sample_request, mock_db):
        """Test unified processor in sync mode (direct HTTP)."""
        strategy = DirectHttpStrategy()
        processor = UnifiedRequestProcessor(strategy)

        with patch(
            "request_manager.communication_strategy.SessionManager"
        ) as mock_session_manager, patch(
            "request_manager.communication_strategy.RequestNormalizer"
        ) as mock_normalizer, patch(
            "request_manager.communication_strategy.get_agent_client"
        ) as mock_get_agent_client:

            # Mock session creation
            mock_session = MagicMock()
            mock_session.session_id = "test-session-456"
            mock_session.current_agent_id = "routing-agent"
            mock_session_manager.return_value.find_or_create_session.return_value = (
                mock_session
            )

            # Mock request normalization
            mock_normalized_request = MagicMock()
            mock_normalized_request.request_id = "test-request-123"
            mock_normalized_request.session_id = "test-session-456"
            mock_normalizer.return_value.normalize_request.return_value = (
                mock_normalized_request
            )

            # Mock agent client
            mock_agent_client = AsyncMock()
            mock_agent_response = MagicMock()
            mock_agent_response.content = "Hello! I'm your AI assistant."
            mock_agent_response.agent_id = "routing-agent"
            mock_agent_response.metadata = {"confidence": 0.95}
            mock_agent_response.processing_time_ms = 1500
            mock_agent_response.requires_followup = False
            mock_agent_response.followup_actions = []
            mock_agent_client.process_request.return_value = mock_agent_response
            mock_get_agent_client.return_value = mock_agent_client

            # Mock integration client
            strategy.integration_client = AsyncMock()
            strategy.integration_client.deliver_response.return_value = True

            result = await processor.process_request_sync(sample_request, mock_db)

            assert result["status"] == "completed"
            assert result["request_id"] == "test-request-123"
            assert result["session_id"] == "test-session-456"
            assert "response" in result

    @pytest.mark.asyncio
    async def test_response_handler_consistency(self, sample_agent_response, mock_db):
        """Test that response handler works consistently for both modes."""
        handler = UnifiedResponseHandler(mock_db)

        with patch.object(
            handler, "_check_existing_response", return_value=None
        ), patch.object(handler, "_update_request_log"), patch.object(
            handler, "_update_session_context"
        ), patch.object(
            handler, "_detect_and_validate_agent_routing", return_value=None
        ):

            result = await handler.process_agent_response(
                request_id=sample_agent_response.request_id,
                session_id=sample_agent_response.session_id,
                agent_id=sample_agent_response.agent_id,
                content=sample_agent_response.content,
                metadata=sample_agent_response.metadata,
                processing_time_ms=sample_agent_response.processing_time_ms,
                requires_followup=sample_agent_response.requires_followup,
                followup_actions=sample_agent_response.followup_actions,
            )

            assert result["status"] == "processed"
            assert result["request_id"] == sample_agent_response.request_id
            assert result["session_id"] == sample_agent_response.session_id

    def test_communication_strategy_factory(self):
        """Test that the communication strategy factory returns correct strategies."""
        with patch.dict("os.environ", {"EVENTING_ENABLED": "true"}):
            strategy = get_communication_strategy()
            assert isinstance(strategy, EventingStrategy)

        with patch.dict("os.environ", {"EVENTING_ENABLED": "false"}):
            strategy = get_communication_strategy()
            assert isinstance(strategy, DirectHttpStrategy)

    @pytest.mark.asyncio
    async def test_identical_response_processing(self, sample_agent_response, mock_db):
        """Test that both modes produce identical response processing results."""
        # Test eventing mode
        eventing_handler = UnifiedResponseHandler(mock_db)

        with patch.object(
            eventing_handler, "_check_existing_response", return_value=None
        ), patch.object(eventing_handler, "_update_request_log"), patch.object(
            eventing_handler, "_update_session_context"
        ), patch.object(
            eventing_handler, "_detect_and_validate_agent_routing", return_value=None
        ):

            eventing_result = await eventing_handler.process_agent_response(
                request_id=sample_agent_response.request_id,
                session_id=sample_agent_response.session_id,
                agent_id=sample_agent_response.agent_id,
                content=sample_agent_response.content,
                metadata=sample_agent_response.metadata,
                processing_time_ms=sample_agent_response.processing_time_ms,
                requires_followup=sample_agent_response.requires_followup,
                followup_actions=sample_agent_response.followup_actions,
            )

        # Test direct HTTP mode (should produce identical results)
        direct_handler = UnifiedResponseHandler(mock_db)

        with patch.object(
            direct_handler, "_check_existing_response", return_value=None
        ), patch.object(direct_handler, "_update_request_log"), patch.object(
            direct_handler, "_update_session_context"
        ), patch.object(
            direct_handler, "_detect_and_validate_agent_routing", return_value=None
        ):

            direct_result = await direct_handler.process_agent_response(
                request_id=sample_agent_response.request_id,
                session_id=sample_agent_response.session_id,
                agent_id=sample_agent_response.agent_id,
                content=sample_agent_response.content,
                metadata=sample_agent_response.metadata,
                processing_time_ms=sample_agent_response.processing_time_ms,
                requires_followup=sample_agent_response.requires_followup,
                followup_actions=sample_agent_response.followup_actions,
            )

        # Both modes should produce identical results
        assert eventing_result == direct_result
        assert eventing_result["status"] == "processed"
        assert direct_result["status"] == "processed"


class TestModeSwitching:
    """Test switching between communication modes."""

    def test_environment_variable_switching(self):
        """Test that switching EVENTING_ENABLED changes the strategy."""
        with patch.dict("os.environ", {"EVENTING_ENABLED": "true"}):
            strategy1 = get_communication_strategy()
            assert isinstance(strategy1, EventingStrategy)

        with patch.dict("os.environ", {"EVENTING_ENABLED": "false"}):
            strategy2 = get_communication_strategy()
            assert isinstance(strategy2, DirectHttpStrategy)

        # Strategies should be different instances
        assert strategy1 is not strategy2

    @pytest.mark.asyncio
    async def test_graceful_mode_switching(self, sample_normalized_request, mock_db):
        """Test that switching modes doesn't break existing functionality."""
        # Test eventing mode
        with patch.dict("os.environ", {"EVENTING_ENABLED": "true"}):
            eventing_strategy = get_communication_strategy()
            with patch.object(eventing_strategy, "send_request", return_value=True):
                success = await eventing_strategy.send_request(
                    sample_normalized_request
                )
                assert success is True

        # Test direct HTTP mode
        with patch.dict("os.environ", {"EVENTING_ENABLED": "false"}):
            direct_strategy = get_communication_strategy()
            with patch.object(direct_strategy, "send_request", return_value=True):
                success = await direct_strategy.send_request(sample_normalized_request)
                assert success is True
