param([int]$Port = 8000, [string]$Python = '', [string]$BindAddress = '127.0.0.1')
$projectRoot = Split-Path $PSScriptRoot -Parent
$pythonRuntime = $Python
if (-not $pythonRuntime) {
    $bundled = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
    if (Test-Path -LiteralPath $bundled) { $pythonRuntime = $bundled }
    else { $pythonRuntime = 'python' }
}
$env:PYTHONPATH = Join-Path $projectRoot '.runtime/python'
if (-not $env:MOD_DATA_DIR) { $env:MOD_DATA_DIR = Join-Path $projectRoot 'build/backend/mvp-local' }
Set-Location $projectRoot
& $pythonRuntime -m uvicorn backend.app:app --host $BindAddress --port $Port --workers 1
