"""Tests for request normalizer."""

from request_manager.normalizer import RequestNormalizer
from request_manager.schemas import CLIRequest, SlackRequest, ToolRequest, WebRequest
from shared_models.models import IntegrationType


class TestRequestNormalizer:
    """Test cases for RequestNormalizer."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.normalizer = RequestNormalizer()
        self.session_id = "test-session-123"

    def test_normalize_slack_request(self) -> None:
        """Test Slack request normalization."""
        slack_request = SlackRequest(
            user_id="user123",
            content="Hello, I need help with my laptop",
            channel_id="C123456789",
            thread_id="1234567890.123456",
            slack_user_id="U123456789",
            slack_team_id="T123456789",
        )

        normalized = self.normalizer.normalize_request(slack_request, self.session_id)

        assert normalized.request_id is not None
        assert normalized.session_id == self.session_id
        assert normalized.user_id == "user123"
        assert normalized.integration_type == IntegrationType.SLACK
        assert normalized.content == "Hello, I need help with my laptop"
        assert normalized.integration_context["platform"] == "slack"
        assert normalized.integration_context["channel_id"] == "C123456789"
        assert normalized.integration_context["slack_user_id"] == "U123456789"
        assert normalized.requires_routing is True

    def test_normalize_slack_request_dm(self) -> None:
        """Test Slack request normalization for DM requests (no channel_id)."""
        slack_request = SlackRequest(
            user_id="user123",
            content="Hello, I need help with my laptop",
            channel_id=None,  # DM request - no channel
            thread_id=None,
            slack_user_id="U123456789",
            slack_team_id="T123456789",
        )

        normalized = self.normalizer.normalize_request(slack_request, self.session_id)

        assert normalized.request_id is not None
        assert normalized.session_id == self.session_id
        assert normalized.user_id == "user123"
        assert normalized.integration_type == IntegrationType.SLACK
        assert normalized.content == "Hello, I need help with my laptop"
        assert normalized.integration_context["platform"] == "slack"
        assert normalized.integration_context["channel_id"] is None
        assert normalized.integration_context["slack_user_id"] == "U123456789"
        assert normalized.requires_routing is True

    def test_normalize_web_request(self) -> None:
        """Test web request normalization."""
        web_request = WebRequest(
            user_id="webuser123",
            content="I want to refresh my laptop",
            session_token="token123",
            client_ip="192.168.1.1",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        )

        normalized = self.normalizer.normalize_request(web_request, self.session_id)

        assert normalized.integration_type == IntegrationType.WEB
        assert normalized.integration_context["platform"] == "web"
        assert normalized.integration_context["client_ip"] == "192.168.1.1"
        assert normalized.user_context["browser"] == "chrome"
        assert normalized.user_context["os"] == "windows"
        assert normalized.user_context["is_mobile"] is False

    def test_normalize_cli_request(self) -> None:
        """Test CLI request normalization."""
        cli_request = CLIRequest(
            user_id="cliuser123",
            content="help me with laptop refresh",
            cli_session_id="cli-session-456",
            command_context={"command": "agent", "args": ["help"]},
        )

        normalized = self.normalizer.normalize_request(cli_request, self.session_id)

        assert normalized.integration_type == IntegrationType.CLI
        assert normalized.integration_context["platform"] == "cli"
        assert normalized.integration_context["cli_session_id"] == "cli-session-456"
        assert normalized.user_context["command_context"]["command"] == "agent"

    def test_normalize_tool_request(self) -> None:
        """Test tool request normalization."""
        tool_request = ToolRequest(
            user_id="tooluser123",
            content="User laptop needs refresh - system notification",
            tool_id="snow-integration",
            tool_instance_id="instance-789",
            trigger_event="laptop.refresh.required",
            tool_context={"ticket_id": "INC123456", "priority": "high"},
        )

        normalized = self.normalizer.normalize_request(tool_request, self.session_id)

        assert normalized.integration_type == IntegrationType.TOOL
        assert normalized.integration_context["platform"] == "tool"
        assert normalized.integration_context["tool_id"] == "snow-integration"
        assert (
            normalized.target_agent_id == "laptop-refresh-agent"
        )  # Should map from tool
        assert normalized.requires_routing is False  # Tool specifies target agent
        assert normalized.user_context["automated_request"] is True

    def test_user_agent_parsing(self) -> None:
        """Test user agent parsing."""
        test_cases = [
            (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                {"browser": "chrome", "os": "windows", "is_mobile": False},
            ),
            (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
                {"browser": "safari", "os": "macos", "is_mobile": False},
            ),
            (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
                {"browser": "safari", "os": "ios", "is_mobile": True},
            ),
        ]

        for user_agent, expected in test_cases:
            result = self.normalizer._parse_user_agent(user_agent)
            for key, value in expected.items():
                assert result[key] == value

    def test_tool_agent_mapping(self) -> None:
        """Test tool to agent mapping."""
        mappings = [
            ("snow-integration", "laptop-refresh-agent"),
            ("email-service", "email-change-agent"),
            ("hr-system", "routing-agent"),
            ("unknown-tool", None),
        ]

        for tool_id, expected_agent in mappings:
            tool_request = ToolRequest(
                user_id="user123",
                content="test content",
                tool_id=tool_id,
                tool_instance_id="test-instance",
                trigger_event="test.event",
            )

            result = self.normalizer._extract_target_agent_from_tool(tool_request)
            assert result == expected_agent
