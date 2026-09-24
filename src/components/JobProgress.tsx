import { ProgressBar } from "@decky/ui";
import { theme } from "../theme";

// Bar drawn with plain divs, used when Steam's ProgressBar module can't be located
// (findModuleExport returns undefined after a Steam client update).
function FallbackBar({ percent, indeterminate }: { percent: number; indeterminate: boolean }) {
  return (
    <div style={{ position: "relative", width: "100%", height: "6px", borderRadius: "3px", overflow: "hidden",
      background: theme.surface.lg }}>
      <style>{`@keyframes wa-indeterminate{0%{left:-40%}100%{left:100%}}`}</style>
      <div style={{
        position: "absolute", top: 0, bottom: 0, left: 0, borderRadius: "3px", background: theme.info.text,
        width: indeterminate ? "40%" : `${Math.max(0, Math.min(100, percent))}%`,
        transition: indeterminate ? "none" : "width 0.4s ease",
        animation: indeterminate ? "wa-indeterminate 1.4s ease-in-out infinite" : "none",
      }} />
    </div>
  );
}

// Deliberately not ProgressBarWithInfo: that component is a Steam Field, which puts the bar into the
// right-hand value column next to an empty label column, far to the right (same fix as the CachyOS
// Updater). Steam's raw ProgressBar in a full-width div sidesteps the Field; the text is ours.
export function JobProgress({ message, percent }: { message: string; percent: number | null }) {
  const indeterminate = percent == null || percent <= 2;
  return (
    <div style={{ width: "100%", boxSizing: "border-box", padding: "4px 0" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "8px",
        marginBottom: "6px", fontSize: theme.fontSize.body, color: theme.text.primary }}>
        <span style={{ overflowWrap: "anywhere" }}>{message}</span>
        {!indeterminate && (
          <span style={{ flexShrink: 0, fontSize: theme.fontSize.small, color: theme.text.secondary }}>
            {Math.round(percent ?? 0)}%
          </span>
        )}
      </div>
      <div style={{ width: "100%" }}>
        {ProgressBar ? (
          <ProgressBar nProgress={indeterminate ? 0 : percent ?? 0} indeterminate={indeterminate} focusable={false} />
        ) : (
          <FallbackBar percent={percent ?? 0} indeterminate={indeterminate} />
        )}
      </div>
    </div>
  );
}
