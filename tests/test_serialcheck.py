import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools.serialcheck import __main__ as serialcheck


class FakePort:
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.closed = False

    def read_until(self, *, size):
        chunk = next(self.chunks, KeyboardInterrupt())
        if isinstance(chunk, BaseException):
            raise chunk
        assert len(chunk) <= size
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True


class SerialCheckTests(unittest.TestCase):
    def test_live_actions_and_host_timing(self):
        port = FakePort([
            b'{"seq":0,"type":"action",',
            b"",
            b'"control":"loop"}\n',
            b'{"seq":1,"type":"action","control":"practice"}\n',
            b'{"seq":2,"type":"action","control":"bypass"}\n',
        ])
        constructor = Mock(return_value=port)
        ticks = iter([10.0, 10.125, 11.375, 11.625])
        monitor = serialcheck.monitor
        output = io.StringIO()
        with (
            patch.dict(sys.modules, serial=SimpleNamespace(Serial=constructor)),
            patch.object(serialcheck, "monitor", side_effect=lambda port: monitor(port, lambda: next(ticks))),
            redirect_stdout(output),
        ):
            self.assertEqual(serialcheck.main(["--port", "COM3"]), 0)
        constructor.assert_called_once_with("COM3", 115200, timeout=0.25)
        self.assertTrue(port.closed)
        self.assertIn("125.0 ms] TAP -> loop  seq=0  (first event)", output.getvalue())
        self.assertIn("1375.0 ms] HOLD -> practice  seq=1  (gap 1250.0 ms)", output.getvalue())
        self.assertIn("1625.0 ms] PRESS -> bypass  seq=2  (gap 250.0 ms)", output.getvalue())

    def test_bad_lines_and_oversize_frame_do_not_hide_next_event(self):
        valid = b'{"seq":0,"type":"action","control":"loop"}\n'
        port = FakePort([
            b'not JSON\n',
            b'{"seq":true,"type":"action","control":"loop"}\n',
            b'{"seq":0,"type":"action","control":[]}\n',
            b'x' * 256,
            b'x',
            b'',
            valid,  # Tail of the oversize frame, still discarded through LF.
            valid,
        ])
        events = serialcheck.read_events(port)
        self.assertEqual([next(events) for _ in range(4)], [None] * 4)
        self.assertEqual(next(events), {"seq": 0, "type": "action", "control": "loop"})

    def test_disconnect_closes_port_and_reports_error(self):
        port = FakePort([OSError("device disconnected")])
        errors = io.StringIO()
        with (
            patch.dict(sys.modules, serial=SimpleNamespace(Serial=Mock(return_value=port))),
            redirect_stdout(io.StringIO()),
            redirect_stderr(errors),
        ):
            self.assertEqual(serialcheck.main(["--port", "COM4"]), 1)
        self.assertTrue(port.closed)
        self.assertIn("COM4: device disconnected", errors.getvalue())
