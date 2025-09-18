"""Tests for Snow Server MCP server."""

import pytest
from snow.server import open_laptop_refresh_ticket


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


def test_open_laptop_refresh_ticket_required_model():
    """Test ticket creation with required preferred model."""
    employee_id = "1002"
    employee_name = "Jane Smith"
    business_justification = "Hardware failure requiring replacement"
    preferred_model = "Dell Latitude 5520"

    result = open_laptop_refresh_ticket(
        employee_id=employee_id,
        employee_name=employee_name,
        business_justification=business_justification,
        preferred_model=preferred_model,
    )

    # Check that result contains the specified model
    assert preferred_model in result


def test_open_laptop_refresh_ticket_empty_employee_id():
    """Test error handling for empty employee ID."""
    with pytest.raises(ValueError, match="Employee ID cannot be empty"):
        open_laptop_refresh_ticket(
            employee_id="",
            employee_name="John Doe",
            business_justification="Need new laptop",
            preferred_model="MacBook Pro",
        )


def test_open_laptop_refresh_ticket_empty_employee_name():
    """Test error handling for empty employee name."""
    with pytest.raises(ValueError, match="Employee name cannot be empty"):
        open_laptop_refresh_ticket(
            employee_id="1001",
            employee_name="",
            business_justification="Need new laptop",
            preferred_model="MacBook Pro",
        )


def test_open_laptop_refresh_ticket_empty_justification():
    """Test error handling for empty business justification."""
    with pytest.raises(ValueError, match="Business justification cannot be empty"):
        open_laptop_refresh_ticket(
            employee_id="1001",
            employee_name="John Doe",
            business_justification="",
            preferred_model="MacBook Pro",
        )


def test_open_laptop_refresh_ticket_empty_preferred_model():
    """Test error handling for empty preferred model."""
    with pytest.raises(ValueError, match="Preferred model cannot be empty"):
        open_laptop_refresh_ticket(
            employee_id="1001",
            employee_name="John Doe",
            business_justification="Need new laptop",
            preferred_model="",
        )
