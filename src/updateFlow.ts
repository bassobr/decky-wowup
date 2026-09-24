import { addEventListener, toaster } from "@decky/api";
import { t } from "./strings";
import { FRONTEND_VERSION } from "./version";

const PLUGIN_NAME = "WoW Addons";
const ARM_TIMEOUT_MS = 15 * 60 * 1000;
let restartScheduled = false;

export function restartSteam(): void {
  if (restartScheduled) return;
  restartScheduled = true;
  toaster.toast({ title: t.title, body: t.restartingSteam });
  window.setTimeout(() => {
    try {
      (globalThis as any).SteamClient.User.StartRestart(false);
    } catch {
      restartScheduled = false;
    }
  }, 1500);
}

/** Restart Steam once the new backend reports itself after an in-app update. */
export function initUpdateFlow(): void {
  addEventListener<[{ version: string; autoRestart: boolean }]>("update_installed", (info) => {
    if (info?.autoRestart && info.version && info.version !== FRONTEND_VERSION) restartSteam();
  });
}

/** Also react to Decky's own install-finished event for our plugin. */
export function armRestartAfterInstall(newVersion: string, autoRestart: boolean): void {
  if (!autoRestart || newVersion === FRONTEND_VERSION) return;
  const backend = window.DeckyBackend as any;
  if (!backend?.addEventListener) return;
  const onFinish = (name: string) => {
    if (name !== PLUGIN_NAME) return;
    cleanup();
    restartSteam();
  };
  const cleanup = () => {
    try {
      backend.removeEventListener?.("loader/plugin_download_finish", onFinish);
    } catch {
      /* ignore */
    }
  };
  backend.addEventListener("loader/plugin_download_finish", onFinish);
  window.setTimeout(cleanup, ARM_TIMEOUT_MS);
}
