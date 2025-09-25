# Refactor Proposal: `import_mangadex_bookmarks_to_suwayomi.py`

## Snapshot of Key Findings

### Functional / Correctness Bugs
- **Early `return` breaks migration loop** – within the global-best migration branch we `return migrated` when the second candidate lacks preferred-language chapters. This exits `main` immediately with a partial count (often a non-zero exit code) and skips the remaining titles.
- **Read-sync token lost when using `--md-login-only`** – `import_ids` only receives `session_token` when `--from-follows` is set, so `--import-read-chapters` + `--md-login-only` silently falls back to no UUID sync.
- **Uninitialized global (`MISSING_REPORT_PATH`)** – modules that call `sync_read_chapters_for_manga` before `main` runs will hit a `NameError`; we should declare it at module scope with a default of `None`.
- **Preference filter ignored in rehome path** – the branch meant to skip non-preferred sources (`if pref and all(...)`) only executes `pass`, so the filter never takes effect.
- **Misleading failure message** – when `add_to_library` fails we print `HTTP True/False`; the numeric code is unavailable, but we should include the status code or message from the response.

### Maintainability / Readability Issues
- The top-level script is ~3.5k lines with several 300+ line functions (`main`, `import_ids`, migration/prune helpers). This makes onboarding and safe changes difficult.
- Globals (`CHAPTER_SYNC_CONF`, `READ_SYNC_DEBUG`, `MISSING_REPORT_PATH`) create implicit coupling between distant functions.
- Duplicated imports (`csv`, `time`) and repeated `requests` logic (MangaDex vs Suwayomi) hint at missing abstraction.
- Multiple sections write the missing-report CSV in slightly different ways; bugs in one path dont surface elsewhere.
- "Debug" markers (e.g. `print("[read-debug] marker...")`) run unconditionally, adding noise.
- Heavy use of `except Exception` swallows actionable errors and complicates debugging.

### Suggested Cleanup Targets
- Normalise API/result-shape parsing (REST & GraphQL) through typed adapters instead of hand-rolled heuristics everywhere.
- Introduce dataclasses or typed dictionaries for CLI-derived config blocks (statuses, lists, sync, migration).
- Improve rate-limit handling and retries by wrapping `requests` calls in resilient helpers.
- Build a consistent logging strategy (Python `logging`) instead of ad-hoc prints & duplicated `try/except` wrappers.

## Proposed Refactor Plan

### Phase 1  Guard Rails & Quick Wins
1. **Bug fixes**
   - Replace the erroneous `return migrated` with a `continue`/branch guard.
   - Always propagate `session_token` to `import_ids` when present.
   - Declare `MISSING_REPORT_PATH: Optional[Path] = None` at module scope.
   - Enforce preferred-source filtering in the rehome branch (`continue` instead of `pass`).
   - Improve failure messaging by capturing `response.status_code`/payload.
2. **Structured logging**
   - Introduce `logging` with debug/info levels and gate the existing print diagnostics behind it.
   - Remove unconditional `[read-debug] marker...` prints.
3. **Housekeeping**
   - Deduplicate imports, add type aliases, and tighten obvious `except Exception` blocks where the failure modes are known.

### Phase 2  Modularise Clients & Config
1. **Client abstraction**
   - Split the monolithic helper set into `MangaDexClient` and `SuwayomiClient` classes (with shared request/retry helpers).
   - Wrap GraphQL handling in a reusable helper that accepts typed documents, handles retries, and normalises error reporting.
2. **Explicit configuration objects**
   - Convert the long argument-passing chains (`status_map`, `lists_membership`, etc.) into `@dataclass` configs passed to services.
   - Store CLI parsing in a small command object; keep `main()` focused on wiring and high-level flow.
3. **CSV/report writer**
   - Centralise missing-report writes in a dedicated component to remove duplication and simplify testing.

### Phase 3  Feature-focused Modules
1. **Import pipeline**
   - Break `import_ids` into composable steps: resolution, add-to-library, category assignment, read-sync, rehome. Each step can then be independently tested/mocked.
2. **Migration & prune utilities**
   - Move migration/prune logic into a separate module with strategy classes (`LibraryMigrator`, `LibraryPruner`) to avoid `main` branching on dozens of flags.
3. **Status & list management**
   - Expose a dedicated status-sync module that handles fetch, filtering, and mapping, reducing duplication across reporting and import flows.

### Phase 4  Testing & Tooling
1. **Unit/functional tests**
   - Add tests for the new service classes using fixtures/mocked responses (e.g. `responses` library) to protect against API regressions.
   - Cover edge cases uncovered above (preferred-source skip, login-only read sync, missing-report writes).
2. **CLI smoke tests**
   - Provide a minimal integration test (maybe via `pytest` + `click.testing.CliRunner`) ensuring main command paths parse and dispatch correctly.

## Risks & Mitigations
- **API variability**: The script currently defends against many REST/GraphQL schema variants. Refactoring must maintain those fallbacks; design typed adapters with optional fields and extensive tests against recorded payloads.
- **Behavioral regression**: Break down large functions incrementally and keep feature flags in place (e.g., migrate/prune) to avoid surprising users.
- **Time cost**: The plan is staged; Phase 1 addresses correctness and developer ergonomics without massive rewrites. Later phases can progress incrementally.

## Next Steps
1. Patch the highlighted bugs and remove noisy debug prints.
2. Introduce logging + module-level defaults, ensuring no behavior change for end users.
3. Draft skeleton classes (`MangaDexClient`, `SuwayomiClient`, `ImportOrchestrator`) and gradually migrate logic into them.
4. Backfill unit tests for the fixed bugs to prevent regressions.

This staged approach fixes immediate reliability issues while laying the groundwork for a maintainable, testable importer.
