#!/usr/bin/env python3
"""Zammad bootstrap: creates group, custom user attribute, and all users.

Authenticates with admin basic auth to self-issue a temporary API token,
so this script has no dependency on an externally provisioned token.

Required env vars:
  ZAMMAD_BASE_URL       e.g. http://zammad-nginx:8080
  ZAMMAD_ADMIN_EMAIL    admin user created by autoWizard
  ZAMMAD_ADMIN_PASSWORD matching password

Optional (integration webhook — same secret as integration-dispatcher ZAMMAD_WEBHOOK_SECRET):
  ZAMMAD_INTEGRATION_WEBHOOK_URL   Full URL e.g. http://RELEASE-integration-dispatcher.NS.svc.cluster.local/zammad/webhook
  ZAMMAD_WEBHOOK_SECRET            HMAC token stored on Zammad Webhook + verified by dispatcher (must match integration-dispatcher; omit → dispatcher returns 401 on webhook POST)
  ZAMMAD_CUSTOMER_SENDER_ID       Optional override (digits only). Default trigger article.sender_id is 2 (Customer per Zammad db/seeds/ticket_article_senders.rb).

Optional trigger narrowing (Zammad trigger conditions — preferred over dispatcher env allowlists):
  ZAMMAD_TRIGGER_GROUP_IDS   Comma-separated internal group IDs (e.g. "3" or "3,5"). Adds ticket.group_id (is / is any of). Overrides GROUP_NAMES if both set.
  ZAMMAD_TRIGGER_GROUP_NAMES  Comma-separated Zammad group names (e.g. "Users" or "Users,human_managed_tickets"). Resolved to ids via GET /api/v1/groups at trigger update time. Helm: bootstrap.integrationWebhook.triggerGroupNames.
  ZAMMAD_TRIGGER_SKIP_GROUP_FILTER  If true/1/yes: do not add ticket.group_id (fire for customer articles in any group).
  ZAMMAD_TRIGGER_TAGS_ANY    Comma-separated tag names; ticket must contain at least one ("contains one"). Mutually exclusive with TAGS_ALL and TAGS_EXCLUDE.
  ZAMMAD_TRIGGER_TAGS_ALL    Comma-separated tag names; ticket must contain all ("contains all"). Mutually exclusive with TAGS_ANY and TAGS_EXCLUDE.
  ZAMMAD_TRIGGER_TAGS_EXCLUDE  Comma-separated tag names; ticket must contain none of them. Uses "contains all not". Values are sent as one comma-separated string (Zammad Selector splits strings; JSON arrays make validation fail with 422). Do not use commas inside a tag name. Mutually exclusive with TAGS_ANY / TAGS_ALL.

  Integration trigger always adds ticket.state_id "is any of" the **new** and **open** states (ids resolved from GET /api/v1/ticket_states at bootstrap time).

Optional customer web UI (Zammad setting customer_ticket_create_group_ids — Admin describes "no selection means all groups"):
  ZAMMAD_SKIP_CUSTOMER_CREATE_GROUP_LIMIT  If true/1/yes: do not set this setting (customers may choose any group for new tickets — avoid with internal queues).
  ZAMMAD_CUSTOMER_TICKET_CREATE_GROUP_NAMES  Comma-separated group names allowed in the customer "new ticket" group picker. Default when unset: only the **Users** group (resolved via id from bootstrap).

Optional employee seeding (same semantics as mock ServiceNow / mock-employee-data ``get_employee_data()``):
  TEST_USERS   Comma-separated emails to provision as Customer-role Zammad users with generated laptop rows. Helm (ticketing): ``ticketingZammad.bootstrap.testUsers``; Makefile: ``TEST_USERS`` passed to ``helm-install-ticketing``.

API resilience (nginx/Rails restarts, cold workers — avoids bootstrap failing on a single 502):
  ZAMMAD_API_RETRY_ATTEMPTS     Max attempts per request (default 10).
  ZAMMAD_API_RETRY_INTERVAL_SEC Base delay before retry; scales linearly with attempt (default 2).

Helm zammad-init Job (DB migrations / seeds — always awaited before HTTP bootstrap when in-cluster):
  ZAMMAD_HELM_INSTANCE_NAME        Helm release/instance label on the zammad-init Job (app.kubernetes.io/instance).
  ZAMMAD_INIT_JOB_WAIT_TIMEOUT_SEC Overall timeout in seconds (default 3600).
  Without in-cluster Kubernetes or this name, the wait is skipped with a warning (local runs).

Object manager migrations (POST …/object_manager_attributes_execute_migrations can run long; nginx may 502 if upstream is slow):
  ZAMMAD_OM_POST_COOLDOWN_SEC             Seconds to wait after creating custom field(s) before execute_migrations (default 20; set 0 to skip).
  ZAMMAD_OM_MIGRATION_TIMEOUT_SEC        HTTP read timeout for execute_migrations only (default 300). Raise if nginx proxy_read_timeout allows it.
  ZAMMAD_OM_POST_MIGRATION_SETTLE_SEC    Seconds to wait after execute_migrations succeeds (default 8; nginx/Rails may briefly 502 — gives upstream time before next API call).
  ZAMMAD_POST_USER_CREATE_SETTLE_SEC     Seconds to sleep after each POST /users create (default 3; reduces 502 on the next GET /users used for idempotent lookups).

Bootstrap does not restart zammad-railsserver (only MCP + integration-dispatcher + optional request-manager when ZAMMAD_CREATE_TOKEN runs).
"""

