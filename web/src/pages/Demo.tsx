import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ThemeToggle } from "../components/ThemeToggle";
import { ResearchMap } from "../components/ResearchMap";
import { Ledger } from "../components/Ledger";
import { EvidenceModal } from "../components/EvidenceModal";
import { DEPARTMENTS, DEPT_LABEL } from "../departments";
import { DEMO_BOXES, DEMO_EVIDENCE, DEMO_PREMISE, DEMO_RUNS, DEMO_VERDICTS } from "../demoData";
import type { Evidence } from "../types";

type Tab = "overview" | "departments" | "evidence" | "trace" | "originality";

export function Demo() {
  const [tab, setTab] = useState<Tab>("overview");
  const [selected, setSelected] = useState<string | null>(null);
  const [modal, setModal] = useState<Evidence | null>(null);
  const names = useMemo(() => Object.fromEntries(DEMO_BOXES.map((b) => [b.id, b.name])), []);
  const selectedEvidence = selected ? DEMO_EVIDENCE.filter((e) => e.objective_id === selected) : [];
  const weak = [...DEMO_BOXES].sort((a, b) => (a.score ?? 0) - (b.score ?? 0)).slice(0, 2);

  return (
    <div className="wrap workspace">
      <header>
        <Link to="/" className="ghost">← THE BOXES</Link>
        <div className="head-actions"><span className="judge-pill">Read-only judge demo</span><ThemeToggle /></div>
      </header>

      <section className="project-hero">
        <div>
          <p className="eyebrow">Production research dossier</p>
          <h1 className="project-title">THE SPACE BETWEEN ORDERS</h1>
          <p className="premise">{DEMO_PREMISE}</p>
        </div>
        <div className="hero-actions">
          <Link className="primary-link" to="/">Build your world</Link>
          <button className="ghost" onClick={() => window.print()}>Print brief</button>
        </div>
      </section>

      <div className="metric-grid" aria-label="Research summary">
        <div className="metric"><span>Readiness</span><b>81%</b><small>research completeness</small></div>
        <div className="metric"><span>Evidence</span><b>42</b><small>12 shown in this demo</small></div>
        <div className="metric"><span>Sources</span><b>31</b><small>18 primary records</small></div>
        <div className="metric"><span>Open risks</span><b>3</b><small>2 thin boxes · 1 timeline</small></div>
      </div>

      <nav className="workspace-tabs" aria-label="Dossier sections">
        {(["overview", "departments", "evidence", "trace", "originality"] as Tab[]).map((id) => (
          <button key={id} className={tab === id ? "on" : ""} onClick={() => setTab(id)}>{id}</button>
        ))}
      </nav>

      {tab === "overview" && <>
        <section className="brief-lead">
          <div>
            <p className="eyebrow">The research picture</p>
            <h2 className="display-heading">The institution changes overnight. The people and power structures do not.</h2>
            <p>Primary records point to a sharper dramatic engine than a generic space-race story: a new civilian mandate lands on top of inherited laboratories, segregated technical labour, and military programmes moving at different speeds.</p>
          </div>
          <aside className="decision-card">
            <span className="signal">Strongest opportunity</span>
            <b>Make invisible calculation audible.</b>
            <p>The archive gives sound and cinematography a repeatable language for intellectual work: carriage returns, relays, paper movement, ventilation, and test-cell machinery.</p>
          </aside>
        </section>
        <section className="card">
          <div className="section-head"><div><p className="eyebrow">Decisions, not documents</p><h2 className="display-heading small">What the crew can act on</h2></div><button className="ghost" onClick={() => setTab("evidence")}>Audit evidence →</button></div>
          <div className="finding-grid">
            <article><span>Script</span><b>Split the founding into two clocks.</b><p>Civilian NASA begins in October. The military rocket transfer remains contested and incomplete.</p></article>
            <article><span>Art direction</span><b>Build paper flow into the set.</b><p>Shared tables, task lights, chalkboards, calculators, and moving folders reveal the hierarchy without exposition.</p></article>
            <article><span>Sound</span><b>Give each kind of thinking a machine rhythm.</b><p>Calculators, teletypes, ventilation, and tunnel tests create distinct acoustic layers.</p></article>
          </div>
        </section>
        <section className="risk-grid">
          <div className="card"><p className="eyebrow">Unresolved risks</p>{weak.map((b) => <div className="risk-row" key={b.id}><span>{b.name}</span><b>{Math.round((b.score ?? 0) * 100)}%</b><small>{b.distinct_domains} independent domains</small></div>)}</div>
          <div className="card"><p className="eyebrow">Cross-examined</p><div className="verdict contextualises"><b>Timeline clarified</b><p>{DEMO_VERDICTS[0].explanation}</p></div></div>
        </section>
      </>}

      {tab === "departments" && <section className="department-grid">
        {DEPARTMENTS.map((d) => {
          const boxes = DEMO_BOXES.filter((b) => b.departments?.includes(d));
          if (!boxes.length) return null;
          return <article className="card department-card" key={d}><p className="eyebrow">{DEPT_LABEL[d]}</p>{boxes.map((b) => <div key={b.id}><b>{b.name}</b><p>{b.description}</p></div>)}</article>;
        })}
      </section>}

      {tab === "evidence" && <>
        <section className="card">
          <div className="section-head"><div><p className="eyebrow">Semantic evidence space</p><h2 className="display-heading small">Every claim remains inspectable</h2></div><span className="muted">click a box or fragment</span></div>
          <ResearchMap boxes={DEMO_BOXES} evidence={DEMO_EVIDENCE} selected={selected} onSelect={setSelected} onOpenEvidence={setModal} />
          <div className="boxwrap">{DEMO_BOXES.map((b) => <button className={`box ${selected === b.id ? "on" : ""}`} key={b.id} onClick={() => setSelected(selected === b.id ? null : b.id)}><div className="box-name">{b.name}{b.emergent ? " ✦" : ""}</div><div className="bar"><span style={{ width: `${(b.score ?? 0) * 100}%` }} /></div><div className="muted">{b.evidence_count} items · {b.distinct_domains} domains</div></button>)}</div>
        </section>
        {selected && <section className="card"><h3>{names[selected]} · {selectedEvidence.length} sample items</h3><div className="evgrid">{selectedEvidence.map((e) => <button className="evcard" key={e.id} onClick={() => setModal(e)}><span className={`source-badge ${e.source_tier}`}>{e.source_tier}</span><div className="evtext">{e.text}</div><span className="muted">{e.title} · {e.source_domain}</span></button>)}</div></section>}
      </>}

      {tab === "trace" && <section className="trace-grid">
        <div className="card"><p className="eyebrow">Agent decisions</p><div className="decision-timeline">
          <div><b>01 · Planned</b><p>Six production questions from the premise.</p></div>
          <div><b>02 · Acquired</b><p>Parallel searched 42 results and extracted 17 source pages.</p></div>
          <div><b>03 · Rejected</b><p>Removed duplicates and low-provenance summaries.</p></div>
          <div className="new"><b>04 · Opened a new box</b><p>Military transfer appeared across four existing boxes, so the agent created ARMY TO CIVILIAN.</p></div>
          <div><b>05 · Cross-examined</b><p>Gemini reconciled two apparently conflicting transition dates.</p></div>
          <div className="done"><b>06 · Stopped</b><p>Critical objectives passed the production threshold. Three risks remain explicit.</p></div>
        </div></div>
        <div className="card"><p className="eyebrow">Research ledger</p><Ledger runs={DEMO_RUNS} evidence={DEMO_EVIDENCE} onOpenEvidence={setModal} /></div>
      </section>}

      {tab === "originality" && <section className="card">
        <div className="section-head"><div><p className="eyebrow">Prior-art survey</p><h2 className="display-heading small">The unclaimed dramatic territory</h2></div><span className="judge-pill">68 films compared by meaning</span></div>
        <div className="brief-lead originality-lead">
          <div><p className="eyebrow">Closest reference set</p><div className="title-list"><span>Hidden Figures · 2016</span><span>The Right Stuff · 1983</span><span>October Sky · 1999</span></div></div>
          <aside className="decision-card"><span className="signal">Unclaimed angle</span><b>The handover itself is the antagonist.</b><p>The closest films centre achievement, selection, or aspiration. This premise can centre the unstable weeks when a new civilian institution exists on paper while inherited hierarchies still control the work.</p></aside>
        </div>
        <div className="verdict angle"><b>Claim boundary</b><p>This is an originality position relative to the 68-title surveyed set, not a universal claim that no similar film exists.</p><div className="muted">checked against the named closest titles and the remaining ranked candidate set</div></div>
      </section>}

      <EvidenceModal evidence={modal} boxName={names} onClose={() => setModal(null)} />
    </div>
  );
}
