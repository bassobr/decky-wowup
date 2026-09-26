"""Headless WowUp-CF runs: gamescope --backend headless -- <AppImage> --hidden --quit.

Validated on SteamOS 3.8 in Desktop and Game Mode (docs/konzept.md, runs V4/V6/GM-V4/GM-V6):
no DISPLAY, XAUTHORITY or D-Bus is needed. WowUp installs updates only for addons with
autoUpdateEnabled, and never quits while a desktop notification is open, so each run temporarily
sets the flags for its mode and turns notifications off. A journal restores both after a crash.
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
from typing import Any, Callable, Dict, Iterable, List, Optional

from . import paths, util
from .constants import KILL_GRACE_S, RUN_TIMEOUT_S, WOWUP_PROCESS_NAMES
from .log import logger
from .wowup_store import WowUpStore, addon_key, is_running, needs_update

MODES = ("check", "all", "auto", "selected")
Progress = Optional[Callable[[str, Optional[float]], None]]

_LOG_LINE = re.compile(r"^\[(?P<ts>[^\]]+)\]\s+\[(?P<level>\w+)\]\s+(?P<msg>.*)$")
_UPDATE = re.compile(r"^\[AddonUpdate\]\s+(?P<provider>\S+)\s+(?P<id>\S+)\s+(?P<name>.+?)\s+"
                     r"'(?P<frm>[^']*)'\s+->\s+'(?P<to>[^']*)'\s*$")
_DONE = re.compile(r"^\[AddonUpdateComplete\]\s+(?P<provider>\S+)\s+(?P<id>\S+)\s+(?P<name>.+?)\s+(?P<version>\S+)\s*$")


# ---------------------------------------------------------------- planning
def plan_flags(addons: Dict[str, Dict[str, Any]], mode: str, selection: Optional[Iterable[str]] = None,
               installation_id: Optional[str] = None, blocked: Optional[Iterable[str]] = None) -> Dict[str, bool]:
    """autoUpdateEnabled per record id for this run; records left out keep the user's flag ('auto').

    Addons of `blocked` installations are never updated: WowUp writes into whatever folder an
    installation points to and creates it if needed, e.g. inside a deleted Proton prefix."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    blocked = set(blocked or [])
    if mode == "auto":
        return {rid: False for rid, a in addons.items() if a.get("installationId") in blocked}
    wanted = set(selection or [])
    plan: Dict[str, bool] = {}
    for rid, a in addons.items():
        in_scope = (installation_id is None or a.get("installationId") == installation_id) \
            and a.get("installationId") not in blocked
        if mode == "check":
            want = False
        elif mode == "all":
            want = in_scope and not a.get("isIgnored")
        else:
            want = in_scope and addon_key(a) in wanted and not a.get("isIgnored")
        plan[rid] = bool(want)
    return plan


def build_env(config_home: Optional[str] = None) -> Dict[str, str]:
    env = util.user_env()
    if config_home:
        env["XDG_CONFIG_HOME"] = config_home
    return env


def build_command(appimage: str, use_gamescope: bool = True) -> List[str]:
    cmd = [appimage, "--hidden", "--quit"]
    if use_gamescope:
        cmd = [util.which("gamescope") or "gamescope", "--backend", "headless", "-W", "1280", "-H", "800", "--"] + cmd
    return cmd


# ---------------------------------------------------------------- results
def parse_log(text: str) -> Dict[str, Any]:
    updates, completed, errors = [], [], []
    quit_seen = False
    for raw in text.splitlines():
        m = _LOG_LINE.match(raw.strip())
        if not m:
            continue
        msg, level = m.group("msg").strip(), m.group("level").lower()
        u = _UPDATE.match(msg)
        if u:
            updates.append({"provider": u.group("provider"), "externalId": u.group("id"), "name": u.group("name"),
                            "from": u.group("frm"), "to": u.group("to")})
            continue
        d = _DONE.match(msg)
        if d:
            completed.append({"provider": d.group("provider"), "externalId": d.group("id"), "name": d.group("name"),
                              "version": d.group("version")})
            continue
        if msg.startswith("[QuitApp]"):
            quit_seen = True
        elif level == "error":
            errors.append(msg[:300])
    return {"updates": updates, "completed": completed, "errors": errors, "quit": quit_seen}