import base64
import datetime
import json
import os
import sys
import time

import requests
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from mock_employee_data.data import get_employee_data

BASE_URL = os.environ["ZAMMAD_BASE_URL"].rstrip("/")
API_URL = f"{BASE_URL}/api/v1"
ADMIN_EMAIL = os.environ["ZAMMAD_ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ZAMMAD_ADMIN_PASSWORD"]
AUTOWIZARD_TOKEN = os.environ["ZAMMAD_AUTOWIZARD_TOKEN"]

# Webhook + trigger (Manage → Webhooks + Triggers); see README.md § Integration with Zammad ticketing
WEBHOOK_RECORD_NAME = "Self-Service Agent — Integration Webhook"
TRIGGER_RECORD_NAME = "Self-Service Agent — Customer article → blueprint"

MANAGER1_EMAIL = "manager1@example.com"
MANAGER2_EMAIL = "manager2@example.com"
DEFAULT_PASSWORD = "ChangeMe123!"

# Stock Zammad db/seeds — fixed ids (create_if_not_exists):
# roles.rb: Admin=1, Agent=2, Customer=3
DEFAULT_AGENT_ROLE_ID = 2
DEFAULT_CUSTOMER_ROLE_ID = 3
# ticket_article_senders.rb (Ticket::Article::Sender): Agent=1, Customer=2, System=3
DEFAULT_CUSTOMER_ARTICLE_SENDER_ID = 2

SESSION = requests.Session()
SESSION.headers.update({"Content-Type": "application/json"})


# ---------------------------------------------------------------------------
# Startup: wait for Zammad, then self-issue an API token
# ---------------------------------------------------------------------------


def wait_for_zammad_init_job(timeout_sec=None, interval=5):
    """Wait for the chart-owned ``zammad-init`` Job to complete (same labels as zammad-helm)."""
    instance = os.environ.get("ZAMMAD_HELM_INSTANCE_NAME", "").strip()
    if not instance:
        print(
            "WARNING: ZAMMAD_HELM_INSTANCE_NAME unset; skip zammad-init Job wait.",
            file=sys.stderr,
        )
        return
    if timeout_sec is None:
        raw_to = os.environ.get("ZAMMAD_INIT_JOB_WAIT_TIMEOUT_SEC", "").strip()
        try:
            timeout_sec = int(raw_to) if raw_to else 3600
        except ValueError:
            timeout_sec = 3600
    try:
        from kubernetes import client  # type: ignore[import-untyped]
        from kubernetes import config as k8s_config  # type: ignore[import-untyped]

        k8s_config.load_incluster_config()
    except Exception as e:
        print(
            f"WARNING: cannot load Kubernetes in-cluster config ({e}); "
            "skip zammad-init Job wait.",
            file=sys.stderr,
        )
        return

    ns_path = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
    try:
        with open(ns_path) as f:
            namespace = f.read().strip()
    except OSError:
        print(
            "WARNING: namespace secret not found; skip zammad-init Job wait.",
            file=sys.stderr,
        )
        return

    batch = client.BatchV1Api()
    sel = (
        "app.kubernetes.io/component=zammad-init,"
        f"app.kubernetes.io/instance={instance}"
    )
    deadline = time.time() + timeout_sec
    print(f"Waiting for zammad-init Job to finish (label selector {sel!r})...")
    while time.time() < deadline:
        try:
            resp = batch.list_namespaced_job(namespace=namespace, label_selector=sel)
            items = resp.items or []
            if not items:
                print("  No zammad-init Job found yet; retrying...")
                time.sleep(interval)
                continue
            j = items[0]
            name = j.metadata.name
            st = j.status
            if st.succeeded:
                print(f"  zammad-init Job {name!r} completed successfully.")
                return
            for cond in st.conditions or []:
                if cond.type == "Failed" and cond.status == "True":
                    print(
                        f"ERROR: zammad-init Job {name!r} failed: {cond.message or cond.reason}. "
                        "Check logs: kubectl logs -n <ns> -l app.kubernetes.io/component=zammad-init --all-containers",
                        file=sys.stderr,
                    )
                    sys.exit(1)
            active = getattr(st, "active", None) or 0
            print(
                f"  zammad-init Job {name!r} still running (active={active}); "
                f"retrying in {interval}s..."
            )
        except Exception as e:
            err = str(e)
            if "403" in err or "Forbidden" in err:
                print(
                    "WARNING: RBAC denied listing Jobs; grant batch/jobs get,list,watch to the "
                    "bootstrap ServiceAccount.",
                    file=sys.stderr,
                )
                return
            print(
                f"  Error listing Jobs ({e}); retrying in {interval}s...",
                file=sys.stderr,
            )
        time.sleep(interval)
    print(
        "ERROR: Timeout waiting for zammad-init Job to complete.",
        file=sys.stderr,
    )
    sys.exit(1)


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
                json={
                    "name": "zammad-bootstrap",
                    # customer_ticket_create_group_ids requires admin.channel_web for PUT (SettingPolicy).
                    "permission": ["admin", "admin.channel_web"],
                },
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

