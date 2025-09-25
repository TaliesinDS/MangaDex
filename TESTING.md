# Seiyomi Test Plan (Manual + Scripted)

This document outlines a practical set of tests to validate the end-to-end behavior of `import_mangadex_bookmarks_to_suwayomi.py` and the GUI.
It now includes an automated `pytest` suite alongside reproducible PowerShell commands (Windows) and clear pass/fail criteria.

> Shell: PowerShell (`pwsh.exe`). Replace backticks with carets (^) for `cmd.exe`. Paths assume repo root.

---

## Automated Tests (pytest)

The repository ships with an initial `pytest` suite that exercises core helper functions. The suite is designed to grow alongside additional fixtures and mocked scenarios (see `docs/automated_test_proposal.md`).

### 0.1 Environment

```powershell
# Activate the virtual environment first
& .\.venv\Scripts\Activate.ps1

# Install development dependencies once
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

### 0.2 Run the Suite

Inside VS Code, open the **Testing** panel and click **Run All Tests**. The project settings already point the test runner at the `tests/` directory.

Alternatively, launch the bundled task or run pytest directly:

```powershell
# VS Code task (Command Palette → "Tasks: Run Task" → "Run importer tests")

# Direct invocation
python -m pytest --maxfail=1 --disable-warnings
```

### 0.3 Current Coverage

- `tests/test_title_and_input_helpers.py` — validates title normalization, similarity checks, ID extraction, multi-format file ingestion, and canonical chapter helpers.
- `tests/test_suwayomi_client_http.py` — exercises `SuwayomiClient` HTTP fallbacks (library removal and GraphQL endpoint probing) using the `responses` mock fixture.
- `tests/fixtures/` — starter payloads for MangaDex and Suwayomi mock data.

Future work will expand into HTTP contract and CLI scenario tests per the automation proposal.

---

## 0. Setup

- Ensure Suwayomi server is running and reachable (e.g., `http://127.0.0.1:4567`).
- Verify Python venv is ready and activated, or use packaged EXE.
- Create `reports/` folder (scripts create it if missing, but we’ll verify permissions).
- Have a MangaDex account with follows and at least a handful of titles with read chapters marked.

Quick checks:
```powershell
# From repo root
Test-Path .\.venv\Scripts\python.exe

# Server check (optional):
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:4567/ -TimeoutSec 5 | Select-Object StatusCode
```

Artifacts we validate frequently:
- `reports\md_missing_reads.csv`
- Optional: `mangadex_follows.json`, status export JSON.

Automation (one command)

Use the bundled PowerShell runner to execute the plan end-to-end without manual copy/paste:

```powershell
# Default (interactive for MD creds)
pwsh -NoLogo -NoProfile -File .\scripts\run_test_plan.ps1 `
  -BaseUrl http://127.0.0.1:4567 `
  -StatusMap "completed=9,reading=5,on_hold=7,dropped=8,plan_to_read=6"

# Non-interactive (env vars for creds)
$env:MD_USER="YOUR_USER"; $env:MD_PASS="YOUR_PASS"; `
pwsh -NoLogo -NoProfile -File .\scripts\run_test_plan.ps1 `
  -BaseUrl http://127.0.0.1:4567 `
  -MissingReport .\reports\md_missing_reads.csv `
  -StatusMap "completed=9,reading=5,on_hold=7,dropped=8,plan_to_read=6" `
  -NonInteractive

# Quick subset (skips some slower steps like migration/prune)
pwsh -NoLogo -NoProfile -File .\scripts\run_test_plan.ps1 -Quick
```

Logs are stored under `reports/` with timestamped filenames, and the missing-reads CSV is updated live during the cross-source read sync step.


## 1. Follows Fetch (baseline)

Goal: Confirm we can authenticate to MangaDex and fetch follows.

Command:
```powershell
.\.venv\Scripts\python.exe .\import_mangadex_bookmarks_to_suwayomi.py `
  --base-url http://127.0.0.1:4567 `
  --from-follows `
  --md-username <USER> `
  --md-password <PASS> `
  --follows-json .\reports\mangadex_follows.json `
  --dry-run `
  --no-progress
```
Pass criteria:
- Exit code 0.
- Console indicates follows fetched (count > 0). `mangadex_follows.json` exists and contains id+title pairs.

