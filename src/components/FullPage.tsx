import { Focusable, gamepadDialogClasses } from "@decky/ui";
import { CSSProperties, ReactNode } from "react";
import { theme } from "../theme";

// Steam draws its header (40px) and the button-hint footer (~42px, CSS px; scaled with the UI, e.g.
// ~75 device px on a 1080p Ally X) over full-screen routes. The scroll container starts below the
// header and the content keeps enough room at the end so the last element can scroll clear of the footer.
const FOOTER_CLEARANCE = "84px";

// Steam's TextField is a Field: label row, vertical padding and a bottom separator. Next to a button
// that made the button sit lower than the input. Inside .wa-inline-field the Field is flattened, and
// the label is rendered by us above the row.
const INLINE_FIELD_CSS = `
.wa-inline-field .${gamepadDialogClasses?.Field ?? "wa-none"} { padding-top: 0 !important; padding-bottom: 0 !important; margin: 0 !important; }
.wa-inline-field .${gamepadDialogClasses?.WithBottomSeparatorStandard ?? "wa-none"}::after,
.wa-inline-field .${gamepadDialogClasses?.WithBottomSeparator ?? "wa-none"}::after,
.wa-inline-field .${gamepadDialogClasses?.WithBottomSeparatorThick ?? "wa-none"}::after { display: none !important; }
`;

export function FullPage({ title, children }: { title: string; children: ReactNode }) {
  const inner: CSSProperties = {
    padding: `0 28px ${FOOTER_CLEARANCE}`, color: "#fff", maxWidth: "1100px", display: "flex",
    flexDirection: "column", gap: "12px", boxSizing: "border-box",
  };
  return (
    <div style={{ marginTop: "40px", height: "calc(100% - 40px)", overflowY: "auto", boxSizing: "border-box" }}>
      <style>{INLINE_FIELD_CSS}</style>
      <Focusable style={inner} flow-children="vertical">
        <h2 style={{ margin: "12px 0 0" }}>{title}</h2>
        {children}
      </Focusable>
    </div>
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
