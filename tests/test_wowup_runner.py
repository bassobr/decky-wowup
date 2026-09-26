import json
import os

import pytest
from helpers import RETAIL_ID, make_fake_wowup, record, write_wowup

from wowaddons import util, wowup_runner
from wowaddons.wowup_store import WowUpStore, addon_key

REAL_LOG = """[2026-09-24 10:42:25.876] [info]  Cannot import wow installations, no agent path
[2026-09-24 10:42:25.931] [info]  onAutoUpdateInterval
[2026-09-24 10:42:26.169] [info]  [AddonUpdate] Curse 91376 ConsolePort '3.2.5' -> '3.2.6'
[2026-09-24 10:42:28.840] [info]  [AddonUpdateComplete] Curse 91376 ConsolePort 3.2.6
[2026-09-24 10:49:30.453] [error] Failed to decode product db at /x Error: EISDIR: illegal operation on a directory, read
    at async decodeProducts (/tmp/.mount_WowUp-Q5EEGa/resources/app.asar/app-build/app/services/x.js:40:22)
[2026-09-24 10:42:28.844] [info]  [QuitApp]
"""


def test_parse_real_log_lines():
    res = wowup_runner.parse_log(REAL_LOG)
    assert res["updates"] == [{"provider": "Curse", "externalId": "91376", "name": "ConsolePort", "from": "3.2.5",
                               "to": "3.2.6"}]
    assert res["completed"][0]["version"] == "3.2.6" and res["quit"] is True
    assert len(res["errors"]) == 1 and res["errors"][0].startswith("Failed to decode product db")


def test_plan_flags_per_mode():
    a = record("a", "A", auto=True)
    b = record("b", "B", auto=False, external_id="200")
    other = record("c", "C", installation_id="other", external_id="300")
    ign = record("d", "D", external_id="400")
    ign["isIgnored"] = True
    addons = {"a": a, "b": b, "c": other, "d": ign}
    assert wowup_runner.plan_flags(addons, "auto") == {}
    assert wowup_runner.plan_flags(addons, "check") == {"a": False, "b": False, "c": False, "d": False}
    assert wowup_runner.plan_flags(addons, "all", installation_id=RETAIL_ID) == {"a": True, "b": True, "c": False,
                                                                                  "d": False}
    assert wowup_runner.plan_flags(addons, "selected", [addon_key(b)]) == {"a": False, "b": True, "c": False, "d": False}
    assert wowup_runner.plan_flags(addons, "all", blocked=["other"]) == {"a": True, "b": True, "c": False, "d": False}
    other["autoUpdateEnabled"] = True
    assert wowup_runner.plan_flags(addons, "auto", blocked=["other"]) == {"c": False}
    assert wowup_runner.plan_flags(addons, "selected", [addon_key(other)], blocked=["other"])["c"] is False
    with pytest.raises(ValueError):
        wowup_runner.plan_flags(addons, "bogus")


def _setup(tmp_path, notifications="true"):
    home = tmp_path / "cfghome"
    cfg = home / "WowUpCf"
    a = record("a", "Alpha", installed="1", latest="1", version="1.0", latest_version="1.0", auto=True)
    a.update({"_fakeLatestId": "2", "_fakeLatestVersion": "1.1"})
    b = record("b", "Beta", external_id="200", installed="5", latest="5", version="5.0", latest_version="5.0", auto=False)
    b.update({"_fakeLatestId": "6", "_fakeLatestVersion": "5.1"})
    write_wowup(str(cfg), {"wow_installations": [{"id": RETAIL_ID, "clientType": 0, "location": "/x/_retail_/Wow.exe"}],
                           "enable_system_notifications": notifications}, {"a": a, "b": b})
    app = make_fake_wowup(str(tmp_path))
    kwargs = dict(use_gamescope=False, config_home=str(home), journal_path=str(tmp_path / "journal.json"),
                  runs_dir=str(tmp_path / "runs"), timeout=30)
    return WowUpStore(str(cfg)), app, kwargs


