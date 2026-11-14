"""Serve the dashboard from localhost (the engine's WebSocket rejects file:// origins).

  python -m dashboard            -> http://127.0.0.1:8080/
  python -m dashboard --port 9000
"""
from __future__ import annotations

import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def make_server(port: int = 8080) -> ThreadingHTTPServer:
    handler = functools.partial(_Quiet, directory=str(HERE))
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
