#!/usr/bin/env python3
"""ServiceNow MCP Server - Submit and check laptop request status."""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List
from dataclasses import dataclass, asdict
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
class LaptopRequest:
    request_id: str
    employee_id: str
    employee_name: str
    employee_email: str
    request_type: str  # "new", "replacement", "upgrade"
    laptop_preference: str
    justification: str
    status: str  # "submitted", "approved", "rejected", "in_progress", "completed"
    created_date: str
    updated_date: str
    notes: List[str]

# Dummy ServiceNow requests database
REQUESTS_DB = {
    "REQ001": LaptopRequest(
        request_id="REQ001",
        employee_id="EMP001",
        employee_name="John Doe",
        employee_email="john.doe@company.com",
        request_type="replacement",
        laptop_preference="Dell Latitude 7430",
        justification="Current laptop is 3 years old and experiencing performance issues",
        status="approved",
        created_date="2024-07-28",
        updated_date="2024-07-30",
        notes=["Request approved by manager", "IT procurement in progress"]
    ),
    "REQ002": LaptopRequest(
        request_id="REQ002",
        employee_id="EMP002",
        employee_name="Jane Smith",
        employee_email="jane.smith@company.com",
        request_type="upgrade",
        laptop_preference="MacBook Pro 16-inch M3",
        justification="Need more processing power for video editing work",
        status="in_progress",
        created_date="2024-08-01",
        updated_date="2024-08-02",
        notes=["Budget approval required", "Waiting for manager approval"]
    ),
    "REQ003": LaptopRequest(
        request_id="REQ003",
        employee_id="EMP004",
        employee_name="Alice Brown",
        employee_email="alice.brown@company.com",
        request_type="new",
        laptop_preference="HP EliteBook 850 G10",
        justification="New hire equipment setup",
        status="completed",
        created_date="2024-07-20",
        updated_date="2024-07-25",
        notes=["Equipment delivered", "Setup completed by IT"]
    )
}

# Health check server
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "healthy", "service": "servicenow"}')
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
server = Server("servicenow")

