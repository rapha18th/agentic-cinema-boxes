import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ResearchMap } from "../components/ResearchMap";
import { Ledger } from "../components/Ledger";
import { useBoxes, useEvidence, useProject, useReel, useRuns, useVerdicts } from "../data";
import { ask, runProject, uploadResource } from "../api";

const pct = (x?: number) => `${Math.round((x ?? 0) * 100)}%`;

export function Project() {
  const { pid = "" } = useParams();
  const project = useProject(pid);
  const boxes = useBoxes(pid);
  const evidence = useEvidence(pid);
  const runs = useRuns(pid);
  const verdicts = useVerdicts(pid);
  const reel = useReel(pid);

  const [activity, setActivity] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [q, setQ] = useState("");
  const [answers, setAnswers] = useState<any[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploadBox, setUploadBox] = useState("");

  const contradicts = verdicts.filter((v: any) => v.relation === "contradicts");
  const contextual = verdicts.filter((v: any) => v.relation === "contextualises");

  const start = async () => {
    setRunning(true);
    setActivity([]);
    try {
      await runProject(pid, (ev) => {
        if (ev.type === "search") push(`search · ${ev.objective}`);
        else if (ev.type === "extract") push(`extract · ${ev.objective}: ${ev.sources} sources`);
        else if (ev.type === "coverage") push(`→ ${ev.summary}`);
        else if (ev.type === "emergent_gap") push(`EMERGENT GAP → opening ${ev.objective.name}`);
        else if (ev.type === "contradiction") push(`! contradiction found`);
        else if (ev.type === "stop") push(`STOP: ${ev.reason}`);
        else if (ev.type === "complete") push(`complete · ${ev.evidence} evidence · ${pct(ev.confidence)}`);
        else if (ev.type === "error") push(`error: ${ev.error}`);
      });
    } finally {
      setRunning(false);
    }
  };
  const push = (s: string) => setActivity((a) => [...a, s]);

  const doAsk = async () => {
    if (!q.trim()) return;
    setAnswers(await ask(pid, q.trim()).catch(() => []));
  };

  const doUpload = async (f: File) => {
    push(`uploading ${f.name} → ${uploadBox || "unfiled"}`);
    await uploadResource(pid, f, uploadBox, "");
    push(`indexed ${f.name}`);
  };

  if (!project) return <div className="wrap"><Link to="/">← projects</Link><p>Loading…</p></div>;

  return (
    <div className="wrap">
      <header>
        <Link to="/" className="ghost">← projects</Link>
        <div className="conf">
          confidence <b>{pct(project.confidence)}</b> · coverage {pct(project.coverage)} · {project.status}
        </div>
      </header>

      <p className="premise">{project.premise}</p>

      <button onClick={start} disabled={running}>
        {running ? "Researching…" : runs.length ? "Research again" : "Start research"}
      </button>

      <div className="grid">
        <section className="card">
          <h3>Research map</h3>
          <ResearchMap boxes={boxes as any} evidence={evidence as any} />
          <div className="boxwrap">
            {[...boxes].sort((a: any, b: any) => (a.score ?? 0) - (b.score ?? 0)).map((b: any) => (
              <div className="box" key={b.id}>
                <div className="box-name">{b.name}{b.emergent ? " ✦" : ""}</div>
                <div className="bar"><span style={{ width: `${(b.score ?? 0) * 100}%` }} /></div>
                <div className="muted">{b.evidence_count ?? 0} items · {b.distinct_domains ?? 0} domains</div>
              </div>
            ))}
          </div>
        </section>

        <section className="card">
          <h3>Activity</h3>
          <pre className="activity">{activity.join("\n") || "idle"}</pre>
          <h3>Ledger</h3>
          <Ledger runs={runs as any} />
        </section>
      </div>

      <section className="card">
        <h3>Contradictions <span className="muted">({contradicts.length} conflict, {contextual.length} context)</span></h3>
        {verdicts.map((v: any) => (
          <div className={`verdict ${v.relation}`} key={v.id}>
            <b>{v.relation}</b> — {v.explanation}
            <div className="muted">A: {v.a_cite}</div>
            <div className="muted">B: {v.b_cite}</div>
          </div>
        ))}
        {!verdicts.length && <p className="muted">None found.</p>}
      </section>

      <section className="card">
        <h3>Add your own reference</h3>
        <div className="row">
          <select value={uploadBox} onChange={(e) => setUploadBox(e.target.value)}>
            <option value="">unfiled</option>
            {boxes.map((b: any) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
          <input ref={fileRef} type="file" onChange={(e) => e.target.files?.[0] && doUpload(e.target.files[0])} />
        </div>
        <p className="muted">Text, PDF, or image. It is embedded into the same space as the agent's findings.</p>
      </section>

      <section className="card">
        <h3>Ask the boxes</h3>
        <div className="row">
          <input value={q} onChange={(e) => setQ(e.target.value)}
                 placeholder="What would our characters hear inside a bank?" onKeyDown={(e) => e.key === "Enter" && doAsk()} />
          <button onClick={doAsk}>Ask</button>
        </div>
        {answers.map((a, i) => (
          <div className="answer" key={i}>
            <div>{a.text}</div>
            <div className="muted">{a.citation} {a.source === "director" ? "· your upload" : ""} · {a.score}</div>
          </div>
        ))}
      </section>

      {!!reel.length && (
        <section className="card">
          <h3>Reference reel</h3>
          {reel.map((b: any, i: number) => (
            <div className="beat" key={i}>
              <b>{b.t}</b> {b.title} — {b.note}
              {b.citations?.slice(0, 3).map((c: string, j: number) => <div className="muted" key={j}>{c}</div>)}
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
