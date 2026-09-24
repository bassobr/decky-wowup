"""Orchestration shared by main.py (Decky) and cli.py: state, runs, WowUp provisioning, snapshots."""
from __future__ import annotations

import os
import re
import time
from typing import Any, Callable, Dict, List, Optional

from . import catalog, paths, snapshots, toc, util, wow, wowup_app, wowup_runner
from . import settings as settings_mod
from .constants import DISCOVERY_CACHE_S, GAME_TYPE_LABELS, SNAPSHOT_KEEP, WOWUP_CHECK_INTERVAL_S, WOWUP_CONFIG_NAME
from .log import logger
from .wowup_store import (CHANNELS, PROVIDERS, WowUpStore, addon_key, is_running, needs_update, placeholder,
                          release_channel)

Progress = Optional[Callable[[str, Optional[float]], None]]

# WowUp record fields that describe the installed version; saved with each snapshot for rollback.
RESTORE_FIELDS = ("installedVersion", "installedExternalReleaseId", "installedAt", "installedFolders",
                  "installedFolderList", "gameVersion")
VALID_EXTERNAL_ID = re.compile(r"^\d{1,12}$")
DEPENDENCY_REQUIRED = 2  # WowUp AddonDependencyType: 1 embedded, 2 required, 3 optional, 4 other
RUN_SUMMARY_KEYS = ("runId", "mode", "installationId", "ok", "rc", "timedOut", "durationMs", "quit", "updated",
                    "errors", "pending", "startedAt", "finishedAt", "snapshots")


