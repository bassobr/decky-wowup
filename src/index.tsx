import { definePlugin, routerHook } from "@decky/api";
import { staticClasses } from "@decky/ui";
import { FaPuzzlePiece } from "react-icons/fa";
import { startAppWatcher, stopAppWatcher } from "./appWatcher";
import { QuickAccess } from "./components/QuickAccess";
import { GET_ADDONS_ROUTE, GetAddonsPage } from "./pages/GetAddonsPage";
import { t } from "./strings";
import { initUpdateFlow } from "./updateFlow";

export default definePlugin(() => {
  routerHook.addRoute(GET_ADDONS_ROUTE, GetAddonsPage, { exact: true });
  startAppWatcher();
  initUpdateFlow();
  return {
    name: t.title,
    titleView: <div className={staticClasses.Title}>{t.title}</div>,
    content: <QuickAccess />,
    icon: <FaPuzzlePiece />,
    onDismount() {
      stopAppWatcher();
      routerHook.removeRoute(GET_ADDONS_ROUTE);
    },
  };
});
