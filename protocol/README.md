# Control envelope v1

All input adapters emit the same JSON object, independently of transport. No audio samples travel in these events. timestamp_ms is a Unix timestamp; receivers check age against their clock and must account for clock skew on remote devices. seq increases within a source session; a source reconnect resets session state explicitly. Schema validity does not prove freshness/order, delivery, or safety.

parameter/set carries a normalized value [0,1]; confidence is [0,1]. The audio owner maps it into safe DSP units and smooths it. loop/toggle and bypass/toggle are debounced actions without value/confidence. Retries must not toggle twice: deduplicate action events by source/session/seq, with session tracking in the adapter connection. Bypass remains locally accessible even if all control senders fail.

The contract is proposed and versioned; transport and mapping implementation are still unbuilt. Agree on updates on issue #1 before dependent work. Example events are fixtures, not live hardware readings.
