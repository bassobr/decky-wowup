export type Compat = "ok" | "outdated" | "incompatible" | "unknown";
export type RunMode = "check" | "all" | "auto" | "selected";

export interface Addon {
  key: string;
  id: string | null;
  name: string;
  author: string | null;
  provider: string | null;
  externalId: string | null;
  installedVersion: string | null;
  latestVersion: string | null;
  needsUpdate: boolean;
  autoUpdate: boolean;
  ignored: boolean;
  channel: string;
  folders: string[];
  compat: Compat;
  interface: number | null;
  missing: boolean;
}

export interface Installation {
  id: string;
  clientType: number | null;
  clientTypeLabel: string;
  label: string;
  location: string;
  flavorDir: string;
  addonsDir: string | null;
  exists: boolean;
  selected: boolean;
  product: string | null;
  version: string | null;
  gameType: string | null;
  gameTypeLabel: string | null;
  interface: number | null;
  addonCount: number;
  updateCount: number;
  incompatibleCount: number;
  unmanaged: string[];
}

export interface Detected {
  product: string;
  subfolder: string;
  version: string | null;
  gameTypeLabel: string | null;
  clientTypeLabel: string | null;
  flavorDir: string;
  shortcut: string | null;
}

export interface Candidate {
  path: string;
  version: string | null;
  managed: boolean;
}

export interface WowUpInfo {
  path: string | null;
  version: string | null;
  verified: boolean | null;
  managed: boolean;
  running: boolean;
  profileExists: boolean;
  channel: string;
  candidates: Candidate[];
  latestVersion: string | null;
  updateAvailable: boolean;
  lastCheck: number | null;
  error: string | null;
}

export interface UpdatedAddon {
  key: string;
  name: string;
  from: string;
  to: string;
  installationId?: string;
}

export interface RunSummary {
  runId: string;
  mode: RunMode;
  installationId: string | null;
  ok: boolean;
  rc: number | null;
  timedOut: boolean;
  durationMs: number;
  quit: boolean;
  updated: UpdatedAddon[];
  errors: string[];
  pending: number | null;
  startedAt: string;
  finishedAt: string | null;
  snapshots: string[] | null;
}

export interface Job {
  id: string;
  kind: string;
  status: "running" | "done" | "error";
  message: string;
  percent: number | null;
  result: any;
  error: string | null;
  startedAt: string;
  finishedAt: string | null;
}

export interface JobStart {
  started: boolean;
  reason?: string;
  job: Job;
}

export interface SnapshotInfo {
  id: string;
  installationId: string | null;
  installationLabel?: string;
  label: string;
  createdAt: string;
  method: string;
}

export interface UpdateInfo {
  currentVersion: string;
  latestVersion: string | null;
  updateAvailable: boolean;
  releaseUrl?: string | null;
  checkedAt?: number | null;
  error?: string | null;
}

export interface UpdateArtifact {
  artifact: string;
  name: string;
  version: string;
  hash: string;
  detail?: string;
}

export interface Settings {
  wowup: { appImage: string | null; channel: string; autoCheck: boolean };
  runner: { timeoutSec: number; disableNotifications: boolean };
  snapshots: { keep: number };
  ui: { installationId: string | null; wowupShortcutAppId: number | null; wowupShortcutExe?: string | null };
  update: { autoCheck: boolean; autoRestartSteam?: boolean; error?: string | null };
}

export interface PluginState {
  version: string;
  wowup: WowUpInfo;
  installations: Installation[];
  addons: Record<string, Addon[]>;
  detected: Detected[];
  missingInWowUp: Detected[];
  lastRun: RunSummary | null;
  snapshots: SnapshotInfo[];
  warnings: string[];
  job: Job | null;
  settings: Settings;
  update: UpdateInfo;
  appEvents: { appId: string; running: boolean; name: string; at: string }[];
}

export interface SearchResult {
  provider: "WowInterface" | "WowUpHub" | "Curse";
  externalId: string;
  name: string;
  author: string;
  version: string;
  updated: string | null;
  downloads: number;
  monthly: number;
  gameTypes: string[];
  compatVersions: string[];
  folders: string[];
  url: string | null;
  thumbnail: string | null;
  summary: string;
  installed: boolean;
  present: boolean;
  compatible: boolean | null;
}

export interface SearchResponse {
  query: string;
  installationId: string;
  gameType: string | null;
  wowinterface: SearchResult[];
  hub: SearchResult[];
  errors: string[];
}

export interface InstallItem {
  provider: string;
  externalId: string;
  name: string;
}

export interface InstallResult {
  installed: { provider: string; externalId: string; name: string; version: string }[];
  failed: { provider: string; externalId: string; name: string; reason: string }[];
  skipped: { provider: string; externalId: string; name: string; reason: string }[];
}
