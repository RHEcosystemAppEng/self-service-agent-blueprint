"""Tests for Snow Server MCP server."""

import pytest
from mcp.server.fastmcp import Context
from snow.server import open_laptop_refresh_ticket


def test_open_laptop_refresh_ticket_success():
    """Test successful ticket creation."""
    employee_id = "1001"
    employee_name = "John Doe"
    business_justification = "Current laptop is outdated and affecting productivity"
    servicenow_laptop_code = "apple_mac_book_pro_14_m_3_pro"
    ctx = Context()

    result = open_laptop_refresh_ticket(
        employee_id=employee_id,
        employee_name=employee_name,
        business_justification=business_justification,
        servicenow_laptop_code=servicenow_laptop_code,
        ctx=ctx,
    )

    # Check that result contains expected information
    assert "ServiceNow Ticket Created Successfully!" in result
    assert employee_id in result
    assert employee_name in result
    assert business_justification in result
    assert servicenow_laptop_code in result
    assert "REQ" in result  # Ticket number format


def test_open_laptop_refresh_ticket_required_model():
    """Test ticket creation with required ServiceNow laptop code."""
    employee_id = "1002"
    employee_name = "Jane Smith"
    business_justification = "Hardware failure requiring replacement"
    servicenow_laptop_code = "lenovo_think_pad_t_14_gen_5_intel"
    ctx = Context()

    result = open_laptop_refresh_ticket(
        employee_id=employee_id,
        employee_name=employee_name,
        business_justification=business_justification,
        servicenow_laptop_code=servicenow_laptop_code,
        ctx=ctx,
    )

    # Check that result contains the specified model
    assert servicenow_laptop_code in result


def test_open_laptop_refresh_ticket_empty_employee_id():
    """Test error handling for empty employee ID."""
    ctx = Context()
    with pytest.raises(ValueError, match="Employee ID cannot be empty"):
        open_laptop_refresh_ticket(
            employee_id="",
            employee_name="John Doe",
            business_justification="Need new laptop",
            servicenow_laptop_code="apple_mac_book_air_m_3",
            ctx=ctx,
        )


def test_open_laptop_refresh_ticket_empty_employee_name():
    """Test error handling for empty employee name."""
    ctx = Context()
    with pytest.raises(ValueError, match="Employee name cannot be empty"):
        open_laptop_refresh_ticket(
            employee_id="1001",
            employee_name="",
            business_justification="Need new laptop",
            servicenow_laptop_code="apple_mac_book_air_m_3",
            ctx=ctx,
        )


def test_open_laptop_refresh_ticket_empty_justification():
    """Test error handling for empty business justification."""
    ctx = Context()
    with pytest.raises(ValueError, match="Business justification cannot be empty"):
        open_laptop_refresh_ticket(
            employee_id="1001",
            employee_name="John Doe",
            business_justification="",
            servicenow_laptop_code="apple_mac_book_air_m_3",
            ctx=ctx,
        )


def test_open_laptop_refresh_ticket_empty_servicenow_code():
    """Test error handling for empty ServiceNow laptop code."""
    ctx = Context()
    with pytest.raises(ValueError, match="ServiceNow laptop code cannot be empty"):
        open_laptop_refresh_ticket(
            employee_id="1001",
            employee_name="John Doe",
            business_justification="Need new laptop",
            servicenow_laptop_code="",
            ctx=ctx,
        )
