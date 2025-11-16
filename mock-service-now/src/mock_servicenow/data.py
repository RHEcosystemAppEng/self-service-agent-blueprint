"""Mock data for ServiceNow API responses."""

import random
from datetime import datetime
from typing import Any, Dict, List

from mock_employee_data import MOCK_EMPLOYEE_DATA


def generate_ticket_number() -> str:
    """Generate a mock ServiceNow ticket number."""
    # Generate 7-digit number to match ServiceNow format (e.g., REQ0010037)
    return f"REQ{random.randint(1000000, 9999999):07d}"


def find_user_by_email(email: str) -> Dict[str, Any] | None:
    """Find user by email address.

    Args:
        email: Email address to search for

    Returns:
        User data dictionary if found, None otherwise
    """
    if not email:
        return None

    user_data = MOCK_EMPLOYEE_DATA.get(email.lower())
    if not user_data:
        return None

    # Return ServiceNow-style user response
    return {
        "sys_id": user_data["sys_id"],
        "name": user_data["name"],
        "email": user_data["email"],
        "user_name": user_data["user_name"],
        "location": {
            "display_value": user_data["location"],
            "value": user_data["location"],
        },
        "active": user_data["active"],
    }


def find_computers_by_user_sys_id(user_sys_id: str) -> List[Dict[str, Any]]:
    """Find computers assigned to a user sys_id.

    Args:
        user_sys_id: User's sys_id

    Returns:
        List of computer data dictionaries
    """
    if not user_sys_id:
        return []

    # Find the user data by sys_id
    user_data = None
    for email, data in MOCK_EMPLOYEE_DATA.items():
        if data["sys_id"] == user_sys_id:
            user_data = data
            break

    if not user_data:
        return []

    # Return ServiceNow-style computer response
    return [
        {
            "sys_id": f"comp_{user_data['sys_id']}",
            "name": f"{user_data['name']}'s Laptop",
            "asset_tag": user_data["asset_tag"],
            "serial_number": user_data["laptop_serial_number"],
            "model_id": {
                "display_value": user_data["laptop_model"],
                "value": user_data["model_id"],
            },
            "assigned_to": user_sys_id,
            "purchase_date": user_data["purchase_date"],
            "warranty_expiration": user_data["warranty_expiry"],
            "install_status": user_data["install_status"],
            "operational_status": user_data["operational_status"],
        }
    ]


def create_laptop_refresh_request(
    laptop_refresh_id: str, laptop_choices: str, who_is_this_request_for: str
) -> Dict[str, Any]:
    """Create a mock laptop refresh request.

    Args:
        laptop_refresh_id: ServiceNow catalog item ID
        laptop_choices: Laptop model choice
        who_is_this_request_for: User sys_id

    Returns:
        ServiceNow-style response for ticket creation
    """
    ticket_number = generate_ticket_number()

    # Generate a mock sys_id for the request
    request_sys_id = f"req_{random.randint(100000, 999999)}"

    # ServiceNow-compatible response format
    return {
        "result": {
            "sys_id": request_sys_id,
            "request_number": ticket_number,
            "state": "1",  # Pending
            "stage": "requested",
            "opened_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "requested_for": who_is_this_request_for,
            "variables": {
                "laptop_choices": laptop_choices,
                "who_is_this_request_for": who_is_this_request_for,
            },
        }
    }
