import { DialogButton, Dropdown, Focusable, Navigation, TextField } from "@decky/ui";
import { toaster } from "@decky/api";
import { CSSProperties, useEffect, useRef, useState } from "react";
import { installAddons, searchAddons, setUi } from "../backend";
import { JobProgress } from "../components/JobProgress";
import { usePluginState } from "../hooks/usePluginState";
import { ensureWowupShortcut, launchShortcut, terminateShortcut } from "../steam/wowupShortcut";
import { t } from "../strings";
import { theme } from "../theme";
import type { InstallItem, Installation, SearchResponse, SearchResult } from "../types";

export const GET_ADDONS_ROUTE = "/wow-addons/get";

const SOURCE_LABEL: Record<string, string> = { WowInterface: "WoWInterface", WowUpHub: "WowUp Hub", Curse: "CurseForge" };

const rowStyle: CSSProperties = {
  display: "flex", alignItems: "center", gap: "12px", padding: "10px 12px", borderRadius: theme.radius.lg,
  background: theme.surface.sm,
};
const buttonStyle: CSSProperties = { width: "150px", minWidth: "150px" };
const hintStyle: CSSProperties = { fontSize: "13px", color: theme.text.secondary, lineHeight: 1.4 };

function downloads(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
  return String(n);
}

function versionTitle(i: Installation): string {
  const kind = i.gameTypeLabel ?? i.clientTypeLabel;
  return `${kind}${i.version ? ` ${i.version}` : ""}${i.label && i.label !== "World of Warcraft" && i.label !== kind ? ` (${i.label})` : ""}`;
}

