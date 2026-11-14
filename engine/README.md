# Host runtime

Owner: Angelo's Codex. State frames follow protocol/state.schema.json, retaining audio.snapshot fields at the top level. UDP control: 127.0.0.1:47800. WebSocket state: ws://127.0.0.1:47801 at 20 Hz. The WS also receives v1 source=dashboard events, so browsers need no UDP bridge. Serve the dashboard from localhost (file:// Origin null is not accepted). CLI WS clients may omit Origin.

```bash
python -m pip install -r engine/requirements.txt
python -m engine --headless --no-keyboard --duration 5
python -m engine --in Focusrite --out Focusrite --hostapi WASAPI --input-channel 2 --serial-port COM3
```

Headless processes silence through the actual audio.Engine: it tests control integration, not a sound card or latency. The hardware run remains pending on Windows/Solo. Keyboard controls are audio's b/l/f/r/s/q fallback. No serial port means disabled; missing serial devices retry without stopping audio. Adapters bind only loopback, have independent retry loops, and stop independently of the audio thread. UDP and WS ports may be overridden (0 requests an ephemeral port in tests). A slow WS client cannot block other clients or audio. Serial bytes are framed with a bounded buffer and processed outside the audio thread.

The gate rejects invalid schemas, nonfinite JSON, >4096-byte messages, events older than 250 ms or >250 ms in the future, non-increasing sequence numbers and backward timestamps, and confidence below audio.config.min_confidence. Timestamp and sequence checks occur before submission. Reject reasons and adapter health appear in state.

v1 has no sender session ID: one active producer per source is supported. A UDP producer may restart at seq 0 after at least 1 second without an accepted/consumed event and with a newer timestamp; actions must not retry with new timestamps. Two dashboards at once must coordinate a single source sequence; use one control dashboard for the MVP. Clocks must agree; this release is loopback-only. Compact serial seq 0 after prior progress is interpreted as board reset; repeated seq 0 is a duplicate. Reopening serial starts a new host session. This inference cannot disambiguate arbitrary replay of serial data; explicit wire session IDs would require a v2 contract.

The state snapshot is best effort across audio/control threads. Missing source entries mean no valid envelope has arrived. An adapter in error/retrying records the last failure (not a current audio failure). Old errors remain for diagnosis after recovery. Stopping a source leaves its last parameter value in place; it does not create a sweep or mute audio. Manual bypass stays available.

Tests: `python -m unittest discover -s engine/tests -v` after installing requirements. tests/test_engine.py bridges this suite into the repository CI discovery. No callback or DSP changes are included here.
