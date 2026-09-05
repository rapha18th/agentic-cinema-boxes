import { useEffect, useRef } from "react";

export interface Progress {
  phase?: string;
  depth?: string;
  round?: number;
  max_rounds?: number;
  objective?: string;
  objective_index?: number;
  objective_count?: number;
  objectives_total?: number;
  evidence?: number;
  confidence?: number;
  coverage?: number;
}

const PHASE_LABEL: Record<string, string> = {
  planning: "DRAWING THE PLAN",
  planned: "PLAN SET",
  researching: "ACQUIRING",
  scoring: "MEASURING COVERAGE",
  verifying: "CROSS-EXAMINING SOURCES",
  done: "RESEARCH COMPLETE",
};

function Bar({ label, value, tone = "amber" }: { label: string; value: number; tone?: string }) {
  const pct = Math.max(0, Math.min(1, value || 0));
  const cells = 32;
  const on = Math.round(pct * cells);
  return (
    <div className="rc-bar">
      <span className="rc-bar-label">{label}</span>
      <span className={`rc-bar-track tone-${tone}`}>
        {"█".repeat(on)}<span className="rc-bar-off">{"─".repeat(cells - on)}</span>
      </span>
      <span className="rc-bar-pct">{Math.round(pct * 100)}%</span>
    </div>
  );
}

export function ResearchConsole({
  progress, log, done, disconnected, errorText,
}: {
  progress: Progress;
  log: string[];
  done: boolean;
  disconnected?: boolean;
  errorText?: string;
}) {
  const p = progress;
  const phase = PHASE_LABEL[p.phase ?? ""] ?? (p.phase ?? "STANDING BY").toUpperCase();
  const objN = (p.objective_index ?? 0) + 1;
  const objT = p.objective_count ?? p.objectives_total ?? 0;
  const round = p.round ?? 0;
  const maxR = p.max_rounds ?? 0;

  const tailRef = useRef<HTMLDivElement>(null);
  useEffect(() => { tailRef.current?.scrollIntoView({ block: "end" }); }, [log]);

  return (
    <div className={`rc ${done ? "rc-done" : ""}`}>
      <div className="rc-scan" />
      <div className="rc-head">
        <span className="rc-depth">{(p.depth ?? "scout").toUpperCase()} RESEARCH</span>
        <span className="rc-round">PASS {round}{maxR ? ` / ${maxR}` : ""}</span>
      </div>

      <div className="rc-phase">
        {phase}
        {!done && <span className="rc-cursor">▊</span>}
      </div>
      {p.objective && !done && (
        <div className="rc-obj">
          OBJECTIVE {objN}{objT ? ` / ${objT}` : ""} · <b>{p.objective}</b>
        </div>
      )}

      <div className="rc-bars">
        {objT > 0 && !done && <Bar label="OBJECTIVE " value={objN / objT} tone="dim" />}
        <Bar label="COVERAGE  " value={p.coverage ?? 0} tone="amber" />
        <Bar label="READINESS " value={p.confidence ?? 0} tone="red" />
      </div>

      <div className="rc-count">{p.evidence ?? 0} FRAGMENTS INDEXED</div>

      {errorText
        ? <div className="rc-note rc-err">RUN ENDED WITH AN ERROR · {errorText}</div>
        : disconnected && !done
          ? <div className="rc-note rc-warn">
              LIVE FEED LOST · THE RUN CONTINUES ON THE SERVER · THIS PAGE KEEPS UPDATING FROM SAVED DATA
            </div>
          : null}

      <div className="rc-log">
        {log.slice(-9).map((l, i) => <div key={i}>{l}</div>)}
        <div ref={tailRef} />
      </div>
    </div>
  );
}
