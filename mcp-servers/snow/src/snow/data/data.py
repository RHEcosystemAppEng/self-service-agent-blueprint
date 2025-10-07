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


# Build employee data by ID for efficient lookup
MOCK_EMPLOYEE_DATA = {
    "1001": {
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
    "1002": {
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
    "1003": {
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
    "1004": {
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
    "1005": {
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
    "1006": {
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
    "1007": {
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
    "1008": {
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
    "1009": {
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
    "1010": {
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
    "2001": {
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
    "2002": {
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
    "2003": {
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
    "2004": {
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
}

# Email to employee ID mapping for O(1) lookup performance
EMAIL_TO_EMPLOYEE_ID = {
    emp_data["email"].lower(): emp_id for emp_id, emp_data in MOCK_EMPLOYEE_DATA.items()
}


def find_employee_by_id_or_email(identifier: str) -> dict:
    """Find employee by either employee ID or email address.

    Uses O(1) hash table lookups for both employee ID and email address.

    Args:
        identifier: Either employee ID (e.g., '1001') or email address (e.g., 'alice.johnson@company.com')

    Returns:
        Employee data dictionary if found

    Raises:
        ValueError: If identifier is not found
    """
    if not identifier:
        raise ValueError("Employee identifier cannot be empty")

    # First try direct lookup by employee ID - O(1)
    employee_data = MOCK_EMPLOYEE_DATA.get(identifier)
    if employee_data:
        return employee_data

    # If not found by ID, try lookup by email using the mapping - O(1)
    employee_id = EMAIL_TO_EMPLOYEE_ID.get(identifier.lower())
    if employee_id:
        return MOCK_EMPLOYEE_DATA[employee_id]

    # If still not found, provide helpful error message
    available_ids = list(MOCK_EMPLOYEE_DATA.keys())
    available_emails = list(EMAIL_TO_EMPLOYEE_ID.keys())
    raise ValueError(
        f"Employee identifier '{identifier}' not found. "
        f"Available IDs: {', '.join(available_ids)} or "
        f"Available emails: {', '.join(available_emails)}"
    )


def format_laptop_info(employee_data: dict, include_employee_id: bool = True) -> str:
    """Format laptop information for display.

    Args:
        employee_data: Employee data dictionary
        include_employee_id: Whether to include employee ID in output

    Returns:
        Formatted laptop information string
    """
    # Calculate laptop age
    laptop_age = _calculate_laptop_age(employee_data["purchase_date"])

    # Build laptop info, conditionally including employee ID
    if include_employee_id:
        laptop_info = f"""
    Employee Name: {employee_data["name"]}
    Employee ID: {employee_data["employee_id"]}
    Employee Location: {employee_data["location"]}
    Laptop Model: {employee_data["laptop_model"]}
    Laptop Serial Number: {employee_data["laptop_serial_number"]}
    Laptop Purchase Date: {employee_data["purchase_date"]}
    Laptop Age: {laptop_age}
    Laptop Warranty Expiry Date: {employee_data["warranty_expiry"]}
    Laptop Warranty: {employee_data["warranty_status"]}
    """
    else:
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
