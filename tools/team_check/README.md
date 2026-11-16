# Cadence cloud reviewer contract

Run from the repository root with Python 3.9+ and pinned Gemini CLI 0.68.0:

```
python tools/team_check/check.py collect --state-dir .team-check
python tools/team_check/check.py model --state-dir .team-check
python tools/team_check/check.py publish --state-dir .team-check --dry-run
```

Only an explicit `--publish` on the final command posts a meaningful review and saves a checkpoint. Give `GH_TOKEN` only to collect/publish and `GEMINI_API_KEY` only to model. The model subprocess uses a minimal environment without GitHub job/runtime credentials. GitHub Actions runs are restricted to this repository and schedule/manual-dispatch events; no source-changing agent runs on pull requests.

Cache **only `.team-check/checkpoint.json`** between runs. Never upload/cache profile history or SDK logs. The checkpoint allows unchanged/nonactionable updates to skip model calls. Existing trusted board marker comments recover duplicate suppression if a cache is lost. Use one concurrency group and a job timeout longer than the 4-minute model limit; do not cancel an active publish in favor of a new scheduled pass.

The CLI asks the distinct teammate to choose/confirm **Cadence**, keeping it separate from Antigravity's John's Gemini. A response cannot be published without explicit name confirmation and verified `gemini-3.8-flash` model statistics. No model/name onboarding is claimed before a successful response. Automated reviews cannot edit source, run shell tools, merge PRs or perform hardware tests.

The setup uses plan mode, a deny policy, no extensions, disabled model auto-routing/retry/relaunch, and process-group timeout cleanup. Provider overload/quota/auth failures leave the checkpoint unchanged and cause no fallback or board post. Raw SDK errors are withheld to avoid credential leakage.

Tests: `python -m unittest discover -s tools/team_check -p 'test_*.py'`. The test module only mocks CLI/GitHub calls; it never uses credentials or invokes a model.
