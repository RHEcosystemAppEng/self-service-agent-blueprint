"""Employee data for the MCP server."""

MOCK_EMPLOYEE_DATA = {
    "emp001": {
        "employee_id": "emp001",
        "name": "Alice Johnson",
        "department": "Engineering",
        "email": "alice.johnson@company.com",
        "laptop": {
            "brand": "Dell",
            "model": "Latitude 7420",
            "serial_number": "DL7420001",
            "assignment_date": "2020-01-15",
            "warranty_expiry": "2023-01-15",
            "warranty_status": "Expired",
            "specs": {
                "cpu": "Intel Core i7-1165G7",
                "ram": "16GB DDR4",
                "storage": "512GB SSD",
                "display": "14-inch FHD",
            },
        },
        "it_contact": {
            "name": "Bob Smith",
            "email": "bob.smith@company.com",
            "phone": "+1-555-0123",
        },
    },
    "emp002": {
        "employee_id": "emp002",
        "name": "John Doe",
        "department": "Marketing",
        "email": "john.doe@company.com",
        "laptop": {
            "brand": "Apple",
            "model": "MacBook Pro 14-inch",
            "serial_number": "MBP14002",
            "assignment_date": "2023-03-20",
            "warranty_expiry": "2026-03-20",
            "warranty_status": "Active",
            "specs": {
                "cpu": "Apple M2 Pro",
                "ram": "16GB Unified Memory",
                "storage": "512GB SSD",
                "display": "14.2-inch Liquid Retina XDR",
            },
        },
        "it_contact": {
            "name": "Sarah Wilson",
            "email": "sarah.wilson@company.com",
            "phone": "+1-555-0456",
        },
    },
    "emp003": {
        "employee_id": "emp003",
        "name": "Maria Garcia",
        "department": "Finance",
        "email": "maria.garcia@company.com",
        "laptop": {
            "brand": "Lenovo",
            "model": "ThinkPad X1 Carbon",
            "serial_number": "TP1C003",
            "assignment_date": "2022-11-10",
            "warranty_expiry": "2025-11-10",
            "warranty_status": "Active",
            "specs": {
                "cpu": "Intel Core i5-1135G7",
                "ram": "8GB DDR4",
                "storage": "256GB SSD",
                "display": "14-inch FHD",
            },
        },
        "it_contact": {
            "name": "Mike Johnson",
            "email": "mike.johnson@company.com",
            "phone": "+1-555-0789",
        },
    },
}
