"""Shared logging configuration for all services."""

import logging
import os
import sys
from typing import Any, MutableMapping, Optional, Protocol

import structlog


class StructuredLogger(Protocol):
    """Protocol for structured logging with arbitrary keyword arguments.

    This protocol allows mypy to understand that our loggers accept
    arbitrary keyword arguments for structured logging, avoiding the need
    for type: ignore comments at every logging call site.
    """

    def debug(self, event: str, **kwargs: Any) -> None:
        """Log a debug message with structured context."""
        ...

    def info(self, event: str, **kwargs: Any) -> None:
        """Log an info message with structured context."""
        ...

    def warning(self, event: str, **kwargs: Any) -> None:
        """Log a warning message with structured context."""
        ...

    def error(self, event: str, **kwargs: Any) -> None:
        """Log an error message with structured context."""
        ...

    def critical(self, event: str, **kwargs: Any) -> None:
        """Log a critical message with structured context."""
        ...

    def exception(self, event: str, **kwargs: Any) -> None:
        """Log an exception with structured context."""
        ...

    def bind(self, **kwargs: Any) -> "StructuredLogger":
        """Bind context to logger."""
        ...


class LoggingConfig:
    """Centralized logging configuration for all services."""

    def __init__(self, service_name: str = "unknown"):
        self.service_name = service_name
        self.log_level = self._get_log_level()
        self.enable_debug = os.getenv("LOG_LEVEL", "INFO").upper() == "DEBUG"
        self.enable_json = os.getenv("LOG_FORMAT", "json").lower() == "json"

    def _get_log_level(self) -> int:
        """Get the appropriate log level from environment."""
        level = os.getenv("LOG_LEVEL", "INFO").upper()
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        return level_map.get(level, logging.INFO)

    def configure_basic_logging(self) -> None:
        """Configure basic Python logging."""
        # Explicitly set root logger level to ensure it takes effect
        logging.getLogger().setLevel(self.log_level)

        logging.basicConfig(
            level=self.log_level,
            format="%(message)s",
            stream=sys.stdout,
        )

    def configure_structlog(self) -> None:
        """Configure structured logging."""
        processors: list[Any] = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
        ]

        # Add service name to context
        processors.insert(0, self._add_service_context)

        # Choose output format
        if self.enable_json:
            processors.append(structlog.processors.JSONRenderer())
        else:
            processors.append(structlog.dev.ConsoleRenderer())

        structlog.configure(
            processors=processors,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

    def _add_service_context(
        self, logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        """Add service name to log context."""
        event_dict["service"] = self.service_name
        return event_dict

    def configure_all(self) -> None:
        """Configure both basic and structured logging."""
        self.configure_basic_logging()
        self.configure_structlog()

    def get_logger(self, name: Optional[str] = None) -> StructuredLogger:
        """Get a configured logger."""
        logger = structlog.get_logger(name)
        return logger  # type: ignore[no-any-return]


def configure_logging(service_name: str = "unknown") -> StructuredLogger:
    """Configure logging for a service and return a logger.

    Args:
        service_name: Name of the service for logging context

    Returns:
        Configured logger instance
    """
    config = LoggingConfig(service_name)
    config.configure_all()
    return config.get_logger()


def get_service_logger(service_name: str) -> StructuredLogger:
    """Get a logger for a specific service.

    Args:
        service_name: Name of the service

    Returns:
        Configured logger for the service
    """
    logger = structlog.get_logger().bind(service=service_name)
    return logger  # type: ignore[no-any-return]


class ServiceLogger:
    """Context manager for service-specific logging."""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.logger: Optional[StructuredLogger] = None

    def __enter__(self) -> StructuredLogger:
        self.logger = get_service_logger(self.service_name)
        return self.logger

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


# Convenience functions for common logging patterns
def log_request(logger: StructuredLogger, request_id: str, **context: Any) -> None:
    """Log a request with standard context."""
    logger.debug("Request received", request_id=request_id, **context)


def log_response(
    logger: StructuredLogger, request_id: str, status: str, **context: Any
) -> None:
    """Log a response with standard context."""
    logger.debug("Response sent", request_id=request_id, status=status, **context)


def log_error(logger: StructuredLogger, error: Exception, **context: Any) -> None:
    """Log an error with standard context."""
    logger.error(
        "Error occurred", error=str(error), error_type=type(error).__name__, **context
    )


def log_health_check(
    logger: StructuredLogger, service: str, status: str, **context: Any
) -> None:
    """Log a health check with standard context."""
    logger.info("Health check", service=service, status=status, **context)


def log_database_operation(
    logger: StructuredLogger, operation: str, **context: Any
) -> None:
    """Log a database operation with standard context."""
    logger.debug("Database operation", operation=operation, **context)


def log_integration_event(
    logger: StructuredLogger, integration: str, event_type: str, **context: Any
) -> None:
    """Log an integration event with standard context."""
    logger.info(
        "Integration event", integration=integration, event_type=event_type, **context
    )
