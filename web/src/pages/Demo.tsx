import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ThemeToggle } from "../components/ThemeToggle";
import { EvidenceModal } from "../components/EvidenceModal";
import {
  DepartmentsTab, EvidenceTab, OverviewTab, PriorArtTab, TAB_IDS, TraceTab,
  conflictMap, pctOf, type TabId,
} from "../workspace/tabs";
import type { Evidence, ResearchBox, ResearchRun, Verdict } from "../types";

interface Snapshot {
  premise: string; title: string; depth: string; overview: string; stop_reason: string;
  confidence: number; coverage: number; unresolved_contradictions: number; generated_at?: number;
  boxes: ResearchBox[]; evidence: Evidence[]; runs: ResearchRun[]; verdicts: Verdict[];
  prior_art: any; reel: any[]; emergent_boxes: string[];
}

const slug = (s: string) =>
  s.replace(/[^a-z0-9]+/gi, "-").replace(/(^-|-$)/g, "").toLowerCase().slice(0, 48);

const DEMOS = [
  { slug: "eliza", label: "ELIZA · 1966", file: "/demo-snapshot.json", pdf: "/demo-dossier.pdf" },
  { slug: "apollo13", label: "Apollo 13 · 1970", file: "/demo-apollo13.json", pdf: "/demo-apollo13-dossier.pdf" },
];

