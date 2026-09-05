import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ThemeToggle } from "../components/ThemeToggle";
import { EvidenceModal } from "../components/EvidenceModal";
import {
  DepartmentsTab, EvidenceTab, OverviewTab, PriorArtTab, TAB_IDS, TraceTab,
  conflictMap, pctOf, type TabId,
} from "../workspace/tabs";
import type { Evidence, ResearchBox, ResearchRun, Verdict } from "../types";

interface Snapshot {
  premise: string; title: string; depth: string; overview: string; stop_reason: string;
  confidence: number; coverage: number; unresolved_contradictions: number;
  boxes: ResearchBox[]; evidence: Evidence[]; runs: ResearchRun[]; verdicts: Verdict[];
  prior_art: any; reel: any[]; emergent_boxes: string[];
}

export function Demo() {
  const [S, setS] = useState<Snapshot | null>(null);
  const [failed, setFailed] = useState(false);
  const [tab, setTab] = useState<TabId>("overview");
  const [selBox, setSelBox] = useState<string | null>(null);
  const [dept, setDept] = useState<string | null>(null);
  const [modalEv, setModalEv] = useState<Evidence | null>(null);

  useEffect(() => {
    fetch("/demo-snapshot.json")
      .then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
      .then(setS)
      .catch(() => setFailed(true));
  }, []);

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

  return (
    <div className="wrap workspace">
      <header>
        <Link to="/" className="ghost">← THE BOXES</Link>
        <div className="head-actions">
          <span className="judge-pill">Read-only demo · one real {S.depth} run</span>
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
          <a className="ghost" href="/demo-dossier.pdf" download>Download dossier</a>
        </div>
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
          conflicts={conflicts}
          onOpen={setModalEv}
          onGoto={goto}
          sideSlot={
            S.verdicts.length ? (
              <div className="card">
                <p className="eyebrow">Cross-examined</p>
                <div className={`verdict ${S.verdicts[0].relation}`}>
                  <b>{S.verdicts[0].relation}</b> · {S.verdicts[0].explanation}
                  <div className="muted">A: {S.verdicts[0].a_cite}</div>
                  <div className="muted">B: {S.verdicts[0].b_cite}</div>
                </div>
              </div>
            ) : (
              <div className="card">
                <p className="eyebrow">How the run stopped</p>
                <p className="muted">{S.stop_reason || "Every objective passed its readiness threshold."}</p>
                {!!S.emergent_boxes.length && (
                  <p className="muted">It opened {S.emergent_boxes.join(", ")} on its own.</p>
                )}
              </div>
            )
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
