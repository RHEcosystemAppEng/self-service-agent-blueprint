#!/usr/bin/env python3
"""Bump the blueprint release version using bump-release.manifest.json (rule + paths[] per entry)."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from typing import Callable

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
DEFAULT_MANIFEST = SCRIPT_DIR / "bump-release.manifest.json"


def read_makefile_base_version(makefile: str, **_: object) -> str:
    m = re.search(r"^BASE_VERSION := (.+)$", makefile, re.MULTILINE)
    if not m:
        sys.exit("Could not find BASE_VERSION in Makefile")
    return m.group(1).strip()


def extract_chart_app_version(
    text: str, *, context_path: str = "", **__: object
) -> str:
    for line in text.splitlines():
        if line.startswith("appVersion:"):
            rest = line[len("appVersion:") :].strip()
            return rest.strip('"').strip("'")
    ctx = f" ({context_path})" if context_path else ""
    sys.exit(f"Could not find appVersion in Chart.yaml{ctx}")


def extract_release_image_tag_anchor(
    text: str, *, context_path: str = "", **__: object
) -> str:
    m = re.search(r'^\s+tag: &releaseImageTag "([^"]+)"', text, flags=re.MULTILINE)
    if not m:
        ctx = f" ({context_path})" if context_path else ""
        sys.exit('Could not find tag: &releaseImageTag "..." in helm values' + ctx)
    return m.group(1)


def extract_bootstrap_image_tag(
    text: str, *, context_path: str = "", **__: object
) -> str:
    m = re.search(r"^(\s+)imageTag:\s*\"([^\"]+)\"", text, flags=re.MULTILINE)
    if not m:
        ctx = f" ({context_path})" if context_path else ""
        sys.exit(f"Could not find bootstrap imageTag in{ctx}")
    return m.group(2)


EXTRACTORS: dict[str, Callable[..., str]] = {
    "makefile_base_version": read_makefile_base_version,
    "chart_app_version": extract_chart_app_version,
    "release_image_tag_anchor": extract_release_image_tag_anchor,
    "bootstrap_image_tag": extract_bootstrap_image_tag,
}


def read_manifest_file(
    rel: str, *, git_ref: str | None, repo_root: pathlib.Path
) -> str:
    """Load file text from the working tree or via git show REF:path."""
    if git_ref:
        cp = subprocess.run(
            ["git", "show", f"{git_ref}:{rel}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if cp.returncode != 0:
            sys.exit(
                f"git show {git_ref}:{rel} failed: {cp.stderr.strip() or cp.stdout.strip()}"
            )
        return cp.stdout
    path = repo_root / rel
    if not path.is_file():
        sys.exit(f"Manifest path does not exist or is not a file: {rel}")
    return path.read_text(encoding="utf-8")


def verify_manifest_alignment(
    manifest_path: pathlib.Path, *, git_ref: str | None, repo_root: pathlib.Path
) -> str:
    """Ensure every manifest path's embedded version matches Makefile BASE_VERSION. Returns base version."""
    data = load_manifest(manifest_path)
    makefile_text = read_manifest_file("Makefile", git_ref=git_ref, repo_root=repo_root)
    base = read_makefile_base_version(makefile_text)

    errors: list[str] = []
    for item in data["replacements"]:
        rule_name = item["rule"]
        extractor = EXTRACTORS[rule_name]
        for rel in item["paths"]:
            text = read_manifest_file(rel, git_ref=git_ref, repo_root=repo_root)
            found = extractor(text, context_path=rel)
            if found != base:
                errors.append(
                    f"{rel} ({rule_name}): found {found!r}, expected {base!r} (Makefile BASE_VERSION)"
                )

    if errors:
        ref_note = f" (git ref {git_ref})" if git_ref else ""
        print(
            f"::error::Release version mismatch across manifest{ref_note}; fix with ./scripts/bump-release.sh {base}",
            file=sys.stderr,
        )
        for msg in errors:
            print(f"::error::{msg}", file=sys.stderr)
        sys.exit(1)

    print(f"✅ bump-release manifest aligned with Makefile BASE_VERSION ({base})")
    return base


