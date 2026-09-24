import os

from helpers import RETAIL_ID, make_addon, make_fake_wowup, make_steam, record, write_wowup

from wowaddons import paths, settings, wowup_runner
from wowaddons.service import Service
from wowaddons.wowup_store import WowUpStore, addon_key


def _service(sandbox, monkeypatch, with_classic_beta=True):
    flavors = [("wow", "_retail_", "12.1.0.69933", "eu", "Wow.exe")]
    if with_classic_beta:
        flavors.append(("wow_classic_beta", "_classic_beta_", "1.60.1.69977", "us", "WowB.exe"))
    tree = make_steam(str(sandbox), flavors=tuple(flavors))
    retail = os.path.join(tree["root"], "_retail_")
    addons_dir = os.path.join(retail, "Interface", "AddOns")
    make_addon(addons_dir, "Fresh", "120100", body="v1\n")
    make_addon(addons_dir, "Legacy", "110207")
    make_addon(addons_dir, "Loose", "120100")
    fresh = record("r1", "Fresh", external_id="1", installed="1", latest="1", version="1.0", latest_version="1.0")
    fresh.update({"_fakeLatestId": "2", "_fakeLatestVersion": "1.1"})
    legacy = record("r2", "Legacy", external_id="2", auto=False)
    # spelled via the ~/.steam/steam symlink, like WowUp stores it on the Deck
    os.makedirs(os.path.join(str(sandbox), ".steam"), exist_ok=True)
    os.symlink(tree["steam"], os.path.join(str(sandbox), ".steam", "steam"))
    location = retail.replace(tree["steam"], os.path.join(str(sandbox), ".steam", "steam")) + "/Wow.exe"
    write_wowup(paths.WOWUP_CONFIG_DIR, {"wow_installations": [{"id": RETAIL_ID, "clientType": 0, "label": "World of Warcraft",
                                                                "location": location, "selected": True}],
                                         "enable_system_notifications": "true"}, {"r1": fresh, "r2": legacy})
    app = make_fake_wowup(str(sandbox))
    s = settings._merge(settings.DEFAULTS, {"wowup": {"appImage": app, "verified": True}})
    monkeypatch.setattr(wowup_runner, "build_command", lambda appimage, use_gamescope=True: [appimage, "--hidden", "--quit"])
    monkeypatch.setattr(wowup_runner, "build_env", lambda config_home=None: {
        "PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(sandbox),
        "XDG_CONFIG_HOME": config_home or os.path.dirname(paths.WOWUP_CONFIG_DIR)})
    return Service(s, lambda: None, WowUpStore(paths.WOWUP_CONFIG_DIR)), addons_dir, tree


def test_state_merges_discovery_and_compat(sandbox, monkeypatch):
    svc, addons_dir, _ = _service(sandbox, monkeypatch)
    st = svc.state(refresh=True)
    inst = st["installations"][0]
    assert inst["gameType"] == "mainline" and inst["version"] == "12.1.0.69933" and inst["label"] == "World of Warcraft"
    assert inst["addonCount"] == 2 and inst["updateCount"] == 0 and inst["incompatibleCount"] == 1
    assert inst["unmanaged"] == ["Loose"]
    by_name = {a["name"]: a for a in st["addons"][RETAIL_ID]}
    assert by_name["Fresh"]["compat"] == "ok" and by_name["Legacy"]["compat"] == "incompatible"
    assert [d["product"] for d in st["missingInWowUp"]] == ["wow_classic_beta"]
    assert st["wowup"]["version"] == "2.23.1" and st["wowup"]["channel"] == "stable"


def test_run_all_snapshots_and_rollback(sandbox, monkeypatch):
    svc, addons_dir, _ = _service(sandbox, monkeypatch)
    res = svc.run_update("all", RETAIL_ID)
    assert res["ok"] and [u["name"] for u in res["updated"]] == ["Fresh"] and len(res["snapshots"]) == 1
    rec = WowUpStore(paths.WOWUP_CONFIG_DIR).load_addons()
    assert rec["r1"]["installedVersion"] == "1.1" and rec["r2"]["autoUpdateEnabled"] is False
    # simulate the new files the update wrote
    lua = os.path.join(addons_dir, "Fresh", "Fresh.lua")
    os.unlink(lua)
    open(lua, "w").write("v2\n")
    out = svc.restore_snapshot(res["snapshots"][0], [addon_key(rec["r1"])])
    assert out["restored"] == ["Fresh"] and out["recordsRestored"] == 1
    assert open(lua).read() == "v1\n"
    rec = WowUpStore(paths.WOWUP_CONFIG_DIR).load_addons()
    assert rec["r1"]["installedVersion"] == "1.0" and rec["r1"]["installedExternalReleaseId"] == "1"


def test_check_run_keeps_no_snapshot(sandbox, monkeypatch):
    svc, _, _ = _service(sandbox, monkeypatch)
    res = svc.run_update("check")
    assert res["ok"] and res["snapshots"] == [] and res["pending"] == 1
    assert svc.state()["lastRun"]["mode"] == "check"


def test_agent_path_reuses_existing_spelling(sandbox, monkeypatch):
    svc, _, tree = _service(sandbox, monkeypatch)
    pdb = os.path.realpath(os.path.join(tree["pfx"], "drive_c", "ProgramData", "Battle.net", "Agent", "product.db"))
    agent = svc._agent_path_like_existing(pdb, svc.store.load_prefs())
    assert agent.startswith(os.path.join(str(sandbox), ".steam", "steam")) and agent.endswith("Agent/product.db")
    assert os.path.realpath(agent) == pdb


def test_dedupe_keeps_entry_with_addons(sandbox, monkeypatch):
    svc, _, tree = _service(sandbox, monkeypatch)
    prefs = svc.store.load_prefs()
    real_loc = os.path.join(os.path.realpath(tree["root"]), "_retail_", "Wow.exe")
    prefs["wow_installations"].append({"id": "dup", "clientType": 0, "label": "{defaultName} 2", "location": real_loc})
    svc.store.save_prefs(prefs)
    assert svc._dedupe_installations() == 1
    assert [w["id"] for w in svc.store.load_prefs()["wow_installations"]] == [RETAIL_ID]
