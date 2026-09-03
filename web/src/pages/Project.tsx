import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ResearchMap } from "../components/ResearchMap";
import { Ledger } from "../components/Ledger";
import { MediaBit } from "../components/Media";
import { ResearchConsole, type Progress } from "../components/ResearchConsole";
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
  const [progress, setProgress] = useState<Progress>({});
  const [liveEv, setLiveEv] = useState<any[]>([]);
  const [q, setQ] = useState("");
  const [answers, setAnswers] = useState<any[]>([]);
  const [selBox, setSelBox] = useState<string | null>(null);
  const [uploadBox, setUploadBox] = useState("");

  const boxName = useMemo(
    () => Object.fromEntries(boxes.map((b: any) => [b.id, b.name])),
    [boxes],
  );
  // Firestore is the source of truth; streamed evidence fills the gap until it catches up.
  const allEvidence = useMemo(() => {
    const seen = new Set(evidence.map((e: any) => e.id));
    return [...evidence, ...liveEv.filter((e) => !seen.has(e.id))];
  }, [evidence, liveEv]);
  const selEvidence = useMemo(
    () => (selBox ? allEvidence.filter((e: any) => e.objective_id === selBox) : []),
    [selBox, allEvidence],
  );

  const push = (s: string) => setActivity((a) => [...a.slice(-120), s]);

  const start = async () => {
    setRunning(true); setActivity([]); setLiveEv([]); setProgress({ phase: "planning" });
    try {
      await runProject(pid, (ev) => {
        if (ev.type === "progress") setProgress((p) => ({ ...p, ...ev }));
        else if (ev.type === "evidence") {
          setLiveEv((cur) => [...cur, ...ev.items]);
          push(`+${ev.items.length} indexed · ${ev.objective}`);
        }
        else if (ev.type === "search") push(`SEARCH  ${ev.objective}`);
        else if (ev.type === "extract") {
          const extra = [ev.images && `${ev.images} img`, ev.docs && `${ev.docs} pdf`, ev.av && `${ev.av} a/v`]
            .filter(Boolean).join(", ");
          push(`EXTRACT ${ev.objective}: ${ev.sources} sources${extra ? ` + ${extra}` : ""}`);
        }
        else if (ev.type === "coverage") push(`SCORE   ${ev.summary}`);
        else if (ev.type === "emergent_gap") push(`GAP     opening ${ev.objective.name}`);
        else if (ev.type === "contradiction") push(`CONFLICT ${ev.verdict.a_cite} vs ${ev.verdict.b_cite}`);
        else if (ev.type === "stop") push(`STOP    ${ev.reason}`);
        else if (ev.type === "complete") { push(`DONE    ${ev.evidence} fragments · ${pct(ev.confidence)}`); setProgress((p) => ({ ...p, phase: "done" })); }
        else if (ev.type === "error") push(`ERROR   ${ev.error}`);
      });
    } finally { setRunning(false); }
  };

  const doAsk = async () => {
    if (!q.trim()) return;
    setAnswers(await ask(pid, q.trim()).catch(() => []));
  };
  const doUpload = async (f: File) => {
    push(`uploading ${f.name} → ${boxName[uploadBox] || "unfiled"}`);
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

      {(running || progress.phase === "done") && (
        <ResearchConsole progress={progress} log={activity} done={!running && progress.phase === "done"} />
      )}

      <div className="grid">
        <section className="card">
          <h3>Research map <span className="muted">{selBox ? "· click empty space to clear" : "· click a box"}</span></h3>
          <ResearchMap boxes={boxes as any} evidence={allEvidence as any} selected={selBox} onSelect={setSelBox} />
          <div className="boxwrap">
            {[...boxes].sort((a: any, b: any) => (a.score ?? 0) - (b.score ?? 0)).map((b: any) => {
              const liveCount = allEvidence.filter((e: any) => e.objective_id === b.id).length;
              return (
                <button className={`box ${selBox === b.id ? "on" : ""}`} key={b.id}
                        onClick={() => setSelBox(selBox === b.id ? null : b.id)}>
                  <div className="box-name">{b.name}{b.emergent ? " ✦" : ""}</div>
                  <div className="bar"><span style={{ width: `${(b.score ?? 0) * 100}%` }} /></div>
                  <div className="muted">{Math.max(b.evidence_count ?? 0, liveCount)} items · {b.distinct_domains ?? 0} domains</div>
                </button>
              );
            })}
          </div>
        </section>

        <section className="card">
          <h3>Activity</h3>
          <pre className="activity">{activity.join("\n") || "idle"}</pre>
          <h3>Ledger</h3>
          <Ledger runs={runs as any} evidence={evidence as any} />
        </section>
      </div>

      {selBox && (
        <section className="card">
          <h3>{boxName[selBox]} <span className="muted">· {selEvidence.length} items</span></h3>
          <div className="evgrid">
            {selEvidence.map((e: any) => (
              <div className="evcard" key={e.id}>
                {e.modality && e.modality !== "text"
                  ? <MediaBit e={e} size="full" />
                  : <div className="evtext">{(e.text || "").slice(0, 220)}</div>}
                <div className="muted">
                  {e.url
                    ? <a href={e.url} target="_blank" rel="noopener">{[e.title || e.source_domain, e.publish_date].filter(Boolean).join(" · ")}</a>
                    : [e.title || e.source_domain, e.publish_date].filter(Boolean).join(" · ")}
                  {e.source === "director" ? " · your upload" : ""}
                  {e.modality && e.modality !== "text" ? ` · ${e.license_note || "check rights"}` : ""}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="card">
        <h3>Contradictions <span className="muted">
          ({verdicts.filter((v: any) => v.relation === "contradicts").length} conflict,
          {" "}{verdicts.filter((v: any) => v.relation === "contextualises").length} context)</span></h3>
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
          <input type="file" onChange={(e) => e.target.files?.[0] && doUpload(e.target.files[0])} />
        </div>
        <p className="muted">Text, PDF, or image. Embedded into the same space as the agent's findings.</p>
      </section>

      <section className="card">
        <h3>Ask the boxes</h3>
        <div className="row">
          <input value={q} onChange={(e) => setQ(e.target.value)}
                 placeholder="What would our characters actually see and hear?"
                 onKeyDown={(e) => e.key === "Enter" && doAsk()} />
          <button onClick={doAsk}>Ask</button>
        </div>
        {answers.map((a, i) => (
          <div className="answer" key={i}>
            {a.modality && a.modality !== "text" && <MediaBit e={a} />}
            <div>{a.text}</div>
            <div className="muted">
              {a.url ? <a href={a.url} target="_blank" rel="noopener">{a.citation}</a> : a.citation}
              {a.source === "director" ? " · your upload" : ""} · {a.score}
            </div>
          </div>
        ))}
      </section>

      {!!reel.length && (
        <section className="card">
          <h3>Reference reel</h3>
          {reel.map((b: any, i: number) => (
            <div className="beat" key={i}>
              <div><b>{b.t}</b> {b.title} — {b.note}</div>
              <div className="beat-src">
                {(b.sources || []).map((s: any, j: number) => {
                  if (s.modality === "image" && (s.image_url || s.media_url)) {
                    return (
                      <a key={j} href={s.url || s.media_url || s.image_url} target="_blank" rel="noopener" title={s.cite}>
                        <img className="ev-thumb" src={s.media_url || s.image_url} alt="" loading="lazy" />
                      </a>
                    );
                  }
                  if ((s.modality === "audio" || s.modality === "video" || s.modality === "pdf") && s.media_url) {
                    return <span key={j} className="beat-media"><MediaBit e={s} /> <span className="muted">{s.cite}</span></span>;
                  }
                  return <a key={j} className="src-link" href={s.url} target="_blank" rel="noopener">{s.cite}</a>;
                })}
              </div>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
