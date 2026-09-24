"""WowUp-CF AppImage: find, verify against the release metadata, install, update (with canary run).

Integrity: every WowUp.CF release ships latest-linux.yml (electron-builder: sha512 in base64 and
size of the AppImage), and the GitHub API reports a sha256 digest per asset. Both must match.
Managed layout: ~/Applications/WowUp-CF/WowUp-CF-<version>.AppImage plus the stable link
WowUp-CF.AppImage that points at the version in use.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import paths, util, wowup_runner
from .constants import DOWNLOAD_TIMEOUT_S, WOWUP_APPIMAGE_RE, WOWUP_CONFIG_NAME, WOWUP_LINK_NAME, WOWUP_REPO
from .log import logger
from .wowup_store import WowUpStore

API = f"https://api.github.com/repos/{WOWUP_REPO}"
_NAME_RE = re.compile(WOWUP_APPIMAGE_RE)
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.]+))?$")


# ---------------------------------------------------------------- versions
def version_key(v: Optional[str]) -> Tuple:
    """Sort key; a pre-release sorts before its release (2.24.0-beta.5 < 2.24.0)."""
    m = _VERSION_RE.match(str(v or "").strip().lstrip("vV"))
    if not m:
        return (-1,)
    pre = m.group(4)
    pre_key: Tuple = (1,) if pre is None else (0,) + tuple(int(p) if p.isdigit() else p for p in pre.split("."))
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) + (pre_key,)


def is_newer(latest: Optional[str], current: Optional[str]) -> bool:
    try:
        return version_key(latest) > version_key(current)
    except TypeError:  # mixed int/str pre-release parts
        return str(latest) != str(current)


def version_from_name(path: str) -> Optional[str]:
    m = _NAME_RE.match(os.path.basename(path or ""))
    return m.group(1) if m else None


def describe(path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path or not os.path.isfile(path):
        return None
    real = os.path.realpath(path)
    return {"path": path, "realpath": real, "version": version_from_name(real) or version_from_name(path),
            "size": os.path.getsize(real), "executable": os.access(real, os.X_OK),
            "managed": os.path.dirname(real) == os.path.realpath(paths.WOWUP_APPS_DIR)}


def find_candidates(dirs: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    dirs = paths.WOWUP_SEARCH_DIRS if dirs is None else dirs
    out: List[Dict[str, Any]] = []
    seen = set()
    for d in dirs:
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for n in names:
            if not (_NAME_RE.match(n) or n == WOWUP_LINK_NAME):
                continue
            info = describe(os.path.join(d, n))
            if not info or not info["version"] or info["realpath"] in seen:
                continue
            seen.add(info["realpath"])
            out.append(info)
    out.sort(key=lambda x: version_key(x["version"]), reverse=True)
    return out


# ---------------------------------------------------------------- releases
def _normalize(rel: Dict[str, Any]) -> Dict[str, Any]:
    tag = str(rel.get("tag_name") or "")
    assets = {a.get("name"): {"url": a.get("browser_download_url"), "size": a.get("size"), "digest": a.get("digest")}
              for a in rel.get("assets") or [] if a.get("name")}
    return {"tag": tag, "version": tag.lstrip("vV"), "prerelease": bool(rel.get("prerelease")),
            "draft": bool(rel.get("draft")), "publishedAt": rel.get("published_at"), "htmlUrl": rel.get("html_url"),
            "assets": assets}


def fetch_releases(limit: int = 15) -> List[Dict[str, Any]]:
    data = util.curl_json(f"{API}/releases?per_page={int(limit)}")
    return [_normalize(r) for r in data if isinstance(r, dict)]


def release_by_version(version: str) -> Dict[str, Any]:
    return _normalize(util.curl_json(f"{API}/releases/tags/v{version}"))


def pick_release(releases: List[Dict[str, Any]], channel: str) -> Optional[Dict[str, Any]]:
    usable = [r for r in releases if not r["draft"] and appimage_asset(r) and (channel == "beta" or not r["prerelease"])]
    return max(usable, key=lambda r: version_key(r["version"]), default=None)


def appimage_asset(release: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
    for name, a in (release.get("assets") or {}).items():
        if _NAME_RE.match(name or "") and a.get("url"):
            return name, a
    return None


def parse_latest_yml(text: str, file_name: str) -> Dict[str, Any]:
    """sha512/size for `file_name` from electron-builder's latest-linux.yml (no YAML library needed)."""
    sha512 = size = None
    block = re.search(r"-\s+url:\s*" + re.escape(file_name) + r"\s*\n((?:\s{2,}\S.*\n?)*)", text)
    if block:
        m = re.search(r"sha512:\s*(\S+)", block.group(1))
        sha512 = m.group(1) if m else None
        m = re.search(r"size:\s*(\d+)", block.group(1))
        size = int(m.group(1)) if m else None
    if sha512 is None and re.search(r"^path:\s*" + re.escape(file_name) + r"\s*$", text, re.M):
        m = re.search(r"^sha512:\s*(\S+)", text, re.M)
        sha512 = m.group(1) if m else None
    return {"sha512": sha512, "size": size}


