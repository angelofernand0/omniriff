# Devpost hardware measurements in two passes. Untested on Windows until the live laptop check.
# Uses the venv's Python directly; does not change PowerShell execution policy.
# From the repository root (execution-policy bypass is process-only):
# 1) Loopback cable (Solo output -> input 2, INST off, low gain, speakers DOWN, Direct Monitor OFF):
#    powershell -ExecutionPolicy Bypass -File .\scripts\windows\measure.ps1 -Pass Loopback
# 2) Guitar in input 2 (INST on, speakers low); keep playing during the soak:
#    powershell -ExecutionPolicy Bypass -File .\scripts\windows\measure.ps1 -Pass Guitar
# Add -BlockSize 64 and/or -Exclusive to try lower latency; keep the lowest setting with 0 xruns.
[CmdletBinding()]
param(
    [ValidateSet('Loopback', 'Guitar')]
    [string]$Pass = 'Loopback',
    [int]$BlockSize = 128,
    [switch]$Exclusive,
    [double]$SoakMinutes = 5,
    [double]$TakeSeconds = 20
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

    $measureArgs = @('-m', 'tools.measure', '--in', 'Focusrite', '--out', 'Focusrite', '--hostapi', 'WASAPI',
                     '--input-channel', '2', '--blocksize', "$BlockSize")
    if ($Exclusive) { $measureArgs += '--exclusive' }
    if ($Pass -eq 'Loopback') {
        Write-Host 'LOOPBACK pass: preflight, round-trip latency and engine CPU. No soak.'
        $measureArgs += @('--soak-minutes', '0')
    }
    else {
        Write-Host "GUITAR pass: $SoakMinutes-minute soak (keep playing), then a $TakeSeconds-second dry take for Ears."
        $measureArgs += @('--skip-check', '--skip-latency', '--skip-cpu',
                          '--soak-minutes', "$SoakMinutes", '--take-seconds', "$TakeSeconds")
    }

    & $venvPython @measureArgs
    exit $LASTEXITCODE
}
catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
finally {
    Pop-Location
}
