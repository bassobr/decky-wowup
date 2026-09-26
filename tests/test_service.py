import json
import os

import pytest

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
    os.makedirs(os.path.join(addons_dir, "wowup_data_addon"))  # WowUp's own, never "unmanaged"
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
    monkeypatch.setattr(catalog, "search_wowi", lambda q, gt, limit=30, sort="relevance": [
        {"provider": "WowInterface", "externalId": "7", "name": "Legacy", "folders": ["Legacy"], "gameTypes": ["mainline"]},
        {"provider": "WowInterface", "externalId": "8", "name": "Loose", "folders": ["Loose"], "gameTypes": ["vanilla"]},
        {"provider": "WowInterface", "externalId": "9", "name": "Old", "folders": [], "gameTypes": [], "compatVersions": ["8.3.0"]},
        {"provider": "WowInterface", "externalId": "10", "name": "NoData", "folders": [], "gameTypes": [], "compatVersions": []}])
    monkeypatch.setattr(catalog, "search_hub", lambda q, ct, limit=20, sort="relevance": [
        {"provider": "Curse", "externalId": "2", "name": "Legacy", "folders": [], "gameTypes": []}])
    res = svc.search_addons(RETAIL_ID, "le")
    wowi = {r["externalId"]: r for r in res["wowinterface"]}
    assert wowi["7"]["present"] is True and wowi["7"]["installed"] is False and wowi["7"]["compatible"] is True
    assert wowi["8"]["compatible"] is False and wowi["9"]["compatible"] is False and wowi["10"]["compatible"] is None
    assert res["hub"][0]["installed"] is True and res["errors"] == []


def test_warns_about_wowup_installation_without_game(sandbox, monkeypatch):
    svc, _, tree = _service(sandbox, monkeypatch)
    stale = os.path.join(str(sandbox), "old-pfx", "World of Warcraft", "_retail_")
    os.makedirs(os.path.join(stale, "Interface", "AddOns"))
    prefs = svc.store.load_prefs()
    prefs["wow_installations"].append({"id": "stale", "clientType": 0, "label": "Old", "location": stale + "/Wow.exe"})
    svc.store.save_prefs(prefs)
    st = svc.state(refresh=True)
    by_id = {i["id"]: i for i in st["installations"]}
    assert by_id["stale"]["hasGame"] is False and by_id[RETAIL_ID]["hasGame"] is True
    assert any("no WoW installation" in w and "Old" in w for w in st["warnings"])


def _with_stale(svc, sandbox, move_addons=False):
    """A WowUp entry left pointing at an old prefix that holds only Interface/AddOns."""
    stale = os.path.join(str(sandbox), "old-pfx", "World of Warcraft", "_retail_")
    make_addon(os.path.join(stale, "Interface", "AddOns"), "Ghosty", "120100")
    prefs = svc.store.load_prefs()
    prefs["wow_installations"].append({"id": "stale", "clientType": 0, "label": "Old", "location": stale + "/Wow.exe"})
    svc.store.save_prefs(prefs)
    addons = svc.store.load_addons()
    ghost = record("g1", "Ghosty", installation_id="stale", external_id="900", installed="1", latest="1", auto=True)
    ghost.update({"_fakeLatestId": "2", "_fakeLatestVersion": "2.0"})
    gone = record("g2", "Gone", installation_id="stale", external_id="901")
    addons.update({"g1": ghost, "g2": gone})
    if move_addons:
        for rid in ("r1", "r2"):
            addons[rid]["installationId"] = "stale"
    svc.store.save_addons(addons)
    return stale


def test_runs_never_write_into_installations_without_game(sandbox, monkeypatch):
    svc, _, _ = _service(sandbox, monkeypatch)
    stale = _with_stale(svc, sandbox)
    res = svc.run_update("auto")
    assert res["ok"] and res["blocked"] == ["stale"] and [u["name"] for u in res["updated"]] == ["Fresh"]
    rec = svc.store.load_addons()
    assert rec["g1"]["installedVersion"] == "1.0" and rec["g1"]["autoUpdateEnabled"] is True  # flag restored
    assert len(res["snapshots"]) == 1  # none for the stale folder
    with pytest.raises(RuntimeError, match="no WoW installation"):
        svc.run_update("all", "stale")
    with pytest.raises(RuntimeError, match="no WoW installation"):
        svc.install_addons("stale", [{"provider": "Curse", "externalId": "5"}])
    st = svc.state()
    inst = next(i for i in st["installations"] if i["id"] == "stale")
    assert [t["possible"] for t in inst["relocateTo"]] == [False]  # the retail entry has addons
    with pytest.raises(RuntimeError, match="already has addons"):
        svc.relocate_installation("stale", inst["relocateTo"][0]["flavorDir"])
    assert os.path.isdir(stale)


