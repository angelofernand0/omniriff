# Tone Match → Gesture Scene

Turn a paired dry/reference guitar recording into an achievable OmniRiff effect,
then move between the original and fitted tone with your hand. This offline tool
searches the **real public audio.Engine** for filter/reverb settings. It exports a
portable audio comparison page and a scene consumed directly by `vision`.

## Try it without hardware

From the repo root, with `requirements-dev.txt` installed:

```sh
python -m tools.tone_match.demo --output /tmp/omniriff-tone-demo
```

Open `/tmp/omniriff-tone-demo/match/index.html`. Hear original → target → matched,
or play each separately. The page pauses other players automatically and has no
external assets, server, tracking, or uploads. The demo uses SM's deterministic
Karplus-Strong guitar synth and a target made with known engine parameters;
those parameters are not supplied to the optimizer. `provenance.json` labels this
as a closed-model synthetic demonstration, not evidence of real-recording accuracy.

## Fit your own paired recordings

```sh
python -m tools.tone_match --dry dry.wav --reference processed.wav \
  --name "Velvet Space" --output /tmp/velvet-space
python -m vision --model /path/to/hand_landmarker.task --scene-file /tmp/velvet-space/scene.json
```

Start the engine separately for live audio. Open your hand to arm, pinch to engage,
and move vertically to morph; release holds the last value. Use the existing
vision calibration workflow before performing. No live camera is needed to fit
or listen to the exported audio.

The input files must contain the **same performance, sample-aligned**, with equal
lengths and sample rates. Use mono or stereo PCM WAV, 0.5–30 seconds, 8–96 kHz.
Stereo is averaged to mono. Include the same leading context and trailing reverb
in both files; trim matching silence together. A silent analysis window is rejected.
The target should have fixed effect settings from the beginning of the phrase.
Unknown latency, changing effects, mastering, another performance, a full song
mix, amp distortion, or a different reverb can prevent a useful fit. The tool
does not align, resample, isolate instruments, or clone amplifiers.

## Outputs and limits

- `scene.json`: open-filter/no-reverb → fitted settings, both clamped to [0,1].
- `index.html`: portable audition page and gesture instructions.
- `baseline.wav`, `reference.wav`, `matched.wav`: full-length mono audio.
- `audition-baseline-reference-match.wav`: the three versions in order, with
  0.5-second gaps and common attenuation if needed to leave peak headroom.
- `report.json`: fitted parameters, gain used for comparison, normalized error,
  search count/time, full-recording and remaining-recording validation.
- `scripted-morph.wav`: first quarter original, middle half morphing, final
  quarter fitted, rendered through SceneMorph and the real engine event API.
- `scripted-morph-controls.jsonl`: the same explicitly scripted trajectory for
  engine replay or `tools.virtual_guitar --controls`. Not a live gesture take.

The fit uses a coarse grid followed by bounded Powell optimization, defaulting to
64 engine renders of the first 4 seconds. `--evaluations 24..256` and
`--seconds 0.5..8` trade computation for search coverage. Computation stays out of
the live audio callback. This is bounded optimization, not a guaranteed global
optimum. The remaining recording, when at least half a second and non-silent,
provides a separate check with DSP state retained from the start.

Error is squared waveform mismatch normalized by reference energy after fitting
a positive recording gain (0.25–4×). That gain is **comparison only**: exported
audio and gestures retain engine levels. Error labels (<0.05 close, <0.25
approximate, otherwise poor) are heuristics, not confidence or perceptual scores.
Different knobs can be indistinguishable on a source with little high-frequency
energy. Always audition the result; the controls need not match the original
knobs. Poor fits still export diagnostics/audio and a best-effort scene, clearly
labeled. The tool refuses to overwrite an existing result folder.

No raw recordings are committed or uploaded. Your output folder contains copies
of reference audio; treat it like the source recordings when sharing.
