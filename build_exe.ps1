param(
  [switch]$Clean
)

$ErrorActionPreference = 'Stop'

Write-Host 'Setting up venv (./.venv) and installing deps...'
if (-not (Test-Path .venv)) {
  python -m venv .venv
}

$venvPython = Join-Path (Resolve-Path .venv).Path 'Scripts/python.exe'
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

if ($Clean) {
  Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue
}

Write-Host 'Building CLI EXE...'
& $venvPython -m PyInstaller --noconfirm --clean `
  --name import_mangadex_bookmarks_to_suwayomi `
  --onefile `
  --console `
  import_mangadex_bookmarks_to_suwayomi.py

Write-Host 'Building GUI EXE...'
& $venvPython -m PyInstaller --noconfirm --clean `
  --name MangaDex_Suwayomi_ControlPanel `
  --onefile `
  --windowed `
  gui_launcher_tk.py

Write-Host 'Done. EXEs located in ./dist'