# Gateway overload / upstream not ready — safe to retry (GET or POST may still need idempotency elsewhere).
_TRANSIENT_HTTP = frozenset({502, 503, 504, 429})


def _float_env(key: str, default: float) -> float:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def execute_object_manager_migrations(*, after_create: bool = False) -> None:
    """Run ObjectManager migrations (single POST). Long timeout; optional cooldown after attribute create."""
    if after_create:
        cooldown = _float_env("ZAMMAD_OM_POST_COOLDOWN_SEC", 20.0)
        if cooldown > 0:
            print(
                f"  Waiting {cooldown:.0f}s before execute_migrations "
                "(Zammad/Rails often reloads after creating field(s))..."
            )
            time.sleep(cooldown)
    mig_timeout = _float_env("ZAMMAD_OM_MIGRATION_TIMEOUT_SEC", 300.0)
    api(
        "POST",
        "object_manager_attributes_execute_migrations",
        timeout=max(30.0, mig_timeout),
    )
    settle = _float_env("ZAMMAD_OM_POST_MIGRATION_SETTLE_SEC", 8.0)
    if settle > 0:
        print(
            f"  Waiting {settle:.0f}s after migrations for Rails/nginx to stabilize "
            "(avoids follow-up HTTP 502 from upstream reload)..."
        )
        time.sleep(settle)


