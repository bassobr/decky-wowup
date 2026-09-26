"""Orchestration shared by main.py (Decky) and cli.py: state, runs, WowUp provisioning, snapshots."""
from __future__ import annotations

import os
import re
import shutil
import time
from typing import Any, Callable, Dict, List, Optional

from . import catalog, finders, paths, snapshots, toc, util, wow, wowup_app, wowup_runner
from . import settings as settings_mod
from .constants import (CLIENT_TYPES, DISCOVERY_CACHE_S, GAME_TYPE_LABELS, SNAPSHOT_KEEP, WOWUP_CHECK_INTERVAL_S,
                        WOWUP_CONFIG_NAME, WOWUP_EXE_BY_CLIENT_TYPE)
from .log import logger
from .wowup_store import (CHANNELS, PROVIDERS, WowUpStore, addon_key, installation_entry, installation_label,
                          is_running, needs_update, placeholder, release_channel)

Progress = Optional[Callable[[str, Optional[float]], None]]

# WowUp record fields that describe the installed version; saved with each snapshot for rollback.
RESTORE_FIELDS = ("installedVersion", "installedExternalReleaseId", "installedAt", "installedFolders",
                  "installedFolderList", "gameVersion")
# Written by WowUp itself for its "Addon Update Notifications" addon (wowup-addon.service.ts).
WOWUP_DATA_ADDON = "wowup_data_addon"
VALID_EXTERNAL_ID = re.compile(r"^\d{1,12}$")
DEPENDENCY_REQUIRED = 2  # WowUp AddonDependencyType: 1 embedded, 2 required, 3 optional, 4 other
RUN_SUMMARY_KEYS = ("runId", "mode", "installationId", "ok", "rc", "timedOut", "durationMs", "quit", "updated",
                    "errors", "pending", "startedAt", "finishedAt", "snapshots", "blocked")


