"""Tests verifying CLI flag parity against documentation runbooks and Windows scripts.

Dynamically extracts `python -m <module> ... --flag` commands from:
- Documentation code blocks (docs/DEMO.md, vision/README.md, engine/README.md, coach/README.md, docs/QA.md)
- Windows PowerShell bring-up scripts (scripts/windows/setup.ps1, start-demo.ps1)

Skips flags nested inside quoted arguments (--vision-args, --coach-args), and asserts
that every extracted flag exists in the matching module's `--help` output.

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

DOC_FILES = [
    ROOT / "README.md",
    ROOT / "docs" / "DEMO.md",
    ROOT / "docs" / "QA.md",
    ROOT / "vision" / "README.md",
    ROOT / "vision" / "REHEARSAL.md",
    ROOT / "vision" / "EVIDENCE.md",
    ROOT / "vision" / "SESSION-EVIDENCE.md",
    ROOT / "vision" / "soundcheck" / "README.md",
    ROOT / "engine" / "README.md",
    ROOT / "coach" / "README.md",
    ROOT / "tools" / "ears" / "README.md",
    ROOT / "tools" / "sim" / "README.md",
    ROOT / "tools" / "virtual_guitar" / "README.md",
    ROOT / "tools" / "tone_match" / "README.md",
    ROOT / "tools" / "latency" / "README.md",
    ROOT / "audio" / "README.md",
]

PS1_DIR = ROOT / "scripts" / "windows"


def extract_commands_from_file(doc_path: Path) -> list[str]:
    """Extract command strings from markdown fenced blocks and inline code spans."""
    text = doc_path.read_text()
    commands: list[str] = []

    # 1. Fenced code blocks: ```[lang]\n...\n```
    for m in re.finditer(r"```[^\n]*\n(.*?)```", text, re.DOTALL):
        block = m.group(1)
        cur = ""
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if cur:
                cur += " " + line
            else:
                cur = line
            if cur.endswith("\\"):
                cur = cur[:-1].strip()
            else:
                commands.append(cur)
                cur = ""
        if cur:
            commands.append(cur)

    # 2. Inline code spans: `...`
    for m in re.finditer(r"(?<!`)`([^`\n]+)`(?!`)", text):
        span = m.group(1).strip()
        commands.append(span)

    return commands


def strip_nested_args(s: str) -> str:
    """Skip flags inside quoted arguments such as --vision-args or --coach-args."""
    # Retain the parent flag (--vision-args / --coach-args) but strip the nested quoted argument
    s = re.sub(r"(--(?:vision-args|coach-args))\s+(\"[^\"]*\"|\x27[^\x27]*\x27)", r"\1", s)
    # Remove any remaining quoted strings
    s = re.sub(r"\"[^\"]*\"", "", s)
    s = re.sub(r"\x27[^\x27]*\x27", "", s)
    return s


def extract_doc_command_flags(doc_files: list[Path] | None = None) -> dict[str, set[str]]:
    """Extract all `python -m <module> ... --flag` invocations across docs.

    Returns:
        Mapping of module name to the set of `--flag` options used in documentation.
    """
    if doc_files is None:
        doc_files = DOC_FILES

    cmd_re = re.compile(
        r"(?:python3?|\.venv[\\/a-zA-Z0-9_.-]*python(?:\.exe)?)\s+-m\s+([a-zA-Z0-9_.]+)(.*?)(?:$|[#])"
    )
    doc_flags: dict[str, set[str]] = {}

    for d in doc_files:
        if not d.exists():
            continue
        for cmd in extract_commands_from_file(d):
            for m in cmd_re.finditer(cmd):
                mod, rest = m.groups()
                cleaned = strip_nested_args(rest)
                flags = set(re.findall(r"(?<![a-zA-Z0-9_-])--[a-zA-Z0-9-]+", cleaned))
                if flags:
                    doc_flags.setdefault(mod, set()).update(flags)

    return doc_flags


def extract_ps1_command_flags(ps1_path: Path) -> dict[str, set[str]]:
    """Extract `python -m <module> ... --flag` commands from a Windows PowerShell script (.ps1).

    Handles both direct invocations (`& $venvPython -m <mod> <flags...>`)
    and array-based invocations (`$demoArgs = @('-m', '<mod>', ...)`).
    Joins PowerShell line continuations (`).
    Strips flags nested inside quoted arguments (--vision-args, --coach-args).
    """
    if not ps1_path.exists():
        return {}

    text = ps1_path.read_text()
    results: dict[str, set[str]] = {}

    # Handle line continuations (PowerShell uses backtick ` at line end)
    lines = text.splitlines()
    joined_lines = []
    cur = ""
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if cur:
            cur += " " + line
        else:
            cur = line
        if cur.endswith("`"):
            cur = cur[:-1].strip()
        else:
            joined_lines.append(cur)
            cur = ""
    if cur:
        joined_lines.append(cur)

    joined_text = "\n".join(joined_lines)

    # 1. Direct commands: & $venvPython -m <mod> <args...> or python -m <mod> <args...>
    cmd_re = re.compile(
        r"(?:&|\b)\s*(?:\$[a-zA-Z0-9_]+|py(?:thon)?(?:3)?(?:\s+-[0-9.]+)?)\s+-m\s+([a-zA-Z0-9_.]+)(.*?)(?:$|[\r\n#])"
    )
    for m in cmd_re.finditer(joined_text):
        mod, rest = m.groups()
        cleaned = strip_nested_args(rest)
        flags = set(re.findall(r"(?<![a-zA-Z0-9_-])--[a-zA-Z0-9-]+", cleaned))
        if flags:
            results.setdefault(mod, set()).update(flags)

    # 2. Array construction: $var = @("-m", "<mod>", ...) and $var += ...
    var_matches = re.finditer(
        r"\$([a-zA-Z0-9_]+)\s*=\s*@\(\s*[\x27\"]-m[\x27\"]\s*,\s*[\x27\"]([a-zA-Z0-9_.]+)[\x27\"](.*?)\)",
        joined_text,
        re.DOTALL,
    )
    for vm in var_matches:
        var_name, mod, init_rest = vm.groups()
        all_elements = [init_rest]
        append_re = re.compile(rf"\${var_name}\s*\+=\s*(.*?)(?:$|[\r\n])")
        for am in append_re.finditer(joined_text):
            all_elements.append(am.group(1))

        combined = " ".join(all_elements)
        literals = re.findall(r"[\x27\"]([^\x27\"]*)[\x27\"]", combined)
        mod_flags: set[str] = set()
        skip_next = False
        for tok in literals:
            tok = tok.strip()
            if skip_next:
                skip_next = False
                continue
            if tok in ("--vision-args", "--coach-args"):
                skip_next = True
                mod_flags.add(tok)
                continue
            for flag in re.findall(r"(?<![a-zA-Z0-9_-])--[a-zA-Z0-9-]+", tok):
                mod_flags.add(flag)

        unquoted = re.sub(r"[\x27\"][^\x27\"]*[\x27\"]", "", combined)
        for flag in re.findall(r"(?<![a-zA-Z0-9_-])--[a-zA-Z0-9-]+", unquoted):
            mod_flags.add(flag)

        if mod_flags:
            results.setdefault(mod, set()).update(mod_flags)

    return results


