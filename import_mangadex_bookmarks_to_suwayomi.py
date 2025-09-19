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
    def __init__(self, base_url: str, auth_mode: str = "auto", username: Optional[str] = None, password: Optional[str] = None, token: Optional[str] = None, verify_tls: bool = True, request_timeout: float = 12.0):
        self.base_url = base_url.rstrip('/')
        self.sess = requests.Session()
        self.verify = verify_tls
        self.timeout = request_timeout
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
        # Default timeout for all requests to avoid stalls
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout
        resp = self.sess.request(method, url, headers=headers, verify=self.verify, **kwargs)
        # Fallback: if 401 with basic on auto, try SIMPLE login
        if resp.status_code == 401 and self.auth_mode == "auto" and self.username and self.password:
            # try simple login once
            login = self.sess.post(f"{self.base_url}/login.html", data={"user": self.username, "pass": self.password}, allow_redirects=False, verify=self.verify, timeout=self.timeout)
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

    # Additional helpers for rehoming/migration
    def get_manga_details(self, manga_id: int) -> Dict[str, Any]:
        r = self.request("GET", f"/api/v1/manga/{manga_id}")
        if r.status_code != 200:
            return {}
        try:
            return r.json()
        except Exception:
            return {}

    def get_manga_chapters_count(self, manga_id: int) -> int:
        """Best-effort chapter count for a manga. Tries multiple endpoints and formats.
        Returns 0 on failure."""
        try:
            # Try common chapters endpoint variants
            for ep in (f"/api/v1/manga/{manga_id}/chapters", f"/api/v1/manga/{manga_id}/chapter"):
                r = self.request("GET", ep)
                if r.status_code != 200:
                    continue
                try:
                    js = r.json()
                except Exception:
                    continue
                if isinstance(js, list):
                    return len(js)
                if isinstance(js, dict):
                    for k in ("chapters", "data", "list"):
                        v = js.get(k)
                        if isinstance(v, list):
                            return len(v)
            # Try details with chapters included
            for ep in (f"/api/v1/manga/{manga_id}?withChapters=true", f"/api/v1/manga/{manga_id}"):
                r = self.request("GET", ep)
                if r.status_code != 200:
                    continue
                try:
                    js = r.json()
                except Exception:
                    continue
                if isinstance(js, dict):
                    for k in ("chapters", "chapterCount", "chaptersCount"):
                        v = js.get(k)
                        if isinstance(v, list):
                            return len(v)
                        if isinstance(v, int):
                            return v
        except Exception:
            pass
        # GraphQL fallback: ask for chapters length via different shapes
        try:
            # Try manga(id:Int!) first
            q1 = "query($id:Int!){ manga(id:$id){ chapters { id } } }"
            res1 = self.graphql(q1, variables={"id": int(manga_id)})
            if res1 and isinstance(res1, dict) and isinstance(res1.get('data'), dict):
                mn = res1['data'].get('manga')
                if isinstance(mn, dict):
                    chs = mn.get('chapters')
                    if isinstance(chs, list):
                        return len(chs)
            # Try chapters(mangaId:Int!) nodes/items/edges
            for q in (
                "query($id:Int!){ chapters(mangaId:$id){ nodes { id } } }",
                "query($id:Int!){ chapters(mangaId:$id){ items { id } } }",
                "query($id:Int!){ chapters(mangaId:$id){ edges { node { id } } } }",
            ):
                res2 = self.graphql(q, variables={"id": int(manga_id)})
                if res2 and isinstance(res2, dict):
                    # Use extractor to count ids
                    ids: List[str] = []
                    def visit(n: Any):
                        if isinstance(n, dict):
                            if 'id' in n and len(n) == 1:
                                ids.append(str(n['id']))
                            for v in n.values():
                                visit(v)
                        elif isinstance(n, list):
                            for it in n:
                                visit(it)
                    visit(res2.get('data'))
                    if ids:
                        return len(ids)
        except Exception:
            pass
        return 0

    def remove_from_library(self, manga_id: int) -> bool:
        # Some builds support DELETE; provide GET fallback path if needed
        r = self.request("DELETE", f"/api/v1/manga/{manga_id}/library")
        if r.status_code == 200:
            return True
        r2 = self.request("GET", f"/api/v1/manga/{manga_id}/library/remove")
        return r2.status_code == 200

    # --- GraphQL helpers ---
    def graphql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        try:
            headers = {"Content-Type": "application/json"}
            payload = {"query": query}
            if variables is not None:
                payload["variables"] = variables
            # Try /api/graphql then /graphql
            paths = ["/api/graphql", "/graphql"]
            last_err = None
            for p in paths:
                try:
                    r = self.sess.post(f"{self.base_url}{p}", headers=headers, data=json.dumps(payload), verify=self.verify)
                except Exception as e:
                    last_err = e
                    if getattr(self, 'debug_library', False):
                        print(f"[gql-debug] Exception posting to {p}: {e}")
                    continue
                if r.status_code != 200:
                    if getattr(self, 'debug_library', False):
                        print(f"[gql-debug] HTTP {r.status_code} {p}: {truncate_text(r.text, 160)}")
                    continue
                try:
                    js = r.json()
                    if getattr(self, 'debug_library', False) and isinstance(js, dict) and js.get('errors'):
                        try:
                            print("[gql-debug] Errors:", json.dumps(js['errors'])[:400])
                        except Exception:
                            pass
                    return js
                except Exception as je:
                    if getattr(self, 'debug_library', False):
                        print(f"[gql-debug] Invalid JSON from {p}: {je}")
                    continue
            if last_err and getattr(self, 'debug_library', False):
                print(f"[gql-debug] All GraphQL paths failed: {last_err}")
            return None
        except Exception as e:
            if getattr(self, 'debug_library', False):
                print(f"[gql-debug] Unexpected GraphQL error: {e}")
            return None

    def _extract_manga_list_from_gql(self, data: Any) -> List[Dict[str, Any]]:
        found: List[Dict[str, Any]] = []
        def visit(node: Any):
            if isinstance(node, dict):
                # Derive id and title from this node considering common variants
                nid = node.get('id')
                if nid is None:
                    nid = node.get('mangaId') or node.get('manga_id') or node.get('seriesId')
                title = node.get('title') or node.get('name')
                # Also check nested 'manga' object for title/id
                if not title and isinstance(node.get('manga'), dict):
                    title = node['manga'].get('title') or node['manga'].get('name')
                if nid is None and isinstance(node.get('manga'), dict):
                    nid = node['manga'].get('id') or node['manga'].get('mangaId') or node['manga'].get('manga_id')
                if nid is not None and title:
                    found.append({'id': nid, 'title': title})
                # Traverse common container keys
                for k in ('nodes','items','edges'):
                    v = node.get(k)
                    if isinstance(v, list):
                        for it in v:
                            if k == 'edges' and isinstance(it, dict) and isinstance(it.get('node'), dict):
                                visit(it['node'])
                            else:
                                visit(it)
                for v in node.values():
                    visit(v)
            elif isinstance(node, list):
                for it in node:
                    visit(it)
        if isinstance(data, dict) and 'data' in data:
            visit(data['data'])
        else:
            visit(data)
        seen = set()
        uniq: List[Dict[str, Any]] = []
        for it in found:
            mid = it.get('id')
            if mid in seen:
                continue
            uniq.append(it)
            seen.add(mid)
        return uniq

    def get_library_graphql(self) -> List[Dict[str, Any]]:
        # Prefer category-based aggregation first (closer to actual library)
        try:
            cats_res = self.graphql("query { categories { nodes { id } edges { node { id } } } }")
            cat_ids: List[int] = []
            if isinstance(cats_res, dict) and isinstance(cats_res.get('data'), dict):
                c_root = cats_res['data'].get('categories')
                if isinstance(c_root, dict):
                    n = c_root.get('nodes') or []
                    if isinstance(n, list):
                        for it in n:
                            if isinstance(it, dict) and isinstance(it.get('id'), int):
                                cat_ids.append(it['id'])
                    e = c_root.get('edges') or []
                    if isinstance(e, list):
                        for it in e:
                            if isinstance(it, dict) and isinstance(it.get('node'), dict):
                                nid = it['node'].get('id')
                                if isinstance(nid, int):
                                    cat_ids.append(nid)
            seen_ids = set()
            out: List[Dict[str, Any]] = []
            for cid in cat_ids:
                q = "query($cid:Int!){ category(id:$cid){ mangas { nodes { id title } edges { node { id title } } } } }"
                res = self.graphql(q, variables={"cid": int(cid)})
                items = self._extract_manga_list_from_gql(res) if res else []
                for it in items:
                    mid = it.get('id')
                    if mid in seen_ids:
                        continue
                    seen_ids.add(mid)
                    out.append(it)
            if out:
                if getattr(self, 'debug_library', False):
                    print(f"[gql-debug] Total from categories (deduped): {len(out)}")
                return out
        except Exception:
            pass

        queries = [
            # Common shapes across forks
            "query { library { entries { id mangaId title name manga { id title name } } } }",
            "query { library { id title name entries { manga { id title name } } } }",
            "query { library { mangaList { id title name } } }",
            "query { libraryEntries { manga { id title name } } }",
            "query { mangas { nodes { id title } } }",
            "query { mangas { edges { node { id title } } } }",
            "query { mangaList { id title name } }",
            "query { library { items { id title name } } }",
            "query { categories { nodes { id } } }",
            "query { categories { edges { node { id } } } }",
        ]
        # Also try parameterized 'mangas' calls with common argument shapes
        param_queries = [
            ("query($in:Boolean!){ mangas(inLibrary:$in){ id title name inLibrary } }", {"in": True}),
            ("query($f:MangaFilter){ mangas(filter:$f){ id title name inLibrary } }", {"f": {"inLibrary": True}}),
            ("query{ mangas { id title name inLibrary } }", None),
        ]
        for q in queries:
            res = self.graphql(q)
            if res is None:
                continue
            if getattr(self, 'debug_library', False):
                try:
                    data_str = json.dumps(res.get('data', {}))
                    print(f"[gql-debug] Query OK; data keys: {', '.join(list((res.get('data') or {}).keys()))}")
                    print(f"[gql-debug] Sample data: {data_str[:400]}{'...' if len(data_str)>400 else ''}")
                except Exception:
                    print("[gql-debug] Query OK, extracting manga list")
            items = self._extract_manga_list_from_gql(res)
            if items:
                return items
        for q, vars in param_queries:
            res = self.graphql(q, variables=vars)
            if res is None:
                continue
            if getattr(self, 'debug_library', False):
                try:
                    data_str = json.dumps(res.get('data', {}))
                    print(f"[gql-debug] Param query OK; data keys: {', '.join(list((res.get('data') or {}).keys()))}")
                    print(f"[gql-debug] Sample data: {data_str[:400]}{'...' if len(data_str)>400 else ''}")
                except Exception:
                    print("[gql-debug] Param query OK, extracting manga list")
            items = self._extract_manga_list_from_gql(res)
            if items:
                return items
        # As a last resort, try introspection to guide user/debugging
        intro = self.graphql("query { __schema { queryType { fields { name } } } }")
        if getattr(self, 'debug_library', False) and intro:
            try:
                fields = [f.get('name') for f in intro.get('data', {}).get('__schema', {}).get('queryType', {}).get('fields', [])]
                print("[gql-debug] Root query fields:", ", ".join(fields[:50]))
            except Exception:
                pass
        # Try fetching via categories (many schemas expose library through categories)
        try:
            cats_res = self.graphql("query { categories { id name } }")
            cat_items: List[Dict[str, Any]] = []
            if isinstance(cats_res, dict) and isinstance(cats_res.get('data'), dict):
                cats = cats_res['data'].get('categories')
                if isinstance(cats, list):
                    if getattr(self, 'debug_library', False):
                        print(f"[gql-debug] Categories found: {len(cats)}")
                    # For each category, attempt paginated fetches with common arg shapes
                    seen_ids: set = set()
                    for c in cats:
                        cid = c.get('id')
                        if cid is None:
                            continue
                        # Try several pagination argument shapes
                        arg_shapes = [
                            ("page", "size"), ("page", "limit"), ("pageNum", "pageSize"), ("offset", "limit"),
                        ]
                        for arg1, arg2 in arg_shapes:
                            page = 1
                            empty_pages = 0
                            while page <= 100:  # safety cap
                                if arg1 in ("offset",):
                                    vars = {"cid": int(cid), arg1: (page-1)*100, arg2: 100}
                                    q = f"query($cid:Int,$offset:Int,$limit:Int){{ category(id:$cid){{ mangas({arg1}:$offset, {arg2}:$limit){{ nodes {{ id title }} edges {{ node {{ id title }} }} }} }} }}"
                                elif arg1 == "pageNum" and arg2 == "pageSize":
                                    vars = {"cid": int(cid), arg1: page, arg2: 100}
                                    q = f"query($cid:Int,$pageNum:Int,$pageSize:Int){{ category(id:$cid){{ mangas({arg1}:$pageNum, {arg2}:$pageSize){{ nodes {{ id title }} edges {{ node {{ id title }} }} }} }} }}"
                                else:
                                    vars = {"cid": int(cid), arg1: page, arg2: 100}
                                    q = f"query($cid:Int,$page:Int,$size:Int){{ category(id:$cid){{ mangas({arg1}:$page, {arg2}:$size){{ nodes {{ id title }} edges {{ node {{ id title }} }} }} }} }}"
                                res = self.graphql(q, variables=vars)
                                if not res or not isinstance(res, dict):
                                    empty_pages += 1
                                    if empty_pages >= 2:
                                        break
                                    page += 1
                                    continue
                                before = len(seen_ids)
                                items = self._extract_manga_list_from_gql(res)
                                for it in items:
                                    mid = it.get('id')
                                    if mid is None or mid in seen_ids:
                                        continue
                                    seen_ids.add(mid)
                                    cat_items.append(it)
                                if getattr(self, 'debug_library', False):
                                    gained = len(seen_ids) - before
                                    print(f"[gql-debug] category {cid} page {page} +{gained} (total {len(seen_ids)})")
                                # Heuristic: stop if no new items
                                if len(seen_ids) == before:
                                    empty_pages += 1
                                else:
                                    empty_pages = 0
                                # advance page regardless
                                page += 1
                        # Move to next category
                    if cat_items:
                        return cat_items
        except Exception as e:
            if getattr(self, 'debug_library', False):
                print("[gql-debug] Category-based fetch error:", e)

        # Introspect 'mangas' field container names and try them dynamically
        try:
            introspect = self.graphql("query { __schema { queryType { fields { name type { name kind ofType { name kind ofType { name kind } } } } } } }")
            if isinstance(introspect, dict):
                fields = (introspect.get('data') or {}).get('__schema', {}).get('queryType', {}).get('fields', [])
                mangas_type = None
                for f in fields:
                    if f.get('name') == 'mangas':
                        t = f.get('type') or {}
                        # Unwrap nested ofType
                        while t and not t.get('name') and t.get('ofType'):
                            t = t['ofType']
                        mangas_type = t.get('name')
                        break
                if mangas_type:
                    type_info = self.graphql("query($n:String!){ __type(name:$n){ fields { name type { name kind ofType { name kind } } } } }", {"n": mangas_type})
                    candidates = []
                    if isinstance(type_info, dict):
                        tfields = (type_info.get('data') or {}).get('__type', {}).get('fields', [])
                        for tf in tfields:
                            fname = tf.get('name')
                            if not fname:
                                continue
                            # try common containers only
                            if fname.lower() in ('list','data','results','items','nodes','edges'):
                                candidates.append(fname)
                    if getattr(self, 'debug_library', False):
                        print("[gql-debug] mangas type:", mangas_type, "candidates:", ", ".join(candidates) or '(none)')
                    for c in candidates:
                        if c == 'edges':
                            q = f"query {{ mangas {{ edges {{ node {{ id title }} }} }} }}"
                        else:
                            q = f"query {{ mangas {{ {c} {{ id title }} }} }}"
                        res = self.graphql(q)
                        if not res:
                            continue
                        items = self._extract_manga_list_from_gql(res)
                        if items:
                            return items
        except Exception as e:
            if getattr(self, 'debug_library', False):
                print("[gql-debug] Introspection error:", e)
        return []

    

    def get_library(self) -> List[Dict[str, Any]]:
        # Try multiple known endpoints across Suwayomi builds
        endpoints = [
            "/api/v1/library",
            "/api/v1/manga/list",
            "/api/v1/manga",
            "/api/v1/library/list",
            "/api/v1/library/manga",
        ]
        for ep in endpoints:
            try:
                r = self.request("GET", ep)
            except Exception as e:
                if getattr(self, 'debug_library', False):
                    print(f"[lib-debug] Exception requesting {ep}: {e}")
                continue
            if r.status_code != 200:
                if getattr(self, 'debug_library', False):
                    print(f"[lib-debug] HTTP {r.status_code} {ep}: {truncate_text(r.text, 120)}")
                continue
            try:
                data = r.json()
            except Exception as je:
                if getattr(self, 'debug_library', False):
                    print(f"[lib-debug] Invalid JSON from {ep}: {je}")
                continue
            if getattr(self, 'debug_library', False):
                shape = type(data).__name__
                print(f"[lib-debug] {ep} -> {shape}")
            # Normalize to list of entries with id and title
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for k in ("data", "manga", "list", "mangaList", "mangaListData", "items"):
                    v = data.get(k)
                    if isinstance(v, list):
                        return v
        # Fallback to GraphQL if REST endpoints didn't yield anything
        if getattr(self, 'debug_library', False):
            print("[lib-debug] Falling back to GraphQL for library list")
        try:
            items = self.get_library_graphql()
            if items:
                return items
        except Exception as e:
            if getattr(self, 'debug_library', False):
                print(f"[lib-debug] GraphQL fallback failed: {e}")
        return []


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
    lists_membership: Optional[Dict[str, List[str]]] = None,
    lists_category_map: Optional[Dict[str, int]] = None,
    lists_ignore_set: Optional[set] = None,
    rehome_conf: Optional[Dict[str, Any]] = None,
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
                if status_map_debug:
                    # Prefer custom list mapping if available
                    display = None
                    target_cat = None
                    via = ''
                    if lists_membership and lists_category_map:
                        names = [n for n in (lists_membership.get(md) or []) if not (lists_ignore_set and n in lists_ignore_set)]
                        for nm in names:
                            if nm in lists_category_map:
                                display = f"List:{nm}"
                                target_cat = lists_category_map[nm]
                                via = 'list-map'
                                break
                    if target_cat is None and status_category_map:
                        raw_status = (reading_statuses.get(md, '') if reading_statuses else '')
                        eff_status = (raw_status or assume_missing_status or '').lower()
                        display = raw_status or (assume_missing_status and f"(assumed {assume_missing_status})") or '(none)'
                        if eff_status:
                            target_cat = status_category_map.get(eff_status)
                            via = 'map'
                            if target_cat is None and status_default_category is not None:
                                target_cat = status_default_category
                                via = 'default'
                            if target_cat is None and raw_status == '' and assume_missing_status and status_category_map.get(assume_missing_status.lower()):
                                target_cat = status_category_map.get(assume_missing_status.lower())
                                via = 'assumed'
                        else:
                            # No effective status (e.g., ignored or missing). Use default if provided.
                            if status_default_category is not None:
                                target_cat = status_default_category
                                via = 'default'
                    if show_progress:
                        if target_cat is not None:
                            print(f"{prefix}STATUS {display or '(none)'} -> cat {target_cat} ({via}) (dry-run)")
                        else:
                            print(f"{prefix}STATUS {(display or '(none)')} -> no mapping (dry-run)")
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
                # Apply list-based category mapping first, then fall back to reading status
                applied = False
                if lists_membership and lists_category_map:
                    names = [n for n in (lists_membership.get(md) or []) if not (lists_ignore_set and n in lists_ignore_set)]
                    for nm in names:
                        if nm in lists_category_map:
                            try:
                                cat_ok = client.add_manga_to_category(manga_id, lists_category_map[nm])
                                applied = True
                                if status_map_debug and show_progress:
                                    print(f"{prefix}STATUS List:{nm} -> cat {lists_category_map[nm]} {'OK' if cat_ok else 'FAIL'}")
                            except Exception as sm_e:
                                if status_map_debug and show_progress:
                                    print(f"{prefix}STATUS List:{nm} ERROR {sm_e}")
                            break
                if (not applied) and (reading_statuses or assume_missing_status or status_default_category is not None) and status_category_map:
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
                    else:
                        # No effective status (e.g., ignored or missing): apply default if provided
                        if status_default_category is not None:
                            try:
                                cat_ok = client.add_manga_to_category(manga_id, status_default_category)
                                if status_map_debug and show_progress:
                                    print(f"{prefix}STATUS (none) -> cat {status_default_category} (default) {'OK' if cat_ok else 'FAIL'}")
                            except Exception as sm_e:
                                if status_map_debug and show_progress:
                                    print(f"{prefix}STATUS (none) -> cat {status_default_category} ERROR {sm_e}")
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
                # Rehoming/migration: if enabled and MangaDex has too few chapters, try alternative sources
                if rehome_conf and rehome_conf.get('enabled'):
                    try:
                        min_ch = int(rehome_conf.get('skip_if_ge', 1))
                    except Exception:
                        min_ch = 1
                    have = client.get_manga_chapters_count(manga_id)
                    if have < min_ch:
                        # We need title to search other sources
                        title = fetched_title or fetch_title_from_mangadex(md) or ''
                        if not title:
                            # last attempt: from details
                            det = client.get_manga_details(manga_id)
                            title = str(det.get('title') or det.get('name') or '')
                        if title:
                            # Prepare preferred sources
                            pref = [s.strip().lower() for s in (rehome_conf.get('sources') or []) if s.strip()]
                            # Load all sources
                            all_sources = client.get_sources()
                            # Exclude unwanted sources by name/apkName
                            exclude_frags = [s.strip().lower() for s in (args.exclude_sources.split(',') if args.exclude_sources else []) if s.strip()]
                            if exclude_frags:
                                _tmp = []
                                for _s in all_sources:
                                    _nm = (_s.get('name') or _s.get('apkName') or '').lower()
                                    if any(f in _nm for f in exclude_frags):
                                        continue
                                    _tmp.append(_s)
                                all_sources = _tmp
                            # Sort sources by preference (those matching any fragment first)
                            def score(src: Dict[str, Any]) -> int:
                                nm = (src.get('name') or src.get('apkName') or '').lower()
                                for i, frag in enumerate(pref):
                                    if frag and frag in nm:
                                        return i
                                return 9999
                            for src in sorted(all_sources, key=score):
                                nm = (src.get('name') or src.get('apkName') or '').lower()
                                if 'mangadex' in nm:
                                    continue
                                if pref and all(f not in nm for f in pref):
                                    # if preferences specified, skip non-matching sources unless we exhausted all
                                    pass
                                try:
                                    rid = int(src.get('id'))
                                except Exception:
                                    continue
                                try:
                                    search = client.search_source(rid, title, page=1)
                                except Exception:
                                    continue
                                items = search.get('mangaList') or search.get('mangaListData') or search.get('manga_list') or []
                                if not items:
                                    continue
                                # take first match
                                alt = items[0]
                                try:
                                    alt_id = int(alt.get('id'))
                                except Exception:
                                    continue
                                added_alt = client.add_to_library(alt_id)
                                if show_progress:
                                    print(f"{prefix}REHOME via '{src.get('name')}' -> {'OK' if added_alt else 'FAIL'}")
                                if added_alt and rehome_conf.get('remove_md'):
                                    try:
                                        rm_ok = client.remove_from_library(manga_id)
                                        if show_progress:
                                            print(f"{prefix}REMOVE MangaDex entry -> {'OK' if rm_ok else 'FAIL'}")
                                    except Exception as _:
                                        pass
                                # stop after first successful alt add attempt
                                break
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
                # API may return either a bare string or an object like {"status": "on_hold"}
                if isinstance(v, str):
                    result[k] = v.lower()
                elif isinstance(v, dict):
                    sv = v.get('status') or v.get('readingStatus') or v.get('value')
                    if isinstance(sv, str):
                        result[k] = sv.lower()
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


