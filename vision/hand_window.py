"""Take-window adaptation of Eyes; absent tracking is never treated as stillness."""
from dataclasses import asdict
import json
import math
from pathlib import Path
from .hand_log import MAX_BYTES,MAX_LINE

MAX_WINDOW_SAMPLES = 250000


def report_for_window(log_path,start_unix_ms,end_unix_ms,take_id,hand='strum'):
    from .eyes import HandMovementAnalyzer
    if (type(start_unix_ms) is not int or type(end_unix_ms) is not int or
        not 0<=start_unix_ms<end_unix_ms or end_unix_ms-start_unix_ms>3600000):
        raise ValueError('take window must be positive and at most one hour')
    if not isinstance(take_id,str) or not take_id.strip() or hand not in ('strum','Left','Right'):
        raise ValueError('take ID and hand selector are required')
    path=Path(log_path)
    remaining=path.stat().st_size  # Snapshot size: never chase an appending writer forever.
    if remaining>MAX_BYTES:raise ValueError('hand log exceeds 64 MiB')
    analyzer=HandMovementAnalyzer()
    reports=[]
    previous=None
    last_stamp=None
    selected_label=None
    rejected=0
    gaps=0
    observed=0.
    sample_count=0
    analyzed_seconds=0.
    selection_changed=False

    def finish():
        nonlocal analyzer,previous,observed,sample_count,analyzed_seconds
        if analyzer.samples:
            span=analyzer.samples[-1][0]-analyzer.samples[0][0]
            observed+=span
            sample_count+=len(analyzer.samples)
            if len(analyzer.samples)>=5 and span>.1:
                analyzed_seconds+=span
                reports.append(analyzer.analyze())
        analyzer=HandMovementAnalyzer()
        previous=None

    with path.open('rb') as stream:
        while remaining>0:
            raw=stream.readline(min(remaining,MAX_LINE+1))
            if not raw:break
            remaining-=len(raw)
            if len(raw)>MAX_LINE:raise ValueError('hand-log line exceeds 4096 bytes')
            if not raw.endswith(b'\n'):
                break  # Concurrent writer or truncated tail: not a complete observation.
            try:
                row=json.loads(raw)
                stamp=row.get('timestamp_ms')
                if type(stamp) is not int:raise ValueError('missing timestamp')
                if not start_unix_ms<=stamp<=end_unix_ms:continue
                if last_stamp is not None and stamp<=last_stamp:
                    rejected+=1
                    finish()
                    gaps+=1
                    continue
                last_stamp=stamp
                label=row.get('strum_hand','Right') if hand=='strum' else hand
                if label not in ('Left','Right'):raise ValueError('invalid strumming-hand label')
                if selected_label is not None and selected_label!=label:
                    selection_changed=True
                    raise ValueError('strumming-hand selection changed within the take')
                selected_label=label
                candidates=row.get('hands')
                if not isinstance(candidates,list):raise ValueError('missing hands array')
                matches=[entry for entry in candidates if isinstance(entry,dict) and entry.get('handedness')==label]
                if len(matches)!=1:
                    finish();gaps+=1;continue
                entry=matches[0];wrist=entry.get('wrist');confidence=entry.get('confidence')
                if not isinstance(wrist,list) or len(wrist)!=2:raise ValueError('invalid wrist')
                if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in [*wrist,confidence]):
                    raise ValueError('invalid coordinates or confidence')
                if confidence<.6:
                    finish();gaps+=1;continue
                t=(stamp-start_unix_ms)/1000
                if previous is not None and (t-previous[0]>.15 or math.hypot(wrist[0]-previous[1],wrist[1]-previous[2])>.3):
                    finish();gaps+=1
                analyzer.add_sample(t,*wrist)
                previous=(t,*wrist)
            except (ValueError,TypeError,AttributeError,UnicodeError,OverflowError,RecursionError):
                rejected+=1
                finish()
                gaps+=1
            if sample_count+len(analyzer.samples)>MAX_WINDOW_SAMPLES:
                raise ValueError('take window exceeds 250000 wrist samples')
    finish()
    duration=(end_unix_ms-start_unix_ms)/1000
    good=[r for r in reports if r.sample_count>=5 and r.duration_s>.1]
    coverage=min(1.,analyzed_seconds/duration)
    stalls=[]
    for segment in good:
        for original in segment.stalls:
            stall=dict(original)
            stall['start_ms']=round(stall['start_time_s']*1000)
            stall['end_ms']=round(stall['end_time_s']*1000)
            stall['message']=f"Selected wrist stayed nearly still from {stall['start_ms']} to {stall['end_ms']} ms; this may be an intentional rest."
            stalls.append(stall)
    longest=max(good,key=lambda r:r.duration_s) if good else None
    available=bool(good) and coverage>=.5 and not selection_changed
    # Preserve the existing HandReport fields, add alignment/coverage metadata.
    result=asdict(longest) if longest else asdict(HandMovementAnalyzer().analyze())
    result.update(source='vision.eyes/window',take_id=take_id,started_unix_ms=start_unix_ms,
                  ended_unix_ms=end_unix_ms,duration_s=duration,sample_count=sample_count,
                  strum_count=sum(r.strum_count for r in good),stalls=stalls,
                  available=available,selected_hand=selected_label or (hand if hand!='strum' else 'Right'),
                  coverage=round(coverage,4),observed_seconds=round(observed,3),
                  observed_coverage=round(min(1.,observed/duration),4),analyzed_seconds=round(analyzed_seconds,3),
                  tracking_gaps=gaps,rejected_rows=rejected,
                  selection_changed=selection_changed,
                  motion_continuity_score=round(max(0.,1-sum(s['duration_ms'] for s in stalls)/max(analyzed_seconds*1000,1)),2),
                  summary=(f"Observed {len(stalls)} stationary wrist spans over {coverage:.0%} of the take. "
                           'Alignment supports comparison with audio, not a diagnosis of why a hesitation happened.'
                           if available else 'Hand evidence unavailable or too incomplete: need at least 50% observed time and one continuous segment of 5+ frames.'))
    if not available:
        result['motion_continuity_score']=0.
    if len(good)>1 or not available:
        result['tempo_bpm']=None
        result['tempo_stability']=0.
    return result


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description='Analyze wrist metadata for the exact window in an audio take sidecar; no model/API calls.')
    parser.add_argument('log',type=Path)
    parser.add_argument('sidecar',type=Path)
    parser.add_argument('--hand',choices=('strum','Left','Right'),default='strum')
    parser.add_argument('--output',type=Path,help='new report JSON file; otherwise print')
    args=parser.parse_args(argv)
    try:
        metadata=json.loads(args.sidecar.read_text())
        report=report_for_window(args.log,metadata['started_unix_ms'],metadata['ended_unix_ms'],metadata['take_id'],args.hand)
        payload=json.dumps(report,indent=2)+'\n'
        if args.output:
            with args.output.open('x',encoding='utf-8') as file:file.write(payload)
        else:print(payload,end='')
    except (ValueError,OSError,KeyError,TypeError) as exc:
        parser.exit(2,f'hand-window: {exc}\n')


if __name__=='__main__':
    main()
