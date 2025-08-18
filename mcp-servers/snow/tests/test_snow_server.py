"""Tests for Snow Server MCP server."""

import pytest
from snow_server.server import open_laptop_refresh_ticket
from snow_server.data.data import MOCK_TICKET_DATA


def test_open_laptop_refresh_ticket_success():
    """Test successful ticket creation."""
    employee_id = "1001"
    employee_name = "John Doe"
    business_justification = "Current laptop is outdated and affecting productivity"
    preferred_model = "MacBook Pro"

    result = open_laptop_refresh_ticket(
        employee_id=employee_id,
        employee_name=employee_name,
        business_justification=business_justification,
        preferred_model=preferred_model,
    )

    # Check that result contains expected information
    assert "ServiceNow Ticket Created Successfully!" in result
    assert employee_id in result
    assert employee_name in result
    assert business_justification in result
    assert preferred_model in result
    assert "INC" in result  # Ticket number format


def test_open_laptop_refresh_ticket_default_model():
    """Test ticket creation with default model."""
    employee_id = "1002"
    employee_name = "Jane Smith"
    business_justification = "Hardware failure requiring replacement"

    result = open_laptop_refresh_ticket(
        employee_id=employee_id,
        employee_name=employee_name,
        business_justification=business_justification,
    )

    # Check that result contains default model
    assert "Standard Business Laptop" in result


def test_open_laptop_refresh_ticket_empty_employee_id():
    """Test error handling for empty employee ID."""
    with pytest.raises(ValueError, match="Employee ID cannot be empty"):
        open_laptop_refresh_ticket(
            employee_id="",
            employee_name="John Doe",
            business_justification="Need new laptop",
        )


def test_open_laptop_refresh_ticket_empty_employee_name():
    """Test error handling for empty employee name."""
    with pytest.raises(ValueError, match="Employee name cannot be empty"):
        open_laptop_refresh_ticket(
            employee_id="1001",
            employee_name="",
            business_justification="Need new laptop",
        )


def test_open_laptop_refresh_ticket_empty_justification():
    """Test error handling for empty business justification."""
    with pytest.raises(ValueError, match="Business justification cannot be empty"):
        open_laptop_refresh_ticket(
            employee_id="1001", employee_name="John Doe", business_justification=""
        )