def api(method, path, **kwargs):
    """HTTP JSON helper with retries on transient errors (502/503/504/429) and connection failures."""
    url = f"{API_URL}/{path.lstrip('/')}"
    req = dict(kwargs)
    if "timeout" not in req:
        req["timeout"] = 60

    raw_attempts = os.environ.get("ZAMMAD_API_RETRY_ATTEMPTS", "10").strip()
    try:
        max_attempts = max(1, int(raw_attempts))
    except ValueError:
        max_attempts = 10

    raw_interval = os.environ.get("ZAMMAD_API_RETRY_INTERVAL_SEC", "2").strip()
    try:
        base_interval = float(raw_interval)
    except ValueError:
        base_interval = 2.0

    last_resp = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = SESSION.request(method, url, **req)
        except requests.exceptions.RequestException as e:
            if attempt >= max_attempts:
                print(
                    f"  ERROR {method} {path}: request failed after {max_attempts} attempts: {e}",
                    file=sys.stderr,
                )
                raise
            wait = min(90.0, base_interval * attempt)
            print(
                f"  WARNING {method} {path}: connection error ({e!s}); "
                f"retry {attempt}/{max_attempts} in {wait:.0f}s...",
                file=sys.stderr,
            )
            time.sleep(wait)
            continue

        last_resp = resp
        if resp.ok:
            if resp.status_code == 204 or not (resp.content or b"").strip():
                return {}
            try:
                return resp.json()
            except ValueError as e:
                if attempt >= max_attempts:
                    print(
                        f"  ERROR {method} {path}: invalid JSON in response: {e}",
                        file=sys.stderr,
                    )
                    raise
                wait = min(90.0, base_interval * attempt)
                print(
                    f"  WARNING {method} {path}: JSON decode error; "
                    f"retry {attempt}/{max_attempts} in {wait:.0f}s...",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue

        if resp.status_code in _TRANSIENT_HTTP and attempt < max_attempts:
            wait = min(90.0, base_interval * attempt)
            ra = resp.headers.get("Retry-After")
            if ra:
                try:
                    wait = min(90.0, float(ra))
                except ValueError:
                    pass
            snippet = (resp.text or "")[:200].replace("\n", " ")
            print(
                f"  WARNING {method} {path}: HTTP {resp.status_code} {snippet!s}… "
                f"retry {attempt}/{max_attempts} in {wait:.0f}s...",
                file=sys.stderr,
            )
            time.sleep(wait)
            continue

        print(
            f"  ERROR {method} {path}: {resp.status_code} {resp.text[:300]}",
            file=sys.stderr,
        )
        resp.raise_for_status()

    # loop exits only if all attempts exhausted on transient path without raise — defensive
    if last_resp is not None:
        print(
            f"  ERROR {method} {path}: {last_resp.status_code} {last_resp.text[:300]}",
            file=sys.stderr,
        )
        last_resp.raise_for_status()
    raise RuntimeError(f"{method} {path}: exhausted retries without response")


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


def lookup_group_id_by_name(name: str) -> int | None:
    """Return Zammad internal group id for an exact group name, or None."""
    for g in api("GET", "groups"):
        if g.get("name") == name:
            return int(g["id"])
    return None


def lookup_ticket_state_id_by_name(name: str) -> int | None:
    """Return Zammad ticket_states.id for an exact state name, or None."""
    for s in api("GET", "ticket_states"):
        if s.get("name") == name:
            return int(s["id"])
    return None


def ensure_customer_ticket_create_group_ids(users_group_id: int) -> None:
    """Set Zammad ``customer_ticket_create_group_ids`` so the customer web UI does not offer internal queues.

    When this setting is empty, Zammad allows customers to create tickets in **all** groups
    (see ``Group.customer_create_groups_with_parent_ids``). After bootstrap adds
    ``human_managed_tickets`` / ``escalated_laptop_refresh_tickets``, restrict the picker
    unless skipped via env.
    """
    if _env_truthy("ZAMMAD_SKIP_CUSTOMER_CREATE_GROUP_LIMIT"):
        print(
            "  Skipping customer_ticket_create_group_ids "
            "(ZAMMAD_SKIP_CUSTOMER_CREATE_GROUP_LIMIT — all groups may appear for customer new ticket)."
        )
        return

    raw_names = os.environ.get("ZAMMAD_CUSTOMER_TICKET_CREATE_GROUP_NAMES", "").strip()
    if raw_names:
        target_ids: list[int] = []
        for part in raw_names.split(","):
            n = part.strip()
            if not n:
                continue
            gid = lookup_group_id_by_name(n)
            if gid is None:
                print(
                    f"ERROR: ZAMMAD_CUSTOMER_TICKET_CREATE_GROUP_NAMES: unknown group {n!r}.",
                    file=sys.stderr,
                )
                sys.exit(1)
            target_ids.append(gid)
    else:
        target_ids = [users_group_id]

    settings_list = api("GET", "settings")
    sid = None
    for s in settings_list:
        if s.get("name") == "customer_ticket_create_group_ids":
            sid = s["id"]
            break
    if sid is None:
        print(
            "  WARNING: Setting customer_ticket_create_group_ids not found; skip.",
            file=sys.stderr,
        )
        return

    # Zammad persists settings in state_current.value (see Setting#state_check). Some API paths
    # ignore bare `state` on PUT; send state_current explicitly.
    body = {"state_current": {"value": target_ids}}
    try:
        api("PUT", f"settings/{sid}", json=body)
    except requests.HTTPError:
        try:
            api("PUT", f"settings/{sid}", json={"state": target_ids})
        except requests.HTTPError:
            print(
                "  WARNING: PUT settings/customer_ticket_create_group_ids failed "
                "(permissions or payload). Customers may still see all groups.",
                file=sys.stderr,
            )
            return

    # Confirm persistence (helps debug UI still listing every group).
    full = api("GET", f"settings/{sid}")
    got = None
    sc = full.get("state_current")
    if isinstance(sc, dict):
        got = sc.get("value")

    def _norm_ids(v: object) -> set[str]:
        if v is None:
            return set()
        if isinstance(v, (list, tuple)):
            return {str(x) for x in v}
        return {str(v)}

    if _norm_ids(got) != _norm_ids(target_ids):
        print(
            f"  WARNING: customer_ticket_create_group_ids after PUT is {got!r}, "
            f"expected {target_ids!r} — check Zammad version / API.",
            file=sys.stderr,
        )

    print(
        f"  Customer web: new-ticket group picker limited to id(s) {target_ids} "
        "(customer_ticket_create_group_ids)."
    )


# ---------------------------------------------------------------------------
# Custom attribute
# ---------------------------------------------------------------------------


def build_current_laptop_json(emp: dict) -> str:
    """Build the JSON string to store in the current_laptop Zammad field."""
    purchase_date = emp.get("purchase_date", "N/A")
    warranty_expiry = emp.get("warranty_expiry", "N/A")
    location = (emp.get("location") or "N/A").upper()

    return json.dumps(
        {
            "name": emp.get("name", "N/A"),
            "location": location,
            "laptop_model": emp.get("laptop_model", "N/A"),
            "serial_number": emp.get("laptop_serial_number", "N/A"),
            "purchase_date": purchase_date,
            "warranty_expiry": warranty_expiry,
        }
    )


def ensure_custom_user_attributes():
    """Create ``manager_email`` / ``current_laptop`` User fields if missing; run migrations **once** (fewer Rails reloads than two separate cycles)."""
    attrs = api("GET", "object_manager_attributes")
    by_name = {a.get("name"): a for a in attrs if a.get("object") == "User"}

    created_any = False
    pending_existing = False

    me = by_name.get("manager_email")
    if me:
        print("  Custom attribute 'manager_email' already exists.")
        if me.get("to_migrate") or me.get("to_create"):
            pending_existing = True
    else:
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
        created_any = True

    cl = by_name.get("current_laptop")
    if cl:
        print("  Custom attribute 'current_laptop' already exists.")
        if cl.get("to_migrate") or cl.get("to_create"):
            pending_existing = True
    else:
        print("  Creating custom attribute 'current_laptop' on User...")
        api(
            "POST",
            "object_manager_attributes",
            json={
                "object": "User",
                "name": "current_laptop",
                "display": "Current Laptop",
                "data_type": "textarea",
                "data_option": {
                    "maxlength": 5000,
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
        created_any = True

    if created_any:
        print("  Executing attribute migrations...")
        execute_object_manager_migrations(after_create=True)
        print("  Attribute migration complete.")
    elif pending_existing:
        print("  Object manager migration still pending; executing...")
        execute_object_manager_migrations()
        print("  Attribute migration complete.")


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
    login,
    firstname,
    lastname,
    email,
    role_ids,
    group_ids=None,
    manager_email=None,
    current_laptop=None,
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
    if current_laptop:
        payload["current_laptop"] = current_laptop

    if existing:
        print(f"  User '{email}' already exists (id={existing['id']}), updating...")
        api("PUT", f"users/{existing['id']}", json=payload)
    else:
        user = api("POST", "users", json=payload)
        print(f"  Created user '{email}' (id={user['id']})")
        settle = _float_env("ZAMMAD_POST_USER_CREATE_SETTLE_SEC", 3.0)
        if settle > 0:
            time.sleep(settle)


# ---------------------------------------------------------------------------
# Token creation + Kubernetes secret/deployment update
# ---------------------------------------------------------------------------

_KUBE_NS = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"


def create_mcp_token_and_update_k8s():
    """Create Zammad MCP agent API token, update k8s secret (read+replace), restart MCP + dispatcher (+ RM if set) — never zammad-railsserver."""
    credentials_secret = os.environ["ZAMMAD_CREDENTIALS_SECRET"]
    mcp_deployment = os.environ.get("ZAMMAD_MCP_DEPLOYMENT", "")
    integration_dispatcher_deployment = os.environ.get(
        "ZAMMAD_INTEGRATION_DISPATCHER_DEPLOYMENT", ""
    )
    request_manager_deployment = os.environ.get("ZAMMAD_REQUEST_MANAGER_DEPLOYMENT", "")
    zammad_url = os.environ["ZAMMAD_BASE_URL"]

    with open(_KUBE_NS) as f:
        namespace = f.read().strip()

    print("\n[Token] Creating MCP agent API token...")
    r = requests.post(
        f"{API_URL}/user_access_token",
        auth=(ADMIN_EMAIL, ADMIN_PASSWORD),
        json={"name": "mcp-agent", "permission": ["admin", "ticket.agent"]},
        timeout=10,
    )
    if not r.ok:
        print(f"  ERROR: {r.status_code} {r.text[:200]}", file=sys.stderr)
        sys.exit(1)
    token = r.json().get("token")
    if not token:
        print("  ERROR: no token in response", file=sys.stderr)
        sys.exit(1)
    print("  MCP token created.")

    k8s_config.load_incluster_config()
    core_v1 = k8s_client.CoreV1Api()
    apps_v1 = k8s_client.AppsV1Api()

    def _b64(s):
        return base64.b64encode(s.encode()).decode()

    print(f"  Updating secret {credentials_secret} in namespace {namespace}...")
    try:
        # Use read + replace instead of PATCH: some clusters (notably OpenShift) return 401 or other
        # failures on strategic-merge PATCH for Secrets even when RBAC allows patch/update.
        existing = core_v1.read_namespaced_secret(
            name=credentials_secret, namespace=namespace
        )
        data = dict(existing.data or {})
        data["zammad-url"] = _b64(zammad_url)
        data["zammad-api-url"] = _b64(f"{zammad_url}/api/v1")
        data["zammad-http-token"] = _b64(token)
        existing.data = data
        core_v1.replace_namespaced_secret(
            name=credentials_secret,
            namespace=namespace,
            body=existing,
        )
    except k8s_client.ApiException as e:
        detail = (e.body or "").strip()[:500]
        extra = f" — {detail}" if detail else ""
        print(
            f"  ERROR updating secret: {e.status} {e.reason}{extra}",
            file=sys.stderr,
        )
        sys.exit(1)
    print("  Secret updated.")

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    restart_patch = {
        "spec": {
            "template": {
                "metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": now}}
            }
        }
    }
    for dep in filter(
        None,
        [mcp_deployment, integration_dispatcher_deployment, request_manager_deployment],
    ):
        print(f"  Restarting deployment {dep}...")
        try:
            apps_v1.patch_namespaced_deployment(
                name=dep,
                namespace=namespace,
                body=restart_patch,
            )
            print(f"  Deployment {dep} restart triggered.")
        except k8s_client.ApiException as e:
            print(
                f"  WARNING: could not restart {dep}: {e.status}",
                file=sys.stderr,
            )
    print("[Token] Done.")


# ---------------------------------------------------------------------------
# Integration webhook + trigger (Zammad → POST /zammad/webhook)
# ---------------------------------------------------------------------------


def _ssl_verify_for_endpoint(endpoint: str) -> bool:
    return endpoint.strip().lower().startswith("https://")


def _parse_zammad_index_list(data: object) -> list | None:
    """Normalize GET index JSON: bare array, ``records``, model-specific keys, or ``assets`` bundles."""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return None
    block = data.get("records")
    if isinstance(block, list):
        return block
    assets = data.get("assets")
    if isinstance(assets, dict):
        for ak in ("TicketArticleSender", "TicketArticle::Sender"):
            bundle = assets.get(ak)
            if isinstance(bundle, dict):
                return list(bundle.values())
    return None


def _resolve_customer_sender_id() -> tuple[int, str]:
    """Return (sender_id, provenance) for trigger condition ``article.sender_id``."""
    raw = os.environ.get("ZAMMAD_CUSTOMER_SENDER_ID", "").strip()
    if raw.isdigit():
        return int(raw), "env ZAMMAD_CUSTOMER_SENDER_ID"
    return (
        DEFAULT_CUSTOMER_ARTICLE_SENDER_ID,
        f"default id={DEFAULT_CUSTOMER_ARTICLE_SENDER_ID} (stock Customer sender seed)",
    )


def _get_record_list(path: str):
    """GET /api/v1/{path}; return list of records."""
    data = api("GET", path)
    parsed = _parse_zammad_index_list(data)
    return parsed if parsed is not None else []


def _find_by_name(records, name: str):
    for r in records:
        if r.get("name") == name:
            return r
    return None


def _split_csv_env(key: str) -> list[str]:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def _zammad_ticket_tags_value(tags: list[str]) -> str:
    """Format tag names for Zammad ``ticket.*tags`` conditions.

    ``Selector::Sql`` always does ``value.split(',').map(&:strip)`` for ticket.tags;
    sending a JSON array causes Ruby to call ``.split`` on an Array and validation fails (422).
    Tag names must not contain commas (Zammad token limitation).
    """
    return ",".join(tags)


def _env_truthy(key: str) -> bool:
    return os.environ.get(key, "").strip().lower() in ("1", "true", "yes", "on")


def _integration_trigger_condition(sender_id: int) -> tuple[dict, list[str]]:
    """Build trigger ``condition`` (article create + sender + customer + state + optional filters).

    Returns (condition, log_notes).
    """
    condition = {
        "article.action": {"operator": "is", "value": "create"},
        "article.sender_id": {"operator": "is", "value": sender_id},
        # UI equivalent: Customer is current user
        "ticket.customer_id": {
            "operator": "is",
            "pre_condition": "current_user.id",
            "value": "",
            "value_completion": "",
        },
    }
    notes: list[str] = []

    skip_group = _env_truthy("ZAMMAD_TRIGGER_SKIP_GROUP_FILTER")
    raw_groups = os.environ.get("ZAMMAD_TRIGGER_GROUP_IDS", "").strip()
    raw_names = os.environ.get("ZAMMAD_TRIGGER_GROUP_NAMES", "").strip()

    if skip_group:
        notes.append("group filter off (ZAMMAD_TRIGGER_SKIP_GROUP_FILTER)")
        if raw_groups or raw_names:
            notes.append(
                "(ZAMMAD_TRIGGER_SKIP_GROUP_FILTER ignores GROUP_IDS / GROUP_NAMES)"
            )
    elif raw_groups:
        ids: list[int] = []
        for part in raw_groups.split(","):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
        if ids:
            if len(ids) == 1:
                condition["ticket.group_id"] = {"operator": "is", "value": ids[0]}
            else:
                condition["ticket.group_id"] = {"operator": "is any of", "value": ids}
            notes.append(
                f"ticket.group_id from ZAMMAD_TRIGGER_GROUP_IDS ({len(ids)} id(s))"
            )
    elif raw_names:
        names = [x.strip() for x in raw_names.split(",") if x.strip()]
        ids_from_names: list[int] = []
        for n in names:
            gid = lookup_group_id_by_name(n)
            if gid is None:
                print(
                    f"ERROR: ZAMMAD_TRIGGER_GROUP_NAMES: no Zammad group named {n!r}. "
                    "Create the group or fix the spelling.",
                    file=sys.stderr,
                )
                sys.exit(1)
            ids_from_names.append(gid)
        if len(ids_from_names) == 1:
            condition["ticket.group_id"] = {
                "operator": "is",
                "value": ids_from_names[0],
            }
        else:
            condition["ticket.group_id"] = {
                "operator": "is any of",
                "value": ids_from_names,
            }
        notes.append(
            f"ticket.group_id from ZAMMAD_TRIGGER_GROUP_NAMES {names} -> ids {ids_from_names}"
        )

    tags_any = _split_csv_env("ZAMMAD_TRIGGER_TAGS_ANY")
    tags_all = _split_csv_env("ZAMMAD_TRIGGER_TAGS_ALL")
    tags_exclude = _split_csv_env("ZAMMAD_TRIGGER_TAGS_EXCLUDE")
    tag_modes = sum(bool(x) for x in (tags_any, tags_all, tags_exclude))
    if tag_modes > 1:
        print(
            "ERROR: Use only one of ZAMMAD_TRIGGER_TAGS_ANY, ZAMMAD_TRIGGER_TAGS_ALL, "
            "or ZAMMAD_TRIGGER_TAGS_EXCLUDE (single ticket.tags condition in bootstrap).",
            file=sys.stderr,
        )
        sys.exit(1)
    if tags_exclude:
        # Operator must be a Tags operator (not plain "contains not"). Value must be a comma-separated
        # string — Zammad runs .split(',') on ticket.tags values; arrays break validation (422).
        condition["ticket.tags"] = {
            "operator": "contains all not",
            "value": _zammad_ticket_tags_value(tags_exclude),
        }
        notes.append(
            f"ticket.tags exclude {tags_exclude} (contains all not — comma-separated value for Zammad API)"
        )
    elif tags_any:
        condition["ticket.tags"] = {
            "operator": "contains one",
            "value": _zammad_ticket_tags_value(tags_any),
        }
    elif tags_all:
        condition["ticket.tags"] = {
            "operator": "contains all",
            "value": _zammad_ticket_tags_value(tags_all),
        }

    state_names = ("new", "open")
    state_ids: list[int] = []
    for sn in state_names:
        sid = lookup_ticket_state_id_by_name(sn)
        if sid is None:
            print(
                f"ERROR: integration trigger requires ticket states {list(state_names)!r}; "
                f"no Zammad ticket_state named {sn!r} (GET /api/v1/ticket_states).",
                file=sys.stderr,
            )
            sys.exit(1)
        state_ids.append(sid)
    condition["ticket.state_id"] = {
        "operator": "is any of",
        "value": state_ids,
    }
    notes.append("ticket.customer_id is current user")
    notes.append(f"ticket.state_id is any of {list(state_names)} -> ids {state_ids}")

    return condition, notes


# ---------------------------------------------------------------------------
# Agent overviews
# ---------------------------------------------------------------------------

DEFAULT_ADMIN_ROLE_ID = 1


def _overview_tag_value(*tags: str) -> str:
    return ",".join(tags)


def get_or_create_overview(name: str, body: dict) -> None:
    overviews = _get_record_list("overviews")
    existing = _find_by_name(overviews, name)
    if existing:
        oid = existing["id"]
        api("PUT", f"overviews/{oid}", json=body)
        print(f"  Updated overview '{name}' (id={oid}).")
    else:
        result = api("POST", "overviews", json=body)
        oid = result.get("id", "?") if isinstance(result, dict) else "?"
        print(f"  Created overview '{name}' (id={oid}).")


def ensure_agent_overviews() -> None:
    tag_laptop = (
        os.environ.get(
            "ZAMMAD_AGENT_MANAGED_TAG", "agent-managed-laptop-refresh"
        ).strip()
        or "agent-managed-laptop-refresh"
    )
    tag_general = (
        os.environ.get(
            "ZAMMAD_GENERAL_AGENT_MANAGED_TAG", "agent-managed-general-support"
        ).strip()
        or "agent-managed-general-support"
    )
    tag_escalate = (
        os.environ.get("ZAMMAD_TAG_ESCALATE_HUMAN", "escalated-human-review").strip()
        or "escalated-human-review"
    )
    tag_manager = (
        os.environ.get("ZAMMAD_TAG_MANAGER_REVIEW", "pending-manager-review").strip()
        or "pending-manager-review"
    )
    tag_closed_ai = (
        os.environ.get("ZAMMAD_TAG_CLOSED_BY_AI", "closed-by-ai-agent").strip()
        or "closed-by-ai-agent"
    )

    _default_view = {
        "d": ["title", "customer", "state", "owner", "created_at"],
        "s": ["title", "state", "created_at"],
        "m": ["title"],
    }
    _default_order = {"by": "created_at", "direction": "DESC"}

    def _overview(name: str, tag_value: str) -> None:
        body = {
            "name": name,
            "active": True,
            "role_ids": [DEFAULT_ADMIN_ROLE_ID],
            "user_ids": [],
            "condition": {
                "ticket.tags": {
                    "operator": "contains all",
                    "value": tag_value,
                }
            },
            "order": _default_order,
            "view": _default_view,
            "out_of_office": False,
            "shared_organization": False,
        }
        get_or_create_overview(name, body)

    _overview("AI LR agent — All Tickets", _overview_tag_value(tag_laptop))
    _overview(
        "AI LR agent — Closed by Agent", _overview_tag_value(tag_laptop, tag_closed_ai)
    )
    _overview(
        "AI LR agent — Escalated to Human",
        _overview_tag_value(tag_laptop, tag_escalate),
    )
    _overview(
        "AI LR agent — Pending Manager Review",
        _overview_tag_value(tag_laptop, tag_manager),
    )
    _overview("AI Gen agent — All Tickets", _overview_tag_value(tag_general))
    _overview(
        "AI Gen agent — Closed by Agent",
        _overview_tag_value(tag_general, tag_closed_ai),
    )
    _overview(
        "AI Gen agent — Escalated to Human",
        _overview_tag_value(tag_general, tag_escalate),
    )


def ensure_integration_webhook_and_trigger():
    """Create or update Zammad Webhook + Trigger for integration-dispatcher POST /zammad/webhook."""
    endpoint = os.environ.get("ZAMMAD_INTEGRATION_WEBHOOK_URL", "").strip()
    if not endpoint:
        print(
            "\n[6/7] Skipping Zammad→blueprint webhook bootstrap"
            "(unset ZAMMAD_INTEGRATION_WEBHOOK_URL — configure manually per docs §5.2)."
        )
        return

    secret = os.environ.get("ZAMMAD_WEBHOOK_SECRET", "").strip()
    sender_id, sender_src = _resolve_customer_sender_id()

    print(
        "\n[6/7] Ensuring Zammad Webhook + Trigger (customer articles → integration-dispatcher)..."
    )
    print(f"  Trigger article.sender_id={sender_id} ({sender_src}).")
    webhooks = _get_record_list("webhooks")
    hook = _find_by_name(webhooks, WEBHOOK_RECORD_NAME)

    webhook_body = {
        "name": WEBHOOK_RECORD_NAME,
        "endpoint": endpoint,
        "http_method": "post",
        "ssl_verify": _ssl_verify_for_endpoint(endpoint),
        "active": True,
    }
    if secret:
        webhook_body["signature_token"] = secret

    if hook:
        webhook_id = hook["id"]
        print(f"  Updating webhook '{WEBHOOK_RECORD_NAME}' (id={webhook_id})...")
        api("PUT", f"webhooks/{webhook_id}", json=webhook_body)
    else:
        print(f"  Creating webhook '{WEBHOOK_RECORD_NAME}'...")
        created = api("POST", "webhooks", json=webhook_body)
        webhook_id = created["id"]

    triggers = _get_record_list("triggers")
    trig = _find_by_name(triggers, TRIGGER_RECORD_NAME)

    trigger_condition, cond_notes = _integration_trigger_condition(sender_id)
    for line in cond_notes:
        print(f"  {line}")
    extra = []
    if "ticket.group_id" in trigger_condition:
        extra.append("ticket.group_id")
    if "ticket.tags" in trigger_condition:
        extra.append("ticket.tags")
    if "ticket.customer_id" in trigger_condition:
        extra.append("ticket.customer_id")
    if "ticket.state_id" in trigger_condition:
        extra.append("ticket.state_id")
    if extra:
        print(
            f"  Trigger conditions include: article create + customer sender + {', '.join(extra)}"
        )

    trigger_body = {
        "name": TRIGGER_RECORD_NAME,
        "activator": "action",
        "execution_condition_mode": "selective",
        "condition": trigger_condition,
        "perform": {"notification.webhook": {"webhook_id": webhook_id}},
        "active": True,
    }

    if trig:
        tid = trig["id"]
        print(f"  Updating trigger '{TRIGGER_RECORD_NAME}' (id={tid})...")
        api("PUT", f"triggers/{tid}", json=trigger_body)
    else:
        print(f"  Creating trigger '{TRIGGER_RECORD_NAME}'...")
        api("POST", "triggers", json=trigger_body)

    print("  Done — Zammad will POST customer articles to the configured URL.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    wait_for_zammad_init_job()
    wait_for_zammad()
    trigger_autowizard()
    acquire_token()

    print("\n[1/6] Ensuring custom attributes exist...")
    ensure_custom_user_attributes()

    print("\n[2/6] Creating groups...")
    users_group_id = get_or_create_group("Users")
    group_id = get_or_create_group("human_managed_tickets")
    escalated_group_id = get_or_create_group("escalated_laptop_refresh_tickets")
    ensure_customer_ticket_create_group_ids(users_group_id)

    print("\n[3/6] Role IDs (stock Zammad seeds)...")
    agent_role_ids = [DEFAULT_AGENT_ROLE_ID]
    customer_role_ids = [DEFAULT_CUSTOMER_ROLE_ID]
    print(
        f"  Agent role id={agent_role_ids}, Customer role id={customer_role_ids} "
        f"(db/seeds: Agent={DEFAULT_AGENT_ROLE_ID}, Customer={DEFAULT_CUSTOMER_ROLE_ID})"
    )

    print("\n[3b/6] Adding admin user to all groups...")
    admin = find_user_by_email("admin@zammad.local")
    if admin:
        api(
            "PUT",
            f"users/{admin['id']}",
            json={
                "group_ids": {
                    str(users_group_id): ["full"],
                    str(group_id): ["full"],
                    str(escalated_group_id): ["full"],
                }
            },
        )
        print(f"  Admin user (id={admin['id']}) added to all groups.")
    else:
        print("  WARNING: admin@zammad.local not found, skipping group assignment.")

    print("\n[4/6] Creating ticket handlers, managers and specialists...")
    # Laptop / general specialists need the same agent queues the ticket may move through;
    # REST ``From`` impersonates them, so ``TicketPolicy`` requires group access on the ticket.
    specialist_group_ids = {
        str(users_group_id): ["full"],
        str(group_id): ["full"],
        str(escalated_group_id): ["full"],
    }
    get_or_create_user(
        "agent.laptop-specialist",
        "Laptop",
        "Specialist",
        "agent.laptop-specialist@example.com",
        role_ids=agent_role_ids,
        group_ids=specialist_group_ids,
    )
    get_or_create_user(
        "agent.general",
        "General",
        "Agent",
        "agent.general@example.com",
        role_ids=agent_role_ids,
        group_ids=specialist_group_ids,
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
    # Managers must belong to human_managed_tickets too — otherwise Zammad clears owner when
    # send_to_manager_review moves the ticket there (owner must have rights on ticket group).
    get_or_create_user(
        "manager1",
        "Manager",
        "One",
        MANAGER1_EMAIL,
        role_ids=agent_role_ids + customer_role_ids,
        group_ids={
            str(users_group_id): ["full"],
            str(group_id): ["full"],
        },
    )
    get_or_create_user(
        "manager2",
        "Manager",
        "Two",
        MANAGER2_EMAIL,
        role_ids=agent_role_ids + customer_role_ids,
        group_ids={
            str(users_group_id): ["full"],
            str(group_id): ["full"],
        },
    )

    print("\n[5/6] Creating employees from mock-employee-data...")
    employees = list(get_employee_data().values())
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
            current_laptop=build_current_laptop_json(emp),
        )

    ensure_integration_webhook_and_trigger()

    print("\n[7/7] Ensuring admin overviews for AI agent statistics...")
    ensure_agent_overviews()

    print("\nZammad bootstrap complete.")

    if os.environ.get("ZAMMAD_CREATE_TOKEN") == "true":
        create_mcp_token_and_update_k8s()


if __name__ == "__main__":
    main()
