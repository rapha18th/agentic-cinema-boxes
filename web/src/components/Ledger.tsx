import { useState } from "react";
import { MODALITY_GLYPH } from "./Media";

interface Run {
  run: number;
  sources_examined?: number;
  evidence_indexed?: number;
  images_indexed?: number;
  media_indexed?: number;
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
  media_url?: string;
  media_mime?: string;
  source_domain?: string;
  publish_date?: string;
}

const pct = (x?: number) => `${Math.round((x ?? 0) * 100)}%`;

function cite(e: Ev) {
  return [e.title || e.source_domain || e.url, e.publish_date].filter(Boolean).join(" · ");
}

/** Strip the markdown/wiki syntax that leaks through raw scraped text so a
 *  one-line preview reads as a sentence, not a source dump. */
function snippet(text?: string) {
  const clean = (text || "")
    .replace(/\[\[([^\]|]+)(\|[^\]]+)?\]\]/g, "$1") // [[wiki links]]
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1") // [md links](url)
    .replace(/[#*_`>]+/g, "") // md punctuation
    .replace(/\{\{[^}]*\}\}/g, "") // {{templates}}
    .replace(/\s+/g, " ")
    .trim();
  return clean.length > 90 ? `${clean.slice(0, 90)}…` : clean;
}

export function Ledger({
  runs, evidence, onOpenEvidence,
}: {
  runs: Run[];
  evidence: Ev[];
  onOpenEvidence: (e: Ev) => void;
}) {
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
              <span className="muted"> · ready {pct(r.confidence_before)} → {pct(r.confidence_after)}</span>
            </button>
            {isOpen && (
              <div className="run-body">
                <div>{r.sources_examined ?? 0} sources · {r.evidence_indexed ?? 0} fragments
                  {!!r.images_indexed && <> · {r.images_indexed} images</>}
                  {!!r.media_indexed && <> · {r.media_indexed} docs/av</>}
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
                    <div className="round-ev-list">
                      {mine.map((e) => (
                        <button type="button" className="ev-row-compact" key={e.id}
                                onClick={() => onOpenEvidence(e)}>
                          <span className="ev-row-modality">{MODALITY_GLYPH[e.modality || "text"] || "·"}</span>
                          <span className="ev-row-cite">{cite(e)}</span>
                          <span className="ev-row-snip">{snippet(e.text)}</span>
                        </button>
                      ))}
                    </div>
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
