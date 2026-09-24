"""Settings persistence (plugin settings only; WowUp's own files live in wowup_store)."""
from __future__ import annotations

import json
from typing import Any, Dict

from . import paths
from .constants import RUN_TIMEOUT_S, SNAPSHOT_KEEP
from .util import read_json, write_json

DEFAULTS: Dict[str, Any] = {
    "schema": 1,
    # appImage: path of the WowUp-CF AppImage in use; channel: "follow" (WowUp's own setting), "stable", "beta".
    "wowup": {"appImage": None, "verified": None, "channel": "follow", "autoCheck": True,
              "lastCheck": 0, "latest": None, "error": None},
    "runner": {"timeoutSec": RUN_TIMEOUT_S, "disableNotifications": True},
    "snapshots": {"keep": SNAPSHOT_KEEP},
    # extra folders to search for WoW (depth-limited), SD cards/USB drives, folders added by hand
    "discovery": {"searchPaths": [], "scanRemovable": True, "manualPaths": []},
    "ui": {"installationId": None, "wowupShortcutAppId": None, "wowupShortcutExe": None},
    "update": {"lastCheck": 0, "latest": None, "autoCheck": True, "autoRestartSteam": True, "error": None},
    # selftestConfigHome: run one check-only pass against a sandbox XDG_CONFIG_HOME at startup (development).
    "dev": {"selftestConfigHome": None},
}


def _merge(defaults: Any, data: Any) -> Any:
    if isinstance(defaults, dict):
        out = {}
        data = data if isinstance(data, dict) else {}
        for k, v in defaults.items():
            out[k] = _merge(v, data.get(k)) if k in data else json.loads(json.dumps(v))
        for k, v in data.items():
            if k not in out:
                out[k] = v
        return out
    return json.loads(json.dumps(defaults)) if data is None else data


def load() -> Dict[str, Any]:
    return _merge(DEFAULTS, read_json(paths.SETTINGS_FILE, {}) or {})


def save(s: Dict[str, Any]) -> None:
    write_json(paths.SETTINGS_FILE, s)


def timeout_s(s: Dict[str, Any]) -> int:
    try:
        v = int((s.get("runner") or {}).get("timeoutSec") or RUN_TIMEOUT_S)
    except (TypeError, ValueError):
        v = RUN_TIMEOUT_S
    return max(30, min(900, v))
