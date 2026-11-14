"""Audition the exported scene with an explicitly scripted hand trajectory."""
import numpy as np
from audio import Engine, EngineConfig
from vision.scenes import SceneMorph


def audition(dry, rate, scene):
    engine = Engine(EngineConfig(samplerate=rate))
    morph = SceneMorph(scene)
    output = np.zeros((len(dry), 2), np.float32)
    duration = len(dry) / rate
    events = []
    next_update = 0
    for start in range(0, len(dry), 128):
        seconds = start / rate
        if seconds >= next_update:
            amount = min(1., max(0., (seconds / duration - .25) * 2))
            for event in morph.events(dict(version=1, source='vision', seq=0,
                    timestamp_ms=int(seconds * 1000), type='parameter',
                    control='filter', value=amount, confidence=1.)):
                if not engine.submit(event):
                    raise RuntimeError('engine rejected scripted morph control')
                events.append(event)
            next_update = seconds + .1
        engine.process(dry[start:start+128], output[start:start+128])
    if not np.isfinite(output).all():
        raise ValueError('nonfinite scripted morph output')
    return output, events
