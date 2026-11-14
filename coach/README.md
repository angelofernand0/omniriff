# Practice coach

The coach is a separate process. It reads completed take WAV/sidecar pairs and
an optional webcam hand log, publishes full coach frames on the loopback
WebSocket `127.0.0.1:47803`, and sends a normal `source: "coach"` UDP control
only after a player approval. Stopping it does not stop the audio engine.

Install the optional dependencies with `python -m pip install -r
coach/requirements.txt` (requires Python 3.11+, e.g. `py -3.12` on Windows). Put
`ANTHROPIC_API_KEY` in a gitignored repo `.env` or `~/.config/omniriff/.env`;
never copy it into the browser or repository.

The hardware-free path is `python -m coach --fixtures`. It generates three
explicitly synthetic guitar/hand takes and waits for dashboard approval. It
does not connect to an engine. For a noninteractive **synthetic
fixture only** check, use `python -m coach --fixtures
--auto-approve-fixtures`. This flag never works with a live rig. Use
`--fixture-limit 1` to bound a first run. Note that `--fixtures` still requires
`ANTHROPIC_API_KEY` and calls the paid model (synthetic takes, real model); the
genuine zero-key, zero-cost offline check is `python -m coach.smoke --tools-only`. The
local guard refuses new runs when its conservative estimated usage is near $8.
`coach/workspace/usage.jsonl` stores counts and an upper-bound estimate, not
the provider's bill. Fixture mode prints `SYNTHETIC FIXTURES` in the terminal.
Its feed has `scripted: false` because the agent is live; that flag does **not**
mean the guitar or camera input was live. Do not present fixture results as a
real performance.
Fixture runs use an ignored `coach/workspace-fixtures/` profile. They never
read or overwrite the real `coach/workspace/memories/player.md`; both modes
share only the conservative usage ledger. A second session opens with a
"Last time…" cue derived from the latest measured before/after numbers, with
synthetic history clearly named as such.

For the full local rig, `python -m engine.demo --coach --vision --hand-log
runs/hand.jsonl` starts the coach beside the engine and dashboard. The coach
uses the engine's take directory and state socket; it never imports the engine
or runs inference in its audio callback. If the vision window API is missing
or camera data are absent, it reports hand data unavailable and teaches from
audio timing only.

Tests without a model key: `python -m unittest discover -s tests -p
test_coach_core.py -v`. The API smoke harness is `python -m coach.smoke
--tools-only`; omitting `--tools-only` makes one paid model call.

In a live session, Riff asks for a goal before the first take. The dashboard
TALK/typed input reaches the runner as `coach.say`; after the first take it is
a note for the next decision. The runner uses judgeable TakeReports for a
two-drill plan with up to three attempts per drill, displays the strongest
measured hesitation as a take-relative loop mark, then returns to quiet PLAY.
The pedal's accepted `practice_count` starts or pauses a round; a new spoken
goal can also start one from PLAY. The engine remains independent of the coach.
The budget guard checks each parent, Ears, Eyes and summarization model call;
the `$8` ceiling is a conservative local estimate, **not** a provider billing
cap. No paid-model quality claim is made by the offline tests.
