# Distribute Seiyomi as a Windows EXE via GitHub Releases

This guide shows how to build the GUI and CLI as Windows executables, test locally, and publish them on GitHub. It also includes an optional CI workflow to build on every tag.

---

## 1) Prerequisites (Windows)

- Windows 10/11
- Python 3.11 (recommended)
- PowerShell 7 (`pwsh`) or Windows PowerShell
- Git
- Optional: Code signing certificate (reduces SmartScreen warnings)

---

## 2) Create a clean virtual environment and install dependencies

```powershell
Set-Location C:\Users\akortekaas\Documents\GitHub\Seiyomi

# Create venv (using your installed Python 3.11)
py -3.11 -m venv .venv

# Install requirements and PyInstaller into the venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
.\.venv\Scripts\python.exe -m pip install pyinstaller
```

---

## 3) Set app version and changelog

- Update `APP_VERSION` in `gui_launcher_tk.py` (and any other place you surface version text).
- Add a short "What’s New" entry in `GUI_README.md` and/or `README.md`.

Tip: Use semantic versions like `v1.2.0`.

---

## 4) Ensure assets and docs are bundled

PyInstaller bundles only what you tell it to. This repo already includes `.spec` files:

- `MangaDex_Suwayomi_ControlPanel.spec` (GUI)
- `import_mangadex_bookmarks_to_suwayomi.spec` (CLI)

Confirm the specs include the data you want in the EXE distribution, like:

- `assets/icon_256.png`
- `GUI_README.md`, `USER_MANUAL.md`, `README.md`, `LICENSE`
- `userscripts/` (optional)

If you need to add files, update the `datas` list in the `.spec` file, for example:

```python
# In MangaDex_Suwayomi_ControlPanel.spec

datas = [
    ('assets/icon_256.png', 'assets'),
    ('GUI_README.md', '.'),
    ('USER_MANUAL.md', '.'),
    ('README.md', '.'),
    ('LICENSE', '.'),
    ('userscripts', 'userscripts'),  # whole folder
]
```

Then build with the spec (next section).

---

## 5) Build EXEs (local)

Option A: Use the provided build script (recommended if you maintain it)

```powershell
# If build_exe.ps1 expects params, run with them; otherwise:
.\build_exe.ps1 -Clean
```

Option B: Run PyInstaller directly via the venv

```powershell
# GUI
.\.venv\Scripts\python.exe -m PyInstaller .\MangaDex_Suwayomi_ControlPanel.spec

# CLI (optional)
.\.venv\Scripts\python.exe -m PyInstaller .\import_mangadex_bookmarks_to_suwayomi.spec
```

Outputs typically land in `./dist/`:

- `./dist/MangaDex_Suwayomi_ControlPanel/...`
- `./dist/import_mangadex_bookmarks_to_suwayomi/...`

Note: "onedir" builds are more reliable than "onefile" for Tk apps; the specs likely use onedir.

---

## 6) Smoke test the builds

```powershell
# GUI
.\dist\MangaDex_Suwayomi_ControlPanel\MangaDex_Suwayomi_ControlPanel.exe

# CLI
.\dist\import_mangadex_bookmarks_to_suwayomi\import_mangadex_bookmarks_to_suwayomi.exe --help
```

Check that:

- GUI opens; manual/README viewers work
- Command Preview renders correctly
- Running a dry-run command works
- CLI prints `--help` without missing-module errors

---

## 7) Package for release (ZIP)

Create a release ZIP with everything users need.

```powershell
$version = "v1.2.0"
$src = ".\dist\MangaDex_Suwayomi_ControlPanel"
$zip = ".\dist\Seiyomi_${version}_Windows_x64.zip"

if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path "$src\*" -DestinationPath $zip

# Compute checksum for users
Get-FileHash $zip -Algorithm SHA256 | Format-List
```

Recommended ZIP contents:

- `MangaDex_Suwayomi_ControlPanel.exe`
- `GUI_README.md`, `USER_MANUAL.md`, `README.md`, `LICENSE` (if not already inside the app folder)
- `assets/` (as needed)
- `userscripts/` (optional)

---

## 8) Optional: Code sign the EXE

If you have a code signing certificate:

```powershell
# Example with signtool (Windows SDK)
signtool sign /tr http://timestamp.sectigo.com /td SHA256 /fd SHA256 `
  /a /f "C:\path\to\your.pfx" /p "PFX_PASSWORD" `
  ".\dist\MangaDex_Suwayomi_ControlPanel\MangaDex_Suwayomi_ControlPanel.exe"
```

This reduces SmartScreen warnings. If you don’t sign, add a note in the README about “More info → Run anyway”.

---

## 9) Create a GitHub Release (manual)

```powershell
# Tag and push
git tag v1.2.0
git push origin v1.2.0
```

Then on GitHub → Releases → Draft a new release:

- Tag: `v1.2.0`
- Title: `Seiyomi v1.2.0`
- Notes: key changes (“What’s New”), system requirements, SmartScreen note
- Upload `Seiyomi_v1.2.0_Windows_x64.zip`
- Upload checksum file (optional)

---

## 10) Optional: Automate via GitHub Actions (Windows build)

Add `.github/workflows/release.yml`:

```yaml
name: Build and Release (Windows)

on:
  push:
    tags:
      - 'v*'

jobs:
  build-windows:
    runs-on: windows-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install -r requirements.txt
          python -m pip install pyinstaller

      - name: Build GUI
        run: |
          python -m PyInstaller MangaDex_Suwayomi_ControlPanel.spec

      - name: Build CLI (optional)
        run: |
          python -m PyInstaller import_mangadex_bookmarks_to_suwayomi.spec

      - name: Package ZIP
        shell: pwsh
        run: |
          $version = "${{ github.ref_name }}"
          $src = "dist/MangaDex_Suwayomi_ControlPanel"
          $zip = "dist/Seiyomi_${version}_Windows_x64.zip"
          if (Test-Path $zip) { Remove-Item $zip -Force }
          Compress-Archive -Path "$src/*" -DestinationPath $zip
          Get-FileHash $zip -Algorithm SHA256 | Out-File "dist/Seiyomi_${version}_Windows_x64.sha256"

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: |
            dist/Seiyomi_${{ github.ref_name }}_Windows_x64.zip
            dist/Seiyomi_${{ github.ref_name }}_Windows_x64.sha256
```

Notes:

- This builds on tag push (`vX.Y.Z`), zips the GUI app folder, computes a SHA256, and attaches both to the release.
- If you need extra files (e.g., `userscripts/`), ensure they’re bundled via the spec or copied into `dist` before the ZIP step.

---

## 11) Release checklist

- [ ] Bump `APP_VERSION` in `gui_launcher_tk.py`
- [ ] Update “What’s New” in `GUI_README.md`
- [ ] Verify `.spec` bundles assets/docs
- [ ] Build locally; smoke test GUI and CLI
- [ ] Zip output + compute SHA256
- [ ] (Optional) Sign EXE
- [ ] Push tag and publish release notes

---

## 12) User install instructions (README blurb)

- Download the latest `Seiyomi_vX.Y.Z_Windows_x64.zip` from Releases.
- Unzip and double‑click `MangaDex_Suwayomi_ControlPanel.exe`.
- If Windows SmartScreen shows a warning (unsigned build), click “More info → Run anyway”.
- Requirements: Windows 10/11. No separate Python install needed.