def _v(s: Any) -> str:
    return str(s or "").strip().lstrip("vV")


def diff_addons(before: Dict[str, Dict[str, Any]], after: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    old = {addon_key(a): a for a in before.values()}
    updated = []
    for a in after.values():
        prev = old.get(addon_key(a))
        if prev is None:
            continue
        if str(prev.get("installedExternalReleaseId")) != str(a.get("installedExternalReleaseId")) \
                or _v(prev.get("installedVersion")) != _v(a.get("installedVersion")):
            updated.append({"key": addon_key(a), "name": a.get("name"), "from": prev.get("installedVersion") or "",
                            "to": a.get("installedVersion") or "", "installationId": a.get("installationId")})
    pending = sum(1 for a in after.values() if needs_update(a))
    return {"updated": updated, "pending": pending}


# ---------------------------------------------------------------- journal
class Journal:
    def __init__(self, path: str):
        self.path = path

    def write(self, data: Dict[str, Any]) -> None:
        util.write_json(self.path, data, 0o600)

    def load(self) -> Optional[Dict[str, Any]]:
        d = util.read_json(self.path)
        return d if isinstance(d, dict) else None

    def clear(self) -> None:
        try:
            os.unlink(self.path)
        except OSError:
            pass


def restore(store: WowUpStore, data: Dict[str, Any]) -> Dict[str, Any]:
    """Put back the flags and preferences a run changed (also used after a crash)."""
    flags = data.get("flags") or {}
    addons = store.load_addons()
    changed = 0
    for a in addons.values():
        k = addon_key(a)
        if k in flags and bool(a.get("autoUpdateEnabled")) != bool(flags[k]):
            a["autoUpdateEnabled"] = bool(flags[k])
            changed += 1
    if changed:
        store.save_addons(addons)
    prefs_orig = data.get("prefs") or {}
    if prefs_orig:
        prefs = store.load_prefs()
        dirty = False
        for k, v in prefs_orig.items():
            if v is None:
                if k in prefs:
                    del prefs[k]
                    dirty = True
            elif prefs.get(k) != v:
                prefs[k] = v
                dirty = True
        if dirty:
            store.save_prefs(prefs)
    return {"flagsRestored": changed, "prefsRestored": sorted(prefs_orig)}


def recover(store: WowUpStore, journal_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    j = Journal(journal_path or paths.JOURNAL_FILE)
    data = j.load()
    if not data:
        return None
    if is_running():
        raise RuntimeError("an interrupted run needs recovery, but WowUp-CF is running")
    target = WowUpStore(data.get("configDir") or store.dir)
    res = restore(target, data)
    j.clear()
    res["runId"] = data.get("runId")
    return res


# ---------------------------------------------------------------- process
def _kill(proc: subprocess.Popen) -> None:
    for sig, wait in ((signal.SIGTERM, KILL_GRACE_S), (signal.SIGKILL, KILL_GRACE_S)):
        try:
            os.killpg(proc.pid, sig)
        except OSError:
            pass
        try:
            proc.wait(timeout=wait)
            break
        except subprocess.TimeoutExpired:
            continue
    for pid in util.pids_by_name(WOWUP_PROCESS_NAMES):  # stray Electron children of this run
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def _prune_outputs(runs_dir: str, keep: int = 20) -> None:
    try:
        files = sorted(f for f in os.listdir(runs_dir) if f.endswith(".out"))
    except OSError:
        return
    for f in files[:-keep]:
        try:
            os.unlink(os.path.join(runs_dir, f))
        except OSError:
            pass


# ---------------------------------------------------------------- run
def run(store: WowUpStore, appimage: str, mode: str = "check", selection: Optional[Iterable[str]] = None,
        installation_id: Optional[str] = None, timeout: int = RUN_TIMEOUT_S, disable_notifications: bool = True,
        blocked: Optional[Iterable[str]] = None,
        use_gamescope: bool = True, config_home: Optional[str] = None, journal_path: Optional[str] = None,
        runs_dir: Optional[str] = None, on_progress: Progress = None) -> Dict[str, Any]:
    def progress(msg: str, pct: Optional[float] = None) -> None:
        if on_progress:
            on_progress(msg, pct)

    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    journal_path = journal_path or paths.JOURNAL_FILE
    runs_dir = runs_dir or paths.RUNS_DIR
    if not appimage or not os.path.isfile(appimage):
        raise RuntimeError("WowUp-CF AppImage not found")
    if is_running():
        raise RuntimeError("WowUp-CF is already running – close it before updating")
    journal = Journal(journal_path)
    if journal.load():
        recover(store, journal_path)
    prefs = store.load_prefs()
    if not (prefs.get("wow_installations") or prefs.get("blizzard_agent_path")):
        raise RuntimeError("WowUp-CF has no WoW installation configured")

    before = store.load_addons()
    snapshot_before = json.loads(json.dumps(before))
    plan = plan_flags(before, mode, selection, installation_id, blocked)
    orig_flags = {addon_key(before[rid]): bool(before[rid].get("autoUpdateEnabled"))
                  for rid, want in plan.items() if bool(before[rid].get("autoUpdateEnabled")) != want}
    orig_prefs: Dict[str, Any] = {}
    if disable_notifications and prefs.get("enable_system_notifications") != "false":
        orig_prefs["enable_system_notifications"] = prefs.get("enable_system_notifications")
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + os.urandom(2).hex()
    journal.write({"runId": run_id, "mode": mode, "configDir": store.dir, "flags": orig_flags,
                   "prefs": orig_prefs, "startedAt": util.now_iso()})
    result: Dict[str, Any] = {"runId": run_id, "mode": mode, "installationId": installation_id, "ok": False,
                              "blocked": sorted(set(blocked or [])),
                              "rc": None, "timedOut": False, "durationMs": 0, "quit": False, "updates": [],
                              "completed": [], "errors": [], "updated": [], "pending": None,
                              "startedAt": util.now_iso(), "finishedAt": None}
    try:
        if orig_flags:
            for rid, want in plan.items():
                before[rid]["autoUpdateEnabled"] = want
            store.save_addons(before)
        if orig_prefs:
            prefs["enable_system_notifications"] = "false"
            store.save_prefs(prefs)
        offset = store.log_size()
        os.makedirs(runs_dir, exist_ok=True)
        out_path = os.path.join(runs_dir, f"{run_id}.out")
        cmd = build_command(appimage, use_gamescope)
        logger.info("WowUp run %s (%s): %s", run_id, mode, " ".join(cmd))
        progress("Running WowUp-CF…", None)
        t0 = time.monotonic()
        with open(out_path, "wb") as out:
            proc = subprocess.Popen(cmd, env=build_env(config_home), stdout=out, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, start_new_session=True, cwd=paths.HOME)
            try:
                rc = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                result["timedOut"] = True
                logger.warning("WowUp run %s timed out after %ss, stopping it", run_id, timeout)
                _kill(proc)
                rc = proc.returncode
        result["rc"] = rc
        result["durationMs"] = int((time.monotonic() - t0) * 1000)
        progress("Reading results…", None)
        result.update(parse_log(store.read_log_since(offset)))
        result.update(diff_addons(snapshot_before, store.load_addons()))
        result["ok"] = rc == 0 and result["quit"] and not result["timedOut"]
        result["output"] = out_path
    finally:
        data = journal.load() or {}
        try:
            restore(store, data)
            journal.clear()
        except Exception as e:  # journal stays for recovery on next start
            logger.error("restoring WowUp settings after run %s failed: %s", run_id, e)
        result["finishedAt"] = util.now_iso()
        _prune_outputs(runs_dir)
    logger.info("WowUp run %s: ok=%s rc=%s %sms, %d updated, %d errors", run_id, result["ok"], result["rc"],
                result["durationMs"], len(result["updated"]), len(result["errors"]))
    return result
