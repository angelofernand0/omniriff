# Confirmed team

- Angelo Fernando — @angelofernand0 — lead and integration owner; Codex and Claude Code.
- SM (Seanmanuel) — @smcogburn — Codex and Claude Code. Prefers "SM" in labels and branches.
- Joey (also called John) — @lsj3l — Codex. Joined 2026-11-13.
- Aditya — @MonkeySeeMonkeyC0de — Codex. Back tomorrow night (2026-11-14) for hardware.

## Ownership (agreed 2026-11-13)

Angelo, SM and Joey do the software. Aditya does the hardware: wiring, flashing, and physical mapping. First tasks and acceptance checks are in [docs/TASKS.md](docs/TASKS.md).

| Agent | Owns | Branch prefix |
|---|---|---|
| Angelo's Claude | `audio/`, `tools/latency/`, `tests/acceptance/`, `engine/check.py`, `engine/demo.py`, `engine/session_log.py`, docs (DEMO, DEVPOST, QA, BACKLOG, SUBMISSION); overnight coordination and merges; coach pieces A (take capture) and I (coach control source) | `angelo/claude/` |
| Angelo's Codex | `engine/` runtime/router/replay, `protocol/state.schema.json` | `angelo/codex/` |
| SM's Claude | `dashboard/`, `tools/sim/`, BRAND_SPEC.md; coach pieces D (core/deep agent), E (feed), F (dashboard layer + Riff), H (voice) | `sm/claude/` |
| SM's Codex | `tools/virtual_guitar/` (virtual guitar, playable demo / play room), B16 backup video | `sm/codex/` |
| Joey's Codex | `vision/` gesture control (control, tracking, scenes, setlists, takes, hand view), `tools/tone_match/` | `john/codex/` |
| John's Claude (Joey) | `vision/eyes.py`, `vision/looper.py`; coach pieces C (Eyes) and B (Ears, `tools/ears/`, in progress) | `john/claude/` |
| John's Gemini (Joey) | `vision/zones.py`, `vision/expressive.py`, `vision/stage.py`, `vision/spatial.py` | `john/gemini/` |
| Aditya's Codex | `firmware/arduino/` and `docs/HARDWARE.md` (draft merged in #5; compile/flash pending) | `aditya/codex/` |
| Aditya | Hardware bring-up from 8 PM Saturday: wiring, flashing, Grove button polarity (backlog B3), pin and gesture mapping; `firmware/sensecap/` is stretch | `aditya/` |

Up-to-date work queue: [docs/BACKLOG.md](docs/BACKLOG.md). Coach plan and piece status: [docs/COACH.md](docs/COACH.md).

Shared files (`protocol/`, `README.md`, `AGENTS.md`, `TEAM.md`, `requirements*.txt`, `.github/`) need a heads-up on issue #1. Angelo merges changes to them. Any change to a contract needs a board post before dependent code merges.

### Overflow

When all of Angelo's, SM's and Joey's agents are busy, post a self-contained task on the board for @MonkeySeeMonkeyC0de (Aditya's Codex). Name the files, contract and acceptance check. It only responds while its session is polling the board, so don't block on it.

Two agents belonging to one human must take different tasks and use different clones or worktrees. Their GitHub account is shared, so their comment labels must identify the agent app.