Edge: invalid credentials → expect graceful error and non-zero exit.

---

## 2. Reading Status Mapping

Goal: Fetch statuses and map to categories.

Prep: Ensure categories exist on Suwayomi and you know their IDs.

Command:
```powershell
.\.venv\Scripts\python.exe .\import_mangadex_bookmarks_to_suwayomi.py `
  --base-url http://127.0.0.1:4567 `
  --from-follows `
  --md-username <USER> `
  --md-password <PASS> `
  --import-reading-status `
  --status-category-map completed=9,reading=5,on_hold=7,dropped=8,plan_to_read=6 `
  --print-status-summary `
  --dry-run
```
Pass criteria:
- Summary prints counts by status and mapping coverage.
- No exceptions; exit code 0.

Edge: `--assume-missing-status reading` shows assumed status in summary.

---

## 3. Read Chapters (UUID on MangaDex source)

Goal: Mark read chapters for MangaDex-source entries.

Command:
```powershell
.\.venv\Scripts\python.exe .\import_mangadex_bookmarks_to_suwayomi.py `
  --base-url http://127.0.0.1:4567 `
  --from-follows `
  --md-username <USER> `
  --md-password <PASS> `
  --import-read-chapters `
  --read-sync-delay 2 `
  --max-read-requests-per-minute 240
```
Pass criteria:
- Progress lines like `Chapters sync <id>: markable=X marked=Y missing=Z` appear.
- Some titles with exact UUID matches show `missing=0`.
- No crash; exit code 0.

Edge: If some show `WARN no chapters loaded yet`, rerun with higher delay (e.g., 5).

---

## 4. Read Chapters Across Sources (chapter number fallback)

Goal: Apply read progress to non-MangaDex entries by chapter number and across sources.

Command:
```powershell
.\.venv\Scripts\python.exe .\import_mangadex_bookmarks_to_suwayomi.py `
  --base-url http://127.0.0.1:4567 `
  --from-follows `
  --md-username <USER> `
  --md-password <PASS> `
  --import-read-chapters `
  --read-sync-number-fallback `
  --read-sync-across-sources `
  --read-sync-only-if-ahead `
  --read-sync-delay 2 `
  --max-read-requests-per-minute 240 `
  --missing-report .\reports\md_missing_reads.csv
```
Pass criteria:
- `reports\md_missing_reads.csv` created with header and rows added during the run where `missing>0` or `unknown`.
- Non-zero `marked` on non-MangaDex entries (by chapter number) when MD progress is higher.
- Exit code 0.

Edge: If CSV rows don’t append, ensure Excel isn’t locking the file and tail with `Get-Content -Wait`.

---

## 5. Verify IDs in Scope

Goal: Confirm specific MangaDex IDs are included after merges/filters.

Command:
```powershell
.\.venv\Scripts\python.exe .\import_mangadex_bookmarks_to_suwayomi.py `
  --base-url http://127.0.0.1:4567 `
  --from-follows `
  --md-username <USER> `
  --md-password <PASS> `
  --verify-id 01453642-9d95-438d-baac-8c362cbe1a6f `
  --verify-id 0bd7972b-adb4-4708-bcb2-4198f95b6074 `
  --dry-run
```
Pass criteria:
- Console prints ID presence results (“present/absent”).

---

## 6. List Categories

Goal: Confirm we can list categories via available endpoints.

Command:
```powershell
.\.venv\Scripts\python.exe .\import_mangadex_bookmarks_to_suwayomi.py `
  --base-url http://127.0.0.1:4567 `
  --list-categories
```
Pass criteria:
- Prints category id + name via at least one of the tried endpoints.

---

## 7. Migration (Existing Library)

Goal: Add a better source for low/zero-chapter entries; optionally remove original.

Command (safe defaults):
```powershell
.\.venv\Scripts\python.exe .\import_mangadex_bookmarks_to_suwayomi.py `
  --base-url http://127.0.0.1:4567 `
  --migrate-library `
  --migrate-threshold-chapters 1 `
  --migrate-sources "bato.to,mangabuddy,weeb central,mangapark" `
  --exclude-sources "comick,hitomi" `
  --migrate-title-threshold 0.6 `
  --best-source `
  --best-source-candidates 4 `
  --migrate-timeout 20 `
  --dry-run