def test_relocate_moves_entry_copies_folders_and_drops_empty_duplicate(sandbox, monkeypatch):
    svc, addons_dir, tree = _service(sandbox, monkeypatch)
    stale = _with_stale(svc, sandbox, move_addons=True)
    target = svc.state(refresh=True)["installations"][1]["relocateTo"][0]
    assert target["possible"] and target["replaces"] == "World of Warcraft"
    res = svc.relocate_installation("stale", target["flavorDir"])
    assert res["removedEntries"] == [RETAIL_ID] and res["copied"] == ["Ghosty"]
    assert sorted(res["kept"]) == ["Fresh", "Legacy"] and res["reinstall"] == ["Gone"]
    assert os.path.isfile(os.path.join(addons_dir, "Ghosty", "Ghosty.toc"))
    assert os.path.isdir(os.path.join(stale, "Interface", "AddOns", "Ghosty"))  # old folder untouched
    entries = svc.store.load_prefs()["wow_installations"]
    assert [w["id"] for w in entries] == ["stale"] and entries[0]["selected"] is True
    assert "/.steam/steam/" in entries[0]["location"] and entries[0]["location"].endswith("_retail_/Wow.exe")
    rec = svc.store.load_addons()
    assert rec["g2"]["installedVersion"] == "0" and rec["g1"]["installedVersion"] == "1.0"
    inst = svc.state()["installations"][0]
    assert inst["hasGame"] and inst["addonCount"] == 4
    res = svc.run_update("all", "stale")
    assert res["ok"] and res["blocked"] == []


def _with_dependencies(svc, addons_dir):
    """Main requires Lib (and Shared); Other uses Shared too; Main and Lib share the folder LibCommon."""
    for name in ("Main", "Lib", "LibCommon", "Shared"):
        make_addon(addons_dir, name)
    addons = svc.store.load_addons()
    main = record("m", "Main", external_id="500", folders=["Main", "LibCommon"])
    main["dependencies"] = [{"externalAddonId": "501", "type": 2}, {"externalAddonId": "502", "type": 2}]
    lib = record("l", "Lib", external_id="501", folders=["Lib", "LibCommon"])
    shared = record("s", "Shared", external_id="502")
    other = record("o", "Other", external_id="503", folders=["Fresh"])
    other["dependencies"] = [{"externalAddonId": "502", "type": 3}]
    addons.update({"m": main, "l": lib, "s": shared, "o": other})
    del addons["r1"]  # "Fresh" belongs to Other here
    svc.store.save_addons(addons)


def test_addon_list_shows_dependencies(sandbox, monkeypatch):
    svc, addons_dir, _ = _service(sandbox, monkeypatch)
    _with_dependencies(svc, addons_dir)
    by_name = {a["name"]: a for a in svc.state()["addons"][RETAIL_ID]}
    assert [d["name"] for d in by_name["Main"]["removableDeps"]] == ["Lib"]  # Shared is still used by Other
    assert by_name["Lib"]["requiredBy"] == ["Main"] and by_name["Shared"]["requiredBy"] == ["Main"]


def test_remove_with_dependencies_and_undo(sandbox, monkeypatch):
    svc, addons_dir, _ = _service(sandbox, monkeypatch)
    _with_dependencies(svc, addons_dir)
    main_key = addon_key(svc.store.load_addons()["m"])
    res = svc.remove_addons(RETAIL_ID, [main_key], ["Loose"], with_dependencies=True)
    assert res["removed"] == ["Main", "Lib", "Loose"] and res["failed"] == []
    assert res["folders"] == ["Lib", "LibCommon", "Loose", "Main"] and res["shared"] == []
    left = sorted(os.listdir(addons_dir))
    assert left == ["Fresh", "Legacy", "Shared"]
    assert sorted(a["name"] for a in svc.store.load_addons().values()) == ["Legacy", "Other", "Shared"]
    snap = svc.state()["snapshots"][0]
    assert snap["kind"] == "remove" and snap["names"] == ["Main", "Lib", "Loose"]
    # Lib was installed again in the meantime: it keeps its new version
    addons = svc.store.load_addons()
    addons["new"] = record("new", "Lib", external_id="501", version="2.0", folders=["Lib"])
    svc.store.save_addons(addons)
    make_addon(addons_dir, "Lib", body="new\n")
    out = svc.restore_snapshot(snap["id"])
    assert sorted(out["restored"]) == ["Loose", "Main"] and out["recordsRestored"] == 1
    assert sorted(os.listdir(addons_dir)) == ["Fresh", "Legacy", "Lib", "Loose", "Main", "Shared"]
    assert open(os.path.join(addons_dir, "Lib", "Lib.lua")).read() == "new\n"
    names = sorted((a["name"], a["installedVersion"]) for a in svc.store.load_addons().values())
    assert names == [("Legacy", "1.0"), ("Lib", "2.0"), ("Main", "1.0"), ("Other", "1.0"), ("Shared", "1.0")]


def test_remove_keeps_folders_other_addons_use(sandbox, monkeypatch):
    svc, addons_dir, _ = _service(sandbox, monkeypatch)
    _with_dependencies(svc, addons_dir)
    res = svc.remove_addons(RETAIL_ID, [addon_key(svc.store.load_addons()["m"])])
    assert res["removed"] == ["Main"] and res["folders"] == ["Main"] and res["shared"] == ["LibCommon"]
    assert os.path.isdir(os.path.join(addons_dir, "LibCommon")) and os.path.isdir(os.path.join(addons_dir, "Lib"))
    with pytest.raises(RuntimeError, match="not installed"):
        svc.remove_addons(RETAIL_ID, ["Curse|nope"])
    with pytest.raises(RuntimeError, match="not an unmanaged folder"):
        svc.remove_addons(RETAIL_ID, None, ["Fresh"])
    with pytest.raises(RuntimeError, match="not an unmanaged folder"):
        svc.remove_addons(RETAIL_ID, None, ["../x"])
