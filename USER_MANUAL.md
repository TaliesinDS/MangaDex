# MangaDex → Suwayomi Import Tool (Beginner Friendly Guide)

This guide shows you how to move ("import") your MangaDex followed manga, reading statuses, and read chapter progress into a Suwayomi (Tachidesk) server **even if you have never used the command line before**.

---

## 1. What This Tool Does

It can:

- Add every manga you follow on MangaDex into your Suwayomi library.
- (Optional) Put each manga into categories based on your MangaDex reading status (Reading, Completed, Dropped, etc.).
- (Optional) Mark chapters as read in Suwayomi to match what you have already read on MangaDex.
- (Optional) Use a local bookmarks/list file instead of your live follows.
- Migrate entries already in your Suwayomi library to alternative sources (e.g., Weeb Central, MangaPark) when the original source has 0 or very few chapters. This is useful for delisted/DMCA’d manga on MangaDex.

It does **not**:

- Create categories automatically (you should create them in Suwayomi first and note their numeric IDs).
- Recover chapters that have been DMCA removed or delisted from MangaDex.
- Sync continuously (it is a one‑time or occasional run tool).

Notes about connections/authentication:

- The tool talks to your Suwayomi server using its REST API and, if needed, its GraphQL endpoint. Many Suwayomi builds expose GraphQL openly on <http://127.0.0.1:4567/api/graphql>, which lets this tool work even if some REST endpoints require a UI token.
- If your server requires authentication for the endpoints this tool needs, you can pass --username/--password or --token. Otherwise you can leave auth out.

---

## 2. Prerequisites (What You Need First)

