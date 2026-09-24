import {
  ButtonItem,
  ConfirmModal,
  DropdownItem,
  Field,
  Navigation,
  PanelSection,
  PanelSectionRow,
  ToggleField,
  showModal,
} from "@decky/ui";
import { toaster } from "@decky/api";
import { useState } from "react";
import {
  adoptWowup,
  applyWowupUpdate,
  checkForUpdate,
  addInstallations,
  installViaDecky,
  installWowup,
  prepareUpdate,
  restoreSnapshot,
  runUpdate,
  setUi,
  setUpdatePrefs,
} from "../backend";
import { usePluginState } from "../hooks/usePluginState";
import { GET_ADDONS_ROUTE } from "../pages/GetAddonsPage";
import { VERSIONS_ROUTE } from "../pages/VersionsPage";
import { JobProgress } from "./JobProgress";
import { t } from "../strings";
import type { Addon, Installation, JobStart, PluginState, UpdatedAddon } from "../types";
import { armRestartAfterInstall, restartSteam } from "../updateFlow";
import { FRONTEND_VERSION } from "../version";

function when(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString([], { dateStyle: "short", timeStyle: "short" });
}

function sortAddons(list: Addon[]): Addon[] {
  const rank = (a: Addon) => (a.needsUpdate ? 0 : a.compat === "incompatible" ? 1 : a.compat === "outdated" ? 2 : 3);
  return [...list].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
}

function addonLine(a: Addon): string {
  const parts = [a.needsUpdate ? `${a.installedVersion ?? "?"} → ${a.latestVersion ?? "?"}` : a.installedVersion ?? "?"];
  if (a.provider) parts.push(a.provider);
  if (t.compat[a.compat]) parts.push(t.compat[a.compat]);
  if (a.ignored) parts.push(t.ignored);
  if (a.missing) parts.push(t.missingFolders);
  return parts.join(" · ");
}

function updatedLine(u: UpdatedAddon): string {
  return !u.from || u.from === "0" ? `${u.name} (${t.installedLabel} ${u.to})` : `${u.name} ${u.to}`;
}

