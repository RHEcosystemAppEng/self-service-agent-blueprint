"""Integration tests for Snow Server MCP server with mock ServiceNow API."""

import os
import subprocess
import time
from typing import Generator

import pytest
from snow.server import get_employee_laptop_info, open_laptop_refresh_ticket


class MockRequest:
    """Mock request object with headers."""

    def __init__(self, headers: dict[str, str]):
        self.headers = headers


class MockRequestContext:
    """Mock request context."""

    def __init__(self, headers: dict[str, str]):
        self.request = MockRequest(headers)


class MockContext:
    """Mock Context object for testing."""

    def __init__(self, headers: dict[str, str]):
        self.request_context = MockRequestContext(headers)


@pytest.fixture(scope="module")
def mock_servicenow_server() -> Generator[str, None, None]:
    """Start and stop the mock ServiceNow server for integration tests."""

    # Find available port
    import socket

    sock = socket.socket()
    sock.bind(("", 0))
    port = sock.getsockname()[1]
    sock.close()

    # Start the mock ServiceNow server
    # Navigate to the mock-service-now directory relative to the current test directory
    import pathlib

    current_dir = pathlib.Path(__file__).parent.resolve()
    mock_servicenow_dir = current_dir.parent.parent.parent / "mock-service-now"

    server_process = subprocess.Popen(
        ["uv", "run", "python", "-m", "mock_service_now.main"],
        env={**os.environ, "PORT": str(port), "HOST": "127.0.0.1"},
        cwd=str(mock_servicenow_dir),
    )

    # Wait for server to be ready by polling health endpoint
    import requests

    server_url = f"http://127.0.0.1:{port}"
    max_attempts = 30  # 30 seconds max wait
    for attempt in range(max_attempts):
        try:
            response = requests.get(f"{server_url}/health", timeout=1)
            if response.status_code == 200:
                print(f"Mock server ready after {attempt + 1} attempts")
                break
        except requests.exceptions.RequestException:
            pass
        time.sleep(1)
    else:
        server_process.terminate()
        server_process.wait()
        raise RuntimeError(
            f"Mock server failed to become ready within {max_attempts} seconds"
        )

    # Set environment for tests to use the mock server
    original_url = os.environ.get("SERVICENOW_INSTANCE_URL")
    os.environ["SERVICENOW_INSTANCE_URL"] = f"http://127.0.0.1:{port}"
    os.environ["SERVICENOW_AUTH_TYPE"] = "basic"
    os.environ["SERVICENOW_USERNAME"] = "testuser"
    os.environ["SERVICENOW_PASSWORD"] = "testpass"

    yield f"http://127.0.0.1:{port}"

    # Cleanup
    server_process.terminate()
    server_process.wait()

    # Restore original environment
    if original_url:
        os.environ["SERVICENOW_INSTANCE_URL"] = original_url
    else:
        os.environ.pop("SERVICENOW_INSTANCE_URL", None)


def test_open_laptop_refresh_ticket_integration(mock_servicenow_server: str) -> None:
    """Test successful ticket creation using actual ServiceNow client against mock server."""
    employee_name = "John Doe"
    business_justification = "Current laptop is outdated and affecting productivity"
    servicenow_laptop_code = "apple_mac_book_pro_14_m_3_pro"

    # Create mock context with AUTHORITATIVE_USER_ID header
    ctx = MockContext({"AUTHORITATIVE_USER_ID": "alice.johnson@company.com"})

    result = open_laptop_refresh_ticket(
        employee_name=employee_name,
        business_justification=business_justification,
        servicenow_laptop_code=servicenow_laptop_code,
        ctx=ctx,
    )

    # Check that result contains expected information (realistic ServiceNow format)
    assert "opened for employee" in result
    assert "alice.johnson@company.com" in result  # authoritative_user_id
    assert "REQ" in result  # Ticket number format
    assert "System ID:" in result  # Should have a sys_id

    # Verify it's not the old hardcoded format
    assert "System ID: 1001" not in result  # Old format should not appear


