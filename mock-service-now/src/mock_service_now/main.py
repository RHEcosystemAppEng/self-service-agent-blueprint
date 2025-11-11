"""Mock ServiceNow API service for testing and CI environments."""

import base64
import os
import uuid
from typing import Any, Dict

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from shared_models import configure_logging, simple_health_check
from tracing_config.auto_tracing import run as auto_tracing_run
from tracing_config.auto_tracing import tracingIsActive

# Configure structured logging and auto tracing
SERVICE_NAME = "mock-service-now"
logger = configure_logging(SERVICE_NAME)
auto_tracing_run(SERVICE_NAME, logger)


class MockServiceNowAPI:
    """Mock ServiceNow API that mimics real ServiceNow behavior and responses."""

    def __init__(self):
        """Initialize the mock ServiceNow API with realistic data."""
        self._init_mock_data()

    def _init_mock_data(self):
        """Initialize mock data that matches ServiceNow structure."""
        # Convert existing mock data to ServiceNow format
        self.mock_users = {}
        self.mock_computers = {}

        # Mock employee data adapted to ServiceNow format
        mock_employee_data = {
            "alice.johnson@company.com": {
                "employee_id": "1001",
                "name": "Alice Johnson",
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
                "location": "LATAM",
                "laptop_model": "ThinkPad X1 Carbon",
                "laptop_serial_number": "TP1C003",
                "purchase_date": "2022-11-10",
                "warranty_expiry": "2025-11-10",
                "warranty_status": "Active",
            },
            "midawson@redhat.com": {
                "employee_id": "3002",
                "name": "Michael Dawson",
                "location": "NA",
                "laptop_model": "MacBook Pro 16-inch",
                "laptop_serial_number": "TCH789111",
                "purchase_date": "2022-01-10",
                "warranty_expiry": "2025-01-10",
                "warranty_status": "Expired",
            },
        }

        # Generate ServiceNow-format data
        for email, employee_data in mock_employee_data.items():
            user_sys_id = self._generate_sys_id()
            computer_sys_id = self._generate_sys_id()

            # Create ServiceNow-format user record
            self.mock_users[user_sys_id] = {
                "sys_id": user_sys_id,
                "name": employee_data["name"],
                "email": email,
                "user_name": email.split("@")[0],
                "location": {
                    "value": self._generate_sys_id(),
                    "display_value": employee_data["location"],
                },
                "active": "true",
                "employee_number": employee_data["employee_id"],
            }

            # Create ServiceNow-format computer record
            self.mock_computers[computer_sys_id] = {
                "sys_id": computer_sys_id,
                "name": f"{employee_data['name']}'s {employee_data['laptop_model']}",
                "asset_tag": f"AT{employee_data['laptop_serial_number'][-6:]}",
                "serial_number": employee_data["laptop_serial_number"],
                "model_id": {
                    "value": self._generate_sys_id(),
                    "display_value": employee_data["laptop_model"],
                },
                "assigned_to": {
                    "value": user_sys_id,
                    "display_value": employee_data["name"],
                },
                "purchase_date": employee_data["purchase_date"],
                "warranty_expiration": employee_data["warranty_expiry"],
                "install_status": "Installed",
                "operational_status": "Operational",
            }

        # Create email to sys_id lookup for quick access
        self.email_to_sys_id = {
            user_data["email"]: sys_id for sys_id, user_data in self.mock_users.items()
        }

        logger.info(
            "Initialized mock ServiceNow data",
            users_count=len(self.mock_users),
            computers_count=len(self.mock_computers),
        )

    def _generate_sys_id(self) -> str:
        """Generate a ServiceNow-style sys_id (32-character hex)."""
        return uuid.uuid4().hex

    def handle_sys_user_query(self, query_params: Dict[str, str]) -> Dict[str, Any]:
        """Handle sys_user table queries."""
        query = query_params.get("sysparm_query", "")
        limit = int(query_params.get("sysparm_limit", "10000"))
        fields = query_params.get("sysparm_fields", "")

        logger.info(
            "Processing sys_user query", query=query, limit=limit, fields=fields
        )

        results = []

        # Parse simple email query (e.g., "email=user@example.com")
        if "email=" in query:
            email = query.split("email=")[1].split("^")[
                0
            ]  # Handle potential additional conditions
            user_sys_id = self.email_to_sys_id.get(email)
            if user_sys_id and user_sys_id in self.mock_users:
                user_data = self.mock_users[user_sys_id].copy()

                # Apply field filtering
                if fields:
                    requested_fields = [f.strip() for f in fields.split(",")]
                    user_data = {
                        k: v for k, v in user_data.items() if k in requested_fields
                    }

                results.append(user_data)

        # Limit results
        results = results[:limit]

        logger.info("Returning sys_user results", count=len(results))
        return {"result": results}

    def handle_computer_query(self, query_params: Dict[str, str]) -> Dict[str, Any]:
        """Handle cmdb_ci_computer table queries."""
        query = query_params.get("sysparm_query", "")
        fields = query_params.get("sysparm_fields", "")

        logger.info("Processing cmdb_ci_computer query", query=query, fields=fields)

        results = []

        # Parse assigned_to query (e.g., "assigned_to=user_sys_id")
        if "assigned_to=" in query:
            user_sys_id = query.split("assigned_to=")[1].split("^")[0]

            # Find computers assigned to this user
            for computer_sys_id, computer_data in self.mock_computers.items():
                if (
                    isinstance(computer_data["assigned_to"], dict)
                    and computer_data["assigned_to"]["value"] == user_sys_id
                ):

                    computer_result = computer_data.copy()

                    # Apply field filtering
                    if fields:
                        requested_fields = [f.strip() for f in fields.split(",")]
                        computer_result = {
                            k: v
                            for k, v in computer_result.items()
                            if k in requested_fields
                        }

                    results.append(computer_result)

        logger.info("Returning cmdb_ci_computer results", count=len(results))
        return {"result": results}

    def handle_catalog_order(
        self, item_id: str, body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle service catalog item orders."""
        logger.info("Processing catalog order", item_id=item_id, body=body)

        # Simulate successful order creation
        request_number = f"REQ{uuid.uuid4().hex[-7:].upper()}"
        request_sys_id = self._generate_sys_id()

        # Extract variables from request body
        variables = body.get("variables", {})
        who_is_this_for = variables.get("who_is_this_request_for", "")
        laptop_choice = variables.get("laptop_choices", "")

        # Create realistic ServiceNow order response
        order_result = {
            "request_number": request_number,
            "sys_id": request_sys_id,
            "state": "requested",
            "stage": "waiting_for_approval",
            "requested_for": {
                "value": who_is_this_for,
                "display_value": self._get_user_display_name(who_is_this_for),
            },
            "catalog_item": {"value": item_id, "display_value": "Laptop Refresh"},
            "variables": {
                "laptop_choices": laptop_choice,
                "who_is_this_request_for": who_is_this_for,
            },
            "order_now": True,
            "quantity": body.get("sysparm_quantity", 1),
        }

        logger.info(
            "Created catalog order",
            request_number=request_number,
            sys_id=request_sys_id,
        )
        return {"result": order_result}

    def _get_user_display_name(self, user_sys_id: str) -> str:
        """Get display name for a user sys_id."""
        if user_sys_id in self.mock_users:
            return self.mock_users[user_sys_id]["name"]
        return "Unknown User"


# Initialize the mock API
mock_api = MockServiceNowAPI()

# Create FastAPI application
app = FastAPI(
    title="Mock ServiceNow API",
    description="Mock ServiceNow API service that mimics real ServiceNow behavior for testing and CI",
    version="0.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Middleware to simulate ServiceNow authentication."""
    # Skip auth check for health endpoint
    if request.url.path == "/health":
        return await call_next(request)

    # Check for authentication headers
    auth_header = request.headers.get("Authorization")
    api_key_header = request.headers.get("X-ServiceNow-API-Key")

    if not auth_header and not api_key_header:
        logger.warning("Authentication required but not provided")
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "error": {
                    "message": "User Not Authenticated",
                    "detail": "Required to provide Auth information",
                },
                "status": "failure",
            },
        )

    # Basic auth validation (simplified)
    if auth_header and auth_header.startswith("Basic "):
        try:
            encoded = auth_header.split(" ")[1]
            decoded = base64.b64decode(encoded).decode()
            username, password = decoded.split(":", 1)
            logger.info("Mock auth successful", username=username)
        except Exception as e:
            logger.error("Invalid authentication", error=str(e))
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": {
                        "message": "Invalid Authentication",
                        "detail": "Invalid credentials provided",
                    },
                    "status": "failure",
                },
            )

    return await call_next(request)


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    return await simple_health_check(
        service_name="mock-service-now",
        version="0.1.0",
    )


