import { ConfirmModal, showModal } from "@decky/ui";
import { relocateInstallation } from "./backend";
import { t } from "./strings";
import type { Installation, JobStart, RelocationTarget } from "./types";

/** Ask before pointing a game-less WowUp installation at the installed game. */
export function confirmRelocate(inst: Installation, target: RelocationTarget,
  act: (fn: () => Promise<JobStart>) => Promise<void>) {
  showModal(
    <ConfirmModal strTitle={t.moveTitle} strDescription={t.moveBody(inst.flavorDir, target.flavorDir, target.replaces)}
      strOKButtonText={t.move} onOK={() => void act(() => relocateInstallation(inst.id, target.flavorDir))} />,
  );
}
