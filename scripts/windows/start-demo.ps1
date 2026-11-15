# Windows bring-up helper. Untested on Windows until the live laptop check.
# Uses the venv's Python directly; does not change PowerShell execution policy.
# From the repository root (choose one; execution-policy bypass is process-only):
# powershell -ExecutionPolicy Bypass -File .\scripts\windows\start-demo.ps1 -SerialPort COM3
# powershell -ExecutionPolicy Bypass -File .\scripts\windows\start-demo.ps1 -Headless
# Add -Coach to either command once the coach package and its dependencies are installed.
# With -Coach and the hand model present, vision and the coach share a fresh wrist log
# (runs\hand-<time>.jsonl) so Eyes has hand evidence for each take.
# -StrumHand / -Camera carry the values you verified in the camera rehearsal (vision/REHEARSAL.md).
[CmdletBinding()]
param(
    [string]$SerialPort = '',
    [switch]$Headless,
    [switch]$Coach,
    [ValidateSet('Left', 'Right')]
    [string]$StrumHand = 'Right',
    [int]$Camera = -1
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
    $hasVision = Test-Path -LiteralPath 'models/hand_landmarker.task' -PathType Leaf
    if ($hasVision) {
        $visionArgs = "--model models/hand_landmarker.task --strum-hand $StrumHand"
        if ($Camera -ge 0) { $visionArgs += " --camera $Camera" }
        $demoArgs += @('--vision', '--vision-args', $visionArgs)
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
    if ($Coach) {
        $demoArgs += '--coach'
        Write-Host 'Coach requested; engine.demo manages its process and take directory.'
        if ($hasVision) {
            New-Item -ItemType Directory -Force -Path 'runs' | Out-Null
            $handLog = 'runs/hand-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.jsonl'
            $demoArgs += @('--hand-log', $handLog)
            Write-Host "Wrist log for Eyes: $handLog (strumming hand: $StrumHand)"
        }
        else {
            Write-Warning 'No hand model: the coach will analyze timing only (no Eyes evidence).'
        }
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