def test_check_mode_installs_nothing_and_restores_everything(tmp_path):
    store, app, kw = _setup(tmp_path)
    res = wowup_runner.run(store, app, "check", **kw)
    assert res["ok"] and res["updated"] == [] and res["pending"] == 2
    addons = store.load_addons()
    assert addons["a"]["autoUpdateEnabled"] is True and addons["b"]["autoUpdateEnabled"] is False
    assert addons["a"]["externalLatestReleaseId"] == "2"  # latest info refreshed
    assert store.load_prefs()["enable_system_notifications"] == "true"
    assert not os.path.exists(kw["journal_path"])


def test_all_mode_updates_everything_even_with_notifications_on(tmp_path):
    store, app, kw = _setup(tmp_path, notifications="true")
    res = wowup_runner.run(store, app, "all", **kw)
    assert res["ok"] and not res["timedOut"]
    assert sorted(u["name"] for u in res["updated"]) == ["Alpha", "Beta"] and res["pending"] == 0
    assert [u["name"] for u in res["updates"]] == ["Alpha", "Beta"]
    addons = store.load_addons()
    assert addons["b"]["autoUpdateEnabled"] is False  # user's flag restored
    assert store.load_prefs()["enable_system_notifications"] == "true"


def test_selected_mode_only_touches_selection(tmp_path):
    store, app, kw = _setup(tmp_path)
    b_key = addon_key(store.load_addons()["b"])
    res = wowup_runner.run(store, app, "selected", [b_key], **kw)
    assert [u["name"] for u in res["updated"]] == ["Beta"]
    addons = store.load_addons()
    assert addons["a"]["installedVersion"] == "1.0" and addons["a"]["autoUpdateEnabled"] is True


def test_timeout_kills_and_restores(tmp_path):
    store, app, kw = _setup(tmp_path)
    open(os.path.join(store.dir, "fake-behavior"), "w").write("hang")
    kw["timeout"] = 1
    res = wowup_runner.run(store, app, "all", **kw)
    assert res["timedOut"] and not res["ok"]
    assert store.load_addons()["b"]["autoUpdateEnabled"] is False
    assert not os.path.exists(kw["journal_path"])


def test_recover_after_crash(tmp_path):
    store, _, kw = _setup(tmp_path)
    addons = store.load_addons()
    key_a = addon_key(addons["a"])
    addons["a"]["autoUpdateEnabled"] = False  # state a crashed run left behind
    store.save_addons(addons)
    prefs = store.load_prefs()
    prefs["enable_system_notifications"] = "false"
    store.save_prefs(prefs)
    util.write_json(kw["journal_path"], {"runId": "x", "configDir": store.dir, "flags": {key_a: True},
                                         "prefs": {"enable_system_notifications": "true"}})
    res = wowup_runner.recover(store, kw["journal_path"])
    assert res["flagsRestored"] == 1 and res["prefsRestored"] == ["enable_system_notifications"]
    assert store.load_addons()["a"]["autoUpdateEnabled"] is True
    assert store.load_prefs()["enable_system_notifications"] == "true"
    assert wowup_runner.recover(store, kw["journal_path"]) is None


def test_missing_notification_pref_is_removed_again(tmp_path):
    store, app, kw = _setup(tmp_path)
    prefs = store.load_prefs()
    del prefs["enable_system_notifications"]
    store.save_prefs(prefs)
    wowup_runner.run(store, app, "check", **kw)
    assert "enable_system_notifications" not in store.load_prefs()


def test_command_and_env():
    assert wowup_runner.build_command("/a/WowUp.AppImage", use_gamescope=False) == ["/a/WowUp.AppImage", "--hidden",
                                                                                     "--quit"]
    cmd = wowup_runner.build_command("/a/WowUp.AppImage")
    assert cmd[1:7] == ["--backend", "headless", "-W", "1280", "-H", "800"] and cmd[-3:] == ["/a/WowUp.AppImage",
                                                                                         "--hidden", "--quit"]
    env = wowup_runner.build_env("/sandbox")
    assert env["XDG_CONFIG_HOME"] == "/sandbox"
    assert not any(k in env for k in ("DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS", "LD_LIBRARY_PATH"))
    json.dumps(env)
