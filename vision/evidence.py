"""Portable, read-only replay of aligned Ears and Eyes evidence for one take."""
import argparse
import json
import math
from pathlib import Path
import shutil
import wave

MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_AUDIO_BYTES = 128 * 1024 * 1024
MAX_ANALYSIS_SECONDS = 60
MAX_ANALYSIS_SAMPLES = 2880000  # PCM channel-samples; Ears allocates full filtering arrays.


def load_report(path):
    path = Path(path)
    if path.stat().st_size > MAX_REPORT_BYTES:
        raise ValueError('report exceeds 8 MiB')
    return json.loads(path.read_text())


def number(value, name, low=0., high=3600000.):
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and low <= value <= high
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f'{name} must be a finite number in [{low},{high}]')
    return value


def validate(ears, hands):
    if not isinstance(ears, dict) or not isinstance(hands, dict):
        raise ValueError('two report objects are required')
    take_id = ears.get('take_id')
    start = ears.get('started_unix_ms')
    if not isinstance(take_id, str) or not take_id.strip() or hands.get('take_id') != take_id:
        raise ValueError('reports must identify the same nonempty take_id')
    if type(start) is not int or start < 0 or type(hands.get('started_unix_ms')) is not int or hands.get('started_unix_ms') != start:
        raise ValueError('reports must have the same started_unix_ms')
    duration = number(ears.get('duration_s'), 'audio duration', .001, 3600)
    hand_duration = number(hands.get('duration_s'), 'hand window duration', .001, 3600)
    if abs(duration-hand_duration) > .1:
        raise ValueError('report durations differ by more than 100 ms')
    if type(hands.get('available')) is not bool:
        raise ValueError('hand report must identify whether evidence is available')
    number(hands.get('coverage'), 'analyzed hand coverage', high=1.)
    for key, report in (('findings', ears), ('stalls', hands)):
        entries = report.get(key, [])
        if not isinstance(entries, list) or len(entries) > 10000:
            raise ValueError(f'{key} must contain at most 10000 entries')
        for item in entries:
            if not isinstance(item, dict):
                raise ValueError(f'invalid {key} entry')
            if key == 'findings':
                number(item.get('at_ms'), 'audio finding time', high=duration*1000+.5)
                number(item.get('extra_ms', 0), 'extra gap', low=-3600000)
            else:
                left = number(item.get('start_ms'), 'wrist span start', high=hand_duration*1000+.5)
                right = number(item.get('end_ms'), 'wrist span end', high=hand_duration*1000+.5)
                if right < left:
                    raise ValueError('wrist span ends before it starts')
    return duration


