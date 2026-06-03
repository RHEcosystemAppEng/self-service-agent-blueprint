"""IntegrationDispatcher.handlers must match channel_registry wiring."""

from integration_dispatcher.main import IntegrationDispatcher
from shared_models.channel_registry import (
    WIRED_DISPATCHER_HANDLER_TYPES,
    WIRED_DISPATCHER_ONLY,
    WIRED_RM_AND_DISPATCHER,
)


def test_dispatcher_handlers_match_wired_registry() -> None:
    dispatcher = IntegrationDispatcher()
    assert frozenset(dispatcher.handlers.keys()) == WIRED_DISPATCHER_HANDLER_TYPES


def test_dispatcher_handlers_match_wiring_buckets() -> None:
    dispatcher = IntegrationDispatcher()
    handler_types = frozenset(dispatcher.handlers.keys())
    assert handler_types == WIRED_RM_AND_DISPATCHER | WIRED_DISPATCHER_ONLY