@app.get("/api/now/table/sys_user")
async def get_sys_users(request: Request):
    """Get users from sys_user table."""
    query_params = dict(request.query_params)
    return mock_api.handle_sys_user_query(query_params)


@app.get("/api/now/table/cmdb_ci_computer")
async def get_computers(request: Request):
    """Get computer records from cmdb_ci_computer table."""
    query_params = dict(request.query_params)
    return mock_api.handle_computer_query(query_params)


@app.post("/api/sn_sc/servicecatalog/items/{item_id}/order_now")
async def order_catalog_item(item_id: str, request: Request):
    """Order a service catalog item."""
    body = await request.json()
    return mock_api.handle_catalog_order(item_id, body)


# Administrative endpoints for testing
@app.post("/reset")
async def reset_service() -> Dict[str, str]:
    """Reset the mock service to initial state."""
    global mock_api
    mock_api = MockServiceNowAPI()
    logger.info("Mock ServiceNow API reset to initial state")
    return {"status": "reset", "message": "Mock ServiceNow API reset to initial state"}


@app.get("/debug/users")
async def debug_users() -> Dict[str, Any]:
    """Debug endpoint to list all mock users."""
    return {
        "users": list(mock_api.mock_users.values()),
        "count": len(mock_api.mock_users),
        "email_mapping": mock_api.email_to_sys_id,
    }


@app.get("/debug/computers")
async def debug_computers() -> Dict[str, Any]:
    """Debug endpoint to list all mock computers."""
    return {
        "computers": list(mock_api.mock_computers.values()),
        "count": len(mock_api.mock_computers),
    }


if tracingIsActive():
    FastAPIInstrumentor.instrument_app(app)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8082"))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info("Starting Mock ServiceNow API", host=host, port=port)

    uvicorn.run(
        "mock_service_now.main:app",
        host=host,
        port=port,
        log_level="info",
        reload=False,
    )
