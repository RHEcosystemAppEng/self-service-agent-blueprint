#!/usr/bin/env python3
"""Integration defaults migration script for existing user configurations."""

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict

# Add the src directory to Python path and import shared_models modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
try:
    from shared_models import configure_logging
    from shared_models.database import get_database_manager
    from shared_models.models import UserIntegrationConfig
    from sqlalchemy import select
except ImportError:
    # If running in container, try direct import
    from shared_models import configure_logging
    from shared_models.database import get_database_manager
    from shared_models.models import UserIntegrationConfig
    from sqlalchemy import select

# Configure logging with structured logging support
logger = configure_logging("smart-defaults-migration")


class IntegrationDefaultsMigration:
    """Migration helper for integration defaults implementation."""

    def __init__(self) -> None:
        """Initialize migration helper."""
        self.db_manager = get_database_manager()

    async def analyze_existing_configs(self) -> Dict[str, Any]:
        """Analyze existing user integration configurations."""
        logger.info("Analyzing existing user integration configurations...")

        async with self.db_manager.get_session() as db:
            # Get all user integration configs
            stmt = select(UserIntegrationConfig)
            result = await db.execute(stmt)
            configs = result.scalars().all()

            # Analyze configurations
            analysis: dict[str, Any] = {
                "total_configs": len(configs),
                "users_with_configs": set(),
                "integration_types": {},
                "enabled_configs": 0,
                "disabled_configs": 0,
            }

            for config in configs:
                analysis["users_with_configs"].add(config.user_id)

                integration_type = config.integration_type.value
                if integration_type not in analysis["integration_types"]:
                    analysis["integration_types"][integration_type] = 0
                analysis["integration_types"][integration_type] += 1

                if config.enabled:
                    analysis["enabled_configs"] += 1
                else:
                    analysis["disabled_configs"] += 1

            analysis["users_with_configs"] = len(analysis["users_with_configs"])

            logger.info(
                "Configuration analysis completed",
                extra={
                    "total_configs": analysis["total_configs"],
                    "users_with_configs": analysis["users_with_configs"],
                    "integration_types": analysis["integration_types"],
                    "enabled_configs": analysis["enabled_configs"],
                    "disabled_configs": analysis["disabled_configs"],
                },
            )

            return analysis

    async def migrate_to_integration_defaults(
        self, dry_run: bool = True, preserve_existing: bool = True
    ) -> Dict[str, Any]:
        """Migrate existing configurations to integration defaults approach.

        Args:
            dry_run: If True, only analyze changes without making them
            preserve_existing: If True, keep existing user configs; if False, remove them
        """
        logger.info(
            "Starting integration defaults migration",
            extra={
                "dry_run": dry_run,
                "preserve_existing": preserve_existing,
            },
        )

        async with self.db_manager.get_session() as db:
            # Get all user integration configs
            stmt = select(UserIntegrationConfig)
            result = await db.execute(stmt)
            configs = result.scalars().all()

            migration_results: Dict[str, Any] = {
                "total_configs": len(configs),
                "users_affected": set(),
                "configs_to_remove": [],
                "configs_to_preserve": [],
            }

            for config in configs:
                migration_results["users_affected"].add(config.user_id)

                if preserve_existing:
                    # Keep existing configs, just mark them as preserved
                    migration_results["configs_to_preserve"].append(
                        {
                            "user_id": config.user_id,
                            "integration_type": config.integration_type.value,
                            "enabled": config.enabled,
                            "priority": config.priority,
                        }
                    )
                    logger.info(
                        "Preserving existing configuration",
                        extra={
                            "user_id": config.user_id,
                            "integration_type": config.integration_type.value,
                            "enabled": config.enabled,
                        },
                    )
                else:
                    # Mark for removal (will use smart defaults instead)
                    migration_results["configs_to_remove"].append(
                        {
                            "user_id": config.user_id,
                            "integration_type": config.integration_type.value,
                            "enabled": config.enabled,
                        }
                    )

                    if not dry_run:
                        # Actually remove the configuration
                        await db.delete(config)
                        logger.info(
                            "Removed user configuration (will use smart defaults)",
                            extra={
                                "user_id": config.user_id,
                                "integration_type": config.integration_type.value,
                            },
                        )

            if not dry_run and not preserve_existing:
                await db.commit()
                logger.info("Database changes committed")

            migration_results["users_affected"] = len(
                migration_results["users_affected"]
            )

            logger.info(
                "Integration defaults migration completed",
                extra={
                    "dry_run": dry_run,
                    "preserve_existing": preserve_existing,
                    "total_configs": migration_results["total_configs"],
                    "users_affected": migration_results["users_affected"],
                    "configs_to_remove": len(migration_results["configs_to_remove"]),
                    "configs_to_preserve": len(
                        migration_results["configs_to_preserve"]
                    ),
                },
            )

            return migration_results

    async def reset_user_to_integration_defaults(
        self, user_id: str, dry_run: bool = True
    ) -> Dict[str, Any]:
        """Reset a specific user to integration defaults.

        Args:
            user_id: User ID to reset
            dry_run: If True, only analyze changes without making them
        """
        logger.info(
            "Resetting user to integration defaults",
            extra={"user_id": user_id, "dry_run": dry_run},
        )

        async with self.db_manager.get_session() as db:
            # Get user's configurations
            stmt = select(UserIntegrationConfig).where(
                UserIntegrationConfig.user_id == user_id
            )
            result = await db.execute(stmt)
            configs = result.scalars().all()

            reset_results: Dict[str, Any] = {
                "user_id": user_id,
                "configs_found": len(configs),
                "configs_to_remove": [],
            }

            for config in configs:
                reset_results["configs_to_remove"].append(
                    {
                        "integration_type": config.integration_type.value,
                        "enabled": config.enabled,
                        "priority": config.priority,
                    }
                )

                if not dry_run:
                    await db.delete(config)
                    logger.info(
                        "Removed user configuration",
                        extra={
                            "user_id": user_id,
                            "integration_type": config.integration_type.value,
                        },
                    )

            if not dry_run:
                await db.commit()
                logger.info("User reset to integration defaults completed")

            return reset_results

    async def close(self) -> None:
        """Close database connections."""
        await self.db_manager.close()


