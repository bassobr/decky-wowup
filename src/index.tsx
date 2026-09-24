import { definePlugin } from "@decky/api";
import { staticClasses } from "@decky/ui";
import { FaPuzzlePiece } from "react-icons/fa";
import { startAppWatcher, stopAppWatcher } from "./appWatcher";
import { QuickAccess } from "./components/QuickAccess";
import { t } from "./strings";
import { initUpdateFlow } from "./updateFlow";

export default definePlugin(() => {
  startAppWatcher();
  initUpdateFlow();
  return {
    name: t.title,
    titleView: <div className={staticClasses.Title}>{t.title}</div>,
    content: <QuickAccess />,
    icon: <FaPuzzlePiece />,
    onDismount() {
      stopAppWatcher();
    },
  };
});
