"""Run the guitar coach as an independent, disposable process."""
from __future__ import annotations

import argparse
import logging
import uuid
from pathlib import Path

from .agent import build_agent, prepare_workspace
from .budget import BudgetGuard
from .feed import CoachFeed
from .memory import prepare_fixture_workspace
from .rig import RigClient, RigStateReader
from .runner import CoachRunner
from .smoke import load_key
from .tools import CoachTools


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "coach" / "workspace"
FIXTURE_WORKSPACE = ROOT / "coach" / "workspace-fixtures"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sim", action="store_true", help="attach to an already running simulator")
    parser.add_argument("--take-dir", type=Path, help="directory of completed WAV+JSON take pairs")
    parser.add_argument("--hand-log", type=Path, help="real webcam hand JSONL from vision")
    parser.add_argument("--fixtures", action="store_true", help="replay explicitly synthetic coach takes without engine")
    parser.add_argument("--auto-approve-fixtures", action="store_true",
                        help="log fixture rig actions without waiting; never valid for a live rig")
    parser.add_argument("--fixture-limit", type=int, choices=(1, 2, 3), default=3,
                        help="number of synthetic takes to replay (default: all three)")
    parser.add_argument("--feed-port", type=int, default=47803)
    parser.add_argument("--state-port", type=int, default=47801)
    parser.add_argument("--control-port", type=int, default=47800)
    args = parser.parse_args(argv)
    if args.auto_approve_fixtures and not args.fixtures:
        parser.error("--auto-approve-fixtures requires --fixtures")
    if not args.fixtures and args.take_dir is None:
        parser.error("--take-dir is required without --fixtures")

    logging.basicConfig(level=logging.INFO, format="coach: %(levelname)s %(message)s")
    load_key()
    workspace = (prepare_fixture_workspace(WORKSPACE, FIXTURE_WORKSPACE)
                 if args.fixtures else prepare_workspace(WORKSPACE))
    budget = BudgetGuard(WORKSPACE / "usage.jsonl")
    session_id = uuid.uuid4().hex
    feed = CoachFeed(session_id, port=args.feed_port, scripted=args.fixtures)
    state = RigStateReader(port=args.state_port)
    rig = RigClient(fixture_mode=args.fixtures, port=args.control_port)
    if args.fixtures:
        state.observe({"source": "synthetic_fixture", "loop": {"state": "idle"},
                       "bypass": False, "filter": {"value": 1.0}, "reverb": {"value": 0.0}})
    service = CoachTools(workspace, feed, rig, state)
    feed.start()
    if not args.fixtures:
        state.start()
    try:
        if not budget.allow_new_run():
            feed.publish(state="asleep", mood="sleepy", cue="Coach is out of credit.")
            print("Coach budget guard: no new model run.")
            return 2
        agent = build_agent(service)
        runner = CoachRunner(
            agent, service, feed, state, budget, hand_log=args.hand_log,
            fixture_mode=args.fixtures, auto_approve_fixtures=args.auto_approve_fixtures,
        )
        if args.fixtures:
            from .fixtures.generate import generate
            fixture_dir = ROOT / "coach" / "fixtures" / "generated"
            generate(fixture_dir)
            print("SYNTHETIC FIXTURES: no live guitar, webcam, engine or rig control.")
            runner.open_session()
            for name in ("before", "after", "clean")[:args.fixture_limit]:
                wav = fixture_dir / f"coach-{name}.wav"
                runner.process_take(wav)
            print(f"Fixture rig actions logged (not sent): {len(rig.sent)}")
        else:
            print(f"Coach feed ws://127.0.0.1:{feed.port}; watching {args.take_dir}")
            runner.run_directory(args.take_dir)
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        state.stop()
        feed.stop()


if __name__ == "__main__":
    raise SystemExit(main())
