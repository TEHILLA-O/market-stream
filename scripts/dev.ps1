$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (-not $env:MARKETSTREAM_PORT) { $env:MARKETSTREAM_PORT = "8000" }
$env:MARKETSTREAM_API = "http://127.0.0.1:$($env:MARKETSTREAM_PORT)"
if (-not (Test-Path .venv\Scripts\python.exe)) {
  python -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"
}
Start-Process -FilePath "$root\.venv\Scripts\python.exe" -ArgumentList "-m","marketstream" -WorkingDirectory $root
Set-Location "$root\frontend"
if (-not (Test-Path node_modules)) { npm install }
npm run dev