def test_open_laptop_refresh_ticket_different_user(mock_servicenow_server: str) -> None:
    """Test ticket creation for a different user."""
    employee_name = "Jane Smith"
    business_justification = "Hardware failure requiring replacement"
    servicenow_laptop_code = "lenovo_think_pad_t_14_gen_5_intel"

    # Use a different user
    ctx = MockContext({"AUTHORITATIVE_USER_ID": "john.doe@company.com"})

    result = open_laptop_refresh_ticket(
        employee_name=employee_name,
        business_justification=business_justification,
        servicenow_laptop_code=servicenow_laptop_code,
        ctx=ctx,
    )

    # Check that result contains the expected format
    assert "opened for employee" in result
    assert "john.doe@company.com" in result
    assert "REQ" in result


def test_get_employee_laptop_info_integration(mock_servicenow_server: str) -> None:
    """Test getting employee laptop info using actual ServiceNow client."""
    ctx = MockContext({"AUTHORITATIVE_USER_ID": "alice.johnson@company.com"})

    result = get_employee_laptop_info(ctx)

    # Verify the response format matches what we expect from ServiceNow
    assert "Employee Name: Alice Johnson" in result
    assert "Employee Location: EMEA" in result
    assert "Laptop Model: Latitude 7420" in result
    assert "Laptop Serial Number: DL7420001" in result
    assert "Laptop Purchase Date:" in result
    assert "Laptop Age:" in result
    assert "Laptop Warranty:" in result


def test_get_employee_laptop_info_different_user(mock_servicenow_server: str) -> None:
    """Test getting laptop info for a different user."""
    ctx = MockContext({"AUTHORITATIVE_USER_ID": "john.doe@company.com"})

    result = get_employee_laptop_info(ctx)

    # Verify it returns info for the correct user
    assert "Employee Name: John Doe" in result
    assert "Employee Location: EMEA" in result
    assert "Laptop Model: MacBook Pro 14-inch" in result


def test_open_laptop_refresh_ticket_empty_employee_name(
    mock_servicenow_server: str,
) -> None:
    """Test error handling for empty employee name."""
    ctx = MockContext({"AUTHORITATIVE_USER_ID": "alice.johnson@company.com"})
    with pytest.raises(ValueError, match="Employee name cannot be empty"):
        open_laptop_refresh_ticket(
            employee_name="",
            business_justification="Need new laptop",
            servicenow_laptop_code="apple_mac_book_air_m_3",
            ctx=ctx,
        )


def test_open_laptop_refresh_ticket_empty_justification(
    mock_servicenow_server: str,
) -> None:
    """Test error handling for empty business justification."""
    ctx = MockContext({"AUTHORITATIVE_USER_ID": "alice.johnson@company.com"})
    with pytest.raises(ValueError, match="Business justification cannot be empty"):
        open_laptop_refresh_ticket(
            employee_name="John Doe",
            business_justification="",
            servicenow_laptop_code="apple_mac_book_air_m_3",
            ctx=ctx,
        )


def test_open_laptop_refresh_ticket_empty_servicenow_code(
    mock_servicenow_server: str,
) -> None:
    """Test error handling for empty ServiceNow laptop code."""
    ctx = MockContext({"AUTHORITATIVE_USER_ID": "alice.johnson@company.com"})
    with pytest.raises(ValueError, match="ServiceNow laptop code cannot be empty"):
        open_laptop_refresh_ticket(
            employee_name="John Doe",
            business_justification="Need new laptop",
            servicenow_laptop_code="",
            ctx=ctx,
        )


def test_missing_authoritative_user_id(mock_servicenow_server: str) -> None:
    """Test error handling when AUTHORITATIVE_USER_ID header is missing."""
    ctx = MockContext({})  # No AUTHORITATIVE_USER_ID header
    with pytest.raises(ValueError, match="Authoritative user ID not found"):
        open_laptop_refresh_ticket(
            employee_name="John Doe",
            business_justification="Need new laptop",
            servicenow_laptop_code="apple_mac_book_air_m_3",
            ctx=ctx,
        )


def test_user_not_found(mock_servicenow_server: str) -> None:
    """Test behavior when user is not found in the mock data."""
    ctx = MockContext({"AUTHORITATIVE_USER_ID": "unknown.user@company.com"})

    # This should fail because the user doesn't exist in our mock data
    with pytest.raises(
        Exception
    ):  # ServiceNow client will raise an exception for user not found
        open_laptop_refresh_ticket(
            employee_name="Unknown User",
            business_justification="Need new laptop",
            servicenow_laptop_code="apple_mac_book_air_m_3",
            ctx=ctx,
        )
