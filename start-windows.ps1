# Windows PowerShell 5.1 / PowerShell 7 launcher. No remote installer is run.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$uvCommand = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -eq $uvCommand) {
    Write-Host 'uv is required. Install it using the official instructions, then reopen PowerShell:' -ForegroundColor Red
    Write-Host 'https://docs.astral.sh/uv/getting-started/installation/'
    exit 127
}

$portText = $env:ARBITER_PORT
if ([string]::IsNullOrWhiteSpace($portText)) { $portText = '8787' }
$portNumber = 0
if ($portText -notmatch '^[0-9]{1,5}$' -or -not [int]::TryParse($portText, [ref]$portNumber) -or $portNumber -lt 1 -or $portNumber -gt 65535) {
    Write-Host 'ARBITER_PORT must be an integer from 1 to 65535.' -ForegroundColor Red
    exit 2
}

Push-Location -LiteralPath $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath 'pyproject.toml' -PathType Leaf) -or -not (Test-Path -LiteralPath 'uv.lock' -PathType Leaf)) {
        throw 'Extract the complete source ZIP first. pyproject.toml or uv.lock is missing.'
    }
    Write-Host 'Preparing the locked Python environment (uv sync --frozen)...'
    & $uvCommand.Source sync --frozen
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed (exit $LASTEXITCODE). See the error above." }

    Write-Host 'Preparing local source and Skill downloads...'
    & $uvCommand.Source run --frozen python scripts/package_downloads.py
    if ($LASTEXITCODE -ne 0) { throw "Download packaging failed (exit $LASTEXITCODE). See the error above." }

    Write-Host "`nOpen http://127.0.0.1:$portNumber/workspace in your browser."
    Write-Host 'Keep this terminal open. Press Ctrl+C to stop Culture-Fit.'
    & $uvCommand.Source run --frozen uvicorn arbiter.app:app --host 127.0.0.1 --port $portNumber
    if ($LASTEXITCODE -ne 0) { throw "Culture-Fit stopped with exit $LASTEXITCODE. Check for a port conflict or the error above." }
}
catch {
    Write-Host "Culture-Fit could not start: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    Pop-Location
}
