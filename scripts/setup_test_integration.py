#!/usr/bin/env python3
"""
Script to set up test user integration configurations for E2E testing.
"""

import asyncio
import os
import sys
from datetime import datetime

# Add the shared-db src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared-db", "src"))

# Import after path modification
from shared_db.models import IntegrationType, UserIntegrationConfig  # noqa: E402
from shared_db.session import DatabaseManager  # noqa: E402
from sqlalchemy import select  # noqa: E402


async def setup_test_integration(user_id: str = "e2e-test-user"):
    """Set up test integration configuration for a user."""
    print(f"🔧 Setting up test integration for user: {user_id}")

    # Initialize database
    db_manager = DatabaseManager()

    async with db_manager.get_session() as db:
        # Check if config already exists
        stmt = select(UserIntegrationConfig).where(
            UserIntegrationConfig.user_id == user_id,
            UserIntegrationConfig.integration_type == IntegrationType.TEST,
        )
        result = await db.execute(stmt)
        existing_config = result.scalar_one_or_none()

        if existing_config:
            print(f"✅ Test integration config already exists for {user_id}")
            print(f"   Config: {existing_config.config}")
            return existing_config

        # Create new test integration config
        test_config = UserIntegrationConfig(
            user_id=user_id,
            integration_type=IntegrationType.TEST,
            enabled=True,
            config={
                "test_id": f"test-{user_id}-{int(datetime.now().timestamp())}",
                "test_name": "E2E Test Integration",
                "output_format": "json",
                "include_metadata": True,
            },
            priority=1,
            retry_count=3,
            retry_delay_seconds=60,
            created_by="setup_script",
        )

        db.add(test_config)
        await db.commit()
        await db.refresh(test_config)

        print(f"✅ Created test integration config for {user_id}")
        print(f"   Integration Type: {test_config.integration_type}")
        print(f"   Config: {test_config.config}")
        print(f"   Priority: {test_config.priority}")
        print(f"   Enabled: {test_config.enabled}")

        return test_config


async def setup_slack_integration(
    user_id: str, channel_id: str = None, user_email: str = None
):
    """Set up Slack integration configuration for a user."""
    print(f"💬 Setting up Slack integration for user: {user_id}")

    if not channel_id and not user_email:
        print(
            "❌ Either channel_id or user_email must be provided for Slack integration"
        )
        return None

    # Initialize database
    db_manager = DatabaseManager()

    async with db_manager.get_session() as db:
        # Check if config already exists
        stmt = select(UserIntegrationConfig).where(
            UserIntegrationConfig.user_id == user_id,
            UserIntegrationConfig.integration_type == IntegrationType.SLACK,
        )
        result = await db.execute(stmt)
        existing_config = result.scalar_one_or_none()

        if existing_config:
            print(f"✅ Slack integration config already exists for {user_id}")
            print(f"   Config: {existing_config.config}")
            return existing_config

        # Build Slack config
        slack_config = {
            "workspace_id": "your-workspace-id",
            "thread_replies": True,
            "include_agent_info": True,
        }

        if channel_id:
            slack_config["channel_id"] = channel_id
        if user_email:
            slack_config["user_email"] = user_email

        # Create new Slack integration config
        integration_config = UserIntegrationConfig(
            user_id=user_id,
            integration_type=IntegrationType.SLACK,
            enabled=True,
            config=slack_config,
            priority=2,  # Higher priority than test
            retry_count=3,
            retry_delay_seconds=60,
            created_by="setup_script",
        )

        db.add(integration_config)
        await db.commit()
        await db.refresh(integration_config)

        print(f"✅ Created Slack integration config for {user_id}")
        print(f"   Integration Type: {integration_config.integration_type}")
        print(f"   Config: {integration_config.config}")
        print(f"   Priority: {integration_config.priority}")
        print(f"   Enabled: {integration_config.enabled}")

        return integration_config


async def list_user_integrations(user_id: str):
    """List all integration configurations for a user."""
    print(f"📋 Integration configurations for user: {user_id}")

    db_manager = DatabaseManager()

    async with db_manager.get_session() as db:
        stmt = (
            select(UserIntegrationConfig)
            .where(UserIntegrationConfig.user_id == user_id)
            .order_by(UserIntegrationConfig.priority.desc())
        )

        result = await db.execute(stmt)
        configs = result.scalars().all()

        if not configs:
            print(f"   No integration configurations found for {user_id}")
            return []

        for i, config in enumerate(configs, 1):
            print(f"   {i}. {config.integration_type.value}")
            print(f"      Enabled: {config.enabled}")
            print(f"      Priority: {config.priority}")
            print(f"      Config: {config.config}")
            print(f"      Created: {config.created_at}")
            print()

        return configs


async def main():
    """Main function to set up test integrations."""
    import argparse

    parser = argparse.ArgumentParser(description="Set up integration configurations")
    parser.add_argument(
        "--user-id", default="e2e-test-user", help="User ID to configure"
    )
    parser.add_argument(
        "--setup-test", action="store_true", help="Set up test integration"
    )
    parser.add_argument(
        "--setup-slack", action="store_true", help="Set up Slack integration"
    )
    parser.add_argument("--slack-channel", help="Slack channel ID for integration")
    parser.add_argument("--slack-email", help="Slack user email for DM integration")
    parser.add_argument(
        "--list", action="store_true", help="List existing integrations"
    )

    args = parser.parse_args()

    if args.list:
        await list_user_integrations(args.user_id)

    if args.setup_test:
        await setup_test_integration(args.user_id)

    if args.setup_slack:
        await setup_slack_integration(
            args.user_id, channel_id=args.slack_channel, user_email=args.slack_email
        )

    if not any([args.list, args.setup_test, args.setup_slack]):
        print("🚀 Setting up default test integration...")
        await setup_test_integration(args.user_id)
        await list_user_integrations(args.user_id)


if __name__ == "__main__":
    asyncio.run(main())
