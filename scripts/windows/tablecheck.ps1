# Read-only rig checks, except an empty temporary take-directory write probe.
# Run from PowerShell: .\scripts\windows\tablecheck.ps1 [--no-vision] [--no-coach]
# Remaining arguments pass directly to Python (for example --engine-port 47811).
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Push-Location $repoRoot
try {
    $venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        throw 'Run scripts\windows\setup.ps1 first.'
    }
    & $venvPython -m tools.tablecheck @args
    $checkExit = $LASTEXITCODE
    exit $checkExit
}
catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
finally {
    Pop-Location
}