export function Demo() {
  const { slug: routeSlug } = useParams();
  const active = DEMOS.find((d) => d.slug === routeSlug) ?? DEMOS[0];
  const [S, setS] = useState<Snapshot | null>(null);
  const [failed, setFailed] = useState(false);
  const [tab, setTab] = useState<TabId>("overview");
  const [selBox, setSelBox] = useState<string | null>(null);
  const [dept, setDept] = useState<string | null>(null);
  const [modalEv, setModalEv] = useState<Evidence | null>(null);

  useEffect(() => {
    setS(null); setFailed(false); setTab("overview"); setSelBox(null); setDept(null);
    fetch(active.file)
      .then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
      .then(setS)
      .catch(() => setFailed(true));
  }, [active.file]);

  const conflicts = useMemo(() => (S ? conflictMap(S.verdicts) : {}), [S]);
  const highlights = useMemo(
    () => (S ? [...S.evidence].sort((a, b) => (b.quality_score ?? 0) - (a.quality_score ?? 0)).slice(0, 3) : []),
    [S],
  );
  const boxName = useMemo(() => (S ? Object.fromEntries(S.boxes.map((b) => [b.id, b.name])) : {}), [S]);

  if (failed) return (
    <div className="wrap">
      <header><Link to="/" className="ghost">← THE BOXES</Link><ThemeToggle /></header>
      <p className="muted">The demo dossier could not be loaded. <Link to="/">Open the app</Link>.</p>
    </div>
  );
  if (!S) return (
    <div className="wrap">
      <header><Link to="/" className="ghost">← THE BOXES</Link><ThemeToggle /></header>
      <p className="muted">Opening the dossier…</p>
    </div>
  );

  const primaryCount = S.evidence.filter((e) => e.source_tier === "primary").length;
  const domainCount = new Set(S.evidence.map((e) => e.source_domain).filter(Boolean)).size;
  const openRisks = S.unresolved_contradictions + S.boxes.filter((b) => (b.score ?? 0) < 0.65).length;
  const goto = (t: TabId, boxId?: string) => { setTab(t); if (boxId !== undefined) setSelBox(boxId); };
  const dossierName = `${slug(S.premise)}-${new Date((S.generated_at ?? Date.now() / 1000) * 1000)
    .toISOString().slice(0, 10)}.pdf`;
  const dossierHref = active.pdf;

  return (
    <div className="wrap workspace">
      <header>
        <Link to="/" className="ghost">← THE BOXES</Link>
        <div className="head-actions">
          <ThemeToggle />
        </div>
      </header>

      <section className="project-hero">
        <div>
          <p className="eyebrow">Production research dossier</p>
          <h1 className="project-title">{S.title}</h1>
          <p className="premise">{S.premise}</p>
        </div>
        <div className="hero-actions">
          <Link className="primary-link" to="/">Build your own</Link>
          <a className="ghost" href={dossierHref} download={dossierName}>Download dossier</a>
        </div>
      </section>

      <nav className="demo-switch" aria-label="Example runs">
        {DEMOS.map((d) => (
          <Link key={d.slug} to={`/demo/${d.slug}`}
                className={d.slug === active.slug ? "on" : ""}>{d.label}</Link>
        ))}
      </nav>

      <section className="impact-strip">
        <p className="impact-lead">
          Kubrick's team filled about a thousand boxes over months in libraries and
          archives. THE BOXES builds the same pile overnight, from a phone.
        </p>
        <blockquote className="impact-quote">
          "I must have gone through several hundred books on the subject, broken it
          down into categories on everything from his food tastes to the weather on
          the day of a specific battle, and cross-indexed all the data in a
          comprehensive research file."
          <cite>Stanley Kubrick on researching Napoleon, to Joseph Gelmis, 1970</cite>
        </blockquote>
        <p className="muted">
          For directors, production designers, writers, and researchers in development
          and pre-production.
        </p>
      </section>

      <div className="metric-grid" aria-label="Research summary">
        <div className="metric"><span>Readiness</span><b>{pctOf(S.confidence)}</b><small>research completeness</small></div>
        <div className="metric"><span>Evidence</span><b>{S.evidence.length}</b><small>{S.boxes.length} research boxes</small></div>
        <div className="metric"><span>Primary records</span><b>{primaryCount}</b><small>{domainCount} independent domains</small></div>
        <div className="metric"><span>Open risks</span><b>{openRisks}</b><small>{S.unresolved_contradictions} factual conflicts</small></div>
      </div>

      <nav className="workspace-tabs" aria-label="Dossier sections">
        {TAB_IDS.map((id) => (
          <button key={id} className={tab === id ? "on" : ""} onClick={() => setTab(id)}>{id}</button>
        ))}
      </nav>

      {tab === "overview" && (
        <OverviewTab
          overview={S.overview}
          boxes={S.boxes}
          highlights={highlights}
          reel={S.reel}
          verdicts={S.verdicts}
          evidence={S.evidence}
          conflicts={conflicts}
          onOpen={setModalEv}
          onGoto={goto}
          sideSlot={
            <div className="card">
              <p className="eyebrow">How the run stopped</p>
              <p className="muted">{S.stop_reason || "Every objective passed its readiness threshold."}</p>
              {!!S.emergent_boxes.length && (
                <p className="muted">It opened {S.emergent_boxes.join(", ")} on its own.</p>
              )}
            </div>
          }
        />
      )}

      {tab === "departments" && (
        <DepartmentsTab boxes={S.boxes} evidence={S.evidence} onOpen={setModalEv} conflicts={conflicts} />
      )}

      {tab === "evidence" && (
        <EvidenceTab
          boxes={S.boxes} evidence={S.evidence}
          selBox={selBox} setSelBox={setSelBox}
          dept={dept} setDept={setDept}
          onOpen={setModalEv} conflicts={conflicts}
          uploadSlot={
            <section className="card upload-card">
              <div className="section-head">
                <div><p className="eyebrow">Add your own reference</p>
                  <h2 className="display-heading small">Bring your own material into the evidence space</h2></div>
              </div>
              <div className="upload-row">
                <select disabled><option>file under: a research box</option></select>
                <input type="file" disabled />
              </div>
              <p className="muted">
                On a signed-in project, drop a script page, a still, or a PDF here. It
                embeds in the same 768-d space as the agent's findings, up to 12 MB.
              </p>
            </section>
          }
        />
      )}

      {tab === "trace" && (
        <TraceTab
          runs={S.runs} verdicts={S.verdicts} boxes={S.boxes} evidence={S.evidence}
          onOpen={setModalEv} stopReason={S.stop_reason}
        />
      )}

      {tab === "prior-art" && <PriorArtTab priorArt={S.prior_art} />}

      <EvidenceModal
        evidence={modalEv} boxName={boxName}
        conflict={modalEv ? conflicts[modalEv.id] : null}
        onClose={() => setModalEv(null)}
      />
    </div>
  );
}
