#!/usr/bin/env python3
"""
Create evaluation users in ServiceNow based on mock data.

This script creates users and their associated laptops in ServiceNow
using the mock data from data.py. It's useful for setting up a ServiceNow
instance with test data that matches the mock data.

Environment Variables Required:
    SERVICENOW_INSTANCE_URL: ServiceNow instance URL (e.g., https://dev12345.service-now.com)
    SERVICENOW_USERNAME: ServiceNow admin username
    SERVICENOW_PASSWORD: ServiceNow admin password
"""

import os
import sys
from typing import Any, Optional

import requests
from requests.auth import HTTPBasicAuth
from snow.data.data import MOCK_EMPLOYEE_DATA


class ServiceNowUserCreator:
    """Create users and laptops in ServiceNow based on mock data."""

    def __init__(self, instance_url: str, username: str, password: str) -> None:
        """Initialize the ServiceNow user creator.

        Args:
            instance_url: ServiceNow instance URL
            username: ServiceNow admin username
            password: ServiceNow admin password
        """
        self.instance_url = instance_url.rstrip("/")
        self.auth = HTTPBasicAuth(username, password)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self.created_users: list[dict[str, Any]] = []
        self.created_computers: list[dict[str, Any]] = []
        self.created_models: list[dict[str, Any]] = []
        self.created_locations: list[dict[str, Any]] = []
        self.model_cache: dict[str, str] = (
            {}
        )  # Cache model lookups to avoid duplicate API calls
        self.location_cache: dict[str, str] = (
            {}
        )  # Cache location lookups to avoid duplicate API calls
        self.errors: list[str] = []

    def get_or_create_model(self, model_name: str) -> str | None:
        """Get or create a product model in ServiceNow.

        Args:
            model_name: Name of the laptop model (e.g., "Latitude 7420")

        Returns:
            Model sys_id if successful, None otherwise
        """
        # Check cache first
        if model_name in self.model_cache:
            return self.model_cache[model_name]

        model_url = f"{self.instance_url}/api/now/table/cmdb_model"

        # First, try to find existing model
        search_params = {
            "sysparm_query": f"name={model_name}",
            "sysparm_limit": "1",
            "sysparm_fields": "sys_id,name",
        }

        try:
            response = requests.get(
                model_url,
                auth=self.auth,
                headers=self.headers,
                params=search_params,
                timeout=30,
            )

            if response.status_code == 200:
                result = response.json().get("result", [])
                if result:
                    model_sys_id = str(result[0].get("sys_id", ""))
                    print(
                        f"    ℹ️  Found existing model: {model_name} (sys_id: {model_sys_id})"
                    )
                    self.model_cache[model_name] = model_sys_id
                    return model_sys_id

            # Model not found, create it
            model_payload = {
                "name": model_name,
                "display_name": model_name,
                "model_number": model_name,
                # Note: cmdb_model_category is a reference field - omitting it to let ServiceNow set defaults
            }

            create_response = requests.post(
                model_url,
                auth=self.auth,
                headers=self.headers,
                json=model_payload,
                timeout=30,
            )

            if create_response.status_code == 201:
                result = create_response.json().get("result", {})
                model_sys_id = str(result.get("sys_id", ""))
                print(f"    ✅ Created model: {model_name} (sys_id: {model_sys_id})")
                self.model_cache[model_name] = model_sys_id
                self.created_models.append({"name": model_name, "sys_id": model_sys_id})
                return model_sys_id
            else:
                error_msg = f"Failed to create model {model_name}: {create_response.status_code} - {create_response.text}"
                print(f"    ⚠️  {error_msg}")
                # Don't add to errors list, just warn - we'll try to create computer anyway
                return None

        except Exception as e:
            error_msg = f"Exception getting/creating model {model_name}: {str(e)}"
            print(f"    ⚠️  {error_msg}")
            return None

    def get_or_create_location(self, location_name: str) -> Optional[str]:
        """Get or create a location in ServiceNow.

        Args:
            location_name: Name of the location (e.g., "EMEA", "San Francisco Office")

        Returns:
            Location sys_id if successful, None otherwise
        """
        # Check cache first
        if location_name in self.location_cache:
            return self.location_cache[location_name]

        location_url = f"{self.instance_url}/api/now/table/cmn_location"

        # First, try to find existing location
        search_params = {
            "sysparm_query": f"name={location_name}",
            "sysparm_limit": "1",
            "sysparm_fields": "sys_id,name",
        }

        try:
            response = requests.get(
                location_url,
                auth=self.auth,
                headers=self.headers,
                params=search_params,
                timeout=30,
            )

            if response.status_code == 200:
                result = response.json().get("result", [])
                if result:
                    location_sys_id = result[0].get("sys_id")
                    sys_id_str = (
                        str(location_sys_id) if location_sys_id is not None else None
                    )
                    print(
                        f"    ℹ️  Found existing location: {location_name} (sys_id: {sys_id_str})"
                    )
                    self.location_cache[location_name] = sys_id_str or ""
                    return sys_id_str

            # Location not found, create it
            location_payload = {
                "name": location_name,
                "city": location_name,  # Use name as city if not specified
            }

            create_response = requests.post(
                location_url,
                auth=self.auth,
                headers=self.headers,
                json=location_payload,
                timeout=30,
            )

            if create_response.status_code == 201:
                result = create_response.json().get("result", {})
                location_sys_id = result.get("sys_id")
                sys_id_str = (
                    str(location_sys_id) if location_sys_id is not None else None
                )
                print(
                    f"    ✅ Created location: {location_name} (sys_id: {sys_id_str})"
                )
                self.location_cache[location_name] = sys_id_str or ""
                self.created_locations.append(
                    {"name": location_name, "sys_id": sys_id_str}
                )
                return sys_id_str
            else:
                error_msg = f"Failed to create location {location_name}: {create_response.status_code} - {create_response.text}"
                print(f"    ⚠️  {error_msg}")
                # Don't add to errors list, just warn - we'll try to create user anyway
                return None

        except Exception as e:
            error_msg = f"Exception getting/creating location {location_name}: {str(e)}"
            print(f"    ⚠️  {error_msg}")
            return None

    def create_user(self, employee_data: dict[str, Any]) -> str | None:
        """Create a user in ServiceNow.

        Args:
            employee_data: Dictionary containing employee information

        Returns:
            User sys_id if successful, None otherwise
        """
        # First, get or create the location
        location_sys_id = self.get_or_create_location(employee_data["location"])

        user_url = f"{self.instance_url}/api/now/table/sys_user"

        # Generate a username from email (before @)
        username = employee_data["email"].split("@")[0]

        user_payload = {
            "user_name": username,
            "email": employee_data["email"],
            "first_name": employee_data["name"].split()[0],
            "last_name": " ".join(employee_data["name"].split()[1:]),
            "active": "true",
        }

        # Only add location if we successfully got/created it
        if location_sys_id:
            user_payload["location"] = location_sys_id

        try:
            response = requests.post(
                user_url,
                auth=self.auth,
                headers=self.headers,
                json=user_payload,
                timeout=30,
            )

            if response.status_code == 201:
                result = response.json().get("result", {})
                user_sys_id = result.get("sys_id")
                sys_id_str = str(user_sys_id) if user_sys_id is not None else None
                print(
                    f"  ✅ Created user: {employee_data['name']} ({employee_data['email']})"
                )
                print(f"     User sys_id: {sys_id_str}")
                self.created_users.append(
                    {
                        "email": employee_data["email"],
                        "sys_id": sys_id_str,
                        "name": employee_data["name"],
                    }
                )
                return sys_id_str
            else:
                error_msg = f"Failed to create user {employee_data['email']}: {response.status_code} - {response.text}"
                print(f"  ❌ {error_msg}")
                self.errors.append(error_msg)
                return None

        except Exception as e:
            error_msg = f"Exception creating user {employee_data['email']}: {str(e)}"
            print(f"  ❌ {error_msg}")
            self.errors.append(error_msg)
            return None

    def create_computer(
        self, employee_data: dict[str, Any], user_sys_id: str
    ) -> str | None:
        """Create a computer/laptop in ServiceNow.

        Args:
            employee_data: Dictionary containing employee and laptop information
            user_sys_id: ServiceNow sys_id of the user who owns this laptop

        Returns:
            Computer sys_id if successful, None otherwise
        """
        # First, get or create the laptop model
        model_sys_id = self.get_or_create_model(employee_data["laptop_model"])

        computer_url = f"{self.instance_url}/api/now/table/cmdb_ci_computer"

        # Build payload - use model_id sys_id if we got one
        computer_payload = {
            "name": f"{employee_data['name']}'s Laptop",
            "asset_tag": employee_data["laptop_serial_number"],
            "serial_number": employee_data["laptop_serial_number"],
            "assigned_to": user_sys_id,
            "purchase_date": employee_data["purchase_date"],
            "warranty_expiration": employee_data["warranty_expiry"],
            "install_status": "1",  # Installed
            "operational_status": "1",  # Operational
        }

        # Only add model_id if we successfully got/created the model
        if model_sys_id:
            computer_payload["model_id"] = model_sys_id

        try:
            response = requests.post(
                computer_url,
                auth=self.auth,
                headers=self.headers,
                json=computer_payload,
                timeout=30,
            )

            if response.status_code == 201:
                result = response.json().get("result", {})
                computer_sys_id = result.get("sys_id")
                sys_id_str = (
                    str(computer_sys_id) if computer_sys_id is not None else None
                )
                print(
                    f"  ✅ Created laptop: {employee_data['laptop_model']} (S/N: {employee_data['laptop_serial_number']})"
                )
                print(f"     Computer sys_id: {sys_id_str}")
                self.created_computers.append(
                    {
                        "serial_number": employee_data["laptop_serial_number"],
                        "sys_id": sys_id_str,
                        "model": employee_data["laptop_model"],
                    }
                )
                return sys_id_str
            else:
                error_msg = f"Failed to create laptop for {employee_data['email']}: {response.status_code} - {response.text}"
                print(f"  ❌ {error_msg}")
                self.errors.append(error_msg)
                return None

        except Exception as e:
            error_msg = (
                f"Exception creating laptop for {employee_data['email']}: {str(e)}"
            )
            print(f"  ❌ {error_msg}")
            self.errors.append(error_msg)
            return None

    def check_user_exists(self, email: str) -> Optional[str]:
        """Check if a user already exists in ServiceNow.

        Args:
            email: Email address to check

        Returns:
            User sys_id if exists, None otherwise
        """
        user_url = f"{self.instance_url}/api/now/table/sys_user"
        params = {
            "sysparm_query": f"email={email}",
            "sysparm_limit": "1",
            "sysparm_fields": "sys_id,email,name",
        }

        try:
            response = requests.get(
                user_url,
                auth=self.auth,
                headers=self.headers,
                params=params,
                timeout=30,
            )

            if response.status_code == 200:
                result = response.json().get("result", [])
                if result:
                    sys_id = result[0].get("sys_id")
                    return str(sys_id) if sys_id is not None else None
            return None

        except Exception:
            return None

    def create_all_users(self, skip_existing: bool = True) -> None:
        """Create all users and laptops from mock data.

        Args:
            skip_existing: If True, skip users that already exist in ServiceNow
        """
        print("=" * 80)
        print("Creating ServiceNow Evaluation Users")
        print("=" * 80)
        print(f"Instance: {self.instance_url}")
        print(f"Total users to create: {len(MOCK_EMPLOYEE_DATA)}")
        print("=" * 80)
        print()

        for emp_id, employee_data in MOCK_EMPLOYEE_DATA.items():
            print(f"Processing Employee {emp_id}: {employee_data['name']}")
            print("-" * 80)

            # Check if user already exists
            if skip_existing:
                existing_user_id = self.check_user_exists(employee_data["email"])
                if existing_user_id:
                    print(
                        f"  ⚠️  User {employee_data['email']} already exists (sys_id: {existing_user_id})"
                    )
                    print("     Skipping user creation, but will create laptop...")
                    user_sys_id = existing_user_id
                else:
                    # Create user
                    user_sys_id = self.create_user(employee_data) or ""
            else:
                # Create user
                user_sys_id = self.create_user(employee_data) or ""

            # Create laptop if user was created/found successfully
            if user_sys_id:
                self.create_computer(employee_data, user_sys_id)
            else:
                print("  ⚠️  Skipping laptop creation (no user sys_id)")

            print()

    def print_summary(self) -> None:
        """Print a summary of created resources and errors."""
        print("=" * 80)
        print("Summary")
        print("=" * 80)
        print(f"✅ Locations created: {len(self.created_locations)}")
        print(f"✅ Product models created: {len(self.created_models)}")
        print(f"✅ Users created: {len(self.created_users)}")
        print(f"✅ Laptops created: {len(self.created_computers)}")
        print(f"❌ Errors: {len(self.errors)}")
        print()

        if self.created_locations:
            print("Created Locations:")
            for location in self.created_locations:
                print(f"  - {location['name']} - sys_id: {location['sys_id']}")
            print()

        if self.created_models:
            print("Created Product Models:")
            for model in self.created_models:
                print(f"  - {model['name']} - sys_id: {model['sys_id']}")
            print()

        if self.created_users:
            print("Created Users:")
            for user in self.created_users:
                print(
                    f"  - {user['name']} ({user['email']}) - sys_id: {user['sys_id']}"
                )
            print()

        if self.created_computers:
            print("Created Laptops:")
            for computer in self.created_computers:
                print(
                    f"  - {computer['model']} (S/N: {computer['serial_number']}) - sys_id: {computer['sys_id']}"
                )
            print()

        if self.errors:
            print("Errors:")
            for error in self.errors:
                print(f"  ❌ {error}")
            print()

        print("=" * 80)