@server.list_tools()
async def handle_list_tools() -> List[types.Tool]:
    """List available tools for ServiceNow laptop requests."""
    return [
        types.Tool(
            name="submit_laptop_request",
            description="Submit a new laptop request to ServiceNow",
            inputSchema={
                "type": "object",
                "properties": {
                    "employee_id": {
                        "type": "string",
                        "description": "Employee ID"
                    },
                    "employee_name": {
                        "type": "string",
                        "description": "Employee full name"
                    },
                    "employee_email": {
                        "type": "string",
                        "description": "Employee email address"
                    },
                    "request_type": {
                        "type": "string",
                        "enum": ["new", "replacement", "upgrade"],
                        "description": "Type of laptop request"
                    },
                    "laptop_preference": {
                        "type": "string",
                        "description": "Preferred laptop model/brand"
                    },
                    "justification": {
                        "type": "string",
                        "description": "Business justification for the request"
                    }
                },
                "required": ["employee_id", "employee_name", "employee_email", "request_type", "laptop_preference", "justification"]
            }
        ),
        types.Tool(
            name="check_request_status",
            description="Check the status of a laptop request",
            inputSchema={
                "type": "object",
                "properties": {
                    "request_id": {
                        "type": "string",
                        "description": "Request ID (e.g., REQ001)"
                    },
                    "employee_id": {
                        "type": "string",
                        "description": "Employee ID to search requests for"
                    }
                },
                "anyOf": [
                    {"required": ["request_id"]},
                    {"required": ["employee_id"]}
                ]
            }
        ),
        types.Tool(
            name="list_all_requests",
            description="List all laptop requests with optional status filter",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["submitted", "approved", "rejected", "in_progress", "completed"],
                        "description": "Filter by request status (optional)"
                    },
                    "employee_id": {
                        "type": "string",
                        "description": "Filter by employee ID (optional)"
                    }
                }
            }
        ),
        types.Tool(
            name="update_request_status",
            description="Update the status of a laptop request (admin function)",
            inputSchema={
                "type": "object",
                "properties": {
                    "request_id": {
                        "type": "string",
                        "description": "Request ID to update"
                    },
                    "new_status": {
                        "type": "string",
                        "enum": ["submitted", "approved", "rejected", "in_progress", "completed"],
                        "description": "New status for the request"
                    },
                    "note": {
                        "type": "string",
                        "description": "Note to add to the request"
                    }
                },
                "required": ["request_id", "new_status"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> List[types.TextContent]:
    """Handle tool calls for ServiceNow laptop requests."""
    
    if name == "submit_laptop_request":
        return await submit_laptop_request(arguments)
    elif name == "check_request_status":
        return await check_request_status(arguments)
    elif name == "list_all_requests":
        return await list_all_requests(arguments)
    elif name == "update_request_status":
        return await update_request_status(arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")

async def submit_laptop_request(arguments: dict) -> List[types.TextContent]:
    """Submit a new laptop request to ServiceNow."""
    
    # Generate a new request ID
    request_id = f"REQ{str(uuid.uuid4())[:3].upper()}"
    
    # Ensure unique request ID
    while request_id in REQUESTS_DB:
        request_id = f"REQ{str(uuid.uuid4())[:3].upper()}"
    
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    new_request = LaptopRequest(
        request_id=request_id,
        employee_id=arguments["employee_id"],
        employee_name=arguments["employee_name"],
        employee_email=arguments["employee_email"],
        request_type=arguments["request_type"],
        laptop_preference=arguments["laptop_preference"],
        justification=arguments["justification"],
        status="submitted",
        created_date=current_date,
        updated_date=current_date,
        notes=["Request submitted successfully"]
    )
    
    # Add to database
    REQUESTS_DB[request_id] = new_request
    
    result = {
        "success": True,
        "message": "Laptop request submitted successfully",
        "request_id": request_id,
        "status": "submitted",
        "created_date": current_date,
        "next_steps": "Your request will be reviewed by your manager and IT team"
    }
    
    return [types.TextContent(
        type="text",
        text=json.dumps(result, indent=2)
    )]

async def check_request_status(arguments: dict) -> List[types.TextContent]:
    """Check the status of a laptop request."""
    request_id = arguments.get("request_id")
    employee_id = arguments.get("employee_id")
    
    if request_id:
        request = REQUESTS_DB.get(request_id)
        if not request:
            return [types.TextContent(
                type="text",
                text=f"Request {request_id} not found. Available request IDs: {', '.join(REQUESTS_DB.keys())}"
            )]
        
        result = asdict(request)
        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    elif employee_id:
        # Find all requests for the employee
        employee_requests = []
        for request in REQUESTS_DB.values():
            if request.employee_id == employee_id:
                employee_requests.append(asdict(request))
        
        if not employee_requests:
            return [types.TextContent(
                type="text",
                text=f"No requests found for employee {employee_id}"
            )]
        
        result = {
            "employee_id": employee_id,
            "total_requests": len(employee_requests),
            "requests": employee_requests
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    else:
        return [types.TextContent(
            type="text",
            text="Please provide either request_id or employee_id"
        )]

async def list_all_requests(arguments: dict) -> List[types.TextContent]:
    """List all laptop requests with optional filters."""
    status_filter = arguments.get("status")
    employee_filter = arguments.get("employee_id")
    
    filtered_requests = []
    
    for request in REQUESTS_DB.values():
        # Apply status filter
        if status_filter and request.status != status_filter:
            continue
        
        # Apply employee filter
        if employee_filter and request.employee_id != employee_filter:
            continue
        
        filtered_requests.append(asdict(request))
    
    result = {
        "total_requests": len(filtered_requests),
        "filters_applied": {
            "status": status_filter,
            "employee_id": employee_filter
        },
        "requests": filtered_requests
    }
    
    return [types.TextContent(
        type="text",
        text=json.dumps(result, indent=2)
    )]

async def update_request_status(arguments: dict) -> List[types.TextContent]:
    """Update the status of a laptop request."""
    request_id = arguments["request_id"]
    new_status = arguments["new_status"]
    note = arguments.get("note", f"Status updated to {new_status}")
    
    request = REQUESTS_DB.get(request_id)
    if not request:
        return [types.TextContent(
            type="text",
            text=f"Request {request_id} not found. Available request IDs: {', '.join(REQUESTS_DB.keys())}"
        )]
    
    # Update the request
    old_status = request.status
    request.status = new_status
    request.updated_date = datetime.now().strftime("%Y-%m-%d")
    request.notes.append(note)
    
    result = {
        "success": True,
        "message": f"Request {request_id} status updated",
        "request_id": request_id,
        "old_status": old_status,
        "new_status": new_status,
        "updated_date": request.updated_date,
        "note_added": note
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
        server_name="servicenow",
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