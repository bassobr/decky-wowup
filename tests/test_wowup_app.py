import base64
import hashlib
import os

from helpers import write

from wowaddons import paths, util, wowup_app

LATEST_YML = """version: 2.23.1
files:
  - url: WowUp-CF-2.23.1.AppImage
    sha512: 0IzgL02tfgZwudK/efaAVU0N+hXF+DeXz3Iyz7G8xUGUMFl7rDydue5rLs6Z4dwAXjU9G3UDe8/xa6enzAR+Qg==
    size: 127052442
    blockMapSize: 133806
path: WowUp-CF-2.23.1.AppImage
sha512: 0IzgL02tfgZwudK/efaAVU0N+hXF+DeXz3Iyz7G8xUGUMFl7rDydue5rLs6Z4dwAXjU9G3UDe8/xa6enzAR+Qg==
releaseDate: '2026-08-31T23:55:35.863Z'
"""


def _release(version, prerelease=False, digest=None, name=None):
    name = name or f"WowUp-CF-{version}.AppImage"
    return wowup_app._normalize({"tag_name": f"v{version}", "prerelease": prerelease, "draft": False,
                                 "assets": [{"name": name, "browser_download_url": f"https://x/{name}", "size": 3,
                                             "digest": digest}]})


def test_versions_and_names():
    assert wowup_app.version_key("2.24.0-beta.5") < wowup_app.version_key("2.24.0") < wowup_app.version_key("2.24.1")
    assert wowup_app.version_key("2.24.0-beta.10") > wowup_app.version_key("2.24.0-beta.5")
    assert wowup_app.is_newer("2.24.0", "2.23.1") and not wowup_app.is_newer("2.23.1", "2.23.1")
    assert wowup_app.version_from_name("/home/deck/WowUp-CF-2.23.1.AppImage") == "2.23.1"
    assert wowup_app.version_from_name("WowUp-2.23.1.AppImage") is None


def test_parse_latest_yml():
    info = wowup_app.parse_latest_yml(LATEST_YML, "WowUp-CF-2.23.1.AppImage")
    assert info["size"] == 127052442 and info["sha512"].startswith("0IzgL02t")


def test_pick_release_by_channel():
    rels = [_release("2.24.0-beta.5", prerelease=True), _release("2.23.1"), _release("2.22.0")]
    assert wowup_app.pick_release(rels, "stable")["version"] == "2.23.1"
    assert wowup_app.pick_release(rels, "beta")["version"] == "2.24.0-beta.5"


def test_verify_requires_matching_digests(tmp_path):
    f = write(str(tmp_path / "WowUp-CF-1.0.0.AppImage"), b"abc")
    exp = {"size": 3, "sha256": hashlib.sha256(b"abc").hexdigest(),
           "sha512": base64.b64encode(hashlib.sha512(b"abc").digest()).decode()}
    assert wowup_app.verify(f, exp)["ok"]
    assert not wowup_app.verify(f, dict(exp, sha512=base64.b64encode(b"x" * 64).decode()))["ok"]
    assert not wowup_app.verify(f, {"size": 3, "sha256": None, "sha512": None})["ok"]


def test_install_link_candidates_and_prune(sandbox, monkeypatch):
    def fake_download(url, dest, timeout, expected_size=None, on_progress=None):
        write(dest, b"abc")

    monkeypatch.setattr(util, "curl_download", fake_download)
    digest = "sha256:" + hashlib.sha256(b"abc").hexdigest()
    for v in ("2.22.0", "2.23.0", "2.23.1"):
        res = wowup_app.install(_release(v, digest=digest))
        assert res["verified"] and os.access(res["path"], os.X_OK)
        wowup_app.set_link(res["path"])
    assert os.path.realpath(paths.WOWUP_LINK).endswith("WowUp-CF-2.23.1.AppImage")
    assert os.readlink(paths.WOWUP_LINK) == "WowUp-CF-2.23.1.AppImage"  # relative link inside the managed dir
    removed = wowup_app.prune(keep=2)
    assert [os.path.basename(r) for r in removed] == ["WowUp-CF-2.22.0.AppImage"]
    write(str(sandbox / "WowUp-CF-2.20.0.AppImage"), b"old", 0o755)
    versions = [c["version"] for c in wowup_app.find_candidates()]
    assert versions == ["2.23.1", "2.23.0", "2.20.0"]


def test_install_rejects_bad_checksum(sandbox, monkeypatch):
    monkeypatch.setattr(util, "curl_download", lambda url, dest, *a, **k: write(dest, b"evil"))
    try:
        wowup_app.install(_release("9.9.9", digest="sha256:" + "0" * 64))
        raise AssertionError("install should fail")
    except RuntimeError as e:
        assert "checksum mismatch" in str(e)
    assert not [f for f in os.listdir(paths.WOWUP_APPS_DIR) if "9.9.9" in f]
