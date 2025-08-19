"""Tests for the Employee Info MCP Server."""

import pytest
from employee_info.server import _get_employee_laptop_info


def test_get_employee_laptop_info_valid_employee():
    """Test retrieving laptop info for a valid employee."""
    result = _get_employee_laptop_info("1001")

    expected = """
    Employee Name: Alice Johnson
    Employee ID: 1001
    Employee Location: EMEA
    Laptop Model: Latitude 7420
    Laptop Serial Number: DL7420001
    Laptop Purchase Date: 2020-01-15
    Laptop Warranty Expiry Date: 2023-01-15
    Laptop Warranty: Expired
    """

    assert result == expected


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
