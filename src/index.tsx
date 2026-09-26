import { definePlugin, routerHook } from "@decky/api";
import { staticClasses } from "@decky/ui";
import { FaPuzzlePiece } from "react-icons/fa";
import { startAppWatcher, stopAppWatcher } from "./appWatcher";
import { QuickAccess } from "./components/QuickAccess";
import { MAIN_ROUTE, MainView } from "./pages/MainView";
import { t } from "./strings";
import { initUpdateFlow } from "./updateFlow";

export default definePlugin(() => {
  routerHook.addRoute(MAIN_ROUTE, MainView);
  startAppWatcher();
  initUpdateFlow();
  return {
    name: t.title,
    titleView: <div className={staticClasses.Title}>{t.title}</div>,
    content: <QuickAccess />,
    icon: <FaPuzzlePiece />,
    onDismount() {
      stopAppWatcher();
      routerHook.removeRoute(MAIN_ROUTE);
    },
  };
});
