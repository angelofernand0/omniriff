"""Budget admission regression tests: synthetic usage, no model or key access."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from coach.budget import BudgetGuard, estimate_upper_bound_usd


def tokens(inputs=0, outputs=0):
    return {"synthetic-model": {"input_tokens": inputs, "output_tokens": outputs}}


class BudgetAdmissionTests(unittest.TestCase):
    def setUp(self):
        # The admission logic below is exercised with round synthetic rates ($15/$75 per M) so the arithmetic
        # in these tests stays readable; real rates are covered by RealRateTests.
        for name, value in (("INPUT_USD_PER_M", 15.0), ("OUTPUT_USD_PER_M", 75.0)):
            patcher = patch(f"coach.budget.{name}", value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "usage.jsonl"

    def test_defaults_preserve_preflight_and_include_active_turn(self):
        guard = BudgetGuard(self.path)
        self.assertTrue(guard.allow_new_run())
        self.assertTrue(guard.before_model_call(tokens(100_000)))
        guard.after_model_call(tokens(100_000))
        # The review's 800k-token/$12 case is synthetic accounting, not a bill.
        self.assertEqual(estimate_upper_bound_usd(tokens(800_000)), 12)
        self.assertFalse(guard.before_model_call(tokens(800_000)))
        self.assertFalse(self.path.exists())

    def test_sequence_checks_each_call_and_refuses_at_reserve_boundary(self):
        guard = BudgetGuard(self.path, limit_usd=2, reserve_usd=.5)
        calls = 0
        while guard.before_model_call(tokens(calls * 20_000)):
            calls += 1
            guard.after_model_call(tokens(calls * 20_000))
        self.assertEqual(calls, 5)  # $1.50 completed + $0.50 reserve hits $2.
        # A post-approval resume receives the same accumulated usage, not zero.
        self.assertFalse(guard.before_model_call(tokens(calls * 20_000)))

    def test_unrecorded_usage_is_not_double_charged_by_checks(self):
        guard = BudgetGuard(self.path, limit_usd=3, reserve_usd=.5)
        usage = tokens(100_000)
        for _ in range(4):
            self.assertTrue(guard.before_model_call(usage))
            guard.after_model_call(usage)
        self.assertFalse(self.path.exists())
        guard.record("synthetic-take", usage, .1)
        self.assertEqual(guard.spent_usd(), 1.5)
        self.assertTrue(guard.before_model_call())
        guard.after_model_call()
        self.assertFalse(guard.before_model_call(usage))

    def test_recorded_prior_turn_plus_unrecorded_specialists_share_ceiling(self):
        guard = BudgetGuard(self.path, limit_usd=3, reserve_usd=.5)
        guard.record("old-synthetic-take", tokens(100_000), .1)
        active = {
            "parent": {"input_tokens": 20_000, "output_tokens": 0},
            "ears": {"input_tokens": 20_000, "output_tokens": 0},
            "eyes": {"input_tokens": 20_000, "output_tokens": 0},
        }
        self.assertTrue(guard.before_model_call(active))  # 1.5 + .9 + .5 < 3
        guard.after_model_call(active)
        active["eyes"]["output_tokens"] = 2_000  # another $.15
        self.assertFalse(guard.before_model_call(active))

    def test_parallel_calls_reserve_atomically_and_release(self):
        guard = BudgetGuard(self.path, limit_usd=2.5, reserve_usd=1)
        attempted = threading.Barrier(16)

        def call():
            admitted = guard.before_model_call(tokens())
            # Nobody releases until all contenders have attempted admission.
            attempted.wait(timeout=5)
            if admitted:
                guard.after_model_call(tokens())
            return admitted

        with ThreadPoolExecutor(max_workers=16) as pool:
            self.assertEqual(sum(pool.map(lambda _: call(), range(16))), 2)
        self.assertTrue(guard.before_model_call())
        guard.after_model_call()

    def test_refused_admission_changes_no_accounting(self):
        guard = BudgetGuard(self.path)
        self.assertFalse(guard.before_model_call(tokens(800_000)))
        self.assertFalse(self.path.exists())
        with self.assertRaises(RuntimeError):
            guard.after_model_call()
        # Rejection did not install the rejected snapshot or a reservation.
        self.assertTrue(guard.before_model_call(tokens()))
        guard.after_model_call(tokens())

    def test_preflight_does_not_leak_a_reservation(self):
        guard = BudgetGuard(self.path, limit_usd=1, reserve_usd=.5)
        for _ in range(4):
            self.assertTrue(guard.allow_new_run())
        self.assertTrue(guard.before_model_call())
        self.assertFalse(guard.before_model_call())
        self.assertFalse(guard.allow_new_run())
        guard.after_model_call()
        self.assertTrue(guard.allow_new_run())

    def test_failed_calls_release_and_stale_snapshots_do_not_refund(self):
        guard = BudgetGuard(self.path, limit_usd=2, reserve_usd=.5)
        self.assertTrue(guard.before_model_call(tokens()))
        try:
            raise RuntimeError("synthetic provider failure")
        except RuntimeError:
            pass
        finally:
            guard.after_model_call(tokens(100_000))
        self.assertFalse(guard.before_model_call(tokens()))
        # Even an older final snapshot must preserve the observed cost.
        guard.record("synthetic-take", tokens(), .1)
        self.assertEqual(BudgetGuard(self.path).spent_usd(), 1.5)

    def test_record_requires_finished_calls_and_reset_follows_durable_write(self):
        guard = BudgetGuard(self.path, limit_usd=2, reserve_usd=.5)
        self.assertTrue(guard.before_model_call())
        with self.assertRaises(RuntimeError):
            guard.record("synthetic-take", tokens(), 0)
        guard.after_model_call(tokens(100_000))
        with patch.object(Path, "open", side_effect=OSError("synthetic disk failure")):
            with self.assertRaises(OSError):
                guard.record("synthetic-take", tokens(), 0)
        self.assertFalse(guard.before_model_call(tokens()))
        with self.assertRaises(RuntimeError):
            guard.after_model_call()

    def test_restart_keeps_persisted_spend_and_configurable_ceiling(self):
        BudgetGuard(self.path).record("synthetic-take", tokens(100_000), .1)
        guard = BudgetGuard(self.path, limit_usd=2, reserve_usd=.5)
        self.assertFalse(guard.before_model_call())
        self.assertFalse(guard.allow_new_run())
        self.assertTrue(BudgetGuard(self.path, limit_usd=3, reserve_usd=.5).allow_new_run())

    def test_corrupt_or_unreadable_ledger_refuses_cleanly(self):
        for line in ("{", "{}", "[]", '{"estimated_upper_bound_usd":NaN}',
                     '{"estimated_upper_bound_usd":Infinity}',
                     '{"estimated_upper_bound_usd":-1}',
                     '{"estimated_upper_bound_usd":true}',
                     '{"estimated_upper_bound_usd":"0"}'):
            with self.subTest(line=line):
                self.path.write_text(line + "\n")
                self.assertFalse(BudgetGuard(self.path).before_model_call())
                self.assertFalse(BudgetGuard(self.path).allow_new_run())
        self.path.unlink()
        self.path.mkdir()
        self.assertFalse(BudgetGuard(self.path).before_model_call())
        with patch.object(Path, "open", side_effect=PermissionError("synthetic denial")):
            self.assertFalse(BudgetGuard(self.path).before_model_call())

    def test_invalid_active_usage_cannot_refund_or_hide_spend(self):
        guard = BudgetGuard(self.path)
        for usage in ([], "bad", {"m": None}, {"m": {}}, {"m": {"total_tokens": 800_000}},
                      {"m": {"input_tokens": 0}}, tokens(-1), tokens(0, -1),
                      tokens(True), tokens(1.5), tokens("100"), tokens(float("inf"))):
            with self.subTest(usage=usage):
                self.assertFalse(guard.before_model_call(usage))
                with self.assertRaises(ValueError):
                    guard.record("synthetic-invalid", usage, 0)
        self.assertFalse(self.path.exists())

    def test_invalid_configuration_fails_early(self):
        for bad in (-1, float("nan"), float("inf"), True, "8"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    BudgetGuard(self.path, limit_usd=bad)
                with self.assertRaises(ValueError):
                    BudgetGuard(self.path, reserve_usd=bad)
        self.assertFalse(BudgetGuard(self.path, limit_usd=0, reserve_usd=0).allow_new_run())

    def test_ledger_keeps_existing_shape(self):
        guard = BudgetGuard(self.path)
        entry = guard.record("synthetic-take", tokens(10, 2), .123)
        self.assertEqual(json.loads(self.path.read_text()), entry)
        self.assertEqual(entry["estimated_upper_bound_usd"], .0003)
        self.assertEqual(entry["elapsed_s"], .12)


if __name__ == "__main__":
    unittest.main()


class RealRateTests(unittest.TestCase):
    def test_estimate_uses_sonnet_rates_and_cheap_cache_reads(self):
        usage = {"m": {"input_tokens": 1_000_000, "output_tokens": 1_000_000,
                       "input_token_details": {"cache_read": 800_000}}}
        # 200k uncached * $2 + 800k cached * $0.10 + 1M out * $10 per M
        self.assertAlmostEqual(estimate_upper_bound_usd(usage), 0.4 + 0.08 + 10.0, places=6)

    def test_a_typical_live_take_fits_the_default_cap_many_times(self):
        take = {"m": {"input_tokens": 100_000, "output_tokens": 2_500,
                      "input_token_details": {"cache_read": 80_000}}}
        self.assertLess(estimate_upper_bound_usd(take), 0.1)
