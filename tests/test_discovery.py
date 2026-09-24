import os

from helpers import BNET_APPID, make_steam, product, product_db, shortcuts_vdf, signed32

from wowaddons import battlenet, steam, wow


def test_binary_vdf_and_unsigned_appid():
    data = shortcuts_vdf([{"appid": signed32(BNET_APPID), "AppName": "Battle.net", "Exe": '"/x/Battle.net.exe"'}])
    parsed, _ = steam.parse_binary_vdf(data)
    entry = parsed["shortcuts"]["0"]
    assert entry["AppName"] == "Battle.net" and entry["appid"] & 0xFFFFFFFF == BNET_APPID


def test_product_db_decoding_matches_on_code():
    data = product_db([product("wow_classic_anniversary", "wow_anniversary", "C:/Games/WoW", "_anniversary_", "2.5.6.1")])
    prods = battlenet.decode_product_db(data)
    wowp = [p for p in prods if p["family"] == "wow"]
    assert prods[0]["code"] == "agent"
    assert wowp == [{"uid": "wow_classic_anniversary", "code": "wow_anniversary", "family": "wow",
                     "installPath": "C:/Games/WoW", "subfolder": "_anniversary_", "version": "2.5.6.1",
                     "installed": True, "playable": True, "updateComplete": True}]


def test_game_type_from_build_version():
    assert wow.game_type("12.1.0.69933") == ("mainline", 120100)
    assert wow.game_type("5.5.4.69934") == ("mists", 50504)
    assert wow.game_type("1.15.9.69722") == ("vanilla", 11509)
    assert wow.game_type("1.60.1.69977") == ("forever", 16001)
    assert wow.game_type("2.5.6") == ("tbc", 20506)
    assert wow.game_type("3.80.2") == ("titan", 38002)
    assert wow.game_type("") == (None, None)


def test_win_path_via_dosdevices(tmp_path):
    pfx = tmp_path / "pfx"
    (pfx / "drive_c").mkdir(parents=True)
    (tmp_path / "sd").mkdir()
    (pfx / "dosdevices").mkdir()
    os.symlink("../drive_c", pfx / "dosdevices" / "c:")
    os.symlink(str(tmp_path / "sd"), pfx / "dosdevices" / "d:")
    assert wow.win_to_linux(str(pfx), "C:/Program Files (x86)/World of Warcraft") == \
        os.path.join(os.path.realpath(pfx / "drive_c"), "Program Files (x86)", "World of Warcraft")
    assert wow.win_to_linux(str(pfx), "D:\\Games\\WoW") == os.path.join(os.path.realpath(tmp_path / "sd"), "Games", "WoW")
    assert wow.win_to_linux(str(pfx), "not a path") is None


def test_discover_end_to_end(sandbox):
    tree = make_steam(str(sandbox), flavors=(("wow", "_retail_", "12.1.0.69933", "eu", "Wow.exe"),
                                             ("wow_classic_beta", "_classic_beta_", "1.60.1.69977", "us", "WowB.exe")))
    prefixes = steam.battlenet_prefixes()
    assert len(prefixes) == 1 and prefixes[0]["appId"] == BNET_APPID and prefixes[0]["shortcut"] == "Battle.net"
    found = {d["product"]: d for d in wow.discover()}
    assert set(found) == {"wow", "wow_classic_beta"}
    retail, beta = found["wow"], found["wow_classic_beta"]
    assert retail["gameType"] == "mainline" and retail["interface"] == 120100 and retail["clientType"] == 0
    assert retail["region"] == "eu" and retail["addonsDirExists"] and retail["exe"].endswith("Wow.exe")
    assert beta["gameType"] == "forever" and beta["clientType"] == 5 and beta["exe"].endswith("WowB.exe")
    assert retail["flavorDir"].startswith(os.path.realpath(tree["root"]))


def test_case_insensitive_child(tmp_path):
    # On case-sensitive filesystems (btrfs on Bazzite, CI) the real spelling is found by scanning;
    # on casefolded ones (SteamOS prefixes, macOS) the requested spelling already resolves.
    (tmp_path / "interface" / "addons").mkdir(parents=True)
    found = wow.find_addons_dir(str(tmp_path))
    assert os.path.isdir(found) and found.lower() == str(tmp_path / "interface" / "addons").lower()
    assert wow.ci_child(str(tmp_path), "missing") is None
