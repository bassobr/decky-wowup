from wowaddons import settings, updater


def test_defaults_merge_keeps_unknown_keys():
    s = settings._merge(settings.DEFAULTS, {"wowup": {"channel": "beta"}, "unknown": 1})
    assert s["wowup"]["channel"] == "beta" and s["wowup"]["autoCheck"] is True and s["unknown"] == 1
    assert settings.timeout_s({"runner": {"timeoutSec": 5}}) == 30
    assert settings.timeout_s({"runner": {"timeoutSec": "x"}}) == 120


def test_version_compare_and_sums():
    assert updater.parse_version("v1.2.3") == (1, 2, 3)
    assert updater.parse_version("0.1") == (0, 1, 0)
    assert updater.is_newer("0.2.0", "0.1.9") and not updater.is_newer("0.1.0", "0.1.0")
    sums = updater.parse_sums("abc\n" + "a" * 64 + "  wow-addons-0.1.0.zip\n" + "b" * 64 + " *other.zip\n")
    assert sums == {"wow-addons-0.1.0.zip": "a" * 64, "other.zip": "b" * 64}


def test_update_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "UPDATE_MARKER", str(tmp_path / ".update-pending"))
    monkeypatch.setattr(updater.paths, "RUNTIME_DIR", str(tmp_path))
    assert not updater.update_in_progress()
    updater.mark_update_pending()
    assert updater.update_in_progress()
    assert not updater.update_in_progress(now=updater.UPDATE_MARKER_TTL_S + 10 ** 10)
    updater.clear_update_marker()
    assert not updater.update_in_progress()
