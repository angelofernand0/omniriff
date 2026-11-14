"""Run the hardware measurements in order and write results.json + results.md.

Every step reports its own status. A skipped or failed step is written as
"not measured": this tool never fills in a default, target or estimate.
The step functions take their hardware dependencies as arguments so tests can
run without audio devices.
"""
from __future__ import annotations

import json
import platform
import threading
import time
from argparse import Namespace
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

NOT_MEASURED = "not measured"


def _step(name, fn, *args, **kwargs) -> dict:
    started = time.monotonic()
    try:
        data = fn(*args, **kwargs)
        status = "pass"
        if isinstance(data, dict) and data.get("_status"):
            status = data.pop("_status")
        return dict(step=name, status=status, seconds=round(time.monotonic() - started, 2), data=data)
    except (Exception, SystemExit) as exc:  # each step fails on its own (resolve_device exits on a missing device)
        return dict(step=name, status="fail", seconds=round(time.monotonic() - started, 2),
                    error=f"{type(exc).__name__}: {exc}"[:300])


def step_check(a, run_checks=None) -> dict:
    if run_checks is None:
        from engine.check import run_checks
    rows = [asdict(r) for r in run_checks(input_channel=a.input_channel)]
    failed = [r["check"] for r in rows if r["status"] == "FAIL"]
    return dict(rows=rows, failed=failed, _status="fail" if failed else "pass")


def step_latency(a, loopback=None) -> dict:
    if loopback is None:
        from tools.latency.__main__ import loopback
    result = loopback(Namespace(in_dev=a.in_dev, out_dev=a.out_dev, hostapi=a.hostapi,
                                input_channel=a.input_channel, samplerate=a.samplerate,
                                blocksize=a.blocksize, latency=a.latency, exclusive=a.exclusive,
                                clicks=a.clicks, interval=0.5))
    if result.get("warning") or not result.get("detected"):
        result["_status"] = "fail"
    return result


def step_cpu(a, time_engine=None) -> dict:
    if time_engine is None:
        from tools.latency.measure import time_engine
    return dict(results=time_engine(blocksizes=(a.blocksize,), samplerate=a.samplerate),
                machine=platform.processor() or platform.machine())


def step_soak(a, run_live=None, resolve=None, engine_factory=None, sleep=time.sleep) -> dict:
    """Play through the real engine for a.soak_minutes and read its xrun counters."""
    if run_live is None or resolve is None:
        from audio import stream
        run_live = run_live or stream.run_live
        resolve = resolve or stream.resolve_device
    if engine_factory is None:
        from audio import Engine, EngineConfig
        engine_factory = lambda: Engine(EngineConfig(samplerate=a.samplerate))
    engine = engine_factory()
    in_dev, out_dev = resolve(a.in_dev, a.hostapi, "input"), resolve(a.out_dev, a.hostapi, "output")
    stop, info, errors = threading.Event(), {}, []

    def target():
        try:
            info.update(run_live(engine, in_dev, out_dev, a.input_channel, 2, a.blocksize,
                                 a.latency, a.exclusive, stop))
        except (Exception, SystemExit) as exc:
            errors.append(f"{type(exc).__name__}: {exc}"[:300])
            stop.set()

    worker = threading.Thread(target=target, name="measure-soak", daemon=True)
    worker.start()
    deadline = time.monotonic() + a.soak_minutes * 60
    while not stop.is_set() and time.monotonic() < deadline:
        sleep(0.5)
    stop.set()
    worker.join(5)
    if errors:
        raise RuntimeError(errors[0])
    snap = engine.snapshot()
    info = {k: (list(v) if isinstance(v, tuple) else v) for k, v in info.items()}
    return dict(minutes=a.soak_minutes, xruns=snap["xruns"], clipped_samples=snap["clipped_samples"],
                blocks=snap["blocks"], stream=info)


def step_take(a, out_dir: Path, record=None, resolve=None, analyze=None) -> dict:
    """Record a take with the guitar (no playback) and run Ears on it."""
    from audio.takes import write_take
    if record is None or resolve is None:
        from audio import stream
        record = record or stream.record_input
        resolve = resolve or stream.resolve_device
    if analyze is None:
        from tools.ears import analyze_take as analyze
    path = out_dir / "take.wav"
    started = time.time() * 1000.0
    mono = record(resolve(a.in_dev, a.hostapi, "input"), a.input_channel, a.take_seconds, a.samplerate)
    write_take(path, mono, a.samplerate, started, source="record")
    report = analyze(path)
    report = report if isinstance(report, dict) else json.loads(report.to_json())
    (out_dir / "take-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return dict(take=str(path), strum_count=report["strum_count"], judgeable=report["judgeable"],
                summary=report["summary"], findings=len(report["findings"]))


