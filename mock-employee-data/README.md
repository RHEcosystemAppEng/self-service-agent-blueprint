# Mock Employee Data

A Python library providing mock employee data for testing purposes.

## Overview

This library contains mock employee data with laptop information for testing ServiceNow integrations and other systems that require employee and asset data.

## Installation

```bash
pip install mock-employee-data
```

## Usage

```python
from mock_employee_data import MOCK_EMPLOYEE_DATA

# Access mock employee data
employee = MOCK_EMPLOYEE_DATA["alice.johnson@company.com"]
print(employee["name"])  # Alice Johnson
print(employee["laptop_model"])  # Latitude 7420
```

## Data Structure

Each employee entry contains:
- Employee information (ID, name, email, location)
- Laptop details (model, serial number, warranty status)
- Asset tracking information (asset tag, operational status)

## Development

To set up for development:

```bash
pip install -e ".[dev]"
```

To run tests:

```bash
pytest
```

To format code:

```bash
black src/
isort src/
```