import { useState, type ReactNode } from "react";
import { ResearchMap } from "../components/ResearchMap";
import { Ledger } from "../components/Ledger";
import { MediaBit } from "../components/Media";
import { isInteractiveClick } from "../components/EvidenceModal";
import { DEPARTMENTS, DEPT_LABEL } from "../departments";
import type { Evidence, ResearchBox, ResearchRun, Verdict } from "../types";

export const pctOf = (x?: number) => `${Math.round((x ?? 0) * 100)}%`;
export type TabId = "overview" | "departments" | "evidence" | "trace" | "prior-art";
export const TAB_IDS: TabId[] = ["overview", "departments", "evidence", "trace", "prior-art"];

const cite = (e: Evidence) =>
  [e.title || e.source_domain, e.publish_date].filter(Boolean).join(" · ");

/** External text (scraped pages, TMDB synopses) arrives with nav chrome, wiki
 *  syntax, and em dashes the house style avoids. Normalise it for display. */
export function tidy(text?: string): string {
  return (text || "").replace(/\s*[—–]\s*/g, ", ").replace(/\s+/g, " ").trim();
}
export function cleanText(text?: string, max = 240): string {
  const clean = tidy(
    (text || "")
      .replace(/^\s*[|#>*-]+\s*/, "")
      .replace(/\[\[([^\]|]+)(\|[^\]]+)?\]\]/g, "$1")
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .replace(/\{\{[^}]*\}\}/g, "")
      .replace(/[`*_#>]+/g, "")
      .replace(/\s*(Home|Menu|Search|Close|Skip to content|Log ?in|Sign ?in)\s*[·|]+/gi, " "),
  );
  return clean.length > max ? `${clean.slice(0, max).trimEnd()}…` : clean;
}
const presentDepts = (boxes: ResearchBox[]) =>
  DEPARTMENTS.filter((d) => boxes.some((b) => b.departments?.includes(d)));

/** Map every fragment that appears in a verdict to that verdict, so the same
 *  cross-examination shows on the evidence cards and the map, not only on the
 *  Trace tab. */
export function conflictMap(verdicts: Verdict[]): Record<string, Verdict> {
  const m: Record<string, Verdict> = {};
  for (const v of verdicts) {
    if (v.a_id) m[v.a_id] = v;
    if (v.b_id) m[v.b_id] = v;
  }
  return m;
}
export const conflictIdSet = (verdicts: Verdict[]) =>
  new Set(verdicts.flatMap((v) => [v.a_id, v.b_id].filter(Boolean) as string[]));

/* ── evidence cards, multimodal ────────────────────────────────────── */
export function EvidenceCards({
  items, onOpen, limit, conflicts,
}: {
  items: Evidence[];
  onOpen: (e: Evidence) => void;
  limit?: number;
  conflicts?: Record<string, Verdict>;
}) {
  const [all, setAll] = useState(false);
  const shown = limit && !all ? items.slice(0, limit) : items;
  return (
    <>
      <div className="evgrid">
        {shown.map((e, idx) => {
          const v = conflicts?.[e.id];
          return (
            <div className={`evcard${v ? ` conflicted ${v.relation}` : ""}`} key={`${e.id}-${idx}`} role="button" tabIndex={0}
                 onClick={(ev) => { if (!isInteractiveClick(ev)) onOpen(e); }}
                 onKeyDown={(ev) => {
                   if ((ev.key === "Enter" || ev.key === " ") && !isInteractiveClick(ev)) onOpen(e);
                 }}>
              <div className="evcard-tags">
                <span className={`source-badge ${e.source_tier || "web"}`}>{e.source_tier || "web source"}</span>
                {v && <span className="conflict-tag">{v.relation === "contradicts" ? "in conflict" : "context flagged"}</span>}
              </div>
              {e.modality && e.modality !== "text"
                ? <MediaBit e={e} size="full" />
                : <div className="evtext">{cleanText(e.text)}</div>}
              <div className="muted">
                {e.url
                  ? <a href={e.url} target="_blank" rel="noopener">{cite(e) || e.url}</a>
                  : cite(e)}
                {e.source === "director" ? " · your upload" : ""}
              </div>
            </div>
          );
        })}
      </div>
      {limit && items.length > limit && (
        <button className="ghost show-more" onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show all ${items.length}`}
        </button>
      )}
    </>
  );
}

