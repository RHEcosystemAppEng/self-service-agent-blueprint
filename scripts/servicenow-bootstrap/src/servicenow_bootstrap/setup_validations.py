#!/usr/bin/env python3
"""
ServiceNow API Key Credentials Test Script
Tests the ability to call various ServiceNow APIs with the provided API Key credentials.
"""

import sys
from typing import Any, Dict, Optional, Tuple

import requests

from .utils import get_env_var


class ServiceNowAPITester:
    """Test ServiceNow API Key credentials against various endpoints."""

    def __init__(self) -> None:
        """Initialize the API tester with environment variables."""
        self.api_key = get_env_var("SERVICENOW_API_KEY")
        self.laptop_refresh_id = get_env_var("SERVICENOW_LAPTOP_REFRESH_ID")
        self.instance_url = get_env_var("SERVICENOW_INSTANCE_URL").rstrip("/")

        # Setup session with API key authentication
        self.session = requests.Session()
        self.session.headers.update(
            {
                "x-sn-apikey": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def _make_request(
        self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Dict[str, Any], str]:
        """
        Make HTTP request to ServiceNow API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            data: Optional request body data

        Returns:
            Tuple of (success, response_data, error_message)
        """
        url = f"{self.instance_url}/api/{endpoint}"

        try:
            if method.upper() == "GET":
                response = self.session.get(url)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data)
            else:
                return False, {}, f"Unsupported HTTP method: {method}"

            # Check if request was successful
            if response.status_code >= 200 and response.status_code < 300:
                try:
                    response_data = response.json()
                    return True, response_data, ""
                except ValueError:
                    return True, {"raw_response": response.text}, ""
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                return False, {}, error_msg

        except requests.exceptions.RequestException as e:
            return False, {}, str(e)

    def _get_arbitrary_user(self) -> str:
        """
        Fetch an arbitrary user from the ServiceNow system with example.com email domain.

        Returns:
            User sys_id if successful, empty string if failed
        """
        # Filter for users with example.com email addresses
        query_params = (
            "sysparm_limit=1"
            "&sysparm_fields=sys_id,user_name,email"
            "&sysparm_query=emailLIKEexample.com"
        )

        success, data, error = self._make_request(
            "GET", f"now/table/sys_user?{query_params}"
        )

        if success and data.get("result"):
            user = data["result"][0]
            user_id = user.get("sys_id")
            user_name = user.get("user_name", "unknown")
            email = user.get("email", "unknown")
            print(f"  Using user: {user_name} ({email}) (ID: {user_id})")
            return str(user_id) if user_id else ""
        else:
            print(
                f"  Warning: Could not fetch user with example.com domain, using fallback: {error}"
            )
            return ""

    def test_cmdb_computers(self) -> Tuple[bool, str]:
        """Test GET api/now/table/cmdb_ci_computer endpoint."""
        print("🖥️  Testing CMDB Computers API...")

        success, data, error = self._make_request(
            "GET", "now/table/cmdb_ci_computer?sysparm_limit=1"
        )

        if success:
            result_count = len(data.get("result", []))
            return (
                True,
                f"✅ Successfully accessed CMDB computers (found {result_count} records)",
            )
        else:
            return False, f"❌ Failed to access CMDB computers: {error}"

    def test_service_catalog_item(self) -> Tuple[bool, str]:
        """Test GET api/sn_sc/servicecatalog/items/{catalog_id} endpoint."""
        print(f"📦 Testing Service Catalog Item API (ID: {self.laptop_refresh_id})...")

        success, data, error = self._make_request(
            "GET", f"sn_sc/servicecatalog/items/{self.laptop_refresh_id}"
        )

        if success:
            item_name = data.get("result", {}).get("name", "Unknown")
            return True, f"✅ Successfully accessed catalog item: {item_name}"
        else:
            return False, f"❌ Failed to access catalog item: {error}"

    def test_catalog_items_table(self) -> Tuple[bool, str]:
        """Test GET api/now/table/sc_cat_item endpoint."""
        print("📋 Testing Catalog Items Table API...")

        success, data, error = self._make_request(
            "GET", "now/table/sc_cat_item?sysparm_limit=1"
        )

        if success:
            result_count = len(data.get("result", []))
            return (
                True,
                f"✅ Successfully accessed catalog items table (found {result_count} records)",
            )
        else:
            return False, f"❌ Failed to access catalog items table: {error}"

    def test_catalog_order(self) -> Tuple[bool, str]:
        """Test POST api/sn_sc/servicecatalog/items/{catalog_id}/order_now endpoint."""
        print(f"🛒 Testing Service Catalog Order API (ID: {self.laptop_refresh_id})...")

        # Get an arbitrary user from the system
        user_id = self._get_arbitrary_user()

        # Prepare minimal order data - this will likely fail due to missing required fields
        # but we're testing authentication and endpoint access
        order_data = {
            "sysparm_quantity": "1",
            "variables": {
                "laptop_choices": "lenovo_think_pad_p_16_gen_2",
                "who_is_this_request_for": user_id,
            },
        }

        success, data, error = self._make_request(
            "POST",
            f"sn_sc/servicecatalog/items/{self.laptop_refresh_id}/order_now",
            order_data,
        )

        if success:
            # Even if the order fails due to missing fields, a successful auth means we can access the endpoint
            if "result" in data:
                req_number = data.get("result", {}).get("request_number", "")
                return (
                    True,
                    f"✅ Successfully accessed catalog order endpoint (authentication works) - [request_number={req_number}]",
                )
            else:
                return True, "✅ Successfully accessed catalog order endpoint"
        else:
            # Check if it's an authentication error vs a validation error
            if (
                "401" in error
                or "403" in error
                or "Unauthorized" in error
                or "Forbidden" in error
            ):
                return False, f"❌ Authentication failed for catalog order: {error}"
            else:
                # If it's a validation error, authentication actually worked
                return (
                    True,
                    f"✅ Successfully accessed catalog order endpoint (got validation error as expected): {error}",
                )

    def run_all_tests(self) -> Dict[str, Tuple[bool, str]]:
        """Run all API tests and return results."""
        print("🧪 Starting ServiceNow API Key Credentials Test")
        print("=" * 60)
        print(f"Instance URL: {self.instance_url}")
        print(f"Laptop Refresh ID: {self.laptop_refresh_id}")
        print(f"API Key: {self.api_key[:8]}..." if len(self.api_key) > 8 else "***")
        print("=" * 60)
        print()

        tests = [
            ("CMDB Computers", self.test_cmdb_computers),
            ("Service Catalog Item", self.test_service_catalog_item),
            ("Catalog Items Table", self.test_catalog_items_table),
            ("Catalog Order", self.test_catalog_order),
        ]

        results = {}
        passed = 0
        total = len(tests)

        for test_name, test_func in tests:
            try:
                success, message = test_func()
                results[test_name] = (success, message)
                print(message)
                if success:
                    passed += 1
            except Exception as e:
                error_msg = f"❌ Test failed with exception: {str(e)}"
                results[test_name] = (False, error_msg)
                print(error_msg)
            print()

        # Print summary
        print("=" * 60)
        print("📊 Test Results Summary")
        print("=" * 60)
        print(f"Passed: {passed}/{total}")

        if passed == total:
            print(
                "🎉 All tests passed! Your API Key credentials are working correctly."
            )
        elif passed > 0:
            print("⚠️  Some tests passed. Check the failed tests for potential issues.")
        else:
            print(
                "❌ All tests failed. Please check your API Key credentials and permissions."
            )

        print("\n📝 Next steps:")
        if passed == total:
            print("✅ Your ServiceNow API integration is ready to use!")
        else:
            print("1. Verify your API Key is correct and active")
            print("2. Check that the MCP agent user has proper permissions")
            print("3. Ensure the catalog item ID is correct")
            print("4. Review API access policies in ServiceNow")

        return results


def main() -> None:
    """Main entry point for the API test script."""
    try:
        tester = ServiceNowAPITester()
        results = tester.run_all_tests()

        # Exit with error code if any tests failed
        failed_tests = [name for name, (success, _) in results.items() if not success]
        if failed_tests:
            sys.exit(1)
        else:
            sys.exit(0)

    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
