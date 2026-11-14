# Windows bring-up helper. Untested on Windows until the live laptop check.
# Uses the venv's Python directly; does not change PowerShell execution policy.
# From the repository root (choose one; execution-policy bypass is process-only):
# powershell -ExecutionPolicy Bypass -File .\scripts\windows\start-demo.ps1 -SerialPort COM3
# powershell -ExecutionPolicy Bypass -File .\scripts\windows\start-demo.ps1 -Headless
[CmdletBinding()]
param(
    [string]$SerialPort = '',
    [switch]$Headless
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

Push-Location $repoRoot
try {
    $venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        throw 'Run scripts\windows\setup.ps1 first to create .venv and install dependencies.'
    }
    & $venvPython -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'The .venv must use Python 3.12. Run scripts\windows\setup.ps1.' }

    $demoArgs = @('-m', 'engine.demo', '--open')
    if (Test-Path -LiteralPath 'models/hand_landmarker.task' -PathType Leaf) {
        $demoArgs += @('--vision', '--vision-args', '--model models/hand_landmarker.task')
    }
    else {
        Write-Warning 'Hand model missing: starting audio/dashboard without vision. Download models/hand_landmarker.task using vision/README.md before the camera test.'
    }

    if ($Headless) {
        $demoArgs += '--headless'
        Write-Host 'HEADLESS: processing silence; no audio interface or audible guitar output.'
    }
    else {
        $demoArgs += @('--in', 'Focusrite', '--out', 'Focusrite', '--hostapi', 'WASAPI', '--input-channel', '2')
    }
    if (-not [string]::IsNullOrWhiteSpace($SerialPort)) {
        $demoArgs += @('--serial-port', $SerialPort)
    }

    Write-Host 'Starting the local dashboard and engine. Keep this terminal open; q or Ctrl+C stops the demo.'
    & $venvPython @demoArgs
    $demoExit = $LASTEXITCODE
    exit $demoExit
}
catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
finally {
    Pop-Location
}
