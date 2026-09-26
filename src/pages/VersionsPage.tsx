import { ToggleField } from "@decky/ui";
import { openFilePicker } from "@decky/api";
import { addInstallationPath, addInstallations, setDiscovery } from "../backend";
import { Button, ButtonRow, h3Style, hintStyle, makeAct, PageBody, Row } from "../components/FullPage";
import { JobProgress } from "../components/JobProgress";
import { versionTitle } from "../format";
import { confirmRelocate } from "../relocate";
import { t } from "../strings";
import { theme } from "../theme";
import type { Detected } from "../types";
import type { PageProps } from "./MainView";

// FileSelectionType.FOLDER: a const enum that @decky/api only declares in its typings, so referencing
// it would be undefined at runtime; the value comes from @decky/api/dist/types.d.ts.
const SELECT_FOLDER = 1;

function detectedTitle(d: Detected): string {
  const kind = d.gameTypeLabel ?? d.product ?? d.subfolder;
  return `${kind}${d.version ? ` ${d.version}` : ""}${d.clientTypeLabel && d.clientTypeLabel !== kind ? ` (${d.clientTypeLabel})` : ""}`;
}

export function VersionsPage({ state: s, refresh }: PageProps) {
  const act = makeAct(refresh);
  const running = s.job?.status === "running";
  const canWrite = !s.wowup.running && !running;
  const disc = s.discovery;

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
  const addable = s.missingInWowUp.filter((d) => d.clientType != null);

  return (
    <PageBody>
      <div style={hintStyle}>{`${t.sourcesChecked}: ${sources || "–"}`}</div>
      {running && <JobProgress message={s.job?.message || t.working} percent={s.job?.percent ?? null} />}
      {s.wowup.running && <div style={{ ...hintStyle, color: theme.warning.text }}>{t.wowupRunning}</div>}

      <h3 style={h3Style}>{t.inWowup}</h3>
      {s.installations.length === 0 && <div style={hintStyle}>{t.noInstallations}</div>}
      {s.installations.map((i) => (
        <div key={i.id} style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          <Row title={versionTitle(i)} tone={i.hasGame === false ? "warning" : undefined}
            lines={[i.source ?? i.clientTypeLabel, i.flavorDir, t.addonsSummary(i.addonCount, i.updateCount, i.incompatibleCount),
              i.hasGame === false && `${t.noGame}. ${t.noGameDesc}`]} />
          {i.hasGame === false && i.relocateTo.map((r) => (
            <Row key={r.flavorDir} title={`${t.moveTo}: ${r.version ?? ""}`} lines={[r.source, r.flavorDir, r.reason]}>
              <Button disabled={!canWrite || !r.possible} onClick={() => confirmRelocate(i, r, act)}>{t.move}</Button>
            </Row>
          ))}
        </div>
      ))}

      <h3 style={h3Style}>{t.foundNotInWowup}</h3>
      {s.missingInWowUp.length === 0 && <div style={hintStyle}>{t.nothingFound}</div>}
      {s.missingInWowUp.map((d) => (
        <Row key={d.flavorDir} title={detectedTitle(d)} lines={[d.source, d.flavorDir]}>
          {d.clientType == null ? (
            <span style={{ width: "140px", fontSize: "12px", color: theme.warning.text, textAlign: "center" }}>{t.unsupportedVersion}</span>
          ) : (
            <Button disabled={!canWrite} onClick={() => void act(() => addInstallations([d.flavorDir]))}>{t.add}</Button>
          )}
        </Row>
      ))}
      {addable.length > 1 && (
        <ButtonRow>
          <Button width="220px" disabled={!canWrite} onClick={() => void act(() => addInstallations(null))}>
            {t.addAllFound(addable.length)}
          </Button>
        </ButtonRow>
      )}
      <div style={hintStyle}>{t.unmanagedHint}</div>

      <h3 style={h3Style}>{t.addFolder.replace("…", "")}</h3>
      <ButtonRow>
        <Button width="260px" disabled={!canWrite}
          onClick={() => void (async () => { const p = await pickFolder(); if (p) await act(() => addInstallationPath(p)); })()}>
          {t.addFolder}
        </Button>
        <div style={{ ...hintStyle, flex: 1, minWidth: "200px" }}>{t.addFolderDesc}</div>
      </ButtonRow>
      {disc.manualPaths.map((p) => (
        <Row key={p} title={t.addedByHand} lines={[p]}>
          <Button onClick={() => void act(() => setDiscovery({ manualPaths: disc.manualPaths.filter((x) => x !== p) }))}>{t.forget}</Button>
        </Row>
      ))}

      <h3 style={h3Style}>{t.searchFolders}</h3>
      <div style={hintStyle}>{t.searchFoldersDesc}</div>
      {disc.searchPaths.map((p) => (
        <Row key={p} title={p}>
          <Button onClick={() => void act(() => setDiscovery({ searchPaths: disc.searchPaths.filter((x) => x !== p) }))}>{t.remove}</Button>
        </Row>
      ))}
      <ButtonRow>
        <Button width="260px"
          onClick={() => void (async () => { const p = await pickFolder(); if (p) await act(() => setDiscovery({ searchPaths: [...disc.searchPaths, p] })); })()}>
          {t.addSearchFolder}
        </Button>
        <Button width="200px" onClick={() => void refresh(true)}>{t.searchAgain}</Button>
      </ButtonRow>
      <ToggleField label={t.scanRemovable} description={disc.removable.length ? `${t.drives}: ${disc.removable.join(", ")}` : undefined}
        checked={disc.scanRemovable} onChange={(v) => void act(() => setDiscovery({ scanRemovable: v }))} />
    </PageBody>
  );
}
