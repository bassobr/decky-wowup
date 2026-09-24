"""WoW installations in Proton prefixes: products, flavor folders, build versions, game types."""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from . import battlenet, steam
from .constants import CLIENT_TYPES, FOLDER_TO_CLIENT_TYPE, GAME_TYPE_LABELS

EXE_NAMES = ("Wow.exe", "WowT.exe", "WowB.exe", "WowClassic.exe", "WowClassicT.exe", "WowClassicB.exe")


def ci_child(parent: str, name: str) -> Optional[str]:
    """Path of `name` inside `parent`, matched case-insensitively (Bazzite/btrfs prefixes are case-sensitive)."""
    exact = os.path.join(parent, name)
    if os.path.exists(exact):
        return exact
    try:
        low = name.lower()
        for entry in os.listdir(parent):
            if entry.lower() == low:
                return os.path.join(parent, entry)
    except OSError:
        pass
    return None


def read_build_info(root: str) -> List[Dict[str, str]]:
    """Rows of <root>/.build.info; header cells look like 'Version!STRING:0'."""
    p = ci_child(root, ".build.info")
    if not p:
        return []
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            lines = [ln.rstrip("\r\n") for ln in f if ln.strip()]
    except OSError:
        return []
    if not lines:
        return []
    cols = [c.split("!")[0].strip() for c in lines[0].split("|")]
    return [dict(zip(cols, ln.split("|"))) for ln in lines[1:]]


def read_flavor_info(flavor_dir: str) -> Optional[str]:
    p = ci_child(flavor_dir, ".flavor.info")
    if not p:
        return None
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        return lines[1] if len(lines) > 1 else None
    except OSError:
        return None


def game_type(version: Optional[str]) -> Tuple[Optional[str], Optional[int]]:
    """('mists', 50504) for '5.5.4.69934'; the interface number is major*10000 + minor*100 + patch."""
    nums = [int(x) for x in re.findall(r"\d+", version or "")[:3]]
    if len(nums) < 2:
        return None, None
    while len(nums) < 3:
        nums.append(0)
    major, minor, patch = nums
    iface = major * 10000 + minor * 100 + patch
    if major >= 6:  # classic flavors use majors 1-5; 6.x-9.x were retail before The War Within
        return "mainline", iface
    kind = {1: "forever" if minor >= 50 else "vanilla", 2: "tbc", 3: "titan" if minor >= 50 else "wrath",
            4: "cata", 5: "mists"}.get(major)
    return kind, iface


def flavor_version(flavor_dir: str) -> Tuple[Optional[str], Optional[str]]:
    """(product code, version) of a flavor folder from .flavor.info and the root .build.info."""
    code = read_flavor_info(flavor_dir)
    if not code:
        return None, None
    row = next((r for r in read_build_info(os.path.dirname(flavor_dir.rstrip("/"))) if r.get("Product") == code), {})
    return code, (row.get("Version") or "").strip() or None


def win_to_linux(prefix: str, win_path: str) -> Optional[str]:
    """'C:/Program Files (x86)/World of Warcraft' -> path inside the prefix via dosdevices symlinks."""
    m = re.match(r"^([A-Za-z]):[\\/]*(.*)$", win_path or "")
    if not m:
        return None
    rest = m.group(2).replace("\\", "/")
    dev = os.path.join(prefix, "dosdevices", f"{m.group(1).lower()}:")
    if os.path.lexists(dev):
        base = os.path.realpath(dev)
    elif m.group(1).lower() == "c":
        base = os.path.join(prefix, "drive_c")
    else:
        return None
    return os.path.normpath(os.path.join(base, rest)) if rest else base


def find_addons_dir(flavor_dir: str) -> str:
    iface = ci_child(flavor_dir, "Interface")
    if iface:
        addons = ci_child(iface, "AddOns")
        if addons:
            return addons
        return os.path.join(iface, "AddOns")
    return os.path.join(flavor_dir, "Interface", "AddOns")


def find_exe(flavor_dir: str) -> Optional[str]:
    for name in EXE_NAMES:
        p = ci_child(flavor_dir, name)
        if p and os.path.isfile(p):
            return p
    return None


def discover(prefixes: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """All WoW flavors Battle.net knows about in any Proton prefix."""
    prefixes = steam.battlenet_prefixes() if prefixes is None else prefixes
    out: List[Dict[str, Any]] = []
    seen = set()
    for p in prefixes:
        for prod in battlenet.read_products(p["productDb"]):
            if prod.get("family") != "wow" or not prod.get("installPath") or not prod.get("subfolder"):
                continue
            root = win_to_linux(p["prefix"], prod["installPath"])
            if not root:
                continue
            flavor_dir = ci_child(root, prod["subfolder"]) if os.path.isdir(root) else None
            if not flavor_dir or not os.path.isdir(flavor_dir):
                continue
            real = os.path.realpath(flavor_dir)
            if real in seen:
                continue
            seen.add(real)
            rows = read_build_info(root)
            row = next((r for r in rows if r.get("Product") == prod["code"]), {})
            version = (row.get("Version") or prod.get("version") or "").strip()
            gtype, iface = game_type(version)
            sub = os.path.basename(flavor_dir)
            ctype = FOLDER_TO_CLIENT_TYPE.get(sub.lower())
            addons_dir = find_addons_dir(flavor_dir)
            out.append({
                "product": prod["code"],
                "subfolder": sub,
                "root": root,
                "flavorDir": flavor_dir,
                "addonsDir": addons_dir,
                "addonsDirExists": os.path.isdir(addons_dir),
                "exe": find_exe(flavor_dir),
                "version": version or None,
                "region": row.get("Branch") or None,
                "gameType": gtype,
                "gameTypeLabel": GAME_TYPE_LABELS.get(gtype or "", gtype),
                "interface": iface,
                "clientType": ctype,
                "clientTypeLabel": CLIENT_TYPES[ctype][2] if ctype is not None else None,
                "flavorInfo": read_flavor_info(flavor_dir),
                "ready": prod.get("installed") is not False and prod.get("playable") is not False,
                "prefix": p["prefix"],
                "productDb": p["productDb"],
                "prefixAppId": p.get("appId"),
                "shortcut": p.get("shortcut"),
            })
    return out
