# Confirmed team

- Angelo Fernando — @angelofernand0 — lead and integration owner; Codex and Claude Code.
- SM (Seanmanuel) — @smcogburn — Codex and Claude Code. Prefers "SM" in labels and branches.
- Aditya — @MonkeySeeMonkeyC0de — Codex. Back tomorrow night (2026-11-14) for hardware.

Joey is not on this team. No fourth member is confirmed.

## Ownership (agreed 2026-11-13)

Angelo and SM do the software. Aditya does the hardware: wiring, flashing, and physical mapping. First tasks and acceptance checks are in [docs/TASKS.md](docs/TASKS.md).

| Agent | Owns | Branch prefix |
|---|---|---|
| Angelo's Claude | `audio/`: real-time engine, effects, loop, bypass, control mailbox | `angelo/claude/` |
| Angelo's Codex | `engine/`: control bus, UDP/serial adapters, state publisher, `protocol/state.schema.json`, launcher, integration | `angelo/codex/` |
| SM's Claude | `tools/sim/` event simulator first, then `dashboard/` browser status and manual-control UI | `sm/claude/` |
| SM's Codex | `vision/`: webcam hand tracking, gesture → `filter`/`reverb` parameter events. **Unclaimed until SM's Codex posts a claim on issue #1.** | `sm/codex/` |
| Aditya's Codex | `firmware/arduino/` and `docs/HARDWARE.md`: footswitch firmware draft and wiring/mapping sheet | `aditya/codex/` |
| Aditya | Hardware bring-up, flashing, pin and gesture mapping; `firmware/sensecap/` is stretch | `aditya/` |

Shared files (`protocol/`, `README.md`, `AGENTS.md`, `TEAM.md`, `requirements*.txt`, `.github/`) need a heads-up on issue #1. Angelo merges changes to them. Any change to a contract needs a board post before dependent code merges.

### Overflow

When all four of Angelo's and SM's agents are busy, post a self-contained task on the board for @MonkeySeeMonkeyC0de (Aditya's Codex). Name the files, contract and acceptance check. It only responds while its session is polling the board, so don't block on it.

Two agents belonging to one human must take different tasks and use different clones or worktrees. Their GitHub account is shared, so their comment labels must identify the agent app.
