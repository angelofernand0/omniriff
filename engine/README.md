# Host runtime

Owner: Angelo's Codex. State frames follow protocol/state.schema.json, retaining audio.snapshot fields at the top level. UDP control: 127.0.0.1:47800. WebSocket state: ws://127.0.0.1:47801 at 20 Hz. The WS also receives v1 source=dashboard events, so browsers need no UDP bridge. Serve the dashboard from localhost (file:// Origin null is not accepted). CLI WS clients may omit Origin.

```bash
python -m pip install -r engine/requirements.txt
python -m engine --headless --no-keyboard --duration 5
python -m engine --in Focusrite --out Focusrite --hostapi WASAPI --input-channel 2 --serial-port COM3
```

Headless processes silence through the actual audio.Engine: it tests control integration, not a sound card or latency. The hardware run remains pending on Windows/Solo. Keyboard controls are audio's b/l/f/r/s/q fallback. No serial port means disabled; missing serial devices retry without stopping audio. Adapters bind only loopback, have independent retry loops, and stop independently of the audio thread. UDP and WS ports may be overridden (0 requests an ephemeral port in tests). A slow WS client cannot block other clients or audio. Serial bytes are framed with a bounded buffer and processed outside the audio thread.

The gate rejects invalid schemas, nonfinite JSON, >4096-byte messages, events older than 250 ms or >250 ms in the future, non-increasing sequence numbers and backward timestamps, and confidence below audio.config.min_confidence. Timestamp and sequence checks occur before submission. Reject reasons and adapter health appear in state.

v1 has no sender session ID: one active producer per source is supported. A UDP producer may restart with a strictly lower sequence after at least 1 second without an accepted/consumed event and with a newer timestamp (seq 0 need not survive delivery); equal sequence identities remain duplicates even after idle; actions must not retry with new timestamps. Two dashboards at once must coordinate a single source sequence; use one control dashboard for the MVP. Clocks must agree; this release is loopback-only. Compact serial seq 0 after prior progress is interpreted as board reset; repeated seq 0 is a duplicate. Reopening serial starts a new host session. This inference cannot disambiguate arbitrary replay of serial data; explicit wire session IDs would require a v2 contract. Equal sequence identities intentionally stay blocked across idle, so a sender that had emitted only seq 0 before a reset must advance to seq 1; v1 cannot distinguish that first restart action from a duplicate.

The state snapshot is best effort across audio/control threads. Missing source entries mean no valid envelope has arrived. An adapter in error/retrying records the last failure (not a current audio failure). Old errors remain for diagnosis after recovery. Stopping a source leaves its last parameter value in place; it does not create a sweep or mute audio. Manual bypass stays available.

Tests: `python -m unittest discover -s engine/tests -v` after installing requirements. tests/test_engine.py bridges this suite into the repository CI discovery. No callback or DSP changes are included here.

## Windows 11 quickstart — Scarlett Solo (3rd gen)

**Windows verification pending.** These commands are prepared from the Python/PortAudio and pySerial interfaces and this repo's CLI; they have not been run on Angelo's Windows laptop or Scarlett Solo. COM3 below is an example, not a detected port. No measured guitar-to-output latency is claimed.

