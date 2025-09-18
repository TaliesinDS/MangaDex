import re
import sys
import json
import csv
import argparse
import os
import getpass
import time
from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Dict, Any

try:
    import pandas as pd  # Optional, only used for xlsx/csv convenience
except Exception:
    pd = None

import requests

# MangaDex API base (public)
MANGADEX_API = "https://api.mangadex.org"

# Utility early so helper functions can use it
def truncate_text(t: str, limit: int = 200) -> str:
    t = (t or "").replace('\n', ' ')[:limit]
    return t + ("..." if len(t) == limit else "")

# --- Helpers: detect MangaDex IDs/URLs ---
MD_ID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
MD_URL_RE = re.compile(r"https?://(www\.)?mangadex\.org/title/([0-9a-fA-F-]{36})(?:/|$)")


def extract_mangadex_ids(text: str) -> List[str]:
    ids = []
    for url_match in MD_URL_RE.finditer(text):
        ids.append(url_match.group(2))
    for id_match in MD_ID_RE.finditer(text):
        ids.append(id_match.group(0))
    # de-dup preserving order
    seen = set()
    uniq: List[str] = []
    for x in ids:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


# --- Input parsing ---

def read_any(path: Path) -> List[str]:
    suffix = path.suffix.lower()
    data: List[str] = []
    if suffix in {".txt", ".log", ".md", ".html", ".htm"}:
        text = path.read_text(encoding="utf-8", errors="ignore")
        data = extract_mangadex_ids(text)
    elif suffix in {".json"}:
        obj = json.loads(path.read_text(encoding="utf-8"))
        def walk(o: Any):
            if isinstance(o, str):
                for i in extract_mangadex_ids(o):
                    yield i
            elif isinstance(o, dict):
                for v in o.values():
                    yield from walk(v)
            elif isinstance(o, list):
                for v in o:
                    yield from walk(v)
        data = list(dict.fromkeys(walk(obj)))
    elif suffix in {".csv"}:
        # try simple pass-through first
        with path.open(newline='', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f)
            buf: List[str] = []
            for row in reader:
                for cell in row:
                    buf.extend(extract_mangadex_ids(str(cell)))
        # unique preserve order
        data = list(dict.fromkeys(buf))
    elif suffix in {".xlsx", ".xls"}:
        if pd is None:
            raise SystemExit("pandas/openpyxl are required for Excel files. Install with: python -m pip install pandas openpyxl")
        buf: List[str] = []
        # Read all sheets
        xls = pd.read_excel(path, sheet_name=None, dtype=str)
        for _, df in xls.items():
            for val in df.astype(str).to_numpy().flatten():
                buf.extend(extract_mangadex_ids(str(val)))
        data = list(dict.fromkeys(buf))
    else:
        # Fallback: treat as text
        text = path.read_text(encoding="utf-8", errors="ignore")
        data = extract_mangadex_ids(text)
    return data


# --- Suwayomi client ---

class SuwayomiClient:
    def __init__(self, base_url: str, auth_mode: str = "auto", username: Optional[str] = None, password: Optional[str] = None, token: Optional[str] = None, verify_tls: bool = True):
        self.base_url = base_url.rstrip('/')
        self.sess = requests.Session()
        self.verify = verify_tls
        self.headers: Dict[str, str] = {}
        self.auth_mode = auth_mode
        self.username = username
        self.password = password
        self.token = token

    def _auth(self):
        # Modes: basic, simple, bearer, auto
        if self.auth_mode == "bearer" and self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"
        elif self.auth_mode == "basic" and self.username and self.password:
            self.sess.auth = (self.username, self.password)
        elif self.auth_mode == "simple" and self.username and self.password:
            # Perform form login to set session cookie
            # POST /login.html with user=, pass=
            resp = self.sess.post(f"{self.base_url}/login.html", data={"user": self.username, "pass": self.password}, allow_redirects=False, verify=self.verify)
            if resp.status_code not in (200, 302, 303, 303):
                raise RuntimeError(f"Simple login failed: HTTP {resp.status_code}")
        elif self.auth_mode == "auto":
            # try bearer first, then basic, then simple
            if self.token:
                self.headers["Authorization"] = f"Bearer {self.token}"
            elif self.username and self.password:
                # try basic; fallback to simple if 401
                self.sess.auth = (self.username, self.password)
            # else unauth

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        headers = dict(self.headers)
        headers.update(kwargs.pop("headers", {}) or {})
        resp = self.sess.request(method, url, headers=headers, verify=self.verify, **kwargs)
        # Fallback: if 401 with basic on auto, try SIMPLE login
        if resp.status_code == 401 and self.auth_mode == "auto" and self.username and self.password:
            # try simple login once
            login = self.sess.post(f"{self.base_url}/login.html", data={"user": self.username, "pass": self.password}, allow_redirects=False, verify=self.verify)
            if login.status_code in (200, 302, 303):
                resp = self.sess.request(method, url, headers=headers, verify=self.verify, **kwargs)
        return resp

    # API helpers
    def get_sources(self) -> List[Dict[str, Any]]:
        r = self.request("GET", "/api/v1/source/list")
        r.raise_for_status()
        return r.json()

    def search_source(self, source_id: int, query: str, page: int = 1) -> Dict[str, Any]:
        r = self.request("GET", f"/api/v1/source/{source_id}/search", params={"searchTerm": query, "pageNum": page})
        r.raise_for_status()
        return r.json()

    def add_to_library(self, manga_id: int) -> bool:
        r = self.request("GET", f"/api/v1/manga/{manga_id}/library")
        return r.status_code == 200

    def add_manga_to_category(self, manga_id: int, category_id: int) -> bool:
        # Endpoint adds manga to category via GET per server API design
        r = self.request("GET", f"/api/v1/manga/{manga_id}/category/{category_id}")
        return r.status_code == 200


