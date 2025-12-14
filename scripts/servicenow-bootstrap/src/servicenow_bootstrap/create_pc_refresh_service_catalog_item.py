#!/usr/bin/env python3
"""
ServiceNow Service Catalog Automation Script
Creates the PC Refresh service catalog item with all necessary configurations.
"""

import argparse
import json
from typing import Any, Dict, List, Optional

import requests

from .utils import get_env_var


class ServiceNowCatalogAutomation:
    def __init__(self, config: Dict[str, Any]):
        # Get sensitive values from environment variables
        self.instance_url = get_env_var("SERVICENOW_INSTANCE_URL").rstrip("/")
        self.admin_username = get_env_var("SERVICENOW_USERNAME")
        self.admin_password = get_env_var("SERVICENOW_PASSWORD")

        # Get non-sensitive values from config
        self.catalog_config = config["catalog"]

        # Setup session for API calls
        self.session = requests.Session()
        self.session.auth = (self.admin_username, self.admin_password)
        self.session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )

    def get_catalog_sys_id(
        self, catalog_name: str = "Service Catalog"
    ) -> Optional[str]:
        """Get the sys_id for the Service Catalog."""
        url = f"{self.instance_url}/api/now/table/sc_catalog"
        params = {"sysparm_query": f"title={catalog_name}", "sysparm_fields": "sys_id"}

        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("result"):
                return str(data["result"][0]["sys_id"])
            return None

        except requests.RequestException as e:
            print(f"Error getting catalog sys_id: {e}")
            return None

    def get_category_sys_id(self, category_name: str) -> Optional[str]:
        """Get the sys_id for a catalog category."""
        url = f"{self.instance_url}/api/now/table/sc_category"
        params = {"sysparm_query": f"title={category_name}", "sysparm_fields": "sys_id"}

        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("result"):
                return str(data["result"][0]["sys_id"])
            return None

        except requests.RequestException as e:
            print(f"Error getting category sys_id for '{category_name}': {e}")
            return None

    def get_user_criteria_sys_id(self, criteria_name: str) -> Optional[str]:
        """Get the sys_id for a user criteria by name."""
        url = f"{self.instance_url}/api/now/table/user_criteria"
        params = {
            "sysparm_query": f"sys_name={criteria_name}",
            "sysparm_fields": "sys_id",
        }

        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("result"):
                return str(data["result"][0]["sys_id"])
            return None

        except requests.RequestException as e:
            print(f"Error getting user criteria sys_id for '{criteria_name}': {e}")
            return None

    def create_catalog_item(self) -> str:
        """Create the PC Refresh catalog item."""
        print("📦 Creating PC Refresh catalog item...")

        catalog_name = self.catalog_config["name"]

        # Check if catalog item already exists
        check_url = f"{self.instance_url}/api/now/table/sc_cat_item"
        check_params = {"sysparm_query": f"name={catalog_name}"}

        try:
            response = self.session.get(check_url, params=check_params)
            response.raise_for_status()
            data = response.json()

            if data.get("result"):
                print(f"✅ Catalog item '{catalog_name}' already exists")
                return str(data["result"][0]["sys_id"])

            # Get catalog and category sys_ids
            catalog_sys_id = self.get_catalog_sys_id()
            if not catalog_sys_id:
                raise ValueError("Service Catalog not found")

            # Try to find categories (Hardware, Laptops, Hardware Asset)
            categories = []
            for cat_name in ["Hardware", "Laptops", "Hardware Asset"]:
                cat_sys_id = self.get_category_sys_id(cat_name)
                if cat_sys_id:
                    categories.append(cat_sys_id)

            if not categories:
                print(
                    "⚠️  No suitable categories found, creating item without categories"
                )

            # Create catalog item
            item_data = {
                "name": catalog_name,
                "short_description": self.catalog_config["short_description"],
                "description": self.catalog_config["short_description"],
                "sc_catalogs": catalog_sys_id,
                "active": "true",
                "hide_sp": "false",  # Don't hide in Service Portal
                "hide_cart": "true",  # Hide 'Add to cart' button
                "no_quantity": "true",  # Hide quantity selector
                "order": 1000,
                "workflow": "",  # Will use Flow Designer
                "flow_designer_flow": "",  # We'll need to set this manually or find the flow
                "template": "",
            }

            # Add categories if found
            if categories:
                item_data["category"] = categories[0]  # Primary category

            create_url = f"{self.instance_url}/api/now/table/sc_cat_item"
            response = self.session.post(create_url, json=item_data)
            response.raise_for_status()

            result = response.json()
            item_sys_id = str(result["result"]["sys_id"])

            print(f"✅ Catalog item '{catalog_name}' created successfully!")

            # Add additional categories if we have them
            if len(categories) > 1:
                for cat_sys_id in categories[1:]:
                    self.add_item_to_category(item_sys_id, cat_sys_id)

            return item_sys_id

        except requests.RequestException as e:
            print(f"❌ Error creating catalog item: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"Response: {e.response.text}")
            raise

    def add_item_to_category(self, item_sys_id: str, category_sys_id: str) -> None:
        """Add catalog item to additional categories."""
        try:
            # Check if relationship already exists
            check_url = f"{self.instance_url}/api/now/table/sc_cat_item_category"
            check_params = {
                "sysparm_query": f"sc_cat_item={item_sys_id}^sc_category={category_sys_id}"
            }

            response = self.session.get(check_url, params=check_params)
            response.raise_for_status()
            data = response.json()

            if data.get("result"):
                return  # Relationship already exists

            # Create relationship
            relationship_data = {
                "sc_cat_item": item_sys_id,
                "sc_category": category_sys_id,
            }

            create_url = f"{self.instance_url}/api/now/table/sc_cat_item_category"
            response = self.session.post(create_url, json=relationship_data)
            response.raise_for_status()

            print("✅ Added item to additional category")

        except requests.RequestException as e:
            print(f"⚠️  Error adding item to category: {e}")

    def create_user_criteria_assignment(self, item_sys_id: str) -> None:
        """Create user criteria assignment for catalog item."""
        print("👥 Creating user criteria assignment...")

        try:
            # Get the User Criteria ID for "All ACME Corporation employees"
            criteria_name = "All ACME Corporation employees"
            user_criteria_sys_id = self.get_user_criteria_sys_id(criteria_name)

            if not user_criteria_sys_id:
                print(
                    f"⚠️  User criteria '{criteria_name}' not found, skipping assignment"
                )
                return

            # Check if assignment already exists
            check_url = (
                f"{self.instance_url}/api/now/table/sc_cat_item_user_criteria_mtom"
            )
            check_params = {
                "sysparm_query": f"sc_cat_item={item_sys_id}^user_criteria={user_criteria_sys_id}"
            }

            response = self.session.get(check_url, params=check_params)
            response.raise_for_status()
            data = response.json()

            if data.get("result"):
                print("✅ User criteria assignment already exists")
                return

            # Create user criteria assignment
            assignment_data = {
                "sc_cat_item": item_sys_id,
                "user_criteria": user_criteria_sys_id,
            }

            create_url = (
                f"{self.instance_url}/api/now/table/sc_cat_item_user_criteria_mtom"
            )
            response = self.session.post(create_url, json=assignment_data)
            response.raise_for_status()

            print(f"✅ User criteria assignment created for '{criteria_name}'")

        except requests.RequestException as e:
            print(f"❌ Error creating user criteria assignment: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"Response: {e.response.text}")
            raise

    def create_variable(self, item_sys_id: str, variable_data: Dict[str, Any]) -> str:
        """Create a catalog variable for the item."""
        try:
            # Check if variable already exists
            check_url = f"{self.instance_url}/api/now/table/item_option_new"
            check_params = {
                "sysparm_query": f'cat_item={item_sys_id}^name={variable_data["name"]}'
            }

            response = self.session.get(check_url, params=check_params)
            response.raise_for_status()
            data = response.json()

            if data.get("result"):
                print(f"✅ Variable '{variable_data['name']}' already exists")
                return str(data["result"][0]["sys_id"])

            # Create variable
            variable_data["cat_item"] = item_sys_id

            create_url = f"{self.instance_url}/api/now/table/item_option_new"
            response = self.session.post(create_url, json=variable_data)
            response.raise_for_status()

            result = response.json()
            variable_sys_id = str(result["result"]["sys_id"])

            print(f"✅ Created variable '{variable_data['name']}'")
            return variable_sys_id

        except requests.RequestException as e:
            print(
                f"❌ Error creating variable '{variable_data.get('name', 'unknown')}': {e}"
            )
            if hasattr(e, "response") and e.response is not None:
                print(f"Response: {e.response.text}")
            raise

    def create_choice_question(
        self, item_sys_id: str, choices: List[Dict[str, Any]]
    ) -> str:
        """Create the laptop choices question variable."""
        variable_data = {
            "name": "laptop_choices",
            "question_text": "Laptop Choices",
            "type": 5,  # Choice type, Dropdown fixed values
            "mandatory": "true",
            "active": "true",
            "order": 200,
        }

        variable_sys_id = self.create_variable(item_sys_id, variable_data)

        # Create choice options
        for i, choice in enumerate(choices):
            choice_data = {
                "question": variable_sys_id,
                "text": choice["label"],
                "value": choice["value"],
                "order": (i + 1) * 100,
                "price": choice.get("price", 0.0),
                "price_currency": choice.get("price_currency", "USD"),
            }

            self.create_choice_option(choice_data)

        return variable_sys_id

    def create_choice_option(self, choice_data: Dict[str, Any]) -> None:
        """Create a choice option for a variable."""
        try:
            # Check if choice already exists
            check_url = f"{self.instance_url}/api/now/table/question_choice"
            check_params = {
                "sysparm_query": f'question={choice_data["question"]}^text={choice_data["text"]}'
            }

            response = self.session.get(check_url, params=check_params)
            response.raise_for_status()
            data = response.json()

            if data.get("result"):
                print(f"✅ Choice option '{choice_data['text']}' already exists")
                return  # Choice already exists

            # Prepare choice data with pricing information
            choice_payload = {
                "question": choice_data["question"],
                "text": choice_data["text"],
                "value": choice_data["value"],
                "order": choice_data["order"],
            }

            # Add pricing fields if they exist
            if "price" in choice_data:
                choice_payload["misc"] = choice_data["price"]
            if "price_currency" in choice_data:
                choice_payload["price_currency"] = choice_data["price_currency"]

            # Create choice
            create_url = f"{self.instance_url}/api/now/table/question_choice"
            response = self.session.post(create_url, json=choice_payload)
            response.raise_for_status()

            price_info = (
                f" (${choice_data.get('price', 0):.2f})"
                if "price" in choice_data
                else ""
            )
            print(f"✅ Created choice option: {choice_data['text']}{price_info}")

        except requests.RequestException as e:
            print(
                f"⚠️  Error creating choice '{choice_data.get('text', 'unknown')}': {e}"
            )
            if hasattr(e, "response") and e.response is not None:
                print(f"Response: {e.response.text}")

    def create_requested_for_variable(self, item_sys_id: str) -> str:
        """Create the 'Requested for' variable."""
        variable_data = {
            "name": "who_is_this_request_for",
            "question_text": "Who is this request for?",
            "type": 8,  # Reference type
            "reference": "sys_user",  # Reference to User table
            "mandatory": "false",
            "active": "true",
            "order": 100,
        }

        return self.create_variable(item_sys_id, variable_data)

    def setup_catalog(self) -> Dict[str, str]:
        """Complete catalog setup process."""
        print("🚀 Starting catalog setup...")

        # Create catalog item
        item_sys_id = self.create_catalog_item()

        # Create user criteria assignment
        self.create_user_criteria_assignment(item_sys_id)

        # Create variables
        print("📋 Creating catalog variables...")

        # Create "Requested for" variable
        requested_for_var = self.create_requested_for_variable(item_sys_id)

        # Create laptop choices variable
        laptop_choices_var = self.create_choice_question(
            item_sys_id, self.catalog_config["laptop_choices"]
        )

        print("✅ Catalog setup completed!")
        print("\n📝 Manual steps still required:")
        print(
            "1. Set proper access controls (Available for: Any User, Not available for: Guest User)"
        )
        print("2. Submit the catalog item")

        return {
            "catalog_item_sys_id": item_sys_id,
            "requested_for_variable": requested_for_var,
            "laptop_choices_variable": laptop_choices_var,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Automate ServiceNow catalog creation")
    parser.add_argument("--config", required=True, help="Path to configuration file")
    args = parser.parse_args()

    try:
        with open(args.config, "r") as f:
            config = json.load(f)

        automation = ServiceNowCatalogAutomation(config)
        results = automation.setup_catalog()

        print("\n🎉 Catalog setup completed!")
        print(f"📦 Catalog item sys_id: {results['catalog_item_sys_id']}")

    except FileNotFoundError:
        print(f"❌ Configuration file not found: {args.config}")
    except json.JSONDecodeError:
        print(f"❌ Invalid JSON in configuration file: {args.config}")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
