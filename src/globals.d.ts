// Decky's backend router; SteamClient, appStore and SteamUIStore come from @decky/ui.
interface Window {
  DeckyBackend?: {
    callable: <T extends any[] = any[], R = any>(route: string) => (...args: T) => Promise<R>;
    addEventListener?: (event: string, listener: (...args: any[]) => any) => void;
    removeEventListener?: (event: string, listener: (...args: any[]) => any) => void;
  };
}
