"""Filesystem layout; DECKY_* variables take precedence, the CLI falls back to the same locations."""
from __future__ import annotations

import os

from .constants import PLUGIN_NAME, WOWUP_CONFIG_NAME, WOWUP_LINK_NAME


def _plugin_dir_default() -> str:
    here = os.path.dirname(os.path.abspath(__file__))  # .../py_modules/wowaddons
    return os.path.abspath(os.path.join(here, os.pardir, os.pardir))


HOME = os.environ.get("DECKY_USER_HOME") or os.path.expanduser("~")
USER = os.environ.get("DECKY_USER") or os.environ.get("USER") or "deck"
PLUGIN_DIR = os.environ.get("WOWADDONS_PLUGIN_DIR") or os.environ.get("DECKY_PLUGIN_DIR") or _plugin_dir_default()
SETTINGS_DIR = os.environ.get("DECKY_PLUGIN_SETTINGS_DIR") or os.path.join(HOME, "homebrew", "settings", PLUGIN_NAME)
RUNTIME_DIR = os.environ.get("DECKY_PLUGIN_RUNTIME_DIR") or os.path.join(HOME, "homebrew", "data", PLUGIN_NAME)
LOG_DIR = os.environ.get("DECKY_PLUGIN_LOG_DIR") or os.path.join(HOME, "homebrew", "logs", PLUGIN_NAME)

SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")
STATE_FILE = os.path.join(RUNTIME_DIR, "state.json")
JOURNAL_FILE = os.path.join(RUNTIME_DIR, "journal.json")
SNAPSHOT_DIR = os.path.join(RUNTIME_DIR, "snapshots")
RUNS_DIR = os.path.join(RUNTIME_DIR, "runs")
TMP_DIR = os.path.join(RUNTIME_DIR, "tmp")
PUBKEY_FILE = os.path.join(PLUGIN_DIR, "minisign.pub")

# WowUp-CF: Electron userData (Decky does not set XDG_CONFIG_HOME) and the managed AppImage location.
WOWUP_CONFIG_DIR = os.path.join(HOME, ".config", WOWUP_CONFIG_NAME)
WOWUP_APPS_DIR = os.path.join(HOME, "Applications", "WowUp-CF")
WOWUP_LINK = os.path.join(WOWUP_APPS_DIR, WOWUP_LINK_NAME)
WOWUP_SEARCH_DIRS = [WOWUP_APPS_DIR, os.path.join(HOME, "Applications"), HOME, os.path.join(HOME, "Downloads")]

STEAM_ROOT_CANDIDATES = [
    os.path.join(HOME, ".local", "share", "Steam"),
    os.path.join(HOME, ".steam", "steam"),
    os.path.join(HOME, ".var", "app", "com.valvesoftware.Steam", ".local", "share", "Steam"),
]


def ensure_dirs() -> None:
    for d in (SETTINGS_DIR, RUNTIME_DIR, LOG_DIR, SNAPSHOT_DIR, RUNS_DIR, TMP_DIR):
        os.makedirs(d, exist_ok=True)
