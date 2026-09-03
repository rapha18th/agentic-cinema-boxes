interface Run {
  run: number;
  sources_examined?: number;
  evidence_indexed?: number;
  sources_extracted?: number;
  coverage_before?: number;
  coverage_after?: number;
  confidence_before?: number;
  confidence_after?: number;
  new_boxes?: string[];
  conflicts?: string[];
  next_action?: string;
}

const pct = (x?: number) => `${Math.round((x ?? 0) * 100)}%`;

export function Ledger({ runs }: { runs: Run[] }) {
  if (!runs.length) return <p className="muted">No research run yet.</p>;
  return (
    <div className="ledger">
      {runs.map((r) => (
        <div className="run" key={r.run}>
          <div className="run-head">RESEARCH RUN {String(r.run).padStart(3, "0")}</div>
          <div>{r.sources_examined ?? 0} sources examined</div>
          <div>{r.evidence_indexed ?? 0} evidence fragments indexed</div>
          {!!r.sources_extracted && <div>{r.sources_extracted} sources enriched via Parallel Extract</div>}
          <div>coverage {pct(r.coverage_before)} → {pct(r.coverage_after)}</div>
          <div>confidence {pct(r.confidence_before)} → {pct(r.confidence_after)}</div>
          {!!r.new_boxes?.length && (
            <div className="new">new boxes opened:{r.new_boxes.map((b) => <div key={b}>+ {b}</div>)}</div>
          )}
          {!!r.conflicts?.length && (
            <div className="conflict">conflicts:{r.conflicts.map((c, i) => <div key={i}>! {c}</div>)}</div>
          )}
          {r.next_action && <div className="next">→ {r.next_action}</div>}
        </div>
      ))}
    </div>
  );
}
