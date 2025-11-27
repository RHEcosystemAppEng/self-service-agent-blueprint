"""Tests for Snow Server MCP server."""

from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock, patch

import pytest
from snow.server import get_employee_laptop_info, open_laptop_refresh_ticket
from snow.servicenow.client import ServiceNowClient
from snow.servicenow.models import OpenServiceNowLaptopRefreshRequestParams


class MockRequest:
    """Mock request object with headers."""

    def __init__(self, headers: dict[str, str]):
        self.headers = headers


class MockRequestContext:
    """Mock request context."""

    def __init__(self, headers: dict[str, str]):
        self.request = MockRequest(headers)


class MockContext:
    """Mock Context object for testing."""

    def __init__(self, headers: dict[str, str]):
        self.request_context = MockRequestContext(headers)


@patch("snow.server.mcp")
@patch("snow.server.ServiceNowClient")
def test_open_laptop_refresh_ticket_success(
    mock_servicenow_client: Mock, mock_mcp: Mock
) -> None:
    """Test successful ticket creation."""
    employee_name = "John Doe"
    business_justification = "Current laptop is outdated and affecting productivity"
    servicenow_laptop_code = "apple_mac_book_pro_14_m_3_pro"

    # Mock the mcp attributes
    mock_mcp.laptop_refresh_id = "test_laptop_refresh_id"
    mock_mcp.laptop_request_limits = 2
    mock_mcp.laptop_avoid_duplicates = False

    # Mock ServiceNow client responses
    mock_client_instance = MagicMock()
    mock_servicenow_client.return_value = mock_client_instance

    # Mock user lookup response
    mock_client_instance.get_user_by_email.return_value = {
        "success": True,
        "user": {"sys_id": "1001"},
    }

    # Mock ticket creation response
    mock_client_instance.open_laptop_refresh_request.return_value = {
        "success": True,
        "data": {"result": {"request_number": "RITM0010037", "sys_id": "1001"}},
    }

    # Create mock context with AUTHORITATIVE_USER_ID header
    ctx = MockContext({"AUTHORITATIVE_USER_ID": "alice.johnson@company.com"})

    result = open_laptop_refresh_ticket(
        employee_name=employee_name,
        business_justification=business_justification,
        servicenow_laptop_code=servicenow_laptop_code,
        ctx=ctx,
    )

    # Check that result contains expected information
    assert "opened for employee" in result
    assert "alice.johnson@company.com" in result  # authoritative_user_id
    assert "System ID: 1001" in result  # employee_id from mock data
    assert "RITM" in result  # Ticket number format


@patch("snow.server.mcp")
@patch("snow.server.ServiceNowClient")
def test_open_laptop_refresh_ticket_required_model(
    mock_servicenow_client: Mock,
    mock_mcp: Mock,
) -> None:
    """Test ticket creation with required ServiceNow laptop code."""
    employee_name = "Jane Smith"
    business_justification = "Hardware failure requiring replacement"
    servicenow_laptop_code = "lenovo_think_pad_t_14_gen_5_intel"

    # Mock the mcp attributes
    mock_mcp.laptop_refresh_id = "test_laptop_refresh_id"
    mock_mcp.laptop_request_limits = 2
    mock_mcp.laptop_avoid_duplicates = False

    # Mock ServiceNow client responses
    mock_client_instance = MagicMock()
    mock_servicenow_client.return_value = mock_client_instance

    # Mock user lookup response
    mock_client_instance.get_user_by_email.return_value = {
        "success": True,
        "user": {"sys_id": "1001"},
    }

    # Mock ticket creation response
    mock_client_instance.open_laptop_refresh_request.return_value = {
        "success": True,
        "data": {"result": {"request_number": "RITM0010038", "sys_id": "1001"}},
    }

    # Create mock context with AUTHORITATIVE_USER_ID header
    ctx = MockContext({"AUTHORITATIVE_USER_ID": "alice.johnson@company.com"})

    result = open_laptop_refresh_ticket(
        employee_name=employee_name,
        business_justification=business_justification,
        servicenow_laptop_code=servicenow_laptop_code,
        ctx=ctx,
    )

    # Check that result contains the expected format
    assert "opened for employee" in result
    assert "alice.johnson@company.com" in result  # authoritative_user_id
    assert "System ID: 1001" in result  # employee_id from mock data
    assert "RITM" in result  # Ticket number format


