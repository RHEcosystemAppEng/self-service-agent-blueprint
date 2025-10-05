"""Mock data for ServiceNow ticket management."""

from datetime import datetime, timedelta

# Mock ticket data for simulation purposes
MOCK_TICKET_DATA = {}


def generate_ticket_number():
    """Generate a mock ServiceNow ticket number."""
    import uuid

    return f"INC{str(uuid.uuid4().hex[:8]).upper()}"


def create_laptop_refresh_ticket(
    employee_id: str,
    employee_name: str,
    business_justification: str,
    preferred_model: str,
):
    """Create a mock laptop refresh ticket and return ticket details."""
    ticket_number = generate_ticket_number()

    ticket_data = {
        "ticket_number": ticket_number,
        "employee_id": employee_id,
        "employee_name": employee_name,
        "request_type": "Laptop Refresh",
        "business_justification": business_justification,
        "preferred_model": preferred_model or "Standard Business Laptop",
        "status": "Open",
        "priority": "Medium",
        "created_date": datetime.now().isoformat(),
        "expected_completion": (datetime.now() + timedelta(days=5)).isoformat(),
        "assigned_group": "IT Hardware Team",
        "description": f"Laptop refresh request for employee {employee_name} (ID: {employee_id}). Justification: {business_justification}",
    }

    # Store in mock data
    MOCK_TICKET_DATA[ticket_number] = ticket_data

    return ticket_data


def get_mock_laptop_info(employee_email: str) -> str:
    """Get laptop information from mock data."""
    # Mock laptop info data
    laptop_info_data = {
        "john.doe@company.com": """Employee Name: John Doe
Employee ID: 1001
Employee Location: New York Office
Total Laptops: 1

Laptop 1:
  Model: Dell Latitude 5520
  Serial Number: ABC123456
  Purchase Date: 2022-03-15
  Warranty Expiry: 2025-03-15
  Warranty Status: Active
""",
        "jane.smith@company.com": """Employee Name: Jane Smith
Employee ID: 1002
Employee Location: San Francisco Office
Total Laptops: 2

Laptop 1:
  Model: MacBook Pro 16-inch
  Serial Number: DEF789012
  Purchase Date: 2023-01-10
  Warranty Expiry: 2026-01-10
  Warranty Status: Active

Laptop 2:
  Model: Dell XPS 13
  Serial Number: GHI345678
  Purchase Date: 2021-06-20
  Warranty Expiry: 2024-06-20
  Warranty Status: Expired
""",
        "bob.wilson@company.com": """Employee Name: Bob Wilson
Employee ID: 1003
Employee Location: London Office
Total Laptops: 1

Laptop 1:
  Model: HP EliteBook 850
  Serial Number: JKL901234
  Purchase Date: 2023-09-05
  Warranty Expiry: 2026-09-05
  Warranty Status: Active
""",
        "alice.brown@company.com": """Employee Name: Alice Brown
Employee ID: 1004
Employee Location: Tokyo Office
Total Laptops: 1

Laptop 1:
  Model: Lenovo ThinkPad X1 Carbon
  Serial Number: MNO567890
  Purchase Date: 2022-11-12
  Warranty Expiry: 2025-11-12
  Warranty Status: Active
""",
        "charlie.davis@company.com": """Employee Name: Charlie Davis
Employee ID: 1005
Employee Location: Sydney Office
Total Laptops: 1

Laptop 1:
  Model: Microsoft Surface Laptop 4
  Serial Number: PQR123456
  Purchase Date: 2023-04-18
  Warranty Expiry: 2026-04-18
  Warranty Status: Active
""",
    }

    if employee_email in laptop_info_data:
        return laptop_info_data[employee_email]
    else:
        return f"Employee with email '{employee_email}' not found in the system."
