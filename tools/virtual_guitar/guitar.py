"""Deterministic physical-model guitar used by the hardware-free test rig.

This is a Karplus-Strong string model, not a sample or a claim about a specific
instrument. Six standard-tuned strings are fretted into real chord voicings and
picked a few milliseconds apart. The result is intended to be recognizably
guitar-shaped enough for effect tuning while remaining reproducible in CI.
"""
from __future__ import annotations


import numpy as np
from scipy.signal import butter, iirpeak, lfilter, sosfilt


OPEN_STRINGS = np.array([82.4069, 110.0, 146.8324, 195.9977, 246.9417, 329.6276])

# Low E through high E. -1 means the string is not played.
CHORDS = (
    ("Em", (0, 2, 2, 0, 0, 0)),
    ("Cmaj7", (-1, 3, 2, 0, 0, 0)),
    ("G", (3, 2, 0, 0, 0, 3)),
    ("Dsus2", (-1, -1, 0, 2, 3, 0)),
)


def fret_frequency(string_index: int, fret: int) -> float:
    return float(OPEN_STRINGS[string_index] * 2.0 ** (fret / 12.0))


def pluck_string(
    frequency: float,
    seconds: float,
    samplerate: int,
    rng: np.random.Generator,
    *,
    decay_seconds: float = 2.2,
    pick_position: float = 0.18,
    brightness: float = 0.72,
) -> np.ndarray:
    """Synthesize one picked string with a feedback-delay physical model."""
    frames = max(0, int(round(seconds * samplerate)))
    if not frames:
        return np.zeros(0, np.float32)
    if not (20.0 <= frequency < samplerate * 0.4):
        raise ValueError("frequency is outside the useful model range")
    if decay_seconds <= 0 or not 0.03 <= pick_position <= 0.5:
        raise ValueError("invalid decay or pick position")

    # The averaging filter contributes half a sample of phase delay.
    delay = max(2, int(round(samplerate / frequency - 0.5)))
    noise = rng.uniform(-1.0, 1.0, delay)

    # Picking at a point on the string creates a comb-shaped excitation: this
    # removes the buzzy all-harmonics noise of the textbook KS example.
    pick_delay = max(1, min(delay - 1, int(round(delay * pick_position))))
    excitation = noise - 0.72 * np.roll(noise, pick_delay)
    mellow = 0.08 + (1.0 - brightness) * 0.34
    excitation = lfilter([mellow, 1.0 - 2 * mellow, mellow], [1.0], excitation)
    excitation *= np.hanning(delay)

    drive = np.zeros(frames, np.float64)
    drive[: min(delay, frames)] = excitation[:frames]

    # A frequency-normalized loop gain gives lower and higher strings similar
    # perceived sustain. The two delay taps are the KS bridge-loss low-pass.
    loop_gain = 10.0 ** (-3.0 / (frequency * decay_seconds))
    denominator = np.zeros(delay + 2, np.float64)
    denominator[0] = 1.0
    denominator[-2:] = -0.5 * loop_gain
    string = lfilter([1.0], denominator, drive)

    # A pick does not reach full displacement instantaneously, and a tiny
    # initial pick transient makes attacks legible through reverb/filters.
    attack = min(frames, max(2, int(0.0012 * samplerate)))
    string[:attack] *= np.linspace(0.0, 1.0, attack)
    click_n = min(frames, max(2, int(0.0025 * samplerate)))
    string[:click_n] += rng.normal(0.0, 0.045, click_n) * np.exp(
        -np.arange(click_n) / max(1.0, 0.00055 * samplerate)
    )
    return string.astype(np.float32)


def _add_strum(
    output: np.ndarray,
    when: float,
    frets: tuple[int, ...],
    samplerate: int,
    rng: np.random.Generator,
    *,
    velocity: float,
    direction: str,
    sustain: float,
    upper_only: bool = False,
) -> None:
    indices = [i for i, fret in enumerate(frets) if fret >= 0 and (not upper_only or i >= 2)]
    if direction == "up":
        indices.reverse()
    spacing = rng.uniform(0.008, 0.014) if direction == "down" else rng.uniform(0.006, 0.011)
    for order, string_index in enumerate(indices):
        start = int(round((when + order * spacing) * samplerate))
        if start >= len(output):
            continue
        fret = frets[string_index]
        frequency = fret_frequency(string_index, fret)
        remaining = (len(output) - start) / samplerate
        tone = pluck_string(
            frequency,
            min(remaining, sustain),
            samplerate,
            rng,
            decay_seconds=sustain * rng.uniform(0.82, 1.08),
            pick_position=rng.uniform(0.12, 0.24),
            brightness=rng.uniform(0.62, 0.82),
        )
        # Lower strings carry more energy, but no string is sample-identical.
        string_balance = 1.08 - string_index * 0.055
        amplitude = velocity * string_balance * rng.uniform(0.90, 1.08)
        output[start:start + len(tone)] += tone * amplitude


def _pickup_and_body(signal: np.ndarray, samplerate: int) -> np.ndarray:
    """Apply clean-pickup bandwidth plus restrained body/pickup resonances."""
    if not len(signal):
        return signal
    nyquist = samplerate / 2
    high = min(7200.0, nyquist * 0.88)
    sos = butter(2, [58.0 / nyquist, high / nyquist], btype="bandpass", output="sos")
    direct = sosfilt(sos, signal.astype(np.float64))

    body = np.zeros_like(direct)
    for frequency, gain, q in ((108.0, 0.12, 3.2), (215.0, 0.08, 4.0), (410.0, 0.045, 5.0)):
        if frequency < nyquist * 0.9:
            b, a = iirpeak(frequency / nyquist, q)
            body += gain * lfilter(b, a, direct)
    output = direct + body

    # Very light clean-preamp saturation controls coincident string attacks
    # without turning the source into a distorted guitar.
    output = np.tanh(output * 1.15) / np.tanh(1.15)
    return output.astype(np.float32)


def performance(
    seconds: float,
    samplerate: int = 48000,
    *,
    bpm: float = 92.0,
    seed: int = 7,
    level: float = 0.28,
) -> np.ndarray:
    """Render a repeated Em–Cmaj7–G–Dsus2 rhythm-guitar performance."""
    frames = max(0, int(round(seconds * samplerate)))
    if not frames:
        return np.zeros(0, np.float32)
    if samplerate < 8000 or bpm <= 0 or not 0 <= level <= 1:
        raise ValueError("invalid samplerate, bpm, or level")

    rng = np.random.default_rng(seed)
    output = np.zeros(frames, np.float64)
    beat = 60.0 / bpm
    bar = beat * 2.0
    bar_index = 0
    while bar_index * bar < seconds:
        _, frets = CHORDS[bar_index % len(CHORDS)]
        start = bar_index * bar
        _add_strum(output, start, frets, samplerate, rng, velocity=0.82,
                   direction="down", sustain=2.5, upper_only=False)
        _add_strum(output, start + 0.52 * beat, frets, samplerate, rng, velocity=0.28,
                   direction="up", sustain=0.75, upper_only=True)
        _add_strum(output, start + 1.02 * beat, frets, samplerate, rng, velocity=0.55,
                   direction="down", sustain=1.25, upper_only=False)
        _add_strum(output, start + 1.55 * beat, frets, samplerate, rng, velocity=0.24,
                   direction="up", sustain=0.65, upper_only=True)
        bar_index += 1

    output = _pickup_and_body(output, samplerate)
    peak = float(np.max(np.abs(output)))
    target_peak = min(0.92, max(0.02, level * 2.0))
    if peak:
        output *= target_peak / peak
    return output.astype(np.float32)
