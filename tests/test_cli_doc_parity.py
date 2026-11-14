"""Tests verifying CLI flag parity against documentation runbooks and checklists.

Ensures that every command line flag documented for humans to type tonight in:
- docs/DEMO.md (demo runbook & hardware bring-up sequence)
- vision/README.md (gesture control, morning hardware checklist, and opt-in --strum-guard)
- engine/README.md (host runtime, Windows 11 Scarlett Solo quickstart, coach launch)
- coach/README.md (practice coach execution & fixture verification)

actually exists in the matching module's `--help` output (via subprocess).
Skips cleanly if optional dependencies (e.g., deepagents, mediapipe, sounddevice)
are missing from the current Python environment.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run_cli_help(module: str, timeout: float = 15.0) -> tuple[set[str] | None, str | None]:
    """Execute `python -m <module> --help` as a subprocess.

    Returns:
        (flags_set, None) if successful.
        (None, skip_reason) if an optional dependency is missing.
    Raises:
        AssertionError on unexpected failure.
    """
    proc = subprocess.run(
        [sys.executable, "-m", module, "--help"],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(ROOT),
    )
    if proc.returncode != 0:
        err = proc.stderr.strip()
        if "ModuleNotFoundError" in err or "ImportError" in err:
            last_line = err.splitlines()[-1] if err.splitlines() else err
            return None, f"missing optional dependency ({last_line})"
        raise AssertionError(
            f"Command '{sys.executable} -m {module} --help' failed with code {proc.returncode}:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    flags = set(re.findall(r"(?<![a-zA-Z0-9_-])--[a-zA-Z0-9-]+", proc.stdout))
    return flags, None


class CliDocParityTests(unittest.TestCase):
    """Assert all CLI flags humans are instructed to type exist in --help."""

    def test_engine_demo_cli_flags(self):
        """flags for python -m engine.demo in docs/DEMO.md & engine/README.md."""
        flags, skip_reason = run_cli_help("engine.demo")
        if flags is None:
            self.skipTest(f"python -m engine.demo skipped: {skip_reason}")

        # docs/DEMO.md §2: python -m engine.demo --open --vision --vision-args "..."
        # docs/DEMO.md §3: --coach --hand-log runs/hand.jsonl
        # engine/README.md §2: --http-port, --coach-args
        expected = {
            "--open",
            "--vision",
            "--vision-args",
            "--coach",
            "--coach-args",
            "--hand-log",
            "--http-port",
        }
        missing = expected - flags
        self.assertFalse(missing, f"python -m engine.demo --help is missing documented flags: {missing}")

    def test_vision_cli_flags(self):
        """flags for python -m vision in docs/DEMO.md, vision/README.md & checklists."""
        flags, skip_reason = run_cli_help("vision")
        if flags is None:
            self.skipTest(f"python -m vision skipped: {skip_reason}")

        # docs/DEMO.md §2: --model, --calibration, --calibrate, --scene, --setlist
        # vision/README.md: --video, --dry-run, --no-overlay, --control, --relative,
        #                   --max-hand-jump, --port, --hand-log, --strum-hand,
        #                   --strum-guard, --metrics-json, --scene-file,
        #                   --no-hand-view, --hand-view-port, --record-take
        expected = {
            "--model",
            "--calibration",
            "--calibrate",
            "--relative",
            "--strum-guard",
            "--dry-run",
            "--video",
            "--no-overlay",
            "--control",
            "--scene",
            "--scene-file",
            "--setlist",
            "--metrics-json",
            "--hand-log",
            "--strum-hand",
            "--no-hand-view",
            "--hand-view-port",
            "--max-hand-jump",
            "--record-take",
            "--port",
        }
        missing = expected - flags
        self.assertFalse(missing, f"python -m vision --help is missing documented flags: {missing}")

    def test_vision_strum_guard_checklist_parity(self):
        """specifically verify the --strum-guard checklist invocation from PR #120."""
        flags, skip_reason = run_cli_help("vision")
        if flags is None:
            self.skipTest(f"python -m vision skipped: {skip_reason}")

        # Human checklist tonight:
        # python -m vision --model models/hand_landmarker.task --relative --strum-guard
        self.assertIn("--model", flags)
        self.assertIn("--relative", flags)
        self.assertIn("--strum-guard", flags)

    def test_coach_cli_flags_subprocess(self):
        """flags for python -m coach in docs/DEMO.md, engine/README.md & coach/README.md."""
        flags, skip_reason = run_cli_help("coach")
        if flags is None:
            self.skipTest(f"python -m coach skipped: {skip_reason}")

        # Documented flags across runbooks:
        expected = {
            "--take-dir",
            "--hand-log",
            "--fixtures",
            "--auto-approve-fixtures",
            "--fixture-limit",
            "--sim",
            "--feed-port",
            "--state-port",
            "--control-port",
        }
        missing = expected - flags
        self.assertFalse(missing, f"python -m coach --help is missing documented flags: {missing}")

    def test_coach_argparse_static_definitions(self):
        """statically verify coach/__main__.py defines all flags even when deps are absent."""
        main_path = ROOT / "coach" / "__main__.py"
        self.assertTrue(main_path.exists(), "coach/__main__.py must exist")
        tree = ast.parse(main_path.read_text())
        static_flags = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and hasattr(node.func, "attr") and node.func.attr == "add_argument":
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("--"):
                        static_flags.add(arg.value)

        expected = {
            "--take-dir",
            "--hand-log",
            "--fixtures",
            "--auto-approve-fixtures",
            "--fixture-limit",
            "--sim",
            "--feed-port",
            "--state-port",
            "--control-port",
        }
        missing = expected - static_flags
        self.assertFalse(missing, f"coach/__main__.py is missing argument definitions: {missing}")

    def test_engine_cli_flags(self):
        """flags for python -m engine in docs/DEMO.md & engine/README.md."""
        flags, skip_reason = run_cli_help("engine")
        if flags is None:
            self.skipTest(f"python -m engine skipped: {skip_reason}")

        # docs/DEMO.md §1 & engine/README.md quickstart:
        expected = {
            "--check",
            "--open-test",
            "--in",
            "--out",
            "--hostapi",
            "--input-channel",
            "--out-channels",
            "--samplerate",
            "--blocksize",
            "--serial-port",
            "--replay",
            "--headless",
            "--no-keyboard",
            "--duration",
            "--take-dir",
            "--session-log",
            "--exclusive",
            "--udp-port",
            "--ws-port",
        }
        missing = expected - flags
        self.assertFalse(missing, f"python -m engine --help is missing documented flags: {missing}")

    def test_audio_cli_flags(self):
        """flags for python -m audio in docs/DEMO.md §1 & engine/README.md."""
        flags, skip_reason = run_cli_help("audio")
        if flags is None:
            self.skipTest(f"python -m audio skipped: {skip_reason}")

        expected = {
            "--list-devices",
            "--level-check",
            "--in",
            "--hostapi",
            "--input-channel",
        }
        missing = expected - flags
        self.assertFalse(missing, f"python -m audio --help is missing documented flags: {missing}")

    def test_doc_runbook_commands_flags_are_valid(self):
        """scan docs/*.md and ensure any flags in python -m <module> commands are valid."""
        doc_files = [
            ROOT / "docs" / "DEMO.md",
            ROOT / "docs" / "QA.md",
            ROOT / "vision" / "README.md",
            ROOT / "engine" / "README.md",
            ROOT / "coach" / "README.md",
        ]

        # Cache CLI help flags
        cli_help = {}
        for mod in ("engine.demo", "vision", "engine", "coach", "audio"):
            flags, skip = run_cli_help(mod)
            cli_help[mod] = flags

        cmd_re = re.compile(
            r"(?:python3?|\.venv[\\/a-zA-Z0-9_.-]*python(?:\.exe)?)\s+-m\s+([a-zA-Z0-9_.]+)(.*?)(?:[\r\n`#<|]|$)"
        )

        for doc_path in doc_files:
            if not doc_path.exists():
                continue
            for line_no, line in enumerate(doc_path.read_text().splitlines(), start=1):
                line = line.strip()
                for match in cmd_re.finditer(line):
                    mod, rest = match.groups()
                    if mod not in cli_help or cli_help[mod] is None:
                        continue

                    # engine.demo forwards remaining arguments to engine, so allow both
                    valid_flags = set(cli_help[mod])
                    if mod == "engine.demo" and cli_help.get("engine") is not None:
                        valid_flags |= cli_help["engine"]

                    # If rest has quoted args like --vision-args "...", ignore flags inside quotes
                    clean_rest = re.sub(r'"[^"]*"', "", rest)
                    clean_rest = re.sub(r"'[^']*'", "", clean_rest)

                    used_flags = re.findall(r"(?<![a-zA-Z0-9_-])--[a-zA-Z0-9-]+", clean_rest)
                    for flag in used_flags:
                        self.assertIn(
                            flag,
                            valid_flags,
                            f"{doc_path.relative_to(ROOT)}:{line_no} documents unknown flag '{flag}' "
                            f"for 'python -m {mod}'",
                        )


if __name__ == "__main__":
    unittest.main()