def expected_hashes(release: Dict[str, Any]) -> Dict[str, Any]:
    found = appimage_asset(release)
    if not found:
        raise RuntimeError(f"release {release.get('tag')} has no AppImage")
    name, asset = found
    exp: Dict[str, Any] = {"name": name, "url": asset["url"], "size": asset.get("size"), "sha256": None, "sha512": None}
    digest = str(asset.get("digest") or "")
    if digest.startswith("sha256:"):
        exp["sha256"] = digest.split(":", 1)[1].lower()
    yml = (release.get("assets") or {}).get("latest-linux.yml")
    if yml and yml.get("url"):
        info = parse_latest_yml(util.curl_text(yml["url"], timeout=20), name)
        exp["sha512"] = info["sha512"]
        exp["size"] = info["size"] or exp["size"]
    if not exp["sha256"] and not exp["sha512"]:
        raise RuntimeError(f"release {release.get('tag')} publishes no checksum for {name}")
    return exp


def verify(path: str, exp: Dict[str, Any]) -> Dict[str, Any]:
    real = os.path.realpath(path)
    digests = util.hash_file(real, ("sha256", "sha512"))
    res = {"size": None, "sha256": None, "sha512": None}
    if exp.get("size") is not None:
        res["size"] = os.path.getsize(real) == int(exp["size"])
    if exp.get("sha256"):
        res["sha256"] = digests["sha256"].hex() == exp["sha256"]
    if exp.get("sha512"):
        res["sha512"] = base64.b64encode(digests["sha512"]).decode() == exp["sha512"]
    checked = [v for v in res.values() if v is not None]
    res["ok"] = bool(checked) and all(checked) and (res["sha256"] or res["sha512"]) is True
    return res


# ---------------------------------------------------------------- install
def set_link(target: str) -> str:
    os.makedirs(paths.WOWUP_APPS_DIR, exist_ok=True)
    rel = os.path.basename(target) if os.path.dirname(os.path.realpath(target)) == os.path.realpath(paths.WOWUP_APPS_DIR) \
        else os.path.realpath(target)
    tmp = os.path.join(paths.WOWUP_APPS_DIR, f".link-{os.getpid()}-{os.urandom(3).hex()}")
    os.symlink(rel, tmp)
    os.replace(tmp, paths.WOWUP_LINK)
    return paths.WOWUP_LINK


def install(release: Dict[str, Any], on_progress: Optional[Callable[[str, Optional[float]], None]] = None) -> Dict[str, Any]:
    exp = expected_hashes(release)
    os.makedirs(paths.WOWUP_APPS_DIR, exist_ok=True)
    final = os.path.join(paths.WOWUP_APPS_DIR, exp["name"])
    if os.path.isfile(final) and verify(final, exp)["ok"]:
        logger.info("WowUp-CF %s already present and verified", release["version"])
    else:
        part = os.path.join(paths.WOWUP_APPS_DIR, f".{exp['name']}.part")

        def dl(done: int, total: Optional[int]) -> None:
            if on_progress:
                pct = (100.0 * done / total) if total else None
                on_progress(f"Downloading WowUp-CF {release['version']} ({util.human_bytes(done)})", pct)

        util.curl_download(exp["url"], part, DOWNLOAD_TIMEOUT_S, exp.get("size"), dl)
        if on_progress:
            on_progress("Verifying checksums…", None)
        res = verify(part, exp)
        if not res["ok"]:
            os.unlink(part)
            raise RuntimeError(f"checksum mismatch for {exp['name']}: {res}")
        os.chmod(part, 0o755)
        os.replace(part, final)
    return {"path": final, "version": release["version"], "verified": True}


def prune(keep: int = 2) -> List[str]:
    """Remove old managed versions, never the one the link points to."""
    current = os.path.realpath(paths.WOWUP_LINK) if os.path.lexists(paths.WOWUP_LINK) else None
    managed = find_candidates([paths.WOWUP_APPS_DIR])
    removed = []
    kept = 0
    for c in managed:  # newest first
        if c["realpath"] == current or kept < keep:
            kept += 1
            continue
        try:
            os.unlink(c["realpath"])
            removed.append(c["realpath"])
        except OSError as e:
            logger.warning("cannot remove %s: %s", c["realpath"], e)
    return removed


# ---------------------------------------------------------------- canary
def canary(appimage: str, source: WowUpStore, workdir: Optional[str] = None, timeout: int = 120) -> Dict[str, Any]:
    """Check-only run of `appimage` against a copy of the WowUp profile before switching to it."""
    if not source.exists():
        return {"ok": True, "skipped": "no WowUp profile yet"}
    workdir = workdir or os.path.join(paths.TMP_DIR, "canary")
    shutil.rmtree(workdir, ignore_errors=True)
    cfg = os.path.join(workdir, WOWUP_CONFIG_NAME)
    os.makedirs(cfg)
    try:
        prefs = source.load_prefs()
        addons = source.load_addons()
        for a in addons.values():
            a["autoUpdateEnabled"] = False
        store = WowUpStore(cfg)
        store.save_prefs(prefs)
        store.save_addons(addons)
        res = wowup_runner.run(store, appimage, mode="check", timeout=timeout, config_home=workdir,
                               journal_path=os.path.join(workdir, "journal.json"),
                               runs_dir=os.path.join(workdir, "runs"))
        after = store.load_addons()
        same_records = set(after) == set(addons) or len(after) >= len(addons)
        ok = bool(res["ok"]) and same_records and isinstance(json.loads(json.dumps(after)), dict)
        return {"ok": ok, "rc": res["rc"], "quit": res["quit"], "durationMs": res["durationMs"],
                "errors": res["errors"][:5], "timedOut": res["timedOut"]}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
