"""Test defaults: ServiceNowClient reads SERVICENOW_INSTANCE_URL at import/init time."""

import os

import pytest


@pytest.fixture(autouse=True)
def _servicenow_instance_url() -> None:
    os.environ.setdefault(
        "SERVICENOW_INSTANCE_URL", "http://self-service-agent-mock-servicenow:8080"
    )
