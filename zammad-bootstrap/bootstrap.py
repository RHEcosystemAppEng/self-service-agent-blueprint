#!/usr/bin/env python3
"""Zammad bootstrap: creates group, custom user attribute, and all users.

Authenticates with admin basic auth to self-issue a temporary API token,
so this script has no dependency on an externally provisioned token.

Required env vars:
  ZAMMAD_BASE_URL       e.g. http://zammad-nginx:8080
  ZAMMAD_ADMIN_EMAIL    admin user created by autoWizard
  ZAMMAD_ADMIN_PASSWORD matching password
"""

import os
import sys
import time

import requests
from mock_employee_data.data import MOCK_EMPLOYEE_DATA

BASE_URL = os.environ["ZAMMAD_BASE_URL"].rstrip("/")
API_URL = f"{BASE_URL}/api/v1"
ADMIN_EMAIL = os.environ["ZAMMAD_ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ZAMMAD_ADMIN_PASSWORD"]
AUTOWIZARD_TOKEN = os.environ["ZAMMAD_AUTOWIZARD_TOKEN"]

MANAGER1_EMAIL = "manager1@example.com"
MANAGER2_EMAIL = "manager2@example.com"
DEFAULT_PASSWORD = "ChangeMe123!"

SESSION = requests.Session()
SESSION.headers.update({"Content-Type": "application/json"})


# ---------------------------------------------------------------------------
# Startup: wait for Zammad, then self-issue an API token
# ---------------------------------------------------------------------------


def wait_for_zammad(timeout=600, interval=10):
    print("Waiting for Zammad to be healthy...")
    health_url = f"{API_URL}/getting_started"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(health_url, timeout=5).ok:
                print("Zammad is healthy.")
                return
        except requests.exceptions.RequestException:
            pass
        print(f"  Not ready yet, retrying in {interval}s...")
        time.sleep(interval)
    print("ERROR: Zammad did not become healthy in time.", file=sys.stderr)
    sys.exit(1)


def trigger_autowizard(timeout=120, interval=10):
    """Trigger the autoWizard via HTTP to seed the initial admin user."""
    print("Triggering autoWizard...")
    url = f"{API_URL}/getting_started/auto_wizard/{AUTOWIZARD_TOKEN}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=10)
            if r.ok:
                print("  autoWizard triggered successfully.")
                return
            print(f"  autoWizard returned {r.status_code}, retrying in {interval}s...")
        except requests.exceptions.RequestException as e:
            print(f"  Request error: {e}, retrying in {interval}s...")
        time.sleep(interval)
    print("ERROR: Could not trigger autoWizard.", file=sys.stderr)
    sys.exit(1)


