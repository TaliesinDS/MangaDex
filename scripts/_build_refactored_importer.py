from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple

SRC = Path("import_mangadex_bookmarks_to_suwayomi.py")
DST = Path("import_mangadex_bookmarks_to_suwayomi_refactored.py")


def apply_replacements(text: str, replacements: Iterable[Tuple[str, str]]) -> str:
    for old, new in replacements:
        if old not in text:
            raise RuntimeError(f"Expected pattern not found in source:\n{old}")
        text = text.replace(old, new)
    return text


def main() -> None:
    text = SRC.read_text(encoding="utf-8")

    replacements = [
        (
            "READ_SYNC_DEBUG: bool = False\n\n# Utility early",
            "READ_SYNC_DEBUG: bool = False\nMISSING_REPORT_PATH: Optional[Path] = None\n\n# Utility early",
        ),
        (
            "self.timeout = request_timeout\n",
            "self.timeout = request_timeout\n        self.last_status: Optional[int] = None\n",
        ),
        (
            "resp = self.sess.request(method, url, headers=headers, verify=self.verify, **kwargs)\n",
            "resp = self.sess.request(method, url, headers=headers, verify=self.verify, **kwargs)\n        self.last_status = resp.status_code\n",
        ),
        (
            """            else:\n                failed += 1\n                failures.append((md, f\"add_to_library HTTP {ok}\"))\n                if show_progress:\n                    print(f\"{prefix}FAIL add {md}\")""",
            """            else:\n                failed += 1\n                status = getattr(client, \"last_status\", None)\n                failures.append((md, f\"add_to_library status {status if status is not None else 'unknown'}\"))\n                if show_progress:\n                    print(f\"{prefix}FAIL add {md} (status {status if status is not None else 'unknown'})\")""",
        ),
        (
            "session_token=session_token if args.from_follows else None",
            "session_token=session_token",
        ),
        (
            """                                if pref and all(f not in nm for f in pref):\n                                    # if preferences specified, skip non-matching sources unless we exhausted all\n                                    pass""",
            """                                if pref and all(f not in nm for f in pref):\n                                    if show_progress:\n                                        print(f\"{prefix}REHOME skip {src.get('name')!r} (outside preferred list)\")\n                                    continue""",
        ),
    ]

    text = apply_replacements(text, replacements)
    text = text.replace("return migrated", "continue")

    debug_blocks = [
        (
            "    try:\n        print(\"[read-debug] marker: after missing_report setup\", flush=True)\n    except Exception:\n        pass",
            "    if READ_SYNC_DEBUG:\n        try:\n            print(\"[read-debug] marker: after missing_report setup\", flush=True)\n        except Exception:\n            pass",
        ),
        (
            "    try:\n        print(\"[read-debug] marker: entering report/sync prelude\", flush=True)\n    except Exception:\n        pass",
            "    if READ_SYNC_DEBUG:\n        try:\n            print(\"[read-debug] marker: entering report/sync prelude\", flush=True)\n        except Exception:\n            pass",
        ),
        (
            "    try:\n        print(f\"[read-debug] marker: no_add_library={bool(args.no_add_library)}\", flush=True)\n    except Exception:\n        pass",
            "    if READ_SYNC_DEBUG:\n        try:\n            print(f\"[read-debug] marker: no_add_library={bool(args.no_add_library)}\", flush=True)\n        except Exception:\n            pass",
        ),
        (
            "    try:\n        print(f\"[read-debug] about to branch on no_add_library={bool(args.no_add_library)}\", flush=True)\n    except Exception:\n        pass",
            "    if READ_SYNC_DEBUG:\n        try:\n            print(f\"[read-debug] about to branch on no_add_library={bool(args.no_add_library)}\", flush=True)\n        except Exception:\n            pass",
        ),
        (
            "    try:\n        print(f\"[read-debug] session_token present: {bool(session_token)}; starting reporting+sync if True\", flush=True)\n    except Exception:\n        pass",
            "    if READ_SYNC_DEBUG:\n        try:\n            print(f\"[read-debug] session_token present: {bool(session_token)}; starting reporting+sync if True\", flush=True)\n        except Exception:\n            pass",
        ),
        (
            "    try:\n        print(f\"[read-debug] MangaDex source id: {md_source_id}\", flush=True)\n    except Exception:\n        pass",
            "    if READ_SYNC_DEBUG:\n        try:\n            print(f\"[read-debug] MangaDex source id: {md_source_id}\", flush=True)\n        except Exception:\n            pass",
        ),
    ]

    for old, new in debug_blocks:
        text = text.replace(old, new)

    DST.write_text(text, encoding="utf-8")
    print(f"Wrote {DST}")


if __name__ == "__main__":
    main()
