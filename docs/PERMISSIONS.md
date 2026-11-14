# Access: GitHub and local agents

## GitHub

Repo: https://github.com/angelofernand0/omniriff (public).
Owner Angelo has admin. SM @smcogburn and Aditya @MonkeySeeMonkeyC0de have write invitations; until accepted, invitation is not active collaboration access. Personal-repository collaborators use write access, sufficient for branches, commits, PRs and issue posts. Their agents act with their own account, not separate GitHub identities. No shared token is required.

`bash scripts/doctor.sh` checks current login, canonical origin, board availability and push permission. The setup agent can verify invitation status, but cannot prove SM's local agent permissions or credential scopes from Angelo's computer.

## Full local execution requested by Angelo

The optional launchers below explicitly start an unrestricted local CLI session. Such a session can run commands/network requests with the human account's OS access, including files outside this repo. Use only on a computer/environment you intend to authorize for this work. They do not change global settings, grant GitHub credentials, or reconfigure an already-running app session.

```bash
bash scripts/codex-full.sh
bash scripts/claude-full.sh
```

Codex uses `--sandbox danger-full-access --ask-for-approval never`, verified against the installed CLI help. Claude Code uses its explicit `--dangerously-skip-permissions` opt-in; the launcher checks local help before using it. Each teammate must install/authenticate their own agent and launch it themselves. Aditya may use his normal Codex app permissions instead. App-managed/organization policies can still restrict either CLI.

For a Codex/Claude desktop session, choose the project's available execution/permission controls in that app. A README or AGENTS.md cannot override the app's sandbox. Do not report a teammate's full access as verified until their doctor check and actual task succeed.

Official Codex sandbox reference: https://learn.chatgpt.com/docs/sandboxing
Claude Code permission reference: https://code.claude.com/docs/en/permissions

## Two agents on one machine

```bash
git worktree add ../omniriff-codex -b angelo/codex
git worktree add ../omniriff-claude -b angelo/claude
```

SM uses separate sm/codex and sm/claude branches/worktrees. Do not run both in the original clone simultaneously. Only one process owns a given clone's board read cursor. Read recent comments again when switching worktrees or accounts.
