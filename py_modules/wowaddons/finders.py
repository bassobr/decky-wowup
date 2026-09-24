"""Where World of Warcraft can live on a Linux handheld.

Every route ends in one of two things, independent of the launcher:
  prefix – a Wine prefix (drive_c/…) with Battle.net's product.db or a WoW folder in the default place;
  root   – a WoW folder (.build.info plus _retail_, _classic_era_ …), e.g. copied from a Windows PC.

Sources: Steam (Proton compatdata, incl. NonSteamLaunchers), Bottles, Lutris, Heroic, plain Wine,
CrossOver, user search folders, SD cards/USB drives, and folders added by hand.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from . import paths, steam, util
from .constants import FOLDER_TO_CLIENT_TYPE

Candidate = Dict[str, Any]

PRODUCT_DB = os.path.join("drive_c", "ProgramData", "Battle.net", "Agent", "product.db")
DEFAULT_WOW_DIRS = (os.path.join("drive_c", "Program Files (x86)", "World of Warcraft"),
                    os.path.join("drive_c", "Program Files", "World of Warcraft"))
LUTRIS_DEFAULT_NAMES = ("battlenet", "battle-net", "battle.net", "world-of-warcraft", "world-of-warcraft-classic")
SCAN_SKIP = {"steamapps", "compatdata", "shadercache", "node_modules", "proc", "sys", "dev", "lost+found",
             "$recycle.bin", "system volume information", "drive_c", "dosdevices"}
SCAN_MAX_DEPTH = 3
SCAN_MAX_DIRS = 4000


def _home(*parts: str) -> str:
    return os.path.join(paths.HOME, *parts)


def _subdirs(base: str) -> List[str]:
    try:
        return sorted(os.path.join(base, e) for e in os.listdir(base) if os.path.isdir(os.path.join(base, e)))
    except OSError:
        return []


def _prefix_dir(path: str) -> Optional[str]:
    """Wine prefix dir (containing drive_c); Proton-style '<dir>/pfx' is accepted too."""
    if not path:
        return None
    path = os.path.expanduser(path)
    if os.path.isdir(os.path.join(path, "drive_c")):
        return path
    if os.path.isdir(os.path.join(path, "pfx", "drive_c")):
        return os.path.join(path, "pfx")
    return None


def has_wow(prefix: str) -> bool:
    return os.path.isfile(os.path.join(prefix, PRODUCT_DB)) or any(
        os.path.isdir(os.path.join(prefix, d)) for d in DEFAULT_WOW_DIRS)


def is_wow_root(path: str) -> bool:
    if not os.path.isdir(path):
        return False
    try:
        entries = {e.lower() for e in os.listdir(path)}
    except OSError:
        return False
    return ".build.info" in entries and any(f in entries for f in FOLDER_TO_CLIENT_TYPE)


def _cand(kind: str, path: str, source: str, source_type: str, **extra: Any) -> Candidate:
    c = {"kind": kind, "path": path, "source": source, "sourceType": source_type}
    c.update(extra)
    return c


def _yaml_value(text: str, key: str) -> Optional[str]:
    m = re.search(r"^\s*" + re.escape(key) + r":\s*(.+?)\s*$", text, re.M)
    if not m:
        return None
    v = m.group(1).strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1]
    return v or None


# ---------------------------------------------------------------- sources
def steam_candidates() -> List[Candidate]:
    out = []
    for p in steam.compat_prefixes():
        if not has_wow(p["prefix"]):
            continue
        name = p.get("shortcut") or (str(p["appId"]) if p.get("appId") else os.path.basename(os.path.dirname(p["prefix"])))
        out.append(_cand("prefix", p["prefix"], f"Steam: {name}", "steam", appId=p.get("appId"), shortcut=p.get("shortcut")))
    return out


def bottles_candidates() -> List[Candidate]:
    out = []
    for base in (_home(".var", "app", "com.usebottles.bottles", "data", "bottles", "bottles"),
                 _home(".local", "share", "bottles", "bottles")):
        for d in _subdirs(base):
            pfx = _prefix_dir(d)
            if not pfx or not has_wow(pfx):
                continue
            name = os.path.basename(d)
            try:
                with open(os.path.join(d, "bottle.yml"), encoding="utf-8", errors="replace") as f:
                    name = _yaml_value(f.read(), "Name") or name
            except OSError:
                pass
            out.append(_cand("prefix", pfx, f"Bottles: {name}", "bottles"))
    return out


def lutris_candidates() -> List[Candidate]:
    out = []
    game_dirs = [_home(".config", "lutris", "games"), _home(".local", "share", "lutris", "games"),
                 _home(".var", "app", "net.lutris.Lutris", "config", "lutris", "games"),
                 _home(".var", "app", "net.lutris.Lutris", "data", "lutris", "games")]
    for gd in game_dirs:
        try:
            files = sorted(f for f in os.listdir(gd) if f.endswith((".yml", ".yaml")))
        except OSError:
            continue
        for f in files:
            try:
                with open(os.path.join(gd, f), encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            pfx = _prefix_dir(_yaml_value(text, "prefix") or "")
            if pfx and has_wow(pfx):
                name = _yaml_value(text, "name") or re.sub(r"-\d+$", "", os.path.splitext(f)[0])
                out.append(_cand("prefix", pfx, f"Lutris: {name}", "lutris"))
    # Lutris' default install folder (the same guess WowUp makes on Linux)
    bases = [_home("Games")]
    for sysyml in (_home(".config", "lutris", "system.yml"), _home(".var", "app", "net.lutris.Lutris", "config", "lutris", "system.yml")):
        try:
            with open(sysyml, encoding="utf-8", errors="replace") as fh:
                gp = _yaml_value(fh.read(), "game_path")
            if gp:
                bases.append(os.path.expanduser(gp))
        except OSError:
            pass
    for base in bases:
        for name in LUTRIS_DEFAULT_NAMES:
            pfx = _prefix_dir(os.path.join(base, name))
            if pfx and has_wow(pfx):
                out.append(_cand("prefix", pfx, f"Lutris: {name}", "lutris"))
    return out


def heroic_candidates() -> List[Candidate]:
    out = []
    for cfg in (_home(".config", "heroic"), _home(".var", "app", "com.heroicgameslauncher.hgl", "config", "heroic")):
        titles: Dict[str, str] = {}
        lib = util.read_json(os.path.join(cfg, "sideload_apps", "library.json"), {}) or {}
        for g in lib.get("games") or [] if isinstance(lib, dict) else []:
            if isinstance(g, dict) and g.get("app_name"):
                titles[str(g["app_name"])] = str(g.get("title") or g["app_name"])
        try:
            files = sorted(f for f in os.listdir(os.path.join(cfg, "GamesConfig")) if f.endswith(".json"))
        except OSError:
            files = []
        for f in files:
            data = util.read_json(os.path.join(cfg, "GamesConfig", f), {}) or {}
            for app, conf in (data.items() if isinstance(data, dict) else []):
                if not isinstance(conf, dict):
                    continue
                pfx = _prefix_dir(str(conf.get("winePrefix") or ""))
                if pfx and has_wow(pfx):
                    out.append(_cand("prefix", pfx, f"Heroic: {titles.get(app, app)}", "heroic"))
    for base in (_home("Games", "Heroic", "Prefixes", "default"), _home("Games", "Heroic", "Prefixes")):
        for d in _subdirs(base):
            pfx = _prefix_dir(d)
            if pfx and has_wow(pfx):
                out.append(_cand("prefix", pfx, f"Heroic: {os.path.basename(d)}", "heroic"))
    return out


def wine_candidates() -> List[Candidate]:
    out = []
    for d in [_home(".wine")] + _subdirs(_home(".local", "share", "wineprefixes")):
        pfx = _prefix_dir(d)
        if pfx and has_wow(pfx):
            out.append(_cand("prefix", pfx, f"Wine: {os.path.basename(d)}", "wine"))
    for d in _subdirs(_home(".cxoffice")):
        pfx = _prefix_dir(d)
        if pfx and has_wow(pfx):
            out.append(_cand("prefix", pfx, f"CrossOver: {os.path.basename(d)}", "crossover"))
    return out


def removable_roots() -> List[str]:
    roots = []
    for base in (os.path.join("/run/media", paths.USER), "/run/media", "/media", "/mnt"):
        for d in _subdirs(base):
            if d not in roots and os.path.ismount(d):
                roots.append(d)
    return roots


def scan(base: str, source: str, source_type: str, max_depth: int = SCAN_MAX_DEPTH) -> List[Candidate]:
    """Depth-limited search for prefixes and WoW roots below `base`."""
    out: List[Candidate] = []
    budget = [SCAN_MAX_DIRS]

    def walk(d: str, depth: int) -> None:
        if budget[0] <= 0:
            return
        budget[0] -= 1
        if is_wow_root(d):
            out.append(_cand("root", d, source, source_type))
            return
        pfx = _prefix_dir(d)
        if pfx and pfx == d and has_wow(pfx):
            out.append(_cand("prefix", pfx, source, source_type))
            return
        if depth >= max_depth:
            return
        try:
            entries = sorted(os.scandir(d), key=lambda e: e.name.lower())
        except OSError:
            return
        for e in entries:
            if e.name.startswith(".") or e.name.lower() in SCAN_SKIP:
                continue
            try:
                if e.is_dir(follow_symlinks=False):
                    walk(e.path, depth + 1)
            except OSError:
                continue

    if os.path.isdir(base):
        walk(base, 0)
    return out


def manual_candidates(path: str) -> List[Candidate]:
    """Resolve a folder picked by hand: a prefix, a WoW root, a flavor folder or its parent."""
    path = os.path.realpath(os.path.expanduser(path or ""))
    if not os.path.isdir(path):
        raise RuntimeError(f"folder not found: {path}")
    source = "Added manually"
    pfx = _prefix_dir(path)
    if pfx and has_wow(pfx):
        return [_cand("prefix", pfx, source, "manual")]
    if is_wow_root(path):
        return [_cand("root", path, source, "manual")]
    if os.path.basename(path).lower() in FOLDER_TO_CLIENT_TYPE and is_wow_root(os.path.dirname(path)):
        return [_cand("root", os.path.dirname(path), source, "manual")]
    found = scan(path, source, "manual", max_depth=2)
    if found:
        return found
    raise RuntimeError("no World of Warcraft installation found in this folder")


def candidates(settings: Optional[Dict[str, Any]] = None) -> List[Candidate]:
    disc = (settings or {}).get("discovery") or {}
    out: List[Candidate] = []
    for finder in (steam_candidates, bottles_candidates, lutris_candidates, heroic_candidates, wine_candidates):
        try:
            out += finder()
        except Exception:  # one broken launcher config must not hide the others
            continue
    for p in disc.get("manualPaths") or []:
        try:
            out += manual_candidates(p)
        except RuntimeError:
            continue
    for p in (disc.get("searchPaths") or []) + [_home("Games")]:
        out += scan(os.path.expanduser(p), f"Search folder: {p}", "search")
    if disc.get("scanRemovable", True):
        for r in removable_roots():
            out += scan(r, f"Drive: {os.path.basename(r)}", "removable")
    return out


def summary(cands: List[Candidate]) -> Dict[str, int]:
    counts: Dict[str, int] = {k: 0 for k in ("steam", "bottles", "lutris", "heroic", "wine", "crossover",
                                             "search", "removable", "manual")}
    seen = set()
    for c in cands:
        key = (c["sourceType"], os.path.realpath(c["path"]))
        if key not in seen:
            seen.add(key)
            counts[c["sourceType"]] = counts.get(c["sourceType"], 0) + 1
    return counts

