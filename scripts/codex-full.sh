#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")/.."
cli=$(command -v codex || true)
if [ -z "$cli" ] && [ -x /Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex ]; then
 cli=/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex
fi
[ -n "$cli" ] || { echo "Install/sign in to Codex first."; exit 1; }
echo "Starting explicitly requested full local execution for this session; OS-account access extends beyond this repo."
exec "$cli" --sandbox danger-full-access --ask-for-approval never "$@"
