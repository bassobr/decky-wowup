"""WowUp-CF data files (electron-store JSON): addons.json, preferences.json and the main log.

electron-store writes tab-indented JSON without a trailing newline and mode 0666; writes here
keep that format and the mode found on disk, and only ever happen while WowUp is not running.
"""
from __future__ import annotations

import json
import os
import stat
from typing import Any, Dict, List, Optional

from . import util, wow
from .constants import CLIENT_TYPES, WOWUP_CHANNEL_BETA, WOWUP_CHANNEL_PREF, WOWUP_PROCESS_NAMES

ELECTRON_STORE_MODE = 0o666
CHANNELS = {0: "stable", 1: "beta", 2: "alpha"}


def addon_key(a: Dict[str, Any]) -> str:
    """Stable identity; WowUp regenerates the record id on every rescan."""
    return f"{a.get('installationId')}|{a.get('providerName')}|{a.get('externalId')}"


def _strip_v(s: Any) -> str:
    s = str(s or "").strip()
    return s[1:] if s[:1] in ("v", "V") else s


def needs_update(a: Dict[str, Any]) -> bool:
    """Same rule as WowUp (addon.utils.ts): release id or version differs, unless ignored."""
    if a.get("isIgnored"):
        return False
    latest, installed = a.get("externalLatestReleaseId"), a.get("installedExternalReleaseId")
    if latest and installed and str(latest) != str(installed):
        return True
    lv, iv = _strip_v(a.get("latestVersion")), _strip_v(a.get("installedVersion"))
    return bool(lv and iv and lv != iv)


def dump_electron(obj: Any) -> str:
    return json.dumps(obj, indent="\t", ensure_ascii=False)


def release_channel(prefs: Dict[str, Any]) -> str:
    return "beta" if str(prefs.get(WOWUP_CHANNEL_PREF)) == WOWUP_CHANNEL_BETA else "stable"


def is_running() -> bool:
    return bool(util.pids_by_name(WOWUP_PROCESS_NAMES))


def installation_label(label: Optional[str], client_type: Any) -> str:
    base = CLIENT_TYPES.get(client_type, (None, None, "WoW"))[2]
    text = (label or "").strip() or "{defaultName}"
    return text.replace("{defaultName}", base)


class WowUpStore:
    def __init__(self, config_dir: str):
        self.dir = config_dir

    @property
    def prefs_path(self) -> str:
        return os.path.join(self.dir, "preferences.json")

    @property
    def addons_path(self) -> str:
        return os.path.join(self.dir, "addons.json")

    @property
    def log_path(self) -> str:
        return os.path.join(self.dir, "logs", "main.log")

    def exists(self) -> bool:
        return os.path.isfile(self.prefs_path)

    # ------------------------------------------------------------ read/write
    def load_prefs(self) -> Dict[str, Any]:
        d = util.read_json(self.prefs_path, {})
        return d if isinstance(d, dict) else {}

    def load_addons(self) -> Dict[str, Dict[str, Any]]:
        d = util.read_json(self.addons_path, {})
        return {k: v for k, v in d.items() if isinstance(v, dict)} if isinstance(d, dict) else {}

    def _write(self, path: str, obj: Any) -> None:
        try:
            mode = stat.S_IMODE(os.stat(path).st_mode)
        except OSError:
            mode = ELECTRON_STORE_MODE
        util.atomic_write_text(path, dump_electron(obj), mode)

    def save_prefs(self, prefs: Dict[str, Any]) -> None:
        self._write(self.prefs_path, prefs)

    def save_addons(self, addons: Dict[str, Dict[str, Any]]) -> None:
        self._write(self.addons_path, addons)

    # ------------------------------------------------------------ views
    def installations(self, prefs: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        prefs = self.load_prefs() if prefs is None else prefs
        out = []
        for wi in prefs.get("wow_installations") or []:
            if not isinstance(wi, dict):
                continue
            location = str(wi.get("location") or "")
            flavor_dir = os.path.dirname(location)
            ct = wi.get("clientType")
            out.append({
                "id": wi.get("id"),
                "clientType": ct,
                "clientTypeLabel": CLIENT_TYPES.get(ct, (None, None, "Unknown"))[2],
                "label": installation_label(wi.get("label"), ct),
                "location": location,
                "flavorDir": flavor_dir,
                "addonsDir": wow.find_addons_dir(flavor_dir) if flavor_dir else None,
                "exists": bool(flavor_dir) and os.path.isdir(flavor_dir),
                "selected": bool(wi.get("selected")),
            })
        return out

    # ------------------------------------------------------------ log
    def log_size(self) -> int:
        try:
            return os.path.getsize(self.log_path)
        except OSError:
            return 0

    def read_log_since(self, offset: int) -> str:
        """Log text written after `offset`; handles electron-log rotation to main.old.log."""
        try:
            size = os.path.getsize(self.log_path)
        except OSError:
            return ""
        parts = []
        if size < offset:
            try:
                with open(os.path.join(self.dir, "logs", "main.old.log"), "rb") as f:
                    f.seek(offset)
                    parts.append(f.read())
            except OSError:
                pass
            offset = 0
        try:
            with open(self.log_path, "rb") as f:
                f.seek(offset)
                parts.append(f.read())
        except OSError:
            pass
        return b"".join(parts).decode("utf-8", "replace")
