#!/usr/bin/env python3
"""
ServiceNow PDI Setup Orchestration Script
Main script that orchestrates the complete ServiceNow PDI setup process.
"""

import argparse
import json
import sys
from typing import Any, Dict

from .create_evaluation_users import ServiceNowUserCreator
from .create_mcp_agent_api_key import ServiceNowAPIAutomation
from .create_mcp_agent_user import ServiceNowUserAutomation
from .create_pc_refresh_service_catalog_item import ServiceNowCatalogAutomation
from .utils import get_env_var


def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from JSON file and override with environment variables."""
    try:
        with open(config_path, "r") as f:
            config: Dict[str, Any] = json.load(f)

        # Override sensitive values with environment variables
        config["servicenow"]["instance_url"] = get_env_var("SERVICENOW_INSTANCE_URL")
        config["servicenow"]["admin_username"] = get_env_var("SERVICENOW_USERNAME")
        config["servicenow"]["admin_password"] = get_env_var("SERVICENOW_PASSWORD")

        return config
    except FileNotFoundError:
        print(f"❌ Configuration file not found: {config_path}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"❌ Invalid JSON in configuration file: {config_path}")
        sys.exit(1)


def validate_config(config: Dict[str, Any]) -> bool:
    """Validate that required configuration fields are present."""
    required_fields = [
        # Note: instance_url, admin_username, admin_password now come from env vars
        "servicenow.agent_user.user_id",
        "servicenow.agent_user.first_name",
        "servicenow.agent_user.last_name",
        "catalog.name",
        "catalog.short_description",
        "catalog.laptop_choices",
    ]

    missing_fields = []

    for field in required_fields:
        keys = field.split(".")
        current = config

        try:
            for key in keys:
                current = current[key]
        except (KeyError, TypeError):
            missing_fields.append(field)

    if missing_fields:
        print("❌ Missing required configuration fields:")
        for field in missing_fields:
            print(f"   - {field}")
        return False

    return True


def print_banner() -> None:
    """Print a welcome banner."""
    print("=" * 60)
    print("🤖 ServiceNow PDI Setup Automation")
    print("=" * 60)
    print()


def print_step(step_num: int, step_name: str) -> None:
    """Print step header."""
    print(f"\n{'=' * 50}")
    print(f"Step {step_num}: {step_name}")
    print(f"{'=' * 50}")


def confirm_proceed(message: str) -> bool:
    """Ask user for confirmation before proceeding."""
    while True:
        response = input(f"{message} (y/n): ").lower().strip()
        if response in ["y", "yes"]:
            return True
        elif response in ["n", "no"]:
            return False
        else:
            print("Please enter 'y' or 'n'")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Complete ServiceNow PDI setup automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  setup-servicenow --config config.json
  setup-servicenow --config config.json --skip-user
  setup-servicenow --config config.json --skip-api --skip-catalog
  setup-servicenow --config config.json --skip-evaluation-users
        """,
    )

    parser.add_argument("--config", required=True, help="Path to configuration file")
    parser.add_argument(
        "--skip-user", action="store_true", help="Skip user creation step"
    )
    parser.add_argument(
        "--skip-api", action="store_true", help="Skip API configuration step"
    )
    parser.add_argument(
        "--skip-catalog", action="store_true", help="Skip catalog creation step"
    )
    parser.add_argument(
        "--skip-evaluation-users",
        action="store_true",
        help="Skip evaluation users creation step",
    )
    parser.add_argument(
        "--no-confirm", action="store_true", help="Skip confirmation prompts"
    )

    args = parser.parse_args()

    print_banner()

    # Load and validate configuration
    print("📋 Loading configuration...")
    config = load_config(args.config)

    if not validate_config(config):
        print("\n❌ Configuration validation failed. Please check your config file.")
        sys.exit(1)

    print("✅ Configuration loaded and validated successfully!")

    # Show what will be done
    print(f"\n🎯 Setup target: {config['servicenow']['instance_url']}")
    print(f"👤 Admin user: {config['servicenow']['admin_username']}")
    print(f"🤖 Agent user: {config['servicenow']['agent_user']['user_id']}")
    print(f"📦 Catalog item: {config['catalog']['name']}")

    steps_to_run = []
    if not args.skip_user:
        steps_to_run.append("Create MCP Agent user")
    if not args.skip_api:
        steps_to_run.append("Configure API keys and authentication")
    if not args.skip_catalog:
        steps_to_run.append("Create PC Refresh catalog item")
    if not args.skip_evaluation_users:
        steps_to_run.append("Create evaluation users and test data")

    if not steps_to_run:
        print("\n⚠️  All steps are being skipped. Nothing to do!")
        sys.exit(0)

    print("\n📝 Steps to execute:")
    for i, step in enumerate(steps_to_run, 1):
        print(f"   {i}. {step}")

    # Confirm before proceeding
    if not args.no_confirm:
        if not confirm_proceed("\n🚀 Proceed with setup?"):
            print("🛑 Setup cancelled by user.")
            sys.exit(0)

    print("\n🚀 Starting setup process...\n")

    results = {}

    try:
        # Step 1: Create user
        if not args.skip_user:
            print_step(1, "Create MCP Agent User")
            user_automation = ServiceNowUserAutomation(config)
            user_results = user_automation.setup_user()
            results["user"] = user_results

        # Step 2: Configure API
        if not args.skip_api:
            print_step(2, "Configure API Keys and Authentication")
            api_automation = ServiceNowAPIAutomation(config)
            api_results = api_automation.setup_api_configuration()
            results["api"] = api_results

        # Step 3: Create catalog
        if not args.skip_catalog:
            print_step(3, "Create PC Refresh Catalog Item")
            catalog_automation = ServiceNowCatalogAutomation(config)
            catalog_results = catalog_automation.setup_catalog()
            results["catalog"] = catalog_results

        # Step 4: Create evaluation users
        if not args.skip_evaluation_users:
            print_step(4, "Create Evaluation Users and Test Data")
            user_creator = ServiceNowUserCreator(
                config["servicenow"]["instance_url"],
                config["servicenow"]["admin_username"],
                config["servicenow"]["admin_password"],
            )
            user_creator.create_all_users(skip_existing=True)
            user_creator.print_summary()

            # Store results for summary
            results["evaluation_users"] = {
                "users_created": str(len(user_creator.created_users)),
                "computers_created": str(len(user_creator.created_computers)),
                "models_created": str(len(user_creator.created_models)),
                "locations_created": str(len(user_creator.created_locations)),
                "errors": str(len(user_creator.errors)),
            }

        # Print final summary
        print("\n" + "=" * 60)
        print("🎉 Setup completed successfully!")
        print("=" * 60)

        if results.get("user"):
            print(f"👤 User created: {config['servicenow']['agent_user']['user_id']}")

        if results.get("api", {}).get("api_key"):
            print(f"🔑 API Key created: {config['servicenow']['api_key_name']}")
            print(
                "🔐 Token: login into Service Account -> All -> Search for 'REST API Key' for this info (set SERVICENOW_API_KEY)"
            )

        if results.get("catalog"):
            print(
                f"📦 Catalog item created: {config['catalog']['name']} (set SERVICENOW_LAPTOP_REFRESH_ID={results['catalog']['catalog_item_sys_id']})"
            )

        if results.get("evaluation_users"):
            eval_results = results["evaluation_users"]
            print(
                f"👥 Evaluation users created: {eval_results['users_created']} users, {eval_results['computers_created']} computers"
            )
            if int(eval_results["errors"]) > 0:
                print(f"⚠️  Evaluation users had {eval_results['errors']} errors")

        print("\n📝 Next steps:")
        print("1. Log into your ServiceNow instance to verify the setup")
        print("2. Set proper access controls on the catalog item")
        print("3. Test the catalog item in the Service Portal")
        print("4. Update your blueprint configuration with the new credentials")
        if results.get("evaluation_users"):
            print(
                "5. Verify the evaluation users and test data are properly configured"
            )

    except KeyboardInterrupt:
        print("\n\n🛑 Setup interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Setup failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
