"""Mock data for ServiceNow ticket management."""

from datetime import datetime, timedelta


def _calculate_laptop_age(purchase_date_str: str) -> str:
    """Calculate the age of a laptop in years and months from purchase date.

    Args:
        purchase_date_str: Purchase date in YYYY-MM-DD format

    Returns:
        A string describing the laptop age in years and months
    """
    try:
        purchase_date = datetime.strptime(purchase_date_str, "%Y-%m-%d")
        current_date = datetime.now()

        # Calculate the difference
        years = current_date.year - purchase_date.year
        months = current_date.month - purchase_date.month

        # Adjust if the current day is before the purchase day in the month
        if current_date.day < purchase_date.day:
            months -= 1

        # Adjust years and months if months is negative
        if months < 0:
            years -= 1
            months += 12

        # Format the output
        if years == 0:
            return f"{months} month{'s' if months != 1 else ''}"
        elif months == 0:
            return f"{years} year{'s' if years != 1 else ''}"
        else:
            return f"{years} year{'s' if years != 1 else ''} and {months} month{'s' if months != 1 else ''}"

    except (ValueError, TypeError):
        return "Unable to calculate age (invalid date format)"


# Mock ticket data for simulation purposes
MOCK_TICKET_DATA = {}


def generate_ticket_number():
    """Generate a mock ServiceNow ticket number."""
    import random

    # Generate 7-digit number to match ServiceNow format (e.g., REQ0010037)
    return f"REQ{random.randint(1000000, 9999999):07d}"


def create_laptop_refresh_ticket(
    authoritative_user_id: str,
    employee_name: str,
    business_justification: str,
    preferred_model: str,
) -> str:
    """Create a mock laptop refresh ticket and return formatted response.

    Args:
        authoritative_user_id: Authoritative user ID from request headers (email address)
        employee_name: Employee's full name
        business_justification: Business reason for laptop refresh
        preferred_model: ServiceNow laptop model code

    Returns:
        Formatted ticket details string matching real ServiceNow response format
    """
    ticket_number = generate_ticket_number()

    # Look up employee to get their employee_id for sys_id
    employee_data = find_employee_by_authoritative_user_id(authoritative_user_id)
    employee_id = employee_data["employee_id"]

    ticket_data = {
        "ticket_number": ticket_number,
        "authoritative_user_id": authoritative_user_id,
        "employee_name": employee_name,
        "request_type": "Laptop Refresh",
        "business_justification": business_justification,
        "preferred_model": preferred_model or "Standard Business Laptop",
        "status": "Open",
        "priority": "Medium",
        "created_date": datetime.now().isoformat(),
        "expected_completion": (datetime.now() + timedelta(days=5)).isoformat(),
        "assigned_group": "IT Hardware Team",
        "description": f"Laptop refresh request for employee {employee_name} ({authoritative_user_id}). Justification: {business_justification}",
        "sys_id": employee_id,  # Use employee_id as sys_id for consistency with real ServiceNow
    }

    # Store in mock data
    MOCK_TICKET_DATA[ticket_number] = ticket_data

    # Return format matching real ServiceNow response
    return f"{ticket_number} opened for employee {authoritative_user_id}. System ID: {employee_id}"


