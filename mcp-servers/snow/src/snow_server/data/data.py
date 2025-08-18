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
    preferred_model: str = None,
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