def brief(res: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return {k: res.get(k) for k in RUN_SUMMARY_KEYS} if res else None


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

    # ---------------------------------------------------------------- discovery
    def detected(self, refresh: bool = False) -> List[Dict[str, Any]]:
        ts, data = self._detected
        if refresh or not ts or time.monotonic() - ts > DISCOVERY_CACHE_S:
            try:
                data = wow.discover()
            except Exception as e:
                logger.error("discovery failed: %s", e)
                data = []
            self._detected = (time.monotonic(), data)
        return data

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
        """Fresh profile: only point WowUp at Battle.net's product.db; it imports all flavors itself (V11)."""
        if self.store.exists():
            return False
        det = self.detected(refresh=True)
        if not det:
            return False
        os.makedirs(self.store.dir, exist_ok=True)
        self.store.save_prefs({"blizzard_agent_path": det[0]["productDb"]})
        return True

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
                         "gameTypeLabel": GAME_TYPE_LABELS.get(gtype or "", gtype), "interface": iface})
            out.append(inst)
        return out

    def addons(self, inst: Dict[str, Any], records: Optional[Dict[str, Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        records = self.store.load_addons() if records is None else records
        addons_dir = inst.get("addonsDir")
        out = []
        for a in sorted((r for r in records.values() if r.get("installationId") == inst["id"]),
                        key=lambda r: str(r.get("name") or "").lower()):
            folders = [f for f in (a.get("installedFolderList") or []) if isinstance(f, str) and f]
            if not folders and a.get("installedFolders"):
                folders = [f.strip() for f in str(a["installedFolders"]).split(",") if f.strip()]
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
            })
        return out

    @staticmethod
    def unmanaged(inst: Dict[str, Any], addons: List[Dict[str, Any]]) -> List[str]:
        d = inst.get("addonsDir")
        if not d or not os.path.isdir(d):
            return []
        claimed = {f.lower() for a in addons for f in a["folders"]}
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
        for inst in insts:
            lst = self.addons(inst, records)
            inst["addonCount"] = len(lst)
            inst["updateCount"] = sum(1 for a in lst if a["needsUpdate"])
            inst["incompatibleCount"] = sum(1 for a in lst if a["compat"] == "incompatible")
            inst["unmanaged"] = self.unmanaged(inst, lst)
            for group in case_duplicates(inst.get("addonsDir")):
                warnings.append(f"{inst['label']}: folders differ only in case: {', '.join(group)}")
            if not inst["exists"]:
                warnings.append(f"{inst['label']}: folder not found ({inst['flavorDir']})")
            per[str(inst["id"])] = lst
        if wowup["running"]:
            warnings.append("WowUp-CF is running – updates are possible once it is closed.")
        if os.path.exists(paths.JOURNAL_FILE):
            warnings.append("An interrupted update run will be repaired automatically.")
        last = util.read_json(paths.STATE_FILE, {}) or {}
        return {"wowup": wowup, "installations": insts, "addons": per, "detected": detected,
                "missingInWowUp": missing, "lastRun": last.get("lastRun"),
                "snapshots": [{k: m.get(k) for k in ("id", "installationId", "installationLabel", "label", "createdAt",
                                                     "method")} for m in snapshots.list_snapshots()[:10]],
                "warnings": warnings}

    # ---------------------------------------------------------------- runs
    def run_update(self, mode: str, installation_id: Optional[str] = None, selection: Optional[List[str]] = None,
                   progress: Progress = None) -> Dict[str, Any]:
        app = self.appimage()
        if not app:
            raise RuntimeError("WowUp-CF is not installed")
        snaps: List[str] = []
        if mode != "check":
            records = self.store.load_addons()
            keep = int(self.settings["snapshots"].get("keep") or SNAPSHOT_KEEP)
            for inst in self.installations():
                if installation_id not in (None, inst["id"]) or not inst.get("addonsDir") \
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

    def import_installations(self, progress: Progress = None) -> Dict[str, Any]:
        """Let WowUp import every flavor from Battle.net's product.db (blizzard_agent_path)."""
        if is_running():
            raise RuntimeError("WowUp-CF is running – close it first")
        det = self.detected(refresh=True)
        if not det:
            raise RuntimeError("no WoW installation found in a Proton prefix")
        counts: Dict[str, int] = {}
        for d in det:
            counts[d["productDb"]] = counts.get(d["productDb"], 0) + 1
        pdb = max(counts, key=lambda k: counts[k])
        before = {i["id"] for i in self.store.installations()}
        prefs = self.store.load_prefs()
        prefs["blizzard_agent_path"] = self._agent_path_like_existing(pdb, prefs)
        self.store.save_prefs(prefs)
        run = self.run_update("check", progress=progress)
        removed = self._dedupe_installations()
        added = [i for i in self.store.installations() if i["id"] not in before]
        return {"added": added, "removedDuplicates": removed, "agentPath": prefs["blizzard_agent_path"],
                "run": brief(run)}

    @staticmethod
    def _agent_path_like_existing(pdb: str, prefs: Dict[str, Any]) -> str:
        """WowUp derives install paths from the agent path and matches them as strings; reuse the path
        spelling of existing installations (e.g. ~/.steam/steam/...) so no duplicates appear."""
        real_drive = os.path.realpath(pdb).split("/drive_c/")[0] + "/drive_c/"
        for wi in prefs.get("wow_installations") or []:
            loc = str(wi.get("location") or "")
            if "/drive_c/" in loc:
                spelled = loc.split("/drive_c/")[0] + "/drive_c/"
                if os.path.realpath(spelled) + "/" == real_drive or os.path.realpath(spelled) == real_drive.rstrip("/"):
                    return spelled + "ProgramData/Battle.net/Agent/product.db"
        return pdb

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

    def search_addons(self, installation_id: str, query: str = "") -> Dict[str, Any]:
        """WoWInterface + WowUp Hub; an empty query returns popular/featured addons."""
        inst = self.installation(installation_id)
        gtype, ctype = inst.get("gameType"), inst.get("clientType")
        q = (query or "").strip()
        out: Dict[str, Any] = {"query": q, "installationId": inst["id"], "gameType": gtype,
                               "wowinterface": [], "hub": [], "errors": []}
        try:
            out["wowinterface"] = catalog.search_wowi(q, gtype) if q else catalog.popular_wowi(gtype)
        except Exception as e:
            out["errors"].append(f"WoWInterface: {e}")
        try:
            out["hub"] = catalog.search_hub(q, ctype) if q else catalog.featured_hub(ctype)
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