function versionTitle(i: Installation): string {
  const kind = i.gameTypeLabel ?? i.clientTypeLabel;
  const label = i.label && i.label !== "World of Warcraft" && i.label !== kind ? `${i.label} – ` : "";
  return `${label}${kind}${i.version ? ` ${i.version}` : ""}`;
}

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
  const inst = s.installations.find((i) => i.id === s.settings.ui.installationId)
    ?? s.installations.find((i) => i.selected) ?? s.installations[0];
  const addons = inst ? sortAddons(s.addons[inst.id] ?? []) : [];
  const snapshot = inst ? s.snapshots.find((x) => x.installationId === inst.id) : undefined;
  const canRun = !!s.wowup.path && !s.wowup.running && !busy;
  const addable = s.missingInWowUp.filter((d) => d.clientType != null).length;

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

  const confirmUndo = () => {
    if (!snapshot) return;
    showModal(
      <ConfirmModal strTitle={t.undoTitle} strDescription={t.undoBody} strOKButtonText={t.restore}
        onOK={() => void act(() => restoreSnapshot(snapshot.id, null))} />,
    );
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

      <PanelSection title={t.wowup}>
        {s.wowup.path ? (
          <>
            <PanelSectionRow>
              <Field label={`${t.wowup} ${s.wowup.version ?? ""}`}
                description={`${s.wowup.verified ? t.verified : t.unverified} · ${t.channel} ${s.wowup.channel}`} />
            </PanelSectionRow>
            {s.wowup.running && (
              <PanelSectionRow>
                <Field description={t.wowupRunning} />
              </PanelSectionRow>
            )}
            {s.wowup.updateAvailable && (
              <PanelSectionRow>
                <ButtonItem layout="below" label={`${t.updateWowup} → ${s.wowup.latestVersion}`} description={t.updateWowupDesc}
                  disabled={busy || s.wowup.running} onClick={() => void act(() => applyWowupUpdate())}>
                  {t.updateWowup}
                </ButtonItem>
              </PanelSectionRow>
            )}
          </>
        ) : (
          <>
            <PanelSectionRow>
              <Field label={t.wowupMissing} description={t.wowupMissingDesc} />
            </PanelSectionRow>
            {s.wowup.candidates.map((c) => (
              <PanelSectionRow key={c.path}>
                <ButtonItem layout="below" label={`${t.wowup} ${c.version ?? ""}`} description={c.path} disabled={busy}
                  onClick={() => void act(() => adoptWowup(c.path))}>
                  {t.useFound}
                </ButtonItem>
              </PanelSectionRow>
            ))}
            <PanelSectionRow>
              <ButtonItem layout="below" description={t.installWowupDesc} disabled={busy}
                onClick={() => void act(() => installWowup(null))}>
                {t.installWowup}
              </ButtonItem>
            </PanelSectionRow>
          </>
        )}
      </PanelSection>

      {s.wowup.path && (
        <PanelSection title={t.addons}>
          {s.installations.length > 1 && (
            <PanelSectionRow>
              <DropdownItem label={t.version} disabled={busy} selectedOption={inst?.id}
                rgOptions={s.installations.map((i) => ({ data: i.id, label: versionTitle(i) }))}
                onChange={(o) => void setUi({ installationId: o.data }).then(() => refresh())} />
            </PanelSectionRow>
          )}
          {!inst ? (
            <PanelSectionRow>
              <Field description={t.noInstallations} />
            </PanelSectionRow>
          ) : (
            <>
              <PanelSectionRow>
                <Field label={versionTitle(inst)} description={t.addonsSummary(inst.addonCount, inst.updateCount, inst.incompatibleCount)} />
              </PanelSectionRow>
              <PanelSectionRow>
                <ButtonItem layout="below" description={t.updateAllDesc} disabled={!canRun}
                  onClick={() => void act(() => runUpdate("all", inst.id, null))}>
                  {inst.updateCount ? `${t.updateAll} (${inst.updateCount})` : t.updateAll}
                </ButtonItem>
              </PanelSectionRow>
              <PanelSectionRow>
                <ButtonItem layout="below" description={t.checkDesc} disabled={!canRun}
                  onClick={() => void act(() => runUpdate("check", inst.id, null))}>
                  {t.check}
                </ButtonItem>
              </PanelSectionRow>
              <PanelSectionRow>
                <ButtonItem layout="below" description={t.getAddonsDesc}
                  onClick={() => { Navigation.Navigate(GET_ADDONS_ROUTE); Navigation.CloseSideMenus(); }}>
                  {`${t.getAddons}…`}
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
              {addons.map((a) =>
                a.needsUpdate ? (
                  <PanelSectionRow key={a.key}>
                    <ButtonItem layout="below" label={a.name} description={addonLine(a)} disabled={!canRun}
                      onClick={() => void act(() => runUpdate("selected", inst.id, [a.key]))}>
                      {t.update}
                    </ButtonItem>
                  </PanelSectionRow>
                ) : (
                  <PanelSectionRow key={a.key}>
                    <Field label={a.name} description={addonLine(a)} focusable />
                  </PanelSectionRow>
                ),
              )}
              {inst.unmanaged.length > 0 && (
                <PanelSectionRow>
                  <Field label={t.unmanaged} description={inst.unmanaged.join(", ")} focusable />
                </PanelSectionRow>
              )}
            </>
          )}
        </PanelSection>
      )}

      {s.wowup.path && (
        <PanelSection title={t.versions}>
          <PanelSectionRow>
            <Field label={t.versionsSummary(s.installations.length, s.missingInWowUp.length)}
              description={s.missingInWowUp.length
                ? s.missingInWowUp.map((d) => `${d.gameTypeLabel ?? d.product} ${d.version ?? ""} · ${d.source ?? d.subfolder}`).join(", ")
                : undefined} />
          </PanelSectionRow>
          {addable > 0 && (
            <PanelSectionRow>
              <ButtonItem layout="below" disabled={!canRun} onClick={() => void act(() => addInstallations(null))}>
                {t.addAllFound(addable)}
              </ButtonItem>
            </PanelSectionRow>
          )}
          <PanelSectionRow>
            <ButtonItem layout="below" description={t.manageVersionsDesc}
              onClick={() => { Navigation.Navigate(VERSIONS_ROUTE); Navigation.CloseSideMenus(); }}>
              {`${t.manageVersions}…`}
            </ButtonItem>
          </PanelSectionRow>
        </PanelSection>
      )}

      {snapshot && (
        <PanelSection title={t.safety}>
          <PanelSectionRow>
            <ButtonItem layout="below" description={t.undoDesc(when(snapshot.createdAt))} disabled={!canRun} onClick={confirmUndo}>
              {t.undo}
            </ButtonItem>
          </PanelSectionRow>
        </PanelSection>
      )}

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
