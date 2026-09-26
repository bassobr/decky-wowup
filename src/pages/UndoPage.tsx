import { ConfirmModal, showModal } from "@decky/ui";
import { restoreSnapshot } from "../backend";
import { Button, hintStyle, makeAct, PageBody, Row } from "../components/FullPage";
import { JobProgress } from "../components/JobProgress";
import { when } from "../format";
import { t } from "../strings";
import type { SnapshotInfo } from "../types";
import type { PageProps } from "./MainView";

function snapshotTitle(x: SnapshotInfo): string {
  if (x.kind === "remove") return t.snapRemoved(x.names ?? []);
  return x.label.startsWith("before restoring") ? t.snapBeforeRestore : t.snapBeforeUpdate;
}

export function UndoPage({ state: s, refresh }: PageProps) {
  const act = makeAct(refresh);
  const running = s.job?.status === "running";
  const canWrite = !s.wowup.running && !running;
  const labels = Object.fromEntries(s.installations.map((i) => [i.id, i.label]));

  const confirm = (x: SnapshotInfo) =>
    showModal(
      <ConfirmModal strTitle={x.kind === "remove" ? t.restoreRemovalTitle : t.undoTitle}
        strDescription={x.kind === "remove" ? t.restoreRemovalBody : t.undoBody} strOKButtonText={t.restore}
        onOK={() => void act(() => restoreSnapshot(x.id, null))} />,
    );

  return (
    <PageBody>
      <div style={hintStyle}>{t.undoIntro}</div>
      {running && <JobProgress message={s.job?.message || t.working} percent={s.job?.percent ?? null} />}
      {s.snapshots.length === 0 && <div style={hintStyle}>{t.noSnapshots}</div>}
      {s.snapshots.map((x) => (
        <Row key={x.id} title={snapshotTitle(x)}
          lines={[`${(x.installationId && labels[x.installationId]) || x.installationLabel || ""} · ${when(x.createdAt)}`]}>
          <Button disabled={!canWrite} onClick={() => confirm(x)}>{t.restore}</Button>
        </Row>
      ))}
    </PageBody>
  );
}
