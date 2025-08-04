#!/usr/bin/env python3
"""Employee Info MCP Server - Returns laptop age information for employees."""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
from dataclasses import dataclass
from mcp.server import Server
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class Employee:
    employee_id: str
    name: str
    email: str
    department: str
    laptop_brand: str
    laptop_model: str
    purchase_date: str
    laptop_age_days: int

# Dummy employee data
EMPLOYEES_DB = {
    "EMP001": Employee(
        employee_id="EMP001",
        name="John Doe",
        email="john.doe@company.com",
        department="Engineering",
        laptop_brand="Dell",
        laptop_model="Latitude 7420",
        purchase_date="2022-03-15",
        laptop_age_days=682
    ),
    "EMP002": Employee(
        employee_id="EMP002",
        name="Jane Smith",
        email="jane.smith@company.com",
        department="Marketing",
        laptop_brand="MacBook",
        laptop_model="MacBook Pro 14-inch",
        purchase_date="2021-11-20",
        laptop_age_days=797
    ),
    "EMP003": Employee(
        employee_id="EMP003",
        name="Bob Johnson",
        email="bob.johnson@company.com",
        department="Sales",
        laptop_brand="Lenovo",
        laptop_model="ThinkPad X1 Carbon",
        purchase_date="2023-01-10",
        laptop_age_days=390
    ),
    "EMP004": Employee(
        employee_id="EMP004",
        name="Alice Brown",
        email="alice.brown@company.com",
        department="HR",
        laptop_brand="HP",
        laptop_model="EliteBook 840 G9",
        purchase_date="2020-08-05",
        laptop_age_days=1278
    ),
}

# Health check server
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "healthy", "service": "employee-info"}')
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress default HTTP server logging
        pass

def start_health_server():
    """Start health check server in background."""
    health_server = HTTPServer(('0.0.0.0', 8000), HealthHandler)
    health_thread = threading.Thread(target=health_server.serve_forever, daemon=True)
    health_thread.start()
    logger.info("Health server started on port 8000")

# Create the server
server = Server("employee-info")

@server.list_tools()
async def handle_list_tools() -> List[types.Tool]:
    """List available tools for employee information lookup."""
    return [
        types.Tool(
            name="lookup_employee_info",
            description="Look up employee information including laptop age",
            inputSchema={
                "type": "object",
                "properties": {
                    "employee_id": {
                        "type": "string",
                        "description": "Employee ID (e.g., EMP001)"
                    },
                    "email": {
                        "type": "string",
                        "description": "Employee email address"
                    }
                },
                "anyOf": [
                    {"required": ["employee_id"]},
                    {"required": ["email"]}
                ]
            }
        ),
        types.Tool(
            name="get_laptop_age",
            description="Get laptop age information for a specific employee",
            inputSchema={
                "type": "object",
                "properties": {
                    "employee_id": {
                        "type": "string",
                        "description": "Employee ID (e.g., EMP001)"
                    }
                },
                "required": ["employee_id"]
            }
        ),
        types.Tool(
            name="list_employees_with_old_laptops",
            description="List employees with laptops older than specified days",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_age_days": {
                        "type": "integer",
                        "description": "Maximum laptop age in days (default: 730 days / 2 years)",
                        "default": 730
                    }
                }
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> List[types.TextContent]:
    """Handle tool calls for employee information lookup."""
    
    if name == "lookup_employee_info":
        return await lookup_employee_info(arguments)
    elif name == "get_laptop_age":
        return await get_laptop_age(arguments)
    elif name == "list_employees_with_old_laptops":
        return await list_employees_with_old_laptops(arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")

async def lookup_employee_info(arguments: dict) -> List[types.TextContent]:
    """Look up employee information by ID or email."""
    employee_id = arguments.get("employee_id")
    email = arguments.get("email")
    
    employee = None
    
    if employee_id:
        employee = EMPLOYEES_DB.get(employee_id)
    elif email:
        # Search by email
        for emp in EMPLOYEES_DB.values():
            if emp.email.lower() == email.lower():
                employee = emp
                break
    
    if not employee:
        return [types.TextContent(
            type="text",
            text=f"Employee not found. Available employee IDs: {', '.join(EMPLOYEES_DB.keys())}"
        )]
    
    # Calculate current laptop age
    purchase_date = datetime.strptime(employee.purchase_date, "%Y-%m-%d")
    current_age = (datetime.now() - purchase_date).days
    
    result = {
        "employee_id": employee.employee_id,
        "name": employee.name,
        "email": employee.email,
        "department": employee.department,
        "laptop_info": {
            "brand": employee.laptop_brand,
            "model": employee.laptop_model,
            "purchase_date": employee.purchase_date,
            "age_days": current_age,
            "age_years": round(current_age / 365.25, 1)
        }
    }
    
    return [types.TextContent(
        type="text",
        text=json.dumps(result, indent=2)
    )]

async def get_laptop_age(arguments: dict) -> List[types.TextContent]:
    """Get laptop age information for a specific employee."""
    employee_id = arguments.get("employee_id")
    
    employee = EMPLOYEES_DB.get(employee_id)
    if not employee:
        return [types.TextContent(
            type="text",
            text=f"Employee {employee_id} not found. Available employee IDs: {', '.join(EMPLOYEES_DB.keys())}"
        )]
    
    # Calculate current laptop age
    purchase_date = datetime.strptime(employee.purchase_date, "%Y-%m-%d")
    current_age = (datetime.now() - purchase_date).days
    
    result = {
        "employee_id": employee.employee_id,
        "name": employee.name,
        "laptop_age": {
            "days": current_age,
            "years": round(current_age / 365.25, 1),
            "purchase_date": employee.purchase_date,
            "laptop": f"{employee.laptop_brand} {employee.laptop_model}"
        }
    }
    
    return [types.TextContent(
        type="text",
        text=json.dumps(result, indent=2)
    )]

async def list_employees_with_old_laptops(arguments: dict) -> List[types.TextContent]:
    """List employees with laptops older than specified days."""
    max_age_days = arguments.get("max_age_days", 730)  # Default 2 years
    
    old_laptops = []
    
    for employee in EMPLOYEES_DB.values():
        purchase_date = datetime.strptime(employee.purchase_date, "%Y-%m-%d")
        current_age = (datetime.now() - purchase_date).days
        
        if current_age > max_age_days:
            old_laptops.append({
                "employee_id": employee.employee_id,
                "name": employee.name,
                "department": employee.department,
                "laptop": f"{employee.laptop_brand} {employee.laptop_model}",
                "age_days": current_age,
                "age_years": round(current_age / 365.25, 1),
                "purchase_date": employee.purchase_date
            })
    
    result = {
        "threshold_days": max_age_days,
        "threshold_years": round(max_age_days / 365.25, 1),
        "employees_with_old_laptops": old_laptops,
        "count": len(old_laptops)
    }
    
    return [types.TextContent(
        type="text",
        text=json.dumps(result, indent=2)
    )]

async def main():
    """Main entry point for the MCP server."""
    # Start health check server
    start_health_server()
    
    options = InitializationOptions(
        server_name="employee-info",
        server_version="1.0.0",
        capabilities=types.ServerCapabilities(
            tools=types.ToolsCapability()
        )
    )
    
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            options
        )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())