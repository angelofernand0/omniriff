"""Continuous scene morphing using the existing v1 parameter envelopes."""
import math

SCENES = {
    'bloom': {'name': 'Clear to Cosmos', 'from': {'filter': 1.0, 'reverb': 0.0},
              'to': {'filter': 0.40, 'reverb': 0.75}},
    'rise': {'name': 'Underwater to Spotlight', 'from': {'filter': 0.12, 'reverb': 0.55},
             'to': {'filter': 1.0, 'reverb': 0.08}},
}


class SceneMorph:
    def __init__(self, scene):
        if not isinstance(scene, dict) or set(scene) != {'name', 'from', 'to'}:
            raise ValueError('scene requires name, from and to')
        if not isinstance(scene['name'], str) or not scene['name'].strip():
            raise ValueError('scene name must be nonempty')
        for end in ('from', 'to'):
            values = scene[end]
            if not isinstance(values, dict) or set(values) != {'filter', 'reverb'}:
                raise ValueError('each endpoint requires filter and reverb')
            for value in values.values():
                if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError('scene values must be finite numbers in [0,1]')
        self.name = scene['name']
        self.start, self.end = dict(scene['from']), dict(scene['to'])
        self.seq = 0

    def values(self, amount):
        if not math.isfinite(amount) or not 0 <= amount <= 1:
            raise ValueError('morph amount must be in [0,1]')
        # Smoothstep gives gentle starts and finishes, with exact endpoints.
        t = amount * amount * (3 - 2 * amount)
        return {key: self.start[key] + t * (self.end[key] - self.start[key]) for key in self.start}

    def events(self, gesture):
        events = []
        for control, value in self.values(gesture['value']).items():
            event = dict(gesture, control=control, value=value, seq=self.seq)
            self.seq += 1
            events.append(event)
        return events
