"""Build a bounded local replay index for a folder of completed audio takes."""
import argparse
from html import escape
import json
from pathlib import Path
import wave

from .evidence import analyze_capture, export
from .hand_log import MAX_BYTES

MAX_DIRECTORY_ENTRIES = 10000
MAX_WAV_CANDIDATES = 1000
MAX_COPIED_AUDIO_BYTES = 512 * 1024 * 1024


def select_takes(directory, limit):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('limit must be an integer in [1,100]')
    paths=[]
    for count,path in enumerate(Path(directory).iterdir(),1):
        if count>MAX_DIRECTORY_ENTRIES:
            raise ValueError('input folder exceeds 10000 entries; choose a session subfolder')
        if path.is_file() and path.suffix.lower()=='.wav':
            paths.append(path)
            if len(paths)>MAX_WAV_CANDIDATES:
                raise ValueError('input folder exceeds 1000 WAVs; choose a session subfolder')
    if not paths:
        raise ValueError('input folder contains no WAV takes')
    return sorted(paths,key=lambda path:path.name)[-limit:]


def index_page(manifest):
    status=('EXPORT FINISHED WITH REJECTED FILES' if manifest['errors'] else 'EXPORT COMPLETE') if manifest['complete'] else 'EXPORT INCOMPLETE — completed pages preserved'
    cards=[]
    for item in manifest['takes']:
        metric=(f"Longest reported extra gap: {item['longest_extra_ms']:.0f} ms" if item['judgeable'] else
                'Too few strums for a timing judgment')
        hand=(f"Wrist evidence: {item['coverage']:.0%} analyzed coverage" if item['hand_available'] else
              'Wrist evidence unavailable / incomplete')
        cards.append(f'''<article><h2><a href="{item['folder']}/index.html">{escape(item['take_id'])}</a></h2>
<p>{item['duration_s']:.2f}s · {item['audio_findings']} audio findings</p><p>{metric}</p><p>{hand}</p></article>''')
    errors=''.join(f'<li><strong>{escape(row["file"])}</strong>: {escape(row["error"])}</li>' for row in manifest['errors'])
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OmniRiff · Session evidence</title><style>
:root{{color-scheme:dark;font:18px/1.6 system-ui;background:#100f19;color:#f6f1ff}}body{{max-width:1050px;margin:auto;padding:36px 24px}}small,a{{color:#f5a2bf}}h1{{font-size:clamp(34px,6vw,56px);line-height:1.1}}p{{color:#c5bad3}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px}}article{{padding:24px;background:#21192e;border:1px solid #65406b;border-radius:12px}}h2{{font-size:24px;overflow-wrap:anywhere}}li{{padding:12px 0}}
</style><small>OMNIRIFF / SESSION EVIDENCE</small><h1>Replay the takes that matter.</h1>
<p>{escape(manifest['label'])}</p><p>{status}</p><p>{len(manifest['takes'])} replay pages · {len(manifest['errors'])} rejected {'file' if len(manifest['errors'])==1 else 'files'} · {manifest['selected']} selected WAVs</p>
<div class="cards">{''.join(cards) or '<p>No replay pages could be built. Inspect the rejected files below.</p>'}</div>
<h2>Rejected files</h2><ul>{errors or '<li>None.</li>'}</ul>
<p>Cards are ordered by each report’s Unix take start. Input selection uses the last {manifest['limit']} WAV filenames in lexical order, nonrecursive. TakeWriter filenames include time; arbitrary filenames may not reflect capture order.</p>
<p>These are measured report summaries, not an improvement grade. Different patterns, intentional rests and incomplete tracking can change the numbers. Source labels are operator-supplied; this index cannot verify provenance or cause.</p>
<p><a href="session.json">Download the session manifest</a></p></html>'''


def build(directory, output, *, label, hand_log=None, limit=20, metadata_only=False):
    if not isinstance(label,str) or not label.strip():
        raise ValueError('provide an explicit source label')
    output=Path(output)
    if output.exists():
        raise FileExistsError('output folder exists; choose a new folder')
    selected=select_takes(directory,limit)
    if not metadata_only and sum(path.stat().st_size for path in selected)>MAX_COPIED_AUDIO_BYTES:
        raise ValueError('selected audio exceeds 512 MiB; lower --limit or use --metadata-only')
    if hand_log is not None:
        hand_log=Path(hand_log)
        if not hand_log.is_file():
            raise ValueError('provided hand log must be an existing file')
        if hand_log.stat().st_size>MAX_BYTES:
            raise ValueError('provided hand log exceeds 64 MiB')
    output.mkdir(parents=True,exist_ok=False)
    manifest=dict(version=1,label=label,selection='last filenames in lexical order',limit=limit,
                  selected=len(selected),audio_included=not metadata_only,complete=False,takes=[],errors=[])
    def save_index():
        for name,payload in [('session.json',json.dumps(manifest,indent=2,allow_nan=False)+'\n'),('index.html',index_page(manifest))]:
            temporary=output/(name+'.tmp')
            temporary.write_text(payload,encoding='utf-8')
            temporary.replace(output/name)
    save_index()
    identities=set()
    for position,wav in enumerate(selected,1):
        try:
            ears,hands=analyze_capture(wav,hand_log=hand_log)
            if ears['take_id'] in identities:
                raise ValueError('duplicate take_id in selected session; prior page preserved')
            folder=f'take-{position:03d}'
            export(ears,hands,output/folder,label=label,audio=None if metadata_only else wav)
            identities.add(ears['take_id'])
            judgeable=ears.get('judgeable') is True
            manifest['takes'].append(dict(folder=folder,file=wav.name,take_id=ears['take_id'],
                started_unix_ms=ears['started_unix_ms'],duration_s=ears['duration_s'],judgeable=judgeable,
                audio_findings=len(ears['findings']),
                longest_extra_ms=max([0.,*[f.get('extra_ms',0) for f in ears['findings']]]) if judgeable else None,
                hand_available=hands['available'],coverage=hands['coverage']))
        except (ValueError,OSError,TypeError,OverflowError,RecursionError,wave.Error) as exc:
            if isinstance(exc,FileNotFoundError):
                reason=f'Missing input file: {Path(exc.filename).name}' if exc.filename else 'Missing input file'
            elif isinstance(exc,OSError):
                reason=exc.strerror or type(exc).__name__
            else:
                reason=str(exc)
            manifest['errors'].append(dict(file=wav.name,error=reason))
        manifest['takes'].sort(key=lambda item:(item['started_unix_ms'],item['take_id']))
        save_index()
    manifest['complete']=True
    save_index()
    return manifest


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('takes',type=Path,help='folder of completed WAV + sidecar pairs, nonrecursive')
    p.add_argument('--hand-log',type=Path,help='one both-hand session log covering the take windows')
    p.add_argument('--limit',type=int,default=20,help='last 1..100 WAV filenames; default 20')
    p.add_argument('--metadata-only',action='store_true',help='omit copied audio')
    p.add_argument('--label',required=True,help='explicit source label; mark synthetic/replay inputs')
    p.add_argument('--output',type=Path,required=True,help='new output folder')
    args=p.parse_args(argv)
    try:
        result=build(args.takes,args.output,label=args.label,hand_log=args.hand_log,limit=args.limit,metadata_only=args.metadata_only)
    except (ValueError,OSError) as exc:
        p.exit(2,f'session-evidence: {exc}\n')
    except KeyboardInterrupt:
        p.exit(130,f'Interrupted; completed pages remain under {args.output}.\n')
    print(f"Built {len(result['takes'])} replay pages; rejected {len(result['errors'])}. Open {args.output/'index.html'}")
    if result['errors']:
        p.exit(2,'Inspect rejected files in session.json; successful pages remain available.\n')


if __name__=='__main__':
    main()
