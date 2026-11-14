#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
command -v gh >/dev/null || { echo "Install GitHub CLI from https://cli.github.com/ and run gh auth login"; exit 1; }
cd "$(dirname "$0")/.."
login=$(gh api user --jq .login)
echo "GitHub account: $login"
repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
[ "$repo" = "angelofernand0/omniriff" ] || { echo "Wrong repository: $repo"; exit 1; }
gh api "repos/$repo" --jq '{full_name,visibility,default_branch,permissions}'
push=$(gh api "repos/$repo" --jq .permissions.push)
[ "$push" = true ] || { echo "No write access yet: accept the invitation or check this account."; exit 1; }
gh api "repos/$repo/issues/1" --jq '{board:.html_url,state}'
echo "PASS: correct identity, repo, push permission and board read. Local agent permissions require a separate check."
