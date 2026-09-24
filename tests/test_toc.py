from helpers import make_addon, write

from wowaddons import toc


def test_pick_toc_prefers_flavor_suffix(tmp_path):
    folder = make_addon(str(tmp_path), "Foo", "110207", extra_tocs={"Mainline": "120100", "Mists": "50504"})
    assert toc.pick_toc(folder, "mainline").endswith("Foo_Mainline.toc")
    assert toc.pick_toc(folder, "mists").endswith("Foo_Mists.toc")
    assert toc.pick_toc(folder, "vanilla").endswith("Foo.toc")


def test_parse_strips_codes_and_reads_ids(tmp_path):
    folder = make_addon(str(tmp_path), "Bar", "120100, 50504, 11509")
    info = toc.parse_toc(toc.pick_toc(folder, "mainline"), "mainline")
    assert info["title"] == "Bar" and info["version"] == "1.0"
    assert info["interfaces"] == [120100, 50504, 11509] and info["ids"]["curse"] == "42"


def test_conditions_on_metadata(tmp_path):
    p = write(str(tmp_path / "Baz" / "Baz.toc"),
              "## Interface [AllowLoadGameType mainline]: 120100\n## Interface: 50504\n## Title: Baz\n")
    assert toc.parse_toc(p, "mainline")["interfaces"] == [120100]
    assert toc.parse_toc(p, "mists")["interfaces"] == [50504]


def test_interface_status():
    assert toc.interface_status([120100], "mainline", 120100) == ("ok", 120100)
    assert toc.interface_status([120001], "mainline", 120100) == ("outdated", 120001)
    assert toc.interface_status([110207], "mainline", 120100) == ("incompatible", 110207)
    assert toc.interface_status([120100, 50504], "mists", 50504) == ("ok", 50504)
    assert toc.interface_status([120100], "mists", 50504) == ("incompatible", 120100)
    assert toc.interface_status([120100], "forever", 16001) == ("unknown", 120100)
    assert toc.interface_status([], "mainline", 120100) == ("unknown", None)