# --- Import logic ---

def find_mangadex_source_id(sources: List[Dict[str, Any]]) -> Optional[int]:
    for s in sources:
        name = (s.get("name") or "").lower()
        apk = (s.get("apkName") or "").lower()
        # Mangadex source typically has name like "MangaDex" and package containing "mangadex"
        if "mangadex" in name or "mangadex" in apk:
            return int(s["id"]) if "id" in s else None
    return None


def search_by_mangadex_id(client: SuwayomiClient, source_id: int, md_id: str) -> Optional[int]:
    """Attempt direct UUID search in source. Returns manga_id or None."""
    try:
        resp = client.search_source(source_id, md_id, page=1)
    except Exception:
        return None
    items = resp.get("mangaList") or resp.get("mangaListData") or resp.get("manga_list") or []
    for it in items:
        url = str(it.get("url", ""))
        if md_id in url:
            return int(it.get("id"))
    for it in items:
        if str(it.get("key", "")) == md_id:
            return int(it.get("id"))
    return None


def fetch_title_from_mangadex(md_id: str) -> Optional[str]:
    """Fetch canonical English (or first available) title from MangaDex API."""
    try:
        r = requests.get(f"{MANGADEX_API}/manga/{md_id}", timeout=12)
        if r.status_code != 200:
            return None
        data = r.json().get("data") or {}
        attrs = data.get("attributes", {})
        titles = attrs.get("title") or {}
        # Prefer 'en', else first
        if "en" in titles:
            return titles["en"].strip()
        if titles:
            return next(iter(titles.values())).strip()
        alt_titles = attrs.get("altTitles") or []
        for alt in alt_titles:
            for v in alt.values():
                return v.strip()
    except Exception:
        return None
    return None


def search_by_title(client: SuwayomiClient, source_id: int, title: str) -> Optional[int]:
    """Search source by title text and attempt fuzzy containment match."""
    if not title:
        return None
    try:
        resp = client.search_source(source_id, title, page=1)
    except Exception:
        return None
    items = resp.get("mangaList") or resp.get("mangaListData") or resp.get("manga_list") or []
    norm_title = title.lower()
    best: Optional[int] = None
    best_len_diff = 10**9
    for it in items:
        t = str(it.get("title") or it.get("name") or "").lower()
        if not t:
            continue
        if norm_title == t:
            return int(it.get("id"))
        if norm_title in t or t in norm_title:
            # pick closest length difference as heuristic
            diff = abs(len(t) - len(norm_title))
            if diff < best_len_diff:
                best_len_diff = diff
                best = int(it.get("id"))
    return best


