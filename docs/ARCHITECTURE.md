# OmniRiff build plan

## Core claim

A guitarist can keep playing while switching a loop/effect with a physical control and shaping an audible effect through a deliberate gesture. A recoverable, low-latency instrument is the product. More devices are stretch scope, not proof of quality.

## Proposed modules (unassigned)

- audio/: laptop input/output, effects, loop state, bypass, levels, underrun counters.
- vision/: webcam hand landmarks, confidence, calibrated mapping, smoothing outside audio callback.
- firmware/arduino/: debounced physical control → serial control event.
- firmware/sensecap/: optional display/preset controls; no mandatory environmental sensing.
- dashboard/: optional UI reading engine state, not processing audio.
- protocol/: versioned shared messages; change with team agreement.

The Focusrite connects to the audio laptop over USB. Keep audio on that host first; do not route raw live audio through Wi-Fi, SenseCAP or Pi. Camera/serial processes send control data only. Transport decision is pending: newline-delimited JSON on serial for Arduino; localhost UDP/WebSocket adapter for vision/UI as selected by implementers. The schema describes the message envelope, not a running server.

## MVP gates

1. Confirm Focusrite model/generation, audio-host OS, guitar cable, headphones/monitor output, device borrowing, and exact SenseCAP/Pi/Grove parts.
2. Get clean guitar pass-through, explicit device selection, gain control and manual bypass. Measure actual input-to-output timing and xruns; buffer size/sample rate alone are not measured round-trip latency. Avoid monitoring both direct and processed audio at once unless deliberate.
3. Add one effect (e.g. low-pass sweep) and one debounced physical bypass/loop control. One reliable loop mode only after pass-through works.
4. Add one calibrated gesture with confidence gate, deadband and smooth control. A guitar-playing hand must not modulate accidentally. Use clutch/gesture activation rather than constant mapping if necessary.
5. Add optional SenseCAP preset/status screen. Pi inference only if it can run the model at a usable control rate. A laptop camera fallback keeps the demo viable.
6. Drop environmental sensors, elaborate reverb, multitrack looping, custom model training and device choreography until the core passes a sustained play test.

## Implementation choices to verify

Use a streaming audio API/host and preallocated DSP state. librosa is primarily offline analysis; do not put it in the real-time callback. Python sounddevice/PortAudio with a DSP library is a prototype candidate; native DSP/plugin hosting may be preferable if timing fails. Choose after testing on the actual OS/driver. Use the exact official docs for installed versions before implementation.

## Proposed acceptance checks

- Sustained playing without underruns, runaway gain, hangs or accumulating control backlog.
- Effect change is audible and bounded; loop start/stop works repeatedly.
- Disconnect camera/serial/dashboard and retain playable audio/manual bypass.
- No hand, low-confidence hand or stale message cannot produce an uncontrolled sweep.
- Record actual latency, control response and failure cases; do not claim a target is a result.

## Two-minute demo

15s musician/problem; 25s live dry guitar; 25s physical loop/toggle; 30s deliberate gesture sweep; 15s dashboard/status if ready; 10s explain reliability/model and one limitation. Prepare a recording, but clearly label playback. No guaranteed podium prediction is supportable.
