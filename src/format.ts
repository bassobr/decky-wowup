import { t } from "./strings";
import type { Addon, Installation, UpdatedAddon } from "./types";

export function when(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString([], { dateStyle: "short", timeStyle: "short" });
}

export function count(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
  return String(n);
}

/** "Retail 12.1.0.69933", with a custom WowUp label in front when there is one. */
export function versionTitle(i: Installation): string {
  const kind = i.gameTypeLabel ?? i.clientTypeLabel;
  const label = i.label && i.label !== "World of Warcraft" && i.label !== kind ? `${i.label} – ` : "";
  return `${label}${kind}${i.version ? ` ${i.version}` : ""}`;
}

export function sortAddons(list: Addon[]): Addon[] {
  const rank = (a: Addon) => (a.needsUpdate ? 0 : a.compat === "incompatible" ? 1 : a.compat === "outdated" ? 2 : 3);
  return [...list].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
}

export function addonLine(a: Addon): string {
  const parts = [a.needsUpdate ? `${a.installedVersion ?? "?"} → ${a.latestVersion ?? "?"}` : a.installedVersion ?? "?"];
  if (a.provider) parts.push(a.provider);
  if (t.compat[a.compat]) parts.push(t.compat[a.compat]);
  if (a.ignored) parts.push(t.ignored);
  if (a.missing) parts.push(t.missingFolders);
  return parts.join(" · ");
}

export function updatedLine(u: UpdatedAddon): string {
  return !u.from || u.from === "0" ? `${u.name} (${t.installedLabel} ${u.to})` : `${u.name} ${u.to}`;
}
