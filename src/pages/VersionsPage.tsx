import { DialogButton, Focusable, Navigation, ToggleField } from "@decky/ui";
import { openFilePicker, toaster } from "@decky/api";
import { CSSProperties, ReactNode } from "react";
import { addInstallationPath, addInstallations, setDiscovery } from "../backend";
import { FullPage } from "../components/FullPage";
import { JobProgress } from "../components/JobProgress";
import { usePluginState } from "../hooks/usePluginState";
import { t } from "../strings";
import { theme } from "../theme";
import type { Detected, Installation, JobStart } from "../types";

export const VERSIONS_ROUTE = "/wow-addons/versions";

// FileSelectionType.FOLDER: a const enum that @decky/api only declares in its typings, so referencing
// it would be undefined at runtime; the value comes from @decky/api/dist/types.d.ts.
const SELECT_FOLDER = 1;

const rowStyle: CSSProperties = {
  display: "flex", alignItems: "center", gap: "12px", padding: "10px 12px", borderRadius: theme.radius.lg,
  background: theme.surface.sm,
};
const buttonStyle: CSSProperties = { width: "150px", minWidth: "150px" };
const hintStyle: CSSProperties = { fontSize: "13px", color: theme.text.secondary, lineHeight: 1.4 };
const h3Style: CSSProperties = { margin: "14px 0 2px", fontSize: "17px" };

function Row({ title, lines, action }: { title: string; lines: (string | null | undefined)[]; action?: ReactNode }) {
  return (
    <Focusable style={rowStyle} flow-children="horizontal" onActivate={action ? undefined : () => undefined}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: "15px", fontWeight: 600, color: theme.text.primary }}>{title}</div>
        {lines.filter(Boolean).map((l, i) => (
          <div key={i} style={{ fontSize: "12px", color: i === 0 ? theme.text.secondary : theme.text.muted, marginTop: "2px",
            overflowWrap: "anywhere" }}>
            {l}
          </div>
        ))}
      </div>
      {action}
    </Focusable>
  );
}

function versionTitle(i: Installation): string {
  const kind = i.gameTypeLabel ?? i.clientTypeLabel;
  return `${kind}${i.version ? ` ${i.version}` : ""}${i.label && i.label !== "World of Warcraft" && i.label !== kind ? ` – ${i.label}` : ""}`;
}

function detectedTitle(d: Detected): string {
  const kind = d.gameTypeLabel ?? d.product ?? d.subfolder;
  return `${kind}${d.version ? ` ${d.version}` : ""}${d.clientTypeLabel && d.clientTypeLabel !== kind ? ` (${d.clientTypeLabel})` : ""}`;
}

