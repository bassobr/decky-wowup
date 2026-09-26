import { ButtonItem, Field, PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useState } from "react";
import { checkForUpdate, installViaDecky, prepareUpdate, runUpdate, setUpdatePrefs } from "../backend";
import { updatedLine, versionTitle, when } from "../format";
import { usePluginState } from "../hooks/usePluginState";
import { openMainView } from "../pages/MainView";
import { t } from "../strings";
import type { JobStart, PluginState } from "../types";
import { armRestartAfterInstall, restartSteam } from "../updateFlow";
import { FRONTEND_VERSION } from "../version";
import { JobProgress } from "./JobProgress";

// Only "Update all" and the plugin's own update live here; everything else is in the full-screen view.
export function QuickAccess() {
  const { state, error, refresh } = usePluginState();
  const [pending, setPending] = useState(false);

  if (error) {
    return (
      <PanelSection title={t.title}>
        <PanelSectionRow>
          <Field label="Backend" description={error} />
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => void refresh(true)}>{t.refresh}</ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    );
  }
  if (!state) {
    return (
      <PanelSection title={t.title}>
        <PanelSectionRow>
          <Field label={t.loading} />
        </PanelSectionRow>
      </PanelSection>
    );
  }

  const s: PluginState = state;
  const running = s.job?.status === "running";
  const busy = pending || running;
  const canRun = !!s.wowup.path && !s.wowup.running && !busy && s.installations.some((i) => i.hasGame !== false);
  const updates = s.installations.reduce((n, i) => n + (i.hasGame === false ? 0 : i.updateCount), 0);

  const act = async (fn: () => Promise<unknown>) => {
    setPending(true);
    try {
      const res = (await fn()) as Partial<JobStart> | undefined;
      if (res && res.started === false) toaster.toast({ title: t.title, body: t.busy });
    } catch (e) {
      toaster.toast({ title: t.title, body: String(e) });
    } finally {
      setPending(false);
      void refresh();
    }
  };

  const onInstallPluginUpdate = () =>
    act(async () => {
      const artifact = await prepareUpdate();
      armRestartAfterInstall(artifact.version, s.settings.update.autoRestartSteam !== false);
      await installViaDecky(artifact);
    });

  return (
    <>
      {running && (
        <PanelSection>
          <PanelSectionRow>
            <JobProgress message={s.job?.message || t.working} percent={s.job?.percent ?? null} />
          </PanelSectionRow>
        </PanelSection>
      )}

      <PanelSection title={t.addons}>
        {!s.wowup.path ? (
          <PanelSectionRow>
            <Field label={t.wowupMissing} description={t.setupInView} />
          </PanelSectionRow>
        ) : s.installations.length === 0 ? (
          <PanelSectionRow>
            <Field description={t.noInstallations} />
          </PanelSectionRow>
        ) : (
          <>
            {s.installations.map((i) => (
              <PanelSectionRow key={i.id}>
                <Field label={versionTitle(i)}
                  description={i.hasGame === false ? t.noGame : t.addonsSummary(i.addonCount, i.updateCount, i.incompatibleCount)} />
              </PanelSectionRow>
            ))}
            {s.wowup.running && (
              <PanelSectionRow>
                <Field description={t.wowupRunning} />
              </PanelSectionRow>
            )}
            <PanelSectionRow>
              <ButtonItem layout="below" description={t.updateAllVersionsDesc} disabled={!canRun}
                onClick={() => void act(() => runUpdate("all", null, null))}>
                {updates ? `${t.updateAll} (${updates})` : t.updateAll}
              </ButtonItem>
            </PanelSectionRow>
            {s.lastRun && (
              <PanelSectionRow>
                <Field label={`${t.lastRun}: ${when(s.lastRun.finishedAt)}`}
                  description={!s.lastRun.ok ? (s.lastRun.timedOut ? t.timedOut : `${t.failed}${s.lastRun.errors[0] ? `: ${s.lastRun.errors[0]}` : ""}`)
                    : s.lastRun.updated.length ? `${t.updatedN(s.lastRun.updated.length)}: ${s.lastRun.updated.map(updatedLine).join(", ")}`
                      : t.nothingUpdated} />
              </PanelSectionRow>
            )}
          </>
        )}
        <PanelSectionRow>
          <ButtonItem layout="below" description={t.openMainDesc} onClick={() => openMainView(s.wowup.path ? "installed" : "wowup")}>
            {`${t.openMain}…`}
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>

      {s.warnings.length > 0 && (
        <PanelSection title={t.warnings}>
          {s.warnings.map((w) => (
            <PanelSectionRow key={w}>
              <Field description={w} focusable />
            </PanelSectionRow>
          ))}
        </PanelSection>
      )}

      <PanelSection title={t.maintenance}>
        {s.version !== FRONTEND_VERSION && (
          <PanelSectionRow>
            <ButtonItem layout="below" label={t.staleUi} description={`UI ${FRONTEND_VERSION}, backend ${s.version}`} onClick={() => restartSteam()}>
              {t.restartSteam}
            </ButtonItem>
          </PanelSectionRow>
        )}
        {s.update.updateAvailable ? (
          <PanelSectionRow>
            <ButtonItem layout="below" description={`${t.updateAvailable}: v${s.update.latestVersion} (${t.pluginVersion} ${s.version})`}
              disabled={busy} onClick={() => void onInstallPluginUpdate()}>
              {t.installUpdate}
            </ButtonItem>
          </PanelSectionRow>
        ) : (
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy}
              description={s.update.error ? `${t.updateFailed}: ${s.update.error}` : `${t.upToDate} · ${t.pluginVersion} ${s.version}`}
              onClick={() => void act(() => checkForUpdate(true))}>
              {t.checkPluginUpdate}
            </ButtonItem>
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <ToggleField label={t.autoRestart} description={t.autoRestartDesc} checked={s.settings.update.autoRestartSteam !== false}
            disabled={busy} onChange={(v) => void act(() => setUpdatePrefs({ autoRestartSteam: v }))} />
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}
