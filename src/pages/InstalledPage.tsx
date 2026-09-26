import { ConfirmModal, Dropdown, Focusable, showModal } from "@decky/ui";
import { removeAddons, runUpdate } from "../backend";
import { Button, ButtonRow, h3Style, hintStyle, makeAct, PageBody, Row } from "../components/FullPage";
import { JobProgress } from "../components/JobProgress";
import { addonLine, sortAddons, updatedLine, versionTitle, when } from "../format";
import { confirmRelocate } from "../relocate";
import { t } from "../strings";
import { theme } from "../theme";
import type { Addon } from "../types";
import type { PageProps } from "./MainView";

export function InstalledPage({ state: s, refresh, inst, selectInstallation, openPage }: PageProps) {
  const act = makeAct(refresh);
  const running = s.job?.status === "running";
  const canRun = !!s.wowup.path && !s.wowup.running && !running;
  const canWrite = !s.wowup.running && !running;

  if (!s.wowup.path || !inst) {
    return (
      <PageBody>
        <div style={hintStyle}>{!s.wowup.path ? `${t.wowupMissing}. ${t.wowupMissingDesc}` : t.noInstallations}</div>
        <ButtonRow>
          <Button width="260px" onClick={() => openPage(!s.wowup.path ? "wowup" : "versions")}>
            {!s.wowup.path ? t.installWowup : t.manageVersions}
          </Button>
        </ButtonRow>
      </PageBody>
    );
  }

  const addons = sortAddons(s.addons[inst.id] ?? []);
  const canUpdate = canRun && inst.hasGame !== false;
  const lastRun = s.lastRun;

  const confirmRemove = (a: Addon) => {
    const keys = [a.key];
    showModal(
      <ConfirmModal strTitle={t.removeTitle(a.name)} strDescription={t.removeBody(a.folders, a.requiredBy)}
        strOKButtonText={t.remove}
        strMiddleButtonText={a.removableDeps.length ? t.removeWithDeps(a.removableDeps.map((d) => d.name)) : undefined}
        onMiddleButton={a.removableDeps.length ? () => void act(() => removeAddons(inst.id, keys, null, true)) : undefined}
        onOK={() => void act(() => removeAddons(inst.id, keys, null, false))} />,
    );
  };
  const confirmRemoveFolder = (folder: string) =>
    showModal(
      <ConfirmModal strTitle={t.removeFolderTitle(folder)} strDescription={t.removeFolderBody} strOKButtonText={t.remove}
        onOK={() => void act(() => removeAddons(inst.id, null, [folder], false))} />,
    );

  return (
    <PageBody>
      {s.installations.length > 1 && (
        <Focusable flow-children="horizontal" style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div style={hintStyle}>{t.version}</div>
          <div style={{ minWidth: "320px" }}>
            <Dropdown rgOptions={s.installations.map((i) => ({ data: i.id, label: versionTitle(i) }))} selectedOption={inst.id}
              onChange={(o) => selectInstallation(o.data)} />
          </div>
        </Focusable>
      )}
      <div style={{ ...hintStyle, color: theme.text.primary }}>
        {`${s.installations.length > 1 ? "" : `${versionTitle(inst)} · `}${t.addonsSummary(inst.addonCount, inst.updateCount, inst.incompatibleCount)}`}
      </div>
      {running && <JobProgress message={s.job?.message || t.working} percent={s.job?.percent ?? null} />}
      {s.wowup.running && <div style={{ ...hintStyle, color: theme.warning.text }}>{t.wowupRunning}</div>}

      {inst.hasGame === false && (
        <>
          <Row tone="warning" title={t.noGame} lines={[t.noGameDesc, inst.flavorDir]} />
          {inst.relocateTo.map((r) => (
            <Row key={r.flavorDir} title={`${t.moveTo}: ${r.version ?? ""}`} lines={[r.source, r.flavorDir, r.reason]}>
              <Button disabled={!canWrite || !r.possible} onClick={() => confirmRelocate(inst, r, act)}>{t.move}</Button>
            </Row>
          ))}
        </>
      )}

      <ButtonRow>
        <Button width="240px" disabled={!canUpdate} onClick={() => void act(() => runUpdate("all", inst.id, null))}>
          {inst.updateCount ? `${t.updateAll} (${inst.updateCount})` : t.updateAll}
        </Button>
        <Button width="240px" disabled={!canRun} onClick={() => void act(() => runUpdate("check", inst.id, null))}>
          {t.check}
        </Button>
      </ButtonRow>
      {lastRun && (
        <div style={hintStyle}>
          {`${t.lastRun}: ${when(lastRun.finishedAt)} – ${!lastRun.ok ? (lastRun.timedOut ? t.timedOut : `${t.failed}${lastRun.errors[0] ? `: ${lastRun.errors[0]}` : ""}`)
            : lastRun.updated.length ? `${t.updatedN(lastRun.updated.length)}: ${lastRun.updated.map(updatedLine).join(", ")}` : t.nothingUpdated}`}
        </div>
      )}

      <h3 style={h3Style}>{t.addons}</h3>
      {addons.length === 0 && <div style={hintStyle}>{t.noAddons}</div>}
      {addons.map((a) => (
        <Row key={a.key} title={a.name}
          lines={[addonLine(a), a.requiredBy.length ? t.neededBy(a.requiredBy) : null]}>
          {a.needsUpdate && (
            <Button disabled={!canUpdate} onClick={() => void act(() => runUpdate("selected", inst.id, [a.key]))}>{t.update}</Button>
          )}
          <Button disabled={!canWrite} onClick={() => confirmRemove(a)}>{t.remove}</Button>
        </Row>
      ))}

      {inst.unmanaged.length > 0 && (
        <>
          <h3 style={h3Style}>{t.unmanaged}</h3>
          <div style={hintStyle}>{t.unmanagedDesc}</div>
          {inst.unmanaged.map((f) => (
            <Row key={f} title={f}>
              <Button disabled={!canWrite} onClick={() => confirmRemoveFolder(f)}>{t.remove}</Button>
            </Row>
          ))}
        </>
      )}
    </PageBody>
  );
}