async def main() -> None:
    """Main migration function."""
    logger.info("Starting integration defaults migration process")

    migration = IntegrationDefaultsMigration()

    try:
        # Analyze existing configurations
        analysis = await migration.analyze_existing_configs()

        # Show migration options
        print("\n" + "=" * 60)
        print("INTEGRATION DEFAULTS MIGRATION ANALYSIS")
        print("=" * 60)
        print(f"Total configurations: {analysis['total_configs']}")
        print(f"Users with configurations: {analysis['users_with_configs']}")
        print(f"Integration types: {analysis['integration_types']}")
        print(f"Enabled configurations: {analysis['enabled_configs']}")
        print(f"Disabled configurations: {analysis['disabled_configs']}")
        print("=" * 60)

        # Check if this is a dry run
        dry_run = os.getenv("MIGRATION_DRY_RUN", "true").lower() == "true"
        preserve_existing = os.getenv("PRESERVE_EXISTING", "true").lower() == "true"

        if dry_run:
            print("\nDRY RUN MODE - No changes will be made")
            print("Set MIGRATION_DRY_RUN=false to make actual changes")
        else:
            print("\nLIVE MODE - Changes will be made to the database")

        if preserve_existing:
            print("PRESERVE MODE - Existing user configurations will be kept")
            print(
                "Set PRESERVE_EXISTING=false to remove existing configs and use integration defaults"
            )
        else:
            print("RESET MODE - Existing user configurations will be removed")
            print("Users will use integration defaults instead")

        # Run migration
        migration_results = await migration.migrate_to_integration_defaults(
            dry_run=dry_run, preserve_existing=preserve_existing
        )

        print("\n" + "=" * 60)
        print("MIGRATION RESULTS")
        print("=" * 60)
        print(f"Total configurations processed: {migration_results['total_configs']}")
        print(f"Users affected: {migration_results['users_affected']}")
        print(
            f"Configurations to remove: {len(migration_results['configs_to_remove'])}"
        )
        print(
            f"Configurations to preserve: {len(migration_results['configs_to_preserve'])}"
        )
        print("=" * 60)

        logger.info("Integration defaults migration process completed successfully")

    except Exception as e:
        logger.error(
            "Migration process failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        logger.exception("Full process error traceback:")
        sys.exit(1)
    finally:
        await migration.close()


if __name__ == "__main__":
    asyncio.run(main())
