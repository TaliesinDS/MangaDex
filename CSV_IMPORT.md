# CSV Import: Comick.io and Manganato

This document proposes adding CSV import support for Comick.io (bookmarks/mylist + history) and Manganato bookmarks, and shows how the imported items flow into Seiyomi via migration to preferred sources.

## Goals
- Parse exported CSVs from Comick and Manganato.
- Normalize rows into a common structure: `{title, synonyms[], external_ids{mal,anilist,mangaupdates,site_specific}, last_read, rating, status}`.
- Import into Seiyomi by searching and adding best matches from configured sources; optionally rehome away from the original site.
- Preserve reading state where possible (last read chapter hints) and map Comick list type to a Seiyomi category or reading status when configured.

## CSV Schemas (observed)

### Comick: `comick-mylist-YYYY-MM-DD.csv`
Header example:
```
hid,title,type,rating,read,last_read,synonyms,mal,anilist,mangaupdates
```
- `hid`: Comick internal ID (short string). Use as `external_ids.comick = hid`.
- `title`: primary title string.
- `type`: e.g., `Reading` (can map to reading status or category).
- `rating`: optional numeric.
- `read`: last-read chapter indicator (often a chapter count/number) — treat as read-progress hint.
- `last_read`: timestamp of when that chapter was read, or `0000:00:00` placeholder (ignore if invalid).
- `synonyms`: comma-separated variants; split to array.
- `mal`/`anilist`/`mangaupdates`: URLs; extract numeric/slug IDs for better matching.

Read-progress notes (Comick):
- Normalize `read` to `last_read_chapter` in the item model.
- If `last_read` is a valid date, retain it as `last_read_at` metadata for auditing.
- Optionally, when importing, attempt to mark chapters up to `last_read_chapter` as read (behind a future flag like `--csv-apply-read-progress`).

Notes:
- Items should be migrated to non-Comick sources (user intent).
- Use titles + synonyms + external ids to search targets.