def html_page(bundle, audio):
    payload = json.dumps(bundle, allow_nan=False).replace('<', '\\u003c')
    player = '<audio id="audio" controls preload="auto" src="take.wav"></audio>' if audio else '<p>No audio included. Timeline evidence is available below.</p>'
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OmniRiff · Take evidence</title><style>
:root{color-scheme:dark;font:17px/1.6 system-ui;background:#100f19;color:#f7f2ff}body{max-width:1100px;margin:auto;padding:32px 24px}small{color:#f5a2bf;letter-spacing:.12em;text-transform:uppercase}h1{font-size:clamp(30px,6vw,54px);margin:10px 0}p{color:#c1b8cd}audio{width:100%}.panel{padding:24px;background:#1d1829;border:1px solid #584263;border-radius:12px;margin:24px 0}#status{color:#ffe0a6;font-weight:600}svg{width:100%;height:250px;overflow:visible}button{color:#fff;background:#402546;border:1px solid #bf82b5;font:inherit;padding:8px 14px;cursor:pointer;border-radius:5px}button:disabled{opacity:.55;cursor:default}li{margin:14px 0;padding:12px;background:#211a2d}a{color:#d9b4ff}.legend{display:flex;gap:24px;flex-wrap:wrap}.pink{color:#f5a2bf}.purple{color:#b6a4ff}#now{font-variant-numeric:tabular-nums}#label{color:#fff}
</style><small>OmniRiff / Take evidence</small><h1>Hear the pause. See the timing.</h1><p id="label"></p><p id="take"></p>
<div class="panel"><div id="status" role="status"></div><p id="alignment"></p>PLAYER<p id="now">Playback: 0.00 s</p><svg id="timeline" viewBox="0 0 1000 220" role="img" aria-label="Audio findings and wrist stationary spans on the same take timeline"></svg><div class="legend"><span class="pink">Pink: extra audio gap / onset marker</span><span class="purple">Purple: observed stationary wrist span</span></div></div>
<h2>Replay an audio finding</h2><ol id="findings"></ol><h2>Wrist evidence</h2><ol id="stalls"></ol>
<p>Both reports use the same take ID and Unix start time. Alignment shows when observations occurred; an intended rest can look like a hesitation or stationary wrist. A matching span does not establish a cause.</p>
<p>Camera timestamps mark frame availability, not sample-accurate exposure. Missing wrist tracking is not plotted as stillness. This viewer cannot verify camera/audio provenance.</p>
<p><a href="evidence.json">Download the underlying evidence</a></p>
<script>
const data=PAYLOAD, ears=data.ears, hands=data.hands, duration=ears.duration_s;
const $=id=>document.getElementById(id), audio=$('audio'), ns='http://www.w3.org/2000/svg';
$('label').textContent=data.label;$('take').textContent='Take '+ears.take_id+' · '+duration.toFixed(2)+' seconds';
const offset=Math.round((hands.duration_s-duration)*1000);$('alignment').textContent=offset?'Wrist-window duration offset: '+(offset>0?'+':'')+offset+' ms. Timeline clips at the audio end.':'Audio and wrist-window durations align.';
const usable=hands.available===true;
$('status').textContent=usable?'Wrist evidence available · analyzed coverage '+Math.round((hands.coverage||0)*100)+'%':'WRIST EVIDENCE INCOMPLETE — inspect coverage and tracking before drawing conclusions';
if(ears.judgeable===false)$('status').textContent+=' · AUDIO TAKE NOT JUDGEABLE';
function svg(tag,attrs,text){const el=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))el.setAttribute(k,v);if(text)el.textContent=text;$('timeline').append(el);return el}
function x(ms){return 95+Math.min(duration*1000,Math.max(0,ms))/(duration*1000)*880}
for(let i=0;i<=4;i++){const seconds=duration*i/4;svg('line',{x1:x(seconds*1000),x2:x(seconds*1000),y1:25,y2:180,stroke:'#54475d'});svg('text',{x:x(seconds*1000),y:208,fill:'#c1b8cd','text-anchor':'middle','font-size':15},seconds.toFixed(1)+'s')}
svg('text',{x:0,y:70,fill:'#eee','font-size':16},'Audio');svg('text',{x:0,y:150,fill:'#eee','font-size':16},'Wrist');
// Buffer the local bundle over HTTP so seeking also works on simple servers
// without byte-range support. Local file playback uses the original WAV URL.
let buffered=null;
function prepareAudio(){if(buffered)return buffered;buffered=audio&&location.protocol!=='file:'?fetch('take.wav').then(r=>{if(!r.ok)throw Error();return r.blob()}).then(blob=>{audio.src=URL.createObjectURL(blob);audio.load()}).catch(()=>{}):Promise.resolve();return buffered}
function metadata(){if(audio.readyState>=1)return Promise.resolve();return new Promise((resolve,reject)=>{let timer;const cleanup=()=>{clearTimeout(timer);audio.removeEventListener('loadedmetadata',ready);audio.removeEventListener('error',failed)};const ready=()=>{cleanup();resolve()};const failed=()=>{cleanup();reject(Error('Audio unavailable or unsupported'))};audio.addEventListener('loadedmetadata',ready);audio.addEventListener('error',failed);timer=setTimeout(failed,8000);if(audio.error)failed()})}
async function play(at){if(!audio)return;try{await prepareAudio();await metadata();audio.currentTime=Math.max(0,at/1000-1);await audio.play()}catch(error){$('status').textContent='Audio could not play. Try the native audio control or open the copied WAV directly.'}}

