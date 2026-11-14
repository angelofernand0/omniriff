"""Expressive Gesture Looper and Automation Engine.

Enables guitarists to capture and loop expressive multi-parameter gesture curves
(filter sweeps, reverb swells, scene morphs) over rhythmic bars, freeing both hands
to play the instrument while continuous physical modulation repeats seamlessly.
"""
from dataclasses import dataclass, field
from enum import Enum
import json
import math
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple


class LoopState(str, Enum):
    IDLE = 'idle'
    RECORDING = 'recording'
    PLAYING = 'playing'
    PUNCHED_IN = 'punched_in'


@dataclass
class GestureKeyframe:
    time_offset_s: float
    parameters: Dict[str, float]


@dataclass
class LoopMetadata:
    version: int = 1
    duration_s: float = 0.0
    bpm: Optional[float] = None
    bars: Optional[int] = None
    sample_count: int = 0
    parameters: List[str] = field(default_factory=list)


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge1 <= edge0:
        return 0.0
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


class GestureLooper:
    """Records, crossfades, loops, and allows live punch-in over gesture automation curves."""

    def __init__(
        self,
        duration_s: float = 4.0,
        bpm: Optional[float] = None,
        bars: Optional[int] = None,
        crossfade_s: float = 0.10,
        target_rate_hz: float = 10.0,
    ):
        if duration_s <= 0.0 or not math.isfinite(duration_s):
            raise ValueError(f"duration_s must be positive and finite, got {duration_s}")

        if bpm is not None and bars is not None:
            if bpm <= 0.0 or not math.isfinite(bpm):
                raise ValueError(f"bpm must be positive and finite, got {bpm}")
            if bars <= 0:
                raise ValueError(f"bars must be positive integer, got {bars}")
            duration_s = (60.0 / bpm) * 4.0 * bars

        self.duration_s: float = duration_s
        self.bpm: Optional[float] = bpm
        self.bars: Optional[int] = bars
        self.crossfade_s: float = min(crossfade_s, duration_s * 0.25)
        self.target_rate_hz: float = target_rate_hz

        self.state: LoopState = LoopState.IDLE
        self._record_start_t: Optional[float] = None
        self._playback_start_t: Optional[float] = None
        self._raw_samples: List[Tuple[float, Dict[str, float]]] = []
        self._keyframes: List[GestureKeyframe] = []
        self._parameter_keys: List[str] = []

        # Punch-in state tracking
        self._punch_in_t: Optional[float] = None
        self._punch_offsets: Dict[str, float] = {}
        self._last_live_params: Dict[str, float] = {}

    @property
    def is_recording(self) -> bool:
        return self.state == LoopState.RECORDING

    @property
    def is_playing(self) -> bool:
        return self.state in (LoopState.PLAYING, LoopState.PUNCHED_IN)

    def start_recording(self, t0: Optional[float] = None) -> None:
        """Starts recording incoming gesture events."""
        now = time.monotonic() if t0 is None else float(t0)
        self.state = LoopState.RECORDING
        self._record_start_t = now
        self._raw_samples = []
        self._keyframes = []
        self._parameter_keys = []

    def record_frame(self, t: float, parameters: Dict[str, float]) -> bool:
        """Records a single gesture frame. Returns True if duration was reached and loop auto-closed."""
        if self.state != LoopState.RECORDING or self._record_start_t is None:
            return False

        t = float(t)
        if not math.isfinite(t):
            return False

        # Validate parameters are finite and bounded [0.0, 1.0]
        cleaned_params = {}
        for k, v in parameters.items():
            if math.isfinite(v):
                cleaned_params[str(k)] = max(0.0, min(1.0, float(v)))

        if not cleaned_params:
            return False

        if not self._parameter_keys:
            self._parameter_keys = sorted(cleaned_params.keys())

        elapsed = t - self._record_start_t
        if elapsed < 0.0:
            return False

        self._raw_samples.append((elapsed, cleaned_params))

        if elapsed >= self.duration_s:
            self.finish_recording(t_end=t)
            return True
        return False

    def finish_recording(self, t_end: Optional[float] = None) -> bool:
        """Finalizes recorded buffer, creates cyclic crossfade, and enters PLAYING mode."""
        if self.state != LoopState.RECORDING or not self._raw_samples:
            self.state = LoopState.IDLE
            return False

        if t_end is not None and self._record_start_t is not None:
            actual_duration = t_end - self._record_start_t
            if actual_duration > 0.1:
                self.duration_s = actual_duration
                self.crossfade_s = min(self.crossfade_s, self.duration_s * 0.25)

        # Sort raw samples by time offset
        self._raw_samples.sort(key=lambda s: s[0])

        # Normalize keyframes into [0.0, duration_s]
        self._keyframes = []
        for offset_s, params in self._raw_samples:
            norm_t = max(0.0, min(self.duration_s, offset_s))
            self._keyframes.append(GestureKeyframe(time_offset_s=norm_t, parameters=params))

        if not self._keyframes:
            self.state = LoopState.IDLE
            return False

        # Apply cyclic crossfade at boundaries to prevent discontinuities
        self._apply_cyclic_crossfade()

        self.state = LoopState.PLAYING
        self._playback_start_t = time.monotonic() if t_end is None else float(t_end)
        return True

    def _apply_cyclic_crossfade(self) -> None:
        """Smooths parameter values near the loop seam so start and end match perfectly."""
        if len(self._keyframes) < 2 or self.crossfade_s <= 0.0:
            return

        start_params = self._keyframes[0].parameters
        fade_dur = self.crossfade_s
        seam_t = self.duration_s - fade_dur

        for kf in self._keyframes:
            if kf.time_offset_s >= seam_t:
                progress = (kf.time_offset_s - seam_t) / fade_dur
                factor = _smoothstep(0.0, 1.0, progress)
                # Blend end toward start
                blended = {}
                for param, val in kf.parameters.items():
                    target = start_params.get(param, val)
                    blended[param] = val * (1.0 - factor) + target * factor
                kf.parameters = blended

    def sample(self, t: float) -> Optional[Dict[str, float]]:
        """Samples the loop at arbitrary monotonic timestamp t."""
        if self.state not in (LoopState.PLAYING, LoopState.PUNCHED_IN):
            return None

        if not self._keyframes or self._playback_start_t is None:
            return None

        cycle_offset = (float(t) - self._playback_start_t) % self.duration_s

        # Interpolate keyframes at cycle_offset
        base_params = self._interpolate_keyframes(cycle_offset)

        if self.state == LoopState.PUNCHED_IN and self._last_live_params:
            # Player is overriding live
            result = {}
            for k in self._parameter_keys:
                live_v = self._last_live_params.get(k, base_params.get(k, 0.0))
                result[k] = max(0.0, min(1.0, live_v))
            return result

        return base_params

    def _interpolate_keyframes(self, cycle_offset: float) -> Dict[str, float]:
        """Performs linear interpolation between neighboring keyframes."""
        if len(self._keyframes) == 1:
            return dict(self._keyframes[0].parameters)

        # Handle wrap-around between last and first keyframe
        if cycle_offset <= self._keyframes[0].time_offset_s:
            return dict(self._keyframes[0].parameters)
        if cycle_offset >= self._keyframes[-1].time_offset_s:
            return dict(self._keyframes[-1].parameters)

        # Binary or linear scan
        idx = 0
        while idx < len(self._keyframes) - 1 and self._keyframes[idx + 1].time_offset_s < cycle_offset:
            idx += 1

        k0 = self._keyframes[idx]
        k1 = self._keyframes[idx + 1]

        dt = k1.time_offset_s - k0.time_offset_s
        if dt <= 1e-6:
            return dict(k0.parameters)

        alpha = (cycle_offset - k0.time_offset_s) / dt
        blended = {}
        for k in self._parameter_keys:
            v0 = k0.parameters.get(k, 0.0)
            v1 = k1.parameters.get(k, v0)
            blended[k] = max(0.0, min(1.0, v0 + alpha * (v1 - v0)))
        return blended

    def punch_in(self, t: float, live_params: Dict[str, float]) -> None:
        """Punches into live control over the loop with smooth relative pickup."""
        if self.state != LoopState.PLAYING:
            return

        self.state = LoopState.PUNCHED_IN
        self._punch_in_t = float(t)
        base = self.sample(t) or {}

        self._last_live_params = {}
        for k, v in live_params.items():
            if math.isfinite(v):
                clean_v = max(0.0, min(1.0, float(v)))
                self._last_live_params[k] = clean_v

    def update_punch_in(self, live_params: Dict[str, float]) -> None:
        """Updates live parameter values while punched in."""
        if self.state != LoopState.PUNCHED_IN:
            return
        for k, v in live_params.items():
            if math.isfinite(v):
                self._last_live_params[k] = max(0.0, min(1.0, float(v)))

    def punch_out(self, t: Optional[float] = None) -> None:
        """Releases punch-in and returns to loop playback."""
        if self.state == LoopState.PUNCHED_IN:
            self.state = LoopState.PLAYING
            self._last_live_params = {}
            self._punch_in_t = None

    def export_take_jsonl(self, path: Path, repetitions: int = 1, source: str = 'vision') -> int:
        """Exports loop repetitions into engine replay compatible JSONL format."""
        if not self._keyframes or repetitions < 1:
            raise ValueError("No recorded keyframes or repetitions < 1")

        path = Path(path)
        if path.exists():
            raise FileExistsError(f"Target take file already exists: {path}")

        path.parent.mkdir(parents=True, exist_ok=True)
        events_written = 0
        seq = 0

        interval_s = 1.0 / max(1.0, self.target_rate_hz)

        with open(path, 'w', encoding='utf-8') as f:
            for rep in range(repetitions):
                base_time = rep * self.duration_s
                t_cursor = 0.0

                while t_cursor < self.duration_s:
                    params = self._interpolate_keyframes(t_cursor)
                    event_time = base_time + t_cursor
                    timestamp_ms = int(round(event_time * 1000))

                    # Emit each parameter as a schema-validated v1 parameter event
                    for param_name in sorted(params.keys()):
                        if param_name not in ('filter', 'reverb'):
                            continue
                        param_val = params[param_name]
                        envelope = {
                            "version": 1,
                            "source": source,
                            "seq": seq,
                            "timestamp_ms": timestamp_ms,
                            "type": "parameter",
                            "control": param_name,
                            "value": float(max(0.0, min(1.0, round(param_val, 4)))),
                            "confidence": 1.0
                        }
                        f.write(json.dumps(envelope) + '\n')
                        seq += 1
                        events_written += 1

                    t_cursor += interval_s

        return events_written