def test_open_laptop_refresh_ticket_empty_employee_name() -> None:
    """Test error handling for empty employee name."""
    ctx = MockContext({"AUTHORITATIVE_USER_ID": "alice.johnson@company.com"})
    with pytest.raises(ValueError, match="Employee name cannot be empty"):
        open_laptop_refresh_ticket(
            employee_name="",
            business_justification="Need new laptop",
            servicenow_laptop_code="apple_mac_book_air_m_3",
            ctx=ctx,
        )


def test_open_laptop_refresh_ticket_empty_justification() -> None:
    """Test error handling for empty business justification."""
    ctx = MockContext({"AUTHORITATIVE_USER_ID": "alice.johnson@company.com"})
    with pytest.raises(ValueError, match="Business justification cannot be empty"):
        open_laptop_refresh_ticket(
            employee_name="John Doe",
            business_justification="",
            servicenow_laptop_code="apple_mac_book_air_m_3",
            ctx=ctx,
        )


def test_open_laptop_refresh_ticket_empty_servicenow_code() -> None:
    """Test error handling for empty ServiceNow laptop code."""
    ctx = MockContext({"AUTHORITATIVE_USER_ID": "alice.johnson@company.com"})
    with pytest.raises(ValueError, match="ServiceNow laptop code cannot be empty"):
        open_laptop_refresh_ticket(
            employee_name="John Doe",
            business_justification="Need new laptop",
            servicenow_laptop_code="",
            ctx=ctx,
        )


@patch("snow.server.mcp")
@patch("snow.server.ServiceNowClient")
def test_get_employee_laptop_info_success(
    mock_servicenow_client: Mock, mock_mcp: Mock
) -> None:
    """Test successful laptop info retrieval."""
    # Mock the mcp attributes
    mock_mcp.laptop_refresh_id = "test_laptop_refresh_id"
    mock_mcp.laptop_request_limits = 2
    mock_mcp.laptop_avoid_duplicates = False

    # Mock ServiceNow client responses
    mock_client_instance = MagicMock()
    mock_servicenow_client.return_value = mock_client_instance

    # Mock laptop info response
    expected_laptop_info = """
    Employee Name: Alice Johnson
    Employee Location: EMEA
    Laptop Model: Latitude 7420
    Laptop Serial Number: DL7420001
    Laptop Purchase Date: 2020-01-15
    Laptop Age: 4 years and 10 months
    Laptop Warranty Expiry Date: 2023-01-15
    Laptop Warranty: Expired
    """

    mock_client_instance.get_employee_laptop_info.return_value = expected_laptop_info

    # Create mock context with AUTHORITATIVE_USER_ID header
    ctx = MockContext({"AUTHORITATIVE_USER_ID": "alice.johnson@company.com"})

    result = get_employee_laptop_info(ctx=ctx)

    # Check that result contains expected information
    assert "Alice Johnson" in result
    assert "EMEA" in result
    assert "Latitude 7420" in result
    assert "DL7420001" in result

    # Verify the ServiceNow client was called with the correct user ID
    mock_client_instance.get_employee_laptop_info.assert_called_once_with(
        "alice.johnson@company.com"
    )


# Tests for open_laptop_refresh_request function


@patch("snow.servicenow.client.requests.post")
def test_open_laptop_refresh_request_same_laptop_existing_request(
    mock_post: Mock,
) -> None:
    """Test returning existing ticket when same laptop model request already exists."""
    # Setup test data
    api_token = "test_token"
    laptop_refresh_id = "test_refresh_id"
    laptop_request_limits = 2

    # Mock parameters
    params = OpenServiceNowLaptopRefreshRequestParams(
        who_is_this_request_for="user123",
        laptop_choices="apple_mac_book_pro_14_m_3_pro",
    )

    # Mock existing requests with same laptop model
    existing_requests = [
        {
            "number": "RITM0010001",
            "variables.laptop_choices": "apple_mac_book_pro_14_m_3_pro",  # Same laptop model
            "state": "1",
        }
    ]

    # Create ServiceNowClient instance with duplicate avoidance enabled
    client = ServiceNowClient(
        api_token=api_token,
        laptop_refresh_id=laptop_refresh_id,
        laptop_request_limits=laptop_request_limits,
        laptop_avoid_duplicates=True,
    )

    # Mock get_open_laptop_requests_for_user to return existing requests
    with patch.object(client, "get_open_laptop_requests_for_user") as mock_get_requests:
        mock_get_requests.return_value = {
            "success": True,
            "requests": existing_requests,
        }

        # Call the function
        result = client.open_laptop_refresh_request(params)

        # Assertions
        assert result["success"] is True
        assert "existing_request" in result["data"]
        assert result["existing_ticket"] is True
        assert (
            "Existing open request found for the same laptop model" in result["message"]
        )
        assert "RITM0010001" in result["message"]

        # Verify that no new request was made
        mock_post.assert_not_called()

        # Verify get_open_laptop_requests_for_user was called
        mock_get_requests.assert_called_once_with("user123")


