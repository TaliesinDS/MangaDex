# Suwayomi Database Tool (with GUI)

A desktop helper for Suwayomi that brings together:

- MangaDex import (follows, statuses, custom lists, read chapters)
- Library migration between sources (rehoming, best-source selection)
- Library pruning (duplicates, non-preferred languages)
- Suwayomi connection utilities (auth modes, categories, throttling)

It includes a Tkinter-based GUI with live command preview and presets, plus a direct command-line interface for automation.

---

## Features

- GUI with tabs for Migrate, Prune, MangaDex Import, Suwayomi Database, Settings, and About
- Command Preview: see the exact command that will run (including log piping)
- General controls on a unified bottom bar: Dry run, Save log, Log path, Run, Reset, Exit
- Per‑tab description and Help button (opens in-app manual viewer)
- Tooltips on nearly every option explaining what to enter and what it does
- Presets for common workflows (e.g., Prefer English Migration)
- Works with packaged EXE or Python script directly

---

## Install / Run

- Requirements: Python 3.11+ (or use provided EXE if available), a running Suwayomi server (e.g. <http://127.0.0.1:4567>)
- Windows: double‑click the GUI script, or run from PowerShell:
  
  ```powershell
  # In repo root
  .\.venv\Scripts\python.exe .\gui_launcher_tk.py
  ```

- Or run the CLI directly:
  
  ```powershell
  python import_mangadex_bookmarks_to_suwayomi.py --help
  ```

---

## Tabs Overview

- Migrate
  - Migrate titles between sources within Suwayomi, pick best alternatives by chapter coverage, optionally keep both
  - Includes rehoming for zero‑chapter entries
- Prune
  - Remove zero/low‑chapter duplicates and entries without preferred‑language chapters
- MangaDex Import
  - Login, fetch follows, import statuses and read chapters, map statuses to categories, import custom lists
- Suwayomi Database
  - Connect to Suwayomi (auth modes: auto/basic/simple/bearer), list categories, open UI, set timeouts/throttle
- Settings
  - Debug output and presets
- About
  - App summary, environment info, quick links (README, Manual, Project Folder)

Each tab starts with a short description and a Help button that opens the manual to the relevant section.

---

## Command Preview and Logging

- Command Preview updates live as you change fields
- Bottom bar controls apply to all tabs:
  - Dry run: simulate without changing your library
  - Save log to file: tee console output to a file (pick a path)
  - Run Script: executes the previewed command
  - Reset: restores defaults

---

## CLI Quick Examples

List categories

```powershell
python import_mangadex_bookmarks_to_suwayomi.py --base-url http://127.0.0.1:4567 --list-categories
```

Import follows + statuses + read chapters (dry run)

```powershell
python import_mangadex_bookmarks_to_suwayomi.py `
  --base-url http://127.0.0.1:4567 `
  --from-follows `
  --md-username USER `
  --md-password PASS `
  --import-reading-status `
  --status-category-map completed=5,reading=2,on_hold=7,dropped=8,plan_to_read=9 `
  --import-read-chapters `
  --read-sync-delay 1 `
  --dry-run
```

Migrate existing library (rehoming preferred sources)

```powershell
python import_mangadex_bookmarks_to_suwayomi.py `
  --base-url http://127.0.0.1:4567 `
  --migrate-library `
  --migrate-threshold-chapters 1 `
  --migrate-sources "bato.to,mangabuddy,weeb central,mangapark" `
  --exclude-sources "comick,hitomi" `
  --migrate-title-threshold 0.7 `
  --best-source `
  --best-source-canonical `
  --best-source-candidates 4 `
  --min-chapters-per-alt 5 `
  --migrate-max-sources-per-site 3 `
  --migrate-timeout 25 `
  --migrate-remove-if-duplicate
```

---

## Web UI Userscripts (Optional)

See `userscripts/README.md` for a Tampermonkey/Violentmonkey script that adds a “Sort: Recently Published” button to the Suwayomi web UI, so you can order titles by the latest published chapter date rather than database added date. Adjust selectors as needed for your UI version.

---

## Troubleshooting

- Use Dry run + Command Preview to validate before running
- Turn on Debug output in Settings for verbose logs
- If auth fails: try different auth modes (auto/basic/simple/bearer) and tokens
- If migration returns few results: raise best‑source candidates and timeout, and consider Preferred only off
- If migration/rehoming picks the wrong title: tune title matching with `--migrate-title-threshold` (default 0.6), or enforce strict matches via `--migrate-title-strict`
- Status mapping issues: enable Map debug and Print status summary

For details, open the in‑app manual (Help button on each tab).

---

## Title Matching (Migration & Rehoming)

Some sources return popular/new lists even for specific searches. To prevent unrelated picks:

- `--migrate-title-threshold <0..1>`: Require a minimum normalized title similarity (Jaccard over cleaned tokens). Default: `0.6`.
- `--migrate-title-strict`: Require normalized exact/containment matches; disables fuzzy-only matches.

These checks are applied before selecting candidates for both migration and rehoming. If no candidates pass, that source is skipped.

---

## License

MIT. Respect site policies and support authors/artists.