def acquire_token(timeout=120, interval=10):
    """Create a short-lived API token using admin basic auth."""
    print("Acquiring API token via admin credentials...")
    url = f"{API_URL}/user_access_token"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.post(
                url,
                auth=(ADMIN_EMAIL, ADMIN_PASSWORD),
                json={"name": "zammad-bootstrap", "permission": ["admin"]},
                timeout=10,
            )
            if r.ok:
                token = r.json().get("token")
                if token:
                    SESSION.headers["Authorization"] = f"Token token={token}"
                    print("  API token acquired.")
                    return
            print(
                f"  Token creation returned {r.status_code}: {r.text[:200]}, retrying in {interval}s..."
            )
        except requests.exceptions.RequestException as e:
            print(f"  Request error: {e}, retrying in {interval}s...")
        time.sleep(interval)
    print("ERROR: Could not acquire API token.", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def api(method, path, **kwargs):
    url = f"{API_URL}/{path.lstrip('/')}"
    resp = SESSION.request(method, url, **kwargs)
    if not resp.ok:
        print(
            f"  ERROR {method} {path}: {resp.status_code} {resp.text[:300]}",
            file=sys.stderr,
        )
        resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------


def get_or_create_group(name):
    for g in api("GET", "groups"):
        if g["name"] == name:
            print(f"  Group '{name}' already exists (id={g['id']})")
            return g["id"]
    g = api("POST", "groups", json={"name": name, "active": True})
    print(f"  Created group '{name}' (id={g['id']})")
    return g["id"]


# ---------------------------------------------------------------------------
# Custom attribute
# ---------------------------------------------------------------------------


def ensure_manager_email_attribute():
    for a in api("GET", "object_manager_attributes"):
        if a.get("object") == "User" and a.get("name") == "manager_email":
            print("  Custom attribute 'manager_email' already exists.")
            return

    print("  Creating custom attribute 'manager_email' on User...")
    api(
        "POST",
        "object_manager_attributes",
        json={
            "object": "User",
            "name": "manager_email",
            "display": "Manager Email",
            "data_type": "input",
            "data_option": {
                "type": "email",
                "maxlength": 255,
                "null": True,
                "note": "",
            },
            "active": True,
            "screens": {
                "edit": {
                    "Admin": {"shown": True, "required": False},
                    "Agent": {"shown": True, "required": False},
                },
                "view": {
                    "Admin": {"shown": True, "required": False},
                    "Agent": {"shown": True, "required": False},
                },
            },
        },
    )
    print("  Executing attribute migrations...")
    api("POST", "object_manager_attributes_execute_migrations")
    print("  Attribute migration complete.")


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


def get_role_ids():
    roles = api("GET", "roles")
    return {r["name"]: r["id"] for r in roles}


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def find_user_by_email(email):
    """Look up a user by email using paginated listing (avoids Elasticsearch lag on fresh deploys)."""
    page = 1
    while True:
        users = api("GET", f"users?page={page}&per_page=100")
        if not users:
            return None
        for u in users:
            if u.get("email", "").lower() == email.lower():
                return u
        if len(users) < 100:
            return None
        page += 1


def get_or_create_user(
    login, firstname, lastname, email, role_ids, group_ids=None, manager_email=None
):
    existing = find_user_by_email(email)
    payload = {
        "login": login,
        "firstname": firstname,
        "lastname": lastname,
        "email": email,
        "role_ids": role_ids,
        "password": DEFAULT_PASSWORD,
        "active": True,
    }
    if group_ids:
        payload["group_ids"] = group_ids
    if manager_email:
        payload["manager_email"] = manager_email

    if existing:
        print(f"  User '{email}' already exists (id={existing['id']}), updating...")
        api("PUT", f"users/{existing['id']}", json=payload)
    else:
        user = api("POST", "users", json=payload)
        print(f"  Created user '{email}' (id={user['id']})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    wait_for_zammad()
    trigger_autowizard()
    acquire_token()

    print("\n[1/5] Ensuring custom attribute 'manager_email' exists...")
    ensure_manager_email_attribute()

    print("\n[2/5] Creating groups...")
    group_id = get_or_create_group("human_managed_tickets")
    escalated_group_id = get_or_create_group("escalated_laptop_refresh_tickets")

    print("\n[3/5] Looking up role IDs...")
    role_map = get_role_ids()
    agent_role_ids = [role_map["Agent"]]
    customer_role_ids = [role_map["Customer"]]
    print(f"  Agent role id={agent_role_ids}, Customer role id={customer_role_ids}")

    print("\n[4/5] Creating ticket handlers, managers and specialists...")
    get_or_create_user(
        "agent.laptop-specialist",
        "Laptop",
        "Specialist",
        "agent.laptop-specialist@example.com",
        role_ids=agent_role_ids,
        group_ids={str(group_id): ["full"]},
    )
    get_or_create_user(
        "ticket_handler1",
        "Ticket",
        "Handler1",
        "ticket_handler1@example.com",
        role_ids=agent_role_ids,
        group_ids={str(group_id): ["full"]},
    )
    get_or_create_user(
        "ticket_handler2",
        "Ticket",
        "Handler2",
        "ticket_handler2@example.com",
        role_ids=agent_role_ids,
        group_ids={str(group_id): ["full"]},
    )
    get_or_create_user(
        "escalated_laptop_refresh_handler1",
        "Escalated Laptop Refresh",
        "Handler1",
        "escalated_laptop_refresh_handler1@example.com",
        role_ids=agent_role_ids,
        group_ids={str(escalated_group_id): ["full"]},
    )
    get_or_create_user(
        "escalated_laptop_refresh_handler2",
        "Escalated Laptop Refresh",
        "Handler2",
        "escalated_laptop_refresh_handler2@example.com",
        role_ids=agent_role_ids,
        group_ids={str(escalated_group_id): ["full"]},
    )
    get_or_create_user(
        "manager1",
        "Manager",
        "One",
        MANAGER1_EMAIL,
        role_ids=agent_role_ids,
    )
    get_or_create_user(
        "manager2",
        "Manager",
        "Two",
        MANAGER2_EMAIL,
        role_ids=agent_role_ids,
    )

    print("\n[5/5] Creating employees from mock-employee-data...")
    employees = list(MOCK_EMPLOYEE_DATA.values())
    for i, emp in enumerate(employees):
        manager_email = MANAGER1_EMAIL if i < 5 else MANAGER2_EMAIL
        name_parts = emp["name"].split(maxsplit=1)
        get_or_create_user(
            emp["user_name"],
            name_parts[0],
            name_parts[1] if len(name_parts) > 1 else "",
            emp["email"],
            role_ids=customer_role_ids,
            manager_email=manager_email,
        )

    print("\nZammad bootstrap complete.")


if __name__ == "__main__":
    main()
