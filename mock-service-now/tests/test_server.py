"""Tests for mock ServiceNow server."""

from fastapi.testclient import TestClient
from mock_servicenow.server import app

client = TestClient(app)


def test_root_endpoint() -> None:
    """Test the root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Mock ServiceNow Server"
    assert "endpoints" in data


def test_health_endpoint() -> None:
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "OK"
    assert data["service"] == "mock-servicenow"


def test_get_user_by_email_success() -> None:
    """Test successful user lookup by email."""
    response = client.get(
        "/api/now/table/sys_user",
        params={
            "sysparm_query": "email=alice.johnson@company.com",
            "sysparm_limit": "1",
            "sysparm_display_value": "true",
            "sysparm_fields": "sys_id,name,email,user_name,location,active",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert len(data["result"]) == 1

    user = data["result"][0]
    assert user["email"] == "alice.johnson@company.com"
    assert user["name"] == "Alice Johnson"
    assert user["sys_id"] == "1001"


def test_get_user_by_email_not_found() -> None:
    """Test user lookup with non-existent email."""
    response = client.get(
        "/api/now/table/sys_user",
        params={"sysparm_query": "email=nonexistent@company.com"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["result"] == []


def test_get_computers_by_user_sys_id() -> None:
    """Test computer lookup by user sys_id."""
    response = client.get(
        "/api/now/table/cmdb_ci_computer",
        params={
            "sysparm_query": "assigned_to=1001",
            "sysparm_display_value": "true",
            "sysparm_fields": "sys_id,name,asset_tag,serial_number,model_id,assigned_to,purchase_date,warranty_expiration,install_status,operational_status",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert len(data["result"]) == 1

    computer = data["result"][0]
    assert computer["assigned_to"] == "1001"
    assert computer["serial_number"] == "DL7420001"
    assert "model_id" in computer
    assert computer["model_id"]["display_value"] == "Latitude 7420"


def test_create_laptop_refresh_request() -> None:
    """Test creating a laptop refresh request."""
    request_data = {
        "sysparm_quantity": 1,
        "variables": {
            "laptop_choices": "apple_mac_book_air_m_3",
            "who_is_this_request_for": "1001",
        },
    }

    response = client.post(
        "/api/sn_sc/servicecatalog/items/test_laptop_refresh_id/order_now",
        json=request_data,
        headers={"x-sn-apikey": "test-api-key"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "result" in data

    result = data["result"]
    assert "request_number" in result
    assert result["request_number"].startswith("REQ")
    assert "sys_id" in result
    assert result["requested_for"] == "1001"
    assert result["variables"]["laptop_choices"] == "apple_mac_book_air_m_3"


def test_create_laptop_refresh_request_missing_variables() -> None:
    """Test creating a laptop refresh request with missing required variables."""
    request_data = {
        "sysparm_quantity": 1,
        "variables": {
            "laptop_choices": "apple_mac_book_air_m_3"
            # Missing who_is_this_request_for
        },
    }

    response = client.post(
        "/api/sn_sc/servicecatalog/items/test_laptop_refresh_id/order_now",
        json=request_data,
    )

    assert response.status_code == 400
    assert "who_is_this_request_for" in response.json()["detail"]


def test_api_key_optional() -> None:
    """Test that API key is optional for mock server."""
    # Test without API key
    response = client.get(
        "/api/now/table/sys_user?sysparm_query=email=alice.johnson@company.com"
    )
    assert response.status_code == 200

    # Test with API key
    response = client.get(
        "/api/now/table/sys_user?sysparm_query=email=alice.johnson@company.com",
        headers={"x-sn-apikey": "test-key"},
    )
    assert response.status_code == 200
