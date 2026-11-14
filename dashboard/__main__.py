"""Serve the dashboard from localhost (the engine's WebSocket rejects file:// origins).

  python -m dashboard            -> http://127.0.0.1:8080/
  python -m dashboard --port 9000
"""
from __future__ import annotations

import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

HERE = Path(__file__).resolve().parent


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def _labelled(sim: str):
    """A handler that sends the bare page to ?sim=..., so a simulated guitar is always named on screen."""
    class _Sim(_Quiet):
        def do_GET(self):
            url = urlsplit(self.path)
            if url.path in ('/', '/index.html') and 'sim' not in parse_qs(url.query):
                query = (url.query + '&' if url.query else '') + urlencode({'sim': sim})
                self.send_response(302)
                self.send_header('Location', f'{url.path}?{query}')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            super().do_GET()
    return _Sim


def make_server(port: int = 8080, sim: str | None = None) -> ThreadingHTTPServer:
    """`sim` is set only by tools that feed a synthetic guitar (tools/sim); the real engine never sets it."""
    handler = functools.partial(_labelled(sim) if sim else _Quiet, directory=str(HERE))
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