### Manganato: `manganato.gg_bookmarks.csv`
Common columns (varies by export tool): typically include title, URL, and a `viewed` field.
- `title`: title string
- `url`: Manganato URL; store as `external_ids.manganato`.
- `viewed`: last read chapter indicator (we'll treat this as a hint for read-progress).
- If columns differ, allow `--csv-col-map title=<col>,url=<col>,viewed=<col>` override.

Read-progress notes:
- If `viewed` parses cleanly as a chapter number or label, we record it in the normalized item as `last_read_chapter`.
- During import, when the selected source is added, we can optionally attempt to mark chapters up to `last_read_chapter` as read (future optional flag, e.g., `--csv-apply-read-progress`).

## CLI Additions

- `--from-csv <path>`: path to a CSV file to import (Comick or Manganato detected automatically by header/URL patterns).
- `--csv-kind <auto|comick|manganato>`: force parser (default `auto`).
- `--csv-col-map key=col,key=col`: user mapping overrides for unknown CSVs.
- `--csv-status-to-category reading=5,completed=9,...`: map `type` (Comick) to Seiyomi categories.
- `--csv-preferred-sources "bato.to,mangabuddy,weeb central,mangapark"`: candidate sites for migration.
- `--csv-preferred-langs "en,en-us"` and `--lang-fallback`: reuse existing flags.
- `--csv-dry-run`: print normalized rows and planned actions without changes (alias of global `--dry-run`).
- Library reconciliation & migration triggers:
   - `--csv-reconcile` (default on): check existing library for duplicates and completeness before adding.
   - `--csv-migrate-if-behind` (default on): if CSV `last_read_chapter` > current library chapter count, attempt to migrate to a more complete source.
   - `--csv-behind-threshold <N>`: minimum chapter gap to trigger migration (default `1`).
   - `--csv-prefer-existing`: if an existing entry meets or exceeds CSV progress, skip adding/migrating.
   - `--csv-apply-read-progress`: after add/migrate, attempt to mark chapters up to `last_read_chapter` as read (best-effort; requires a source with chapters loaded).

Reusing existing knobs:
- Search and selection use existing `--best-source`, `--best-source-canonical`, `--best-source-candidates`, `--min-chapters-per-alt`, `--migrate-title-threshold`, etc.
- Removal/destructive behavior remains opt-in (`--migrate-remove`, `--migrate-remove-if-duplicate`).

## Flow
1. Parse CSV -> list of items: `{title, synonyms[], ids, site_hint, status, last_read, last_read_chapter?}`.
2. Reconcile with existing library:
   - Find existing entries by normalized title (and, if available, site-specific URL/ID heuristics).
   - Compute current chapter counts for the existing entry (canonical and/or preferred-langs).
   - If `--csv-prefer-existing` and existing is sufficiently complete (>= CSV `last_read_chapter` and meets language preference), skip add/migrate.
   - If `--csv-migrate-if-behind` and CSV `last_read_chapter` > existing count by `--csv-behind-threshold`, mark the item for migration (search for a more complete source).
3. For each item (new or marked for migration):
   - Build candidate queries: primary title + synonyms; if external ids available (MAL/AniList/MU), optionally query their titles to enrich.
   - Search target sources (per `--csv-preferred-sources`).
   - Score candidates using existing language-aware and canonical chapter counts; apply title threshold.
   - Add best candidate to Seiyomi library.
   - If `--migrate-remove` or `--migrate-remove-if-duplicate` is set, remove zero/low-chapter original when appropriate (for Comick intent: rehome away from Comick).
   - If `--csv-status-to-category` provided, add to mapped category.
   - If `--csv-apply-read-progress` and we have `last_read_chapter`, attempt to mark chapters as read (best-effort, respects rate limits and server readiness).
4. Summary: print counts and a CSV of failures with reasons.

## Matching Strategy
- Title-first with synonyms fallback.
- If MAL/AniList/MU IDs exist, optionally hit those APIs (future work) to fetch canonical English/Japanese titles for better matching.
- Strict option: `--migrate-title-strict` to avoid false positives from noisy sources.
 - Library reconciliation: match normalized titles and prefer sources with higher canonical or preferred-language chapter counts.

## Edge Cases
- Empty/placeholder `last_read` like `0000:00:00`: ignore.
- Multiple matches above threshold: prefer more chapters; prefer preferred-langs count if configured.
- Non-Latin titles: rely on synonyms list and external IDs; consider lower threshold with strict mode off.
- Duplicates across CSV and existing library: de-dup by normalized title; if found, optionally skip or rehome.
- `last_read_chapter` not numeric (e.g., "Chapter 50.5", "50 extra"): parse best-effort (float or integer extraction); if unparsable, skip progress-based migration.
- Existing entry distributed across categories: treat as one; avoid duplicate adds.

Fractional chapter policy (.1–.9):
- Canonical segmentation: treat `.1–.4` as canonical parts of a split chapter and count them toward progress/completeness.
- `.5` rule: if any split exists for the same base chapter (i.e., any of `.1–.4` OR any of `.6+` are present), treat `.5` as canonical too (part of the regular chapter pack). Only exclude `.5` when it is an isolated half-chapter with no other splits for that base chapter (e.g., you have 1–24 and then stray `33.5`, `38.5`).
- Higher fractions: when `.6+` exist for a base chapter, consider the entire `.x` range for that base as canonical (unless title hints mark them as extras).
- Title-based hints: strings like "extra", "omake", "special", "side story" cause exclusion even if numeric fraction looks canonical.
- Ambiguity policy: if splits are present for the base chapter but `.5` might be an extra, assume canonical (include) to avoid undercounting. If no splits are present, exclude `.5` from progress by default.

## Examples (PowerShell)

Dry-run Comick import, prefer English, add to category 5 for `Reading`:
```powershell
.\.venv\Scripts\python.exe .\import_mangadex_bookmarks_to_suwayomi.py `
  --base-url http://127.0.0.1:4567 `
  --from-csv .\comick-mylist-2025-09-23.csv `
  --csv-kind comick `
  --csv-preferred-sources "bato.to,mangabuddy,weeb central,mangapark" `
  --preferred-langs "en,en-us" `
  --lang-fallback `
  --best-source --best-source-canonical `
  --csv-status-to-category reading=5,completed=9,on_hold=7,dropped=8,plan_to_read=10 `
  --dry-run
```

Import Manganato bookmarks (title + URL), no removal, add only best source:
```powershell
.\.venv\Scripts\python.exe .\import_mangadex_bookmarks_to_suwayomi.py `
  --base-url http://127.0.0.1:4567 `
  --from-csv .\manganato.gg_bookmarks.csv `
  --csv-kind manganato `
  --csv-preferred-sources "mangabuddy,weeb central,mangapark" `
  --best-source --best-source-canonical `
  --dry-run
```

Migrate if library is behind your CSV progress (auto-detect and rehome to fuller source):
```powershell
.\.venv\Scripts\python.exe .\import_mangadex_bookmarks_to_suwayomi.py `
   --base-url http://127.0.0.1:4567 `
   --from-csv .\comick-mylist-2025-09-23.csv `
   --csv-kind auto `
   --csv-preferred-sources "bato.to,mangabuddy,weeb central,mangapark" `
   --preferred-langs "en,en-us" `
   --csv-reconcile `
   --csv-migrate-if-behind `
   --csv-behind-threshold 1 `
   --best-source --best-source-canonical `
   --migrate-remove-if-duplicate `
   --dry-run
```

Strict matching (reduce false positives):
```powershell
.\.venv\Scripts\python.exe .\import_mangadex_bookmarks_to_suwayomi.py `
  --base-url http://127.0.0.1:4567 `
  --from-csv .\comick-mylist-2025-09-23.csv `
  --csv-kind auto `
  --migrate-title-strict `
  --dry-run
```

## Implementation Plan (incremental)
1. Parser module:
   - Detect CSV type by headers or URL patterns.
   - Implement `parse_comick_csv(path)` and `parse_manganato_csv(path, colmap)` that return normalized items.
2. CLI wiring:
   - Add `--from-csv`, `--csv-kind`, `--csv-col-map`, `--csv-status-to-category`, `--csv-preferred-sources` flags.
   - In `main()`, when `--from-csv` present, bypass MangaDex follow flow and pass items into an `import_csv_items()` function that reuses migration logic.
3. Import logic:
   - Implement `import_csv_items(client, items, ...)` using existing search/migration helpers (`search_by_title`, best-source, language filters, categories).
   - Reconciliation step: fetch library via `get_library_graphql()` (faster) to map normalized titles to existing internal IDs; for candidates, compute chapter counts using `get_manga_chapters_canonical_count()` or `get_manga_chapters_count_by_lang()` and compare to `last_read_chapter`.
   - If behind and allowed, search and add a fuller source; optionally remove or keep the old source per existing migration flags.
4. UX & Safety:
   - Respect existing non-destructive defaults; require explicit `--migrate-remove*` to delete originals.
   - Produce a `reports/csv_import_failures_YYYYMMDD_HHMMSS.csv` summary when `--out` or logs are requested.
5. Future work:
   - Optional enrichment via MAL/AniList APIs; add caching.
   - Read-progress mapping when CSV exposes chapter counts.

---

Questions or tweaks? We can extend this to other CSVs by adding small, pluggable parsers and a column map.