# audio/ — OmniRiff real-time engine

Owner: Angelo's Claude. The signal chain is guitar → Scarlett Solo → engine → headphones/amp. Controls arrive as v1 control envelopes; no other module touches samples.

## Signal chain

```
input ch → gain → (+ loop playback) → low-pass sweep → bypass crossfade → limiter → all output channels
              └→ loop recorder (dry, post-gain)
```

- **Low-pass sweep.** `filter` in [0,1] sets the cutoff exponentially from 120 Hz (0) to 18 kHz (1). The default is 1, fully open, so nothing changes until a control moves it. It's smoothed (40 ms) and updated every 32 samples.
- **Loop.** The `loop` action steps idle → recording → playing → idle (cleared). It holds up to 30 s, with 5 ms fades at the seam. The loop records the dry signal and plays back through the filter, so a gesture shapes both the loop and live playing.
- **Bypass.** The `bypass` action toggles a 10 ms crossfade to the dry signal. The loop keeps playing.
- **Limiter.** A hard ceiling at −1 dBFS. Clipped samples are counted in the snapshot.
- **Reverb.** `reverb` is accepted, smoothed and reported, but there's no reverb DSP yet (`snapshot()["reverb"]["dsp"] == False`).

## Run it

```bash
python -m pip install -r audio/requirements.txt
python -m audio --list-devices
python -m audio --make-test-wav test.wav                 # synthetic chord, not a recording
python -m audio --input-wav test.wav --output-wav out.wav --sweep 4 --loop-at 0.5,2.5
python -m audio --input-wav test.wav --play --sweep 4    # through the default speakers
```

### Live on the Windows 11 laptop + Scarlett Solo (3rd gen)

1. Install Focusrite's driver. Plug the guitar into the Solo's **instrument jack (input 2)** with **INST** on. Turn **Direct Monitor off**, or you'll hear the dry guitar on top of the processed one.
2. Find the device: `python -m audio --list-devices`.
3. Start with WASAPI:

   ```bash
   python -m audio --in Focusrite --out Focusrite --hostapi WASAPI --input-channel 2 --status-every 2
   ```

   Add `--exclusive` for WASAPI exclusive mode, which usually gives lower latency. Try `--blocksize 64` or `256` if you hear dropouts. The `xruns` counter shows whether the buffer is too small.
4. Keyboard controls while running: `b` bypass, `l` loop, `f 0.3` filter, `s` full status, `q` quit. This manual control works with every other module down.

ASIO: the standard `sounddevice` wheel's PortAudio may not expose ASIO devices. Check `--list-devices` for an ASIO entry, and follow the sounddevice docs if you need the ASIO-enabled build. Not yet verified on the team laptop.

**Not yet verified:** this hasn't been run on the Windows laptop or the Solo. Round-trip latency is **unmeasured**. `stream.latency` (printed on exit) is PortAudio's reported buffer latency, not a measured guitar-to-ear time.

## Interface for engine/

```python
from audio import Engine, EngineConfig
engine = Engine(EngineConfig(samplerate=48000))
engine.submit(event_dict) -> bool   # v1 envelope; never blocks; call from any non-audio thread
engine.snapshot() -> dict           # best-effort state, any thread
engine.process(mono_in, out_frames_by_channels)   # audio callback only
engine.note_xrun()                  # call from the stream callback on under/overflow
```

`submit` accepts `parameter` (`filter`, `reverb`) with `value` and `confidence` in [0,1], and `action` (`loop`, `bypass`) with neither. It rejects anything malformed. It ignores `confidence < min_confidence` (default 0.6) and counts those separately. Freshness, ordering and dedupe are engine/'s job, per protocol/README.md.

Snapshot keys (stable; the source for `protocol/state.schema.json`):

| key | type |
|---|---|
| `samplerate` | int |
| `bypass` | bool |
| `loop` | `{state: "idle"\|"recording"\|"playing", seconds, max_seconds}` |
| `filter` | `{target, value, cutoff_hz}` (target/value in [0,1]) |
| `reverb` | `{target, value, dsp: bool}` |
| `input_peak_dbfs`, `output_peak_dbfs` | float, decaying peak meter |
| `xruns`, `clipped_samples`, `blocks` | int counters |
| `events` | `{accepted, rejected, low_confidence}` |

## Real-time rules followed

The callback does no I/O, logging, locks or blocking calls. Buffers are preallocated and numpy writes in place. The exception is `scipy.signal.lfilter`, which returns a small array for each 32-sample sub-block, and a one-time ramp allocation when a loop recording ends. Measured on an Apple M1 Pro (Python 3.14): a 128-frame block takes about 0.03 ms mean and 0.14 ms max, against a 2.67 ms budget. Re-check on the Windows laptop.
