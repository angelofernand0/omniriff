"""Observe the live engine and hand feed through a guided, read-only soundcheck."""
import argparse
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlparse
from jsonschema import Draft202012Validator
from websockets.asyncio.client import connect
from .session import Session
from .page import page

ROOT = Path(__file__).resolve().parents[2]


def local_ws(value):
    parsed = urlparse(value)
    if parsed.scheme!='ws' or parsed.hostname not in ('127.0.0.1','localhost','::1') or parsed.username or parsed.password or parsed.fragment:
        raise argparse.ArgumentTypeError('use a local ws://127.0.0.1:PORT endpoint')
    try:
        if not parsed.port:
            raise ValueError()
    except ValueError:
        raise argparse.ArgumentTypeError('endpoint requires a valid port')
    return value


class Feed:
    def __init__(self, schema):
        self.validator = Draft202012Validator(schema)
        self.value = None
        self.received = 0.
        self.connected = False
        self.error = None

    def accept(self, value, received):
        self.validator.validate(value)
        # Duplicate/reordered cached frames cannot extend freshness or a hold.
        if self.value is not None and value['timestamp_ms']<=self.value['timestamp_ms']:
            return False
        self.value, self.received = value, received
        return True

    def fresh(self, now, wall):
        if not self.connected or self.value is None:
            return False
        timestamp = self.value.get('timestamp_ms',0)/1000
        return 0<=now-self.received<=.5 and abs(wall-timestamp)<=.5

    async def run(self, url):
        while True:
            try:
                async with connect(url, max_size=65536, max_queue=1, open_timeout=2, close_timeout=.2) as ws:
                    self.connected = True
                    self.error = None
                    async for raw in ws:
                        value = json.loads(raw)
                        self.accept(value,time.monotonic())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.error = type(exc).__name__
            finally:
                self.connected = False
                self.value = None
            await asyncio.sleep(.5)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        allowed = {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        if self.headers.get('Host') not in allowed:
            self.send_error(403)
            return
        if self.path=='/':
            body,kind = self.server.html, 'text/html; charset=utf-8'
        elif self.path=='/api/state':
            body,kind = self.server.payload, 'application/json'
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


async def run(args):
    session = Session(targets=args.targets, timeout=args.timeout)
    feeds = {name: Feed(json.loads((ROOT/'protocol'/f'{name}.schema.json').read_text())) for name in ('state','hand')}
    server = ThreadingHTTPServer(('127.0.0.1',args.http_port),Handler)
    server.html = page().encode()
    server.payload = json.dumps(session.report()).encode()
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    tasks = []
    try:
        # Reserve output before starting observers; never overwrite prior evidence.
        args.output.mkdir(parents=True,exist_ok=False)
        thread.start()
        print(f'Gesture soundcheck: http://127.0.0.1:{server.server_port}/',flush=True)
        print('Read-only: no rig commands, video, audio or landmark recordings.',flush=True)
        tasks = [asyncio.create_task(feeds['state'].run(args.engine_ws)),
                 asyncio.create_task(feeds['hand'].run(args.hand_ws))]
        previous_cue = None
        while not session.done:
            now,wall = time.monotonic(),time.time()
            state,hand = feeds['state'].value or {},feeds['hand'].value or {}
            fresh = all(feed.fresh(now,wall) for feed in feeds.values())
            session.update(now,value=state.get('filter',{}).get('target'),
                           hand_present=hand.get('present',False), engaged=hand.get('engaged',False),
                           confidence=hand.get('confidence',0), fresh=fresh,control=hand.get('control'))
            report = session.report()
            report['source_label'] = args.source_label
            report['feeds'] = {name: dict(connected=feed.connected,error=feed.error) for name,feed in feeds.items()}
            server.payload = json.dumps(report,allow_nan=False).encode()
            if previous_cue!=session.cue:
                print(f"{min(session.index+1,len(session.targets))}/{len(session.targets)}: {session.cue}",flush=True)
                previous_cue = session.cue
            await asyncio.sleep(.05)
        await asyncio.sleep(.3)  # Let the live page receive the final state.
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        report = session.report()
        report['source_label'] = args.source_label
        report['feeds'] = {name: dict(connected=feed.connected,error=feed.error) for name,feed in feeds.items()}
        # Don't touch an existing folder if exclusive mkdir failed.
        if thread.ident is not None:
            (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
            (args.output/'index.html').write_text(page(report),encoding='utf-8')
            await asyncio.to_thread(server.shutdown)
            thread.join(2)
            print(f"Saved {args.output/'index.html'}",flush=True)
        server.server_close()
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine-ws',type=local_ws,default='ws://127.0.0.1:47801')
    p.add_argument('--hand-ws',type=local_ws,default='ws://127.0.0.1:47802')
    p.add_argument('--http-port',type=int,default=0)
    p.add_argument('--targets',type=float,nargs='+',default=[.25,.75,.5])
    p.add_argument('--timeout',type=float,default=20,help='deadline in seconds for each target')
    p.add_argument('--output',type=Path,required=True,help='new report folder; refuses overwrite')
    p.add_argument('--source-label',default='Local rig: camera source unverified',help='label synthetic feeds explicitly when testing')
    args = p.parse_args()
    if not 0<=args.http_port<=65535:
        p.error('http port must be in [0,65535]')
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass  # run() saves an explicitly incomplete report.
    except (ValueError,OSError) as exc:
        p.exit(2,f'soundcheck: {exc}\n')


if __name__=='__main__':
    main()
