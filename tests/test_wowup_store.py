import json
import os
import stat

from helpers import RETAIL_ID, record, write_wowup

from wowaddons.wowup_store import WowUpStore, addon_key, installation_label, needs_update, release_channel


def test_write_keeps_electron_store_format_and_mode(tmp_path):
    cfg = str(tmp_path / "WowUpCf")
    write_wowup(cfg, {"a": "1"}, {"x": record("x", "Ümlaut")}, mode=0o666)
    store = WowUpStore(cfg)
    addons = store.load_addons()
    addons["x"]["autoUpdateEnabled"] = False
    store.save_addons(addons)
    raw = open(store.addons_path, encoding="utf-8").read()
    assert raw == json.dumps(addons, indent="\t", ensure_ascii=False) and not raw.endswith("\n")
    assert "Ümlaut" in raw
    assert stat.S_IMODE(os.stat(store.addons_path).st_mode) == 0o666


def test_needs_update_rules():
    assert needs_update(record("a", "A", installed="1", latest="2"))
    assert needs_update(record("a", "A", version="v1.0", latest_version="1.1"))
    assert not needs_update(record("a", "A", version="v1.0", latest_version="1.0"))
    ignored = record("a", "A", installed="1", latest="2")
    ignored["isIgnored"] = True
    assert not needs_update(ignored)


def test_installations_and_labels(tmp_path):
    flavor = tmp_path / "wow" / "_retail_"
    (flavor / "Interface" / "AddOns").mkdir(parents=True)
    cfg = str(tmp_path / "WowUpCf")
    write_wowup(cfg, {"wow_installations": [{"id": RETAIL_ID, "clientType": 0, "label": "{defaultName} 2",
                                             "location": str(flavor / "Wow.exe"), "selected": True}]}, {})
    inst = WowUpStore(cfg).installations()[0]
    assert inst["label"] == "Retail 2" and inst["addonsDir"] == str(flavor / "Interface" / "AddOns") and inst["exists"]
    assert installation_label("World of Warcraft", 0) == "World of Warcraft"


def test_key_and_channel():
    assert addon_key(record("a", "A", external_id="91376")) == f"{RETAIL_ID}|Curse|91376"
    assert release_channel({"wowup_release_channel_2_6": "0"}) == "beta"
    assert release_channel({"wowup_release_channel_2_6": "1"}) == "stable"
    assert release_channel({}) == "stable"


def test_read_log_since_handles_rotation(tmp_path):
    cfg = tmp_path / "WowUpCf"
    (cfg / "logs").mkdir(parents=True)
    (cfg / "logs" / "main.log").write_text("old line\n")
    store = WowUpStore(str(cfg))
    offset = store.log_size()
    with open(cfg / "logs" / "main.log", "a") as f:
        f.write("new line\n")
    assert store.read_log_since(offset) == "new line\n"
    (cfg / "logs" / "main.old.log").write_text("old line\nrotated tail\n")
    (cfg / "logs" / "main.log").write_text("x\n")
    assert store.read_log_since(offset) == "rotated tail\nx\n"
