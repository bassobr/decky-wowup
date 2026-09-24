import { onAppEvent } from "./backend";

let unregister: (() => void) | null = null;

function appName(appId: number): string | null {
  try {
    return (globalThis as any).appStore?.GetAppOverviewByAppID?.(appId)?.display_name ?? null;
  } catch {
    return null;
  }
}

/** Reports app start/stop to the backend. For now only logged: it answers which id Steam
 *  reports for the Battle.net shortcut (sources disagree), the basis for "update on launch". */
export function startAppWatcher(): void {
  try {
    const reg = (globalThis as any).SteamClient?.GameSessions?.RegisterForAppLifetimeNotifications?.(
      (e: { unAppID: number; nInstanceID?: number; bRunning: boolean }) => {
        const main = (globalThis as any).SteamUIStore?.MainRunningAppID;
        const id = e?.unAppID || (typeof main === "number" ? main : 0);
        onAppEvent(String(id), !!e?.bRunning, appName(id) ?? `unAppID=${e?.unAppID} main=${main}`).catch(() => undefined);
      },
    );
    unregister = reg?.unregister ? () => reg.unregister() : null;
  } catch {
    unregister = null;
  }
}

export function stopAppWatcher(): void {
  try {
    unregister?.();
  } catch {
    /* ignore */
  }
  unregister = null;
}
