import json
import os

from helpers import make_steam, product, product_db, write

from wowaddons import finders, wow


def _prefix(base, products=None, default_wow_flavors=()):
    """Wine prefix; either with Battle.net's product.db or with a WoW folder in the default place."""
    os.makedirs(os.path.join(base, "drive_c"), exist_ok=True)
    os.makedirs(os.path.join(base, "dosdevices"), exist_ok=True)
    if not os.path.lexists(os.path.join(base, "dosdevices", "c:")):
        os.symlink("../drive_c", os.path.join(base, "dosdevices", "c:"))
    root = os.path.join(base, "drive_c", "Program Files (x86)", "World of Warcraft")
    rows = ["Branch!STRING:0|Version!STRING:0|Product!STRING:0"]
    for code, sub, version in (products or []) + list(default_wow_flavors):
        os.makedirs(os.path.join(root, sub, "Interface", "AddOns"), exist_ok=True)
        rows.append(f"eu|{version}|{code}")
    if products or default_wow_flavors:
        write(os.path.join(root, ".build.info"), "\n".join(rows) + "\n")
    if products:
        write(os.path.join(base, "drive_c", "ProgramData", "Battle.net", "Agent", "product.db"),
              product_db([product(c, c, "C:/Program Files (x86)/World of Warcraft", sub, v) for c, sub, v in products]))
    return root


def test_every_source_is_found_with_its_label(sandbox, monkeypatch):
    home = str(sandbox)
    make_steam(home)  # Steam: Battle.net with Retail
    b = os.path.join(home, ".var", "app", "com.usebottles.bottles", "data", "bottles", "bottles", "Gaming")
    _prefix(b, [("wow_classic_era", "_classic_era_", "1.15.9.1")])
    write(os.path.join(b, "bottle.yml"), "Arch: win64\nName: My Gaming\n")
    lutris_pfx = os.path.join(home, "Games", "battlenet")
    _prefix(lutris_pfx, default_wow_flavors=[("wow_classic", "_classic_", "5.5.4.1")])  # no product.db
    write(os.path.join(home, ".config", "lutris", "games", "battlenet-1700000000.yml"),
          f"name: Battle.net\ngame:\n  exe: x.exe\n  prefix: {lutris_pfx}\n")
    heroic_pfx = os.path.join(home, "Games", "Heroic", "Prefixes", "default", "Battle.net")
    _prefix(heroic_pfx, [("wow_anniversary", "_anniversary_", "2.5.6.1")])
    write(os.path.join(home, ".config", "heroic", "GamesConfig", "abc123.json"),
          json.dumps({"abc123": {"winePrefix": heroic_pfx}}))
    write(os.path.join(home, ".config", "heroic", "sideload_apps", "library.json"),
          json.dumps({"games": [{"app_name": "abc123", "title": "Battle.net (Heroic)"}]}))
    _prefix(os.path.join(home, ".wine"), [("wowt", "_ptr_", "12.1.5.1")])
    _prefix(os.path.join(home, ".cxoffice", "Warcraft"), [("wow_beta", "_beta_", "12.0.1.1")])

    found = {d["product"]: d for d in wow.discover(finders.candidates({}))}
    assert found["wow"]["source"] == "Steam: Battle.net" and found["wow"]["sourceType"] == "steam"
    assert found["wow_classic_era"]["source"] == "Bottles: My Gaming"
    assert found["wow_classic"]["source"] == "Lutris: Battle.net" and found["wow_classic"]["gameType"] == "mists"
    assert found["wow_anniversary"]["source"] == "Heroic: Battle.net (Heroic)" and found["wow_anniversary"]["clientType"] == 9
    assert found["wowt"]["source"] == "Wine: .wine" and found["wowt"]["clientType"] == 2
    assert found["wow_beta"]["source"] == "CrossOver: Warcraft"
    counts = finders.summary(finders.candidates({}))
    assert counts["steam"] == 1 and counts["bottles"] == 1 and counts["heroic"] == 1 and counts["wine"] == 1
    assert counts["lutris"] == 1  # yml and default folder point at the same prefix


def test_search_folders_removable_and_dedupe(sandbox, monkeypatch, tmp_path):
    drive = tmp_path / "sdcard"
    copy = drive / "Games" / "World of Warcraft"
    write(str(copy / ".build.info"), "Branch!STRING:0|Version!STRING:0|Product!STRING:0\neu|1.15.9.2|wow_classic_era\n")
    os.makedirs(copy / "_classic_era_" / "Interface" / "AddOns")
    write(str(copy / "_classic_era_" / ".flavor.info"), "Product Flavor!STRING:0\nwow_classic_era\n")
    os.makedirs(drive / "steamapps" / "common" / "Deep" / "World of Warcraft")  # skipped folder
    monkeypatch.setattr(finders, "removable_roots", lambda: [str(drive)])
    found = wow.discover(finders.candidates({"discovery": {"searchPaths": [str(drive / "Games")], "scanRemovable": True}}))
    assert len(found) == 1 and found[0]["source"].startswith("Search folder") and found[0]["version"] == "1.15.9.2"
    found = wow.discover(finders.candidates({"discovery": {"scanRemovable": True}}))
    assert [f["source"] for f in found] == ["Drive: sdcard"]
    assert wow.discover(finders.candidates({"discovery": {"scanRemovable": False}})) == []


def test_manual_candidates(sandbox, tmp_path):
    pfx = str(tmp_path / "pfx")
    root = _prefix(pfx, [("wow", "_retail_", "12.1.0.1")])
    assert finders.manual_candidates(pfx)[0]["kind"] == "prefix"
    assert finders.manual_candidates(root)[0] == {"kind": "root", "path": os.path.realpath(root),
                                                  "source": "Added manually", "sourceType": "manual"}
    assert finders.manual_candidates(os.path.join(root, "_retail_"))[0]["path"] == os.path.realpath(root)
    assert finders.manual_candidates(str(tmp_path))[0]["kind"] == "prefix"  # found by a shallow scan
    empty = tmp_path / "empty"
    empty.mkdir()
    try:
        finders.manual_candidates(str(empty))
        raise AssertionError("must fail")
    except RuntimeError as e:
        assert "no World of Warcraft" in str(e)


def test_nonsteamlaunchers_prefix(sandbox):
    tree = make_steam(str(sandbox))
    nsl = os.path.join(tree["steam"], "steamapps", "compatdata", "NonSteamLaunchers", "pfx")
    _prefix(nsl, [("wow_classic_era", "_classic_era_", "1.15.9.1")])
    found = {d["product"]: d["source"] for d in wow.discover(finders.candidates({}))}
    assert found["wow_classic_era"] == "Steam: NonSteamLaunchers"
