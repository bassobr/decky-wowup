// Non-Steam shortcut for opening WowUp-CF's own window in Game Mode (CurseForge search needs it:
// without an own API key the plugin cannot search CurseForge). Follows MoonDeck's handling:
// AddShortcut no longer sets the name, and a shortcut without app overview is removed again,
// because duplicate/incomplete shortcuts confuse Steam.

import { toaster } from "@decky/api";
import { setUi } from "../backend";
import { t } from "../strings";
import type { PluginState } from "../types";

const NAME = "WowUp-CF";

function apps(): any {
  return (globalThis as any).SteamClient?.Apps;
}

function overview(appId: number): any {
  try {
    return (globalThis as any).appStore?.GetAppOverviewByAppID?.(appId) ?? null;
  } catch {
    return null;
  }
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitForOverview(appId: number, tries = 20): Promise<any> {
  for (let i = 0; i < tries; i++) {
    const ov = overview(appId);
    if (ov) return ov;
    await sleep(250);
  }
  return null;
}

/** Existing shortcut for `exe`, or a new one; returns its app id. */
export async function ensureWowupShortcut(exe: string, knownAppId: number | null, knownExe: string | null): Promise<number> {
  const a = apps();
  if (!a?.AddShortcut) throw new Error("Steam's shortcut API is not available");
  if (knownAppId && overview(knownAppId)) {
    if (knownExe === exe) return knownAppId;
    try {
      a.RemoveShortcut(knownAppId); // AppImage moved (e.g. into ~/Applications/WowUp-CF after an update)
    } catch {
      /* ignore */
    }
  }
  const appId: number = await a.AddShortcut(NAME, exe, "", "");
  if (typeof appId !== "number" || !(await waitForOverview(appId))) {
    try {
      if (typeof appId === "number") a.RemoveShortcut(appId);
    } catch {
      /* ignore */
    }
    throw new Error("Steam did not create the WowUp-CF shortcut");
  }
  try {
    a.SetShortcutName(appId, NAME);
  } catch {
    /* name stays derived from the file name */
  }
  return appId;
}

export async function launchShortcut(appId: number): Promise<void> {
  const gameId = (await waitForOverview(appId))?.m_gameid;
  if (!gameId) throw new Error("the WowUp-CF shortcut has no game id");
  apps().RunGame(String(gameId), "", -1, 100);
}

export function terminateShortcut(appId: number | null): boolean {
  const gameId = appId ? overview(appId)?.m_gameid : null;
  if (!gameId) return false;
  try {
    apps().TerminateApp(String(gameId), false);
    return true;
  } catch {
    return false;
  }
}

/** Open WowUp-CF's window from the plugin state (creates or updates the shortcut first). */
export async function openWowupWindow(state: PluginState): Promise<void> {
  if (!state.wowup.path) return;
  try {
    const ui = state.settings.ui;
    const appId = await ensureWowupShortcut(state.wowup.path, ui.wowupShortcutAppId, ui.wowupShortcutExe ?? null);
    await setUi({ wowupShortcutAppId: appId, wowupShortcutExe: state.wowup.path });
    await launchShortcut(appId);
  } catch (e) {
    toaster.toast({ title: t.title, body: String(e) });
  }
}

export function closeWowupWindow(state: PluginState): void {
  if (!terminateShortcut(state.settings.ui.wowupShortcutAppId)) toaster.toast({ title: t.title, body: t.openWowupHint });
}
