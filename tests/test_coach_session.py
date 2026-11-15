"""Practice-card data comes from the plan and judgeable measured takes only."""
import unittest

from coach.feed import CoachFeed, VALIDATOR
from coach.session import PracticeSession


class PracticeSessionTests(unittest.TestCase):
    def test_plan_drill_and_measured_history_validate(self):
        session = PracticeSession(last_time="Last time, your longest gap was 900 ms.")
        session.plan(goal="Clean the chord change", next_step="Full pattern at tempo",
                     drill_step=2, drill_count=3, attempt_count=3)
        session.set_drill_card({"title": "Keep the hand moving", "skill": "keep-the-hand-moving",
                                "pass_rule": "longest gap under 700 ms"})
        self.assertFalse(session.record_take({"take_id": "silent", "judgeable": False,
                                              "intervals_ms": []}))
        self.assertTrue(session.record_take({"take_id": "first", "judgeable": True,
                                             "intervals_ms": [500, 900, 500]}))
        self.assertFalse(session.record_take({"take_id": "first", "judgeable": True,
                                              "intervals_ms": [500, 200, 500]}))
        self.assertTrue(session.record_take({"take_id": "second", "judgeable": True,
                                             "intervals_ms": [500, 620, 500]}))
        snapshot = session.snapshot()
        self.assertEqual(snapshot["drill"]["step"], 2)
        self.assertEqual(snapshot["drill"]["of"], 3)
        self.assertEqual(snapshot["attempt"], {"n": 2, "of": 3})
        self.assertEqual(snapshot["metric"]["history"], [400.0, 120.0])  # late vs the 500 ms beat
        self.assertEqual(snapshot["metric"]["target"], 700.0)
        self.assertEqual(snapshot["next"], "Full pattern at tempo")
        feed = CoachFeed("session-test")
        self.assertTrue(VALIDATOR.is_valid(feed.publish(session=snapshot)))

    def test_unknown_targets_stay_null_and_history_is_bounded(self):
        session = PracticeSession()
        session.set_drill_card({"title": "Dry check", "skill": "dry-check",
                                "pass_rule": "Sound clean and even"})
        self.assertIsNone(session.snapshot()["metric"])
        self.assertIsNone(session.snapshot()["attempt"])
        self.assertFalse(session.record_take({"take_id": "bad", "judgeable": True,
                                              "intervals_ms": [float("nan")]}))
        for n in range(14):
            self.assertTrue(session.record_take({"take_id": f"take-{n}", "judgeable": True,
                                                 "intervals_ms": [500, 500, 500 + n + 1.0]}))
        session.set_drill_card({"title": "Dry check", "skill": "dry-check",
                                "pass_rule": "worst gap under 150 ms"})
        snapshot = session.snapshot()
        self.assertEqual(snapshot["metric"]["history"], [float(n) for n in range(3, 15)])
        self.assertTrue(VALIDATOR.is_valid(CoachFeed("session-test").publish(session=snapshot)))


if __name__ == "__main__":
    unittest.main()
