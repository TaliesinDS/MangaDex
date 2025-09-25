# Automated Test Proposal for the MangaDex → Suwayomi Importer

## 1. Objectives
- Verify every feature described in `USER_MANUAL.md` and surfaced through `gui_launcher_tk.py` works as expected.
- Provide confidence that refactors (e.g., `import_mangadex_bookmarks_to_suwayomi_refactored.py`) remain behavior-compatible with the original importer.
- Allow the full suite to be executed directly inside VS Code (Python Test Explorer / `pytest` integration) without dropping to an external PowerShell session.
- Document a roadmap for incrementally delivering coverage, starting with high-value “happy paths” and expanding into edge cases and regression guards.

## 2. Scope & Assumptions
- We will treat the CLI script as the system under test (SUT); GUI coverage focuses on argument construction and safety toggles rather than full Tkinter UI automation.
- External services (MangaDex, Suwayomi) will be simulated. No live network access is required.
- Tests should run on Windows, macOS, and Linux, using the repo’s virtual environment (`.venv`) managed through VS Code.
- Optional dependencies (e.g., `pandas` for Excel ingestion) will be installed for the test environment to ensure those code paths can be exercised.

## 3. Tooling Stack
| Purpose | Tool / Library | Notes |
| --- | --- | --- |
| Test runner | `pytest` | Native integration with VS Code Test Explorer. |
| HTTP stubbing | `responses` (or `requests-mock`) | Intercepts `requests` calls to MangaDex/Suwayomi APIs. |
| Structured fake servers | `pytest-httpserver` | For scenarios needing stateful REST/GraphQL sequences (e.g., migration loops). |
| Data factories | `factory_boy` or simple fixtures | Generate MangaDex and Suwayomi payloads. |
| Time control | `freezegun` or monkeypatching `time.sleep` | Avoid real throttling delays. |
| Coverage | `coverage.py` with `pytest-cov` | Optional, to feed quality gates. |
| GUI logic tests | `pytest` + `tkinter` fixtures | Use hidden root (`tk.Tk().withdraw()`) for argument-building tests. |

_Dev-dependency additions_ (in `requirements-dev.txt` or similar):
```
pytest
pytest-cov
responses
pytest-httpserver
freezegun
factory_boy
```

## 4. Test Architecture
1. **Unit Tests (fast)**
   - Pure helpers: title normalization, token extraction, fraction handling, chapter canonicalization, ID parsing.
   - Input readers (`read_any`) against sample text/json/csv/xlsx fixtures.
   - `SuwayomiClient` helper methods with mocked `requests.Session`.
   - GUI command assembly/preset toggles.

2. **Service Contract Tests**
   - Validate `SuwayomiClient` request/response handling under varied payload shapes (GraphQL vs REST fallbacks).
   - Verify MangaDex login, follows fetch, status retrieval, and list APIs handle error codes, pagination, throttling.
   - Ensure read-sync logic respects throttle, delay, `--only-if-ahead`, and missing-report writes.

3. **Command-Level Scenario Tests**
   - Invoke `main()` with synthetic CLI arguments, capturing stdout/stderr.
   - Use `responses` / `pytest-httpserver` to emulate Suwayomi & MangaDex behaviour for:
     - Follows import + category mapping.
     - Reading status mapping (including ignored statuses, default category).
     - Read-chapter sync: UUID hits, number fallback, across sources.
     - Rehoming and migration flows (best-source scoring, preferred languages, removal toggles).
     - Prune modes (thresholds, language filters).
     - Library/status export/report writing.
     - Listing commands (`--list-categories`, `--list-library-titles`).
   - Assert on side effects (CSV contents, JSON exports, library add/remove calls).

4. **Regression & Configuration Tests**
   - Compare legacy vs refactored importer outputs for identical mocked inputs (golden-file diff of requests/responses and generated artifacts).
   - GUI preset smoke tests ensuring generated CLI args exercise scenarios covered by CLI tests.

## 5. Fixture & Data Design
- `tests/fixtures/mangadex/` — JSON fixtures for follows, statuses, lists, read history.
- `tests/fixtures/suwayomi/` — Library payloads, chapter listings, search results, category lists.
- `tests/data/input/` — Sample text/csv/json/xlsx ID sources (tiny size, hand-crafted).
- Reusable factory functions for building varied source entries, categories, chapter states.
- Utility fixture to create temporary directories/files so report outputs can be inspected without polluting the repo.