def fetch_all_statuses(session_token: str) -> Dict[str, str]:
    """Fetch all reading statuses for the authenticated user via /manga/status without ids filter.
    Returns dict md_uuid -> status (lowercase)."""
    headers = {"Authorization": f"Bearer {session_token}"}
    try:
        r = requests.get(f"{MANGADEX_API}/manga/status", headers=headers, timeout=30)
        if r.status_code != 200:
            return {}
        raw = r.json().get('statuses') or {}
        out: Dict[str, str] = {}
        for k, v in raw.items():
            if isinstance(v, str):
                out[k] = v.lower()
            elif isinstance(v, dict):
                sv = v.get('status') or v.get('readingStatus') or v.get('value')
                if isinstance(sv, str):
                    out[k] = sv.lower()
        return out
    except Exception:
        return {}


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


# --- MangaDex custom lists helpers ---
def fetch_user_lists(session_token: str, debug: bool = False) -> List[Dict[str, Any]]:
    """Fetch user's custom reading lists (id + name)."""
    headers = {"Authorization": f"Bearer {session_token}"}
    limit = 100
    offset = 0
    items: List[Dict[str, Any]] = []
    while True:
        try:
            r = requests.get(f"{MANGADEX_API}/user/list", params={"limit": limit, "offset": offset}, headers=headers, timeout=20)
        except Exception as e:
            if debug:
                print(f"[lists debug] Exception at offset={offset}: {e}")
            break
        if r.status_code != 200:
            if debug:
                print(f"[lists debug] HTTP {r.status_code} at offset={offset}: {truncate_text(r.text,120)}")
            break
        js = r.json()
        data = js.get("data") or []
        if not data:
            break
        for entry in data:
            lid = entry.get("id")
            name = ((entry.get("attributes") or {}).get("name")) or entry.get("name")
            if lid and name:
                items.append({"id": lid, "name": name})
        offset += len(data)
        if len(data) < limit:
            break
        time.sleep(0.15)
    if debug:
        print(f"[lists debug] Collected {len(items)} lists")
    return items


