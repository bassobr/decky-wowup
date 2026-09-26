import { DialogButton, Dropdown, Focusable, TextField } from "@decky/ui";
import { toaster } from "@decky/api";
import { useEffect, useRef, useState } from "react";
import { installAddons, searchAddons } from "../backend";
import { Button, buttonStyle, ButtonRow, h3Style, hintStyle, InlineField, PageBody, rowStyle } from "../components/FullPage";
import { JobProgress } from "../components/JobProgress";
import { count, versionTitle } from "../format";
import { closeWowupWindow, openWowupWindow } from "../steam/wowupShortcut";
import { t } from "../strings";
import { theme } from "../theme";
import type { InstallItem, SearchResponse, SearchResult, SortOrder } from "../types";
import type { PageProps } from "./MainView";

const SOURCE_LABEL: Record<string, string> = { WowInterface: "WoWInterface", WowUpHub: "WowUp Hub", Curse: "CurseForge" };
const SORTS: SortOrder[] = ["relevance", "popular", "downloads", "favorites", "updated", "name"];

function ResultRow({ r, disabled, onInstall }: { r: SearchResult; disabled: boolean; onInstall: (r: SearchResult) => void }) {
  const meta = [
    r.author,
    SOURCE_LABEL[r.provider] ?? r.provider,
    r.version,
    r.downloads ? `${count(r.downloads)} ${t.downloads}` : "",
    r.favorites ? `${count(r.favorites)} ${t.favorites}` : "",
    r.updated ? `${t.updatedOn} ${r.updated}` : "",
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
        <span style={{ ...buttonStyle, textAlign: "center", fontSize: "13px", color: theme.success.text,
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
      <h3 style={h3Style}>{title}</h3>
      {results === undefined ? null : results.length === 0 ? (
        <div style={hintStyle}>{t.noResults}</div>
      ) : (
        results.map((r) => <ResultRow key={`${r.provider}:${r.externalId}`} r={r} disabled={disabled} onInstall={onInstall} />)
      )}
    </div>
  );
}

export function GetAddonsPage({ state, refresh, inst, selectInstallation }: PageProps) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortOrder>("popular");
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [cfId, setCfId] = useState("");
  const handledJob = useRef<string | null>(null);

  const job = state.job;
  const running = job?.status === "running";
  const canInstall = !!state.wowup.path && !state.wowup.running && !running && inst?.hasGame !== false;

  const search = async (q: string, order: SortOrder = sort) => {
    if (!inst) return;
    // "best match" only means something with a query; without one the list is the popular one
    const effective: SortOrder = !q.trim() && order === "relevance" ? "popular" : order;
    setSort(effective);
    setLoading(true);
    try {
      setData(await searchAddons(inst.id, q, effective));
    } catch (e) {
      toaster.toast({ title: t.title, body: String(e) });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (inst) void search("", "popular");
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

  if (!inst) {
    return (
      <PageBody>
        <div style={hintStyle}>{t.noInstallations}</div>
      </PageBody>
    );
  }

  const searched = !!data?.query;
  // a new query starts with the best matches; a sort chosen for an earlier query is kept
  const submit = () => search(query, query.trim() && !searched ? "relevance" : sort);
  const sorts = SORTS.filter((o) => o !== "relevance" || query.trim() || searched);
  return (
    <PageBody>
      <Focusable flow-children="horizontal" style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <div style={hintStyle}>{t.getAddonsIntro}</div>
        {state.installations.length > 1 ? (
          <div style={{ minWidth: "280px" }}>
            <Dropdown rgOptions={state.installations.map((i) => ({ data: i.id, label: versionTitle(i) }))} selectedOption={inst.id}
              onChange={(o) => selectInstallation(o.data)} />
          </div>
        ) : (
          <div style={{ ...hintStyle, color: theme.text.primary }}>{versionTitle(inst)}</div>
        )}
      </Focusable>
      {inst.hasGame === false && <div style={{ ...hintStyle, color: theme.warning.text }}>{`${t.noGame}. ${t.noGameDesc}`}</div>}

      {running && <JobProgress message={job?.message || t.working} percent={job?.percent ?? null} />}
      {state.wowup.running && (
        <Focusable flow-children="horizontal" style={{ ...rowStyle, background: theme.warning.bg }}>
          <div style={{ flex: 1, fontSize: "13px", color: theme.warning.text }}>{t.wowupRunning}</div>
          <DialogButton style={buttonStyle} onClick={() => closeWowupWindow(state)}>{t.closeWowup}</DialogButton>
        </Focusable>
      )}

      <InlineField label={t.searchLabel}>
        <div style={{ flex: 1 }}>
          <TextField value={query} bShowClearAction
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") void submit(); }} />
        </div>
        <DialogButton style={buttonStyle} disabled={loading} onClick={() => void submit()}>
          {loading ? t.searching : t.search}
        </DialogButton>
      </InlineField>
      <Focusable flow-children="horizontal" style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <div style={hintStyle}>{t.sortBy}</div>
        <div style={{ minWidth: "240px" }}>
          <Dropdown rgOptions={sorts.map((o) => ({ data: o, label: t.sorts[o] }))} selectedOption={sort} disabled={loading}
            onChange={(o) => void search(data?.query ?? "", o.data as SortOrder)} />
        </div>
      </Focusable>
      <div style={{ ...hintStyle, fontSize: "12px" }}>{t.sortHint}</div>
      {data?.errors.map((e) => <div key={e} style={{ fontSize: "13px", color: theme.error.text }}>{e}</div>)}

      <ResultSection title={searched ? t.resultsWowi : t.popularWowi} results={data?.wowinterface} disabled={!canInstall}
        onInstall={(r) => void install([{ provider: r.provider, externalId: r.externalId, name: r.name }])} />
      <ResultSection title={searched ? t.resultsHub : t.featuredHub} results={data?.hub} disabled={!canInstall}
        onInstall={(r) => void install([{ provider: r.provider, externalId: r.externalId, name: r.name }])} />

      <h3 style={h3Style}>{t.curseforge}</h3>
      <div style={hintStyle}>{t.curseforgeIntro}</div>
      <InlineField label={t.cfProjectId}>
        <div style={{ flex: 1 }}>
          <TextField value={cfId} mustBeNumeric
            onChange={(e) => setCfId(e.target.value.replace(/\D/g, "").slice(0, 12))} />
        </div>
        <DialogButton style={buttonStyle} disabled={!canInstall || !cfId}
          onClick={() => void install([{ provider: "Curse", externalId: cfId, name: "" }])}>
          {t.install}
        </DialogButton>
      </InlineField>
      <ButtonRow>
        <Button width="320px" disabled={!state.wowup.path || running || state.wowup.running}
          onClick={() => void openWowupWindow(state)}>
          {t.openWowup}
        </Button>
        <div style={hintStyle}>{t.openWowupHint}</div>
      </ButtonRow>
    </PageBody>
  );
}
