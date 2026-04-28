#!/usr/bin/env bash
# Bump the blueprint release version. Files and replacement rules are listed in
# scripts/bump-release.manifest.json (override with bump_release.py --manifest PATH).
#
# Usage:
#   ./scripts/bump-release.sh <new-version>
#   ./scripts/bump-release.sh --dry-run <new-version>
#   python3 scripts/bump_release.py --verify
#   python3 scripts/bump_release.py --verify --git-ref <sha>   # CI (git show)
#   python3 scripts/bump_release.py --print-manifest-paths --null | xargs -0 git add --
#
# Release checklist (also run CI / image builds as appropriate):
#   [ ] ./scripts/bump-release.sh X.Y.Z
#   [ ] git diff — expect BASE_VERSION, appVersion, tag: &releaseImageTag, helm/zammad bootstrap.imageTag
#   [ ] Build and push container images tagged X.Y.Z if your pipeline requires it
#   [ ] Merge dev → main when checks pass

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/bump_release.py" "$@"
