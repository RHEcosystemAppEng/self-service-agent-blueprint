#!/usr/bin/env python3
"""
ServiceNow API Configuration Automation Script
Creates API keys, authentication profiles, and access policies for ServiceNow integration.
"""

import argparse
import json
from typing import Any, Dict, Optional

import requests


class ServiceNowAPIAutomation:
    def __init__(self, config: Dict[str, Any]):
        self.instance_url = config["servicenow"]["instance_url"].rstrip("/")
        self.admin_username = config["servicenow"]["admin_username"]
        self.admin_password = config["servicenow"]["admin_password"]
        self.agent_user_id = config["servicenow"]["agent_user"]["user_id"]
        self.api_key_name = config["servicenow"]["api_key_name"]

        # Setup session for API calls
        self.session = requests.Session()
        self.session.auth = (self.admin_username, self.admin_password)
        self.session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )

    def get_user_sys_id(self, user_id: str) -> str:
        """Get the sys_id for a user."""
        url = f"{self.instance_url}/api/now/table/sys_user"
        params = {"sysparm_query": f"user_name={user_id}", "sysparm_fields": "sys_id"}

        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("result"):
                return data["result"][0]["sys_id"]
            else:
                raise ValueError(f"User '{user_id}' not found")

        except requests.RequestException as e:
            print(f"Error getting user sys_id: {e}")
            raise

    def create_api_key(self) -> Dict[str, str]:
        """Create API key for the MCP agent user."""
        print("🔑 Creating API key...")

        # Check if API key already exists
        check_url = f"{self.instance_url}/api/now/table/api_key"
        check_params = {"sysparm_query": f"name={self.api_key_name}"}

        try:
            response = self.session.get(check_url, params=check_params)
            response.raise_for_status()
            data = response.json()

            if data.get("result"):
                print(f"✅ API key '{self.api_key_name}' already exists")
                api_key_record = data["result"][0]
                return {
                    "api_key_sys_id": api_key_record["sys_id"],
                    "token": api_key_record.get("token", "hidden"),
                }

            # Get user sys_id
            user_sys_id = self.get_user_sys_id(self.agent_user_id)

            # Create API key
            api_key_data = {
                "name": self.api_key_name,
                "user": user_sys_id,
                "active": "true",
            }

            create_url = f"{self.instance_url}/api/now/table/api_key"
            response = self.session.post(create_url, json=api_key_data)
            response.raise_for_status()

            result = response.json()
            api_key_info = result["result"]

            print(f"✅ API key '{self.api_key_name}' created successfully!")
            print(
                f"🔐 API Key Token: {api_key_info.get('token', 'Check ServiceNow instance for token')}"
            )
            print("⚠️  Please save this token securely!")

            return {
                "api_key_sys_id": api_key_info["sys_id"],
                "token": api_key_info.get("token", "hidden"),
            }

        except requests.RequestException as e:
            print(f"❌ Error creating API key: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"Response: {e.response.text}")
            raise

    def create_auth_profile(self, name: str, auth_type: str) -> str:
        """Create authentication profile."""
        print(f"🔐 Creating authentication profile: {name}")

        # Check if profile already exists
        check_url = f"{self.instance_url}/api/now/table/inbound_auth_profile"
        check_params = {"sysparm_query": f"name={name}"}

        try:
            response = self.session.get(check_url, params=check_params)
            response.raise_for_status()
            data = response.json()

            if data.get("result"):
                print(f"✅ Authentication profile '{name}' already exists")
                return data["result"][0]["sys_id"]

            if auth_type == "api_key":
                url = "http_key_auth"
                profile_data = {"name": name, "auth_parameter": "Header for API Key"}
            else:
                url = "std_http_auth"
                profile_data = {"name": name, "type": "basic_auth"}

            create_url = f"{self.instance_url}/api/now/table/{url}"
            response = self.session.post(create_url, json=profile_data)
            response.raise_for_status()

            result = response.json()
            profile_sys_id = result["result"]["sys_id"]

            print(f"✅ Authentication profile '{name}' created successfully!")
            return profile_sys_id

        except requests.RequestException as e:
            print(f"❌ Error creating authentication profile '{name}': {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"Response: {e.response.text}")
            raise

    def create_api_access_policy(
        self, policy_name: str, api_name: str, auth_profiles: list
    ) -> str:
        """Create API access policy."""
        print(f"🛡️  Creating API access policy: {policy_name}")

        # Check if policy already exists
        check_url = f"{self.instance_url}/api/now/table/sys_api_access_policy"
        check_params = {"sysparm_query": f"name={policy_name}"}

        try:
            response = self.session.get(check_url, params=check_params)
            response.raise_for_status()
            data = response.json()

            if data.get("result"):
                print(f"✅ API access policy '{policy_name}' already exists")
                return data["result"][0]["sys_id"]

            # Create access policy with fields matching the working structure
            policy_data = {
                "name": policy_name,
                "active": "true",
                "apply_all_methods": "true",
                "apply_all_resources": "true",
                "apply_all_versions": "true",
            }

            # For some reason service now is ignoring this value
            # The following example values haven't worked: b4558e83c3a302006f333b0ac3d3ae8e, Service Catalog API, servicecatalog, service_catalog_api, service-catalog-api
            policy_data["api"] = api_name

            # Add specific API paths based on the API type
            if "SC" in policy_name or "Service Catalog" in api_name:
                policy_data["api_path"] = "sn_sc/servicecatalog"
            elif "Table" in api_name:
                policy_data["api_path"] = "now/table"
            elif "UI" in api_name:
                policy_data["api_path"] = "now/ui"

            create_url = f"{self.instance_url}/api/now/table/sys_api_access_policy"
            response = self.session.post(create_url, json=policy_data)
            response.raise_for_status()

            result = response.json()
            policy_sys_id = result["result"]["sys_id"]

            # Add authentication profiles to the policy
            #             for auth_profile_sys_id in auth_profiles:
            #                 if auth_profile_sys_id:  # Only add if we have a valid sys_id
            #                     auth_data = {
            #                         'api_access_policy': policy_sys_id,
            #                         'auth_profile': auth_profile_sys_id
            #                     }
            #
            #                     auth_url = f"{self.instance_url}/api/now/table/sys_api_access_policy"
            #                     auth_response = self.session.post(auth_url, json=auth_data)
            #                     auth_response.raise_for_status()

            print(f"✅ API access policy '{policy_name}' created successfully!")
            return policy_sys_id

        except requests.RequestException as e:
            print(f"❌ Error creating API access policy '{policy_name}': {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"Response: {e.response.text}")
            raise

    def setup_api_configuration(self) -> Dict[str, Any]:
        """Complete API configuration setup."""
        print("🚀 Starting API configuration setup...")

        results = {}

        # Create API key
        api_key_info = self.create_api_key()
        results["api_key"] = api_key_info

        # Create authentication profiles
        api_key_profile_sys_id = self.create_auth_profile("API Key", "api_key")
        basic_auth_profile_sys_id = self.create_auth_profile("Basic Auth", "basic")

        results["auth_profiles"] = {
            "api_key": api_key_profile_sys_id,
            "basic_auth": basic_auth_profile_sys_id,
        }

        # Create API access policies
        auth_profiles = [api_key_profile_sys_id, basic_auth_profile_sys_id]

        # Service Catalog API
        sc_policy_sys_id = self.create_api_access_policy(
            "MCP Agent - SC", "Service Catalog API", auth_profiles
        )
        results["sc_policy"] = sc_policy_sys_id

        # Table API
        table_policy_sys_id = self.create_api_access_policy(
            "MCP Agent - Tables", "Table API", auth_profiles
        )
        results["table_policy"] = table_policy_sys_id

        # UI GlideRecord API
        ui_policy_sys_id = self.create_api_access_policy(
            "MCP Agent - UI", "UI GlideRecord API", auth_profiles
        )
        results["ui_policy"] = ui_policy_sys_id

        print("✅ API configuration setup completed!")
        return results


def main():
    parser = argparse.ArgumentParser(
        description="Automate ServiceNow API configuration"
    )
    parser.add_argument("--config", required=True, help="Path to configuration file")
    args = parser.parse_args()

    try:
        with open(args.config, "r") as f:
            config = json.load(f)

        automation = ServiceNowAPIAutomation(config)
        results = automation.setup_api_configuration()

        # Update config with API key token if available
        if (
            "token" in results.get("api_key", {})
            and results["api_key"]["token"] != "hidden"
        ):
            config["servicenow"]["api_key_token"] = results["api_key"]["token"]

            # Write updated config back
            config_path = args.config.replace(".example.json", ".json")
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)
            print(f"💾 Updated configuration saved to: {config_path}")

        print(
            "\n🎉 Setup completed! You can now use the ServiceNow instance with your automation."
        )
        print("\n📝 Next steps:")
        print("1. Verify the API key token in your ServiceNow instance")
        print("2. Test the API access with the created credentials")
        print("3. Run the catalog automation script to create the PC Refresh catalog")

    except FileNotFoundError:
        print(f"❌ Configuration file not found: {args.config}")
    except json.JSONDecodeError:
        print(f"❌ Invalid JSON in configuration file: {args.config}")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
