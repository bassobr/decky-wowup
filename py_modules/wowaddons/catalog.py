"""Addon catalogues that can be searched without API keys.

- WoWInterface: the public file list of the MMOUI API (≈8,000 addons, ≈6 MB), refreshed daily
  and searched locally.
- WowUp Hub: WowUp's own catalogue of GitHub-hosted addons, searched through its public API.

CurseForge has no key-free search. CurseForge addons are installed by project ID, or found in
WowUp-CF's own window. Results are installed through WowUp-CF as placeholder records
(see service.install_addons).
"""
from __future__ import annotations

import os
import re
import time
import urllib.parse
from typing import Any, Dict, List, Optional

from . import paths, util, wow
from .constants import RETAIL_MIN_INTERFACE
from .log import logger

WOWI_FILELIST = "https://api.mmoui.com/v3/game/WOW/filelist.json"
WOWI_MAX_AGE_S = 24 * 3600
HUB_API = "https://hub.wowup.io"

# WowUp client type -> WowUp Hub game type (wowup-lib wow-client.utils.ts, getWowGameType)
HUB_GAME_TYPES = {0: "retail", 2: "retail", 4: "retail", 8: "retail", 1: "mists", 3: "mists", 5: "forever",
                  6: "classic", 7: "classic", 9: "burningCrusade"}
# WowUp Hub game type -> game type as derived from the build version (wow.game_type)
HUB_TO_GAME_TYPE = {"retail": "mainline", "classic": "vanilla", "burningCrusade": "tbc", "wotlk": "wrath",
                    "cata": "cata", "mists": "mists", "forever": "forever"}

# Sort orders offered for results. "relevance" only differs from "popular" when there is a query;
# WowUp Hub has neither monthly downloads nor favourites and falls back to total downloads there.
SORTS = ("relevance", "popular", "downloads", "favorites", "updated", "name")

_wowi_cache: Dict[str, Any] = {"mtime": 0.0, "entries": []}
_TAG = re.compile(r"<[^>]+>")
_ENTITY = re.compile(r"&(#\d+|#x[0-9a-fA-F]+|[A-Za-z]+);")
_NAMED = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'", "nbsp": " ", "ndash": "–", "mdash": "—"}
_NON_WORD = re.compile(r"[^0-9a-z]+")


