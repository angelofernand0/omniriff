"""tools.sim.control: the /sim/... endpoints behind the dashboard's ?manual=1 flag (simulated input only)."""
import asyncio
import unittest

from tools.sim.control import SimControl
from tools.sim.hand import HandState


class _Guitar:
    level = 0.28


class SimControlTest(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.view, self.guitar = HandState(), _Guitar()
        # port 9 (discard): nothing listens; UDP sends are fire and forget
        self.c = SimControl(self.loop, 9, self.view, self.guitar, 0.28, demo_on=False)

    def tearDown(self):
        self.c.pedal.close(); self.c.vision.close(); self.loop.close()

    def test_guitar_mutes_and_restores(self):
        self.assertFalse(self.c.handle('/sim/guitar', {'on': '0'})['guitar'])
        self.assertEqual(self.guitar.level, 0.0)
        self.assertTrue(self.c.handle('/sim/guitar', {'on': '1'})['guitar'])
        self.assertEqual(self.guitar.level, 0.28)

    def test_hand_in_frame_then_pinch_then_release(self):
        s = self.c.handle('/sim/hand', {'present': '1', 'engaged': '0'})
        self.assertTrue(s['hand']['present']); self.assertFalse(s['hand']['engaged'])
        s = self.c.handle('/sim/hand', {'present': '1', 'engaged': '1', 'control': 'reverb', 'value': '0.7'})
        self.assertTrue(s['hand']['engaged'])
        self.assertEqual((self.view.control, self.view.value), ('reverb', 0.7))
        s = self.c.handle('/sim/hand', {'present': '1', 'engaged': '0'})
        self.assertTrue(s['hand']['present']); self.assertFalse(s['hand']['engaged'])

    def test_value_is_clamped_and_hand_out_clears_pinch(self):
        self.c.handle('/sim/hand', {'present': '1', 'engaged': '1', 'control': 'filter', 'value': '9'})
        self.assertEqual(self.view.value, 1.0)
        s = self.c.handle('/sim/hand', {'present': '0', 'engaged': '1'})
        self.assertFalse(s['hand']['present']); self.assertFalse(s['hand']['engaged'])

    def test_auto_off_is_reported_and_unknown_path_is_an_error(self):
        self.assertFalse(self.c.handle('/sim/auto', {'on': '0'})['auto'])
        self.assertIn('error', self.c.handle('/sim/nope', {}))


if __name__ == '__main__':
    unittest.main()