/* ── overview ──────────────────────────────────────────────────────── */
export function OverviewTab({
  overview, boxes, highlights, reel, onOpen, onGoto, sideSlot, conflicts,
}: {
  overview?: string;
  boxes: ResearchBox[];
  highlights: Evidence[];
  reel?: any[];
  onOpen: (e: Evidence) => void;
  onGoto?: (tab: TabId, boxId?: string) => void;
  sideSlot?: ReactNode;
  conflicts?: Record<string, Verdict>;
}) {
  const sorted = [...boxes].sort((a, b) => (a.score ?? 0) - (b.score ?? 0));
  return (
    <>
      <section className="brief-lead">
        <div>
          <p className="eyebrow">The research picture</p>
          <h2 className="display-heading">
            {overview || (boxes.length
              ? "The archive is ready to turn evidence into production decisions."
              : "Start a research run to build the world behind this premise.")}
          </h2>
        </div>
        <aside className="decision-card">
          <span className="signal">Next decision</span>
          <b>{sorted[0]?.name || "Draw the research plan"}</b>
          <p>{sorted[0]?.rationale || sorted[0]?.description
            || "The agent will identify the first evidence gap and pursue it."}</p>
        </aside>
      </section>

      {!!highlights.length && (
        <section className="card">
          <div className="section-head">
            <div><p className="eyebrow">Strongest evidence</p>
              <h2 className="display-heading small">What the crew can use now</h2></div>
            {onGoto && <button className="ghost" onClick={() => onGoto("evidence")}>Audit evidence →</button>}
          </div>
          <EvidenceCards items={highlights} onOpen={onOpen} conflicts={conflicts} />
        </section>
      )}

      <section className="risk-grid">
        <div className="card">
          <p className="eyebrow">Thin research boxes</p>
          {sorted.slice(0, 3).map((b) => (
            <button className="risk-row" key={b.id} onClick={() => onGoto?.("evidence", b.id)}>
              <span>{b.name}</span><b>{pctOf(b.score)}</b>
              <small>{b.distinct_domains ?? 0} independent domains</small>
            </button>
          ))}
          {!boxes.length && <p className="muted">The first run will make gaps explicit.</p>}
        </div>
        {sideSlot}
      </section>

      {!!reel?.length && (
        <section className="card">
          <p className="eyebrow">Reference sequence</p>
          {reel.map((b: any, i: number) => (
            <div className="beat" key={i}>
              <div><b>{b.t}</b> {b.title} · {b.note}</div>
              <div className="beat-src">
                {(b.sources || []).map((s: Evidence, j: number) => (
                  <button key={j} className="src-link" onClick={() => onOpen(s)}>
                    {(s as any).cite || s.title || `source ${j + 1}`}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </section>
      )}
    </>
  );
}

/* ── departments: expandable, evidence per box, multimodal ─────────── */
export function DepartmentsTab({
  boxes, evidence, onOpen, conflicts,
}: {
  boxes: ResearchBox[];
  evidence: Evidence[];
  onOpen: (e: Evidence) => void;
  conflicts?: Record<string, Verdict>;
}) {
  const present = presentDepts(boxes);
  if (!present.length) {
    return <div className="card"><p className="muted">Department packets appear after the plan is drawn.</p></div>;
  }
  return (
    <div className="department-stack">
      {present.map((d, i) => {
        const mine = boxes.filter((b) => b.departments?.includes(d));
        const ids = new Set(mine.map((b) => b.id));
        const count = evidence.filter((e) => ids.has(e.objective_id || "")).length;
        return (
          <details className="card department-card" key={d} open={i === 0}>
            <summary>
              <span className="dept-name">{DEPT_LABEL[d] || d}</span>
              <span className="muted">{mine.length} {mine.length === 1 ? "box" : "boxes"} · {count} sources</span>
            </summary>
            <div className="department-body">
              {mine.map((b) => {
                const bev = evidence.filter((e) => e.objective_id === b.id);
                return (
                  <section className="dept-box" key={b.id}>
                    <header>
                      <b>{b.name}{b.emergent ? " ✦" : ""}</b>
                      <span className="muted">{pctOf(b.score)} ready · {b.distinct_domains ?? 0} domains</span>
                    </header>
                    {(b.summary || b.description) && (
                      <p className="dept-box-note">{b.summary || b.description}</p>
                    )}
                    {!!bev.length && <EvidenceCards items={bev} onOpen={onOpen} limit={4} conflicts={conflicts} />}
                  </section>
                );
              })}
            </div>
          </details>
        );
      })}
    </div>
  );
}

/* ── evidence: semantic map, All / department splits, modals ───────── */
export function EvidenceTab({
  boxes, evidence, selBox, setSelBox, dept, setDept, onOpen, footer, conflicts,
}: {
  boxes: ResearchBox[];
  evidence: Evidence[];
  selBox: string | null;
  setSelBox: (id: string | null) => void;
  dept: string | null;
  setDept: (d: string | null) => void;
  onOpen: (e: Evidence) => void;
  footer?: ReactNode;
  conflicts?: Record<string, Verdict>;
}) {
  const conflictIds = conflicts ? new Set(Object.keys(conflicts)) : undefined;
  const present = presentDepts(boxes);
  const fboxes = dept ? boxes.filter((b) => b.departments?.includes(dept)) : boxes;
  const fids = new Set(fboxes.map((b) => b.id));
  const fev = dept ? evidence.filter((e) => fids.has(e.objective_id || "")) : evidence;
  const sel = selBox ? evidence.filter((e) => e.objective_id === selBox) : [];
  const selName = boxes.find((b) => b.id === selBox)?.name;
  return (
    <>
      <section className="card">
        <div className="section-head">
          <div><p className="eyebrow">Semantic evidence space</p>
            <h2 className="display-heading small">Every claim remains inspectable</h2></div>
          <span className="muted">click a box or fragment</span>
        </div>
        {!!present.length && (
          <div className="dept-bar">
            <button className={`chip ${!dept ? "on" : ""}`}
                    onClick={() => { setDept(null); setSelBox(null); }}>All</button>
            {present.map((d) => (
              <button key={d} className={`chip ${dept === d ? "on" : ""}`}
                      onClick={() => { setDept(dept === d ? null : d); setSelBox(null); }}>
                {DEPT_LABEL[d] || d}
              </button>
            ))}
          </div>
        )}
        <ResearchMap boxes={fboxes} evidence={fev} selected={selBox}
                     onSelect={setSelBox} onOpenEvidence={onOpen} conflictIds={conflictIds} />
        <div className="boxwrap">
          {[...fboxes].sort((a, b) => (a.score ?? 0) - (b.score ?? 0)).map((b) => {
            const c = evidence.filter((e) => e.objective_id === b.id).length;
            return (
              <button className={`box ${selBox === b.id ? "on" : ""}`} key={b.id}
                      onClick={() => setSelBox(selBox === b.id ? null : b.id)}>
                <div className="box-name">{b.name}{b.emergent ? " ✦" : ""}</div>
                <div className="bar"><span style={{ width: `${(b.score ?? 0) * 100}%` }} /></div>
                <div className="muted">{Math.max(b.evidence_count ?? 0, c)} items · {b.distinct_domains ?? 0} domains</div>
              </button>
            );
          })}
        </div>
      </section>
      {selBox && (
        <section className="card">
          <h3>{selName} · {sel.length} items</h3>
          <EvidenceCards items={sel} onOpen={onOpen} conflicts={conflicts} />
        </section>
      )}
      {footer}
    </>
  );
}

/* ── trace: decision timeline, ledger, verdicts ───────────────────── */
type Step = { label: string; detail: string; kind?: string };

export function deriveTimeline(
  runs: ResearchRun[], verdicts: Verdict[], boxes: ResearchBox[], stopReason?: string,
): Step[] {
  const steps: Step[] = [];
  if (boxes.length) {
    steps.push({ label: "Planned", detail: `${boxes.length} research boxes from the premise` });
  }
  runs.forEach((r) => {
    steps.push({
      label: `Round ${r.run}`,
      detail: `${r.sources_examined ?? 0} sources examined · ${r.sources_extracted ?? 0} extracted · ${r.evidence_indexed ?? 0} fragments kept`,
    });
    (r.new_boxes || []).forEach((nb) =>
      steps.push({ label: "Opened a box", detail: `${nb}, a signal that kept recurring across the evidence`, kind: "new" }));
  });
  verdicts.forEach((v) =>
    steps.push({ label: `Cross-examined · ${v.relation}`, detail: `${v.a_cite}  vs  ${v.b_cite}` }));
  if (stopReason) steps.push({ label: "Stopped", detail: stopReason, kind: "done" });
  return steps;
}

export function TraceTab({
  runs, verdicts, boxes, evidence, onOpen, activityLines, consoleSlot, stopReason,
}: {
  runs: ResearchRun[];
  verdicts: Verdict[];
  boxes: ResearchBox[];
  evidence: Evidence[];
  onOpen: (e: Evidence) => void;
  activityLines?: string[];
  consoleSlot?: ReactNode;
  stopReason?: string;
}) {
  const steps: Step[] = activityLines?.length
    ? activityLines.map((line, i) => ({ label: String(i + 1).padStart(2, "0"), detail: line }))
    : deriveTimeline(runs, verdicts, boxes, stopReason);
  return (
    <>
      {consoleSlot}
      <section className="trace-grid">
        <div className="card">
          <p className="eyebrow">Agent decisions</p>
          <div className="decision-timeline">
            {steps.length ? steps.map((s, i) => (
              <div key={i} className={s.kind || ""}><b>{s.label}</b><p>{s.detail}</p></div>
            )) : (
              <div><b>Standing by</b>
                <p>Start a run to see every search, gap, verification, and stopping decision.</p></div>
            )}
          </div>
        </div>
        <div className="card">
          <p className="eyebrow">Research ledger</p>
          <Ledger runs={runs} evidence={evidence} onOpenEvidence={onOpen} />
        </div>
      </section>
      <section className="card">
        <p className="eyebrow">Cross-examined sources</p>
        {verdicts.map((v, i) => (
          <div className={`verdict ${v.relation}`} key={v.id || i}>
            <b>{v.relation}</b> · {v.explanation}
            <div className="muted">A: {v.a_cite}</div>
            <div className="muted">B: {v.b_cite}</div>
          </div>
        ))}
        {!verdicts.length && <p className="muted">No unresolved conflicts found in this run.</p>}
      </section>
    </>
  );
}

/* ── prior art: posters, descriptions, unclaimed angles ───────────── */
export function PriorArtTab({
  priorArt, onSurvey, surveying,
}: {
  priorArt: any;
  onSurvey?: () => void;
  surveying?: boolean;
}) {
  const has = priorArt?.neighbors?.length;
  return (
    <section className="card">
      <div className="section-head">
        <div><p className="eyebrow">Prior art</p>
          <h2 className="display-heading small">Where this premise remains unclaimed</h2></div>
        {has
          ? <span className="judge-pill">{priorArt.surveyed} films compared by meaning</span>
          : null}
        {onSurvey && has && (
          <button className="ghost" onClick={onSurvey} disabled={surveying}>
            {surveying ? "Surveying…" : "Re-survey"}
          </button>
        )}
      </div>

      {!has && !surveying && (
        onSurvey
          ? <><p className="muted">Survey films with a similar premise, ranked by what the story is about.</p>
              <button onClick={onSurvey}>Survey prior art</button></>
          : <p className="muted">No prior-art survey in this dossier.</p>
      )}
      {surveying && <p className="muted">Surveying TMDB and the live web…</p>}

      {has && (
        <>
          <div className="neighborgrid">
            {priorArt.neighbors.map((n: any, i: number) => (
              <a className="neighbor" key={i} href={n.url} target="_blank" rel="noopener">
                {n.poster_url
                  ? <img className="neighbor-poster" src={n.poster_url} alt="" loading="lazy" />
                  : <div className="neighbor-poster neighbor-poster-blank">{(n.title || "?")[0]}</div>}
                <div className="neighbor-title">{n.title} <span className="muted">{n.year}</span></div>
                {n.overview && (
                  <p className="neighbor-overview">
                    {tidy(n.overview).length > 160 ? `${tidy(n.overview).slice(0, 160)}…` : tidy(n.overview)}
                  </p>
                )}
                <div className="muted">similarity {pctOf(n.similarity)}</div>
              </a>
            ))}
          </div>
          {(priorArt.unclaimed_angles || []).map((a: any, i: number) => (
            <div className="verdict angle" key={i}>
              <b>{a.angle}</b>
              {a.why && <p>{a.why}</p>}
              {!!a.contrast_titles?.length && (
                <div className="muted">checked against: {a.contrast_titles.join(", ")}</div>
              )}
            </div>
          ))}
        </>
      )}
    </section>
  );
}