for(const f of ears.findings||[]){const left=x(f.at_ms-Math.max(0,f.extra_ms||0)), right=x(f.at_ms);svg('rect',{x:left,y:43,width:Math.max(3,right-left),height:36,fill:'#f5a2bf'});svg('line',{x1:right,x2:right,y1:36,y2:86,stroke:'white','stroke-width':2});const li=document.createElement('li'),button=document.createElement('button');button.textContent='Play at '+(f.at_ms/1000).toFixed(2)+'s';button.disabled=!audio;button.onclick=()=>play(f.at_ms);li.append(button,document.createTextNode(' '+(f.message||f.type||'Audio finding')));$('findings').append(li)}
if(!(ears.findings||[]).length)$('findings').textContent='No audio findings in this report.';
for(const s of hands.stalls||[]){svg('rect',{x:x(s.start_ms),y:121,width:Math.max(3,x(s.end_ms)-x(s.start_ms)),height:36,fill:usable?'#b6a4ff':'#6b627e'});const li=document.createElement('li');li.textContent=(s.start_ms/1000).toFixed(2)+'–'+(s.end_ms/1000).toFixed(2)+'s · '+(s.message||'Stationary wrist span');$('stalls').append(li)}
if(!(hands.stalls||[]).length)$('stalls').textContent=usable?'No stationary spans reported.':'No usable stationary-span conclusion.';
const cursor=svg('line',{x1:x(0),x2:x(0),y1:20,y2:180,stroke:'#fff','stroke-width':2});
if(audio)audio.ontimeupdate=()=>{cursor.setAttribute('x1',x(audio.currentTime*1000));cursor.setAttribute('x2',x(audio.currentTime*1000));$('now').textContent='Playback: '+audio.currentTime.toFixed(2)+' s'};
</script></html>'''.replace('PLAYER',player).replace('PAYLOAD',payload)


def inspect_wav(path, *, duration=None, analysis=False):
    path=Path(path)
    if path.stat().st_size>MAX_AUDIO_BYTES:
        raise ValueError('WAV exceeds 128 MiB')
    with wave.open(str(path),'rb') as info:
        frames,rate,channels=info.getnframes(),info.getframerate(),info.getnchannels()
        if (channels not in (1,2) or info.getcomptype()!='NONE' or
            info.getsampwidth() not in (1,2,3,4) or not 8000<=rate<=96000 or frames<1):
            raise ValueError('use a nonempty mono/stereo PCM WAV at 8..96 kHz')
        seconds=frames/rate
        if duration is not None and abs(seconds-duration)>.1:
            raise ValueError('WAV duration differs from the reports')
        if analysis and (seconds>MAX_ANALYSIS_SECONDS or frames*channels>MAX_ANALYSIS_SAMPLES):
            raise ValueError('analysis is limited to 60 seconds and 2880000 PCM channel-samples')
        expected=frames*channels*info.getsampwidth()
        decoded=0
        while decoded<expected:
            chunk=info.readframes(16384)
            if not chunk:
                raise ValueError('WAV payload is incomplete')
            decoded+=len(chunk)
    return dict(frames=frames,samplerate=rate,channels=channels,seconds=seconds)


def analyze_capture(take, *, sidecar=None, hand_log=None):
    """Use the production offline analyzers after validating a completed capture."""
    from dataclasses import asdict
    from tools.ears.analyze import analyze_take
    from .eyes import HandMovementAnalyzer, report_for_window

    take=Path(take)
    sidecar=Path(sidecar) if sidecar else take.with_suffix('.json')
    metadata=load_report(sidecar)
    if not isinstance(metadata,dict) or type(metadata.get('version')) is not int or metadata['version']!=1:
        raise ValueError('a version 1 audio take sidecar is required')
    take_id=metadata.get('take_id')
    if not isinstance(take_id,str) or not take_id.strip():
        raise ValueError('sidecar take_id must be nonempty')
    start,end=metadata.get('started_unix_ms'),metadata.get('ended_unix_ms')
    if type(start) is not int or type(end) is not int or not 0<=start<end or end-start>3600000:
        raise ValueError('sidecar requires a positive take window of at most one hour')
    header=inspect_wav(take,analysis=True)
    for key in ('frames','samplerate'):
        if type(metadata.get(key)) is not int or metadata[key]!=header[key]:
            raise ValueError(f'sidecar {key} does not match WAV')
    seconds=number(metadata.get('seconds'),'sidecar seconds',.001,3600)
    if abs(seconds-header['seconds'])>.001 or abs((end-start)/1000-header['seconds'])>.1:
        raise ValueError('sidecar duration/window does not match WAV')
    if metadata.get('wav')!=take.name:
        raise ValueError('sidecar wav must name the selected WAV basename')
    if hand_log is not None:
        # Fail before audio analysis when a provided log is invalid/unavailable.
        hands=report_for_window(hand_log,start,end,take_id)
    else:
        hands=asdict(HandMovementAnalyzer().analyze())
        hands.update(take_id=take_id,started_unix_ms=start,ended_unix_ms=end,
                     duration_s=(end-start)/1000,available=False,coverage=0.,
                     source='vision.eyes/unavailable',summary='No hand log supplied; wrist evidence unavailable.')
    ears=asdict(analyze_take(take,sidecar))
    validate(ears,hands)
    return ears,hands


def export(ears, hands, output, *, label, audio=None):
    duration = validate(ears,hands)
    if not isinstance(label,str) or not label.strip():
        raise ValueError('provide an explicit source label')
    if audio:
        audio=Path(audio)
        inspect_wav(audio,duration=duration)
    bundle=dict(version=1,label=label,ears=ears,hands=hands)
    # Check serialization before creating any output.
    encoded=json.dumps(bundle,indent=2,allow_nan=False)+'\n'
    html=html_page(bundle,bool(audio))
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    (output/'evidence.json').write_text(encoded,encoding='utf-8')
    (output/'index.html').write_text(html,encoding='utf-8')
    if audio:shutil.copyfile(audio,output/'take.wav')
    return output/'index.html'


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    source=p.add_mutually_exclusive_group(required=True)
    source.add_argument('--ears',type=Path,help='precomputed Ears report; requires --hands')
    source.add_argument('--take',type=Path,help='completed take WAV; analyze it and copy audio for replay')
    p.add_argument('--hands',type=Path,help='precomputed take-window Eyes report')
    p.add_argument('--sidecar',type=Path,help='with --take: audio sidecar override; defaults to WAV basename.json')
    p.add_argument('--hand-log',type=Path,help='with --take: both-hand log; omission explicitly marks wrist evidence unavailable')
    p.add_argument('--metadata-only',action='store_true',help='with --take: omit the audio copy from the output')
    p.add_argument('--audio',type=Path,help='optionally copy the take WAV for local replay')
    p.add_argument('--label',required=True,help='explicit source label; mark synthetic/replay inputs')
    p.add_argument('--output',type=Path,required=True,help='new folder; refuses overwrite')
    args=p.parse_args(argv)
    if args.take and (args.hands or args.audio):
        p.error('--take computes reports and includes its WAV; omit --hands/--audio')
    if args.ears and (not args.hands or args.sidecar or args.hand_log or args.metadata_only):
        p.error('--ears requires --hands; --sidecar/--hand-log/--metadata-only require --take')
    try:
        if args.output.exists():
            raise ValueError('output folder exists; choose a new folder')
        if args.take:
            ears,hands=analyze_capture(args.take,sidecar=args.sidecar,hand_log=args.hand_log)
            audio=None if args.metadata_only else args.take
        else:
            ears,hands=load_report(args.ears),load_report(args.hands)
            audio=args.audio
        print(export(ears,hands,args.output,label=args.label,audio=audio))
    except (ValueError,OSError,TypeError,OverflowError,RecursionError,wave.Error) as exc:
        p.exit(2,f'evidence: {exc}\n')


if __name__=='__main__':
    main()
