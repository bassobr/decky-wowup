import { addEventListener, removeEventListener, toaster } from "@decky/api";
import { useCallback, useEffect, useRef, useState } from "react";
import { getState } from "../backend";
import { t } from "../strings";
import type { InstallResult, Job, PluginState, RunSummary, UpdateInfo } from "../types";

function jobSummary(job: Job): string {
  if (job.status === "error") return `${t.jobDone[job.kind] ?? job.kind} ${t.jobFailed}: ${job.error ?? ""}`;
  if (job.kind === "run" && job.result) {
    const r = job.result as RunSummary;
    if (!r.ok) return `${t.jobDone.run}: ${r.timedOut ? t.timedOut : t.failed}`;
    const names = r.updated.map((u) => u.name).slice(0, 3).join(", ");
    return r.updated.length ? `${t.updatedN(r.updated.length)}: ${names}` : `${t.jobDone.run}: ${t.nothingUpdated}`;
  }
  if (job.kind === "install" && job.result) {
    const r = job.result as InstallResult;
    const parts = [];
    if (r.installed.length) parts.push(t.installedN(r.installed.map((i) => i.name || i.externalId).join(", ")));
    if (r.failed.length) parts.push(t.failedN(r.failed.length));
    if (!parts.length && r.skipped.length) parts.push(`${r.skipped.map((i) => i.name || i.externalId).join(", ")}: ${t.installedBadge}`);
    return parts.join(" · ") || (t.jobDone.install ?? job.kind);
  }
  return t.jobDone[job.kind] ?? job.kind;
}

export function usePluginState() {
  const [state, setState] = useState<PluginState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const lastToast = useRef<string | null>(null);

  const refresh = useCallback(async (full = false) => {
    try {
      setState(await getState(full));
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    void refresh(true);
    const onJob = (job: Job) => {
      setState((s) => (s ? { ...s, job } : s));
      if (job.status !== "running" && lastToast.current !== job.id) {
        lastToast.current = job.id;
        toaster.toast({ title: t.title, body: jobSummary(job) });
        void refresh();
      }
    };
    const onChanged = () => void refresh();
    const onUpdate = (u: UpdateInfo) => setState((s) => (s ? { ...s, update: u } : s));
    addEventListener<[Job]>("job", onJob);
    addEventListener<[unknown]>("state_changed", onChanged);
    addEventListener<[UpdateInfo]>("update_state", onUpdate);
    return () => {
      removeEventListener("job", onJob);
      removeEventListener("state_changed", onChanged);
      removeEventListener("update_state", onUpdate);
    };
  }, [refresh]);

  return { state, error, refresh };
}
