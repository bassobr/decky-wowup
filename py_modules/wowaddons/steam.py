"""Steam: roots, library folders, non-Steam shortcuts (binary VDF) and Proton prefixes."""
from __future__ import annotations

import os
import re
import struct
from typing import Any, Dict, List, Optional, Tuple

from . import paths
from .log import logger


def parse_binary_vdf(data: bytes, i: int = 0) -> Tuple[Dict[str, Any], int]:
    """Binary KeyValues as used by shortcuts.vdf: 0x00 map, 0x01 string, 0x02 int32, 0x08 end."""
    obj: Dict[str, Any] = {}
    n = len(data)
    while i < n:
        t = data[i]
        i += 1
        if t == 0x08:
            return obj, i
        j = data.index(b"\x00", i)
        key = data[i:j].decode("utf-8", "replace")
        i = j + 1
        if t == 0x00:
            val, i = parse_binary_vdf(data, i)
        elif t == 0x01:
            j = data.index(b"\x00", i)
            val = data[i:j].decode("utf-8", "replace")
            i = j + 1
        elif t == 0x02:
            val = struct.unpack_from("<i", data, i)[0]
            i += 4
        elif t == 0x03:
            val = struct.unpack_from("<f", data, i)[0]
            i += 4
        elif t == 0x07:
            val = struct.unpack_from("<Q", data, i)[0]
            i += 8
        else:
            raise ValueError(f"unsupported binary VDF type 0x{t:02x} at offset {i - 1}")
        obj[key] = val
    return obj, i


def steam_roots() -> List[str]:
    roots: List[str] = []
    for cand in paths.STEAM_ROOT_CANDIDATES:
        if not os.path.isdir(cand):
            continue
        real = os.path.realpath(cand)
        if real in roots:
            continue
        if os.path.isdir(os.path.join(real, "steamapps")) or os.path.isdir(os.path.join(real, "userdata")):
            roots.append(real)
    return roots


_PATH_RE = re.compile(r'"path"\s+"((?:[^"\\]|\\.)*)"')


def library_paths(root: str) -> List[str]:
    libs = [root]
    try:
        with open(os.path.join(root, "steamapps", "libraryfolders.vdf"), "r", encoding="utf-8", errors="replace") as f:
            for m in _PATH_RE.finditer(f.read()):
                libs.append(m.group(1).replace("\\\\", "\\"))
    except OSError:
        pass
    out: List[str] = []
    for p in libs:
        rp = os.path.realpath(p)
        if rp not in out and os.path.isdir(rp):
            out.append(rp)
    return out


def read_shortcuts(root: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    userdata = os.path.join(root, "userdata")
    try:
        users = sorted(os.listdir(userdata))
    except OSError:
        return out
    for user in users:
        f = os.path.join(userdata, user, "config", "shortcuts.vdf")
        if not os.path.isfile(f):
            continue
        try:
            with open(f, "rb") as fh:
                data, _ = parse_binary_vdf(fh.read())
        except (OSError, ValueError) as e:
            logger.warning("cannot parse %s: %s", f, e)
            continue
        for entry in (data.get("shortcuts") or {}).values():
            if not isinstance(entry, dict):
                continue
            low = {str(k).lower(): v for k, v in entry.items()}
            appid = low.get("appid")
            if not isinstance(appid, int):
                continue
            out.append({
                "userId": user,
                "appId": appid & 0xFFFFFFFF,  # names the compatdata folder
                "name": str(low.get("appname", "")),
                "exe": str(low.get("exe", "")).strip('"'),
                "startDir": str(low.get("startdir", "")).strip('"'),
                "launchOptions": str(low.get("launchoptions", "")),
            })
    return out


def battlenet_prefixes(roots: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Proton prefixes (compatdata/<id>/pfx) that contain Battle.net's product.db, newest first."""
    roots = steam_roots() if roots is None else roots
    shortcuts: Dict[int, Dict[str, Any]] = {}
    for r in roots:
        for s in read_shortcuts(r):
            shortcuts.setdefault(s["appId"], s)
    found: List[Dict[str, Any]] = []
    seen = set()
    for r in roots:
        for lib in library_paths(r):
            cd = os.path.join(lib, "steamapps", "compatdata")
            try:
                ids = os.listdir(cd)
            except OSError:
                continue
            for d in ids:
                pfx = os.path.join(cd, d, "pfx")
                pdb = os.path.join(pfx, "drive_c", "ProgramData", "Battle.net", "Agent", "product.db")
                if not os.path.isfile(pdb):
                    continue
                real = os.path.realpath(pfx)
                if real in seen:
                    continue
                seen.add(real)
                appid = int(d) if d.isdigit() else None
                sc = shortcuts.get(appid) if appid is not None else None
                found.append({"appId": appid, "prefix": real, "productDb": os.path.realpath(pdb),
                              "shortcut": sc["name"] if sc else None, "mtime": os.path.getmtime(pdb)})
    found.sort(key=lambda x: x["mtime"], reverse=True)
    return found
