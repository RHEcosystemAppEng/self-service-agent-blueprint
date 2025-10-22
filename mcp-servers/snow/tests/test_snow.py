"""Tests for Snow Server MCP server."""

import pytest
from snow.server import open_laptop_refresh_ticket


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


def test_open_laptop_refresh_ticket_success() -> None:
    """Test successful ticket creation."""
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

    # Check that result contains expected information
    assert "opened for employee" in result
    assert "alice.johnson@company.com" in result  # authoritative_user_id
    assert "System ID: 1001" in result  # employee_id from mock data
    assert "REQ" in result  # Ticket number format


def test_open_laptop_refresh_ticket_required_model() -> None:
    """Test ticket creation with required ServiceNow laptop code."""
    employee_name = "Jane Smith"
    business_justification = "Hardware failure requiring replacement"
    servicenow_laptop_code = "lenovo_think_pad_t_14_gen_5_intel"

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
