# MangaDex → Suwayomi Importer

Import your MangaDex follows, reading statuses, and read chapters into a Suwayomi (Tachidesk) server. Optionally migrate existing Suwayomi entries to alternative sources when the original source has 0 chapters (rehoming).

This project is a standalone fork focused solely on MangaDex → Suwayomi. For a step‑by‑step, beginner‑friendly guide, see USER_MANUAL.md.

---

## Features

- Import all followed manga from MangaDex into Suwayomi
- Map MangaDex reading statuses (Reading, Completed, Dropped, On Hold, Plan to Read) to Suwayomi categories
- Sync read chapter markers to match MangaDex
- Import from a local list file as an alternative to live follows
- Migrate existing Suwayomi library entries to alternative sources (e.g., Weeb Central, MangaPark) when the current source has few/zero chapters
- Diagnostics and dry‑run mode to preview actions safely

---

## Prerequisites

- Windows (or any OS with Python 3.11+)
- Python 3.11 or newer
- A running Suwayomi server (for example <http://127.0.0.1:4567>)
- MangaDex account (username/password) if importing follows, statuses, or read markers
- Suwayomi categories created ahead of time if you want status mapping

Auth notes:

- Many Suwayomi builds expose GraphQL openly, so you may not need a UI token. If your server requires auth, pass `--username/--password` or `--token`.

---

## Quick Start (Beginner)

1) Double‑click `run_importer.bat`
2) Enter base URL (e.g. `http://127.0.0.1:4567`)
3) Choose to fetch follows, enter MangaDex credentials
4) Choose status mapping and/or chapter sync (optional)
5) Run a dry‑run first; then run again without dry‑run to apply

Full instructions live in USER_MANUAL.md.

---

## Usage (Direct Python)

Import follows + statuses + chapters (dry run):

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

Apply changes: remove `--dry-run`.

List categories:

```powershell
python import_mangadex_bookmarks_to_suwayomi.py `
  --base-url http://127.0.0.1:4567 `
  --list-categories
```

---

## Migrate Existing Library (Rehome)

Add an alternative source for entries with few/zero chapters (dry run):

```powershell
python import_mangadex_bookmarks_to_suwayomi.py `
  --base-url http://127.0.0.1:4567 `
  --migrate-library `
  --migrate-threshold-chapters 1 `
  --migrate-sources "weeb central,mangapark" `
  --dry-run
```

Apply changes and remove the original after success:

```powershell
python import_mangadex_bookmarks_to_suwayomi.py `
  --base-url http://127.0.0.1:4567 `
  --migrate-library `
  --migrate-threshold-chapters 1 `
  --migrate-sources "weeb central,mangapark" `
  --migrate-remove
```

Tips:

- Use `--debug-library` to see which API/GraphQL paths are used
- The tool deduplicates across categories and uses best‑effort chapter counting

---

## Troubleshooting

- Use `--dry-run` to preview actions
- `--debug-follows` shows MangaDex follow pagination
- `--status-map-debug` explains status mapping decisions
- `--debug-library` prints Suwayomi library discovery and chapter count paths

If you need help, see USER_MANUAL.md → “Troubleshooting” and “Getting Help”.

---

## License

This project is provided as‑is without warranty. Respect site and content policies, and support authors/artists.
