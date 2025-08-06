"""Tests for the Employee Info MCP Server."""

import pytest
from employee_info.server import _get_employee_laptop_info, _list_employees


def test_get_employee_laptop_info_valid_employee():
    """Test retrieving laptop info for a valid employee."""
    result = _get_employee_laptop_info("emp001")

    assert result["employee_id"] == "emp001"
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


def test_list_employees():
    """Test listing all employees."""
    result = _list_employees()

    assert "total_employees" in result
    assert "employees" in result
    assert result["total_employees"] == 3
    assert len(result["employees"]) == 3

    employee_ids = [emp["employee_id"] for emp in result["employees"]]
    assert "emp001" in employee_ids
    assert "emp002" in employee_ids
    assert "emp003" in employee_ids


def test_employee_data_structure():
    """Test that employee data has the expected structure."""
    result = _get_employee_laptop_info("emp002")

    required_fields = [
        "employee_id",
        "name",
        "department",
        "email",
        "laptop",
        "it_contact",
    ]
    for field in required_fields:
        assert field in result

    laptop_fields = [
        "brand",
        "model",
        "serial_number",
        "assignment_date",
        "warranty_expiry",
        "warranty_status",
        "specs",
    ]
    for field in laptop_fields:
        assert field in result["laptop"]

    it_contact_fields = ["name", "email", "phone"]
    for field in it_contact_fields:
        assert field in result["it_contact"]