def replace_makefile_base_version(text: str, new_ver: str, **_: object) -> str:
    def repl(match: re.Match[str]) -> str:
        return f"{match.group(1)}{new_ver}"

    out, n = re.subn(r"^(BASE_VERSION := ).+$", repl, text, count=1, flags=re.MULTILINE)
    if n != 1:
        sys.exit("Failed to replace BASE_VERSION in Makefile")
    return out


def replace_chart_app_version(text: str, new_ver: str, **_: object) -> str:
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.startswith("appVersion:"):
            rest = line[len("appVersion:") :].strip()
            if rest.startswith('"') and rest.endswith('"'):
                lines[i] = f'appVersion: "{new_ver}"\n'
            elif rest.startswith("'") and rest.endswith("'"):
                lines[i] = f"appVersion: '{new_ver}'\n"
            else:
                lines[i] = f"appVersion: {new_ver}\n"
            return "".join(lines)
    sys.exit("Could not find appVersion in helm/Chart.yaml")


def replace_release_image_tag_anchor(text: str, new_ver: str, **_: object) -> str:
    pattern = r'(^\s+tag: &releaseImageTag )"[^"]+"'
    out, n = re.subn(pattern, rf'\1"{new_ver}"', text, count=1, flags=re.MULTILINE)
    if n != 1:
        sys.exit(
            'Could not find exactly one line matching: tag: &releaseImageTag "..." (release_image_tag_anchor rule)'
        )
    return out


def replace_bootstrap_image_tag(
    text: str, new_ver: str, *, context_path: pathlib.Path | None = None, **_: object
) -> str:
    pattern = r"^(\s+imageTag:\s*)\"[^\"]+\""
    out, n = re.subn(pattern, rf'\1"{new_ver}"', text, count=1, flags=re.MULTILINE)
    display = context_path if context_path is not None else "manifest path"
    if n != 1:
        sys.exit(f"Could not find bootstrap imageTag in {display}")
    return out


RULES: dict[str, Callable[..., str]] = {
    "makefile_base_version": replace_makefile_base_version,
    "chart_app_version": replace_chart_app_version,
    "release_image_tag_anchor": replace_release_image_tag_anchor,
    "bootstrap_image_tag": replace_bootstrap_image_tag,
}

if set(EXTRACTORS.keys()) != set(RULES.keys()):
    raise RuntimeError(
        "RULES and EXTRACTORS must define the same rule names (bump vs verify)"
    )


def manifest_rel_paths(data: dict) -> list[str]:
    """Paths from the manifest in JSON order; each path appears once."""
    seen: set[str] = set()
    out: list[str] = []
    for item in data["replacements"]:
        for p in item["paths"]:
            if p not in seen:
                seen.add(p)
                out.append(p)
    return out


