"""Mock employee data for testing purposes."""

import os
import random
from datetime import datetime, timedelta
from typing import Any, Dict

MOCK_EMPLOYEE_DATA = {
    "alice.johnson@company.com": {
        "employee_id": "1001",
        "sys_id": "1001",
        "name": "Alice Johnson",
        "email": "alice.johnson@company.com",
        "user_name": "alice.johnson",
        "location": "EMEA",
        "active": "true",
        "laptop_model": "Latitude 7420",
        "laptop_serial_number": "DL7420001",
        "purchase_date": "2020-01-15",
        "warranty_expiry": "2023-01-15",
        "warranty_status": "Expired",
        "asset_tag": "ASSET-001",
        "model_id": "latitude_7420",
        "install_status": "1",
        "operational_status": "1",
    },
    "john.doe@company.com": {
        "employee_id": "1002",
        "sys_id": "1002",
        "name": "John Doe",
        "email": "john.doe@company.com",
        "user_name": "john.doe",
        "location": "EMEA",
        "active": "true",
        "laptop_model": "MacBook Pro 14-inch",
        "laptop_serial_number": "MBP14002",
        "purchase_date": "2023-03-20",
        "warranty_expiry": "2026-03-20",
        "warranty_status": "Active",
        "asset_tag": "ASSET-002",
        "model_id": "macbook_pro_14",
        "install_status": "1",
        "operational_status": "1",
    },
    "maria.garcia@company.com": {
        "employee_id": "1003",
        "sys_id": "1003",
        "name": "Maria Garcia",
        "email": "maria.garcia@company.com",
        "user_name": "maria.garcia",
        "location": "LATAM",
        "active": "true",
        "laptop_model": "ThinkPad X1 Carbon",
        "laptop_serial_number": "TP1C003",
        "purchase_date": "2022-11-10",
        "warranty_expiry": "2025-11-10",
        "warranty_status": "Active",
        "asset_tag": "ASSET-003",
        "model_id": "thinkpad_x1_carbon",
        "install_status": "1",
        "operational_status": "1",
    },
    "oliver.smith@company.com": {
        "employee_id": "1004",
        "sys_id": "1004",
        "name": "Oliver Smith",
        "email": "oliver.smith@company.com",
        "user_name": "oliver.smith",
        "location": "EMEA",
        "active": "true",
        "laptop_model": "EliteBook 840 G7",
        "laptop_serial_number": "HP840004",
        "purchase_date": "2019-05-12",
        "warranty_expiry": "2022-05-12",
        "warranty_status": "Expired",
        "asset_tag": "ASSET-004",
        "model_id": "elitebook_840_g7",
        "install_status": "1",
        "operational_status": "1",
    },
    "yuki.tanaka@company.com": {
        "employee_id": "1005",
        "sys_id": "1005",
        "name": "Yuki Tanaka",
        "email": "yuki.tanaka@company.com",
        "user_name": "yuki.tanaka",
        "location": "APAC",
        "active": "true",
        "laptop_model": "XPS 13 9310",
        "laptop_serial_number": "DL13005",
        "purchase_date": "2018-09-03",
        "warranty_expiry": "2021-09-03",
        "warranty_status": "Expired",
        "asset_tag": "ASSET-005",
        "model_id": "xps_13_9310",
        "install_status": "1",
        "operational_status": "1",
    },
    "isabella.mueller@company.com": {
        "employee_id": "1006",
        "sys_id": "1006",
        "name": "Isabella Mueller",
        "email": "isabella.mueller@company.com",
        "user_name": "isabella.mueller",
        "location": "EMEA",
        "active": "true",
        "laptop_model": "ThinkPad T14",
        "laptop_serial_number": "TP14006",
        "purchase_date": "2019-11-18",
        "warranty_expiry": "2022-11-18",
        "warranty_status": "Expired",
        "asset_tag": "ASSET-006",
        "model_id": "thinkpad_t14",
        "install_status": "1",
        "operational_status": "1",
    },
    "carlos.rodriguez@company.com": {
        "employee_id": "1007",
        "sys_id": "1007",
        "name": "Carlos Rodriguez",
        "email": "carlos.rodriguez@company.com",
        "user_name": "carlos.rodriguez",
        "location": "LATAM",
        "active": "true",
        "laptop_model": "MacBook Air M1",
        "laptop_serial_number": "MBA1007",
        "purchase_date": "2021-02-14",
        "warranty_expiry": "2024-02-14",
        "warranty_status": "Active",
        "asset_tag": "ASSET-007",
        "model_id": "macbook_air_m1",
        "install_status": "1",
        "operational_status": "1",
    },
    "david.chen@company.com": {
        "employee_id": "1008",
        "sys_id": "1008",
        "name": "David Chen",
        "email": "david.chen@company.com",
        "user_name": "david.chen",
        "location": "APAC",
        "active": "true",
        "laptop_model": "ZenBook Pro 15",
        "laptop_serial_number": "AS15008",
        "purchase_date": "2020-07-22",
        "warranty_expiry": "2023-07-22",
        "warranty_status": "Expired",
        "asset_tag": "ASSET-008",
        "model_id": "zenbook_pro_15",
        "install_status": "1",
        "operational_status": "1",
    },
    "sophie.dubois@company.com": {
        "employee_id": "1009",
        "sys_id": "1009",
        "name": "Sophie Dubois",
        "email": "sophie.dubois@company.com",
        "user_name": "sophie.dubois",
        "location": "EMEA",
        "active": "true",
        "laptop_model": "Surface Laptop 4",
        "laptop_serial_number": "MS4009",
        "purchase_date": "2021-08-05",
        "warranty_expiry": "2024-08-05",
        "warranty_status": "Active",
        "asset_tag": "ASSET-009",
        "model_id": "surface_laptop_4",
        "install_status": "1",
        "operational_status": "1",
    },
    "ahmed.hassan@company.com": {
        "employee_id": "1010",
        "sys_id": "1010",
        "name": "Ahmed Hassan",
        "email": "ahmed.hassan@company.com",
        "user_name": "ahmed.hassan",
        "location": "EMEA",
        "active": "true",
        "laptop_model": "Inspiron 15 5000",
        "laptop_serial_number": "DL15010",
        "purchase_date": "2018-03-14",
        "warranty_expiry": "2021-03-14",
        "warranty_status": "Expired",
        "asset_tag": "ASSET-010",
        "model_id": "inspiron_15_5000",
        "install_status": "1",
        "operational_status": "1",
    },
    "jane.smith@company.com": {
        "employee_id": "2001",
        "sys_id": "2001",
        "name": "Jane Smith",
        "email": "jane.smith@company.com",
        "user_name": "jane.smith",
        "location": "San Francisco Office",
        "active": "true",
        "laptop_model": "MacBook Pro 16-inch",
        "laptop_serial_number": "DEF789012",
        "purchase_date": "2023-01-10",
        "warranty_expiry": "2026-01-10",
        "warranty_status": "Active",
        "asset_tag": "ASSET-011",
        "model_id": "macbook_pro_16",
        "install_status": "1",
        "operational_status": "1",
    },
    "bob.wilson@company.com": {
        "employee_id": "2002",
        "sys_id": "2002",
        "name": "Bob Wilson",
        "email": "bob.wilson@company.com",
        "user_name": "bob.wilson",
        "location": "London Office",
        "active": "true",
        "laptop_model": "HP EliteBook 850",
        "laptop_serial_number": "JKL901234",
        "purchase_date": "2023-09-05",
        "warranty_expiry": "2026-09-05",
        "warranty_status": "Active",
        "asset_tag": "ASSET-012",
        "model_id": "elitebook_850",
        "install_status": "1",
        "operational_status": "1",
    },
    "alice.brown@company.com": {
        "employee_id": "2003",
        "sys_id": "2003",
        "name": "Alice Brown",
        "email": "alice.brown@company.com",
        "user_name": "alice.brown",
        "location": "Tokyo Office",
        "active": "true",
        "laptop_model": "Lenovo ThinkPad X1 Carbon",
        "laptop_serial_number": "MNO567890",
        "purchase_date": "2022-11-12",
        "warranty_expiry": "2025-11-12",
        "warranty_status": "Active",
        "asset_tag": "ASSET-013",
        "model_id": "thinkpad_x1_carbon",
        "install_status": "1",
        "operational_status": "1",
    },
    "charlie.davis@company.com": {
        "employee_id": "2004",
        "sys_id": "2004",
        "name": "Charlie Davis",
        "email": "charlie.davis@company.com",
        "user_name": "charlie.davis",
        "location": "Sydney Office",
        "active": "true",
        "laptop_model": "Microsoft Surface Laptop 4",
        "laptop_serial_number": "PQR123456",
        "purchase_date": "2023-04-18",
        "warranty_expiry": "2026-04-18",
        "warranty_status": "Active",
        "asset_tag": "ASSET-014",
        "model_id": "surface_laptop_4",
        "install_status": "1",
        "operational_status": "1",
    },
    "tchughesiv@gmail.com": {
        "employee_id": "3001",
        "sys_id": "3001",
        "name": "Tommy Hughes",
        "email": "tchughesiv@gmail.com",
        "user_name": "tommy.hughes",
        "location": "New Orleans - Remote",
        "active": "true",
        "laptop_model": "MacBook Pro 16-inch",
        "laptop_serial_number": "TCH789012",
        "purchase_date": "2021-01-10",
        "warranty_expiry": "2024-01-10",
        "warranty_status": "Expired",
        "asset_tag": "ASSET-015",
        "model_id": "macbook_pro_16",
        "install_status": "1",
        "operational_status": "1",
    },
}


