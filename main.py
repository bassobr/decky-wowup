"""Decky Loader entry point; async facade over py_modules/wowaddons."""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import time
from typing import Any, Callable, Dict, List, Optional

import decky  # type: ignore

sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), "py_modules"))

from wowaddons import paths, settings, updater, util  # noqa: E402
from wowaddons.service import Service  # noqa: E402
from wowaddons.wowup_runner import MODES  # noqa: E402

MAX_APP_EVENTS = 20


class Plugin:
    # ---------------------------------------------------------------- lifecycle
    async def _main(self):
        self.loop = asyncio.get_event_loop()
        paths.ensure_dirs()
        self.settings: Dict[str, Any] = settings.load()
        self.service = Service(self.settings, self._save)
        self.job: Optional[Dict[str, Any]] = None
        self.job_task: Optional[asyncio.Task] = None
        self.app_events: List[Dict[str, Any]] = []
        self.loop.create_task(self._startup())
        decky.logger.info("WoW Addons backend started (plugin dir %s)", paths.PLUGIN_DIR)

    async def _unload(self):
        # A running WowUp process keeps going in its own session; the journal repairs flags on next start.
        if self.job_task and not self.job_task.done():
            self.job_task.cancel()
        decky.logger.info("WoW Addons backend unloaded")

    async def _uninstall(self):
        # Decky also calls this while replacing the plugin during an update.
        if updater.update_in_progress():
            decky.logger.info("update in progress: keeping runtime data")
            return
        shutil.rmtree(paths.RUNTIME_DIR, ignore_errors=True)
        decky.logger.info("uninstalled: runtime data (snapshots, logs) deleted; WowUp-CF is left untouched")

    async def _startup(self):
        try:
            rec = await asyncio.to_thread(self.service.recover)
            if rec:
                decky.logger.info("recovered interrupted run %s: %s", rec.get("runId"), rec)
            if updater.update_in_progress():
                updater.clear_update_marker()
                await decky.emit("update_installed", {"version": decky.DECKY_PLUGIN_VERSION,
                                                      "autoRestart": bool(self.settings["update"].get("autoRestartSteam", True))})
            adopted = await asyncio.to_thread(self.service.auto_adopt)
            if adopted:
                decky.logger.info("adopted existing WowUp-CF AppImage: %s", adopted)
            if self.settings["update"].get("autoCheck", True):
                await self.check_for_update(False)
            if self.settings["wowup"].get("autoCheck", True):
                await asyncio.to_thread(self.service.check_wowup_update, False)
            sandbox = (self.settings.get("dev") or {}).get("selftestConfigHome")
            if sandbox:
                self.settings["dev"]["selftestConfigHome"] = None
                self._save()
                await self._start_job("selftest", lambda p: self.service.selftest(sandbox, p))
            await decky.emit("state_changed", {})
        except Exception as e:
            decky.logger.error("startup failed: %s", e)

    # ---------------------------------------------------------------- helpers
    def _save(self) -> None:
        settings.save(self.settings)

    def _emit_threadsafe(self, event: str, payload: Any) -> None:
        self.loop.call_soon_threadsafe(lambda: self.loop.create_task(decky.emit(event, payload)))

    def _busy(self) -> bool:
        return bool(self.job_task and not self.job_task.done())

    async def _start_job(self, kind: str, fn: Callable[[Callable[[str, Optional[float]], None]], Any]) -> Dict[str, Any]:
        """One writing job at a time; progress and the result arrive as 'job' events and via get_state."""
        if self._busy():
            return {"started": False, "reason": "busy", "job": dict(self.job or {})}
        job: Dict[str, Any] = {"id": f"{int(time.time() * 1000)}", "kind": kind, "status": "running",
                               "message": "", "percent": None, "result": None, "error": None,
                               "startedAt": util.now_iso(), "finishedAt": None}
        self.job = job

        def progress(message: str, percent: Optional[float] = None) -> None:
            job["message"], job["percent"] = message, percent
            self._emit_threadsafe("job", dict(job))

        async def runner():
            try:
                job["result"] = await asyncio.to_thread(fn, progress)
                job["status"] = "done"
            except asyncio.CancelledError:
                job["status"], job["error"] = "error", "cancelled"
                raise
            except Exception as e:
                decky.logger.error("%s failed: %s", kind, e)
                job["status"], job["error"] = "error", str(e)
            finally:
                job["finishedAt"] = util.now_iso()
                job["message"] = ""
            await decky.emit("job", dict(job))
            await decky.emit("state_changed", {})

        self.job_task = self.loop.create_task(runner())
        await decky.emit("job", dict(job))
        return {"started": True, "job": dict(job)}

    def _update_info(self) -> Dict[str, Any]:
        if self.settings["update"].get("latest"):
            return updater.check(self.settings["update"], decky.DECKY_PLUGIN_VERSION, force=False)
        return {"currentVersion": decky.DECKY_PLUGIN_VERSION, "updateAvailable": False, "latestVersion": None,
                "error": self.settings["update"].get("error")}

    # ---------------------------------------------------------------- state
    async def get_state(self, refresh: bool = False) -> Dict[str, Any]:
        st = await asyncio.to_thread(self.service.state, bool(refresh))
        st.update({"version": decky.DECKY_PLUGIN_VERSION, "job": self.job, "settings": self.settings,
                   "update": self._update_info(), "appEvents": self.app_events[-5:]})
        return st

    async def set_ui(self, prefs: Dict[str, Any]) -> Dict[str, Any]:
        if "installationId" in prefs:
            self.settings["ui"]["installationId"] = str(prefs["installationId"]) if prefs["installationId"] else None
        if "wowupShortcutAppId" in prefs:
            v = prefs["wowupShortcutAppId"]
            self.settings["ui"]["wowupShortcutAppId"] = int(v) if isinstance(v, (int, float)) and v > 0 else None
        if "wowupShortcutExe" in prefs:
            self.settings["ui"]["wowupShortcutExe"] = str(prefs["wowupShortcutExe"])[:500] if prefs["wowupShortcutExe"] else None
        self._save()
        return dict(self.settings["ui"])

    # ---------------------------------------------------------------- addon runs
    async def run_update(self, mode: str, installation_id: Optional[str] = None,
                         selection: Optional[List[str]] = None) -> Dict[str, Any]:
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}")
        sel = [str(k) for k in selection] if selection else None
        return await self._start_job("run", lambda p: self.service.run_update(mode, installation_id or None, sel, p))

    async def search_addons(self, installation_id: str, query: str = "") -> Dict[str, Any]:
        return await asyncio.to_thread(self.service.search_addons, str(installation_id), str(query or "")[:100])

    async def install_addons(self, installation_id: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        clean = [{"provider": str(i.get("provider") or ""), "externalId": str(i.get("externalId") or ""),
                  "name": str(i.get("name") or "")[:120]} for i in (items or []) if isinstance(i, dict)][:20]
        if not clean:
            raise ValueError("nothing to install")
        return await self._start_job("install", lambda p: self.service.install_addons(str(installation_id), clean, p))

    async def import_installations(self) -> Dict[str, Any]:
        return await self._start_job("versions", lambda p: self.service.add_installations(None, p))

    async def add_installations(self, flavor_dirs: Optional[List[str]] = None) -> Dict[str, Any]:
        dirs = [str(d) for d in flavor_dirs][:50] if flavor_dirs else None
        return await self._start_job("versions", lambda p: self.service.add_installations(dirs, p))

    async def add_installation_path(self, path: str) -> Dict[str, Any]:
        return await self._start_job("versions", lambda p: self.service.add_installation_path(str(path), p))

    async def relocate_installation(self, installation_id: str, flavor_dir: str) -> Dict[str, Any]:
        return await self._start_job("versions", lambda p: self.service.relocate_installation(
            str(installation_id), str(flavor_dir), p))

    async def set_discovery(self, prefs: Dict[str, Any]) -> Dict[str, Any]:
        res = await asyncio.to_thread(self.service.set_discovery, dict(prefs or {}))
        await decky.emit("state_changed", {})
        return res

    async def restore_snapshot(self, snapshot_id: str, keys: Optional[List[str]] = None) -> Dict[str, Any]:
        k = [str(x) for x in keys] if keys else None
        return await self._start_job("restore", lambda p: self.service.restore_snapshot(str(snapshot_id), k, p))

    # ---------------------------------------------------------------- WowUp-CF AppImage
    async def install_wowup(self, channel: Optional[str] = None) -> Dict[str, Any]:
        return await self._start_job("wowup_install", lambda p: self.service.install_wowup(p, channel))

    async def adopt_wowup(self, path: str) -> Dict[str, Any]:
        res = await asyncio.to_thread(self.service.adopt, str(path), True)
        await decky.emit("state_changed", {})
        return res

    async def check_wowup_update(self, force: bool = False) -> Dict[str, Any]:
        res = await asyncio.to_thread(self.service.check_wowup_update, bool(force))
        await decky.emit("state_changed", {})
        return res

    async def apply_wowup_update(self) -> Dict[str, Any]:
        return await self._start_job("wowup_update", lambda p: self.service.apply_wowup_update(p))

    # ---------------------------------------------------------------- Steam app lifetime (diagnostics for now)
    async def on_app_event(self, app_id: str, running: bool, name: Optional[str] = None) -> Dict[str, Any]:
        ev = {"appId": str(app_id), "running": bool(running), "name": (name or "")[:80], "at": util.now_iso()}
        self.app_events = (self.app_events + [ev])[-MAX_APP_EVENTS:]
        decky.logger.info("app event: %s", ev)
        if not ev["running"]:  # e.g. WowUp-CF's own window was closed: addons.json may have changed
            await decky.emit("state_changed", {})
        return ev

    # ---------------------------------------------------------------- plugin updates
    async def check_for_update(self, force: bool = False) -> Dict[str, Any]:
        res = await asyncio.to_thread(updater.check, self.settings["update"], decky.DECKY_PLUGIN_VERSION, bool(force))
        self._save()
        await decky.emit("update_state", res)
        return res

    async def set_update_prefs(self, prefs: Dict[str, Any]) -> Dict[str, Any]:
        for key in ("autoRestartSteam", "autoCheck"):
            if key in prefs:
                self.settings["update"][key] = bool(prefs[key])
        self._save()
        return dict(self.settings["update"])

    async def prepare_update(self) -> Dict[str, Any]:
        latest = self.settings["update"].get("latest")
        if not latest:
            latest = await asyncio.to_thread(updater.fetch_latest)
            self.settings["update"]["latest"] = latest
            self._save()
        info = await asyncio.to_thread(updater.verify_release, latest)
        updater.mark_update_pending()
        return info

    # ---------------------------------------------------------------- diagnostics
    async def get_diagnostics(self) -> Dict[str, Any]:
        text = await asyncio.to_thread(self.service.diagnostics)
        try:
            os.makedirs(paths.LOG_DIR, exist_ok=True)
            with open(os.path.join(paths.LOG_DIR, "diagnostics.txt"), "w", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError:
            pass
        return {"text": text}