def load_manifest(path: pathlib.Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"Manifest not found: {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"Invalid JSON in {path}: {e}")
    if not isinstance(data, dict):
        sys.exit("Manifest root must be a JSON object")
    reps = data.get("replacements")
    if not isinstance(reps, list) or not reps:
        sys.exit('Manifest must contain a non-empty "replacements" array')
    for i, item in enumerate(reps):
        if not isinstance(item, dict):
            sys.exit(f"replacements[{i}] must be an object")
        if "rule" not in item:
            sys.exit(f'replacements[{i}] must have "rule"')
        rule = item["rule"]
        if rule not in RULES:
            sys.exit(f'Unknown rule {rule!r}; known: {", ".join(sorted(RULES))}')
        paths = item.get("paths")
        if not isinstance(paths, list) or not paths:
            sys.exit(f'replacements[{i}] must have a non-empty "paths" array')
        for j, p in enumerate(paths):
            if not isinstance(p, str) or not p.strip():
                sys.exit(f"replacements[{i}].paths[{j}] must be a non-empty string")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        usage="%(prog)s [--verify] [--print-manifest-paths [-0]] [--git-ref REF] [--dry-run] [--manifest PATH] [<version>]",
    )
    parser.add_argument(
        "--manifest",
        type=pathlib.Path,
        default=DEFAULT_MANIFEST,
        help=f"JSON manifest of files and rules (default: {DEFAULT_MANIFEST})",
    )
    parser.add_argument(
        "--print-manifest-paths",
        action="store_true",
        help="Print manifest-relative paths (one per line, or use -0 for xargs -0 git add)",
    )
    parser.add_argument(
        "-0",
        "--null",
        dest="paths_nul_terminated",
        action="store_true",
        help="With --print-manifest-paths: write paths separated by ASCII NUL (safe for xargs -0 git add --)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Exit 0 if Makefile BASE_VERSION matches every path/rule in the manifest (same scope as bump)",
    )
    parser.add_argument(
        "--git-ref",
        metavar="REF",
        default=None,
        help="With --verify: read files via git show REF:path (CI compares dev commit without checkout)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes without writing files",
    )
    parser.add_argument(
        "version",
        nargs="?",
        default=None,
        help="New release version (e.g. 0.0.14); required unless --verify or --print-manifest-paths",
    )
    args = parser.parse_args()

    manifest_path = args.manifest
    if not manifest_path.is_absolute():
        manifest_path = (ROOT / manifest_path).resolve()

    if args.paths_nul_terminated and not args.print_manifest_paths:
        parser.error("-0/--null is only valid with --print-manifest-paths")

    if args.print_manifest_paths:
        if args.verify:
            parser.error("--print-manifest-paths cannot be combined with --verify")
        if args.git_ref:
            parser.error("--print-manifest-paths cannot be combined with --git-ref")
        if args.version:
            parser.error("version must not be given with --print-manifest-paths")
        data = load_manifest(manifest_path)
        paths = manifest_rel_paths(data)
        if args.paths_nul_terminated:
            if paths:
                sys.stdout.buffer.write("\0".join(paths).encode("utf-8"))
        else:
            for rel in paths:
                print(rel)
        return

    if args.verify:
        verify_manifest_alignment(manifest_path, git_ref=args.git_ref, repo_root=ROOT)
        return

    if not args.version:
        parser.error("version is required unless --verify or --print-manifest-paths")

    data = load_manifest(manifest_path)
    new_ver = args.version.strip().strip('"').strip("'")
    if not re.fullmatch(r"\d+\.\d+\.\d+(-\w+)?", new_ver):
        sys.exit(f"Version must look like a semver release tag (got {new_ver!r})")

    makefile_path = ROOT / "Makefile"
    makefile = makefile_path.read_text(encoding="utf-8")
    old_ver = read_makefile_base_version(makefile)

    updates: list[tuple[pathlib.Path, str, str]] = []
    for item in data["replacements"]:
        rule_name = item["rule"]
        rule_fn = RULES[rule_name]
        for rel in item["paths"]:
            path = ROOT / rel
            if not path.is_file():
                sys.exit(f"Manifest path does not exist or is not a file: {rel}")
            text = path.read_text(encoding="utf-8")
            new_text = rule_fn(text, new_ver, context_path=path)
            updates.append((path, new_text, text))

    changed = [(path, nt) for path, nt, ot in updates if nt != ot]
    if not changed:
        print(f"Already at {new_ver}; all manifest paths aligned.")
        return

    if old_ver != new_ver:
        print(f"Bumping release version: {old_ver} -> {new_ver}")
    else:
        print(
            f"Makefile BASE_VERSION already {new_ver}; updating other drifted manifest paths."
        )
    for path, _ in changed:
        print(f"  write {path.relative_to(ROOT)}")
    if not args.dry_run:
        for path, content in changed:
            path.write_text(content, encoding="utf-8")
        print(
            "Done. Review with git diff; build/push images for the new tag as needed."
        )
    else:
        print("(dry-run: no files modified)")


if __name__ == "__main__":
    main()
