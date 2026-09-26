import { Focusable } from "@decky/ui";
import { toaster } from "@decky/api";
import { useState } from "react";
import { getDiagnostics } from "../backend";
import { Button, ButtonRow, h3Style, hintStyle, PageBody, Row } from "../components/FullPage";
import { t } from "../strings";
import { theme } from "../theme";
import { FRONTEND_VERSION } from "../version";
import type { PageProps } from "./MainView";

export function NotesPage({ state: s }: PageProps) {
  const [diag, setDiag] = useState<string | null>(null);
  const load = async () => {
    try {
      setDiag((await getDiagnostics()).text);
    } catch (e) {
      toaster.toast({ title: t.title, body: String(e) });
    }
  };

  return (
    <PageBody>
      {s.warnings.length === 0 && <div style={hintStyle}>{t.noNotes}</div>}
      {s.warnings.map((w) => <Row key={w} tone="warning" title={w} />)}

      <h3 style={h3Style}>{t.diagnostics}</h3>
      <div style={hintStyle}>{`${t.pluginVersion} ${s.version} (UI ${FRONTEND_VERSION}). ${t.pluginUpdatesInQam}`}</div>
      <ButtonRow>
        <Button width="260px" onClick={() => void load()}>{t.showDiagnostics}</Button>
        <div style={hintStyle}>{t.diagnosticsDesc}</div>
      </ButtonRow>
      {/* one focusable block per line, so the D-pad scrolls through long output */}
      {diag?.split("\n").filter((p) => p.trim()).map((p, i) => (
        <Focusable key={i} onActivate={() => undefined}
          style={{ background: theme.surface.sm, borderRadius: theme.radius.lg, padding: "8px 12px" }}>
          <pre style={{ margin: 0, fontSize: "12px", color: theme.text.primary, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{p}</pre>
        </Focusable>
      ))}
    </PageBody>
  );
}
