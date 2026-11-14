"""Input level analysis for setting the Scarlett Solo's gain knob.

Pure functions only; recording lives in audio/stream.py. Targets: strummed
peaks around -12 dBFS, leaving headroom for hard playing. The Solo's own gain
halo (green / amber / red) shows the same thing at the interface.
"""
from __future__ import annotations

import math

import numpy as np

SILENT_PEAK_DB = -60.0   # below this, nothing is reaching the input
LOW_PEAK_DB = -24.0      # quieter than this, turn the gain up
HOT_PEAK_DB = -6.0       # louder than this, turn the gain down
CLIP_LEVEL = 10 ** (-0.1 / 20)  # samples this close to full scale count as clipped


def _db(x: float) -> float:
    return 20.0 * math.log10(max(x, 1e-9))


def analyze_levels(samples: np.ndarray) -> dict:
    """Return peak/RMS levels in dBFS, clipping, and gain advice for a mono buffer."""
    x = np.asarray(samples, dtype=np.float64).ravel()
    if x.size == 0:
        raise ValueError("no samples to analyze")
    absx = np.abs(x)
    peak = float(absx.max())
    rms = float(np.sqrt(np.mean(x * x)))
    clipped = int(np.count_nonzero(absx >= CLIP_LEVEL))
    peak_db, rms_db = _db(peak), _db(rms)

    if peak_db < SILENT_PEAK_DB:
        advice, message = "silent", (
            "No signal. Check the cable is in input 2, INST is on, the guitar volume is up, "
            "and you picked the Focusrite device and --input-channel 2.")
    elif clipped or peak_db > HOT_PEAK_DB:
        advice, message = "turn_down", (
            f"Too hot ({clipped} clipped samples). Turn the Solo's input 2 gain down until "
            "the halo stays green/amber on your hardest strum.")
    elif peak_db < LOW_PEAK_DB:
        advice, message = "turn_up", (
            "Quiet. Turn the Solo's input 2 gain up until hard strums light the halo amber "
            "(peaks near -12 dBFS).")
    else:
        advice, message = "good", "Good level: peaks have headroom and the signal is well above the noise."

    return {
        "peak_dbfs": round(peak_db, 1),
        "rms_dbfs": round(rms_db, 1),
        "clipped_samples": clipped,
        "advice": advice,
        "message": message,
    }
