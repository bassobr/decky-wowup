"""Snapshots of AddOns folders before each run, as hardlink trees (cheap: WowUp replaces files
instead of rewriting them in place), falling back to copies across filesystems."""
from __future__ import annotations

import errno
import os
import shutil
import time
from typing import Any, Dict, List, Optional

from . import paths, util, wow
from .constants import SNAPSHOT_KEEP
from .log import logger

_LINK_FALLBACK = {errno.EXDEV, errno.EPERM, errno.EMLINK, errno.ENOTSUP, errno.EOPNOTSUPP}


def _link_tree(src: str, dst: str) -> str:
    method = "hardlink"
    if os.path.islink(src):
        os.symlink(os.readlink(src), dst)
        return method
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        target = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(target, exist_ok=True)
        for d in list(dirs):
            s = os.path.join(root, d)
            if os.path.islink(s):
                os.symlink(os.readlink(s), os.path.join(target, d))
                dirs.remove(d)
        for f in files:
            s, t = os.path.join(root, f), os.path.join(target, f)
            if os.path.islink(s):
                os.symlink(os.readlink(s), t)
                continue
            try:
                os.link(s, t)
            except OSError as e:
                if e.errno not in _LINK_FALLBACK:
                    raise
                shutil.copy2(s, t)
                method = "copy"
    return method


def _valid_name(name: str) -> bool:
    return bool(name) and name not in (".", "..") and "/" not in name and "\x00" not in name


valid_name = _valid_name


def create(addons_dir: str, installation_id: Optional[str], label: str, keep: int = SNAPSHOT_KEEP,
           base: Optional[str] = None, extra: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    base = base or paths.SNAPSHOT_DIR
    if not addons_dir or not os.path.isdir(addons_dir):
        return None
    now = time.time()  # ids sort chronologically (millisecond resolution)
    sid = time.strftime("%Y%m%d-%H%M%S", time.localtime(now)) + f"{int(now * 1000) % 1000:03d}-" + os.urandom(2).hex()
    root = os.path.join(base, sid)
    target = os.path.join(root, "AddOns")
    os.makedirs(target)
    folders = sorted(e for e in os.listdir(addons_dir) if os.path.isdir(os.path.join(addons_dir, e)) and _valid_name(e))
    method = "hardlink"
    for name in folders:
        if _link_tree(os.path.join(addons_dir, name), os.path.join(target, name)) == "copy":
            method = "copy"
    meta = {"id": sid, "installationId": installation_id, "addonsDir": addons_dir, "label": label,
            "createdAt": util.now_iso(), "folders": folders, "method": method}
    if extra:
        meta.update(extra)
    util.write_json(os.path.join(root, "meta.json"), meta)
    if keep > 0:
        prune(installation_id, keep, base)
    return meta


def list_snapshots(installation_id: Optional[str] = None, base: Optional[str] = None) -> List[Dict[str, Any]]:
    base = base or paths.SNAPSHOT_DIR
    out = []
    try:
        ids = os.listdir(base)
    except OSError:
        return out
    for sid in ids:
        meta = util.read_json(os.path.join(base, sid, "meta.json"))
        if isinstance(meta, dict) and (installation_id is None or meta.get("installationId") == installation_id):
            out.append(meta)
    out.sort(key=lambda m: m.get("id", ""), reverse=True)
    return out


def get(sid: str, base: Optional[str] = None) -> Optional[Dict[str, Any]]:
    base = base or paths.SNAPSHOT_DIR
    if not _valid_name(sid):
        return None
    meta = util.read_json(os.path.join(base, sid, "meta.json"))
    return meta if isinstance(meta, dict) else None


def delete(sid: str, base: Optional[str] = None) -> None:
    base = base or paths.SNAPSHOT_DIR
    if _valid_name(sid):
        shutil.rmtree(os.path.join(base, sid), ignore_errors=True)


def prune(installation_id: Optional[str], keep: int = SNAPSHOT_KEEP, base: Optional[str] = None) -> None:
    for meta in list_snapshots(installation_id, base)[max(1, keep):]:
        delete(meta["id"], base)


def restore(sid: str, folders: Optional[List[str]] = None, base: Optional[str] = None) -> Dict[str, Any]:
    """Put folders back from snapshot `sid` (all when `folders` is None; then folders that did not
    exist at snapshot time are removed). A safety snapshot of the current state is taken first."""
    base = base or paths.SNAPSHOT_DIR
    meta = get(sid, base)
    if not meta:
        raise RuntimeError(f"snapshot {sid} not found")
    addons_dir = meta["addonsDir"]
    src = os.path.join(base, sid, "AddOns")
    names = list(meta.get("folders") or []) if folders is None else [f for f in folders if _valid_name(f)]
    missing = [n for n in names if not os.path.lexists(os.path.join(src, n))]
    if missing:
        raise RuntimeError(f"snapshot {sid} does not contain {', '.join(missing)}")
    # keep=0: no pruning here, which could otherwise delete the snapshot being restored
    safety = create(addons_dir, meta.get("installationId"), f"before restoring {sid}", 0, base)
    os.makedirs(addons_dir, exist_ok=True)
    removed = []
    if folders is None:
        wanted = {n.lower() for n in names}
        for e in os.listdir(addons_dir):
            p = os.path.join(addons_dir, e)
            if os.path.isdir(p) and e.lower() not in wanted and _valid_name(e):
                shutil.rmtree(p) if not os.path.islink(p) else os.unlink(p)
                removed.append(e)
    for name in names:
        cur = wow.ci_child(addons_dir, name)
        if cur:
            shutil.rmtree(cur) if (os.path.isdir(cur) and not os.path.islink(cur)) else os.unlink(cur)
        _link_tree(os.path.join(src, name), os.path.join(addons_dir, name))
    logger.info("restored %d folders from snapshot %s (removed %d)", len(names), sid, len(removed))
    return {"restored": names, "removed": removed, "safetySnapshot": safety["id"] if safety else None}
