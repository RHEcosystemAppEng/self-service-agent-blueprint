#!/usr/bin/env python3
"""
Demo script showing how to interact with the Request Management Layer.

This script demonstrates:
1. Creating sessions for different integration types
2. Sending requests through various channels
3. Handling responses
4. Session management
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict

import httpx


class RequestManagerClient:
    """Client for interacting with the Request Manager API."""

    def __init__(
        self, base_url: str = "http://request-manager.llama-stack-rag.svc.cluster.local"
    ):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)

    async def create_session(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new session."""
        response = await self.client.post(
            f"{self.base_url}/api/v1/sessions",
            json=session_data,
        )
        response.raise_for_status()
        return response.json()

    async def get_session(self, session_id: str) -> Dict[str, Any]:
        """Get session information."""
        response = await self.client.get(
            f"{self.base_url}/api/v1/sessions/{session_id}"
        )
        response.raise_for_status()
        return response.json()

    async def send_slack_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send a Slack request."""
        response = await self.client.post(
            f"{self.base_url}/api/v1/requests/slack",
            json=request_data,
        )
        response.raise_for_status()
        return response.json()

    async def send_web_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send a web request."""
        response = await self.client.post(
            f"{self.base_url}/api/v1/requests/web",
            json=request_data,
        )
        response.raise_for_status()
        return response.json()

    async def send_cli_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send a CLI request."""
        response = await self.client.post(
            f"{self.base_url}/api/v1/requests/cli",
            json=request_data,
        )
        response.raise_for_status()
        return response.json()

    async def send_tool_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send a tool request."""
        response = await self.client.post(
            f"{self.base_url}/api/v1/requests/tool",
            json=request_data,
        )
        response.raise_for_status()
        return response.json()

    async def health_check(self) -> Dict[str, Any]:
        """Check service health."""
        response = await self.client.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


async def demo_slack_integration():
    """Demonstrate Slack integration."""
    print("🔵 Slack Integration Demo")
    print("=" * 50)

    client = RequestManagerClient()

    try:
        # Create a Slack session
        session_data = {
            "user_id": "alice.johnson",
            "integration_type": "slack",
            "channel_id": "C123456789",
            "thread_id": "1234567890.123456",
            "integration_metadata": {
                "slack_team_id": "T123456789",
                "channel_name": "it-support",
                "team_name": "Acme Corp",
            },
            "user_context": {
                "display_name": "Alice Johnson",
                "email": "alice.johnson@acme.com",
                "timezone": "America/New_York",
            },
        }

        session = await client.create_session(session_data)
        print(f"✅ Created session: {session['session_id']}")

        # Send a request
        request_data = {
            "user_id": "alice.johnson",
            "content": "Hi! I need help refreshing my laptop. It's getting really slow.",
            "channel_id": "C123456789",
            "thread_id": "1234567890.123456",
            "slack_user_id": "U123456789",
            "slack_team_id": "T123456789",
            "metadata": {"message_ts": "1234567890.123456", "channel_type": "channel"},
        }

        response = await client.send_slack_request(request_data)
        print(f"✅ Request sent: {response['request_id']}")
        print(f"   Status: {response['status']}")
        print(f"   Message: {response['message']}")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await client.close()


async def demo_web_integration():
    """Demonstrate web integration."""
    print("\n🌐 Web Integration Demo")
    print("=" * 50)

    client = RequestManagerClient()

    try:
        # Send a web request (session will be created automatically)
        request_data = {
            "user_id": "bob.smith",
            "content": "I want to update my email address in the system",
            "session_token": "web-session-abc123",
            "client_ip": "192.168.1.100",
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "metadata": {
                "page_url": "https://selfservice.acme.com/chat",
                "referrer": "https://selfservice.acme.com/profile",
                "browser_session_id": "sess_xyz789",
            },
        }

        response = await client.send_web_request(request_data)
        print(f"✅ Request sent: {response['request_id']}")
        print(f"   Session: {response['session_id']}")

        # Get session info
        session = await client.get_session(response["session_id"])
        print("✅ Session info retrieved:")
        print(f"   User: {session['user_id']}")
        print(f"   Integration: {session['integration_type']}")
        print(f"   Total requests: {session['total_requests']}")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await client.close()


