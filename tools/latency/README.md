# tools/latency — measure, don't guess

Owner: Angelo's Claude. Two modes.

## Engine-only (any laptop, CI)

```bash
python -m tools.latency --engine-only
```

This times `audio.Engine.process` with the filter and reverb active, at block sizes 64, 128 and 256. It reports mean, p99 and max per block, and load as a percent of the block's real-time budget. **This is CPU cost, not latency.** It shows whether the engine keeps up with the buffer.

## Loopback (Windows laptop + Scarlett Solo)

1. Turn headphones and speakers **down** and the Solo's **Direct Monitor off**.
2. Patch a cable from a Solo output (line out or the headphone jack) into **input 2**. Use INST off and low gain, since a line-level click is loud.
3. Run:

   ```bash
   python -m tools.latency --in Focusrite --out Focusrite --hostapi WASAPI --input-channel 2 --blocksize 128
   ```

   Repeat with `--exclusive`, `--blocksize 64`/`256`, or another `--hostapi` to compare.

The tool plays 20 clicks, 0.5 s apart, and finds when each comes back. It prints the median, min, max and spread in ms, the number detected, any xruns, and PortAudio's *reported* latencies, which are buffer estimates, not measurements.

The engine isn't in the loop during the test, because that would feed back. In live use it runs inside the same duplex callback, so the measured round trip is the guitar-to-output latency, plus negligible DSP delay. The Solo's analog path adds well under a millisecond.

Record results in the PR or on issue #1 as: date, host API, block size, exclusive or not, median ± spread, detected/total. Only quote numbers measured this way in the demo or on Devpost.
