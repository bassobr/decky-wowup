import { callable } from "@decky/api";
import type {
  InstallItem, JobStart, PluginState, RunMode, SearchResponse, Settings, UpdateArtifact, UpdateInfo, WowUpInfo,
} from "./types";

export const getState = callable<[refresh: boolean], PluginState>("get_state");
export const setUi = callable<[prefs: Partial<Settings["ui"]>], Settings["ui"]>("set_ui");
export const runUpdate = callable<[mode: RunMode, installationId: string | null, selection: string[] | null], JobStart>("run_update");
export const searchAddons = callable<[installationId: string, query: string], SearchResponse>("search_addons");
export const installAddons = callable<[installationId: string, items: InstallItem[]], JobStart>("install_addons");
export const importInstallations = callable<[], JobStart>("import_installations");
export const restoreSnapshot = callable<[snapshotId: string, keys: string[] | null], JobStart>("restore_snapshot");
export const installWowup = callable<[channel: string | null], JobStart>("install_wowup");
export const adoptWowup = callable<[path: string], { path: string; version: string; verified: boolean | null }>("adopt_wowup");
export const checkWowupUpdate = callable<[force: boolean], WowUpInfo>("check_wowup_update");
export const applyWowupUpdate = callable<[], JobStart>("apply_wowup_update");
export const onAppEvent = callable<[appId: string, running: boolean, name: string | null], unknown>("on_app_event");
export const checkForUpdate = callable<[force: boolean], UpdateInfo>("check_for_update");
export const prepareUpdate = callable<[], UpdateArtifact>("prepare_update");
export const setUpdatePrefs = callable<[prefs: { autoRestartSteam?: boolean; autoCheck?: boolean }], Settings["update"]>("set_update_prefs");
export const getDiagnostics = callable<[], { text: string }>("get_diagnostics");

/** Hand the verified release to Decky Loader's installer. */
export async function installViaDecky(a: UpdateArtifact): Promise<void> {
  const backend = window.DeckyBackend;
  if (!backend?.callable) throw new Error("Decky install API not available");
  const install = backend.callable<[string, string, string, string, number], void>("utilities/install_plugin");
  // InstallType.UPDATE = 2 (decky-loader frontend enum)
  await install(a.artifact, a.name, a.version, a.hash, 2);
}
