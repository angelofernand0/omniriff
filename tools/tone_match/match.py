"""Fit the public audio.Engine; no DSP or model training is duplicated here."""
from dataclasses import dataclass
import math
import time
import numpy as np
from scipy.optimize import minimize
from audio import Engine, EngineConfig
from audio.offline import render


@dataclass
class FitResult:
    filter: float
    reverb: float
    residual: float
    baseline_residual: float
    reference_gain: float
    evaluations: int
    elapsed_seconds: float
    assessment: str

    def scene(self, name='Matched tone'):
        return dict(name=name, **{'from': {'filter': 1.0, 'reverb': 0.0},
                                 'to': {'filter': self.filter, 'reverb': self.reverb}})


def effect(mono, samplerate, filter_value, reverb_value):
    """Render a settled effect state through the real engine, retaining its limiter."""
    engine = Engine(EngineConfig(samplerate=samplerate))
    engine.set_filter(float(filter_value))
    engine.set_reverb(float(reverb_value))
    render(engine, np.zeros(int(samplerate * .4), dtype=np.float32))
    return render(engine, mono)[:, 0]


def validate_pair(dry, reference, samplerate):
    if not isinstance(samplerate, int) or not 8000 <= samplerate <= 96000:
        raise ValueError('sample rate must be 8000..96000 Hz')
    for name, value in (('dry', dry), ('reference', reference)):
        if value.ndim != 1 or len(value) < samplerate // 2:
            raise ValueError(f'{name} must contain at least 0.5 seconds of mono audio')
        if len(value) > samplerate * 30:
            raise ValueError('inputs may contain at most 30 seconds')
        if not np.isfinite(value).all():
            raise ValueError(f'{name} contains nonfinite samples')
        if np.max(np.abs(value)) > 1:
            raise ValueError(f'{name} must have normalized samples in [-1,1]')
        if float(np.sqrt(np.mean(value.astype(np.float64) ** 2))) < 1e-5:
            raise ValueError(f'{name} is silent or too quiet for fitting')
    if len(dry) != len(reference):
        raise ValueError('paired recordings must have equal lengths and sample alignment')


def residual(rendered, reference):
    """Least-squares positive recording gain, bounded to +/-12 dB approximately."""
    x, y = rendered.astype(np.float64), reference.astype(np.float64)
    gain = float(np.clip(np.dot(x, y) / max(float(np.dot(x, x)), 1e-20), .25, 4))
    error = y - gain * x
    return float(np.dot(error, error) / max(float(np.dot(y, y)), 1e-20)), gain


def fit(dry, reference, samplerate, *, evaluations=64, seconds=4, progress=None):
    validate_pair(dry, reference, samplerate)
    if not isinstance(evaluations, int) or not 24 <= evaluations <= 256:
        raise ValueError('evaluations must be an integer in [24,256]')
    if not math.isfinite(seconds) or not .5 <= seconds <= 8:
        raise ValueError('analysis seconds must be in [0.5,8]')
    n = min(len(dry), int(seconds * samplerate))
    dry, reference = dry[:n], reference[:n]
    validate_pair(dry, reference, samplerate)
    started = time.monotonic()
    cache = {}
    best = [float('inf'), 1., 0., 1.]

    def objective(params):
        key = tuple(round(float(np.clip(v, 0, 1)), 7) for v in params)
        if key in cache:
            return cache[key][0]
        if len(cache) >= evaluations:
            return best[0] + 1  # No additional DSP evaluations beyond the budget.
        loss, gain = residual(effect(dry, samplerate, *key), reference)
        cache[key] = (loss, gain)
        if loss < best[0]:
            best[:] = [loss, *key, gain]
        if progress:
            progress(len(cache), best[0])
        return loss

    baseline = objective((1, 0))
    for f in np.linspace(0, 1, 6):
        for r in (0., .5, 1.):
            objective((f, r))
    minimize(objective, best[1:3], method='Powell', bounds=((0, 1), (0, 1)),
             options={'maxfev': evaluations - len(cache), 'xtol': .0005, 'ftol': 1e-6})
    loss, f, r, gain = best
    assessment = 'close paired-signal fit' if loss < .05 else 'approximate fit' if loss < .25 else 'poor fit: reference is not explained by these effects'
    return FitResult(f, r, loss, baseline, gain, len(cache), time.monotonic() - started, assessment)