```
Pass criteria:
- For low-chapter entries, candidates are found and a choice is printed.
- No destructive actions performed in dry run.

Optional apply:
- Re-run without `--dry-run`, optionally add `--migrate-remove-if-duplicate` or `--migrate-remove`.

---

## 8. Prune (No Searching)

8.1 Zero/Low-Chapter Duplicates
```powershell
.\.venv\Scripts\python.exe .\import_mangadex_bookmarks_to_suwayomi.py `
  --base-url http://127.0.0.1:4567 `
  --prune-zero-duplicates `
  --prune-threshold-chapters 1 `
  --dry-run
```
Pass criteria:
- Report prints prune summary: kept/removed counts. No removals in dry run.

8.2 Non‑Preferred Languages
```powershell
.\.venv\Scripts\python.exe .\import_mangadex_bookmarks_to_suwayomi.py `
  --base-url http://127.0.0.1:4567 `
  --prune-nonpreferred-langs `
  --preferred-langs "en,en-us" `
  --prune-lang-threshold 1 `
  --dry-run
```
Pass criteria:
- Summary indicates which titles would be removed/kept under language rules.

---

## 9. Failure Handling & Diagnostics

9.1 Invalid MangaDex credentials → expect login failure message and exit code != 0.

9.2 Network timeout on Suwayomi → adjust `--request-timeout`, confirm graceful error.

9.3 Debug flags
- `--debug-follows`: verify pagination debug prints.
- `--debug-library`: verify library and chapters endpoint attempts are printed.
- `--status-endpoint-raw`: inspect raw JSON for statuses.

---

## 10. GUI Validation (Control Panel)

10.1 Launch GUI
```powershell
.\.venv\Scripts\python.exe .\gui_launcher_tk.py
```
- Navigate tabs, confirm tooltips.
- Open manual via Help.

10.2 Presets
- Select “Read Sync Across Sources” → ensure these toggle:
  - MangaDex Import enabled, Import read chapters ON
  - Number fallback, Across sources, Only if ahead ON
  - Delay = 2, Max RPM = 240
  - Missing report prefilled
- Preview shows all flags; Run executes without error.

10.3 Command Preview
- Changing fields updates preview within ~120ms.
- “Open in external terminal” launches PowerShell with the command.

---

## 11. Post-run Sanity

- Spot-check a few titles in Suwayomi to confirm read markers are applied.
- Check missing CSV for rows to migrate later.
- If you ran migration, confirm new entries exist and original removal (if chosen) is correct.

---

## 12. Suggested Automation Hooks (Optional)

- Wrap the above commands into a PowerShell script that writes timestamps and exit codes to `reports/`.
- Add a “smoke test” script:
```powershell
$env:STLMGR_DB_URL="sqlite:///./data/stl_manager_v1.db"; `
.\.venv\Scripts\python.exe -m pytest -q  # if you add unit tests later
```
- Consider a small set of mock fixtures for HTTP endpoints if you plan to add unit tests; today’s plan is integration/manual focused.

---

## 13. Pass/Fail Tracker (Template)

Use this table to log outcomes per run:

| Test | Date | Result | Notes |
|------|------|--------|-------|
| 1 Follows | | Pass/Fail | |
| 2 Statuses | | Pass/Fail | |
| 3 Read UUID | | Pass/Fail | |
| 4 Read Across | | Pass/Fail | |
| 5 Verify IDs | | Pass/Fail | |
| 6 Categories | | Pass/Fail | |
| 7 Migration | | Pass/Fail | |
| 8.1 Prune Dups | | Pass/Fail | |
| 8.2 Prune Lang | | Pass/Fail | |
| 9 Diagnostics | | Pass/Fail | |
| 10 GUI | | Pass/Fail | |
| 11 Post-run | | Pass/Fail | |
