#!/usr/bin/env bash
# Builds the web app and pushes a "release" branch the server installs from:
# backend/ + deploy/ + web/ (already built) + wa/ (the WhatsApp link service, the only part that needs Node), no tests, no mobile.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd); cd "$ROOT"
(cd web && npm run build)
TMP=$(mktemp -d); git worktree add -q --detach "$TMP"
trap 'git worktree remove --force "$TMP"; git -C "$ROOT" branch -D "release-$$" >/dev/null 2>&1 || true' EXIT
cd "$TMP"; git checkout -q --orphan "release-$$"; git rm -rqf .
git -C "$ROOT" archive HEAD backend deploy wa | tar -x; rm -rf backend/tests
cp -r "$ROOT/web/dist" web
git add -A; git commit -qm "Release $(git -C "$ROOT" rev-parse --short HEAD)"
git push -qf origin HEAD:release
echo "release branch updated from $(git -C "$ROOT" rev-parse --short HEAD)"
