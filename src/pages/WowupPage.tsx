import { adoptWowup, applyWowupUpdate, checkWowupUpdate, installWowup } from "../backend";
import { Button, ButtonRow, h3Style, hintStyle, makeAct, PageBody, Row } from "../components/FullPage";
import { JobProgress } from "../components/JobProgress";
import { closeWowupWindow, openWowupWindow } from "../steam/wowupShortcut";
import { t } from "../strings";
import { theme } from "../theme";
import type { PageProps } from "./MainView";

export function WowupPage({ state: s, refresh }: PageProps) {
  const act = makeAct(refresh);
  const running = s.job?.status === "running";
  const w = s.wowup;

  return (
    <PageBody>
      {running && <JobProgress message={s.job?.message || t.working} percent={s.job?.percent ?? null} />}
      {w.path ? (
        <>
          <Row title={`${t.wowup} ${w.version ?? ""}`}
            lines={[`${w.verified ? t.verified : t.unverified} · ${t.channel} ${w.channel}`, `${t.wowupPath}: ${w.path}`]} />
          {w.running && <div style={{ ...hintStyle, color: theme.warning.text }}>{t.wowupRunning}</div>}
          {w.updateAvailable ? (
            <ButtonRow>
              <Button width="300px" disabled={running || w.running} onClick={() => void act(() => applyWowupUpdate())}>
                {`${t.updateWowup} → ${w.latestVersion}`}
              </Button>
              <div style={hintStyle}>{t.updateWowupDesc}</div>
            </ButtonRow>
          ) : (
            <ButtonRow>
              <Button width="300px" disabled={running} onClick={() => void act(() => checkWowupUpdate(true))}>{t.checkWowup}</Button>
              <div style={{ ...hintStyle, color: w.error ? theme.error.text : theme.text.secondary }}>
                {w.error ? `${t.updateFailed}: ${w.error}` : t.wowupUpToDate}
              </div>
            </ButtonRow>
          )}
          <h3 style={h3Style}>{t.openWowupApp}</h3>
          <div style={hintStyle}>{t.openWowupAppDesc}</div>
          <ButtonRow>
            <Button width="300px" disabled={running || w.running} onClick={() => void openWowupWindow(s)}>{t.openWowupApp}</Button>
            {w.running && <Button width="220px" onClick={() => closeWowupWindow(s)}>{t.closeWowup}</Button>}
          </ButtonRow>
        </>
      ) : (
        <>
          <div style={hintStyle}>{`${t.wowupMissing}. ${t.wowupMissingDesc}`}</div>
          {w.candidates.map((c) => (
            <Row key={c.path} title={`${t.wowup} ${c.version ?? ""}`} lines={[c.path]}>
              <Button width="200px" disabled={running} onClick={() => void act(() => adoptWowup(c.path))}>{t.useFound}</Button>
            </Row>
          ))}
          <ButtonRow>
            <Button width="300px" disabled={running} onClick={() => void act(() => installWowup(null))}>{t.installWowup}</Button>
            <div style={hintStyle}>{t.installWowupDesc}</div>
          </ButtonRow>
        </>
      )}
    </PageBody>
  );
}