Run PowerShell in the repository root. Install Python 3.12 with the Windows launcher if `py -3.12 --version` fails. Install the official Scarlett Solo 3rd-gen Windows driver from [Focusrite Downloads](https://downloads.focusrite.com/focusrite/scarlett-3rd-gen/scarlett-solo-3rd-gen), then attach the interface and reboot if its installer requests it.

```powershell
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r engine/requirements.txt
```

Using the venv's Python directly avoids needing PowerShell activation or an execution-policy change. For optional development checks, install `requirements-dev.txt` and run unittest discovery with that same Python.

### Identify the actual devices

```powershell
.\.venv\Scripts\python.exe -m audio --list-devices
.\.venv\Scripts\python.exe -m serial.tools.list_ports -v
```

The first command prints sound-device indexes, names, host APIs and channel counts. Find the Focusrite input and output entries under WASAPI. The engine's `--in`/`--out` accept the shown numeric indexes or case-insensitive name substrings; indexes can change after reconnects. If the printed name does not contain Focusrite, use its actual name/index instead. `--input-channel 2` is the Solo's instrument input, not the microphone input.

For the Arduino, compare the serial list with the board disconnected and reconnected. Use the COM port that appears; confirm it in Arduino IDE's port menu or Windows Device Manager → Ports (COM & LPT). A charge-only USB cable will not create a port. Close Arduino Serial Monitor and other serial tools before the engine opens it; only one program should own that COM port.

### Live demo command

Plug the guitar into input 2, enable INST, and turn Direct Monitor off to avoid double monitoring. Connect headphones/monitor output to the Solo, start with low physical output volume, and keep the engine terminal focused for manual controls. After replacing COM3 with the detected port:

```powershell
.\.venv\Scripts\python.exe -m engine --in Focusrite --out Focusrite --hostapi WASAPI --input-channel 2 --out-channels 2 --samplerate 48000 --blocksize 128 --serial-port COM3
```

Without a pedal, omit `--serial-port COM3`; audio and the UDP/WebSocket adapters still run. Type commands followed by Enter: `b` bypass, `l` loop, `f 0.3` filter, `r 0.3` reverb, `s` audio status, `q` stop. Do not use `--no-keyboard` for the live demo: the local bypass is the independent fallback. Dashboard state is at `ws://127.0.0.1:47801`; serve the dashboard on localhost. Camera controls go to UDP 47800 on the same laptop. The dashboard and vision are separate processes, not started by this command.

If audio drops out, try `--blocksize 256` and check `xruns`. Test `--exclusive` only with WASAPI devices; it may conflict with another program using the same device. Buffer settings and reported PortAudio latency are not a real round-trip measurement. Follow `tests/acceptance/MANUAL.md` and `tools/latency/README.md` on the actual hardware.

ASIO is an optional comparison, not required for the first demo. Current pip-installed sounddevice Windows builds document setting `$env:SD_ENABLE_ASIO = "1"` **before starting Python**, then listing devices again and choosing an actual ASIO entry. This depends on the installed sounddevice/PortAudio build and is unverified here; do not assume a device is available just because the flag exists. Use `--hostapi ASIO` only when listing confirms it; omit `--exclusive` for ASIO.

### Hardware-free sanity check

```powershell
.\.venv\Scripts\python.exe -m engine --headless --no-keyboard --duration 5
```

This processes silence and starts the control servers. It cannot establish driver functionality, audibility, camera recognition, pedal wiring or live latency.

References: [sounddevice installation and ASIO](https://python-sounddevice.readthedocs.io/en/latest/installation.html), [pySerial port enumeration](https://pyserial.readthedocs.io/en/latest/tools.html#serial-tools-list-ports). All Windows/device-specific bring-up remains pending until tested at the laptop.

## Explicit control replay / backup

Replay is a labeled **control script**, not recorded guitar audio, a camera run or a pedal run. Keep playing the real guitar through the audio engine while the script drives selected controls. Existing live wire envelopes are unchanged; replay mode adds the optional `replay` state object approved by Angelo. Normal live frames have no such object.

```powershell
.\.venv\Scripts\python.exe -m engine --replay engine/demo-controls.jsonl --in Focusrite --out Focusrite --hostapi WASAPI --input-channel 2
```

`engine/demo-controls.jsonl` is a synthetic filter/reverb/loop demonstration, not a captured performance: loop records at 1 s, plays at 3 s and clears at 6 s. Play a short riff during that recording window. On any development machine, test it without sound hardware using `python -m engine --replay engine/demo-controls.jsonl --headless --no-keyboard --duration 8`. Windows/Focusrite replay still needs a live test.

A script contains one existing full v1 envelope per JSONL line. Its nondecreasing Unix `timestamp_ms` values establish offsets from the first event; playback starts at offset zero now. Scripts from vision dry-run output are suitable if they contain only those event lines. The whole file is validated before opening any device. Blank lines are ignored; invalid events, nonfinite values, backwards times, repeated/decreasing per-source sequences (trim capture resets/retries), >4096-byte lines, >10000 events or >one-hour duration are rejected. Historical timestamps/sequence/source are replaced with scheduled current timestamps, a fresh increasing sequence and source=manual **only inside replay**. Original parameter/action content still passes the same confidence/schema/audio gate. Late scheduled events are dropped by the normal stale gate rather than delivered in a burst.

The terminal announces `REPLAY CONTROL MODE`. WS state includes `replay:{label:"REPLAY",active,status,position,total}`. The label remains after completion/error/stop so the session cannot look like a live sensor run afterward. If any scheduled control is rejected (including a stale event, low confidence or audio rejection), playback stops with `status:"error"`; the log names the event and the existing `controls` counters explain the drop. `position` counts attempted events, including the rejected one. Later events are not sent: missing a loop toggle can change the meaning of the rest of the performance. `completed` means every event passed the control gate, not proof of audible output or hardware timing. A completed or failed script does not stop audio; stop with `q` / Ctrl+C. Keyboard bypass remains available; localhost dashboard manual controls remain available too. UDP input is disabled and `--serial-port` is rejected in replay mode, preventing camera/pedal duplicates from mixing into the scripted run. Restart without `--replay` to return to live sensor controls. No source/file metadata is written to an audio callback or sent to an external service.

### Serial read responsiveness

The worker waits for one byte when idle, then drains bytes already queued, up to 256 per read. It does not ask pySerial to fill a 256-byte read before processing a short footswitch line. The idle timeout remains 100 ms for shutdown/reconnect handling; this is not an added per-message delay when a byte arrives. Partial and oversized lines still pass through the bounded NDJSON decoder. The [pySerial read contract](https://pyserial.readthedocs.io/en/latest/pyserial_api.html#serial.Serial.read) documents size/timeout behavior. Unit checks verify this read policy; actual pedal-to-audio latency on Windows is unmeasured.

### Adapter startup diagnostics

A missing COM port or occupied control/state port produces a terminal warning naming the failing adapter. Identical failures are suppressed while retries continue; a new failure after recovery is reported again. State still retains error counters and the last error for diagnosis. Audio and local keyboard bypass remain independent. If a port is busy, stop the other demo/engine process or choose unused `--udp-port`/`--ws-port` values and point the senders/dashboard at those ports. Do not kill unrelated processes automatically.