function ResultRow({ r, disabled, onInstall }: { r: SearchResult; disabled: boolean; onInstall: (r: SearchResult) => void }) {
  const meta = [
    r.author,
    SOURCE_LABEL[r.provider] ?? r.provider,
    r.version,
    r.downloads ? `${downloads(r.downloads)} ${t.downloads}` : "",
    r.compatVersions.length ? `${t.forVersions} ${r.compatVersions.slice(0, 3).join(", ")}` : "",
  ].filter(Boolean).join(" · ");
  return (
    <Focusable style={rowStyle} flow-children="horizontal">
      {r.thumbnail ? (
        <img src={r.thumbnail} style={{ width: "56px", height: "56px", objectFit: "cover", borderRadius: theme.radius.md, flexShrink: 0 }} />
      ) : (
        <div style={{ width: "56px", height: "56px", borderRadius: theme.radius.md, background: theme.surface.lg, flexShrink: 0 }} />
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: "15px", fontWeight: 600, color: theme.text.primary }}>{r.name}</div>
        <div style={{ fontSize: "12px", color: theme.text.secondary, marginTop: "2px" }}>{meta}</div>
        {r.summary && (
          <div style={{ fontSize: "12px", color: theme.text.muted, marginTop: "3px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {r.summary}
          </div>
        )}
        {r.compatible === false && <div style={{ fontSize: "12px", color: theme.warning.text, marginTop: "3px" }}>{t.maybeIncompatible}</div>}
        {r.present && <div style={{ fontSize: "12px", color: theme.info.text, marginTop: "3px" }}>{t.presentNote}</div>}
      </div>
      {r.installed ? (
        <span style={{ ...buttonStyle, textAlign: "center", fontSize: "13px", color: theme.success.text, padding: "8px 0",
          borderRadius: theme.radius.md, background: theme.success.badgeBg }}>
          {t.installedBadge}
        </span>
      ) : (
        <DialogButton style={buttonStyle} disabled={disabled} onClick={() => onInstall(r)}>{t.install}</DialogButton>
      )}
    </Focusable>
  );
}

function ResultSection({ title, results, disabled, onInstall }: {
  title: string; results: SearchResult[] | undefined; disabled: boolean; onInstall: (r: SearchResult) => void;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
      <h3 style={{ margin: "10px 0 2px", fontSize: "17px" }}>{title}</h3>
      {results === undefined ? null : results.length === 0 ? (
        <div style={hintStyle}>{t.noResults}</div>
      ) : (
        results.map((r) => <ResultRow key={`${r.provider}:${r.externalId}`} r={r} disabled={disabled} onInstall={onInstall} />)
      )}
    </div>
  );
}

export function GetAddonsPage() {
  const { state, refresh } = usePluginState();
  const [instId, setInstId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [cfId, setCfId] = useState("");
  const handledJob = useRef<string | null>(null);

  const insts = state?.installations ?? [];
  const inst = insts.find((i) => i.id === (instId ?? state?.settings.ui.installationId))
    ?? insts.find((i) => i.selected) ?? insts[0];
  const job = state?.job ?? null;
  const running = job?.status === "running";
  const canInstall = !!state?.wowup.path && !state.wowup.running && !running;

  const search = async (q: string) => {
    if (!inst) return;
    setLoading(true);
    try {
      setData(await searchAddons(inst.id, q));
    } catch (e) {
      toaster.toast({ title: t.title, body: String(e) });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (inst) void search("");
  }, [inst?.id]);

  useEffect(() => {  // refresh the installed markers once an install job finished
    if (job && job.kind === "install" && job.status !== "running" && handledJob.current !== job.id) {
      handledJob.current = job.id;
      void search(data?.query ?? "");
    }
  }, [job?.id, job?.status]);

  const install = async (items: InstallItem[]) => {
    if (!inst) return;
    try {
      const res = await installAddons(inst.id, items);
      if (!res.started) toaster.toast({ title: t.title, body: t.busy });
    } catch (e) {
      toaster.toast({ title: t.title, body: String(e) });
    } finally {
      void refresh();
    }
  };

  const openWowup = async () => {
    if (!state?.wowup.path) return;
    try {
      const ui = state.settings.ui;
      const appId = await ensureWowupShortcut(state.wowup.path, ui.wowupShortcutAppId, ui.wowupShortcutExe ?? null);
      await setUi({ wowupShortcutAppId: appId, wowupShortcutExe: state.wowup.path });
      await launchShortcut(appId);
    } catch (e) {
      toaster.toast({ title: t.title, body: String(e) });
    }
  };

  const page: CSSProperties = { padding: "0 28px 28px", color: "#fff", maxWidth: "1100px", display: "flex", flexDirection: "column", gap: "12px" };

  if (!state || !inst) {
    return (
      <div style={{ marginTop: "40px", height: "calc(100% - 40px)", overflowY: "auto" }}>
        <Focusable style={page} flow-children="vertical">
          <h2 style={{ margin: "8px 0 0" }}>{t.getAddons}</h2>
          <div style={hintStyle}>{state ? t.noInstallations : t.loading}</div>
          <DialogButton style={{ width: "200px" }} onClick={() => Navigation.NavigateBack()}>{t.back}</DialogButton>
        </Focusable>
      </div>
    );
  }

  const searched = !!data?.query;
  return (
    <div style={{ marginTop: "40px", height: "calc(100% - 40px)", overflowY: "auto" }}>
      <Focusable style={page} flow-children="vertical">
        <h2 style={{ margin: "8px 0 0" }}>{t.getAddons}</h2>
        <Focusable flow-children="horizontal" style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div style={hintStyle}>{t.getAddonsIntro}</div>
          {insts.length > 1 ? (
            <div style={{ minWidth: "280px" }}>
              <Dropdown rgOptions={insts.map((i) => ({ data: i.id, label: versionTitle(i) }))} selectedOption={inst.id}
                onChange={(o) => { setInstId(o.data); void setUi({ installationId: o.data }); }} />
            </div>
          ) : (
            <div style={{ ...hintStyle, color: theme.text.primary }}>{versionTitle(inst)}</div>
          )}
        </Focusable>

        {running && <JobProgress message={job?.message || t.working} percent={job?.percent ?? null} />}
        {state.wowup.running && (
          <Focusable flow-children="horizontal" style={{ ...rowStyle, background: theme.warning.bg }}>
            <div style={{ flex: 1, fontSize: "13px", color: theme.warning.text }}>{t.wowupRunning}</div>
            <DialogButton style={buttonStyle} onClick={() => { if (!terminateShortcut(state.settings.ui.wowupShortcutAppId)) toaster.toast({ title: t.title, body: t.openWowupHint }); }}>
              {t.closeWowup}
            </DialogButton>
          </Focusable>
        )}

        <Focusable flow-children="horizontal" style={{ display: "flex", gap: "10px", alignItems: "flex-end" }}>
          <div style={{ flex: 1 }}>
            <TextField label={t.searchLabel} value={query} bShowClearAction
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") void search(query); }} />
          </div>
          <DialogButton style={buttonStyle} disabled={loading} onClick={() => void search(query)}>
            {loading ? t.searching : t.search}
          </DialogButton>
        </Focusable>
        {data?.errors.map((e) => <div key={e} style={{ fontSize: "13px", color: theme.error.text }}>{e}</div>)}

        <ResultSection title={searched ? t.resultsWowi : t.popularWowi} results={data?.wowinterface} disabled={!canInstall}
          onInstall={(r) => void install([{ provider: r.provider, externalId: r.externalId, name: r.name }])} />
        <ResultSection title={searched ? t.resultsHub : t.featuredHub} results={data?.hub} disabled={!canInstall}
          onInstall={(r) => void install([{ provider: r.provider, externalId: r.externalId, name: r.name }])} />

        <h3 style={{ margin: "14px 0 2px", fontSize: "17px" }}>{t.curseforge}</h3>
        <div style={hintStyle}>{t.curseforgeIntro}</div>
        <Focusable flow-children="horizontal" style={{ display: "flex", gap: "10px", alignItems: "flex-end" }}>
          <div style={{ flex: 1 }}>
            <TextField label={t.cfProjectId} value={cfId} mustBeNumeric
              onChange={(e) => setCfId(e.target.value.replace(/\D/g, "").slice(0, 12))} />
          </div>
          <DialogButton style={buttonStyle} disabled={!canInstall || !cfId}
            onClick={() => void install([{ provider: "Curse", externalId: cfId, name: "" }])}>
            {t.install}
          </DialogButton>
        </Focusable>
        <Focusable flow-children="horizontal" style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <DialogButton style={{ width: "320px", minWidth: "320px" }} disabled={!state.wowup.path || running || state.wowup.running}
            onClick={() => void openWowup()}>
            {t.openWowup}
          </DialogButton>
          <div style={hintStyle}>{t.openWowupHint}</div>
        </Focusable>

        <DialogButton style={{ width: "200px", marginTop: "10px" }} onClick={() => Navigation.NavigateBack()}>{t.back}</DialogButton>
      </Focusable>
    </div>
  );
}
