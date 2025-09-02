"""Integration defaults service for user integration configurations."""

import os
from typing import Any, Dict, List, Optional

import structlog
from shared_models.models import IntegrationDefaultConfig, IntegrationType
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


class IntegrationDefaultsService:
    """Service for managing integration defaults with user overrides."""

    def __init__(self):
        """Initialize integration defaults service."""
        self.default_integrations = self._load_default_integrations()
        self.last_health_status = {}

        logger.info(
            "Integration defaults service initialized",
            default_integrations=list(self.default_integrations.keys()),
        )

    def _load_default_integrations(self) -> Dict[str, Dict[str, Any]]:
        """Load default integration configurations from environment."""
        # Default configurations - will be updated with health check results
        defaults = {
            "SLACK": {
                "enabled": False,  # Will be updated by health check
                "priority": 1,
                "retry_count": 3,
                "retry_delay_seconds": 60,
                "config": {
                    "thread_replies": False,
                    "mention_user": False,
                    "include_agent_info": True,
                },
            },
            "EMAIL": {
                "enabled": False,  # Will be updated by health check
                "priority": 2,
                "retry_count": 3,
                "retry_delay_seconds": 60,
                "config": {"include_agent_info": True},
            },
            "WEBHOOK": {
                "enabled": False,  # Controlled by enabled flag only (no health check)
                "priority": 3,
                "retry_count": 1,
                "retry_delay_seconds": 30,
                "config": {},
            },
            "SMS": {
                "enabled": False,  # Always disabled by default (no handler available)
                "priority": 4,
                "retry_count": 2,
                "retry_delay_seconds": 45,
                "config": {},
            },
            "TEST": {
                "enabled": False,  # Will be updated by health check
                "priority": 5,
                "retry_count": 1,
                "retry_delay_seconds": 10,
                "config": {},
            },
        }

        # Override with environment variables if available
        for integration_type in defaults:
            env_prefix = f"INTEGRATION_DEFAULTS_{integration_type}_"

            # Check for enabled override
            enabled_env = os.getenv(f"{env_prefix}ENABLED")
            if enabled_env is not None:
                defaults[integration_type]["enabled"] = enabled_env.lower() == "true"

            # Check for priority override
            priority_env = os.getenv(f"{env_prefix}PRIORITY")
            if priority_env is not None:
                try:
                    defaults[integration_type]["priority"] = int(priority_env)
                except ValueError:
                    logger.warning(
                        "Invalid priority value for integration defaults",
                        integration_type=integration_type,
                        value=priority_env,
                    )

            # Check for retry count override
            retry_count_env = os.getenv(f"{env_prefix}RETRY_COUNT")
            if retry_count_env is not None:
                try:
                    defaults[integration_type]["retry_count"] = int(retry_count_env)
                except ValueError:
                    logger.warning(
                        "Invalid retry count value for integration defaults",
                        integration_type=integration_type,
                        value=retry_count_env,
                    )

            # Check for retry delay override
            retry_delay_env = os.getenv(f"{env_prefix}RETRY_DELAY_SECONDS")
            if retry_delay_env is not None:
                try:
                    defaults[integration_type]["retry_delay_seconds"] = int(
                        retry_delay_env
                    )
                except ValueError:
                    logger.warning(
                        "Invalid retry delay value for integration defaults",
                        integration_type=integration_type,
                        value=retry_delay_env,
                    )

        return defaults

    async def initialize_defaults(self, db: AsyncSession) -> None:
        """Initialize default configs in the database on startup."""
        await self._refresh_default_configs(db)
        logger.info("Integration defaults initialized in database")

    async def _refresh_default_configs(self, db: AsyncSession) -> None:
        """Refresh default configs in database based on current health status."""
        # Clear existing defaults
        await db.execute(delete(IntegrationDefaultConfig))

        # Check current health status
        health_status = await self._check_integration_health()

        # Insert new defaults
        for integration_type, config in self.default_integrations.items():
            # Check if enabled environment variable allows integration
            enabled_env = os.getenv(f"INTEGRATION_DEFAULTS_{integration_type}_ENABLED")
            health_check_passed = health_status.get(integration_type, False)

            if enabled_env is not None:
                # Environment variable must be true AND health check must pass
                env_allows = enabled_env.lower() == "true"
                enabled = env_allows and health_check_passed
                logger.info(
                    "Integration status determined by environment variable and health check",
                    integration_type=integration_type,
                    enabled=enabled,
                    env_allows=env_allows,
                    health_check_passed=health_check_passed,
                    env_value=enabled_env,
                )
            else:
                # Use health check result only
                enabled = health_check_passed

            default_config = IntegrationDefaultConfig(
                integration_type=IntegrationType(integration_type),
                enabled=enabled,
                priority=config["priority"],
                retry_count=config["retry_count"],
                retry_delay_seconds=config["retry_delay_seconds"],
                config=config["config"],
                created_by="system",
            )
            db.add(default_config)

        await db.commit()
        logger.info(
            "Integration defaults refreshed in database", health_status=health_status
        )

    async def _check_integration_health(self) -> Dict[str, bool]:
        """Check health status of all integrations."""
        health_status = {}

        # Check Slack health
        try:
            from .slack import SlackIntegrationHandler

            slack_handler = SlackIntegrationHandler()
            health_status["SLACK"] = await slack_handler.health_check()
        except Exception as e:
            logger.warning("Slack integration health check failed", error=str(e))
            health_status["SLACK"] = False

        # Check Email health
        try:
            from .email import EmailIntegrationHandler

            email_handler = EmailIntegrationHandler()
            health_status["EMAIL"] = await email_handler.health_check()
        except Exception as e:
            logger.warning("Email integration health check failed", error=str(e))
            health_status["EMAIL"] = False

        # Check Test health
        try:
            from .test import TestIntegrationHandler

            test_handler = TestIntegrationHandler()
            health_status["TEST"] = await test_handler.health_check()
        except Exception as e:
            logger.warning("Test integration health check failed", error=str(e))
            health_status["TEST"] = False

        # Controlled by enabled flag only (no meaningful health check)
        health_status["WEBHOOK"] = False
        health_status["SMS"] = False

        return health_status

    async def get_user_integrations(
        self,
        user_id: str,
        user_overrides: Optional[Dict[str, Any]] = None,
        db: Optional[AsyncSession] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Get integration configurations for a user using integration defaults with overrides.

        Args:
            user_id: User identifier
            user_overrides: Optional user-specific overrides
            db: Database session for persisting default configs
            context: Optional context information (e.g., channel_id for Slack)

        Returns:
            List of integration configurations
        """
        if not db:
            logger.warning("No database session provided for integration defaults")
            return []

        # Check if database is in sync with current health status
        current_health = await self._check_integration_health()
        current_enabled = set(
            integration for integration, enabled in current_health.items() if enabled
        )

        # Get currently enabled integrations from database
        stmt = select(IntegrationDefaultConfig).where(IntegrationDefaultConfig.enabled)
        result = await db.execute(stmt)
        db_configs = result.scalars().all()
        db_enabled = set(config.integration_type.value for config in db_configs)

        # Only refresh if the enabled integrations don't match
        if current_enabled != db_enabled:
            logger.info(
                "Integration health status mismatch, refreshing database",
                current_enabled=current_enabled,
                db_enabled=db_enabled,
                health_status=current_health,
            )
            await self._refresh_default_configs(db)
            self.last_health_status = current_health
        else:
            logger.debug(
                "Integration health status matches database, no refresh needed"
            )
            self.last_health_status = current_health

        # Get defaults from database
        stmt = select(IntegrationDefaultConfig).where(IntegrationDefaultConfig.enabled)
        result = await db.execute(stmt)
        default_configs = result.scalars().all()

        # Convert to user integration format
        integrations = []
        for default_config in default_configs:
            config = {
                "user_id": user_id,
                "integration_type": default_config.integration_type,
                "enabled": default_config.enabled,
                "priority": default_config.priority,
                "retry_count": default_config.retry_count,
                "retry_delay_seconds": default_config.retry_delay_seconds,
                "config": default_config.config.copy(),
            }

            # Apply user overrides if provided
            if user_overrides:
                user_override = user_overrides.get(
                    default_config.integration_type.value
                )
                if user_override:
                    # Apply overrides
                    if "enabled" in user_override:
                        config["enabled"] = user_override["enabled"]
                    if "priority" in user_override:
                        config["priority"] = user_override["priority"]
                    if "retry_count" in user_override:
                        config["retry_count"] = user_override["retry_count"]
                    if "retry_delay_seconds" in user_override:
                        config["retry_delay_seconds"] = user_override[
                            "retry_delay_seconds"
                        ]
                    if "config" in user_override:
                        # Merge config dictionaries
                        config["config"].update(user_override["config"])

            # Apply context-specific configuration
            if default_config.integration_type.value == "SLACK":
                # For Slack, include channel information from context or use user ID for DM
                channel_id = None
                if context:
                    channel_id = context.get("slack_channel")
                    logger.info(
                        "Found Slack channel in context",
                        user_id=user_id,
                        channel_id=channel_id,
                        context=context,
                    )

                if not channel_id:
                    # For direct messages, we need to get the DM channel for the user
                    # We'll set the user_id in the config so the Slack handler can create/find the DM channel
                    slack_config = dict(config["config"])  # Create a mutable copy
                    slack_config["slack_user_id"] = user_id
                    config["config"] = slack_config  # Update the config
                    logger.info(
                        "Applied Slack user ID for DM lookup (no channel in context)",
                        user_id=user_id,
                        config=slack_config,
                    )
                else:
                    slack_config = dict(config["config"])  # Create a mutable copy
                    slack_config["channel_id"] = channel_id
                    config["config"] = slack_config  # Update the config
                    logger.info(
                        "Applied Slack channel context",
                        user_id=user_id,
                        channel_id=channel_id,
                        config=slack_config,
                    )

            # Only include enabled integrations
            if config["enabled"]:
                # Create a temporary user config in the database
                from shared_models.models import UserIntegrationConfig

                temp_config = UserIntegrationConfig(
                    user_id=user_id,
                    integration_type=config["integration_type"],
                    enabled=config["enabled"],
                    priority=config["priority"],
                    retry_count=config["retry_count"],
                    retry_delay_seconds=config["retry_delay_seconds"],
                    config=config["config"],
                )
                db.add(temp_config)
                await db.flush()  # Flush to get the ID without committing
                config["id"] = temp_config.id
                integrations.append(config)

        logger.info(
            "Generated user integrations with integration defaults",
            user_id=user_id,
            integrations_count=len(integrations),
            integration_types=[i["integration_type"] for i in integrations],
        )

        return integrations

    def get_default_integrations(self) -> Dict[str, Dict[str, Any]]:
        """Get the current default integration configurations."""
        return self.default_integrations.copy()

    async def get_database_integration_defaults(
        self, db: AsyncSession
    ) -> Dict[str, Dict[str, Any]]:
        """Get integration defaults from the database (health-checked configuration)."""
        from sqlalchemy import select

        stmt = select(IntegrationDefaultConfig)
        result = await db.execute(stmt)
        db_configs = result.scalars().all()

        # Convert database configs to the expected format
        defaults = {}
        for config in db_configs:
            defaults[config.integration_type.value] = {
                "enabled": config.enabled,
                "priority": config.priority,
                "retry_count": config.retry_count,
                "retry_delay_seconds": config.retry_delay_seconds,
                "config": config.config,
            }

        # Ensure all integration types are represented (fill in missing ones with defaults)
        for integration_type in self.default_integrations:
            if integration_type not in defaults:
                defaults[integration_type] = self.default_integrations[
                    integration_type
                ].copy()
                defaults[integration_type][
                    "enabled"
                ] = False  # Disabled if not in database

        return defaults

    def update_default_integration(
        self, integration_type: str, config: Dict[str, Any]
    ) -> None:
        """Update default configuration for an integration type.

        Args:
            integration_type: Integration type to update
            config: New configuration
        """
        if integration_type in self.default_integrations:
            self.default_integrations[integration_type].update(config)
            logger.info(
                "Updated default integration configuration",
                integration_type=integration_type,
                config=config,
            )
        else:
            logger.warning(
                "Unknown integration type for default update",
                integration_type=integration_type,
            )

    def is_integration_enabled_by_default(self, integration_type: str) -> bool:
        """Check if an integration is enabled by default.

        Args:
            integration_type: Integration type to check

        Returns:
            True if enabled by default, False otherwise
        """
        return self.default_integrations.get(integration_type, {}).get("enabled", False)
