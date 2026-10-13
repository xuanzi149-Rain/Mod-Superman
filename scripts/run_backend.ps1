param([int]$Port = 8000)
$projectRoot = Split-Path $PSScriptRoot -Parent
$pythonRuntime = 'C:\Users\17583\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$env:PYTHONPATH = Join-Path $projectRoot '.runtime/python'
Set-Location $projectRoot
& $pythonRuntime -m uvicorn backend.app:app --host 127.0.0.1 --port $Port --workers 1