def import_ids(
    client: SuwayomiClient,
    ids: List[str],
    dry_run: bool = False,
    use_title_fallback: bool = True,
    show_progress: bool = True,
    throttle: float = 0.0,
    category_id: Optional[int] = None,
    reading_statuses: Optional[Dict[str, str]] = None,
    status_category_map: Optional[Dict[str, int]] = None,
    status_default_category: Optional[int] = None,
    session_token: Optional[str] = None,
    chapter_sync_conf: Optional[Dict[str, Any]] = None,
    status_map_debug: bool = False,
    assume_missing_status: Optional[str] = None,
) -> Tuple[int, int, List[Tuple[str, str]]]:
    client._auth()
    sources = client.get_sources()
    source_id = find_mangadex_source_id(sources)
    if not source_id:
        raise SystemExit("Could not find MangaDex source. Ensure the MangaDex extension is installed and enabled in Suwayomi.")

    added = 0
    failed = 0
    failures: List[Tuple[str, str]] = []

    total = len(ids)
    for idx, md in enumerate(ids, 1):
        prefix = f"[{idx}/{total}] " if show_progress else ""
        try:
            manga_id = search_by_mangadex_id(client, source_id, md)
            fetched_title: Optional[str] = None
            if manga_id is None and use_title_fallback:
                fetched_title = fetch_title_from_mangadex(md)
                if fetched_title:
                    manga_id = search_by_title(client, source_id, fetched_title)
            if manga_id is None:
                failures.append((md, "not found (uuid + title fallback failed)" if use_title_fallback else "not found"))
                failed += 1
                if show_progress:
                    print(f"{prefix}FAIL {md} {('- ' + fetched_title) if fetched_title else ''}".rstrip())
                continue
            if dry_run:
                # Simulate status mapping output if requested (even if status missing)
                if status_map_debug and status_category_map:
                    raw_status = (reading_statuses.get(md, '') if reading_statuses else '')
                    eff_status = (raw_status or assume_missing_status or '').lower()
                    display_status = raw_status or (assume_missing_status and f"(assumed {assume_missing_status})") or '(none)'
                    target_cat = None
                    via = ''
                    if eff_status:
                        target_cat = status_category_map.get(eff_status)
                        via = 'map'
                        if target_cat is None and status_default_category is not None:
                            target_cat = status_default_category
                            via = 'default'
                        if target_cat is None and raw_status == '' and assume_missing_status and status_category_map.get(assume_missing_status.lower()):
                            target_cat = status_category_map.get(assume_missing_status.lower())
                            via = 'assumed'
                    if show_progress:
                        if target_cat is not None:
                            print(f"{prefix}STATUS {display_status} -> cat {target_cat} ({via}) (dry-run)")
                        else:
                            print(f"{prefix}STATUS {display_status} -> no mapping (dry-run)")
                added += 1
                if show_progress:
                    print(f"{prefix}OK (dry-run) {md}")
                continue
            ok = client.add_to_library(manga_id)
            if ok:
                cat_result = True
                # Apply explicit category first
                if category_id is not None:
                    cat_result = client.add_manga_to_category(manga_id, category_id)
                # Apply status-based category mapping
                if (reading_statuses or assume_missing_status) and status_category_map:
                    raw_status = (reading_statuses.get(md, '') if reading_statuses else '')
                    eff_status = (raw_status or assume_missing_status or '').lower()
                    if eff_status:
                        target_cat = status_category_map.get(eff_status)
                        resolved_via = 'map'
                        if target_cat is None and status_default_category is not None:
                            target_cat = status_default_category
                            resolved_via = 'default'
                        if target_cat is None and raw_status == '' and assume_missing_status and status_category_map.get(assume_missing_status.lower()):
                            target_cat = status_category_map.get(assume_missing_status.lower())
                            resolved_via = 'assumed'
                        if target_cat is not None:
                            try:
                                cat_ok = client.add_manga_to_category(manga_id, target_cat)
                                if status_map_debug and show_progress:
                                    display_status = raw_status or f"(assumed {assume_missing_status})"
                                    print(f"{prefix}STATUS {display_status} -> cat {target_cat} ({resolved_via}) {'OK' if cat_ok else 'FAIL'}")
                            except Exception as sm_e:
                                if status_map_debug and show_progress:
                                    print(f"{prefix}STATUS {eff_status} -> cat {target_cat} ERROR {sm_e}")
                        else:
                            if status_map_debug and show_progress:
                                display_status = raw_status or '(none)'
                                print(f"{prefix}STATUS {display_status} -> no mapping applied")
                # Chapter read sync (per manga) optionally delayed
                if chapter_sync_conf and chapter_sync_conf.get('enabled') and session_token:
                    delay = chapter_sync_conf.get('delay') or 0
                    if delay > 0:
                        time.sleep(delay)
                    try:
                        sync_read_chapters_for_manga(
                            client=client,
                            session_token=session_token,
                            manga_md_id=md,
                            manga_internal_id=manga_id,
                            dry_run=chapter_sync_conf.get('dry_run', False),
                            rpm=chapter_sync_conf.get('rpm', 300),
                            show_progress=show_progress,
                            prefix=prefix
                        )
                    except Exception as ce:
                        if show_progress:
                            print(f"{prefix}WARN chapters {md}: {ce}")
                added += 1
                if show_progress:
                    if category_id is not None:
                        print(f"{prefix}OK added {md} (category {'ok' if cat_result else 'fail'})")
                    else:
                        print(f"{prefix}OK added {md}")
            else:
                failed += 1
                failures.append((md, f"add_to_library HTTP {ok}"))
                if show_progress:
                    print(f"{prefix}FAIL add {md}")
        except Exception as e:
            failed += 1
            failures.append((md, str(e)))
            if show_progress:
                print(f"{prefix}ERROR {md}: {e}")
        if throttle > 0:
            time.sleep(throttle)
    return added, failed, failures

# ---------------- MangaDex follows helpers (defined BEFORE main so they exist when called) ---------------- #

def login_mangadex(username: str, password: str) -> Optional[str]:
    """Return session token or None (legacy simple version kept for backward compat calls)."""
    token, _ = login_mangadex_verbose(username=username, password=password)
    return token