async def demo_cli_integration():
    """Demonstrate CLI integration."""
    print("\n💻 CLI Integration Demo")
    print("=" * 50)

    client = RequestManagerClient()

    try:
        # Send a CLI request
        request_data = {
            "user_id": "charlie.brown",
            "content": "agent help laptop-refresh",
            "cli_session_id": "cli-sess-def456",
            "command_context": {
                "command": "agent",
                "subcommand": "help",
                "args": ["laptop-refresh"],
                "working_directory": "/home/charlie",
                "shell": "bash",
            },
            "metadata": {
                "cli_version": "1.2.3",
                "os": "linux",
                "terminal": "xterm-256color",
            },
        }

        response = await client.send_cli_request(request_data)
        print(f"✅ CLI request sent: {response['request_id']}")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await client.close()


async def demo_tool_integration():
    """Demonstrate tool integration."""
    print("\n🔧 Tool Integration Demo")
    print("=" * 50)

    client = RequestManagerClient()

    try:
        # Simulate a tool-generated request (e.g., from ServiceNow)
        request_data = {
            "user_id": "diana.prince",
            "content": "Automated notification: User's laptop is due for refresh based on asset management policy. Current device is 3+ years old.",
            "tool_id": "snow-integration",
            "tool_instance_id": "snow-prod-01",
            "trigger_event": "asset.refresh.due",
            "tool_context": {
                "ticket_id": "INC0012345",
                "asset_tag": "LAPTOP-12345",
                "current_model": "Dell Latitude 7420",
                "purchase_date": "2021-01-15",
                "refresh_due_date": "2024-01-15",
                "priority": "medium",
                "target_agent_id": "laptop-refresh-agent",  # Tool specifies target agent
            },
            "metadata": {
                "automation_rule": "3-year-refresh-policy",
                "triggered_by": "scheduled-job",
                "correlation_id": "corr-abc123",
            },
        }

        response = await client.send_tool_request(request_data)
        print(f"✅ Tool request sent: {response['request_id']}")
        print("   This request will be routed directly to the laptop-refresh-agent")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await client.close()


async def demo_health_check():
    """Demonstrate health check."""
    print("\n🏥 Health Check Demo")
    print("=" * 50)

    client = RequestManagerClient()

    try:
        health = await client.health_check()
        print(f"✅ Service health: {health['status']}")
        print(f"   Database connected: {health['database_connected']}")
        print(f"   Version: {health['version']}")
        print(f"   Services: {health['services']}")

    except Exception as e:
        print(f"❌ Health check failed: {e}")
    finally:
        await client.close()


async def demo_session_management():
    """Demonstrate session management features."""
    print("\n📋 Session Management Demo")
    print("=" * 50)

    client = RequestManagerClient()

    try:
        # Create multiple sessions for the same user but different integrations
        user_id = "multi.user"

        # Slack session
        slack_session = await client.create_session(
            {
                "user_id": user_id,
                "integration_type": "slack",
                "channel_id": "C999888777",
                "integration_metadata": {"team_id": "T999888777"},
            }
        )

        # Web session
        web_session = await client.create_session(
            {
                "user_id": user_id,
                "integration_type": "web",
                "integration_metadata": {"browser": "chrome"},
            }
        )

        print(f"✅ Created Slack session: {slack_session['session_id']}")
        print(f"✅ Created Web session: {web_session['session_id']}")

        # Send requests to both sessions
        await client.send_slack_request(
            {
                "user_id": user_id,
                "content": "Hello from Slack!",
                "channel_id": "C999888777",
                "slack_user_id": "U999888777",
                "slack_team_id": "T999888777",
            }
        )

        await client.send_web_request(
            {"user_id": user_id, "content": "Hello from web!", "client_ip": "10.0.0.1"}
        )

        # Check session states
        slack_updated = await client.get_session(slack_session["session_id"])
        web_updated = await client.get_session(web_session["session_id"])

        print(f"✅ Slack session requests: {slack_updated['total_requests']}")
        print(f"✅ Web session requests: {web_updated['total_requests']}")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await client.close()


async def main():
    """Run all demos."""
    print("🚀 Request Management Layer Demo")
    print("=" * 50)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}Z")
    print()

    # Run health check first
    await demo_health_check()

    # Run integration demos
    await demo_slack_integration()
    await demo_web_integration()
    await demo_cli_integration()
    await demo_tool_integration()

    # Run session management demo
    await demo_session_management()

    print("\n✅ All demos completed!")


if __name__ == "__main__":
    asyncio.run(main())
