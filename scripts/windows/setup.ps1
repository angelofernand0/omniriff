# Windows bring-up helper. Untested on Windows until the live laptop check.
# Uses the venv's Python directly; does not change PowerShell execution policy.
# From the repository root (execution-policy bypass applies to this process only):
# powershell -ExecutionPolicy Bypass -File .\scripts\windows\setup.ps1
# Add -Coach to also install the practice coach's dependencies (coach/requirements.txt).
[CmdletBinding()]
param(
    [switch]$Coach
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

Push-Location $repoRoot
try {
    if (-not (Get-Command py -CommandType Application -ErrorAction SilentlyContinue)) {
        throw 'Install Python 3.12 with the Windows Python launcher, then rerun this script.'
    }
    & py -3.12 --version
    if ($LASTEXITCODE -ne 0) {
        throw 'Python 3.12 is unavailable. Install it with the Windows Python launcher, then rerun.'
    }

    $venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        & py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv.' }
    }
    & $venvPython -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)'
    if ($LASTEXITCODE -ne 0) {
        throw 'The existing .venv does not use Python 3.12. Move it aside and rerun setup; no files were deleted.'
    }

    & $venvPython -m pip install -r engine/requirements.txt -r vision/requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed; fix the pip error above and rerun.' }
    if ($Coach) {
        & $venvPython -m pip install -r coach/requirements.txt
        if ($LASTEXITCODE -ne 0) { throw 'Coach dependency installation failed; fix the pip error above and rerun.' }
        Write-Host 'Coach dependencies installed. Put ANTHROPIC_API_KEY in a gitignored .env (see coach/README.md).'
    }

    Write-Host 'Dependencies installed. Running device, model and port preflight (no audio stream).'
    & $venvPython -m engine --check
    $checkExit = $LASTEXITCODE
    Write-Host "Preflight exit code: $checkExit (0 = ready; 1 = resolve the FAIL rows above)."
    Write-Host 'Windows/Solo/Arduino operation and latency still require the live hardware checks.'
    exit $checkExit
}
catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
finally {
    Pop-Location
}