def fetch_manga_ids_in_list(session_token: str, list_id: str, debug: bool = False) -> List[str]:
    """Fetch manga IDs belonging to a specific list via /manga?list=<listId>."""
    headers = {"Authorization": f"Bearer {session_token}"}
    limit = 100
    offset = 0
    ids: List[str] = []
    while True:
        try:
            r = requests.get(f"{MANGADEX_API}/manga", params={"limit": limit, "offset": offset, "list": list_id}, headers=headers, timeout=25)
        except Exception as e:
            if debug:
                print(f"[lists debug] Exception fetching list {list_id} offset={offset}: {e}")
            break
        if r.status_code != 200:
            if debug:
                print(f"[lists debug] HTTP {r.status_code} for list {list_id} at offset={offset}: {truncate_text(r.text,120)}")
            break
        js = r.json()
        data = js.get("data") or []
        if not data:
            break
        for m in data:
            mid = m.get("id")
            if mid:
                ids.append(mid)
        offset += len(data)
        if len(data) < limit:
            break
        time.sleep(0.15)
    if debug:
        print(f"[lists debug] List {list_id}: {len(ids)} manga ids")
    return ids


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
    p.add_argument("--export-statuses", type=Path, help="Write the final fetched statuses mapping (after filters) to this JSON file")
    p.add_argument("--include-library-statuses", action="store_true", help="Include ALL manga that have a MangaDex library reading status (merge into processing set)")
    p.add_argument("--library-statuses-only", action="store_true", help="Process ONLY manga that have a MangaDex library reading status (ignore follows and file)")
    # Rehoming/migration options
    p.add_argument("--rehoming-enabled", action="store_true", help="Attempt to add an alternative source entry when MangaDex has no chapters")
    p.add_argument("--rehoming-sources", help="Comma-separated list of source name fragments in priority order (e.g. 'mangasee,comick')")
    p.add_argument("--rehoming-skip-if-chapters-ge", type=int, default=1, help="Skip rehoming if MangaDex already has at least this many chapters (default 1)")
    p.add_argument("--rehoming-remove-mangadex", action="store_true", help="After successful rehome, remove the MangaDex entry from library (if API supports it)")
    # Migrate existing library without MangaDex data
    p.add_argument("--migrate-library", action="store_true", help="Scan current Suwayomi library and add an alternative source for entries under a chapter threshold")
    p.add_argument("--migrate-threshold-chapters", type=int, default=1, help="Only migrate entries with fewer than this many chapters (default 1)")
    p.add_argument("--migrate-sources", help="Preferred alternative sources (comma-separated fragments). If omitted, uses --rehoming-sources")
    p.add_argument("--exclude-sources", default="comick,hitomi", help="Comma-separated source name fragments to always exclude (default: 'comick,hitomi')")
    p.add_argument("--migrate-remove", action="store_true", help="Remove the original library entry after a successful migration")
    p.add_argument("--debug-library", action="store_true", help="Verbose diagnostics for library and chapter listing endpoints during migration")
    p.add_argument("--request-timeout", type=float, default=12.0, help="Default HTTP request timeout in seconds (default 12)")
    p.add_argument("--migrate-timeout", type=float, default=20.0, help="Max seconds to spend trying sources for a single migration item (default 20)")
    p.add_argument("--migrate-max-sources-per-site", type=int, default=3, help="Limit attempts per site name (e.g. 'mangapark') to this many different source IDs (default 3)")
    p.add_argument("--migrate-try-second-page", action="store_true", help="Try page 2 if page 1 had no results (slower)")
    # Custom lists support
    p.add_argument("--import-lists", action="store_true", help="Fetch MangaDex custom lists and map list names to categories")
    p.add_argument("--list-lists", action="store_true", help="List your MangaDex custom lists (id + name) and exit")
    p.add_argument("--lists-category-map", help="Comma list mapping ListName=categoryId (e.g. Dropped=7,On Hold=5,Plan to Read=8,Completed=9,Reading=4)")
    p.add_argument("--lists-ignore", help="Comma-separated list names to ignore when importing lists (e.g. Reading)")
    p.add_argument("--debug-lists", action="store_true", help="Verbose output for custom lists fetching and mapping decisions")

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

    # Optionally merge or replace with all-statuses library set
    library_statuses_all: Dict[str, str] = {}
    if (args.include_library_statuses or args.library_statuses_only):
        # Ensure we have a session
        if not session_token:
            md_user = args.md_username or os.environ.get("MANGADEX_USERNAME")
            md_pass = args.md_password or os.environ.get("MANGADEX_PASSWORD")
            if md_user and md_pass:
                session_token, _ = login_mangadex_verbose(username=md_user, password=md_pass, two_factor=args.md_2fa)
            else:
                print("--include-library-statuses/--library-statuses-only requires MangaDex credentials (use --md-username/--md-password)")
                return 2
        library_statuses_all = fetch_all_statuses(session_token) if session_token else {}
        lib_ids = list(library_statuses_all.keys())
        if args.library_statuses_only:
            ids = lib_ids
        else:
            seen = set(ids)
            for mid in lib_ids:
                if mid not in seen:
                    ids.append(mid)
                    seen.add(mid)

    if not ids and not args.list_categories and not args.migrate_library:
        print("No MangaDex IDs to process (empty file and no follows fetched). Use --migrate-library to operate only on Suwayomi.")
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

    # --- Reading status + Lists mapping (optional) ---
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
    lists_membership: Dict[str, List[str]] = {}
    lists_category_map: Dict[str, int] = {}
    lists_ignore_set: set = set()
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
            # Prefer using the pre-fetched all-statuses map when available
            if library_statuses_all:
                reading_statuses = {k: v for k, v in library_statuses_all.items() if k in set(ids)}
            else:
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

            # If bulk returned some, still fill in any missing IDs when fallback is requested
            if args.status_fallback_single and ids:
                missing_ids = [mid for mid in ids if mid not in reading_statuses]
                if missing_ids:
                    if args.debug_status:
                        print(f"[debug-status] Fallback for missing {len(missing_ids)} ids after bulk")
                    filled = 0
                    for mid in missing_ids:
                        st = fetch_single_status(session_token, mid)
                        if st:
                            reading_statuses[mid] = st
                            filled += 1
                        time.sleep(max(0.0, args.status_fallback_throttle))
                    if args.debug_status:
                        print(f"[debug-status] Fallback filled {filled} additional statuses")
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

            # Print raw summary before ignore if requested
            if args.print_status_summary and reading_statuses:
                raw_counts: Dict[str, int] = {}
                for s in reading_statuses.values():
                    raw_counts[s] = raw_counts.get(s, 0) + 1
                print("Raw status summary:", ", ".join(f"{k}={v}" for k,v in sorted(raw_counts.items())))

            # Filter out ignored statuses from mapping phase (still appear in raw summary before removal)
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

    # Optionally export the final statuses used for mapping (after ignore filters)
    if args.export_statuses:
        try:
            args.export_statuses.write_text(json.dumps(reading_statuses, indent=2), encoding="utf-8")
            print(f"Wrote {len(reading_statuses)} statuses to {args.export_statuses}")
        except Exception as e:
            print(f"Warning: failed to write --export-statuses: {e}")

    # Parse lists mapping
    if args.lists_category_map:
        for part in args.lists_category_map.split(','):
            part = part.strip()
            if not part:
                continue
            if '=' not in part:
                print(f"Warning: ignoring malformed lists map entry '{part}'")
                continue
            k, v = part.split('=', 1)
            try:
                lists_category_map[k.strip()] = int(v)
            except ValueError:
                print(f"Warning: invalid category id in lists map entry '{part}'")
    if args.lists_ignore:
        lists_ignore_set = {s.strip() for s in args.lists_ignore.split(',') if s.strip()}

    # Fetch and list user lists if requested
    if (args.import_lists or args.list_lists) and not session_token:
        # Need a session; try logging in if not already
        md_user = args.md_username or os.environ.get("MANGADEX_USERNAME")
        md_pass = args.md_password or os.environ.get("MANGADEX_PASSWORD")
        if md_user and md_pass:
            session_token, login_err = login_mangadex_verbose(username=md_user, password=md_pass, two_factor=args.md_2fa)
        else:
            print("Cannot fetch lists without MangaDex credentials/session.")
    if args.list_lists and session_token:
        lists = fetch_user_lists(session_token, debug=args.debug_lists)
        if not lists:
            print("No lists found or fetch failed.")
        else:
            print("MangaDex Lists:")
            for it in lists:
                print(f"  {it['id']}: {it['name']}")
        return 0

    # Load list memberships for current ids if requested
    if args.import_lists and session_token:
        lists = fetch_user_lists(session_token, debug=args.debug_lists)
        name_by_id = {it['id']: it['name'] for it in lists}
        for lid, lname in name_by_id.items():
            ids_in = fetch_manga_ids_in_list(session_token, lid, debug=args.debug_lists)
            for mid in ids_in:
                if mid not in ids:
                    # include if not already
                    ids.append(mid)
                lists_membership.setdefault(mid, []).append(lname)

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
        request_timeout=args.request_timeout,
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

    # Standalone library migration flow (no MangaDex needed)
    if args.migrate_library:
        client_auth = SuwayomiClient(
            base_url=args.base_url,
            auth_mode=args.auth_mode,
            username=args.username,
            password=args.password,
            token=args.token,
            verify_tls=not args.insecure,
            request_timeout=args.request_timeout,
        )
        client_auth._auth()
        # Attach debug flag
        setattr(client_auth, 'debug_library', bool(args.debug_library))
        library = client_auth.get_library()
        if not library:
            print("Could not fetch library or library is empty. Try --debug-library to see endpoint attempts.")
            return 5
        if not args.no_progress:
            print(f"Library entries discovered: {len(library)}")
        # Prepare preferred sources
        pref_str = args.migrate_sources or args.rehoming_sources or ""
        pref = [s.strip().lower() for s in pref_str.split(',') if s.strip()]
        # Find all sources and sort by preference
        sources = client_auth.get_sources()
        # Exclude unwanted sources by name/apkName
        exclude_frags = [s.strip().lower() for s in (args.exclude_sources.split(',') if args.exclude_sources else []) if s.strip()]
        if exclude_frags:
            def not_excluded(src: Dict[str, Any]) -> bool:
                nm = (src.get('name') or src.get('apkName') or '').lower()
                return all(frag not in nm for frag in exclude_frags)
            sources = [s for s in sources if not_excluded(s)]
        def score(src: Dict[str, Any]) -> int:
            nm = (src.get('name') or src.get('apkName') or '').lower()
            for i, frag in enumerate(pref):
                if frag and frag in nm:
                    return i
            return 9999
        sorted_sources = sorted(sources, key=score)
        # Helper: normalize site key from name/apkName
        def site_key(src: Dict[str, Any]) -> str:
            nm = (src.get('name') or src.get('apkName') or '').lower()
            return re.sub(r"[^a-z]+", "", nm)[:32]
        # Helper: generate conservative title variants
        def title_variants(full: str) -> List[str]:
            vars: List[str] = []
            def add(s: str):
                s = ' '.join(s.split())
                if s and s not in vars:
                    vars.append(s)
            add(full)
            # Strip after common separators
            m = re.split(r"\s*[~:\-–—]\s*", full)
            if m:
                add(m[0])
            # Remove bracketed segments
            add(re.sub(r"[\(\[\{].*?[\)\]\}]", "", full))
            # Remove punctuation
            add(re.sub(r"[^0-9A-Za-z\s]", "", full))
            # Truncate
            if len(full) > 64:
                add(full[:64])
            return vars[:4]
        migrated = 0
        skipped = 0
        failed = 0
        threshold = max(0, args.migrate_threshold_chapters)
        for idx, entry in enumerate(library, 1):
            mid = entry.get('id') or entry.get('mangaId') or entry.get('manga_id')
            try:
                mid_int = int(mid)
            except Exception:
                continue
            title = str(entry.get('title') or entry.get('name') or '').strip()
            ch_count = client_auth.get_manga_chapters_count(mid_int)
            if ch_count >= threshold:
                skipped += 1
                if not args.no_progress:
                    reason = f">={threshold} chapters" if ch_count is not None else "unknown chapter count"
                    print(f"[{idx}] SKIP '{title or mid_int}' ({reason})")
                continue
            if not title:
                # Try fetching details for title
                det = client_auth.get_manga_details(mid_int)
                title = str(det.get('title') or det.get('name') or '').strip()
            if not title:
                failed += 1
                if not args.no_progress:
                    print(f"[{idx}] MIGRATE skip (no title)")
                continue
            if not args.no_progress:
                print(f"[{idx}] MIGRATE '{title}' (chapters={ch_count})")
            added_any = False
            start_ts = time.time()
            per_site_counts: Dict[str, int] = {}
            cap_announced: Dict[str, bool] = {}
            for src in sorted_sources:
                nm = (src.get('name') or src.get('apkName') or '').lower()
                try:
                    sid = int(src.get('id'))
                except Exception:
                    continue
                skey = site_key(src)
                cnt = per_site_counts.get(skey, 0)
                if args.migrate_max_sources_per_site and cnt >= max(1, int(args.migrate_max_sources_per_site)):
                    if args.debug_library and not args.no_progress and not cap_announced.get(skey):
                        print(f"[{idx}]   skip remaining '{nm}' sources (cap {args.migrate_max_sources_per_site})")
                        cap_announced[skey] = True
                    continue
                if args.migrate_timeout and (time.time() - start_ts) > args.migrate_timeout:
                    if not args.no_progress:
                        print(f"[{idx}] MIGRATE timeout after {args.migrate_timeout:.0f}s; giving up on this title")
                    break
                got_items: List[Dict[str, Any]] = []
                # Try small set of title variants for this source
                for qtitle in title_variants(title):
                    try:
                        if args.debug_library and not args.no_progress:
                            print(f"[{idx}]   search '{qtitle}' in source id={sid} ({nm})")
                        res = client_auth.search_source(sid, qtitle, page=1)
                    except Exception as e:
                        if args.debug_library and not args.no_progress:
                            print(f"[{idx}]   search error on source id={sid}: {e}")
                        res = None
                    items = (res or {}).get('mangaList') or (res or {}).get('mangaListData') or (res or {}).get('manga_list') or []
                    if items:
                        got_items = items
                        break
                    if args.migrate_try_second_page:
                        try:
                            res2 = client_auth.search_source(sid, qtitle, page=2)
                        except Exception:
                            res2 = None
                        items2 = (res2 or {}).get('mangaList') or (res2 or {}).get('mangaListData') or (res2 or {}).get('manga_list') or []
                        if items2:
                            got_items = items2
                            break
                if not got_items:
                    if args.debug_library and not args.no_progress:
                        print(f"[{idx}]   no results")
                    per_site_counts[skey] = cnt + 1
                    continue
                try:
                    alt_id = int(got_items[0].get('id'))
                except Exception:
                    if args.debug_library and not args.no_progress:
                        print(f"[{idx}]   unexpected search payload shape")
                    continue
                if args.dry_run:
                    added_any = True
                    if not args.no_progress:
                        print(f"[{idx}] MIGRATE '{title}' via '{src.get('name')}' -> OK (dry-run)")
                else:
                    try:
                        added_any = client_auth.add_to_library(alt_id)
                    except Exception as e:
                        if args.debug_library and not args.no_progress:
                            print(f"[{idx}]   add_to_library error for id={alt_id}: {e}")
                        added_any = False
                    if not args.no_progress:
                        print(f"[{idx}] MIGRATE '{title}' via '{src.get('name')}' -> {'OK' if added_any else 'FAIL'}")
                per_site_counts[skey] = cnt + 1
                if added_any and args.migrate_remove and not args.dry_run:
                    try:
                        rm_ok = client_auth.remove_from_library(mid_int)
                        if not args.no_progress:
                            print(f"[{idx}] REMOVE original -> {'OK' if rm_ok else 'FAIL'}")
                    except Exception:
                        pass
                if added_any:
                    migrated += 1
                    break
            if not added_any:
                failed += 1
            # Optional light throttle between items if --throttle set
            if args.throttle:
                time.sleep(max(0.0, float(args.throttle)))
        print(f"Migrate summary: migrated={migrated} skipped={skipped} failed={failed}")
        return 0 if failed == 0 else 6

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
    lists_membership=lists_membership if args.import_lists else None,
    lists_category_map=lists_category_map if args.import_lists else None,
    lists_ignore_set=lists_ignore_set if args.import_lists else None,
    rehome_conf={
        'enabled': args.rehoming_enabled,
        'sources': [s.strip() for s in (args.rehoming_sources.split(',') if args.rehoming_sources else []) if s.strip()],
        'skip_if_ge': args.rehoming_skip_if_chapters_ge,
        'remove_md': args.rehoming_remove_mangadex,
    } if args.rehoming_enabled else None,
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
