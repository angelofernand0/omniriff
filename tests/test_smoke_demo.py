import unittest

from scripts.smoke_demo import preflight_ok, run_python


class SmokeDemoTests(unittest.TestCase):
    def test_preflight_does_not_hide_missing_packages_or_port_failures(self):
        self.assertTrue(preflight_ok('FAIL  audio Focusrite device  not found\n', 1))
        self.assertTrue(preflight_ok('PASS  package numpy  installed\n', 0))
        self.assertFalse(preflight_ok('FAIL  package numpy  missing\n', 1))
        self.assertFalse(preflight_ok('FAIL  port TCP 8080  in use\n', 1))
        self.assertFalse(preflight_ok('Traceback: broken preflight', 1))
        self.assertFalse(preflight_ok('', 0))
        self.assertFalse(preflight_ok('FAIL  audio Focusrite device  not found', 2))

    def test_failed_or_stalled_child_is_not_reported_as_success(self):
        with self.assertRaisesRegex(RuntimeError, 'exit 7'):
            run_python(['-c', 'raise SystemExit(7)'])
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            run_python(['-c', 'import time; time.sleep(10)'], timeout=.1)
