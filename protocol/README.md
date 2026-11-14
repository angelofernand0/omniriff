# Control envelope v1

All input adapters emit the same JSON object, independently of transport. No audio samples travel in these events. timestamp_ms is a Unix timestamp; receivers check age against their clock and must account for clock skew on remote devices. seq increases within a source session; a source reconnect resets session state explicitly. Schema validity does not prove freshness/order, delivery, or safety.

parameter/set carries a normalized value [0,1]; confidence is [0,1]. The audio owner maps it into safe DSP units and smooths it. loop/toggle and bypass/toggle are debounced actions without value/confidence. Retries must not toggle twice: deduplicate action events by source/session/seq, with session tracking in the adapter connection. Bypass remains locally accessible even if all control senders fail.

The contract is versioned. Agree on updates on issue #1 before dependent work. Example events are fixtures, not live hardware readings.

## Transports v1 (set by the lead on 2026-11-13)

Changes to these go through issue #1. Ports can be overridden in config, but these are the defaults everyone builds against.

| Path | Transport | Format |
|---|---|---|
| vision, dashboard, sim → engine | UDP `127.0.0.1:47800` | one control envelope JSON per datagram |
| Arduino → engine | USB serial, 115200 baud | one compact JSON line per event, `\n`-terminated (see below) |
| engine → dashboard | WebSocket `ws://127.0.0.1:47801` | state JSON at about 20 Hz, defined in `protocol/state.schema.json` (owned by Angelo's Codex; first PR) |
| engine → audio | in-process | latest-value mailbox / bounded queue; never blocks the audio callback |

**Arduino lines.** The Arduino has no wall clock, so it sends `{"seq":N,"type":"action","control":"loop"}` or `"bypass"`. The engine's serial adapter wraps each line into a full v1 envelope, adding `version`, `source: "arduino"` and the host `timestamp_ms`. A board reset starts a new session, with `seq` restarting at 0, which the adapter must handle.

**Senders** must validate against `control.schema.json` before sending. **The engine** drops invalid, stale (older than 250 ms by default) and duplicate events, and counts the drops in its state.