@patch("snow.servicenow.client.requests.post")
def test_open_laptop_refresh_request_exceeds_limit(
    mock_post: Mock,
) -> None:
    """Test error when adding new request would exceed the laptop request limit."""
    # Setup test data
    api_token = "test_token"
    laptop_refresh_id = "test_refresh_id"
    laptop_request_limits = 2  # Set limit to 2

    # Mock parameters for a different laptop
    params = OpenServiceNowLaptopRefreshRequestParams(
        who_is_this_request_for="user123",
        laptop_choices="lenovo_think_pad_t_14_gen_5_intel",  # Different laptop
    )

    # Mock existing requests - user already has 2 open requests (at the limit)
    existing_requests = [
        {
            "number": "RITM0010001",
            "variables.laptop_choices": "apple_mac_book_pro_14_m_3_pro",  # Different laptop
            "state": "1",
        },
        {
            "number": "RITM0010002",
            "variables.laptop_choices": "dell_latitude_7420",  # Another different laptop
            "state": "1",
        },
    ]

    # Create ServiceNowClient instance with duplicate avoidance disabled to test limit behavior
    client = ServiceNowClient(
        api_token=api_token,
        laptop_refresh_id=laptop_refresh_id,
        laptop_request_limits=laptop_request_limits,
        laptop_avoid_duplicates=False,
    )

    # Mock get_open_laptop_requests_for_user to return existing requests
    with patch.object(client, "get_open_laptop_requests_for_user") as mock_get_requests:
        mock_get_requests.return_value = {
            "success": True,
            "requests": existing_requests,
        }

        # Call the function
        result = client.open_laptop_refresh_request(params)

        # Assertions
        assert result["success"] is False
        assert "Cannot open new laptop request" in result["message"]
        assert (
            "2 open request(s), which meets or exceeds the limit of 2"
            in result["message"]
        )
        assert result["data"]["existing_requests"] == existing_requests
        assert result["data"]["limit"] == 2

        # Verify that no new request was made
        mock_post.assert_not_called()

        # Verify get_open_laptop_requests_for_user was called
        mock_get_requests.assert_called_once_with("user123")


@patch("snow.servicenow.client.requests.post")
def test_open_laptop_refresh_request_within_limits_creates_new_ticket(
    mock_post: Mock,
) -> None:
    """Test creating new ticket when different laptop requested and within limits."""
    # Setup test data
    api_token = "test_token"
    laptop_refresh_id = "test_refresh_id"
    laptop_request_limits = 2  # Set limit to 2

    # Mock parameters for a different laptop
    params = OpenServiceNowLaptopRefreshRequestParams(
        who_is_this_request_for="user123",
        laptop_choices="lenovo_think_pad_t_14_gen_5_intel",  # Different laptop
    )

    # Mock existing requests - user has only 1 open request (under the limit)
    existing_requests = [
        {
            "number": "RITM0010001",
            "variables.laptop_choices": "apple_mac_book_pro_14_m_3_pro",  # Different laptop
            "state": "1",
        }
    ]

    # Mock successful ServiceNow API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": {"request_number": "RITM0010003", "sys_id": "new_request_id"}
    }
    mock_post.return_value = mock_response

    # Create ServiceNowClient instance with duplicate avoidance disabled to test new ticket creation
    client = ServiceNowClient(
        api_token=api_token,
        laptop_refresh_id=laptop_refresh_id,
        laptop_request_limits=laptop_request_limits,
        laptop_avoid_duplicates=False,
    )

    # Mock get_open_laptop_requests_for_user to return existing requests
    with patch.object(client, "get_open_laptop_requests_for_user") as mock_get_requests:
        mock_get_requests.return_value = {
            "success": True,
            "requests": existing_requests,
        }

        # Call the function
        result = client.open_laptop_refresh_request(params)

        # Assertions
        assert result["success"] is True
        assert result["existing_ticket"] is False
        assert "Successfully opened laptop refresh request" in result["message"]
        assert result["data"]["result"]["request_number"] == "RITM0010003"
        assert result["data"]["result"]["sys_id"] == "new_request_id"

        # Verify that a new request was made to ServiceNow
        mock_post.assert_called_once()

        # Verify the request was made to the correct URL
        call_args = mock_post.call_args
        assert (
            f"/api/sn_sc/servicecatalog/items/{laptop_refresh_id}/order_now"
            in call_args[0][0]
        )

        # Verify request body contains correct parameters
        request_body = call_args[1]["json"]
        assert request_body["sysparm_quantity"] == 1
        assert (
            request_body["variables"]["laptop_choices"]
            == "lenovo_think_pad_t_14_gen_5_intel"
        )
        assert request_body["variables"]["who_is_this_request_for"] == "user123"

        # Verify get_open_laptop_requests_for_user was called
        mock_get_requests.assert_called_once_with("user123")