def html_to_text(s: Optional[str], limit: int = 280) -> str:
    """Plain text from untrusted HTML (never rendered as HTML in the Steam UI)."""
    def entity(m: "re.Match[str]") -> str:
        e = m.group(1)
        try:
            if e.startswith("#x"):
                return chr(int(e[2:], 16))
            if e.startswith("#"):
                return chr(int(e[1:]))
        except (ValueError, OverflowError):
            return " "
        return _NAMED.get(e.lower(), " ")

    text = _ENTITY.sub(entity, _TAG.sub(" ", s or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def norm(s: str) -> str:
    return _NON_WORD.sub(" ", (s or "").lower()).strip()


def _score(name_norm: str, folders: List[str], q: str, tokens: List[str]) -> int:
    if not tokens:
        return 0
    if name_norm == q:
        return 100
    if name_norm.startswith(q):
        return 80
    if any(f.lower() == q.replace(" ", "") or norm(f) == q for f in folders):
        return 75
    words = name_norm.split()
    if all(any(w.startswith(t) for w in words) for t in tokens):
        return 60
    if all(t in name_norm for t in tokens):
        return 40
    return 0


# ---------------------------------------------------------------- WoWInterface
def _wowi_path() -> str:
    return os.path.join(paths.RUNTIME_DIR, "catalog", "wowi-filelist.json")


def loadable_game_types(versions: List[str]) -> List[str]:
    """Game types an addon plausibly loads in; retail below 12.0 no longer loads since Midnight."""
    types = set()
    for v in versions:
        t, iface = wow.game_type(v)
        if t and not (t == "mainline" and (iface or 0) < RETAIL_MIN_INTERFACE):
            types.add(t)
    return sorted(types)


def _wowi_entry(e: Dict[str, Any]) -> Dict[str, Any]:
    compat = [c.get("version") for c in e.get("UICompatibility") or [] if isinstance(c, dict) and c.get("version")]
    types = loadable_game_types(compat)
    try:
        ts = int(e.get("UIDate") or 0) // 1000
        updated = time.strftime("%Y-%m-%d", time.gmtime(ts)) if ts else None
    except (TypeError, ValueError, OverflowError):
        ts, updated = 0, None
    thumbs = e.get("UIIMG_Thumbs") or []
    return {
        "provider": "WowInterface", "externalId": str(e.get("UID")), "name": str(e.get("UIName") or ""),
        "author": str(e.get("UIAuthorName") or ""), "version": str(e.get("UIVersion") or ""), "updated": updated,
        "downloads": _int(e.get("UIDownloadTotal")), "monthly": _int(e.get("UIDownloadMonthly")),
        "favorites": _int(e.get("UIFavoriteTotal")), "updatedTs": ts,
        "gameTypes": types, "compatVersions": compat[:6], "folders": [str(f) for f in e.get("UIDir") or []],
        "url": e.get("UIFileInfoURL"), "thumbnail": thumbs[0] if thumbs else None, "summary": "",
        "_norm": norm(str(e.get("UIName") or "")),
    }


def _int(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def sort_key(e: Dict[str, Any], sort: str) -> tuple:
    if sort == "downloads":
        return (-e.get("downloads", 0),)
    if sort == "favorites":
        return (-e.get("favorites", 0), -e.get("downloads", 0))
    if sort == "updated":
        return (-e.get("updatedTs", 0), -e.get("downloads", 0))
    if sort == "name":
        return (e.get("name", "").lower(),)
    return (-e.get("monthly", 0), -e.get("downloads", 0))  # popular


def wowi_entries(refresh: bool = False) -> List[Dict[str, Any]]:
    path = _wowi_path()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0.0
    if refresh or time.time() - mtime > WOWI_MAX_AGE_S:
        try:
            part = path + ".part"
            util.curl_download(WOWI_FILELIST, part, 90)
            if not isinstance(util.read_json(part), list):
                raise RuntimeError("unexpected file list format")
            os.replace(part, path)
            mtime = os.path.getmtime(path)
        except Exception as e:
            logger.warning("WoWInterface file list download failed: %s", e)
            if not mtime:
                raise RuntimeError(f"WoWInterface catalogue unavailable: {e}")
    if _wowi_cache["mtime"] != mtime:
        data = util.read_json(path, []) or []
        _wowi_cache.update(mtime=mtime, entries=[_wowi_entry(e) for e in data if isinstance(e, dict) and e.get("UID")])
    return _wowi_cache["entries"]


def _public(e: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in e.items() if not k.startswith("_")}


def _rank(e: Dict[str, Any], game_type: Optional[str], score: int, sort: str = "relevance") -> tuple:
    """Addons for this WoW version first, then by match quality or by the chosen order."""
    compatible = 1 if game_type and game_type in e["gameTypes"] else 0
    if sort == "relevance":
        return (-compatible, -score) + sort_key(e, "popular")
    return (-compatible,) + sort_key(e, sort)


def search_wowi(query: str, game_type: Optional[str], limit: int = 30, sort: str = "relevance") -> List[Dict[str, Any]]:
    q = norm(query)
    tokens = q.split()
    hits = []
    for e in wowi_entries():
        s = _score(e["_norm"], e["folders"], q, tokens)
        if s:
            hits.append((_rank(e, game_type, s, sort), e))
    hits.sort(key=lambda h: h[0])
    return [_public(e) for _, e in hits[:limit]]


def popular_wowi(game_type: Optional[str], limit: int = 25, sort: str = "popular") -> List[Dict[str, Any]]:
    entries = [e for e in wowi_entries() if not game_type or game_type in e["gameTypes"]]
    entries.sort(key=lambda e: sort_key(e, sort))
    return [_public(e) for e in entries[:limit]]


# ---------------------------------------------------------------- WowUp Hub
def _hub_entry(a: Dict[str, Any]) -> Dict[str, Any]:
    types = set()
    version, published = "", ""
    for r in a.get("releases") or []:
        for gv in r.get("game_versions") or []:
            t = HUB_TO_GAME_TYPE.get(str(gv.get("game_type") or ""))
            if t:
                types.add(t)
        version = version or str(r.get("tag_name") or "")
        published = max(published, str(r.get("published_at") or ""))  # ISO 8601, sorts as text
    ts = 0
    if published:
        try:
            ts = int(time.mktime(time.strptime(published[:19], "%Y-%m-%dT%H:%M:%S")))
        except ValueError:
            pass
    return {
        "provider": "WowUpHub", "externalId": str(a.get("id")), "name": str(a.get("repository_name") or ""),
        "author": str(a.get("owner_name") or ""), "version": version, "updated": published[:10] or None,
        "updatedTs": ts, "favorites": 0,
        "downloads": _int(a.get("total_download_count")), "monthly": 0, "gameTypes": sorted(types),
        "compatVersions": [], "folders": [], "url": a.get("repository") or a.get("homepage"),
        "thumbnail": a.get("image_url") or a.get("owner_image_url"), "summary": html_to_text(a.get("description")),
    }


def _hub_sorted(entries: List[Dict[str, Any]], sort: str) -> List[Dict[str, Any]]:
    if sort in ("relevance", "popular"):
        return entries  # the Hub's own order (match quality / featured)
    return sorted(entries, key=lambda e: sort_key(e, "downloads" if sort == "favorites" else sort))


def search_hub(query: str, client_type: Optional[int], limit: int = 20, sort: str = "relevance") -> List[Dict[str, Any]]:
    gt = HUB_GAME_TYPES.get(client_type if client_type is not None else 0, "retail")
    url = f"{HUB_API}/addons/search/{gt}?query={urllib.parse.quote(query.strip())}&limit={int(limit)}"
    data = util.curl_json(url, timeout=20, github=False)
    return _hub_sorted([_hub_entry(a) for a in (data or {}).get("addons") or [] if isinstance(a, dict) and a.get("id")],
                       sort)


def featured_hub(client_type: Optional[int], count: int = 20, sort: str = "popular") -> List[Dict[str, Any]]:
    """Featured addons; for other orders the recently updated ones are added before sorting."""
    gt = HUB_GAME_TYPES.get(client_type if client_type is not None else 0, "retail")
    data = util.curl_json(f"{HUB_API}/addons/featured/{gt}?count={int(count)}&recent=30", timeout=20, github=False) or {}
    lists = [data.get("addons") or []] + ([] if sort in ("relevance", "popular") else [data.get("recent") or []])
    out, seen = [], set()
    for lst in lists:
        for a in lst:
            if isinstance(a, dict) and a.get("id") and a["id"] not in seen:
                seen.add(a["id"])
                out.append(_hub_entry(a))
    return _hub_sorted(out, sort)[:max(count, 25)]
