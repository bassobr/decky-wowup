import json
import os

from helpers import RETAIL_ID, make_addon, make_fake_wowup, make_steam, record, write, write_wowup

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


def test_add_installations_uses_wowup_spelling_and_exe(sandbox, monkeypatch):
    svc, _, tree = _service(sandbox, monkeypatch)
    res = svc.add_installations(None)
    assert [a["clientType"] for a in res["added"]] == [5]
    assert [s["reason"] for s in res["skipped"]] == ["already in WowUp"]
    entries = svc.store.load_prefs()["wow_installations"]
    beta = entries[-1]
    steam_link = os.path.join(str(sandbox), ".steam", "steam")
    assert beta["location"].startswith(steam_link) and beta["location"].endswith("/_classic_beta_/WowClassicB.exe")
    assert os.path.realpath(os.path.dirname(beta["location"])) == os.path.realpath(os.path.join(tree["root"], "_classic_beta_"))
    assert set(beta) == {"id", "clientType", "defaultAddonChannelType", "defaultAutoUpdate", "label", "displayName",
                         "location", "selected"}
    assert beta["label"] == "{defaultName}" and beta["selected"] is False
    assert svc.add_installations(None)["added"] == []  # idempotent


def test_add_installation_path_and_second_retail(sandbox, monkeypatch):
    svc, _, _ = _service(sandbox, monkeypatch, with_classic_beta=False)
    copy = os.path.join(str(sandbox), "Copied", "World of Warcraft")
    write(os.path.join(copy, ".build.info"), "Branch!STRING:0|Version!STRING:0|Product!STRING:0\neu|12.1.0.1|wow\n"
                                              "eu|1.15.9.2|wow_classic_era\n")
    for sub in ("_retail_", "_classic_era_"):
        os.makedirs(os.path.join(copy, sub, "Interface", "AddOns"))
    res = svc.add_installation_path(os.path.join(copy, "_classic_era_"))  # a flavor folder picked by hand
    added = {a["clientType"]: a for a in res["added"]}
    assert sorted(added) == [0, 6] and res["found"] == 2
    assert added[6]["location"] == os.path.join(os.path.realpath(copy), "_classic_era_", "WowClassic.exe")
    labels = {w["clientType"]: w["label"] for w in svc.store.load_prefs()["wow_installations"] if w["id"] != RETAIL_ID}
    assert labels[0] == "{defaultName} (Added manually)"  # a second Retail next to the Steam one
    assert svc.settings["discovery"]["manualPaths"] == [os.path.realpath(copy)]
    st = svc.state(refresh=True)
    assert st["missingInWowUp"] == [] and {i["gameType"] for i in st["installations"]} == {"mainline", "vanilla"}


def test_seed_profile_writes_entries(sandbox, monkeypatch):
    svc, _, _ = _service(sandbox, monkeypatch)
    os.unlink(svc.store.prefs_path)
    assert svc._seed_profile() is True
    types = sorted(w["clientType"] for w in svc.store.load_prefs()["wow_installations"])
    assert types == [0, 5]


def test_dedupe_keeps_entry_with_addons(sandbox, monkeypatch):
    svc, _, tree = _service(sandbox, monkeypatch)
    prefs = svc.store.load_prefs()
    real_loc = os.path.join(os.path.realpath(tree["root"]), "_retail_", "Wow.exe")
    prefs["wow_installations"].append({"id": "dup", "clientType": 0, "label": "{defaultName} 2", "location": real_loc})
    svc.store.save_prefs(prefs)
    assert svc._dedupe_installations() == 1
    assert [w["id"] for w in svc.store.load_prefs()["wow_installations"]] == [RETAIL_ID]


def test_install_addons_with_dependency_failure_and_skip(sandbox, monkeypatch):
    svc, addons_dir, _ = _service(sandbox, monkeypatch)
    write_catalog = {
        "Curse|257550": {"name": "Immersion", "version": "1.4.60", "releaseId": "8940431", "folders": ["Immersion"],
                         "dependencies": [{"externalAddonId": "999", "type": 2}, {"externalAddonId": "5", "type": 1}]},
        "Curse|999": {"name": "LibNeeded", "version": "2.0", "folders": ["LibNeeded"]},
        "WowInterface|11190": {"name": "Bartender4", "version": "4.17.9.1", "folders": ["Bartender4"]},
    }
    with open(os.path.join(paths.WOWUP_CONFIG_DIR, "fake-catalog.json"), "w") as f:
        json.dump(write_catalog, f)
    res = svc.install_addons(RETAIL_ID, [
        {"provider": "Curse", "externalId": "257550", "name": ""},
        {"provider": "WowInterface", "externalId": "11190", "name": "Bartender4"},
        {"provider": "Curse", "externalId": "1", "name": "Fresh"},          # already installed (r1)
        {"provider": "Curse", "externalId": "424242", "name": "Unknown"},   # WowUp cannot install it
        {"provider": "Curse", "externalId": "12ab", "name": "bad"},
    ])
    assert sorted(i["name"] for i in res["installed"]) == ["Bartender4", "Immersion", "LibNeeded"]
    assert [s["externalId"] for s in res["skipped"]] == ["1"]
    assert sorted(f["externalId"] for f in res["failed"]) == ["12ab", "424242"]
    assert len(res["runs"]) == 2  # second pass for the required dependency
    records = WowUpStore(paths.WOWUP_CONFIG_DIR).load_addons()
    assert not [a for a in records.values() if a.get("externalId") == "424242"]  # no ghost record
    new = {a["name"]: a for a in records.values() if a["name"] in ("Immersion", "Bartender4")}
    assert new["Bartender4"]["providerName"] == "WowInterface" and new["Immersion"]["autoUpdateEnabled"] is True
    assert os.path.isdir(os.path.join(addons_dir, "LibNeeded"))


def test_search_marks_installed(sandbox, monkeypatch):
    svc, addons_dir, _ = _service(sandbox, monkeypatch)
    from wowaddons import catalog
    monkeypatch.setattr(catalog, "search_wowi", lambda q, gt, limit=30: [
        {"provider": "WowInterface", "externalId": "7", "name": "Legacy", "folders": ["Legacy"], "gameTypes": ["mainline"]},
        {"provider": "WowInterface", "externalId": "8", "name": "Loose", "folders": ["Loose"], "gameTypes": ["vanilla"]},
        {"provider": "WowInterface", "externalId": "9", "name": "Old", "folders": [], "gameTypes": [], "compatVersions": ["8.3.0"]},
        {"provider": "WowInterface", "externalId": "10", "name": "NoData", "folders": [], "gameTypes": [], "compatVersions": []}])
    monkeypatch.setattr(catalog, "search_hub", lambda q, ct, limit=20: [
        {"provider": "Curse", "externalId": "2", "name": "Legacy", "folders": [], "gameTypes": []}])
    res = svc.search_addons(RETAIL_ID, "le")
    wowi = {r["externalId"]: r for r in res["wowinterface"]}
    assert wowi["7"]["present"] is True and wowi["7"]["installed"] is False and wowi["7"]["compatible"] is True
    assert wowi["8"]["compatible"] is False and wowi["9"]["compatible"] is False and wowi["10"]["compatible"] is None
    assert res["hub"][0]["installed"] is True and res["errors"] == []