def extract_all_ps1_command_flags(ps1_dir: Path | None = None) -> dict[str, set[str]]:
    """Extract all `python -m <module> ... --flag` invocations across Windows PowerShell scripts."""
    if ps1_dir is None:
        ps1_dir = PS1_DIR
    all_flags: dict[str, set[str]] = {}
    if not ps1_dir.exists():
        return all_flags
    for ps1_file in sorted(ps1_dir.glob("*.ps1")):
        for mod, flags in extract_ps1_command_flags(ps1_file).items():
            all_flags.setdefault(mod, set()).update(flags)
    return all_flags


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
    if module == "tools.sim":
        for sub in ("run", "send", "coach"):
            sub_proc = subprocess.run(
                [sys.executable, "-m", "tools.sim", sub, "--help"],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(ROOT),
            )
            if sub_proc.returncode == 0:
                flags.update(re.findall(r"(?<![a-zA-Z0-9_-])--[a-zA-Z0-9-]+", sub_proc.stdout))
    return flags, None


class CliDocParityTests(unittest.TestCase):
    """Assert all CLI flags extracted from doc code blocks and Windows scripts exist in --help."""

    @classmethod
    def setUpClass(cls):
        cls.extracted_flags = extract_doc_command_flags(DOC_FILES)
        cls.extracted_ps1_flags = extract_all_ps1_command_flags(PS1_DIR)

    def test_auto_extracted_doc_code_block_flags_match_cli_help(self):
        """dynamically assert all doc code-block flags exist in CLI --help."""
        self.assertGreater(len(self.extracted_flags), 0, "must extract command flags from docs")

        for mod, flags in sorted(self.extracted_flags.items()):
            if mod in ("pip", "unittest", "venv", "http.server"):
                continue

            cli_flags, skip_reason = run_cli_help(mod)
            if cli_flags is None:
                # e.g. coach without deepagents
                continue

            # engine.demo forwards unrecognized options to engine
            if mod == "engine.demo":
                engine_flags, _ = run_cli_help("engine")
                if engine_flags:
                    cli_flags = cli_flags | engine_flags

            missing = flags - cli_flags
            self.assertFalse(
                missing,
                f"Docs code blocks use flags not present in 'python -m {mod} --help': {missing}",
            )

    def test_windows_powershell_scripts_flags_match_cli_help(self):
        """extract every python -m X --flag from scripts/windows/*.ps1 and assert flags exist in --help."""
        self.assertGreater(
            len(self.extracted_ps1_flags),
            0,
            "must extract command flags from scripts/windows/*.ps1",
        )

        for mod, flags in sorted(self.extracted_ps1_flags.items()):
            if mod in ("pip", "unittest", "venv"):
                continue

            cli_flags, skip_reason = run_cli_help(mod)
            if cli_flags is None:
                continue

            # engine.demo forwards unrecognized options to engine
            if mod == "engine.demo":
                engine_flags, _ = run_cli_help("engine")
                if engine_flags:
                    cli_flags = cli_flags | engine_flags

            missing = flags - cli_flags
            self.assertFalse(
                missing,
                f"scripts/windows/*.ps1 use flags not present in 'python -m {mod} --help': {missing}",
            )

    def test_engine_demo_cli_flags(self):
        """flags for python -m engine.demo in docs/DEMO.md, engine/README.md & Windows scripts."""
        flags, skip_reason = run_cli_help("engine.demo")
        if flags is None:
            self.skipTest(f"python -m engine.demo skipped: {skip_reason}")

        # Core options + all flags extracted from doc code blocks & Windows scripts for engine.demo
        doc_flags = self.extracted_flags.get("engine.demo", set())
        ps1_flags = self.extracted_ps1_flags.get("engine.demo", set())
        # engine.demo forwards passthrough flags to engine; subtract engine flags to isolate direct demo flags
        engine_flags, _ = run_cli_help("engine")
        passthrough_flags = engine_flags or {"--in", "--out", "--hostapi", "--input-channel", "--serial-port", "--headless"}
        direct_demo_flags = (doc_flags | ps1_flags) - passthrough_flags
        expected = {
            "--open",
            "--vision",
            "--vision-args",
            "--coach",
            "--coach-args",
            "--hand-log",
            "--http-port",
        } | direct_demo_flags

        missing = expected - flags
        self.assertFalse(missing, f"python -m engine.demo --help is missing flags: {missing}")

    def test_vision_cli_flags(self):
        """flags for python -m vision in docs/DEMO.md, vision/README.md & checklists."""
        flags, skip_reason = run_cli_help("vision")
        if flags is None:
            self.skipTest(f"python -m vision skipped: {skip_reason}")

        doc_flags = self.extracted_flags.get("vision", set())
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
        } | doc_flags

        missing = expected - flags
        self.assertFalse(missing, f"python -m vision --help is missing flags: {missing}")

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

        doc_flags = self.extracted_flags.get("coach", set())
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
        } | doc_flags

        missing = expected - flags
        self.assertFalse(missing, f"python -m coach --help is missing flags: {missing}")

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

        doc_flags = self.extracted_flags.get("coach", set())
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
        } | doc_flags

        missing = expected - static_flags
        self.assertFalse(missing, f"coach/__main__.py is missing argument definitions: {missing}")

    def test_engine_cli_flags(self):
        """flags for python -m engine in docs/DEMO.md, engine/README.md & Windows scripts."""
        flags, skip_reason = run_cli_help("engine")
        if flags is None:
            self.skipTest(f"python -m engine skipped: {skip_reason}")

        doc_flags = self.extracted_flags.get("engine", set())
        ps1_flags = self.extracted_ps1_flags.get("engine", set())
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
        } | doc_flags | ps1_flags

        missing = expected - flags
        self.assertFalse(missing, f"python -m engine --help is missing flags: {missing}")

    def test_audio_cli_flags(self):
        """flags for python -m audio in docs/DEMO.md §1 & engine/README.md."""
        flags, skip_reason = run_cli_help("audio")
        if flags is None:
            self.skipTest(f"python -m audio skipped: {skip_reason}")

        doc_flags = self.extracted_flags.get("audio", set())
        expected = {
            "--list-devices",
            "--level-check",
            "--in",
            "--hostapi",
            "--input-channel",
        } | doc_flags

        missing = expected - flags
        self.assertFalse(missing, f"python -m audio --help is missing flags: {missing}")


if __name__ == "__main__":
    unittest.main()
