"""B20 test helper, not a demo entry point or evidence of live AI inference.

Uses the public injected-agent path. Never imports the model builder, loads
keys, reads real player memory, or calls voice. Network clients are loopback.
"""
import argparse
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from langgraph.types import Command
    from coach.budget import BudgetGuard
    from coach.feed import CoachFeed
    from coach.rig import RigClient, RigStateReader
    from coach.runner import CoachRunner
    from coach.tools import CoachTools

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--take-dir',type=Path,required=True)
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--state-port',type=int,required=True)
    parser.add_argument('--control-port',type=int,required=True)
    parser.add_argument('--ready',type=Path,required=True)
    parser.add_argument('--go',type=Path,required=True)
    parser.add_argument('--result',type=Path,required=True)
    args = parser.parse_args()
    feed = CoachFeed('offline-integration',port=0,scripted=False)
    state = RigStateReader(port=args.state_port)
    rig = RigClient(port=args.control_port)
    service = CoachTools(args.workspace,feed,rig,state)

    class FakeAgent:
        finding = None
        def invoke(self,payload,config):
            if isinstance(payload,Command):
                if payload.resume != {'decisions':[{'type':'approve'}]}:
                    raise RuntimeError('test agent resumed without the expected approval')
                service.rig_control('bypass')
                return {'messages':[]}
            report = service.get_take_report(service.current_take_id)
            self.finding = next(item for item in report['findings'] if item['type']=='hesitation')
            at = self.finding['at_ms']
            service.write_drill_card('dry-check',f'Change near {at:.0f} ms',2,
                                     'Reduce the measured hesitation',{'bypass':True})
            feed.publish(state='speaking',mood='concentrating',target='loop',
                         cue=f"Measured hesitation at {at:.1f} ms; gap {self.finding['gap_ms']:.1f} ms.")
            return {'__interrupt__':[SimpleNamespace(value={'action_requests':[
                {'name':'rig_control','args':{'control':'bypass'}}]})]}

    fake = FakeAgent()
    runner = CoachRunner(fake,service,feed,state,BudgetGuard(args.workspace/'usage.jsonl'),
                         approval_timeout_s=10)
    print('OFFLINE FAKE AGENT: synthetic take; no model/key/voice calls.',flush=True)
    try:
        feed.start()
        state.start()
        args.ready.write_text(json.dumps({'port':feed.port}))
        deadline = time.monotonic()+15
        while not args.go.exists():
            if time.monotonic()>deadline: raise TimeoutError('parent never connected')
            time.sleep(.01)
        runner.run_directory(args.take_dir,once=True)
        if fake.finding is None or len(rig.sent)!=1:
            raise RuntimeError('take processing or approved control did not complete')
        args.result.write_text(json.dumps({'finding':fake.finding,'sent':rig.sent,
                                          'mode':'deterministic injected agent; no live AI inference'}))
        return 0
    finally:
        state.stop()
        feed.stop()


if __name__=='__main__':
    raise SystemExit(main())
