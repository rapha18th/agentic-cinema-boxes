import { useState } from "react";

interface Run {
  run: number;
  sources_examined?: number;
  evidence_indexed?: number;
  images_indexed?: number;
  sources_extracted?: number;
  coverage_before?: number;
  coverage_after?: number;
  confidence_before?: number;
  confidence_after?: number;
  new_boxes?: string[];
  conflicts?: string[];
  searches?: { objective: string; queries: string[] }[];
  next_action?: string;
}
interface Ev {
  id: string;
  round?: number;
  modality?: string;
  title?: string;
  text?: string;
  url?: string;
  image_url?: string;
  source_domain?: string;
  publish_date?: string;
}

const pct = (x?: number) => `${Math.round((x ?? 0) * 100)}%`;

function cite(e: Ev) {
  return [e.title || e.source_domain || e.url, e.publish_date].filter(Boolean).join(" · ");
}

export function Ledger({ runs, evidence }: { runs: Run[]; evidence: Ev[] }) {
  const [open, setOpen] = useState<number | null>(runs.length ? runs[runs.length - 1].run : null);
  if (!runs.length) return <p className="muted">No research run yet.</p>;

  return (
    <div className="ledger">
      {runs.map((r) => {
        const mine = evidence.filter((e) => (e.round ?? 0) === r.run);
        const isOpen = open === r.run;
        return (
          <div className="run" key={r.run}>
            <button className="run-head linkish" onClick={() => setOpen(isOpen ? null : r.run)}>
              {isOpen ? "▾" : "▸"} RESEARCH RUN {String(r.run).padStart(3, "0")}
              <span className="muted"> — conf {pct(r.confidence_before)} → {pct(r.confidence_after)}</span>
            </button>
            {isOpen && (
              <div className="run-body">
                <div>{r.sources_examined ?? 0} sources · {r.evidence_indexed ?? 0} fragments
                  {!!r.images_indexed && <> · {r.images_indexed} images</>}
                  {!!r.sources_extracted && <> · {r.sources_extracted} via Extract</>}
                </div>
                <div>coverage {pct(r.coverage_before)} → {pct(r.coverage_after)}</div>
                {!!r.new_boxes?.length && (
                  <div className="new">opened: {r.new_boxes.join(", ")}</div>
                )}
                {!!r.conflicts?.length && (
                  <div className="conflict">{r.conflicts.map((c, i) => <div key={i}>! {c}</div>)}</div>
                )}
                {!!r.searches?.length && (
                  <div className="searches">
                    {r.searches.map((s, i) => (
                      <div key={i}><b>{s.objective}</b>{s.queries.map((q, j) => <div className="muted q" key={j}>q: {q}</div>)}</div>
                    ))}
                  </div>
                )}
                {!!mine.length && (
                  <details className="round-ev">
                    <summary>{mine.length} evidence items this round</summary>
                    {mine.map((e) => (
                      <div className="ev-row" key={e.id}>
                        {e.modality === "image" && e.image_url && (
                          <img className="ev-thumb" src={e.image_url} alt="" loading="lazy" />
                        )}
                        <div>
                          {e.url
                            ? <a href={e.url} target="_blank" rel="noopener">{cite(e)}</a>
                            : <span>{cite(e)}</span>}
                          <div className="muted">{(e.text || "").slice(0, 140)}</div>
                        </div>
                      </div>
                    ))}
                  </details>
                )}
                {r.next_action && <div className="next">→ {r.next_action}</div>}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