def main() -> None:
    """Main function to create evaluation users."""
    # Get credentials from environment
    instance_url = os.getenv("SERVICENOW_INSTANCE_URL")
    username = os.getenv("SERVICENOW_USERNAME")
    password = os.getenv("SERVICENOW_PASSWORD")

    # Validate environment variables
    if not instance_url:
        print("❌ ERROR: SERVICENOW_INSTANCE_URL environment variable is not set")
        sys.exit(1)

    if not username:
        print("❌ ERROR: SERVICENOW_USERNAME environment variable is not set")
        sys.exit(1)

    if not password:
        print("❌ ERROR: SERVICENOW_PASSWORD environment variable is not set")
        sys.exit(1)

    # Create users
    creator = ServiceNowUserCreator(instance_url, username, password)

    try:
        creator.create_all_users(skip_existing=True)
        creator.print_summary()

        if creator.errors:
            print("⚠️  Script completed with errors")
            sys.exit(1)
        else:
            print("🎉 All users and laptops created successfully!")
            sys.exit(0)

    except KeyboardInterrupt:
        print("\n\n⚠️  Script interrupted by user")
        creator.print_summary()
        sys.exit(1)

    except Exception as e:
        print(f"\n\n❌ Unexpected error: {str(e)}")
        import traceback

        traceback.print_exc()
        creator.print_summary()
        sys.exit(1)


if __name__ == "__main__":
    main()