def _generate_user_data_for_email(email: str, employee_id: int) -> Dict[str, Any]:
    """Generate user data for a TEST_USERS email.

    Args:
        email: Email address to generate data for
        employee_id: Unique employee ID to use

    Returns:
        Dictionary containing employee and laptop information
    """
    # Extract username from email (part before @)
    username = email.split("@")[0]
    name = username  # Use username directly as name

    # Generate sys_id starting from 9000 to avoid conflicts with existing data
    sys_id = str(9000 + employee_id)

    # Use static values for simplicity
    location = "Remote"
    laptop_model = "MacBook Pro 16-inch"
    model_id = "macbook_pro_16"

    # Generate dates
    purchase_date_obj = datetime.now() - timedelta(
        days=random.randint(365, 1095)
    )  # 1-3 years ago
    purchase_date = purchase_date_obj.strftime("%Y-%m-%d")
    warranty_expiry_obj = purchase_date_obj + timedelta(days=1095)  # 3 years warranty
    warranty_expiry = warranty_expiry_obj.strftime("%Y-%m-%d")
    warranty_status = "Active" if datetime.now() < warranty_expiry_obj else "Expired"

    # Generate serial numbers
    laptop_serial = f"TEST{employee_id:04d}"
    asset_tag = f"ASSET-TEST-{employee_id:03d}"

    return {
        "employee_id": str(employee_id),
        "sys_id": sys_id,
        "name": name,
        "email": email,
        "user_name": username,
        "location": location,
        "active": "true",
        "laptop_model": laptop_model,
        "laptop_serial_number": laptop_serial,
        "purchase_date": purchase_date,
        "warranty_expiry": warranty_expiry,
        "warranty_status": warranty_status,
        "asset_tag": asset_tag,
        "model_id": model_id,
        "install_status": "1",
        "operational_status": "1",
    }


def get_employee_data() -> Dict[str, Dict[str, Any]]:
    """Get employee data, optionally augmented with TEST_USERS.

    Returns:
        Dictionary of employee data, possibly extended with TEST_USERS
    """
    # Start with base mock data
    result = MOCK_EMPLOYEE_DATA.copy()

    # Check for TEST_USERS environment variable
    test_users_env = os.getenv("TEST_USERS")
    if not test_users_env:
        return result

    # Parse comma-separated emails
    test_emails = [
        email.strip() for email in test_users_env.split(",") if email.strip()
    ]
    if not test_emails:
        return result

    # Generate data for TEST_USERS emails
    for idx, email in enumerate(test_emails):
        # Skip if email already exists in MOCK_EMPLOYEE_DATA
        if email.lower() in result:
            continue

        # Generate unique employee_id starting from 9001
        employee_id = 9001 + idx
        user_data = _generate_user_data_for_email(email, employee_id)
        result[email.lower()] = user_data

    return result
