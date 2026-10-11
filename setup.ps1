# One-time setup (Windows PowerShell): creates .venv and installs dependencies.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Write-Host "Done. In VS Code: Ctrl+Shift+P -> 'Python: Select Interpreter' -> .venv, then press F5."