def brief(res: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return {k: res.get(k) for k in RUN_SUMMARY_KEYS} if res else None


def _name(a: Dict[str, Any]) -> str:
    return str(a.get("name") or addon_key(a))


class Dependencies:
    """Dependency edges between the WowUp records of one installation, by record id. WowUp resolves
    a dependency within the same provider and installation (addon-install.service removeDependencies)."""

    def __init__(self, mine: Dict[str, Dict[str, Any]]):
        by_ext = {(r.get("providerName"), str(r.get("externalId"))): rid for rid, r in mine.items()}
        self.required: Dict[str, List[str]] = {}
        self.users: Dict[str, set] = {}  # record id -> ids of records that depend on it (any type)
        for rid, a in mine.items():
            req: List[str] = []
            for dep in a.get("dependencies") or []:
                if not isinstance(dep, dict) or not dep.get("externalAddonId"):
                    continue
                d = by_ext.get((a.get("providerName"), str(dep["externalAddonId"])))
                if d is None or d == rid:
                    continue
                self.users.setdefault(d, set()).add(rid)
                if str(dep.get("type")) == str(DEPENDENCY_REQUIRED) and d not in req:
                    req.append(d)
            self.required[rid] = req

    def removable(self, removing: List[str]) -> List[str]:
        """Required dependencies of `removing` that no addon staying installed depends on (one level, like WowUp)."""
        gone = set(removing)
        out: List[str] = []
        for rid in removing:
            for d in self.required.get(rid, []):
                if d not in gone and d not in out and not (self.users.get(d, set()) - gone):
                    out.append(d)
        return out

    def required_by(self, rid: str) -> List[str]:
        return [u for u, req in self.required.items() if rid in req]


def case_duplicates(addons_dir: Optional[str]) -> List[List[str]]:
    if not addons_dir or not os.path.isdir(addons_dir):
        return []
    groups: Dict[str, List[str]] = {}
    for e in os.listdir(addons_dir):
        groups.setdefault(e.lower(), []).append(e)
    return [sorted(v) for v in groups.values() if len(v) > 1]


class Service:
    def __init__(self, settings: Dict[str, Any], save: Callable[[], None], store: Optional[WowUpStore] = None):
        self.settings = settings
        self._save = save
        self.store = store or WowUpStore(paths.WOWUP_CONFIG_DIR)
        self._detected: tuple = (0.0, [])
        self._sources: Dict[str, int] = {}

    # ---------------------------------------------------------------- discovery
    def detected(self, refresh: bool = False) -> List[Dict[str, Any]]:
        ts, data = self._detected
        if refresh or not ts or time.monotonic() - ts > DISCOVERY_CACHE_S:
            try:
                cands = finders.candidates(self.settings)
                self._sources = finders.summary(cands)
                data = wow.discover(cands)
            except Exception as e:
                logger.error("discovery failed: %s", e)
                data = []
            self._detected = (time.monotonic(), data)
        return data

    def discovery_info(self) -> Dict[str, Any]:
        d = self.settings.get("discovery") or {}
        return {"sources": dict(self._sources), "searchPaths": list(d.get("searchPaths") or []),
                "manualPaths": list(d.get("manualPaths") or []), "scanRemovable": d.get("scanRemovable", True) is not False,
                "home": paths.HOME, "removable": finders.removable_roots()}

    def set_discovery(self, prefs: Dict[str, Any]) -> Dict[str, Any]:
        d = self.settings.setdefault("discovery", {})
        if "searchPaths" in prefs:
            clean = []
            for p in prefs.get("searchPaths") or []:
                p = os.path.realpath(os.path.expanduser(str(p)))
                if os.path.isdir(p) and p not in clean:
                    clean.append(p)
            d["searchPaths"] = clean[:20]
        if "scanRemovable" in prefs:
            d["scanRemovable"] = bool(prefs["scanRemovable"])
        if "manualPaths" in prefs:
            d["manualPaths"] = [str(p) for p in prefs.get("manualPaths") or []][:20]
        self._save()
        self.detected(refresh=True)
        return self.discovery_info()

    # ---------------------------------------------------------------- WowUp-CF AppImage
    def appimage(self) -> Optional[str]:
        p = self.settings["wowup"].get("appImage")
        if p and os.path.isfile(p):
            return p
        return paths.WOWUP_LINK if os.path.isfile(paths.WOWUP_LINK) else None

    def channel(self) -> str:
        c = self.settings["wowup"].get("channel") or "follow"
        if c in ("stable", "beta"):
            return c
        return release_channel(self.store.load_prefs()) if self.store.exists() else "stable"

    def wowup_info(self) -> Dict[str, Any]:
        app = self.appimage()
        info = wowup_app.describe(app) if app else None
        w = self.settings["wowup"]
        latest = w.get("latest") or None
        current = info["version"] if info else None
        return {
            "path": app,
            "version": current,
            "verified": w.get("verified") if app else None,
            "managed": bool(info and info["managed"]),
            "running": is_running(),
            "profileExists": self.store.exists(),
            "configDir": self.store.dir,
            "channel": self.channel(),
            "candidates": [] if app else wowup_app.find_candidates(),
            "latestVersion": latest.get("version") if latest else None,
            "updateAvailable": bool(latest and current and wowup_app.is_newer(latest.get("version"), current)),
            "lastCheck": w.get("lastCheck"),
            "error": w.get("error"),
        }

    def adopt(self, path: str, require_verified: bool = True) -> Dict[str, Any]:
        info = wowup_app.describe(path)
        if not info or not info["version"]:
            raise RuntimeError(f"not a WowUp-CF AppImage: {path}")
        verified: Optional[bool] = None
        detail: Any = None
        try:
            exp = wowup_app.expected_hashes(wowup_app.release_by_version(info["version"]))
            detail = wowup_app.verify(path, exp)
            verified = bool(detail["ok"])
        except Exception as e:
            detail = str(e)
            if require_verified:
                raise RuntimeError(f"cannot verify {os.path.basename(path)}: {e}")
        if verified is False:
            raise RuntimeError(f"{os.path.basename(path)} does not match the checksums of release {info['version']}")
        if not info["executable"]:
            os.chmod(info["realpath"], 0o755)
        self.settings["wowup"].update({"appImage": path, "verified": verified})
        self._save()
        logger.info("using WowUp-CF %s at %s (verified=%s)", info["version"], path, verified)
        return {"path": path, "version": info["version"], "verified": verified, "detail": detail}

    def auto_adopt(self) -> Optional[Dict[str, Any]]:
        """Pick up an existing AppImage once, but only after it matched its release checksums."""
        if self.appimage():
            return None
        cands = wowup_app.find_candidates()
        if not cands:
            return None
        try:
            return self.adopt(cands[0]["path"], require_verified=True)
        except Exception as e:
            logger.warning("found %s but did not adopt it: %s", cands[0]["path"], e)
            return None

    def check_wowup_update(self, force: bool = False) -> Dict[str, Any]:
        w = self.settings["wowup"]
        now = int(time.time())
        if force or not w.get("latest") or now - int(w.get("lastCheck") or 0) >= WOWUP_CHECK_INTERVAL_S:
            try:
                rel = wowup_app.pick_release(wowup_app.fetch_releases(), self.channel())
                w["latest"] = {"version": rel["version"], "tag": rel["tag"], "prerelease": rel["prerelease"],
                               "publishedAt": rel["publishedAt"], "htmlUrl": rel["htmlUrl"]} if rel else None
                w["error"] = None
            except Exception as e:
                logger.warning("WowUp-CF update check failed: %s", e)
                w["error"] = str(e)
            w["lastCheck"] = now
            self._save()
        return self.wowup_info()

    def install_wowup(self, progress: Progress = None, channel: Optional[str] = None) -> Dict[str, Any]:
        if is_running():
            raise RuntimeError("WowUp-CF is running – close it first")
        ch = channel if channel in ("stable", "beta") else self.channel()
        rel = wowup_app.pick_release(wowup_app.fetch_releases(), ch)
        if not rel:
            raise RuntimeError("no WowUp-CF release with an AppImage found")
        res = wowup_app.install(rel, progress)
        wowup_app.set_link(res["path"])
        self.settings["wowup"].update({"appImage": paths.WOWUP_LINK, "verified": True, "latest": {
            "version": rel["version"], "tag": rel["tag"], "prerelease": rel["prerelease"],
            "publishedAt": rel["publishedAt"], "htmlUrl": rel["htmlUrl"]}, "lastCheck": int(time.time())})
        self._save()
        seeded = self._seed_profile()
        first = self.run_update("check", progress=progress) if seeded else None
        return {"installed": res, "seededProfile": seeded, "firstRun": brief(first)}

    def _seed_profile(self) -> bool:
        """Fresh profile: write every WoW version found (all sources) as WowUp installations."""
        if self.store.exists():
            return False
        if not self.detected(refresh=True):
            return False
        os.makedirs(self.store.dir, exist_ok=True)
        return bool(self.add_installations(None)["added"])

    def apply_wowup_update(self, progress: Progress = None) -> Dict[str, Any]:
        if is_running():
            raise RuntimeError("WowUp-CF is running – close it first")
        latest = (self.settings["wowup"].get("latest") or {}).get("version")
        if not latest:
            latest = self.check_wowup_update(force=True).get("latestVersion")
        if not latest:
            raise RuntimeError("no WowUp-CF release information")
        current = self.wowup_info()["version"]
        if current and not wowup_app.is_newer(latest, current):
            return {"updated": False, "version": current}
        res = wowup_app.install(wowup_app.release_by_version(latest), progress)
        if progress:
            progress(f"Testing WowUp-CF {latest} on a copy of your profile…", None)
        can = wowup_app.canary(res["path"], self.store, timeout=settings_mod.timeout_s(self.settings))
        if not can["ok"]:
            raise RuntimeError(f"WowUp-CF {latest} failed the test run; staying on {current}: {can}")
        wowup_app.set_link(res["path"])
        self.settings["wowup"].update({"appImage": paths.WOWUP_LINK, "verified": True})
        self._save()
        return {"updated": True, "from": current, "to": latest, "canary": can, "pruned": wowup_app.prune(keep=2)}

    # ---------------------------------------------------------------- installations and addons
    def installations(self) -> List[Dict[str, Any]]:
        by_real = {os.path.realpath(d["flavorDir"]): d for d in self.detected()}
        out = []
        for inst in self.store.installations():
            d = by_real.get(os.path.realpath(inst["flavorDir"])) if inst["flavorDir"] else None
            if d:
                product, version = d["product"], d["version"]
            else:
                product, version = wow.flavor_version(inst["flavorDir"]) if inst["exists"] else (None, None)
            gtype, iface = wow.game_type(version)
            inst.update({"product": product, "version": version, "gameType": gtype,
                         "gameTypeLabel": GAME_TYPE_LABELS.get(gtype or "", gtype), "interface": iface,
                         "source": d.get("source") if d else None})
            out.append(inst)
        return out

    @staticmethod
    def folders_of(a: Dict[str, Any]) -> List[str]:
        folders = [f for f in (a.get("installedFolderList") or []) if isinstance(f, str) and f]
        if not folders and a.get("installedFolders"):
            folders = [f.strip() for f in str(a["installedFolders"]).split(",") if f.strip()]
        return folders

    def addons(self, inst: Dict[str, Any], records: Optional[Dict[str, Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        records = self.store.load_addons() if records is None else records
        addons_dir = inst.get("addonsDir")
        mine = {rid: r for rid, r in records.items() if r.get("installationId") == inst["id"]}
        deps = Dependencies(mine)
        out = []
        for rid, a in sorted(mine.items(), key=lambda kv: str(kv[1].get("name") or "").lower()):
            folders = self.folders_of(a)
            status, iface, present = "unknown", None, False
            for f in folders:
                p = wow.ci_child(addons_dir, f) if addons_dir else None
                if not p or not os.path.isdir(p):
                    continue
                present = True
                fs = toc.folder_status(p, inst.get("gameType"), inst.get("interface"))
                if fs.get("toc") and (status == "unknown" or not fs.get("loadOnDemand")):
                    status, iface = fs["status"], fs["interface"]
                    if not fs.get("loadOnDemand"):
                        break
            out.append({
                "key": addon_key(a), "id": a.get("id"), "name": a.get("name") or (folders[0] if folders else "?"),
                "author": a.get("author"), "provider": a.get("providerName"), "externalId": a.get("externalId"),
                "installedVersion": a.get("installedVersion"), "latestVersion": a.get("latestVersion"),
                "needsUpdate": needs_update(a), "autoUpdate": bool(a.get("autoUpdateEnabled")),
                "ignored": bool(a.get("isIgnored")), "channel": CHANNELS.get(a.get("channelType"), "stable"),
                "folders": folders, "compat": status, "interface": iface, "missing": bool(folders) and not present,
                "removableDeps": [{"key": addon_key(mine[d]), "name": _name(mine[d])} for d in deps.removable([rid])],
                "requiredBy": sorted(_name(mine[u]) for u in deps.required_by(rid)),
            })
        return out

    @staticmethod
    def unmanaged(inst: Dict[str, Any], addons: List[Dict[str, Any]]) -> List[str]:
        d = inst.get("addonsDir")
        if not d or not os.path.isdir(d):
            return []
        claimed = {f.lower() for a in addons for f in a["folders"]} | {WOWUP_DATA_ADDON}
        return sorted(e for e in os.listdir(d)
                      if os.path.isdir(os.path.join(d, e)) and not e.startswith(".") and e.lower() not in claimed)

    def state(self, refresh: bool = False) -> Dict[str, Any]:
        if refresh:
            self.detected(refresh=True)
        wowup = self.wowup_info()
        records = self.store.load_addons()
        insts = self.installations()
        known = {os.path.realpath(i["flavorDir"]) for i in insts if i.get("flavorDir")}
        detected = self.detected()
        missing = [d for d in detected if os.path.realpath(d["flavorDir"]) not in known]
        per: Dict[str, List[Dict[str, Any]]] = {}
        warnings: List[str] = []
        per_count: Dict[Any, int] = {}
        for a in records.values():
            per_count[a.get("installationId")] = per_count.get(a.get("installationId"), 0) + 1
        for inst in insts:
            lst = self.addons(inst, records)
            inst["addonCount"] = len(lst)
            inst["updateCount"] = sum(1 for a in lst if a["needsUpdate"])
            inst["incompatibleCount"] = sum(1 for a in lst if a["compat"] == "incompatible")
            inst["unmanaged"] = self.unmanaged(inst, lst)
            for group in case_duplicates(inst.get("addonsDir")):
                warnings.append(f"{inst['label']}: folders differ only in case: {', '.join(group)}")
            inst["hasGame"] = self.has_game(inst)
            inst["relocateTo"] = [] if inst["hasGame"] else self.relocation_targets(inst, insts, per_count)
            if not inst["exists"]:
                warnings.append(f"{inst['label']}: folder not found ({inst['flavorDir']}) – its addons are not updated")
            elif not inst["hasGame"]:
                warnings.append(f"{inst['label']}: no WoW installation in {inst['flavorDir']} (only an AddOns folder, "
                                f"e.g. an old Proton prefix) – its addons are not updated")
            per[str(inst["id"])] = lst
        if wowup["running"]:
            warnings.append("WowUp-CF is running – updates are possible once it is closed.")
        if os.path.exists(paths.JOURNAL_FILE):
            warnings.append("An interrupted update run will be repaired automatically.")
        last = util.read_json(paths.STATE_FILE, {}) or {}
        return {"wowup": wowup, "installations": insts, "addons": per, "detected": detected,
                "missingInWowUp": missing, "lastRun": last.get("lastRun"), "discovery": self.discovery_info(),
                "snapshots": [dict({k: m.get(k) for k in ("id", "installationId", "installationLabel", "label", "createdAt",
                                                          "method", "names")}, kind=m.get("kind") or "update")
                              for m in snapshots.list_snapshots()[:12]],
                "warnings": warnings}

    # ---------------------------------------------------------------- runs
    def run_update(self, mode: str, installation_id: Optional[str] = None, selection: Optional[List[str]] = None,
                   progress: Progress = None) -> Dict[str, Any]:
        app = self.appimage()
        if not app:
            raise RuntimeError("WowUp-CF is not installed")
        insts = self.installations()
        blocked = [i["id"] for i in insts if not self.has_game(i)]
        if blocked:
            logger.info("not updating addons of installations without a game: %s", blocked)
        if mode != "check" and installation_id is not None and installation_id in blocked:
            inst = next(i for i in insts if i["id"] == installation_id)
            raise RuntimeError(f"{inst['label']}: no WoW installation in {inst['flavorDir']} – "
                               f"move it to the real WoW folder first")
        snaps: List[str] = []
        if mode != "check":
            records = self.store.load_addons()
            keep = int(self.settings["snapshots"].get("keep") or SNAPSHOT_KEEP)
            for inst in insts:
                if installation_id not in (None, inst["id"]) or inst["id"] in blocked or not inst.get("addonsDir") \
                        or not os.path.isdir(inst["addonsDir"]):
                    continue
                if progress:
                    progress(f"Snapshot of {inst['label']}…", None)
                saved = {addon_key(a): {k: a.get(k) for k in RESTORE_FIELDS}
                         for a in records.values() if a.get("installationId") == inst["id"]}
                meta = snapshots.create(inst["addonsDir"], inst["id"], f"before '{mode}' run", keep,
                                        extra={"wowupRecords": saved, "installationLabel": inst["label"]})
                if meta:
                    snaps.append(meta["id"])
        # WowUp must read the same profile this service reads (matters for sandboxes/canaries).
        res = wowup_runner.run(self.store, app, mode, selection, installation_id,
                               timeout=settings_mod.timeout_s(self.settings),
                               disable_notifications=bool(self.settings["runner"].get("disableNotifications", True)),
                               blocked=blocked,
                               config_home=os.path.dirname(self.store.dir.rstrip("/")), on_progress=progress)
        if not res["updated"]:
            for sid in snaps:  # nothing changed, nothing to roll back to
                snapshots.delete(sid)
            snaps = []
        res["snapshots"] = snaps
        state = util.read_json(paths.STATE_FILE, {}) or {}
        state["lastRun"] = brief(res)
        util.write_json(paths.STATE_FILE, state)
        return res

    def restore_snapshot(self, sid: str, keys: Optional[List[str]] = None, progress: Progress = None) -> Dict[str, Any]:
        if is_running():
            raise RuntimeError("WowUp-CF is running – close it first")
        meta = snapshots.get(sid)
        if not meta:
            raise RuntimeError(f"snapshot {sid} not found")
        if meta.get("kind") == "remove":
            return self._restore_removal(meta, keys, progress)
        saved = meta.get("wowupRecords") or {}
        folders = None
        if keys:
            folders = sorted({f for k in keys for f in (saved.get(k, {}).get("installedFolderList") or [])})
            if not folders:
                raise RuntimeError("the snapshot has no folders for the selected addons")
        if progress:
            progress("Restoring addon folders…", None)
        res = snapshots.restore(sid, folders)
        addons = self.store.load_addons()
        changed = 0
        for a in addons.values():
            k = addon_key(a)
            if k in saved and (not keys or k in keys):
                for field in RESTORE_FIELDS:
                    if field in saved[k]:
                        a[field] = saved[k][field]
                changed += 1
        if changed:  # WowUp then reports the update again; ignore the addon to stay on the old version
            self.store.save_addons(addons)
        res["recordsRestored"] = changed
        return res

    def _restore_removal(self, meta: Dict[str, Any], keys: Optional[List[str]], progress: Progress) -> Dict[str, Any]:
        """Undo a removal: put back the removed folders and WowUp records. Addons installed again in
        the meantime keep their current folders and records."""
        inst_ids = {w.get("id") for w in self.store.load_prefs().get("wow_installations") or [] if isinstance(w, dict)}
        if meta.get("installationId") not in inst_ids:
            raise RuntimeError("the WoW version of this snapshot is no longer in WowUp-CF")
        addons = self.store.load_addons()
        now = {addon_key(a) for a in addons.values()}
        removed = {rid: rec for rid, rec in (meta.get("removedRecords") or {}).items() if isinstance(rec, dict)}
        back = {rid for rid, rec in removed.items() if addon_key(rec) not in now and (not keys or addon_key(rec) in keys)}
        not_back = {f.lower() for rid, rec in removed.items() if rid not in back for f in self.folders_of(rec)}
        wanted = [f for f in meta.get("removedFolders") or [] if f.lower() not in not_back]
        if keys:  # only the folders of the chosen addons, no loose folders
            mine = {f.lower() for rid in back for f in self.folders_of(removed[rid])}
            wanted = [f for f in wanted if f.lower() in mine]
        addons_dir = meta.get("addonsDir") or ""
        wanted = [f for f in wanted if not (os.path.isdir(addons_dir) and wow.ci_child(addons_dir, f))]
        if progress:
            progress("Restoring addon folders…", None)
        res = snapshots.restore(meta["id"], wanted) if wanted else {"restored": [], "removed": [], "safetySnapshot": None}
        for rid in back:
            rec = dict(removed[rid])
            if rid in addons:
                rid = rec["id"] = util.new_uuid4()
            addons[rid] = rec
        if back:
            self.store.save_addons(addons)
        res["recordsRestored"] = len(back)
        return res

    def remove_addons(self, installation_id: str, keys: Optional[List[str]] = None, folders: Optional[List[str]] = None,
                      with_dependencies: bool = False, progress: Progress = None) -> Dict[str, Any]:
        """Remove addons like WowUp does (delete their folders, drop their records), plus folders WowUp
        does not manage. Folders another addon still uses stay. A snapshot is taken first (undo)."""
        if is_running():
            raise RuntimeError("WowUp-CF is running – close it first")
        inst = self.installation(installation_id)
        addons_dir = inst.get("addonsDir")
        if not addons_dir or not os.path.isdir(addons_dir):
            raise RuntimeError(f"{inst['label']}: AddOns folder not found")
        records = self.store.load_addons()
        mine = {rid: a for rid, a in records.items() if a.get("installationId") == inst["id"]}
        wanted = set(keys or [])
        targets = [rid for rid, a in mine.items() if addon_key(a) in wanted]
        if len(targets) != len(wanted):
            raise RuntimeError("some of these addons are not installed here (any more)")
        if with_dependencies:
            targets += Dependencies(mine).removable(targets)
        loose = []
        if folders:
            unmanaged = {f.lower(): f for f in self.unmanaged(inst, self.addons(inst, records))}
            for f in folders:
                if f.lower() not in unmanaged:
                    raise RuntimeError(f"{f} is not an unmanaged folder of {inst['label']}")
                loose.append(unmanaged[f.lower()])
        if not targets and not loose:
            raise RuntimeError("nothing to remove")
        staying = {f.lower() for rid, a in mine.items() if rid not in targets for f in self.folders_of(a)}
        delete: Dict[str, str] = {}  # lower-case name -> folder as it is on disk
        shared = set()
        for f in [f for rid in targets for f in self.folders_of(mine[rid])] + loose:
            p = wow.ci_child(addons_dir, f) if snapshots.valid_name(f) else None
            if f.lower() in staying:
                shared.add(f)
            elif p:
                delete[f.lower()] = os.path.basename(p)
        names = [_name(mine[rid]) for rid in targets] + loose
        if progress:
            progress("Snapshot of the AddOns folder…", None)
        keep = int(self.settings["snapshots"].get("keep") or SNAPSHOT_KEEP)
        meta = snapshots.create(addons_dir, inst["id"], "before removing " + ", ".join(names), keep, extra={
            "kind": "remove", "names": names, "installationLabel": inst["label"],
            "removedFolders": sorted(delete.values(), key=str.lower),
            "removedRecords": {rid: mine[rid] for rid in targets}})
        if progress:
            progress(f"Removing {', '.join(names)}…", None)
        deleted, failed = [], []
        for name in sorted(delete.values(), key=str.lower):
            p = os.path.join(addons_dir, name)
            try:
                shutil.rmtree(p) if (os.path.isdir(p) and not os.path.islink(p)) else os.unlink(p)
                deleted.append(name)
            except OSError as e:
                failed.append(f"{name}: {e}")
        if targets:
            for rid in targets:
                records.pop(rid, None)
            self.store.save_addons(records)
        logger.info("removed %s from %s (folders %s, shared %s, snapshot %s)", names, inst["label"], deleted,
                    sorted(shared), meta["id"] if meta else None)
        return {"removed": names, "folders": deleted, "shared": sorted(shared), "failed": failed,
                "snapshot": meta["id"] if meta else None}

    def import_installations(self, progress: Progress = None) -> Dict[str, Any]:
        """Add every WoW version found but not yet in WowUp (kept for older frontends)."""
        return self.add_installations(None, progress)

    def add_installations(self, flavor_dirs: Optional[List[str]] = None, progress: Progress = None) -> Dict[str, Any]:
        """Write WowUp installations directly, for any source and any number of prefixes.

        Location = flavor folder + WowUp's executable name for the client type, spelled like the
        existing entries of the same prefix (WowUp's own product.db import compares exact strings)."""
        if is_running():
            raise RuntimeError("WowUp-CF is running – close it first")
        det = self.detected(refresh=True)
        prefs = self.store.load_prefs()
        entries = [w for w in prefs.get("wow_installations") or [] if isinstance(w, dict)]
        known = {os.path.realpath(os.path.dirname(str(w.get("location") or ""))) for w in entries if w.get("location")}
        wanted = {os.path.realpath(p) for p in flavor_dirs} if flavor_dirs else None
        added, skipped = [], []
        for d in det:
            real = os.path.realpath(d["flavorDir"])
            if wanted is not None and real not in wanted:
                continue
            info = {"flavorDir": d["flavorDir"], "source": d.get("source"), "version": d.get("version"),
                    "gameTypeLabel": d.get("gameTypeLabel"), "clientTypeLabel": d.get("clientTypeLabel")}
            if real in known:
                skipped.append(dict(info, reason="already in WowUp"))
                continue
            ct = d.get("clientType")
            if ct not in WOWUP_EXE_BY_CLIENT_TYPE:
                skipped.append(dict(info, reason="this WowUp version does not support this WoW folder yet"))
                continue
            location = self._spell_like_existing(os.path.join(real, WOWUP_EXE_BY_CLIENT_TYPE[ct]), entries)
            same_type = [w for w in entries if w.get("clientType") == ct]
            label = "{defaultName}" if not same_type else "{defaultName} (%s)" % (d.get("source") or len(same_type) + 1)
            entries.append(installation_entry(ct, location, label))
            known.add(real)
            added.append(dict(info, location=location, clientType=ct))
        if added:
            if not any(w.get("selected") for w in entries):
                entries[0]["selected"] = True
            prefs["wow_installations"] = entries
            os.makedirs(self.store.dir, exist_ok=True)
            self.store.save_prefs(prefs)
            logger.info("added %d WoW installation(s) to WowUp: %s", len(added), [a["location"] for a in added])
        if progress:
            progress(f"{len(added)} WoW version(s) added", None)
        return {"added": added, "skipped": skipped}

    def add_installation_path(self, path: str, progress: Progress = None) -> Dict[str, Any]:
        """A folder picked by hand: prefix, WoW folder or flavor folder. Remembered for later discovery."""
        cands = finders.manual_candidates(path)
        found = wow.discover(cands)
        if not found:
            raise RuntimeError("no World of Warcraft version found in this folder")
        d = self.settings.setdefault("discovery", {})
        manual = [p for p in d.get("manualPaths") or [] if p != cands[0]["path"]] + [cands[0]["path"]]
        d["manualPaths"] = manual[-20:]
        self._save()
        self._detected = (0.0, [])
        res = self.add_installations([f["flavorDir"] for f in found], progress)
        res["found"] = len(found)
        return res

    @staticmethod
    def has_game(inst: Dict[str, Any]) -> bool:
        """False for WowUp entries whose folder is gone or holds only Interface/AddOns (see wow.has_game)."""
        return bool(inst.get("exists")) and wow.has_game(inst["flavorDir"])

    def relocation_targets(self, inst: Dict[str, Any], insts: List[Dict[str, Any]],
                           addon_counts: Dict[Any, int]) -> List[Dict[str, Any]]:
        """Detected WoW folders of the same client type that a game-less installation can be moved to."""
        owners = {os.path.realpath(i["flavorDir"]): i for i in insts if i.get("flavorDir") and i["id"] != inst["id"]}
        out = []
        for d in self.detected():
            if d.get("clientType") != inst.get("clientType") or not wow.has_game(d["flavorDir"]):
                continue
            owner = owners.get(os.path.realpath(d["flavorDir"]))
            busy = bool(owner and addon_counts.get(owner["id"]))
            out.append({"flavorDir": d["flavorDir"], "version": d.get("version"), "source": d.get("source"),
                        "replaces": owner["label"] if owner else None, "possible": not busy,
                        "reason": f"{owner['label']} already has addons there" if busy else None})
        return out

    def relocate_installation(self, installation_id: str, flavor_dir: str, progress: Progress = None) -> Dict[str, Any]:
        """Point a WowUp installation at another WoW folder, keeping its addon list.

        Addon folders are copied from the old place when they exist there and are missing in the new
        one; addons with nothing to copy are marked for reinstall on the next update. An entry that
        already points at the new folder without addons is removed. The old folder is not touched."""
        if is_running():
            raise RuntimeError("WowUp-CF is running – close it first")
        inst = self.installation(installation_id)
        real = os.path.realpath(flavor_dir)
        target = next((d for d in self.detected(refresh=True) if os.path.realpath(d["flavorDir"]) == real), None)
        if not target or not wow.has_game(target["flavorDir"]):
            raise RuntimeError(f"no WoW installation found in {flavor_dir}")
        ct = inst.get("clientType")
        if target.get("clientType") != ct or ct not in WOWUP_EXE_BY_CLIENT_TYPE:
            raise RuntimeError(f"{flavor_dir} is a different WoW version than {inst['label']}")
        prefs = self.store.load_prefs()
        entries = [w for w in prefs.get("wow_installations") or [] if isinstance(w, dict)]
        addons = self.store.load_addons()
        mine = [a for a in addons.values() if a.get("installationId") == inst["id"]]
        used = {a.get("installationId") for a in addons.values()}
        spellings = list(entries)  # incl. an entry removed below: its spelling is what WowUp imports compare
        replaced = []
        for w in list(entries):
            loc = str(w.get("location") or "")
            if w.get("id") == inst["id"] or not loc or os.path.realpath(os.path.dirname(loc)) != real:
                continue
            if w.get("id") in used:
                raise RuntimeError(f"{installation_label(w.get('label'), w.get('clientType'))} already has addons "
                                   f"in {flavor_dir}")
            entries.remove(w)
            replaced.append(w.get("id"))
        if progress:
            progress("Copying addon folders…", None)
        old_dir = inst.get("addonsDir")
        new_dir = wow.find_addons_dir(target["flavorDir"])
        copied, kept, reinstall = [], [], []
        for a in mine:
            folders = [f for f in (a.get("installedFolderList") or []) if isinstance(f, str) and f] \
                or [f.strip() for f in str(a.get("installedFolders") or "").split(",") if f.strip()]
            complete = bool(folders)
            for f in folders:
                if os.path.basename(f) != f or f in (".", ".."):
                    complete = False
                    continue
                if os.path.isdir(new_dir) and wow.ci_child(new_dir, f):
                    kept.append(f)
                    continue
                src = wow.ci_child(old_dir, f) if old_dir and os.path.isdir(old_dir) else None
                if src and os.path.isdir(src):
                    os.makedirs(new_dir, exist_ok=True)
                    shutil.copytree(src, os.path.join(new_dir, f), symlinks=True)
                    copied.append(f)
                else:
                    complete = False
            if not complete:  # WowUp installs it again on the next update (same as a new placeholder)
                a["installedVersion"] = "0"
                a["installedExternalReleaseId"] = "0"
                reinstall.append(a.get("name") or addon_key(a))
        me = next(w for w in entries if w.get("id") == inst["id"])
        me["location"] = self._spell_like_existing(os.path.join(real, WOWUP_EXE_BY_CLIENT_TYPE[ct]),
                                                   [w for w in spellings if w is not me])
        if replaced and not any(w.get("selected") for w in entries):
            me["selected"] = True
        prefs["wow_installations"] = entries
        if reinstall:
            self.store.save_addons(addons)
        self.store.save_prefs(prefs)
        self._detected = (0.0, [])
        logger.info("moved WowUp installation %s from %s to %s (copied %s, reinstall %s, removed entries %s)",
                    inst["id"], inst["flavorDir"], me["location"], copied, reinstall, replaced)
        if progress:
            progress(f"{inst['label']} now uses {target['flavorDir']}", None)
        return {"installationId": inst["id"], "from": inst["flavorDir"], "to": os.path.dirname(me["location"]),
                "copied": copied, "kept": kept, "reinstall": reinstall, "removedEntries": replaced}

    @staticmethod
    def _spell_like_existing(path: str, entries: List[Dict[str, Any]]) -> str:
        """Reuse the prefix spelling of existing entries (e.g. ~/.steam/steam/... instead of the real path)."""
        real = os.path.realpath(os.path.dirname(path))
        for w in entries:
            loc = str(w.get("location") or "")
            if "/drive_c/" not in loc:
                continue
            spelled = loc.split("/drive_c/")[0] + "/drive_c"
            real_prefix = os.path.realpath(spelled)
            if real == real_prefix or real.startswith(real_prefix + "/"):
                return spelled + real[len(real_prefix):] + "/" + os.path.basename(path)
        return os.path.join(real, os.path.basename(path))

    def _dedupe_installations(self) -> int:
        prefs = self.store.load_prefs()
        lst = [w for w in prefs.get("wow_installations") or [] if isinstance(w, dict)]
        used = {a.get("installationId") for a in self.store.load_addons().values()}
        order = sorted(range(len(lst)), key=lambda i: (lst[i].get("id") not in used, i))
        seen, keep = set(), set()
        for i in order:
            loc = str(lst[i].get("location") or "")
            real = os.path.realpath(os.path.dirname(loc)) if loc else f"#{i}"
            if real not in seen:
                seen.add(real)
                keep.add(i)
        removed = len(lst) - len(keep)
        if removed:
            prefs["wow_installations"] = [lst[i] for i in range(len(lst)) if i in keep]
            if prefs["wow_installations"] and not any(w.get("selected") for w in prefs["wow_installations"]):
                prefs["wow_installations"][0]["selected"] = True
            self.store.save_prefs(prefs)
            logger.info("removed %d duplicate WowUp installation(s)", removed)
        return removed

    # ---------------------------------------------------------------- search and install
    def installation(self, installation_id: str) -> Dict[str, Any]:
        for inst in self.installations():
            if str(inst["id"]) == str(installation_id):
                return inst
        raise RuntimeError("this WoW version is not set up in WowUp-CF")

    def search_addons(self, installation_id: str, query: str = "", sort: str = "relevance") -> Dict[str, Any]:
        """WoWInterface + WowUp Hub; an empty query returns popular/featured addons."""
        inst = self.installation(installation_id)
        gtype, ctype = inst.get("gameType"), inst.get("clientType")
        q = (query or "").strip()
        sort = sort if sort in catalog.SORTS else "relevance"
        out: Dict[str, Any] = {"query": q, "sort": sort, "installationId": inst["id"], "gameType": gtype,
                               "wowinterface": [], "hub": [], "errors": []}
        try:
            out["wowinterface"] = catalog.search_wowi(q, gtype, sort=sort) if q else catalog.popular_wowi(gtype, sort=sort)
        except Exception as e:
            out["errors"].append(f"WoWInterface: {e}")
        try:
            out["hub"] = catalog.search_hub(q, ctype, sort=sort) if q else catalog.featured_hub(ctype, sort=sort)
        except Exception as e:
            out["errors"].append(f"WowUp Hub: {e}")
        records = [a for a in self.store.load_addons().values() if a.get("installationId") == inst["id"]]
        known = {(a.get("providerName"), str(a.get("externalId"))) for a in records}
        d = inst.get("addonsDir")
        present = {e.lower() for e in os.listdir(d)} if d and os.path.isdir(d) else set()
        for r in out["wowinterface"] + out["hub"]:
            r["installed"] = (r["provider"], r["externalId"]) in known
            r["present"] = not r["installed"] and bool(r["folders"]) and all(f.lower() in present for f in r["folders"])
            # listed versions but none loadable here (e.g. retail 8.3 only) -> not compatible; no data -> unknown
            listed = r["gameTypes"] or r.get("compatVersions")
            r["compatible"] = (gtype in r["gameTypes"]) if gtype and listed else None
        return out

    def install_addons(self, installation_id: str, items: List[Dict[str, Any]], progress: Progress = None) -> Dict[str, Any]:
        """Install addons through WowUp-CF: placeholder records, then a run for exactly those.
        Required CurseForge dependencies are added in up to two further passes."""
        if is_running():
            raise RuntimeError("WowUp-CF is running – close it first")
        inst = self.installation(installation_id)
        if not self.has_game(inst):
            raise RuntimeError(f"{inst['label']}: no WoW installation in {inst['flavorDir']} – "
                               f"move it to the real WoW folder first")
        wi = next((w for w in self.store.load_prefs().get("wow_installations") or []
                   if isinstance(w, dict) and w.get("id") == inst["id"]), {})
        auto = wi.get("defaultAutoUpdate", True) is not False
        try:
            channel = int(wi.get("defaultAddonChannelType") or 0)
        except (TypeError, ValueError):
            channel = 0
        result: Dict[str, Any] = {"installed": [], "failed": [], "skipped": [], "runs": []}
        pending = [(str(i.get("provider") or ""), str(i.get("externalId") or "").strip(), str(i.get("name") or ""))
                   for i in items]
        tried = set()
        for attempt in range(3):
            addons = self.store.load_addons()
            known = {(a.get("providerName"), str(a.get("externalId")))
                     for a in addons.values() if a.get("installationId") == inst["id"]}
            created = []
            for provider, ext, name in pending:
                item = {"provider": provider, "externalId": ext, "name": name}
                if provider not in PROVIDERS or not VALID_EXTERNAL_ID.match(ext):
                    result["failed"].append(dict(item, reason="invalid id"))
                    continue
                if (provider, ext) in known or (provider, ext) in tried:
                    if attempt == 0:
                        result["skipped"].append(dict(item, reason="already installed"))
                    continue
                tried.add((provider, ext))
                rec = placeholder(inst["id"], inst.get("clientType"), provider, ext, name, auto, channel)
                addons[rec["id"]] = rec
                created.append(rec["id"])
            if not created:
                break
            self.store.save_addons(addons)
            if progress:
                progress(f"Installing {len(created)} addon(s) with WowUp-CF…", None)
            res = self.run_update("selected", inst["id"], [addon_key(addons[r]) for r in created], progress)
            result["runs"].append(brief(res))
            after = self.store.load_addons()
            pending = []
            removed = False
            for rid in created:
                a = after.get(rid) or addons[rid]
                entry = {"provider": a.get("providerName"), "externalId": a.get("externalId"),
                         "name": a.get("name") or "", "version": a.get("installedVersion")}
                if a.get("installedFolderList") and str(a.get("installedVersion") or "") not in ("", "0"):
                    result["installed"].append(entry)
                    if a.get("providerName") == "Curse":
                        for dep in a.get("dependencies") or []:
                            if isinstance(dep, dict) and str(dep.get("type")) == str(DEPENDENCY_REQUIRED) \
                                    and dep.get("externalAddonId"):
                                pending.append(("Curse", str(dep["externalAddonId"]), ""))
                else:
                    result["failed"].append(dict(entry, reason="not available for this WoW version or unknown id"))
                    after.pop(rid, None)
                    removed = True
            if removed:  # no ghost records for addons WowUp could not install
                self.store.save_addons(after)
            if not pending:
                break
        return result

    # ---------------------------------------------------------------- maintenance
    def recover(self) -> Optional[Dict[str, Any]]:
        try:
            return wowup_runner.recover(self.store)
        except Exception as e:
            logger.error("journal recovery failed: %s", e)
            return None

    def selftest(self, config_home: str, progress: Progress = None) -> Dict[str, Any]:
        """Check-only run against a sandbox XDG_CONFIG_HOME (development: proves the headless run
        works from the Decky backend without touching the real profile)."""
        app = self.appimage()
        if not app:
            raise RuntimeError("WowUp-CF is not installed")
        env = wowup_runner.build_env(config_home)
        logger.info("selftest env: uid=%s XDG_RUNTIME_DIR=%s exists=%s gamescope=%s LD_LIBRARY_PATH(parent)=%s",
                    os.getuid(), env.get("XDG_RUNTIME_DIR"), os.path.isdir(env.get("XDG_RUNTIME_DIR", "")),
                    util.which("gamescope"), bool(os.environ.get("LD_LIBRARY_PATH")))
        store = WowUpStore(os.path.join(config_home, WOWUP_CONFIG_NAME))
        res = wowup_runner.run(store, app, "check", timeout=settings_mod.timeout_s(self.settings),
                               config_home=config_home, journal_path=os.path.join(paths.TMP_DIR, "selftest-journal.json"),
                               on_progress=progress)
        logger.info("selftest result: ok=%s rc=%s quit=%s %sms errors=%s", res["ok"], res["rc"], res["quit"],
                    res["durationMs"], res["errors"][:3])
        return brief(res) or {}

    def diagnostics(self) -> str:
        st = self.state(refresh=True)
        w = st["wowup"]
        lines = [f"plugin dir: {paths.PLUGIN_DIR}", f"data dir: {paths.RUNTIME_DIR}",
                 f"WowUp-CF: {w['version']} at {w['path']} (verified={w['verified']}, channel={w['channel']}, "
                 f"running={w['running']}, profile={w['profileExists']}, latest={w['latestVersion']})"]
        for i in st["installations"]:
            lines.append(f"installation {i['label']} [{i['clientTypeLabel']}] {i.get('gameTypeLabel')} {i.get('version')}"
                         f" – {i['addonCount']} addons, {i['updateCount']} updates, {i['incompatibleCount']} incompatible,"
                         f" unmanaged: {', '.join(i['unmanaged']) or '-'}")
        for d in st["missingInWowUp"]:
            lines.append(f"not in WowUp: {d['product']} {d['subfolder']} {d.get('version')}")
        if st["lastRun"]:
            r = st["lastRun"]
            lines.append(f"last run {r['runId']} {r['mode']}: ok={r['ok']} rc={r['rc']} {r['durationMs']}ms"
                         f" updated={len(r.get('updated') or [])} errors={r.get('errors')}")
        lines += [f"warning: {x}" for x in st["warnings"]]
        return "\n".join(lines)
