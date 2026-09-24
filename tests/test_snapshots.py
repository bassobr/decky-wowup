import os

from helpers import make_addon

from wowaddons import snapshots


def test_snapshot_uses_hardlinks_and_restores(sandbox, tmp_path):
    addons = tmp_path / "AddOns"
    make_addon(str(addons), "Alpha", body="v1\n")
    make_addon(str(addons), "Beta", body="b1\n")
    meta = snapshots.create(str(addons), "inst", "before run")
    src = addons / "Alpha" / "Alpha.lua"
    snap = sandbox / "homebrew" / "data" / "WoW Addons" / "snapshots" / meta["id"] / "AddOns" / "Alpha" / "Alpha.lua"
    assert os.stat(src).st_ino == os.stat(snap).st_ino and meta["method"] == "hardlink"

    # an update replaces files (new inode) and adds a folder
    os.unlink(src)
    src.write_text("v2\n")
    make_addon(str(addons), "Gamma")
    assert snap.read_text() == "v1\n"

    res = snapshots.restore(meta["id"], ["Alpha"])
    assert (addons / "Alpha" / "Alpha.lua").read_text() == "v1\n" and (addons / "Gamma").exists()
    assert res["safetySnapshot"]

    res = snapshots.restore(meta["id"])
    assert res["removed"] == ["Gamma"] and not (addons / "Gamma").exists()
    assert sorted(os.listdir(addons)) == ["Alpha", "Beta"]


def test_prune_keeps_newest(sandbox, tmp_path):
    addons = tmp_path / "AddOns"
    make_addon(str(addons), "Alpha")
    ids = [snapshots.create(str(addons), "inst", f"s{i}", keep=3)["id"] for i in range(5)]
    left = [m["id"] for m in snapshots.list_snapshots("inst")]
    assert left == sorted(ids, reverse=True)[:3]


def test_restore_rejects_unknown(sandbox):
    try:
        snapshots.restore("../../etc")
        raise AssertionError("must fail")
    except RuntimeError:
        pass