MOCK_EMPLOYEE_DATA = {
    "alice.johnson@company.com": {
        "employee_id": "1001",
        "name": "Alice Johnson",
        "email": "alice.johnson@company.com",
        "location": "EMEA",
        "laptop_model": "Latitude 7420",
        "laptop_serial_number": "DL7420001",
        "purchase_date": "2020-01-15",
        "warranty_expiry": "2023-01-15",
        "warranty_status": "Expired",
    },
    "john.doe@company.com": {
        "employee_id": "1002",
        "name": "John Doe",
        "email": "john.doe@company.com",
        "location": "EMEA",
        "laptop_model": "MacBook Pro 14-inch",
        "laptop_serial_number": "MBP14002",
        "purchase_date": "2023-03-20",
        "warranty_expiry": "2026-03-20",
        "warranty_status": "Active",
    },
    "maria.garcia@company.com": {
        "employee_id": "1003",
        "name": "Maria Garcia",
        "email": "maria.garcia@company.com",
        "location": "LATAM",
        "laptop_model": "ThinkPad X1 Carbon",
        "laptop_serial_number": "TP1C003",
        "purchase_date": "2022-11-10",
        "warranty_expiry": "2025-11-10",
        "warranty_status": "Active",
    },
    "oliver.smith@company.com": {
        "employee_id": "1004",
        "name": "Oliver Smith",
        "email": "oliver.smith@company.com",
        "location": "EMEA",
        "laptop_model": "EliteBook 840 G7",
        "laptop_serial_number": "HP840004",
        "purchase_date": "2019-05-12",
        "warranty_expiry": "2022-05-12",
        "warranty_status": "Expired",
    },
    "yuki.tanaka@company.com": {
        "employee_id": "1005",
        "name": "Yuki Tanaka",
        "email": "yuki.tanaka@company.com",
        "location": "APAC",
        "laptop_model": "XPS 13 9310",
        "laptop_serial_number": "DL13005",
        "purchase_date": "2018-09-03",
        "warranty_expiry": "2021-09-03",
        "warranty_status": "Expired",
    },
    "isabella.mueller@company.com": {
        "employee_id": "1006",
        "name": "Isabella Mueller",
        "email": "isabella.mueller@company.com",
        "location": "EMEA",
        "laptop_model": "ThinkPad T14",
        "laptop_serial_number": "TP14006",
        "purchase_date": "2019-11-18",
        "warranty_expiry": "2022-11-18",
        "warranty_status": "Expired",
    },
    "carlos.rodriguez@company.com": {
        "employee_id": "1007",
        "name": "Carlos Rodriguez",
        "email": "carlos.rodriguez@company.com",
        "location": "LATAM",
        "laptop_model": "MacBook Air M1",
        "laptop_serial_number": "MBA1007",
        "purchase_date": "2021-02-14",
        "warranty_expiry": "2024-02-14",
        "warranty_status": "Active",
    },
    "david.chen@company.com": {
        "employee_id": "1008",
        "name": "David Chen",
        "email": "david.chen@company.com",
        "location": "APAC",
        "laptop_model": "ZenBook Pro 15",
        "laptop_serial_number": "AS15008",
        "purchase_date": "2020-07-22",
        "warranty_expiry": "2023-07-22",
        "warranty_status": "Expired",
    },
    "sophie.dubois@company.com": {
        "employee_id": "1009",
        "name": "Sophie Dubois",
        "email": "sophie.dubois@company.com",
        "location": "EMEA",
        "laptop_model": "Surface Laptop 4",
        "laptop_serial_number": "MS4009",
        "purchase_date": "2021-08-05",
        "warranty_expiry": "2024-08-05",
        "warranty_status": "Active",
    },
    "ahmed.hassan@company.com": {
        "employee_id": "1010",
        "name": "Ahmed Hassan",
        "email": "ahmed.hassan@company.com",
        "location": "EMEA",
        "laptop_model": "Inspiron 15 5000",
        "laptop_serial_number": "DL15010",
        "purchase_date": "2018-03-14",
        "warranty_expiry": "2021-03-14",
        "warranty_status": "Expired",
    },
    "jane.smith@company.com": {
        "employee_id": "2001",
        "name": "Jane Smith",
        "email": "jane.smith@company.com",
        "location": "San Francisco Office",
        "laptop_model": "MacBook Pro 16-inch",
        "laptop_serial_number": "DEF789012",
        "purchase_date": "2023-01-10",
        "warranty_expiry": "2026-01-10",
        "warranty_status": "Active",
    },
    "bob.wilson@company.com": {
        "employee_id": "2002",
        "name": "Bob Wilson",
        "email": "bob.wilson@company.com",
        "location": "London Office",
        "laptop_model": "HP EliteBook 850",
        "laptop_serial_number": "JKL901234",
        "purchase_date": "2023-09-05",
        "warranty_expiry": "2026-09-05",
        "warranty_status": "Active",
    },
    "alice.brown@company.com": {
        "employee_id": "2003",
        "name": "Alice Brown",
        "email": "alice.brown@company.com",
        "location": "Tokyo Office",
        "laptop_model": "Lenovo ThinkPad X1 Carbon",
        "laptop_serial_number": "MNO567890",
        "purchase_date": "2022-11-12",
        "warranty_expiry": "2025-11-12",
        "warranty_status": "Active",
    },
    "charlie.davis@company.com": {
        "employee_id": "2004",
        "name": "Charlie Davis",
        "email": "charlie.davis@company.com",
        "location": "Sydney Office",
        "laptop_model": "Microsoft Surface Laptop 4",
        "laptop_serial_number": "PQR123456",
        "purchase_date": "2023-04-18",
        "warranty_expiry": "2026-04-18",
        "warranty_status": "Active",
    },
    "tchughesiv@gmail.com": {
        "employee_id": "3001",
        "name": "Tommy Hughes",
        "email": "tchughesiv@gmail.com",
        "location": "New Orleans - Remote",
        "laptop_model": "MacBook Pro 16-inch",
        "laptop_serial_number": "TCH789012",
        "purchase_date": "2021-01-10",
        "warranty_expiry": "2024-01-10",
        "warranty_status": "Expired",
    },
    "midawson@redhat.com": {
        "employee_id": "3002",
        "name": "Michael Dawson",
        "email": "midawson@redhat.com",
        "location": "NA",
        "laptop_model": "MacBook Pro 16-inch",
        "laptop_serial_number": "TCH789111",
        "purchase_date": "2022-01-10",
        "warranty_expiry": "2025-01-10",
        "warranty_status": "Expired",
    },
}


def find_employee_by_authoritative_user_id(authoritative_user_id: str) -> dict:
    """Find employee by email from authoritative user ID. Currently only
       email is supported for authoritative user id

    Args:
        authoritative_user_id: the authoritative user id

    Returns:
        Employee data dictionary if found

    Raises:
        ValueError: If email is not found or is empty
    """
    if not authoritative_user_id:
        raise ValueError("Authoritative user ID cannot be empty")

    employee_data = MOCK_EMPLOYEE_DATA.get(authoritative_user_id.lower())
    if employee_data:
        return employee_data

    # If not found, provide helpful error message
    available_authoritative_user_ids = list(MOCK_EMPLOYEE_DATA.keys())
    raise ValueError(
        f"Authoritative user ID '{authoritative_user_id}' not found. "
        f"Available authoritative user IDs: {', '.join(available_authoritative_user_ids)}"
    )


def format_laptop_info(employee_data: dict) -> str:
    """Format laptop information for display.

    Args:
        employee_data: Employee data dictionary

    Returns:
        Formatted laptop information string (without employee ID)
    """
    # Calculate laptop age
    laptop_age = _calculate_laptop_age(employee_data["purchase_date"])

    laptop_info = f"""
    Employee Name: {employee_data["name"]}
    Employee Location: {employee_data["location"]}
    Laptop Model: {employee_data["laptop_model"]}
    Laptop Serial Number: {employee_data["laptop_serial_number"]}
    Laptop Purchase Date: {employee_data["purchase_date"]}
    Laptop Age: {laptop_age}
    Laptop Warranty Expiry Date: {employee_data["warranty_expiry"]}
    Laptop Warranty: {employee_data["warranty_status"]}
    """

    return laptop_info
