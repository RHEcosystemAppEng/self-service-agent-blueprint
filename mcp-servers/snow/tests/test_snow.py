"""Tests for Snow Server MCP server."""

from unittest.mock import MagicMock, Mock, patch

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


@patch("snow.server.mcp")
@patch("snow.server.ServiceNowClient")
def test_open_laptop_refresh_ticket_success(
    mock_servicenow_client: Mock, mock_mcp: Mock
) -> None:
    """Test successful ticket creation."""
    employee_name = "John Doe"
    business_justification = "Current laptop is outdated and affecting productivity"
    servicenow_laptop_code = "apple_mac_book_pro_14_m_3_pro"

    # Mock the mcp.laptop_refresh_id attribute
    mock_mcp.laptop_refresh_id = "test_laptop_refresh_id"

    # Mock ServiceNow client responses
    mock_client_instance = MagicMock()
    mock_servicenow_client.return_value = mock_client_instance

    # Mock user lookup response
    mock_client_instance.get_user_by_email.return_value = {
        "success": True,
        "user": {"sys_id": "1001"},
    }

    # Mock ticket creation response
    mock_client_instance.open_laptop_refresh_request.return_value = {
        "success": True,
        "data": {"result": {"request_number": "REQ0010037", "sys_id": "1001"}},
    }

    # Create mock context with AUTHORITATIVE_USER_ID header
    ctx = MockContext({"AUTHORITATIVE_USER_ID": "alice.johnson@company.com"})

    result = open_laptop_refresh_ticket(
        employee_name=employee_name,
        business_justification=business_justification,
        servicenow_laptop_code=servicenow_laptop_code,
        ctx=ctx,
    )

    # Check that result contains expected information
    assert "opened for employee" in result
    assert "alice.johnson@company.com" in result  # authoritative_user_id
    assert "System ID: 1001" in result  # employee_id from mock data
    assert "REQ" in result  # Ticket number format


@patch("snow.server.mcp")
@patch("snow.server.ServiceNowClient")
def test_open_laptop_refresh_ticket_required_model(
    mock_servicenow_client: Mock,
    mock_mcp: Mock,
) -> None:
    """Test ticket creation with required ServiceNow laptop code."""
    employee_name = "Jane Smith"
    business_justification = "Hardware failure requiring replacement"
    servicenow_laptop_code = "lenovo_think_pad_t_14_gen_5_intel"

    # Mock the mcp.laptop_refresh_id attribute
    mock_mcp.laptop_refresh_id = "test_laptop_refresh_id"

    # Mock ServiceNow client responses
    mock_client_instance = MagicMock()
    mock_servicenow_client.return_value = mock_client_instance

    # Mock user lookup response
    mock_client_instance.get_user_by_email.return_value = {
        "success": True,
        "user": {"sys_id": "1001"},
    }

    # Mock ticket creation response
    mock_client_instance.open_laptop_refresh_request.return_value = {
        "success": True,
        "data": {"result": {"request_number": "REQ0010038", "sys_id": "1001"}},
    }

    # Create mock context with AUTHORITATIVE_USER_ID header
    ctx = MockContext({"AUTHORITATIVE_USER_ID": "alice.johnson@company.com"})

    result = open_laptop_refresh_ticket(
        employee_name=employee_name,
        business_justification=business_justification,
        servicenow_laptop_code=servicenow_laptop_code,
        ctx=ctx,
    )

    # Check that result contains the expected format
    assert "opened for employee" in result
    assert "alice.johnson@company.com" in result  # authoritative_user_id
    assert "System ID: 1001" in result  # employee_id from mock data
    assert "REQ" in result  # Ticket number format


def test_open_laptop_refresh_ticket_empty_employee_name() -> None:
    """Test error handling for empty employee name."""
    ctx = MockContext({"AUTHORITATIVE_USER_ID": "alice.johnson@company.com"})
    with pytest.raises(ValueError, match="Employee name cannot be empty"):
        open_laptop_refresh_ticket(
            employee_name="",
            business_justification="Need new laptop",
            servicenow_laptop_code="apple_mac_book_air_m_3",
            ctx=ctx,
        )


def test_open_laptop_refresh_ticket_empty_justification() -> None:
    """Test error handling for empty business justification."""
    ctx = MockContext({"AUTHORITATIVE_USER_ID": "alice.johnson@company.com"})
    with pytest.raises(ValueError, match="Business justification cannot be empty"):
        open_laptop_refresh_ticket(
            employee_name="John Doe",
            business_justification="",
            servicenow_laptop_code="apple_mac_book_air_m_3",
            ctx=ctx,
        )


def test_open_laptop_refresh_ticket_empty_servicenow_code() -> None:
    """Test error handling for empty ServiceNow laptop code."""
    ctx = MockContext({"AUTHORITATIVE_USER_ID": "alice.johnson@company.com"})
    with pytest.raises(ValueError, match="ServiceNow laptop code cannot be empty"):
        open_laptop_refresh_ticket(
            employee_name="John Doe",
            business_justification="Need new laptop",
            servicenow_laptop_code="",
            ctx=ctx,
        )


@patch("snow.server.mcp")
@patch("snow.server.ServiceNowClient")
def test_get_employee_laptop_info_success(
    mock_servicenow_client: Mock, mock_mcp: Mock
) -> None:
    """Test successful laptop info retrieval."""
    # Mock the mcp.laptop_refresh_id attribute
    mock_mcp.laptop_refresh_id = "test_laptop_refresh_id"

    # Mock ServiceNow client responses
    mock_client_instance = MagicMock()
    mock_servicenow_client.return_value = mock_client_instance

    # Mock laptop info response
    expected_laptop_info = """
    Employee Name: Alice Johnson
    Employee Location: EMEA
    Laptop Model: Latitude 7420
    Laptop Serial Number: DL7420001
    Laptop Purchase Date: 2020-01-15
    Laptop Age: 4 years and 10 months
    Laptop Warranty Expiry Date: 2023-01-15
    Laptop Warranty: Expired
    """

    mock_client_instance.get_employee_laptop_info.return_value = expected_laptop_info

    # Create mock context with AUTHORITATIVE_USER_ID header
    ctx = MockContext({"AUTHORITATIVE_USER_ID": "alice.johnson@company.com"})

    result = get_employee_laptop_info(ctx=ctx)

    # Check that result contains expected information
    assert "Alice Johnson" in result
    assert "EMEA" in result
    assert "Latitude 7420" in result
    assert "DL7420001" in result

    # Verify the ServiceNow client was called with the correct user ID
    mock_client_instance.get_employee_laptop_info.assert_called_once_with(
        "alice.johnson@company.com"
    )
