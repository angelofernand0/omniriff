"""Deterministic target/hold/release exercise; never sends rig commands."""
import math


class Session:
    def __init__(self, *, targets=(.25, .75, .5), tolerance=.05, hold=1., release=.5, timeout=20.):
        if not targets or len(targets)>9 or any(not math.isfinite(v) or not 0<=v<=1 for v in targets):
            raise ValueError('choose 1..9 target values in [0,1]')
        if not 0<tolerance<=.2 or not .1<=hold<=10 or not .1<=release<=5 or not hold+release<timeout<=120:
            raise ValueError('invalid exercise timing or tolerance')
        self.targets = tuple(targets)
        self.tolerance, self.hold, self.release, self.timeout = tolerance, hold, release, timeout
        self.index = 0
        self.phase = 'reach'
        self.started = self.trial_started = self.since = self.previous = None
        self.results = []
        self.tracking_breaks = 0
        self.was_usable = False
        self.trace = []
        self.next_sample = 0.
        self.cue = 'Waiting for fresh engine and hand feeds'
        self.value = None
        self.progress = 0.
        self.usable = False

    @property
    def done(self):
        return self.index == len(self.targets)

    def update(self, now, *, value=None, hand_present=False, engaged=False, confidence=0., fresh=False, control='filter'):
        if not math.isfinite(now) or (self.previous is not None and now<self.previous):
            raise ValueError('time must be finite and monotonic')
        self.previous = now
        if self.started is None:
            self.started = self.trial_started = now
        if self.done:
            return self.snapshot()
        valid_value = type(value) in (float,int) and math.isfinite(value) and 0<=value<=1
        self.value = value if valid_value else None
        usable = fresh and hand_present and confidence>=.6 and valid_value and control=='filter'
        self.usable = bool(usable)
        if self.was_usable and not usable:
            self.tracking_breaks += 1
        self.was_usable = bool(usable)
        target = self.targets[self.index]
        in_range = usable and abs(value-target)<=self.tolerance
        if now>=self.next_sample:
            if len(self.trace)<12000:
                self.trace.append(dict(seconds=round(now-self.started,3), target=target, value=self.value,
                                       engaged=bool(engaged), usable=bool(usable), phase=self.phase))
            self.next_sample = now+.1
        if now-self.trial_started>=self.timeout:
            self._finish(now, False, 'Target/hold/release not completed before deadline')
        elif not usable:
            self.since = None
            self.progress = 0.
            self.phase = 'reach'
            self.cue = ('Waiting for fresh engine and hand feeds' if not fresh else
                        'Use single-filter slider mode' if control!='filter' else
                        'Show the control hand in front lighting')
        elif self.phase in ('reach','hold'):
            if in_range and engaged:
                if self.since is None:
                    self.since = now
                self.phase = 'hold'
                self.progress = min(1.,(now-self.since)/self.hold)
                self.cue = 'Hold the pinch steady'
                if self.progress>=1:
                    self.phase = 'release'
                    self.since = None
                    self.progress = 0.
                    self.cue = 'Open your hand; keep the sound here'
            else:
                self.since = None
                self.phase = 'reach'
                self.progress = 0.
                self.cue = 'Open hand, pinch, then drag to the target'
        else:  # Release needs a visible, confident open hand, not tracking loss.
            if not in_range:
                self.phase = 'reach'
                self.since = None
                self.progress = 0.
                self.cue = 'Value moved; reach the target again'
            elif not engaged:
                if self.since is None:
                    self.since = now
                self.progress = min(1.,(now-self.since)/self.release)
                self.cue = 'Release holds the value'
                if self.progress>=1:
                    self._finish(now, True, 'Reached, held while engaged, then held on release')
            else:
                self.since = None
                self.progress = 0.
                self.cue = 'Open your hand to release'
        return self.snapshot()

    def _finish(self, now, passed, reason):
        self.results.append(dict(target=self.targets[self.index], passed=passed,
                                 seconds=round(now-self.trial_started,3), reason=reason))
        self.index += 1
        self.trial_started = now
        self.since = None
        self.progress = 0.
        self.phase = 'done' if self.done else 'reach'
        self.cue = 'Soundcheck complete' if self.done else 'Next target: open hand, pinch and drag'

    def snapshot(self):
        return dict(phase=self.phase, cue=self.cue, target=None if self.done else self.targets[self.index],
                    value=self.value, progress=self.progress, usable=self.usable,
                    step=min(self.index+1,len(self.targets)), total=len(self.targets),
                    results=list(self.results), tracking_breaks=self.tracking_breaks,
                    seconds=round(self.previous-self.started,2) if self.started is not None else 0.)

    def report(self):
        return dict(version=1, label='OBSERVED CONTROL SOUNDCHECK', **self.snapshot(),
                    complete=self.done, targets=self.targets, tolerance=self.tolerance,
                    hold_seconds=self.hold, release_seconds=self.release, trace=list(self.trace),
                    limits='Observes local engine/hand messages, not camera accuracy, audible output, guitar technique or causality. Manual controls can also move the filter. Synthetic feeds must be labeled by the operator.')
