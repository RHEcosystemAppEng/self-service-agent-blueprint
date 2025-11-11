#!/usr/bin/env python3
"""
ServiceNow User Automation Script
Creates and configures the MCP Agent user for ServiceNow integration.
"""

import argparse
import json
import secrets
import string
from typing import Any, Dict

import requests

from .utils import get_env_var


class ServiceNowUserAutomation:
    def __init__(self, config: Dict[str, Any]):
        # Get sensitive values from environment variables
        self.instance_url = get_env_var("SERVICENOW_INSTANCE_URL").rstrip("/")
        self.admin_username = get_env_var("SERVICENOW_USERNAME")
        self.admin_password = get_env_var("SERVICENOW_PASSWORD")

        # Get non-sensitive values from config
        self.agent_config = config["servicenow"]["agent_user"]

        # Setup session for API calls
        self.session = requests.Session()
        self.session.auth = (self.admin_username, self.admin_password)
        self.session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )

    def generate_password(self, length: int = 16) -> str:
        """Generate a secure random password."""
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        password = "".join(secrets.choice(alphabet) for i in range(length))
        return password

    def check_user_exists(self, user_id: str) -> bool:
        """Check if user already exists."""
        url = f"{self.instance_url}/api/now/table/sys_user"
        params = {"sysparm_query": f"user_name={user_id}"}

        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return len(data.get("result", [])) > 0
        except requests.RequestException as e:
            print(f"Error checking if user exists: {e}")
            return False

    def create_user(self) -> Dict[str, str]:
        """Create the MCP Agent user."""
        user_id = self.agent_config["user_id"]

        if self.check_user_exists(user_id):
            print(f"User '{user_id}' already exists. Skipping creation.")
            return {"user_id": user_id, "password": "existing_user"}

        # Generate password
        password = self.generate_password()

        user_data = {
            "user_name": user_id,
            "first_name": self.agent_config["first_name"],
            "last_name": self.agent_config["last_name"],
            "user_password": password,
            "password_needs_reset": "false",
            "active": "true",
            "locked_out": "false",
            "identity_type": self.agent_config["identity_type"],
        }

        url = f"{self.instance_url}/api/now/table/sys_user"

        try:
            response = self.session.post(url, json=user_data)
            response.raise_for_status()

            result = response.json()
            print(f"✅ User '{user_id}' created successfully!")
            print(f"🔐 Generated password: {password}")
            print("⚠️  Please save this password securely!")

            return {
                "user_id": user_id,
                "password": password,
                "sys_id": result["result"]["sys_id"],
            }

        except requests.RequestException as e:
            print(f"❌ Error creating user: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"Response: {e.response.text}")
            raise

    def get_user_sys_id(self, user_id: str) -> str:
        """Get the sys_id for a user."""
        url = f"{self.instance_url}/api/now/table/sys_user"
        params = {"sysparm_query": f"user_name={user_id}", "sysparm_fields": "sys_id"}

        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("result"):
                return str(data["result"][0]["sys_id"])
            else:
                raise ValueError(f"User '{user_id}' not found")

        except requests.RequestException as e:
            print(f"Error getting user sys_id: {e}")
            raise

    def assign_roles(self, user_sys_id: str) -> None:
        """Assign necessary roles to the user."""
        # Get roles from configuration
        roles_to_assign = self.agent_config["roles_to_assign"]

        for role_name in roles_to_assign:
            try:
                # First, get the role sys_id
                role_url = f"{self.instance_url}/api/now/table/sys_user_role"
                role_params = {
                    "sysparm_query": f"name={role_name}",
                    "sysparm_fields": "sys_id",
                }

                role_response = self.session.get(role_url, params=role_params)
                role_response.raise_for_status()
                role_data = role_response.json()

                if not role_data.get("result"):
                    print(f"⚠️  Role '{role_name}' not found, skipping...")
                    continue

                role_sys_id = role_data["result"][0]["sys_id"]

                # Check if user already has this role
                has_role_url = f"{self.instance_url}/api/now/table/sys_user_has_role"
                has_role_params = {
                    "sysparm_query": f"user={user_sys_id}^role={role_sys_id}",
                    "sysparm_fields": "sys_id",
                }

                has_role_response = self.session.get(
                    has_role_url, params=has_role_params
                )
                has_role_response.raise_for_status()
                has_role_data = has_role_response.json()

                if has_role_data.get("result"):
                    print(f"✅ User already has role '{role_name}'")
                    continue

                # Assign the role
                assignment_data = {"user": user_sys_id, "role": role_sys_id}

                assignment_url = f"{self.instance_url}/api/now/table/sys_user_has_role"
                assignment_response = self.session.post(
                    assignment_url, json=assignment_data
                )
                assignment_response.raise_for_status()

                print(f"✅ Assigned role '{role_name}' to user")

            except requests.RequestException as e:
                print(f"⚠️  Error assigning role '{role_name}': {e}")
                continue

    def setup_user(self) -> Dict[str, str]:
        """Complete user setup process."""
        print("🚀 Starting user setup...")

        # Create user
        user_info = self.create_user()

        if user_info["password"] != "existing_user":
            # Get sys_id if not already available
            if "sys_id" not in user_info:
                user_info["sys_id"] = self.get_user_sys_id(user_info["user_id"])

            # Assign roles
            print("🔐 Assigning roles...")
            self.assign_roles(user_info["sys_id"])
        else:
            print("ℹ️  User already exists, skipping role assignment")

        print("✅ User setup completed!")
        return user_info


def main() -> None:
    parser = argparse.ArgumentParser(description="Automate ServiceNow user creation")
    parser.add_argument("--config", required=True, help="Path to configuration file")
    args = parser.parse_args()

    try:
        with open(args.config, "r") as f:
            config = json.load(f)

        automation = ServiceNowUserAutomation(config)
        user_info = automation.setup_user()

        # Update config with generated password
        if user_info["password"] != "existing_user":
            config["servicenow"]["agent_user"]["password"] = user_info["password"]

            # Write updated config back
            config_path = args.config.replace(".example.json", ".json")
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)
            print(f"💾 Updated configuration saved to: {config_path}")

    except FileNotFoundError:
        print(f"❌ Configuration file not found: {args.config}")
    except json.JSONDecodeError:
        print(f"❌ Invalid JSON in configuration file: {args.config}")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
