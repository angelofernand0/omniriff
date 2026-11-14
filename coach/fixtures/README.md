# Synthetic coach fixtures

Run `python -m coach.fixtures.generate` to create three deterministic WAV takes,
TakeWriter-shaped JSON sidecars, per-frame hand JSONL logs, and a ground-truth
manifest in `generated/`. The WAVs are physical-model guitar, **not** player
recordings; the wrist positions are synthetic, **not** webcam data.

`coach-before` adds 400 ms at each chord change, with a simultaneous wrist
freeze. `coach-clean` has neither delay nor freeze. `coach-after` retains a
smaller 120 ms delay/freeze to test before/after improvement. The fixture
generator does not require an audio interface, camera, engine, or API key.

The generated files are ignored by Git. They are reproducible from this script
and should not be presented as live measurements. Run
`python -m unittest discover -s tests -p test_coach_fixtures.py -v` for the
Ears/Eyes detection check.