| Item | Why You Need It | How to Get It |
|------|-----------------|---------------|
| Windows PC | Runs the tool | You already have it |
| Python (version 3.11 or newer recommended) | Runs the script | [Download Python](https://www.python.org/downloads/) (check "Add python.exe to PATH" during install) |
| Suwayomi (Tachidesk) server running | Destination library | Start your server (default often `http://localhost:4567`) |
| MangaDex account credentials | To fetch your follows & read markers | Use your normal username and password |
| Categories in Suwayomi (optional) | For mapping statuses | Create them in Suwayomi UI first |

### How to Check Python Installed

1. Press the Windows key.
2. Type: `cmd` and press Enter.
3. In the black window type: `python --version` and press Enter.
   - If you see something like: `Python 3.12.0` you’re good.
   - If you get an error, install Python (make sure to tick **Add to PATH** during installation).

---

## 3. Download / Place the Files

1. Put the script files (`import_mangadex_bookmarks_to_suwayomi.py`, `run_importer.bat`, and this `USER_MANUAL.md`) together in a folder. For example: `C:\MangaDexImport`.
2. (Optional) Create a shortcut to `run_importer.bat` on your Desktop so you can double‑click it.

---

## 4. Quick Start (Easiest Path)

1. Double‑click `run_importer.bat`.
2. When asked for the **Suwayomi base URL**, type: `http://localhost:4567` (change if yours differs) and press Enter.
3. For **Fetch all MangaDex follows?** press Enter to accept `Y`.
4. Enter your **MangaDex username**.
5. Enter your **MangaDex password** (it will be visible while typing—batch files cannot hide input easily). You can change your password later if concerned.
6. For **Import reading statuses** press Enter to accept `Y`.
7. When prompted for a **status map**, you can paste something like:
   `completed=5,reading=2,on_hold=7,dropped=8,plan_to_read=9`
   (Only include the statuses you actually want. Make sure those category IDs exist in Suwayomi.)
8. For **Import chapter read markers?** answer `Y` if you want your read chapter progress imported, else `N`.
9. If you said `Y`, set a delay (1 second is safe) so the server can load chapters before they are marked.
10. (Optional) Enter a single category id to force everything into it as well (e.g. a general "Imported" category). Leave blank to skip.
11. Accept the default to do a **Dry run** first (`Y`).
12. Wait—dry run shows what *would* be added (no changes yet).
13. At the end it will ask if you want to run again without dry-run. Press `Y` to perform the real import.

---

## 4.1 Migrate Library (Rehome Delisted/Empty Sources)

If you already have a Suwayomi library and want to add an alternative source entry for series that have 0 (or very few) chapters on their current source, use migrate mode. This is ideal when MangaDex entries are delisted/empty.

Basic dry run:

```powershell
python import_mangadex_bookmarks_to_suwayomi.py `
   --base-url http://127.0.0.1:4567 `
   --migrate-library `
   --migrate-threshold-chapters 1 `
   --migrate-sources "weeb central,mangapark" `
   --exclude-sources "comick,hitomi" `
   --dry-run
```

Apply changes (remove `--dry-run`), and optionally delete the original entry when an alternative is added:

```powershell
python import_mangadex_bookmarks_to_suwayomi.py `
   --base-url http://127.0.0.1:4567 `
   --migrate-library `
   --migrate-threshold-chapters 1 `
   --migrate-sources "weeb central,mangapark" `
   --migrate-remove
```

Notes:

- The tool discovers your library through GraphQL (categories first) and deduplicates across categories.
- Chapter count is computed from available endpoints; if chapter endpoints need auth on your server, the tool will fall back to GraphQL and best-effort counting.
- You can add `--debug-library` to print which endpoints and GraphQL fields were used.
- Default excluded sources: `--exclude-sources "comick,hitomi"`. Adjust if you want to exclude more.

---

## 5. Understanding Categories & Status Mapping

If you want statuses to map to categories, first create categories inside Suwayomi (e.g. Reading, Completed, Dropped, On Hold, Plan to Read). Each category has a numeric ID. You can usually find IDs by inspecting the UI or API; if you’re unsure, temporarily add one manga to a category and look at network calls, or keep a small note of ID order.

Example mapping string:

```text
completed=5,reading=2,on_hold=7,dropped=8,plan_to_read=9
```

If a status appears for a manga but is not in the map, that manga just won’t get a status category (unless a default category is added later).

---

## 6. Chapter Read Markers

When enabled, the script tries to:

1. Fetch which chapters you have read on MangaDex.
2. Ask Suwayomi for the list of chapters for that manga.
3. Match by internal MangaDex chapter ID hidden inside the source’s URL/key.
4. Mark them as read (unless you used `--read-chapters-dry-run`).

If you see warnings like `WARN no chapters loaded yet`, run the script again later with only the chapter sync enabled:

```text
run_importer.bat (answer only: base URL, follows Y, user/pass, chapter markers Y, delay 0, dry-run N)
```

The second pass usually catches stragglers.

Chapters that are DMCA removed or deleted cannot be re-marked—they simply don’t exist for the source anymore.

---

## 7. Safety Tips

| Situation | Recommendation |
|-----------|---------------|
| Large libraries (1000+) | Use a dry run first to spot obvious failures. |
| Slow or rate limit errors | Add a throttle (`--throttle 0.1`) or keep the 1-second read-sync delay. |
| Password safety | Change your MangaDex password after import if you typed it in and are worried about someone seeing it. |
| Interrupted run | Just re-run; already added manga will typically be skipped or harmlessly re-added. |
| Many "not found" failures | The manga may be delisted, or title matching needs improvement; rerun later or manually add. |

---

## 8. Advanced Users (Direct Python Command Examples)

Run directly (dry run):

```powershell
python import_mangadex_bookmarks_to_suwayomi.py `
   --base-url http://localhost:4567 `
   --from-follows `
   --md-username YOURUSER `
   --md-password YOURPASS `
   --follows-json mangadex_follows.json `
   --import-reading-status `
   --status-category-map completed=5,reading=2,on_hold=7,dropped=8,plan_to_read=9 `
   --import-read-chapters `
   --read-sync-delay 1 `
   --dry-run
```

Real run (remove `--dry-run`).

Minimal just to import follows:

```powershell
python import_mangadex_bookmarks_to_suwayomi.py --base-url http://localhost:4567 --from-follows --md-username USER --md-password PASS
```

Only chapter sync (after everything already added):

```powershell
python import_mangadex_bookmarks_to_suwayomi.py `
   --base-url http://localhost:4567 `
   --from-follows `
   --md-username USER `
   --md-password PASS `
   --import-read-chapters `
   --read-sync-delay 0
```

Diagnostics pagination (if counts look off):

```powershell
python import_mangadex_bookmarks_to_suwayomi.py `
   --base-url http://localhost:4567 `
   --from-follows `
   --md-username USER `
   --md-password PASS `
   --debug-follows `
   --dry-run `
   --no-progress
```

---

## 8.1 Useful Utilities

- List categories (get IDs you can map to):

```powershell
python import_mangadex_bookmarks_to_suwayomi.py `
   --base-url http://127.0.0.1:4567 `
   --list-categories
```

- Import MangaDex custom lists and map by list name (optional):

```powershell
python import_mangadex_bookmarks_to_suwayomi.py `
   --base-url http://127.0.0.1:4567 `
   --from-follows `
   --md-username USER `
   --md-password PASS `
   --import-lists `
   --lists-category-map "Dropped=7,On Hold=5,Plan to Read=8,Completed=9,Reading=4"
```

- Verify specific MangaDex IDs are in scope (after filters):

```powershell
python import_mangadex_bookmarks_to_suwayomi.py `
   --base-url http://127.0.0.1:4567 `
   --from-follows `
   --md-username USER `
   --md-password PASS `
   --verify-id 123e4567-e89b-12d3-a456-426614174000 `
   --verify-id 765e4321-e89b-12d3-a456-426614174111 `
   --dry-run
```

- Export statuses you fetched to a JSON file (for auditing):

```powershell
python import_mangadex_bookmarks_to_suwayomi.py `
   --base-url http://127.0.0.1:4567 `
   --from-follows `
   --md-username USER `
   --md-password PASS `
   --import-reading-status `
   --export-statuses statuses.json
```

---

## 8.2 Diagnostic Flags

- `--debug-login` Show MangaDex login flow details (never prints your password).
- `--debug-follows` Show MangaDex follows pagination.
- `--debug-status` Print a sample of fetched statuses.
- `--status-endpoint-raw` Dump raw JSON from the MangaDex status endpoint(s).
- `--status-map-debug` Explain status->category mapping decisions.
- `--debug-library` Show Suwayomi library/chapters endpoint attempts and GraphQL choices.

---

## 8.3 Flag Reference (Quick)

- Core: `--base-url`, `--dry-run`, `--no-progress`, `--throttle`, `--category-id`, `--no-title-fallback`
- Suwayomi auth (only if needed): `--auth-mode auto|basic|simple|bearer`, `--username`, `--password`, `--token`, `--insecure`
- MangaDex auth: `--md-username`, `--md-password`, `--md-client-id`, `--md-client-secret`, `--md-2fa`
- Follows: `--from-follows`, `--follows-json`, `--max-follows`, `--debug-follows`
- Reading status: `--import-reading-status`, `--status-category-map`, `--status-default-category`, `--assume-missing-status`, `--ignore-statuses`, `--print-status-summary`, `--debug-status`, `--status-endpoint-raw`, `--status-fallback-single`, `--status-fallback-throttle`, `--export-statuses`, `--include-library-statuses`, `--library-statuses-only`
- Chapter progress: `--import-read-chapters`, `--read-chapters-dry-run`, `--read-sync-delay`, `--max-read-requests-per-minute`
- Lists: `--import-lists`, `--list-lists`, `--lists-category-map`, `--lists-ignore`, `--debug-lists`
- Migration/Rehoming (existing library): `--migrate-library`, `--migrate-threshold-chapters`, `--migrate-sources`, `--migrate-remove`, `--debug-library`
- Rehoming during import (optional path used when MangaDex has 0 chapters): `--rehoming-enabled`, `--rehoming-sources`, `--rehoming-skip-if-chapters-ge`, `--rehoming-remove-mangadex`

Tip: When using PowerShell, line continuation is the backtick (`). In cmd.exe use ^ instead, or put the whole command on one line.