@patch("snow.servicenow.client.requests.post")
def test_open_laptop_refresh_request_no_existing_requests(
    mock_post: Mock,
) -> None:
    """Test creating ticket when user has no existing requests."""
    # Setup test data
    api_token = "test_token"
    laptop_refresh_id = "test_refresh_id"
    laptop_request_limits = 2

    # Mock parameters
    params = OpenServiceNowLaptopRefreshRequestParams(
        who_is_this_request_for="user123",
        laptop_choices="apple_mac_book_pro_14_m_3_pro",
    )

    # Mock no existing requests
    existing_requests: List[Dict[str, Any]] = []

    # Mock successful ServiceNow API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": {"request_number": "RITM0010004", "sys_id": "new_request_id"}
    }
    mock_post.return_value = mock_response

    # Create ServiceNowClient instance
    client = ServiceNowClient(
        api_token=api_token,
        laptop_refresh_id=laptop_refresh_id,
        laptop_request_limits=laptop_request_limits,
        laptop_avoid_duplicates=False,
    )

    # Mock get_open_laptop_requests_for_user to return no existing requests
    with patch.object(client, "get_open_laptop_requests_for_user") as mock_get_requests:
        mock_get_requests.return_value = {
            "success": True,
            "requests": existing_requests,
        }

        # Call the function
        result = client.open_laptop_refresh_request(params)

        # Assertions
        assert result["success"] is True
        assert result["existing_ticket"] is False
        assert "Successfully opened laptop refresh request" in result["message"]
        assert result["data"]["result"]["request_number"] == "RITM0010004"
        assert result["data"]["result"]["sys_id"] == "new_request_id"

        # Verify that a new request was made to ServiceNow
        mock_post.assert_called_once()

        # Verify the request was made to the correct URL
        call_args = mock_post.call_args
        assert (
            f"/api/sn_sc/servicecatalog/items/{laptop_refresh_id}/order_now"
            in call_args[0][0]
        )

        # Verify request body contains correct parameters
        request_body = call_args[1]["json"]
        assert request_body["sysparm_quantity"] == 1
        assert (
            request_body["variables"]["laptop_choices"]
            == "apple_mac_book_pro_14_m_3_pro"
        )
        assert request_body["variables"]["who_is_this_request_for"] == "user123"

        # Verify get_open_laptop_requests_for_user was called
        mock_get_requests.assert_called_once_with("user123")


@patch("snow.servicenow.client.requests.post")
def test_open_laptop_refresh_request_get_existing_requests_failure(
    mock_post: Mock,
) -> None:
    """Test error handling when get_open_laptop_requests_for_user fails."""
    # Setup test data
    api_token = "test_token"
    laptop_refresh_id = "test_refresh_id"
    laptop_request_limits = 2

    # Mock parameters
    params = OpenServiceNowLaptopRefreshRequestParams(
        who_is_this_request_for="user123",
        laptop_choices="apple_mac_book_pro_14_m_3_pro",
    )

    # Create ServiceNowClient instance
    client = ServiceNowClient(
        api_token=api_token,
        laptop_refresh_id=laptop_refresh_id,
        laptop_request_limits=laptop_request_limits,
        laptop_avoid_duplicates=False,
    )

    # Mock get_open_laptop_requests_for_user to return failure
    with patch.object(client, "get_open_laptop_requests_for_user") as mock_get_requests:
        mock_get_requests.return_value = {
            "success": False,
            "message": "Failed to fetch existing requests",
        }

        # Call the function
        result = client.open_laptop_refresh_request(params)

        # Assertions
        assert result["success"] is False
        assert result["message"] == "Failed to fetch existing requests"

        # Verify that no new request was made
        mock_post.assert_not_called()

        # Verify get_open_laptop_requests_for_user was called
        mock_get_requests.assert_called_once_with("user123")


