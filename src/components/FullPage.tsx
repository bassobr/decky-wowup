import { DialogButton, Focusable, gamepadDialogClasses } from "@decky/ui";
import { toaster } from "@decky/api";
import { CSSProperties, ReactNode } from "react";
import { t } from "../strings";
import { theme } from "../theme";
import type { JobStart } from "../types";

// SidebarNavigation already ends its scroll area above Steam's button-hint footer; a little room at the
// end keeps the last element from touching it.
const FOOTER_CLEARANCE = "24px";

// Steam's TextField is a Field: label row, vertical padding and a bottom separator. Next to a button
// that made the button sit lower than the input. Inside .wa-inline-field the Field is flattened, and
// the label is rendered by us above the row.
const INLINE_FIELD_CSS = `
.wa-inline-field .${gamepadDialogClasses?.Field ?? "wa-none"} { padding-top: 0 !important; padding-bottom: 0 !important; margin: 0 !important; }
.wa-inline-field .${gamepadDialogClasses?.WithBottomSeparatorStandard ?? "wa-none"}::after,
.wa-inline-field .${gamepadDialogClasses?.WithBottomSeparator ?? "wa-none"}::after,
.wa-inline-field .${gamepadDialogClasses?.WithBottomSeparatorThick ?? "wa-none"}::after { display: none !important; }
`;

export const rowStyle: CSSProperties = {
  display: "flex", alignItems: "center", gap: "12px", padding: "10px 12px", borderRadius: theme.radius.lg,
  background: theme.surface.sm,
};
export const buttonStyle: CSSProperties = { width: "140px", minWidth: "140px", padding: "8px 0" };
export const hintStyle: CSSProperties = { fontSize: "13px", color: theme.text.secondary, lineHeight: 1.4 };
export const h3Style: CSSProperties = { margin: "14px 0 2px", fontSize: "17px" };

/** Content of one page of the central view: a vertical column with room for Steam's footer. */
export function PageBody({ children }: { children: ReactNode }) {
  return (
    <Focusable flow-children="vertical" style={{ display: "flex", flexDirection: "column", gap: "12px", color: "#fff",
      paddingBottom: FOOTER_CLEARANCE, boxSizing: "border-box" }}>
      <style>{INLINE_FIELD_CSS}</style>
      {children}
    </Focusable>
  );
}

/** A card with a title, a few text lines and buttons on the right. */
export function Row({ title, lines, children, tone }: {
  title: ReactNode; lines?: (ReactNode | null | undefined | false)[]; children?: ReactNode; tone?: "warning";
}) {
  return (
    <Focusable style={{ ...rowStyle, ...(tone === "warning" ? { background: theme.warning.bg } : {}) }}
      flow-children="horizontal" onActivate={children ? undefined : () => undefined}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: "15px", fontWeight: 600, color: theme.text.primary, overflowWrap: "anywhere" }}>{title}</div>
        {(lines ?? []).filter(Boolean).map((l, i) => (
          <div key={i} style={{ fontSize: "12px", color: i === 0 ? theme.text.secondary : theme.text.muted, marginTop: "2px",
            overflowWrap: "anywhere" }}>
            {l}
          </div>
        ))}
      </div>
      {children}
    </Focusable>
  );
}

/** Buttons side by side. */
export function ButtonRow({ children }: { children: ReactNode }) {
  return (
    <Focusable flow-children="horizontal" style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
      {children}
    </Focusable>
  );
}

export function Button({ children, onClick, disabled, width }: {
  children: ReactNode; onClick: () => void; disabled?: boolean; width?: string;
}) {
  return (
    <DialogButton style={width ? { width, minWidth: width, padding: "8px 12px" } : buttonStyle} disabled={disabled}
      onClick={onClick}>
      {children}
    </DialogButton>
  );
}

/** A text field and its buttons on one line, vertically centred; the label sits above. */
export function InlineField({ label, children }: { label?: string; children: ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      {label && (
        <div style={{ fontSize: "13px", letterSpacing: "0.04em", textTransform: "uppercase", color: theme.text.secondary }}>
          {label}
        </div>
      )}
      <Focusable className="wa-inline-field" flow-children="horizontal"
        style={{ display: "flex", gap: "10px", alignItems: "center" }}>
        {children}
      </Focusable>
    </div>
  );
}

/** Start a backend job and report "busy" or errors as a toast; the state is refreshed either way. */
export function makeAct(refresh: (full?: boolean) => Promise<void>) {
  return async (fn: () => Promise<unknown>) => {
    try {
      const res = (await fn()) as Partial<JobStart> | undefined;
      if (res && res.started === false) toaster.toast({ title: t.title, body: t.busy });
    } catch (e) {
      toaster.toast({ title: t.title, body: String(e) });
    } finally {
      void refresh();
    }
  };
}