---

## 9. Troubleshooting

| Problem | What You See | Fix |
|---------|--------------|-----|
| Wrong credentials | HTTP 401 / login failed | Re-enter username/password carefully (case-sensitive). |
| Script seems stuck early | No per-item lines yet | It’s still fetching follows; try with `--debug-follows`. |
| Many "WARN no chapters loaded yet" | Chapter sync too early | Re-run only chapter sync later with zero delay. |
| Count mismatch vs MangaDex | WARNING collected X < reported total Y | Update to latest script (pagination fix). |
| Lots of "not found" | Title fallback failing | Manga may be delisted; retry later or manual add. |
| Chapter read markers low | Marked far fewer than expected | Run another chapter-only pass after allowing caching. |
| Batch file closes instantly | Python not installed / crash | Open `cmd`, `cd` to folder, run same command to read the error. |

---

## 10. FAQ

**Q: Will this overwrite anything?**  
No—worst case it re-calls add-to-library on a series already added (harmless).

**Q: Can I stop and resume?**  
Yes. Just run again; already imported series are fine. Read markers will be re-applied to any newly loaded chapters.

**Q: Do I have to share my password?**  
It stays local on your computer. Change it afterward if you’re uneasy.

**Q: Can I map multiple statuses to one category?**  
Yes—just set the same category id for each status in the map.

**Q: How do I find category IDs?**  
Easiest: run the tool with `--list-categories`:

```powershell
python import_mangadex_bookmarks_to_suwayomi.py `
   --base-url http://localhost:4567 `
   --list-categories
```

This prints something like:

```text
Available Categories:
   1: Default
   5: Reading
   7: On Hold
   8: Dropped
   9: Plan to Read
```

Use those numeric IDs in your `--status-category-map`. If that fails, ensure you can access the server and that categories exist.

> NOTE: The PowerShell backtick (`) is the line continuation character in PowerShell. If you are using the older Command Prompt (cmd.exe) instead, replace each backtick with a caret (^) or put the whole command on one line.

---

## 11. Next Improvements (Planned / Optional)

- Session token login (`--md-session`).
- Retry pass for manga whose chapters weren’t loaded in time.
- Export a report file summarizing per-manga chapter sync results.
- GUI wrapper (.exe) version for completely click‑based use.

If you need any of these sooner, ask and they can be added.

---

## 12. Getting Help

If something still doesn’t work:

1. Take a screenshot or copy the last 10 lines of the console (hide your password!).
2. Note the command you ran (again, hide password).
3. Share those details with the maintainer / issue tracker.

---

**You’re done!** Enjoy having your MangaDex library and progress inside Suwayomi.
