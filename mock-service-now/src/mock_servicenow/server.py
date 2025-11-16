"""Mock ServiceNow server implementation."""

import os
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from shared_models import configure_logging

from .data import (
    create_laptop_refresh_request,
    find_computers_by_user_sys_id,
    find_user_by_email,
)

# Configure logging
logger = configure_logging(__name__)

# FastAPI app
app = FastAPI(
    title="Mock ServiceNow Server",
    description="Mock ServiceNow REST API for testing self-service agent blueprint",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# API Key authentication (optional for mock server)
api_key_header = APIKeyHeader(name="x-sn-apikey", auto_error=False)


def get_api_key(api_key: Optional[str] = Security(api_key_header)) -> Optional[str]:
    """Validate API key (optional validation for mock server)."""
    # For mock server, we accept any API key or no API key
    # In a real implementation, you would validate against actual API keys
    logger.debug("API key received", api_key_status="***" if api_key else "None")
    return api_key


class OrderNowRequest(BaseModel):
    """Request model for service catalog order_now endpoint."""

    sysparm_quantity: int = 1
    variables: Dict[str, str]


@app.get("/")
async def root() -> Dict[str, Any]:
    """Root endpoint."""
    return {
        "message": "Mock ServiceNow Server",
        "version": "0.1.0",
        "endpoints": {
            "service_catalog": "/api/sn_sc/servicecatalog/items/{item_id}/order_now",
            "users": "/api/now/table/sys_user",
            "computers": "/api/now/table/cmdb_ci_computer",
            "docs": "/docs",
        },
    }


@app.get("/health")
async def health() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "OK", "service": "mock-servicenow"}


@app.post("/api/sn_sc/servicecatalog/items/{laptop_refresh_id}/order_now")
async def order_laptop_refresh(
    laptop_refresh_id: str,
    order_request: OrderNowRequest,
    api_key: Optional[str] = Depends(get_api_key),
) -> Dict[str, Any]:
    """Create a laptop refresh request.

    This endpoint mimics ServiceNow's service catalog order_now API.
    """
    logger.info("Creating laptop refresh request", laptop_refresh_id=laptop_refresh_id)
    logger.debug("Request variables", variables=order_request.variables)

    # Validate required variables
    if "laptop_choices" not in order_request.variables:
        raise HTTPException(
            status_code=400, detail="Missing required variable: laptop_choices"
        )

    if "who_is_this_request_for" not in order_request.variables:
        raise HTTPException(
            status_code=400, detail="Missing required variable: who_is_this_request_for"
        )

    laptop_choices = order_request.variables["laptop_choices"]
    who_is_this_request_for = order_request.variables["who_is_this_request_for"]

    # Create the mock request
    try:
        result = create_laptop_refresh_request(
            laptop_refresh_id=laptop_refresh_id,
            laptop_choices=laptop_choices,
            who_is_this_request_for=who_is_this_request_for,
        )

        logger.info(
            "Successfully created laptop refresh request",
            request_number=result["result"]["request_number"],
            user=who_is_this_request_for,
        )

        return result

    except Exception as e:
        logger.error("Error creating laptop refresh request", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error creating request: {str(e)}")


@app.get("/api/now/table/sys_user")
async def get_users(
    request: Request,
    api_key: Optional[str] = Depends(get_api_key),
) -> Dict[str, Any]:
    """Get users from the sys_user table.

    This endpoint mimics ServiceNow's Table API for sys_user.
    Supports filtering by email via sysparm_query parameter.
    """
    # Parse query parameters
    query_params = dict(request.query_params)
    logger.debug("User query parameters", query_params=query_params)

    sysparm_query = query_params.get("sysparm_query", "")
    sysparm_limit = int(query_params.get("sysparm_limit", "1"))

    # Parse email from query (format: email=user@company.com)
    email = None
    if sysparm_query.startswith("email="):
        email = sysparm_query[6:]  # Remove "email=" prefix

    if not email:
        logger.warning("No email specified in sysparm_query")
        return {"result": []}

    # Find user by email
    user = find_user_by_email(email)
    if not user:
        logger.info("User not found for email", email=email)
        return {"result": []}

    logger.info("Found user for email", email=email, user_name=user["name"])

    # Return ServiceNow-style response
    result = [user] if sysparm_limit >= 1 else []
    return {"result": result}


@app.get("/api/now/table/cmdb_ci_computer")
async def get_computers(
    request: Request,
    api_key: Optional[str] = Depends(get_api_key),
) -> Dict[str, Any]:
    """Get computers from the cmdb_ci_computer table.

    This endpoint mimics ServiceNow's Table API for cmdb_ci_computer.
    Supports filtering by assigned_to via sysparm_query parameter.
    """
    # Parse query parameters
    query_params = dict(request.query_params)
    logger.debug("Computer query parameters", query_params=query_params)

    sysparm_query = query_params.get("sysparm_query", "")

    # Parse assigned_to user sys_id from query (format: assigned_to=sys_id)
    user_sys_id = None
    if sysparm_query.startswith("assigned_to="):
        user_sys_id = sysparm_query[12:]  # Remove "assigned_to=" prefix

    if not user_sys_id:
        logger.warning("No user sys_id specified in sysparm_query")
        return {"result": []}

    # Find computers for user
    computers = find_computers_by_user_sys_id(user_sys_id)

    logger.info(
        "Found computers for user",
        computer_count=len(computers),
        user_sys_id=user_sys_id,
    )

    # Return ServiceNow-style response
    return {"result": computers}


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> HTTPException:
    """Handle unexpected exceptions."""
    logger.error(
        "Unexpected error", method=request.method, url=str(request.url), error=str(exc)
    )
    return HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))

    logger.info("Starting Mock ServiceNow server", host=host, port=port)

    uvicorn.run(
        "mock_servicenow.server:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )
