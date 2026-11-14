import socket
import sys
import threading
import time
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import engine.demo as demo  # noqa: E402
from engine.demo import _ws_port, main, start_vision, stop_process, vision_command  # noqa: E402


def free_port(kind=socket.SOCK_STREAM):
    s = socket.socket(socket.AF_INET, kind)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class DemoLauncherTests(unittest.TestCase):
    def test_headless_run_serves_dashboard_and_cleans_up(self):
        http, ws, udp = free_port(), free_port(), free_port(socket.SOCK_DGRAM)
        result = {}
        t = threading.Thread(target=lambda: result.setdefault("rc", main([
            "--http-port", str(http), "--headless", "--no-keyboard", "--duration", "2",
            "--ws-port", str(ws), "--udp-port", str(udp)])))
        t.start()
        body = b""
        deadline = time.time() + 5
        while time.time() < deadline and not body:
            try:
                body = urllib.request.urlopen(f"http://127.0.0.1:{http}/", timeout=1).read()
            except OSError:
                time.sleep(0.1)
        t.join(10)
        self.assertFalse(t.is_alive())
        self.assertEqual(result.get("rc"), 0)
        self.assertIn(b"<html", body.lower())
        from dashboard.__main__ import make_server
        again = make_server(http)  # the launcher released its port: a new dashboard can start there
        again.server_close()

    def test_busy_dashboard_port_fails_fast(self):
        holder = socket.socket()
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        try:
            self.assertEqual(main(["--http-port", str(holder.getsockname()[1]), "--headless", "--duration", "1"]), 1)
        finally:
            holder.close()

    def test_child_process_is_stopped(self):
        proc = start_vision([sys.executable, "-c", "import time; time.sleep(30)"])
        self.assertIsNone(proc.poll())
        stop_process(proc, timeout=3)
        self.assertIsNotNone(proc.poll())
        stop_process(None)  # no-op

    def test_ws_port_is_read_from_engine_args(self):
        self.assertEqual(_ws_port(["--headless", "--ws-port", "48001"]), 48001)
        self.assertEqual(_ws_port(["--headless"]), 47801)

    def test_vision_is_pointed_at_this_engines_udp_port(self):
        cmd = vision_command(["--model", "m.task"], ["--headless", "--udp-port", "48720"])
        self.assertEqual(cmd[cmd.index("--port") + 1], "48720")
        self.assertEqual(vision_command([], ["--headless"])[-2:], ["--port", "47800"])
        explicit = vision_command(["--port", "49000"], ["--udp-port", "48720"])
        self.assertEqual(explicit.count("--port"), 1)  # user's choice kept (a warning is printed)

    def test_launcher_passes_the_port_to_the_vision_child(self):
        import importlib.util
        seen = {}
        original_start, original_find = demo.start_vision, importlib.util.find_spec
        demo.start_vision = lambda cmd: seen.setdefault("cmd", cmd) and None
        importlib.util.find_spec = lambda name, *a: object() if name == "vision.__main__" else original_find(name, *a)
        try:
            ws, udp = free_port(), free_port(socket.SOCK_DGRAM)
            rc = main(["--http-port", "0", "--vision", "--vision-args", "--model m.task", "--headless",
                       "--no-keyboard", "--duration", "0.5", "--ws-port", str(ws), "--udp-port", str(udp)])
        finally:
            demo.start_vision, importlib.util.find_spec = original_start, original_find
        self.assertEqual(rc, 0)
        cmd = seen["cmd"]
        self.assertEqual(cmd[cmd.index("--port") + 1], str(udp))


if __name__ == "__main__":
    unittest.main()
