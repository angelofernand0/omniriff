"""Serve the dashboard from localhost (the engine's WebSocket rejects file:// origins).

  python -m dashboard            -> http://127.0.0.1:8080/
  python -m dashboard --port 9000
"""
from __future__ import annotations

import argparse
import functools
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

HERE = Path(__file__).resolve().parent


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def _labelled(sim: str, hooks: dict | None = None):
    """A handler that sends the bare page to ?sim=..., so a simulated guitar is always named on screen.
    `hooks['handle'](path, query)` answers /sim/... (tools/sim's manual test control; localhost only)."""
    class _Sim(_Quiet):
        def do_GET(self):
            url = urlsplit(self.path)
            if hooks is not None and url.path.startswith('/sim/'):
                handle = hooks.get('handle')
                body = {'error': 'not ready'} if handle is None else handle(url.path, {k: v[0] for k, v in parse_qs(url.query).items()})
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if url.path in ('/', '/index.html') and 'sim' not in parse_qs(url.query):
                query = (url.query + '&' if url.query else '') + urlencode({'sim': sim})
                self.send_response(302)
                self.send_header('Location', f'{url.path}?{query}')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            super().do_GET()
    return _Sim


def make_server(port: int = 8080, sim: str | None = None, hooks: dict | None = None) -> ThreadingHTTPServer:
    """`sim` is set only by tools that feed a synthetic guitar (tools/sim); the real engine never sets it."""
    handler = functools.partial(_labelled(sim, hooks) if sim else _Quiet, directory=str(HERE))
    return ThreadingHTTPServer(('127.0.0.1', port), handler)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog='python -m dashboard')
    p.add_argument('--port', type=int, default=8080)
    a = p.parse_args(argv)
    server = make_server(a.port)
    print(f'dashboard http://127.0.0.1:{server.server_address[1]}/  (state from ws://127.0.0.1:47801; ?ws=... to override)')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
