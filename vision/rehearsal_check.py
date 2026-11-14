"""Human-confirmed camera rehearsal with measured timing and an explicit scope."""
import math
import os
import shlex
from .metrics import FrameMetrics


class RehearsalCheck:
    def __init__(self, *, strum_hand, source, transmission, seconds=30., command=None):
        if strum_hand not in ('Left','Right') or source not in ('webcam','recorded-video') or transmission not in ('udp','dry-run'):
            raise ValueError('invalid rehearsal source/hand/transmission')
        if not math.isfinite(seconds) or not 1<=seconds<=300:
            raise ValueError('rehearsal duration must be in [1,300]')
        self.strum_hand,self.source,self.transmission=strum_hand,source,transmission
        self.seconds=seconds
        self.command=list(command) if command else []
        self.command_line=('& '+' '.join("'"+arg.replace("'","''")+"'" for arg in self.command) if os.name=='nt' else shlex.join(self.command)) if self.command else 'not recorded'
        self.label_confirmed=self.zone_confirmed=False
        self.started=self.finished=None
        self.metrics=FrameMetrics()
        self.expired_frames=self.slow_frames=self.strum_hand_frames=0
        self.configured_hand_events=0
        self.control_hand_events={'Left':0,'Right':0,'unknown':0}
        self.minimum=self.maximum=None
        self.done=False
        self.previous_frame=None
        self.maximum_gap=None
        self.notice='Raise strumming hand; check its displayed label and framing'

    def confirm(self,key,now,hands):
        if self.started is not None:return
        if key==ord('c'):
            matches=[hand for hand in hands if hand['handedness']==self.strum_hand and hand['confidence']>=.6]
            if len(matches)==1:
                self.label_confirmed=True
                self.notice=f'Human confirmed {self.strum_hand} as the strumming hand'
            else:
                self.notice=f'Cannot confirm: show exactly one confident {self.strum_hand} hand'
        elif key==ord('z'):
            matches=[hand for hand in hands if hand['handedness']==self.strum_hand and hand['confidence']>=.6]
            if len(matches)==1 and matches[0]['wrist'][1]>=.55:
                self.zone_confirmed=True
                self.notice='Human confirmed framing with strum wrist below the line'
            else:
                self.notice=f'Place the {self.strum_hand} wrist below the line, then press Z'
        if self.label_confirmed and self.zone_confirmed:
            self.started=now
            self.notice=f'{self.seconds:g}s: pinch above line, move, release, open/pinch again'

    def observe(self,started,finished,events,hands,expired,control_hand=None):
        if self.started is None or self.done:return
        self.finished=finished
        gap=started-(self.previous_frame if self.previous_frame is not None else self.started)
        self.maximum_gap=gap if self.maximum_gap is None else max(self.maximum_gap,gap)
        self.previous_frame=started
        visible=any(hand['handedness']==self.strum_hand and hand['confidence']>=.6 for hand in hands)
        self.metrics.record(started,finished,len(events),hand_present=visible)
        self.strum_hand_frames+=int(visible)
        self.expired_frames+=int(expired)
        self.slow_frames+=int(finished-started>.25)
        label=control_hand if control_hand in ('Left','Right') else 'unknown'
        self.control_hand_events[label]+=len(events)
        for event in events:
            if control_hand!=self.strum_hand:continue
            self.configured_hand_events+=1
            value=event['value']
            self.minimum=value if self.minimum is None else min(self.minimum,value)
            self.maximum=value if self.maximum is None else max(self.maximum,value)
        self.done=finished-self.started>=self.seconds
        if self.done:self.notice='Check complete; inspect the saved measured results'

    def remaining(self,now):
        return max(0.,self.seconds-(now-self.started)) if self.started is not None else self.seconds

    def report(self):
        elapsed=max(0.,self.finished-self.started) if self.started is not None and self.finished is not None else 0.
        metrics=self.metrics.snapshot()
        metrics.update(observed_seconds=elapsed,processed_fps=metrics['frames']/elapsed if elapsed else None,
                       emitted_events_hz=metrics['events']/elapsed if elapsed else None,
                       measurement=f'{self.seconds:g}s interval after human confirmation; processing is frame availability to send/print, excluding camera exposure and audio latency')
        span=self.maximum-self.minimum if self.minimum is not None else None
        visibility=self.strum_hand_frames/metrics['frames'] if metrics['frames'] else None
        checks=dict(human_confirmed_strum_label=self.label_confirmed,human_confirmed_zone=self.zone_confirmed,
                    full_interval_completed=self.done,webcam_input=self.source=='webcam',
                    strum_hand_observed=self.strum_hand_frames>0,
                    configured_hand_visible_80_percent=visibility is not None and visibility>=.8,
                    no_frame_gap_over500ms=self.maximum_gap is not None and self.maximum_gap<=.5+1e-9 and self.done,
                    moving_control_output=self.configured_hand_events>=2 and span is not None and span>=.05,
                    no_expired_frames=self.expired_frames==0 and self.done,
                    processing_within250ms=self.slow_frames==0 and self.done)
        return dict(version=1,label='CAMERA REHEARSAL CHECK',source=self.source,transmission=self.transmission,
                    configured_strum_hand=self.strum_hand,required_seconds=self.seconds,
                    command=self.command,command_line=self.command_line,
                    complete=self.done,passed=all(checks.values()),checks=checks,metrics=metrics,
                    expired_frames=self.expired_frames,processing_over250ms_frames=self.slow_frames,
                    strum_hand_frames=self.strum_hand_frames,emitted_value_range=span,
                    configured_hand_visible_fraction=visibility,maximum_frame_gap_ms=self.maximum_gap*1000 if self.maximum_gap is not None else None,
                    configured_hand_events=self.configured_hand_events,control_hand_events=dict(self.control_hand_events),
                    scope='Label and zone are human confirmations; movement requires >=5 percentage points of filter range emitted by the configured hand. Not camera accuracy, strum immunity, UDP acknowledgment, audible quality or audio latency. Replay is never a live rehearsal pass.')

    def summary(self):
        report=self.report();metrics=report['metrics']
        fmt=lambda value: 'not measured' if value is None else f'{value:.2f}'
        return (f"COMMAND: {self.command_line}\nREHEARSAL {'PASS' if report['passed'] else 'INCOMPLETE' if not self.done else 'FAIL'} "
                f"({self.source}, {self.transmission}); measured {fmt(metrics['processed_fps'])} processed FPS, "
                f"{fmt(metrics['emitted_events_hz'])} emitted controls/s; processing mean/p95 "
                f"{fmt(metrics['processing_mean_ms'])}/{fmt(metrics['processing_p95_ms'])} ms; "
                f"expired frames {self.expired_frames}, >250ms processing frames {self.slow_frames}. "
                f"Max frame gap {fmt(report['maximum_frame_gap_ms'])} ms; configured-hand visibility {fmt(report['configured_hand_visible_fraction']*100 if report['configured_hand_visible_fraction'] is not None else None)}%. "
                'Human-confirmed framing/label; local output only, no audio latency measured.')
