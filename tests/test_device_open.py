import contextlib
import io
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
import audio  # Load DSP dependencies before isolating the backend in sys.modules.

from engine.__main__ import main
from engine.check import FAIL, PASS, OpenTest, Row, check_stream, main_check


class DeviceOpenTests(unittest.TestCase):
    @contextlib.contextmanager
    def backend(self, *, xrun=False, frames=2, nonfinite=False, error=None):
        result = SimpleNamespace(closed=False, output=None)
        resolver = Mock(side_effect=[4, 7])
        extras = Mock(return_value=None)
        class Stream:
            active = True
            def __init__(self, **kwargs): result.options = kwargs
            def __enter__(self):
                inp = np.array([[.9, -.5], [.8, .25]], dtype=np.float32)
                if nonfinite: inp[0,1] = np.nan
                result.output = np.ones((2,2),np.float32)
                result.options['callback'](inp,result.output,frames,None,
                                           SimpleNamespace(input_overflow=xrun,output_underflow=False))
                return self
            def __exit__(self, *args): result.closed = True
        constructor = Mock(side_effect=error) if error else Mock(side_effect=Stream)
        with patch.dict(sys.modules,{'sounddevice':SimpleNamespace(Stream=constructor)}), \
                patch('audio.stream',SimpleNamespace(resolve_device=resolver,_extra_settings=extras),create=True):
            result.constructor, result.resolver = constructor, resolver
            yield result

    def test_opt_in_opens_selected_stream_silently_and_measures_selected_channel(self):
        with self.backend() as backend:
            rows = check_stream(OpenTest(.001,in_dev='3',out_dev='5',hostapi='WASAPI',blocksize=64))
        self.assertTrue(backend.closed)
        self.assertTrue(np.all(backend.output==0))
        self.assertEqual(backend.options['device'],(4,7))
        self.assertEqual(backend.options['blocksize'],64)
        self.assertEqual(backend.options['channels'],(2,2))
        self.assertEqual(backend.resolver.call_args_list[0].args,('3','WASAPI','input'))
        self.assertEqual([row.status for row in rows],[PASS,PASS,PASS])
        self.assertIn('-6.0 dBFS',rows[-1].detail)  # input 2's -.5, not input 1's .9

    def test_xruns_or_missing_invalid_samples_fail_and_release_stream(self):
        for options in ({'xrun':True},{'frames':0},{'nonfinite':True}):
            with self.subTest(options=options):
                with self.backend(**options) as backend:
                    rows = check_stream(OpenTest(.001))
                self.assertTrue(backend.closed)
                self.assertTrue(any(row.status==FAIL for row in rows))

    def test_driver_error_is_a_failed_row(self):
        with self.backend(error=OSError('simulated busy device')):
            rows = check_stream(OpenTest(.001))
        self.assertEqual(rows[0].status,FAIL)
        self.assertIn('simulated busy device',rows[0].detail)

    def test_default_check_does_not_invoke_stream_probe(self):
        output = io.StringIO()
        with patch('engine.check.run_checks',return_value=[Row('package',PASS,'ok')]), \
                patch('engine.check.check_stream') as probe, contextlib.redirect_stdout(output):
            self.assertEqual(main(['--check']),0)
        probe.assert_not_called()
        self.assertIn('No audio was opened.',output.getvalue())

    def test_cli_passes_explicit_settings_and_rejects_unsafe_combinations_before_checks(self):
        with patch('engine.check.main_check',return_value=0) as check:
            self.assertEqual(main(['--check','--open-test','3','--hostapi','WASAPI','--blocksize','64']),0)
        options = check.call_args.kwargs['open_test']
        self.assertEqual((options.seconds,options.hostapi,options.blocksize),(3,'WASAPI',64))
        self.assertEqual((options.in_dev,options.out_dev),('Focusrite','Focusrite'))
        for args in (['--open-test','1'],['--check','--headless','--open-test','1'],
                     ['--check','--open-test','nan'],['--check','--open-test','0'],
                     ['--check','--open-test','1','--blocksize','0'],
                     ['--check','--open-test','1','--in','']):
            with self.subTest(args=args), patch('engine.check.run_checks') as checks, \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                main(args)
            self.assertEqual(raised.exception.code,2)
            checks.assert_not_called()

    def test_explicit_check_summary_reports_open_request_and_failure_exit(self):
        output = io.StringIO()
        with patch('engine.check.run_checks',return_value=[Row('package',PASS,'ok')]), \
                patch('engine.check.check_stream',return_value=[Row('audio open-test',FAIL,'driver')]), \
                contextlib.redirect_stdout(output):
            self.assertEqual(main_check(open_test=OpenTest(.001)),1)
        self.assertIn('Device-open test requested',output.getvalue())
        self.assertNotIn('No audio was opened.',output.getvalue())
