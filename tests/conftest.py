import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, "py_modules"))
sys.path.insert(0, HERE)
FIXTURES = os.path.join(HERE, "fixtures")


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Point every plugin path at a temporary home."""
    from wowaddons import finders, paths

    home = tmp_path / "home"
    home.mkdir()
    runtime = home / "homebrew" / "data" / "WoW Addons"
    values = {
        "HOME": str(home),
        "SETTINGS_DIR": str(home / "homebrew" / "settings" / "WoW Addons"),
        "RUNTIME_DIR": str(runtime),
        "LOG_DIR": str(home / "homebrew" / "logs" / "WoW Addons"),
        "SETTINGS_FILE": str(home / "homebrew" / "settings" / "WoW Addons" / "settings.json"),
        "STATE_FILE": str(runtime / "state.json"),
        "JOURNAL_FILE": str(runtime / "journal.json"),
        "SNAPSHOT_DIR": str(runtime / "snapshots"),
        "RUNS_DIR": str(runtime / "runs"),
        "TMP_DIR": str(runtime / "tmp"),
        "WOWUP_CONFIG_DIR": str(home / ".config" / "WowUpCf"),
        "WOWUP_APPS_DIR": str(home / "Applications" / "WowUp-CF"),
        "WOWUP_LINK": str(home / "Applications" / "WowUp-CF" / "WowUp-CF.AppImage"),
        "WOWUP_SEARCH_DIRS": [str(home / "Applications" / "WowUp-CF"), str(home / "Applications"), str(home),
                              str(home / "Downloads")],
        "STEAM_ROOT_CANDIDATES": [str(home / ".local" / "share" / "Steam"), str(home / ".steam" / "steam")],
    }
    for k, v in values.items():
        monkeypatch.setattr(paths, k, v)
    monkeypatch.setattr(finders, "removable_roots", lambda: [])
    paths.ensure_dirs()
    return home