## 6. Feature Coverage Matrix (excerpt)
| Feature Block | Key Flags/Behaviours | Planned Tests |
| --- | --- | --- |
| ID ingestion | File formats, de-duplication, merge with follows/library statuses | Unit + scenario tests with mixed sources. |
| MangaDex auth | `--from-follows`, `--md-login-only`, `--md-client` secrets, 2FA, failure modes | Mocked login endpoints returning success/401/429. |
| Follows merge | Order preservation, `--verify-id`, `--max-follows`, `--follows-json` output | CLI scenario verifying stdout, JSON file contents. |
| Reading status | Map, default, ignore, fallback single fetch | Scenario tests asserting category add calls and exported JSON if requested. |
| Custom lists | `--import-lists`, `--list-lists`, ignores | Sequence hitting list endpoints, verifying membership merge. |
| Read sync | UUID vs number fallback, across sources opt-in, missing report, dry-run, rpm throttle enforcement | Parameterized CLI tests measuring call counts & CSV records. |
| Rehoming | Preferred sources, exclusion list, `best_source` scoring, removal toggles | Multi-step fake search responses verifying add/remove actions. |
| Migration | Category filters, timeout/second page, preferred languages, keep-both | Complex scenario using `pytest-httpserver`. |
| Prune modes | Threshold, language filters, fallback keep-most | Validate remove calls & output messaging. |
| Reporting | `--missing-report`, `--export-statuses` contents | File assertions. |
| Library listing | `--list-categories`, `--list-library-titles`, filtering | CLI output snapshot tests. |
| GUI behaviour | Argument synthesis, preset application, destructive warnings, config persistence | Tkinter-based unit tests. |

A full matrix will be maintained in `docs/testing_matrix.csv` once implementation starts.

## 7. Execution in VS Code
1. Add a `tests/` package with `__init__.py` and the fixtures structure above.
2. Configure VS Code:
   - `.vscode/settings.json`:
     ```json
     {
       "python.testing.pytestEnabled": true,
       "python.testing.pytestArgs": ["tests"],
       "python.testing.unittestEnabled": false,
       "python.testing.autoTestDiscoverOnSaveEnabled": true
     }
     ```
   - Optional `launch.json` entry for `pytest` debugging.
3. Provide a convenience task (`.vscode/tasks.json`) called “Run importer tests” executing `python -m pytest --maxfail=1`.
4. Document the workflow in `TESTING.md` (new section) so contributors can press **Run All Tests** inside VS Code.

## 8. Incremental Delivery Plan
1. **Week 1** — Establish scaffolding: dependencies, VS Code config, base fixtures, unit tests for helpers & input readers.
2. **Week 2** — Implement MangaDex/Suwayomi contract stubs; cover follows import, status mapping, read-sync UUID path.
3. **Week 3** — Expand to migration/rehoming/prune scenarios, plus reporting outputs.
4. **Week 4** — GUI argument builder tests, cross-source read sync edge cases, coverage targets, refactor parity checks.
5. Continuous — Add regression cases whenever new CLI flags or GUI toggles ship.

## 9. Risks & Mitigations
- **Complex API variability** — Capture multiple payload shapes from real servers and encode them as fixtures to avoid false negatives.
- **Test flakiness due to timing** — Replace `time.sleep` with patched versions; configure throttling logic to respect mock timers.
- **Fixture drift vs manual** — Maintain the coverage matrix and update fixtures when manual/GUI documentation changes.
- **Large scenario permutations** — Use parametrized tests and shared factories to keep runtime manageable (< 2 minutes on CI workstations).

## 10. Next Steps
- Approve tooling additions and directory structure.
- Create `requirements-dev.txt` (or Poetry extras) capturing test dependencies.
- Implement scaffolding PR: add `tests/` skeleton, VS Code settings, sample fixture, first helper unit test.
- Track progress via GitHub Projects / issues aligned with the incremental delivery roadmap.

Once the scaffolding lands, the suite can grow alongside features, ensuring the importer remains reliable and the GUI instructions stay truthful.