def login_mangadex_verbose(
    username: str,
    password: str,
    two_factor: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    debug: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    """Enhanced login returning (session_token, error_message)."""
    try:
        payload: Dict[str, Any] = {
            "username": (username or "").strip(),
            "password": (password or ""),
        }
        if two_factor:
            payload["code"] = two_factor.strip()
        # MangaDex currently does not require client id/secret for basic auth/login, but keep for future
        headers = {"Content-Type": "application/json", "User-Agent": "SuwayomiImporter/1.0"}
        r = requests.post(f"{MANGADEX_API}/auth/login", json=payload, headers=headers, timeout=20)
        if r.status_code != 200:
            msg = f"HTTP {r.status_code}: {truncate_text(r.text)}"
            if debug:
                print(f"[login debug] Login failed: {msg}")
            return None, msg
        data = r.json()
        token = ((data.get("token") or {}).get("session"))
        if not token:
            if debug:
                print(f"[login debug] No session token field in response: keys={list(data.keys())}")
            return None, "No session token in response"
        return token, None
    except Exception as e:
        if debug:
            print(f"[login debug] Exception during login: {e}")
        return None, str(e)


def fetch_all_follows(session_token: str) -> List[Dict[str, Any]]:
    # Legacy simple version kept for backward compatibility; wraps new function with defaults
    return fetch_all_follows_adv(session_token=session_token)


def fetch_all_follows_adv(session_token: str, debug: bool = False, max_follows: Optional[int] = None, pause: float = 0.2) -> List[Dict[str, Any]]:
    headers = {"Authorization": f"Bearer {session_token}"}
    limit = 100
    offset = 0
    results: List[Dict[str, Any]] = []
    total_reported: Optional[int] = None
    consecutive_failures = 0
    while True:
        if max_follows is not None and len(results) >= max_follows:
            if debug:
                print(f"[follows debug] Reached max_follows={max_follows}, stopping early")
            break
        params = {"limit": limit, "offset": offset}
        try:
            r = requests.get(f"{MANGADEX_API}/user/follows/manga", params=params, headers=headers, timeout=25)
        except Exception as e:
            consecutive_failures += 1
            if debug:
                print(f"[follows debug] Exception offset={offset}: {e}")
            if consecutive_failures >= 3:
                break
            time.sleep(1.0 * consecutive_failures)
            continue
        if r.status_code != 200:
            consecutive_failures += 1
            if debug:
                print(f"[follows debug] HTTP {r.status_code} at offset={offset}: {truncate_text(r.text, 120)} (failure {consecutive_failures})")
            if consecutive_failures >= 3:
                break
            time.sleep(1.0 * consecutive_failures)
            continue
        consecutive_failures = 0
        js = r.json()
        data = js.get("data") or []
        limit_returned = js.get("limit") or len(data)
        total_reported = js.get("total") if total_reported is None else total_reported
        if debug:
            tr = f" total={total_reported}" if total_reported is not None else ""
            print(f"[follows debug] Page offset={offset} got={len(data)} limit={limit_returned}{tr} accum={len(results)}")
        if not data:
            # No more data
            break
        before_add = len(results)
        for entry in data:
            mid = entry.get("id")
            attrs = (entry.get("attributes") or {})
            titles = (attrs.get("title") or {})
            title = titles.get("en") or (next(iter(titles.values())) if titles else "")
            results.append({"id": mid, "title": title})
            if max_follows is not None and len(results) >= max_follows:
                break
        added_now = len(results) - before_add
        if debug:
            print(f"[follows debug] Added {added_now} this page; new_total={len(results)}")
        if total_reported is not None and len(results) >= total_reported:
            # Collected all
            break
        # Increment offset by actual number of items received to avoid gaps when a page is short
        offset += len(data)
        # Safety: if API stops increasing offset effectively
        if offset > 10000:  # arbitrary guard to avoid infinite loop
            if debug:
                print("[follows debug] Offset exceeded safety guard; stopping")
            break
        time.sleep(pause)
    if debug:
        if total_reported is not None and len(results) < total_reported:
            print(f"[follows debug] WARNING collected {len(results)} < reported total {total_reported}")
        print(f"[follows debug] Finished follows fetch: {len(results)} items")
    return results


def fetch_reading_statuses(session_token: str, manga_ids: List[str]) -> Dict[str, str]:
    """Fetch reading status for given MangaDex manga ids.
    MangaDex offers bulk endpoint: GET /manga/status?ids[]=... but to avoid very long URLs we batch.
    Returns dict md_uuid -> status (lowercase)."""
    headers = {"Authorization": f"Bearer {session_token}"}
    result: Dict[str, str] = {}
    batch = 50
    for i in range(0, len(manga_ids), batch):
        subset = manga_ids[i:i+batch]
        try:
            params = []
            for mid in subset:
                params.append(("ids[]", mid))
            r = requests.get(f"{MANGADEX_API}/manga/status", params=params, headers=headers, timeout=20)
            if r.status_code != 200:
                continue
            data = r.json().get('statuses') or {}
            for k, v in data.items():
                if isinstance(v, str):
                    result[k] = v.lower()
        except Exception:
            continue
        time.sleep(0.15)
    return result


def fetch_single_status(session_token: str, manga_id: str) -> Optional[str]:
    """Fetch status for a single manga via /manga/{id}/status endpoint. Returns lowercase status or None."""
    headers = {"Authorization": f"Bearer {session_token}"}
    try:
        r = requests.get(f"{MANGADEX_API}/manga/{manga_id}/status", headers=headers, timeout=12)
        if r.status_code != 200:
            return None
        js = r.json()
        # Spec shows { result: ok, status: <value|null> }
        val = js.get('status')
        if isinstance(val, str) and val:
            return val.lower()
        return None
    except Exception:
        return None


def fetch_suwayomi_chapters(client: SuwayomiClient, manga_internal_id: int) -> List[Dict[str, Any]]:
    try:
        r = client.request("GET", f"/api/v1/manga/{manga_internal_id}/chapters")
        if r.status_code != 200:
            return []
        js = r.json()
        # adaptive: look for list keys
        if isinstance(js, list):
            return js
        for key in ("chapters", "chapterList", "data"):
            if key in js and isinstance(js[key], list):
                return js[key]
        return []
    except Exception:
        return []


MD_CHAPTER_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def extract_chapter_uuid_from_item(item: Dict[str, Any]) -> Optional[str]:
    for field in ("url", "key", "chapterUrl", "sourceUrl"):
        v = item.get(field)
        if not v:
            continue
        m = MD_CHAPTER_UUID_RE.search(str(v))
        if m:
            return m.group(0)
    return None


def mark_chapter_read(client: SuwayomiClient, chapter_internal_id: int) -> bool:
    # Try GET first
    r = client.request("GET", f"/api/v1/chapter/{chapter_internal_id}/read")
    if r.status_code == 200:
        return True
    # Try POST fallback
    r2 = client.request("POST", f"/api/v1/chapter/{chapter_internal_id}/read")
    return r2.status_code == 200


def fetch_mangadex_read_chapters(session_token: str, manga_md_id: str) -> List[str]:
    headers = {"Authorization": f"Bearer {session_token}"}
    try:
        r = requests.get(f"{MANGADEX_API}/manga/{manga_md_id}/read", headers=headers, timeout=20)
        if r.status_code != 200:
            return []
        data = r.json().get('data') or []
        return [c for c in data if isinstance(c, str)]
    except Exception:
        return []


def sync_read_chapters_for_manga(
    client: SuwayomiClient,
    session_token: str,
    manga_md_id: str,
    manga_internal_id: int,
    dry_run: bool,
    rpm: int,
    show_progress: bool,
    prefix: str,
) -> None:
    md_read = fetch_mangadex_read_chapters(session_token, manga_md_id)
    if not md_read:
        return
    su_chapters = fetch_suwayomi_chapters(client, manga_internal_id)
    if not su_chapters:
        if show_progress:
            print(f"{prefix}WARN no chapters loaded yet for {manga_md_id}")
        return
    uuid_to_internal: Dict[str, int] = {}
    for ch in su_chapters:
        cid = ch.get('id') or ch.get('chapterId') or ch.get('chapter_id')
        try:
            cid_int = int(cid)
        except Exception:
            continue
        md_uuid = extract_chapter_uuid_from_item(ch)
        if md_uuid:
            uuid_to_internal[md_uuid.lower()] = cid_int
    # throttle calculations
    min_interval = 60.0 / rpm if rpm > 0 else 0
    last_time = 0.0
    marked = 0
    missing = 0
    for md_uuid in md_read:
        internal = uuid_to_internal.get(md_uuid.lower())
        if not internal:
            missing += 1
            continue
        if dry_run:
            marked += 1
            continue
        now = time.time()
        if min_interval > 0 and (now - last_time) < min_interval:
            time.sleep(min_interval - (now - last_time))
        ok = mark_chapter_read(client, internal)
        last_time = time.time()
        if ok:
            marked += 1
    if show_progress:
        print(f"{prefix}Chapters sync {manga_md_id}: markable={len(md_read)} marked={marked} missing={missing}")


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Import MangaDex bookmarks / follows into Suwayomi library.")
    p.add_argument("input_file", type=Path, nargs="?", help="Optional path to bookmarks file (txt/csv/xlsx/json/html). Omit when using --from-follows only.")
    p.add_argument("--base-url", required=True, help="Suwayomi base URL, e.g. http://localhost:4567")
    p.add_argument("--auth-mode", choices=["auto", "basic", "simple", "bearer"], default="auto")
    p.add_argument("--username", help="Username for BASIC or SIMPLE login (if applicable)")
    p.add_argument("--password", help="Password for BASIC or SIMPLE login (if applicable)")
    p.add_argument("--token", help="Bearer token for UI_LOGIN mode (Settings -> API Tokens)")
    p.add_argument("--insecure", action="store_true", help="Disable TLS certificate verification")
    p.add_argument("--dry-run", action="store_true", help="Do not modify library, just simulate")
    p.add_argument("--no-title-fallback", action="store_true", help="Disable title lookup fallback via MangaDex API when direct UUID search fails")
    p.add_argument("--no-progress", action="store_true", help="Disable per-item progress output")
    p.add_argument("--throttle", type=float, default=0.0, help="Sleep seconds between items (avoid rate limits)")
    p.add_argument("--category-id", type=int, help="Optional Suwayomi category id to assign each added manga")
    # Follows fetch options
    p.add_argument("--from-follows", action="store_true", help="Fetch followed manga from MangaDex for the authenticated user and include them")
    p.add_argument("--follows-json", type=Path, help="Write fetched follows (id + title) to this JSON file")
    p.add_argument("--md-username", help="MangaDex username (or set MANGADEX_USERNAME env)")
    p.add_argument("--md-password", help="MangaDex password (or set MANGADEX_PASSWORD env). If omitted and needed, you'll be prompted.")
    p.add_argument("--md-client-id", help="MangaDex client id (optional; or env MANGADEX_CLIENT_ID)")
    p.add_argument("--md-client-secret", help="MangaDex client secret (optional; or env MANGADEX_CLIENT_SECRET)")
    p.add_argument("--md-2fa", help="MangaDex 2FA/OTP code if your account has 2FA enabled")
    p.add_argument("--debug-login", action="store_true", help="Print diagnostic details if MangaDex login fails (redacts password)")
    p.add_argument("--debug-follows", action="store_true", help="Verbose pagination diagnostics for follows fetch")
    p.add_argument("--max-follows", type=int, help="Optional cap on number of follows to fetch (diagnostics/testing)")
    # Reading status & chapters sync
    p.add_argument("--import-reading-status", action="store_true", help="Fetch MangaDex reading statuses and map to categories")
    p.add_argument("--status-category-map", help="Comma list mapping status=categoryId (e.g. completed=5,reading=2,on_hold=7,dropped=8,plan_to_read=9,re_reading=10)")
    p.add_argument("--status-default-category", type=int, help="Fallback category id if a status has no explicit mapping")
    p.add_argument("--import-read-chapters", action="store_true", help="Fetch MangaDex read chapter UUIDs and mark them read in Suwayomi")
    p.add_argument("--read-chapters-dry-run", action="store_true", help="Simulate chapter read marking only")
    p.add_argument("--read-sync-delay", type=float, default=0.0, help="Seconds to wait after adding a manga before syncing read chapters (allow chapters to populate)")
    p.add_argument("--max-read-requests-per-minute", type=int, default=300, help="Throttle for chapter read mark requests")
    p.add_argument("--list-categories", action="store_true", help="List Suwayomi categories (id + name) and exit")
    p.add_argument("--status-map-debug", action="store_true", help="Verbose output for status->category mapping decisions")
    p.add_argument("--assume-missing-status", help="If a manga has no MangaDex status, assume this status (e.g. reading)")
    p.add_argument("--print-status-summary", action="store_true", help="Print summary of fetched statuses and mapping coverage")
    p.add_argument("--debug-status", action="store_true", help="Print raw status dict sample after fetch")
    p.add_argument("--status-endpoint-raw", action="store_true", help="Dump full raw JSON from /manga/status (and per-manga fallback) for diagnostics")
    p.add_argument("--status-fallback-single", action="store_true", help="If bulk status returns empty, fetch each via /manga/{id}/status")
    p.add_argument("--status-fallback-throttle", type=float, default=0.3, help="Sleep seconds between single status fallback calls (default 0.3)")
    p.add_argument("--ignore-statuses", help="Comma-separated list of status values to ignore for category mapping (e.g. reading)")
    p.add_argument("--verify-id", action="append", dest="verify_ids", help="Repeatable. Verify this MangaDex UUID is in the final import set (after follows merge). Can be specified multiple times.")

    args = p.parse_args(argv)

    # Ensure session_token always defined to avoid UnboundLocalError when using --import-reading-status without --from-follows
    session_token: Optional[str] = None

    ids: List[str] = []
    if args.input_file:
        ids = read_any(args.input_file)

    # --- MangaDex follows fetch ---
    follows_meta: List[Dict[str, Any]] = []
    if args.from_follows:
        md_user = args.md_username or os.environ.get("MANGADEX_USERNAME")
        md_pass = args.md_password or os.environ.get("MANGADEX_PASSWORD")
        if not md_user:
            print("MangaDex username required for --from-follows (flag --md-username or env MANGADEX_USERNAME)")
            return 2
        if not md_pass:
            md_pass = getpass.getpass("MangaDex password: ")
        session_token, login_err = login_mangadex_verbose(
            username=md_user,
            password=md_pass,
            two_factor=args.md_2fa,
            client_id=args.md_client_id or os.environ.get("MANGADEX_CLIENT_ID"),
            client_secret=args.md_client_secret or os.environ.get("MANGADEX_CLIENT_SECRET"),
            debug=args.debug_login,
        )
        if not session_token:
            print("Failed to authenticate with MangaDex." + (f" Reason: {login_err}" if login_err else ""))
            return 3
        follows_meta = fetch_all_follows_adv(
            session_token=session_token,
            debug=args.debug_follows,
            max_follows=args.max_follows,
        )
        follow_ids = [m["id"] for m in follows_meta]
        # Merge with file IDs preserving order preference: file first, then new
        seen = set(ids)
        for fid in follow_ids:
            if fid not in seen:
                ids.append(fid)
                seen.add(fid)
        if args.follows_json:
            try:
                args.follows_json.write_text(json.dumps(follows_meta, indent=2), encoding="utf-8")
            except Exception as e:
                print(f"Warning: failed to write follows JSON: {e}")

    if not ids and not args.list_categories:
        print("No MangaDex IDs to process (empty file and no follows fetched).")
        return 1

    # Optional presence verification of specific IDs
    if args.verify_ids:
        print("ID presence verification (after merge):")
        id_set = set(ids)
        for vid in args.verify_ids:
            if vid in id_set:
                print(f"  {vid} : PRESENT")
            else:
                print(f"  {vid} : MISSING (not in file nor follows)" )

    # --- Reading status mapping (optional) ---
    status_map: Dict[str, int] = {}
    if args.status_category_map:
        for part in args.status_category_map.split(','):
            part = part.strip()
            if not part:
                continue
            if '=' not in part:
                print(f"Warning: ignoring malformed status map entry '{part}'")
                continue
            k, v = part.split('=', 1)
            try:
                status_map[k.strip().lower()] = int(v)
            except ValueError:
                print(f"Warning: invalid category id in map entry '{part}'")
    reading_statuses: Dict[str, str] = {}
    status_fetch_note = ""
    if args.import_reading_status:
        # We can reuse session_token from follows, or login solely for status fetch.
        if not session_token:
            # Attempt standalone login if credentials provided and from-follows not used.
            md_user = args.md_username or os.environ.get("MANGADEX_USERNAME")
            md_pass = args.md_password or os.environ.get("MANGADEX_PASSWORD")
            if md_user and md_pass:
                session_token, login_err = login_mangadex_verbose(username=md_user, password=md_pass, two_factor=args.md_2fa)
                if not session_token:
                    print("Failed MangaDex login for status fetch." + (f" Reason: {login_err}" if login_err else ""))
                    status_fetch_note = "login failed"
            else:
                print("No session (need --from-follows or MangaDex credentials) to fetch statuses.")
                status_fetch_note = "no credentials"
        if session_token:
            # If raw dump requested, capture raw JSON pages by temporarily wrapping fetch_reading_statuses batching
            if args.status_endpoint_raw:
                print("[status-raw] Fetching statuses for", len(ids), "ids")
            reading_statuses = fetch_reading_statuses(session_token, ids)
            if not reading_statuses:
                status_fetch_note = "0 statuses fetched"
                if args.debug_status:
                    print("[debug-status] No statuses returned. If you just set one on MangaDex, wait a few seconds or toggle it again.")
                if args.status_endpoint_raw and ids:
                    # Try single-item fallback endpoint described in docs: GET /manga/{id}/status
                    test_id = ids[0]
                    try:
                        import requests as _rq
                        r2 = _rq.get(f"{MANGADEX_API}/manga/{test_id}/status", headers={"Authorization": f"Bearer {session_token}"}, timeout=15)
                        print(f"[status-raw] Single /manga/{{id}}/status HTTP {r2.status_code}")
                        try:
                            print("[status-raw] Body:", truncate_text(r2.text, 400))
                        except Exception:
                            pass
                    except Exception as se:
                        print(f"[status-raw] Single status fetch error: {se}")
                # Automatic or explicit fallback to single fetch per id
                if args.status_fallback_single or (not reading_statuses and args.import_reading_status):
                    if args.debug_status:
                        print(f"[debug-status] Starting single-status fallback for {len(ids)} ids")
                    fetched_any = False
                    for mid in ids:
                        st = fetch_single_status(session_token, mid)
                        if st:
                            reading_statuses[mid] = st
                            fetched_any = True
                        time.sleep(max(0.0, args.status_fallback_throttle))
                    if args.debug_status:
                        print(f"[debug-status] Single-status fallback {'found some' if fetched_any else 'found none'}.")
                    if reading_statuses and status_fetch_note.startswith('0 statuses'):
                        status_fetch_note = f"{len(reading_statuses)} statuses fetched (fallback)"
            else:
                status_fetch_note = f"{len(reading_statuses)} statuses fetched"
            if args.debug_status:
                sample_items = list(reading_statuses.items())[:10]
                print("[debug-status] Sample:")
                for k,v in sample_items:
                    print(f"  {k}: {v}")
                if len(reading_statuses) > 10:
                    print(f"  ... {len(reading_statuses)-10} more")
            if args.status_endpoint_raw and reading_statuses:
                # Dump full mapping (may be large) truncated
                try:
                    js_dump = json.dumps(reading_statuses)
                    print("[status-raw] Full statuses JSON (truncated 800 chars):", js_dump[:800] + ("..." if len(js_dump) > 800 else ""))
                except Exception as je:
                    print(f"[status-raw] Could not dump statuses JSON: {je}")

            # Filter out ignored statuses from mapping phase (still appear in summary before removal)
            if args.ignore_statuses:
                ignore_set = {s.strip().lower() for s in args.ignore_statuses.split(',') if s.strip()}
                if ignore_set:
                    removed = 0
                    for k in list(reading_statuses.keys()):
                        if reading_statuses[k] in ignore_set:
                            del reading_statuses[k]
                            removed += 1
                    if args.debug_status:
                        print(f"[debug-status] Removed {removed} entries due to ignore-statuses filter {sorted(ignore_set)}")

    if args.print_status_summary and args.import_reading_status:
        if reading_statuses:
            counts: Dict[str, int] = {}
            for s in reading_statuses.values():
                counts[s] = counts.get(s, 0) + 1
            mapped = sum(1 for s in reading_statuses.values() if s in status_map)
            coverage = (mapped / len(reading_statuses)) * 100 if reading_statuses else 0.0
            print("Status summary:", ", ".join(f"{k}={v}" for k,v in sorted(counts.items())))
            print(f"Status mapping coverage: {mapped}/{len(reading_statuses)} ({coverage:.1f}%)")
        else:
            print(f"Status summary: NONE ({status_fetch_note or 'no data'})")
        if args.assume_missing_status:
            print(f"Assuming missing status = '{args.assume_missing_status.lower()}'")

    # --- Chapter read marker sync configuration ---
    chapter_sync_conf = {
        'enabled': args.import_read_chapters,
        'dry_run': args.read_chapters_dry_run,
        'delay': args.read_sync_delay,
        'rpm': args.max_read_requests_per_minute,
    }
    if args.import_read_chapters and not (args.from_follows and session_token):
        print("--import-read-chapters requires a MangaDex session (use --from-follows login path). Disabling.")
        chapter_sync_conf['enabled'] = False

    client = SuwayomiClient(
        base_url=args.base_url,
        auth_mode=args.auth_mode,
        username=args.username,
        password=args.password,
        token=args.token,
        verify_tls=not args.insecure,
    )

    if args.list_categories:
        try:
            cat_endpoints = [
                "/api/v1/category/list",  # common
                "/api/v1/category",       # alternative
                "/api/v1/categories",     # plural variant
            ]
            last_err: Optional[str] = None
            for ep in cat_endpoints:
                r = client.request("GET", ep)
                if r.status_code == 200:
                    try:
                        data = r.json()
                    except Exception as je:
                        last_err = f"Invalid JSON from {ep}: {je}"
                        continue
                    # Some APIs wrap list inside a key
                    if isinstance(data, dict):
                        for k in ("data", "categories", "list"):
                            if k in data and isinstance(data[k], list):
                                data = data[k]
                                break
                    if not isinstance(data, list):
                        last_err = f"Unexpected format from {ep} (type {type(data)})"
                        continue
                    print("Available Categories (from", ep, "):")
                    for cat in data:
                        if not isinstance(cat, dict):
                            continue
                        cid = cat.get('id') or cat.get('categoryId')
                        name = cat.get('name') or cat.get('label') or ''
                        print(f"  {cid}: {name}")
                    return 0
                else:
                    last_err = f"HTTP {r.status_code} {truncate_text(r.text,120)} at {ep}"
            print(f"Failed to fetch categories. Tried endpoints: {', '.join(cat_endpoints)}")
            if last_err:
                print("Last error:", last_err)
            return 4
        except Exception as ce:
            print(f"Error retrieving categories: {ce}")
            return 4

    added, failed, failures = import_ids(
        client,
        ids,
        dry_run=args.dry_run,
        use_title_fallback=not args.no_title_fallback,
        show_progress=not args.no_progress,
        throttle=args.throttle,
        category_id=args.category_id,
        reading_statuses=reading_statuses,
        status_category_map=status_map,
        status_default_category=args.status_default_category,
        session_token=session_token if args.from_follows else None,
        chapter_sync_conf=chapter_sync_conf,
    status_map_debug=args.status_map_debug,
    assume_missing_status=(args.assume_missing_status.lower() if args.assume_missing_status else None),
    )

    print(f"Found {len(ids)} MangaDex IDs; Added: {added}, Failed: {failed}")
    if failures:
        print("Failures:")
        for md, reason in failures[:50]:  # cap output
            print(f"  {md}: {reason}")
        if len(failures) > 50:
            print(f"  ... and {len(failures) - 50} more")

    return 0 if failed == 0 else 2

if __name__ == "__main__":
    sys.exit(main())
