import { Navigation, SidebarNavigation } from "@decky/ui";
import { useState } from "react";
import { FaBoxOpen, FaDownload, FaInfoCircle, FaLayerGroup, FaPuzzlePiece, FaUndo } from "react-icons/fa";
import { setUi } from "../backend";
import { hintStyle, PageBody } from "../components/FullPage";
import { usePluginState } from "../hooks/usePluginState";
import { t } from "../strings";
import type { Installation, PluginState } from "../types";
import { GetAddonsPage } from "./GetAddonsPage";
import { InstalledPage } from "./InstalledPage";
import { NotesPage } from "./NotesPage";
import { UndoPage } from "./UndoPage";
import { VersionsPage } from "./VersionsPage";
import { WowupPage } from "./WowupPage";

/** Registered without `exact`: every page below has its own route, like Decky's settings. */
export const MAIN_ROUTE = "/wow-addons";
export type PageId = "installed" | "get" | "versions" | "undo" | "wowup" | "notes";

export function pageRoute(page: PageId): string {
  return `${MAIN_ROUTE}/${page}`;
}

/** Open the full-screen view from the Quick Access menu. */
export function openMainView(page: PageId = "installed"): void {
  Navigation.Navigate(pageRoute(page));
  Navigation.CloseSideMenus();
}

export interface PageProps {
  state: PluginState;
  refresh: (full?: boolean) => Promise<void>;
  /** WoW version shown on "Installed" and targeted by "Get addons" (shared, remembered in settings) */
  inst: Installation | undefined;
  selectInstallation: (id: string) => void;
  openPage: (page: PageId) => void;
}

export function MainView() {
  const { state, error, refresh } = usePluginState();
  const [instId, setInstId] = useState<string | null>(null);

  if (!state) {
    return (
      <div style={{ marginTop: "60px", padding: "0 28px" }}>
        <PageBody>
          <div style={hintStyle}>{error ?? t.loading}</div>
        </PageBody>
      </div>
    );
  }

  const insts = state.installations;
  const inst = insts.find((i) => i.id === (instId ?? state.settings.ui.installationId))
    ?? insts.find((i) => i.selected) ?? insts[0];
  const props: PageProps = {
    state, refresh, inst,
    selectInstallation: (id) => { setInstId(id); void setUi({ installationId: id }); },
    openPage: (page) => Navigation.Navigate(pageRoute(page)),
  };
  const updates = insts.reduce((n, i) => n + i.updateCount, 0);

  return (
    <SidebarNavigation title={t.title} showTitle pages={[
      { title: updates ? `${t.pages.installed} (${updates})` : t.pages.installed, icon: <FaPuzzlePiece />,
        route: pageRoute("installed"), content: <InstalledPage {...props} /> },
      { title: t.pages.get, icon: <FaDownload />, route: pageRoute("get"), content: <GetAddonsPage {...props} /> },
      { title: t.pages.versions, icon: <FaLayerGroup />, route: pageRoute("versions"), content: <VersionsPage {...props} /> },
      { title: t.pages.undo, icon: <FaUndo />, route: pageRoute("undo"), content: <UndoPage {...props} /> },
      // no "separator" entry: SidebarNavigation then highlights the entry below the current route
      { title: t.pages.wowup, icon: <FaBoxOpen />, route: pageRoute("wowup"), content: <WowupPage {...props} /> },
      { title: state.warnings.length ? `${t.pages.notes} (${state.warnings.length})` : t.pages.notes, icon: <FaInfoCircle />,
        route: pageRoute("notes"), content: <NotesPage {...props} /> },
    ]} />
  );
}
