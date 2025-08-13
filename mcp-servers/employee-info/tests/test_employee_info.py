"""Tests for the Employee Info MCP Server."""

import pytest
from employee_info.server import _get_employee_laptop_info


def test_get_employee_laptop_info_valid_employee():
    """Test retrieving laptop info for a valid employee."""
    result = _get_employee_laptop_info("1001")

    expected = f"""
    Employee Laptop Information-
    Model: Latitude 7420
    Purchase Date: 2020-01-15
    Warranty Expiry Date: 2023-01-15
    Warranty Status: Expired
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
