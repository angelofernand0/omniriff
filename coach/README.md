# Practice coach

The coach is a separate process. It reads completed take WAV/sidecar pairs and
an optional webcam hand log, publishes full coach frames on the loopback
WebSocket `127.0.0.1:47803`, and sends a normal `source: "coach"` UDP control
only after a player approval. Stopping it does not stop the audio engine.

Install the optional dependencies with `python -m pip install -r
coach/requirements.txt`. Put `ANTHROPIC_API_KEY` in a gitignored repo `.env` or
`~/.config/omniriff/.env`; never copy it into the browser or repository.

The hardware-free path is `python -m coach --fixtures`. It generates three
explicitly synthetic guitar/hand takes and waits for dashboard approval. It
does not connect to an engine. For a noninteractive **synthetic
fixture only** check, use `python -m coach --fixtures
--auto-approve-fixtures`. This flag never works with a live rig. Use
`--fixture-limit 1` to bound a first run. These runs call a paid model; the
local guard refuses new runs when its conservative estimated usage is near $8.
`coach/workspace/usage.jsonl` stores counts and an upper-bound estimate, not
the provider's bill. The fixture run is labeled scripted in the feed because
its input is replayed synthetic data, even though the agent itself is live.
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