export function VersionsPage() {
  const { state, refresh } = usePluginState();
  if (!state) {
    return (
      <FullPage title={t.versions}>
        <div style={hintStyle}>{t.loading}</div>
        <DialogButton style={{ width: "200px" }} onClick={() => Navigation.NavigateBack()}>{t.back}</DialogButton>
      </FullPage>
    );
  }

  const s = state;
  const running = s.job?.status === "running";
  const canWrite = !s.wowup.running && !running;
  const disc = s.discovery;

  const act = async (fn: () => Promise<unknown>) => {
    try {
      const res = (await fn()) as Partial<JobStart> | undefined;
      if (res && res.started === false) toaster.toast({ title: t.title, body: t.busy });
    } catch (e) {
      toaster.toast({ title: t.title, body: String(e) });
    } finally {
      void refresh(true);
    }
  };

  const pickFolder = async (): Promise<string | null> => {
    try {
      const res = await openFilePicker(SELECT_FOLDER as Parameters<typeof openFilePicker>[0], disc.home, false, true,
        undefined, undefined, true);
      return res.realpath || res.path || null;
    } catch {
      return null; // picker cancelled
    }
  };

  const sources = Object.entries(disc.sources)
    .filter(([, n]) => n > 0)
    .map(([k, n]) => `${t.sourceNames[k] ?? k}: ${n}`)
    .join(" · ");

  return (
    <FullPage title={t.versions}>
        <div style={hintStyle}>{`${t.sourcesChecked}: ${sources || "–"}`}</div>
        {running && <JobProgress message={s.job?.message || t.working} percent={s.job?.percent ?? null} />}
        {s.wowup.running && <div style={{ ...hintStyle, color: theme.warning.text }}>{t.wowupRunning}</div>}

        <h3 style={h3Style}>{t.inWowup}</h3>
        {s.installations.length === 0 ? (
          <div style={hintStyle}>{t.noInstallations}</div>
        ) : (
          s.installations.map((i) => (
            <Row key={i.id} title={versionTitle(i)}
              lines={[i.source ?? i.clientTypeLabel, i.flavorDir, t.addonsSummary(i.addonCount, i.updateCount, i.incompatibleCount)]} />
          ))
        )}

        <h3 style={h3Style}>{t.foundNotInWowup}</h3>
        {s.missingInWowUp.length === 0 ? (
          <div style={hintStyle}>{t.nothingFound}</div>
        ) : (
          <>
            {s.missingInWowUp.map((d) => (
              <Row key={d.flavorDir} title={detectedTitle(d)} lines={[d.source, d.flavorDir]}
                action={d.clientType == null ? (
                  <span style={{ ...buttonStyle, fontSize: "12px", color: theme.warning.text, textAlign: "center" }}>{t.unsupportedVersion}</span>
                ) : (
                  <DialogButton style={buttonStyle} disabled={!canWrite} onClick={() => void act(() => addInstallations([d.flavorDir]))}>
                    {t.add}
                  </DialogButton>
                )} />
            ))}
            {s.missingInWowUp.filter((d) => d.clientType != null).length > 1 && (
              <DialogButton style={{ width: "220px" }} disabled={!canWrite} onClick={() => void act(() => addInstallations(null))}>
                {t.addAll}
              </DialogButton>
            )}
          </>
        )}
        <div style={hintStyle}>{t.unmanagedHint}</div>

        <h3 style={h3Style}>{t.addFolder.replace("…", "")}</h3>
        <Focusable flow-children="horizontal" style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          <DialogButton style={{ width: "260px", minWidth: "260px" }} disabled={!canWrite}
            onClick={() => void (async () => { const p = await pickFolder(); if (p) await act(() => addInstallationPath(p)); })()}>
            {t.addFolder}
          </DialogButton>
          <div style={hintStyle}>{t.addFolderDesc}</div>
        </Focusable>
        {disc.manualPaths.map((p) => (
          <Row key={p} title={t.addedByHand} lines={[p]}
            action={<DialogButton style={buttonStyle} onClick={() => void act(() => setDiscovery({ manualPaths: disc.manualPaths.filter((x) => x !== p) }))}>{t.forget}</DialogButton>} />
        ))}

        <h3 style={h3Style}>{t.searchFolders}</h3>
        <div style={hintStyle}>{t.searchFoldersDesc}</div>
        {disc.searchPaths.map((p) => (
          <Row key={p} title={p} lines={[]}
            action={<DialogButton style={buttonStyle} onClick={() => void act(() => setDiscovery({ searchPaths: disc.searchPaths.filter((x) => x !== p) }))}>{t.remove}</DialogButton>} />
        ))}
        <Focusable flow-children="horizontal" style={{ display: "flex", gap: "12px" }}>
          <DialogButton style={{ width: "260px" }}
            onClick={() => void (async () => { const p = await pickFolder(); if (p) await act(() => setDiscovery({ searchPaths: [...disc.searchPaths, p] })); })()}>
            {t.addSearchFolder}
          </DialogButton>
          <DialogButton style={{ width: "200px" }} onClick={() => void refresh(true)}>{t.searchAgain}</DialogButton>
        </Focusable>
        <ToggleField label={t.scanRemovable} description={disc.removable.length ? `${t.drives}: ${disc.removable.join(", ")}` : undefined}
          checked={disc.scanRemovable} onChange={(v) => void act(() => setDiscovery({ scanRemovable: v }))} />

        <DialogButton style={{ width: "200px", marginTop: "10px" }} onClick={() => Navigation.NavigateBack()}>{t.back}</DialogButton>
    </FullPage>
  );
}