@patch("snow.servicenow.client.requests.post")
def test_open_laptop_refresh_request_api_failure(
    mock_post: Mock,
) -> None:
    """Test error handling when ServiceNow API request fails."""
    import requests

    # Setup test data
    api_token = "test_token"
    laptop_refresh_id = "test_refresh_id"
    laptop_request_limits = 2

    # Mock parameters
    params = OpenServiceNowLaptopRefreshRequestParams(
        who_is_this_request_for="user123",
        laptop_choices="apple_mac_book_pro_14_m_3_pro",
    )

    # Mock no existing requests
    existing_requests: List[Dict[str, Any]] = []

    # Mock API request failure
    mock_post.side_effect = requests.exceptions.RequestException("Connection error")

    # Create ServiceNowClient instance
    client = ServiceNowClient(
        api_token=api_token,
        laptop_refresh_id=laptop_refresh_id,
        laptop_request_limits=laptop_request_limits,
        laptop_avoid_duplicates=False,
    )

    # Mock get_open_laptop_requests_for_user to return no existing requests
    with patch.object(client, "get_open_laptop_requests_for_user") as mock_get_requests:
        mock_get_requests.return_value = {
            "success": True,
            "requests": existing_requests,
        }

        # Call the function
        result = client.open_laptop_refresh_request(params)

        # Assertions
        assert result["success"] is False
        assert "Error opening laptop refresh request" in result["message"]
        assert "Connection error" in result["message"]
        assert result["data"] is None

        # Verify that a request was attempted
        mock_post.assert_called_once()

        # Verify get_open_laptop_requests_for_user was called
        mock_get_requests.assert_called_once_with("user123")


@patch("snow.servicenow.client.requests.post")
def test_open_laptop_refresh_request_duplicate_avoidance_disabled(
    mock_post: Mock,
) -> None:
    """Test creating new ticket when same laptop model request exists but duplicate avoidance is disabled."""
    # Setup test data
    api_token = "test_token"
    laptop_refresh_id = "test_refresh_id"
    laptop_request_limits = 5  # Set high limit so it doesn't interfere

    # Mock parameters - same laptop as existing request
    params = OpenServiceNowLaptopRefreshRequestParams(
        who_is_this_request_for="user123",
        laptop_choices="apple_mac_book_pro_14_m_3_pro",  # Same laptop model as existing
    )

    # Mock existing requests with same laptop model
    existing_requests = [
        {
            "number": "RITM0010001",
            "variables.laptop_choices": "apple_mac_book_pro_14_m_3_pro",  # Same laptop model
            "state": "1",
        }
    ]

    # Mock successful ServiceNow API response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": {"request_number": "RITM0010005", "sys_id": "new_request_id"}
    }
    mock_post.return_value = mock_response

    # Create ServiceNowClient instance with duplicate avoidance disabled
    client = ServiceNowClient(
        api_token=api_token,
        laptop_refresh_id=laptop_refresh_id,
        laptop_request_limits=laptop_request_limits,
        laptop_avoid_duplicates=False,
    )

    # Mock get_open_laptop_requests_for_user to return existing requests
    with patch.object(client, "get_open_laptop_requests_for_user") as mock_get_requests:
        mock_get_requests.return_value = {
            "success": True,
            "requests": existing_requests,
        }

        # Call the function
        result = client.open_laptop_refresh_request(params)

        # Assertions - should create new ticket despite duplicate
        assert result["success"] is True
        assert result["existing_ticket"] is False
        assert "Successfully opened laptop refresh request" in result["message"]
        assert result["data"]["result"]["request_number"] == "RITM0010005"
        assert result["data"]["result"]["sys_id"] == "new_request_id"

        # Verify that a new request was made to ServiceNow (allowing duplicate)
        mock_post.assert_called_once()

        # Verify the request was made to the correct URL
        call_args = mock_post.call_args
        assert (
            f"/api/sn_sc/servicecatalog/items/{laptop_refresh_id}/order_now"
            in call_args[0][0]
        )

        # Verify request body contains correct parameters
        request_body = call_args[1]["json"]
        assert request_body["sysparm_quantity"] == 1
        assert (
            request_body["variables"]["laptop_choices"]
            == "apple_mac_book_pro_14_m_3_pro"
        )
        assert request_body["variables"]["who_is_this_request_for"] == "user123"

        # Verify get_open_laptop_requests_for_user was called
        mock_get_requests.assert_called_once_with("user123")
