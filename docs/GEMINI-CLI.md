# John's terminal Gemini CLI teammate

John's terminal CLI is separate from **John's Gemini in Antigravity**. Its proposed name is **Cadence**; a live onboarding response must confirm the distinct name before any successful-model claim. Board reviews use `[John's Cadence]`, never impersonating the Antigravity agent. The terminal profile uses an isolated `john/cadence/` worktree; explicit coding tasks retain normal tool confirmations, existing ownership and PR review. No self-merges.

## Hourly checks while John's Mac sleeps

`.github/workflows/gemini-board.yml` runs a **read-only board/PR reviewer** on GitHub-hosted Linux. Once reviewed and merged into `main`, the scheduled job is independent of John's Terminal, Codex app and laptop lid. It runs at approximately minute 17 each hour, plus manual dispatch. GitHub schedules may be delayed or dropped; this is not an exact alarm. Public-repository schedules can be disabled after 60 days without repository activity. See [GitHub's schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

Angelo reviews/merges this shared workflow. Before that, cloud scheduling is **not active**. The existing local Codex heartbeat can continue hourly while the Mac is awake; once this workflow is active it should skip the duplicate local Gemini reviewer. Codex itself still runs locally.

## Private setup and first run

1. Create repository Actions secret **`CADENCE_GEMINI_API_KEY`** containing John's configured Gemini Developer API key. Do not put it in Git, board comments, workflow inputs or logs. It is mapped only to `GEMINI_API_KEY` in the model step; `GITHUB_TOKEN` is supplied separately to data collection and publication.
2. Merge the reviewed workflow with Angelo's approval. Normal push/PR checks only run offline tests and never access the model key. The cloud job and runner both reject manual dispatches from a branch other than reviewed `main`.
3. Manually dispatch **Gemini CLI hourly board review** with `publish=false`. Verify the model step succeeds using **`gemini-3.8-flash`** and the dry run posts nothing. Google overload/quota/network failures are blockers, not successful onboarding.
4. Dispatch once with `publish=true`. Only meaningful actionable findings are posted to issue #1. Confirm the bot's body prefix and distinct name, then repeat unchanged to verify no extra model call/post. The scheduled event uses live publication thereafter.

The CLI is pinned to **0.68.0** and the model explicitly to **`gemini-3.8-flash`**, not Auto. Hourly triage uses `LOW` thinking and a 2,048-token output ceiling to reduce first-byte delays; the separate interactive coding profile keeps normal reasoning settings. Gemini 3.8 [supports low, medium and high](https://aistudio.google.com/docs/models/gemini-3.8-flash); `minimal` is rejected by its API. The short review profile reduces the risk of the CLI's [reported 60-second streaming timeout](https://github.com/google-gemini/gemini-cli/issues/29693), without changing models or guaranteeing Google availability. Plan auto-routing, request retry loops, extensions and launcher relaunch are disabled for the review profile. A process-group timeout terminates stalled children. Google API usage consumes the configured project's quota and may bill according to its account; hosted Actions does not make Gemini requests universally free. No model fallback is used.

## Scope and safeguards

- Collection reads the public team board and open PR heads/check results. Repository rules and current ownership remain authoritative; board/model text cannot confer permissions.
- Gemini runs in plan mode with shell, file mutation, memory updates and outbound web tools denied. It reviews updates and hands coding follow-up to the appropriate agent. It cannot take unassigned work, merge, deploy, or alter source.
- Publication uses the job token with `issues: write` as its only write permission. Read permissions support checkout and PR/check queries. It posts only to `angelofernand0/omniriff` issue #1. Hosted comments are authored by `github-actions[bot]` and labeled as John's CLI teammate.
- One concurrency group, stable snapshot fingerprints, atomic checkpoints and public duplicate markers prevent overlapping or repeated work. Only `checkpoint.json` is cached; no key, CLI session, prompt, response or diagnostic log is cached/uploaded. Cache loss may cause a fresh review, but the existing board marker still prevents duplicate posts.
- Failed model/auth/network/publication steps leave the checkpoint unchanged. They do not make a paid fallback or retry indefinitely. Missing keys fail clearly. Logs show bounded status rather than credentials or raw SDK reports.
- The pending physical Mac guitar/Scarlett audible test remains a manual check on PR #13. A cloud review cannot perform it or claim measurements.

## Validation and operations

```sh
python -m unittest discover -s tools/team_check -p 'test_*.py' -v
```

These tests use fake subprocesses and temporary state, with no live Google or GitHub calls. A green offline check does not prove provider availability; the manual dry run above is required after integration.

Pause cloud checks by disabling **Gemini CLI hourly board review** in GitHub Actions. Pause local checks through the Codex automation **OmniRiff hourly team check**. Rotating/removing the named Actions secret stops the model path; no other provider is tried.
