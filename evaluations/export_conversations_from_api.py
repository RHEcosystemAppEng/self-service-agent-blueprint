#!/usr/bin/env python3
"""
Export real conversations from Request Manager into eval format.

By default runs the get-conversations script inside the request-manager pod via
`kubectl exec` (or `oc exec` if --exec-cli oc), so the API is called from
in-cluster (localhost:8080). No need for shared-clients or a reachable
REQUEST_MANAGER_URL from the host.

Uses test/get-conversations-request-mgr.py in the container (same script as
`kubectl exec ... -- python /app/test/get-conversations-request-mgr.py`). Output is
converted to the same format as generator.py and run_conversations.py:
- metadata.authoritative_user_id (from session user_email or user_id)
- metadata.description
- conversation: list of { "role": "user" | "assistant", "content": "..." }

Saved files go to results/conversation_results/ and can be evaluated with:
  uv run deep_eval.py --results-dir results/conversation_results

Pass --agent-id laptop-refresh (or another agent name) to restrict export to
sessions that used that agent; otherwise all sessions are eligible.

Invoked by evaluate.py when --conversation-source export (step 2 in the pipeline).
Uses the same -n/--num-conversations as the pipeline.

Usage:
  # Default: kubectl exec into request-manager pod (set NAMESPACE or use --namespace)
  uv run export_conversations_from_api.py -n 20
  NAMESPACE=<namespace> uv run export_conversations_from_api.py -n 10
  uv run export_conversations_from_api.py -n 5 --namespace tommy --user-email user@example.com
  uv run export_conversations_from_api.py -n 20 --start-date 2026-01-01T00:00:00Z --end-date 2026-01-31T23:59:59Z
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, cast


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export Request Manager conversations to eval-format JSON files (via oc exec)"
    )
    parser.add_argument(
        "-n",
        "--num-conversations",
        type=int,
        default=20,
        help="Number of sessions to export (same -n as evaluate.py; default 20)",
    )
    parser.add_argument("--offset", type=int, default=0, help="Pagination offset")
    parser.add_argument(
        "--agent-id",
        default=None,
        help="Only export sessions that used this agent (optional)",
    )
    parser.add_argument("--user-email", help="Filter by user email")
    parser.add_argument("--user-id", help="Filter by user ID")
    parser.add_argument("--session-id", help="Filter by session ID")
    parser.add_argument(
        "--start-date",
        help="Filter from date; ISO 8601 format (e.g., 2026-01-01T00:00:00Z)",
    )
    parser.add_argument(
        "--end-date",
        help="Filter to date; ISO 8601 format (e.g., 2026-01-31T23:59:59Z)",
    )
    parser.add_argument(
        "--no-messages",
        action="store_true",
        help="Exclude conversation messages (only session metadata)",
    )
    parser.add_argument(
        "--random",
        action="store_true",
        default=True,
        help="Return random sample of sessions (default: True)",
    )
    parser.add_argument(
        "--no-random",
        action="store_false",
        dest="random",
        help="Return sessions in order (most recent first) instead of random sample",
    )
    parser.add_argument(
        "--output-dir",
        default="results/conversation_results",
        help="Output directory (default results/conversation_results)",
    )
    parser.add_argument(
        "--namespace",
        "-N",
        dest="exec_namespace",
        default=os.environ.get("NAMESPACE") or None,
        help="Namespace for request-manager pod (default: NAMESPACE env if set; else exec uses current context)",
    )
    parser.add_argument(
        "--deploy",
        default="deploy/self-service-agent-request-manager",
        help="Deploy/pod selector (default: deploy/self-service-agent-request-manager)",
    )
    parser.add_argument(
        "--exec-cli",
        default="kubectl",
        help="CLI for exec (kubectl or oc; default: kubectl)",
    )
    return parser.parse_args()


def _is_token_summary_turn(user_msg: str, agent_msg: str) -> bool:
    """True if this turn is the CLI **tokens** command and TOKEN_SUMMARY response."""
    u = (user_msg or "").strip()
    a = (agent_msg or "").strip()
    return u == "**tokens**" and a.startswith("TOKEN_SUMMARY:")


def _session_to_eval_format(session: dict[str, Any]) -> dict[str, Any]:
    """Convert one API session to eval format (metadata + conversation turns).
    Drops CLI token-summary turns (user **tokens** / assistant TOKEN_SUMMARY) so
    from_api aligns with generated_flow for evaluation.
    """
    authoritative_user_id = (
        session.get("user_email") or session.get("user_id") or "unknown"
    )
    full_sid = session.get("session_id") or "unknown"
    sid_short = full_sid[:8]
    metadata = {
        "authoritative_user_id": authoritative_user_id,
        "description": f"From Request Manager (session {sid_short})",
        "session_id": full_sid,
    }
    conversation: list[dict[str, str]] = []
    for item in session.get("conversation") or []:
        user_msg = item.get("user_message")
        agent_msg = item.get("agent_response")
        if _is_token_summary_turn(user_msg or "", agent_msg or ""):
            continue
        if user_msg is not None and str(user_msg).strip():
            conversation.append({"role": "user", "content": str(user_msg)})
        if agent_msg is not None and str(agent_msg).strip():
            conversation.append({"role": "assistant", "content": str(agent_msg)})
    return {"metadata": metadata, "conversation": conversation}


def _save_eval_file(payload: dict[str, Any], base_name: str, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{base_name}_{ts}.json"
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def _cleanup_old_export_files(output_dir: str) -> None:
    """Remove existing from_api_* files in output_dir so this run writes a fresh set."""
    out = Path(output_dir)
    if not out.exists():
        return
    for f in out.glob("from_api_*"):
        try:
            f.unlink()
        except OSError:
            pass


def _fetch_via_exec(args: argparse.Namespace) -> dict[str, Any] | None:
    """Run get-conversations-request-mgr.py inside the request-manager pod; return parsed JSON or None."""
    limit = args.num_conversations
    cmd = [args.exec_cli, "exec", args.deploy]
    if args.exec_namespace:
        cmd.extend(["-n", args.exec_namespace])
    cmd.extend(
        [
            "--",
            "python",
            "/app/test/get-conversations-request-mgr.py",
            "--limit",
            str(limit),
            "--offset",
            str(args.offset),
        ]
    )
    if args.user_email:
        cmd.extend(["--user-email", args.user_email])
    if args.user_id:
        cmd.extend(["--user-id", args.user_id])
    if args.session_id:
        cmd.extend(["--session-id", args.session_id])
    if args.agent_id:
        cmd.extend(["--agent-id", args.agent_id])
    if args.start_date:
        cmd.extend(["--start-date", args.start_date])
    if args.end_date:
        cmd.extend(["--end-date", args.end_date])
    if args.no_messages:
        cmd.append("--no-messages")
    if args.random:
        cmd.append("--random")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=Path(__file__).resolve().parent,
        )
    except FileNotFoundError:
        print(
            f"{args.exec_cli} not found. Install kubectl (or use --exec-cli oc).",
            file=sys.stderr,
        )
        return None
    except subprocess.TimeoutExpired:
        print(f"{args.exec_cli} exec timed out after 120s.", file=sys.stderr)
        return None

    if result.returncode != 0:
        print(
            f"{args.exec_cli} exec failed (exit {result.returncode}): {result.stderr or result.stdout}",
            file=sys.stderr,
        )
        return None

    try:
        return cast("dict[str, Any]", json.loads(result.stdout))
    except json.JSONDecodeError as e:
        print(f"Invalid JSON from pod: {e}", file=sys.stderr)
        return None


def _run(args: argparse.Namespace) -> int:
    _cleanup_old_export_files(args.output_dir)
    data = _fetch_via_exec(args)
    if data is None:
        return 1

    sessions = data.get("sessions") or []
    if not sessions:
        print("No sessions returned.", file=sys.stderr)
        return 0

    total_available = data.get("total")
    if total_available is not None and total_available < args.num_conversations:
        print(
            f"Note: requested {args.num_conversations}, only {total_available} session(s) available.",
            file=sys.stderr,
        )

    saved = []
    skipped = 0
    for session in sessions:
        eval_payload = _session_to_eval_format(session)
        if len(eval_payload["conversation"]) < 2:
            skipped += 1
            continue
        sid = (session.get("session_id") or "unknown")[:8]
        path = _save_eval_file(eval_payload, f"from_api_{sid}", args.output_dir)
        saved.append(path)
    if skipped:
        print(f"Skipped {skipped} session(s) with fewer than 2 turns.", file=sys.stderr)
    print(f"Exported {len(saved)} conversation(s) to {args.output_dir}")
    for p in saved:
        print(f"  {p}")
    return 0


def main() -> int:
    args = _parse_args()
    return _run(args)


if __name__ == "__main__":
    sys.exit(main())
