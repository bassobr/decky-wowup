"""TOC selection and parsing; interface compatibility against the installed game version."""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .constants import RETAIL_MIN_INTERFACE

# Client picks exactly one TOC: flavor-specific suffix first, then the plain Name.toc.
TOC_SUFFIXES: Dict[str, List[str]] = {
    "mainline": ["mainline"],
    "forever": ["camelot", "mainline"],
    "vanilla": ["vanilla", "classic"],
    "tbc": ["tbc", "bcc", "classic"],
    "wrath": ["wrath", "wotlkc", "classic"],
    "titan": ["wrath", "wotlkc", "classic"],
    "cata": ["cata", "classic"],
    "mists": ["mists", "classic"],
}
CLASSIC_TYPES = {"vanilla", "tbc", "wrath", "titan", "cata", "mists"}

_CODES = re.compile(r"\|c[0-9a-fA-F]{8}|\|r|\|T[^|]*\|t|\|A[^|]*\|a|\|n")
_META = re.compile(r"^##\s*([A-Za-z0-9_\-]+)\s*(\[[^\]]*\])?\s*:\s?(.*)$")
_COND = re.compile(r"\[(AllowLoadGameType|ExcludeLoadGameType)\s+([^\]]*)\]", re.I)


def strip_codes(s: str) -> str:
    return _CODES.sub("", s or "").strip()


def pick_toc(folder: str, game_type: Optional[str]) -> Optional[str]:
    try:
        names = os.listdir(folder)
    except OSError:
        return None
    tocs = {n.lower(): n for n in names if n.lower().endswith(".toc")}
    base = os.path.basename(folder.rstrip("/")).lower()
    for suffix in TOC_SUFFIXES.get(game_type or "", []):
        for sep in ("_", "-"):
            hit = tocs.get(f"{base}{sep}{suffix}.toc")
            if hit:
                return os.path.join(folder, hit)
    plain = tocs.get(f"{base}.toc")
    return os.path.join(folder, plain) if plain else None


def _type_matches(names: List[str], game_type: Optional[str]) -> bool:
    if not game_type:
        return True
    for n in names:
        if n == game_type or (n == "classic" and game_type in CLASSIC_TYPES) \
                or (game_type == "forever" and n in ("camelot", "mainline")):
            return True
    return False


def _condition_ok(cond: str, game_type: Optional[str]) -> bool:
    for kind, arg in _COND.findall(cond or ""):
        names = [x.strip().lower() for x in re.split(r"[,\s]+", arg) if x.strip()]
        hit = _type_matches(names, game_type)
        if kind.lower() == "allowloadgametype" and not hit:
            return False
        if kind.lower() == "excludeloadgametype" and hit:
            return False
    return True


def parse_toc(path: str, game_type: Optional[str] = None) -> Dict[str, Any]:
    meta: Dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            for i, line in enumerate(f):
                if i > 2000:
                    break
                m = _META.match(line.rstrip("\r\n")[:1024])
                if not m:
                    continue
                key, cond, val = m.group(1), m.group(2), m.group(3).strip()
                if cond and not _condition_ok(cond, game_type):
                    continue
                meta.setdefault(key, val)
    except OSError:
        return {}
    deps = ",".join(v for k, v in meta.items() if k in ("Dependencies", "RequiredDeps") or re.match(r"^Dep\w*$", k))
    return {
        "title": strip_codes(meta.get("Title", "")) or None,
        "version": strip_codes(meta.get("Version", "")) or None,
        "author": strip_codes(meta.get("Author", "")) or None,
        "interfaces": [int(x) for x in re.findall(r"\d+", meta.get("Interface", ""))],
        "loadOnDemand": meta.get("LoadOnDemand", "").strip() == "1",
        "dependencies": [d.strip() for d in deps.split(",") if d.strip()],
        "ids": {"curse": meta.get("X-Curse-Project-ID") or None, "wowi": meta.get("X-WoWI-ID") or None,
                "wago": meta.get("X-Wago-ID") or None},
    }


def _series_match(value: int, game_type: str) -> bool:
    major, minor = value // 10000, (value // 100) % 100
    return {
        "mainline": major >= 10,
        "forever": major == 1 and minor >= 50,
        "vanilla": major == 1 and minor < 50,
        "tbc": major == 2,
        "wrath": major == 3 and minor < 50,
        "titan": major == 3 and minor >= 50,
        "cata": major == 4,
        "mists": major == 5,
    }.get(game_type, False)


def interface_status(interfaces: List[int], game_type: Optional[str],
                     game_interface: Optional[int]) -> Tuple[str, Optional[int]]:
    """'ok' | 'outdated' | 'incompatible' | 'unknown', plus the interface value used."""
    if not interfaces or not game_type:
        return "unknown", None
    in_series = [v for v in interfaces if _series_match(v, game_type)]
    if not in_series:
        # WoW: Forever is still in beta; its loading rules for mainline TOCs are not settled.
        return ("unknown" if game_type == "forever" else "incompatible"), max(interfaces)
    best = max(in_series)
    if game_type == "mainline" and best < RETAIL_MIN_INTERFACE:
        return "incompatible", best
    if game_interface and best < game_interface:
        return "outdated", best
    return "ok", best


def folder_status(folder: str, game_type: Optional[str], game_interface: Optional[int]) -> Dict[str, Any]:
    toc = pick_toc(folder, game_type)
    if not toc:
        return {"status": "unknown", "interface": None, "toc": None}
    info = parse_toc(toc, game_type)
    status, used = interface_status(info.get("interfaces") or [], game_type, game_interface)
    return {"status": status, "interface": used, "toc": os.path.basename(toc), "title": info.get("title"),
            "version": info.get("version"), "loadOnDemand": info.get("loadOnDemand", False),
            "ids": info.get("ids"), "dependencies": info.get("dependencies", [])}
