"""Tests for the Employee Info MCP Server."""

import pytest
from employee_info.server import _get_employee_laptop_info


def test_get_employee_laptop_info_valid_employee():
    """Test retrieving laptop info for a valid employee."""
    result = _get_employee_laptop_info("1001")

    assert result["employee_id"] == "1001"
    assert result["name"] == "Alice Johnson"
    assert result["department"] == "Engineering"
    assert "laptop" in result
    assert result["laptop"]["brand"] == "Dell"
    assert result["laptop"]["model"] == "Latitude 7420"
    assert "it_contact" in result


def test_get_employee_laptop_info_invalid_employee():
    """Test error handling for invalid employee ID."""
    with pytest.raises(ValueError) as exc_info:
        _get_employee_laptop_info("invalid_id")

    assert "not found" in str(exc_info.value)
    assert "Available IDs" in str(exc_info.value)


def test_get_employee_laptop_info_empty_employee_id():
    """Test error handling for empty employee ID."""
    with pytest.raises(ValueError) as exc_info:
        _get_employee_laptop_info("")

    assert "cannot be empty" in str(exc_info.value)


def test_employee_data_structure():
    """Test that employee data has the expected structure."""
    result = _get_employee_laptop_info("1002")

    required_fields = [
        "employee_id",
        "name",
        "department",
        "email",
        "location",
        "laptop_model",
        "laptop_serial_number",
        "laptop",
        "it_contact",
    ]
    for field in required_fields:
        assert field in result

    laptop_fields = [
        "brand",
        "model",
        "serial_number",
        "purchase_date",
        "warranty_expiry",
        "warranty_status",
        "specs",
    ]
    for field in laptop_fields:
        assert field in result["laptop"]

    it_contact_fields = ["name", "email", "phone"]
    for field in it_contact_fields:
        assert field in result["it_contact"]


def test_new_top_level_laptop_fields():
    """Test that new laptop fields are present at the top level."""
    result = _get_employee_laptop_info("1001")
    
    # Test top-level laptop fields
    assert "laptop_model" in result
    assert "laptop_serial_number" in result
    assert result["laptop_model"] == "Latitude 7420"
    assert result["laptop_serial_number"] == "DL7420001"
    
    # Test location field exists and has valid values
    assert "location" in result
    assert result["location"] in ["NA", "LATAM", "EMEA", "APAC"]


def test_purchase_date_field():
    """Test that purchase_date field exists and is properly formatted."""
    result = _get_employee_laptop_info("1003")
    
    assert "laptop" in result
    assert "purchase_date" in result["laptop"]
    
    # Verify date format (YYYY-MM-DD)
    purchase_date = result["laptop"]["purchase_date"]
    assert len(purchase_date) == 10
    assert purchase_date[4] == "-"
    assert purchase_date[7] == "-"
    
    # Verify year is between 2018-2023 as required
    year = int(purchase_date[:4])
    assert 2018 <= year <= 2023
