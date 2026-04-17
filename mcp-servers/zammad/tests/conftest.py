"""Ensure Zammad MCP settings can import under pytest (required env for ``load_zammad_mcp_settings``)."""

import os

# Applied when this conftest is loaded, before test modules import ``zammad_mcp.*``.
os.environ.setdefault("ZAMMAD_URL", "https://zammad.test.invalid")
os.environ.setdefault("ZAMMAD_HTTP_TOKEN", "pytest-placeholder-token")
