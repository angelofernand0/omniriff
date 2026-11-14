#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")/.."
command -v claude >/dev/null || { echo "Install/sign in to Claude Code first."; exit 1; }
claude --help | grep -q -- --dangerously-skip-permissions || { echo "Installed Claude CLI does not advertise the expected flag."; exit 1; }
echo "Starting explicitly requested full local execution for this session; OS-account access extends beyond this repo."
exec claude --dangerously-skip-permissions "$@"