def settings(a) -> dict:
    return dict(input=a.in_dev, output=a.out_dev, hostapi=a.hostapi, input_channel=a.input_channel,
                samplerate=a.samplerate, blocksize=a.blocksize, latency=a.latency, exclusive=a.exclusive)


def get(results: dict, step: str):
    r = results["steps"].get(step)
    return r["data"] if r and r["status"] == "pass" else None


def markdown(results: dict) -> str:
    s = results["settings"]
    where = f"{s['blocksize']}-sample blocks, {s['hostapi'] or 'default host API'}" + (", exclusive" if s["exclusive"] else "")
    lat, soak, cpu, take = (get(results, k) for k in ("latency", "soak", "cpu", "take"))
    lines = [f"# Measured results — {results['started_utc']}", "",
             f"Command: `{results['command']}`", f"Machine: {results['machine']}", "",
             "Paste into docs/DEVPOST.md 'Measured results' (only rows that say measured):", ""]
    if lat:
        lines.append(f"- Guitar-to-output latency: {lat['median_ms']} ms median (spread {lat['min_ms']}–{lat['max_ms']} ms) "
                     f"at {where}, via `tools.latency` loopback, {lat['detected']}/{lat['clicks']} clicks detected")
    else:
        lines.append(f"- Guitar-to-output latency: {NOT_MEASURED}")
    if soak:
        lines.append(f"- Dropouts over a {soak['minutes']:g}-minute play test: {soak['xruns']} xruns, "
                     f"{soak['clipped_samples']} clipped samples ({soak['blocks']} blocks, {where})")
    else:
        lines.append(f"- Dropouts over a play test: {NOT_MEASURED}")
    if cpu and cpu.get("results"):
        r = cpu["results"][0]
        lines.append(f"- Engine CPU per {r.get('blocksize', s['blocksize'])}-frame block: {r.get('mean_ms')} ms mean "
                     f"(p99 {r.get('p99_ms')} ms; {r.get('load_pct_mean')}% of the {r.get('budget_ms')} ms real-time budget) "
                     f"on {cpu['machine']}")
    else:
        lines.append(f"- Engine CPU per block: {NOT_MEASURED}")
    if take:
        lines.append(f"- Ears on a real take: {take['strum_count']} strums detected; {take['summary']} "
                     "(compare by ear/eye with what was played before quoting)")
    else:
        lines.append(f"- Ears on a real take: {NOT_MEASURED}")
    lines += ["", "## Steps", ""]
    for name, r in results["steps"].items():
        lines.append(f"- {name}: **{r['status']}**" + (f" — {r['error']}" if r.get("error") else ""))
    if results["steps"].get("check", {}).get("data", {}).get("failed"):
        lines.append(f"  - preflight FAIL rows: {', '.join(results['steps']['check']['data']['failed'])}")
    return "\n".join(lines) + "\n"


def run(a, argv, steps=None, now=None) -> Path:
    """Run every selected step and write the results folder. Refuses to overwrite."""
    started = now or datetime.now(timezone.utc)
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(a.out) / stamp
    out_dir.mkdir(parents=True, exist_ok=False)
    steps = steps or {}
    plan = [("check", not a.skip_check, lambda: step_check(a, **steps.get("check", {}))),
            ("latency", not a.skip_latency, lambda: step_latency(a, **steps.get("latency", {}))),
            ("cpu", not a.skip_cpu, lambda: step_cpu(a, **steps.get("cpu", {}))),
            ("soak", a.soak_minutes > 0, lambda: step_soak(a, **steps.get("soak", {}))),
            ("take", a.take_seconds > 0, lambda: step_take(a, out_dir, **steps.get("take", {})))]
    results = dict(version=1, started_utc=started.isoformat(timespec="seconds"),
                   command="python -m tools.measure " + " ".join(argv),
                   machine=f"{platform.system()} {platform.release()} / {platform.processor() or platform.machine()}",
                   settings=settings(a), steps={})
    for name, enabled, fn in plan:
        if not enabled:
            results["steps"][name] = dict(step=name, status="skipped")
            continue
        print(f"measure: {name} ...", flush=True)
        results["steps"][name] = _step(name, fn)
        print(f"measure: {name} {results['steps'][name]['status']}", flush=True)
    (out_dir / "results.json").write_text(json.dumps(results, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (out_dir / "results.md").write_text(markdown(results), encoding="utf-8")
    return out_dir
