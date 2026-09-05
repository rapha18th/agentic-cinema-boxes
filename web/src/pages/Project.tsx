import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ResearchMap } from "../components/ResearchMap";
import { Ledger } from "../components/Ledger";
import { MediaBit } from "../components/Media";
import { ResearchConsole, type Progress } from "../components/ResearchConsole";
import { ThemeToggle } from "../components/ThemeToggle";
import { EvidenceModal, isInteractiveClick } from "../components/EvidenceModal";
import { Markdown } from "../components/Markdown";
import { useBoxes, useEvidence, usePriorArt, useProject, useReel, useRuns, useVerdicts } from "../data";
import {
  ask, deleteProject, downloadReport, runProject, surveyPriorArt, updateProject, uploadResource,
} from "../api";
import { DEPARTMENTS, DEPT_LABEL } from "../departments";

const pct = (x?: number) => `${Math.round((x ?? 0) * 100)}%`;

export function Project() {
  const { pid = "" } = useParams();
  const nav = useNavigate();
  const project = useProject(pid);
  const boxes = useBoxes(pid);
  const evidence = useEvidence(pid);
  const runs = useRuns(pid);
  const verdicts = useVerdicts(pid);
  const reel = useReel(pid);
  const priorArtDoc = usePriorArt(pid);

  const [activity, setActivity] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [streamLost, setStreamLost] = useState(false);
  const [progress, setProgress] = useState<Progress>({});
  const [liveEv, setLiveEv] = useState<any[]>([]);
  const [q, setQ] = useState("");
  const [answers, setAnswers] = useState<any[]>([]);
  const [asking, setAsking] = useState(false);
  const [askErr, setAskErr] = useState("");
  const [asked, setAsked] = useState(false);
  const [selBox, setSelBox] = useState<string | null>(null);
  const [uploadBox, setUploadBox] = useState("");
  const [editing, setEditing] = useState(false);
  const [editPremise, setEditPremise] = useState("");
  const [editDepth, setEditDepth] = useState("scout");
  const [saving, setSaving] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const [dept, setDept] = useState<string | null>(null);
  const [surveying, setSurveying] = useState(false);
  const [priorArtLocal, setPriorArtLocal] = useState<any>(null);
  const priorArt = priorArtDoc || priorArtLocal;
  const [modalEv, setModalEv] = useState<any | null>(null);

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

  const deptsPresent = useMemo(() => {
    const set = new Set<string>();
    boxes.forEach((b: any) => (b.departments || []).forEach((d: string) => set.add(d)));
    return DEPARTMENTS.filter((d) => set.has(d));
  }, [boxes]);
  const filteredBoxes = useMemo(
    () => (dept ? boxes.filter((b: any) => (b.departments || []).includes(dept)) : boxes),
    [boxes, dept],
  );
  const filteredEvidence = useMemo(() => {
    if (!dept) return allEvidence;
    const ids = new Set(filteredBoxes.map((b: any) => b.id));
    return allEvidence.filter((e: any) => ids.has(e.objective_id));
  }, [allEvidence, dept, filteredBoxes]);
  const pickDept = (d: string | null) => { setDept(d); setSelBox(null); };

  const push = (s: string) => setActivity((a) => [...a.slice(-120), s]);

  const start = async () => {
    setRunning(true); setStreamLost(false); setActivity([]); setLiveEv([]);
    setProgress({ phase: "planning" });
    try {
      await runProject(pid, (ev) => {
        if (ev.type === "progress") setProgress((p) => ({ ...p, ...ev }));
        else if (ev.type === "disconnect") { setStreamLost(true); push(`FEED LOST — ${ev.reason}; run continues on the server`); }
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
    if (!q.trim() || asking) return;
    setAsking(true); setAskErr(""); setAnswers([]); setAsked(true);
    try {
      setAnswers(await ask(pid, q.trim()));
    } catch (e: any) {
      const msg = String(e?.message || e);
      setAskErr(
        /no research yet/i.test(msg) ? "No research yet — run the agent first."
        : /409/.test(msg) ? "Nothing indexed yet. Run the research, then ask."
        : "Could not reach the index. Try again in a moment.",
      );
    } finally {
      setAsking(false);
    }
  };

  const beginEdit = () => {
    setEditPremise(project.premise || "");
    setEditDepth(project.depth || "scout");
    setEditing(true);
  };
  const saveEdit = async () => {
    if (!editPremise.trim() || saving) return;
    setSaving(true);
    try {
      await updateProject(pid, { premise: editPremise.trim(), depth: editDepth });
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };
  const getReport = async () => {
    if (reporting) return;
    setReporting(true);
    try { await downloadReport(pid); }
    catch { push("report failed — is the backend deployed?"); }
    finally { setReporting(false); }
  };
  const doDelete = async () => {
    await deleteProject(pid);
    nav("/");
  };
  const doSurvey = async () => {
    if (surveying) return;
    setSurveying(true);
    try { setPriorArtLocal(await surveyPriorArt(pid)); }
    catch (e: any) {
      const msg = String(e?.message || e);
      push(/already running/i.test(msg)
        ? "a prior-art survey is already running — it will appear here when it finishes"
        : "prior-art survey failed — is TMDB_API_KEY set on the backend?");
    }
    finally { setSurveying(false); }
  };
  const doUpload = async (f: File) => {
    push(`uploading ${f.name} → ${boxName[uploadBox] || "unfiled"}`);
    await uploadResource(pid, f, uploadBox, "");
    push(`indexed ${f.name}`);
  };

  if (!project) return (
    <div className="wrap">
      <header><Link to="/" className="ghost">← projects</Link><ThemeToggle /></header>
      <p className="muted">Loading…</p>
    </div>
  );

  // When the SSE stream is cut mid-run the loop keeps going on the server;
  // fall back to the project's live Firestore document for progress and state.
  const consoleOpen = running || streamLost || progress.phase === "done";
  const shownProgress = streamLost ? { ...progress, ...(project.progress || {}) } : progress;
  const runDone = !running && (progress.phase === "done" || project.status === "done");
  const runErrored = project.status === "error";

  return (
    <div className="wrap">
      <header>
        <Link to="/" className="ghost">← projects</Link>
        <div className="head-actions">
          <div className="conf">
            confidence <b>{pct(project.confidence)}</b> · coverage {pct(project.coverage)} · {project.status}
          </div>
          <ThemeToggle />
        </div>
      </header>

      {editing ? (
        <section className="card">
          <h3>Edit project</h3>
          <textarea rows={3} value={editPremise} onChange={(e) => setEditPremise(e.target.value)} />
          <div className="row">
            <select value={editDepth} onChange={(e) => setEditDepth(e.target.value)}>
              <option value="scout">Scout · minutes</option>
              <option value="production">Production · deeper</option>
              <option value="kubrick">Kubrick · obsessive</option>
            </select>
            <button onClick={saveEdit} disabled={saving || !editPremise.trim()}>
              {saving ? "Saving…" : "Save"}
            </button>
            <button className="ghost" onClick={() => setEditing(false)}>Cancel</button>
          </div>
        </section>
      ) : (
        <p className="premise">{project.premise}</p>
      )}

      <div className="row action-row">
        <button onClick={start} disabled={running}>
          {running ? "Researching…" : runs.length ? "Research again" : "Start research"}
        </button>
        <button className="ghost" onClick={getReport} disabled={reporting}>
          {reporting ? "Building…" : "Download report"}
        </button>
        {!editing && <button className="ghost" onClick={beginEdit}>Edit</button>}
      </div>

      {consoleOpen && (
        <ResearchConsole
          progress={shownProgress}
          log={activity}
          done={runDone}
          disconnected={streamLost && !runDone && !runErrored}
          errorText={runErrored ? (project.error || "see the activity log below") : ""}
        />
      )}

      <div className="grid">
        <section className="card">
          <h3>Research map <span className="muted">{selBox ? "· click empty space to clear" : "· click a box"}</span></h3>
          {!!deptsPresent.length && (
            <div className="dept-bar">
              <button className={`chip ${!dept ? "on" : ""}`} onClick={() => pickDept(null)}>All</button>
              {deptsPresent.map((d) => (
                <button key={d} className={`chip ${dept === d ? "on" : ""}`}
                        onClick={() => pickDept(dept === d ? null : d)}>
                  {DEPT_LABEL[d] || d}
                </button>
              ))}
            </div>
          )}
          <ResearchMap boxes={filteredBoxes as any} evidence={filteredEvidence as any} selected={selBox}
                       onSelect={setSelBox} onOpenEvidence={setModalEv} />
          <div className="boxwrap">
            {[...filteredBoxes].sort((a: any, b: any) => (a.score ?? 0) - (b.score ?? 0)).map((b: any) => {
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
          <Ledger runs={runs as any} evidence={evidence as any} onOpenEvidence={setModalEv} />
        </section>
      </div>

      {selBox && (
        <section className="card">
          <h3>{boxName[selBox]} <span className="muted">· {selEvidence.length} items</span></h3>
          <div className="evgrid">
            {selEvidence.map((e: any) => (
              <div className="evcard" key={e.id} role="button" tabIndex={0}
                   onClick={(ev) => { if (!isInteractiveClick(ev)) setModalEv(e); }}
                   onKeyDown={(ev) => {
                     if ((ev.key === "Enter" || ev.key === " ") && !isInteractiveClick(ev)) setModalEv(e);
                   }}>
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
        <h3>Prior art <span className="muted">· TMDB + web, ranked by meaning not genre</span></h3>
        {!priorArt && !surveying && (
          <>
            <p className="muted">
              Survey films with a similar premise and see where this one is still unclaimed.
            </p>
            <button onClick={doSurvey}>Survey prior art</button>
          </>
        )}
        {surveying && <p className="muted">Surveying TMDB and the web… this can take a minute.</p>}
        {priorArt && !!priorArt.neighbors?.length && (
          <>
            <p className="muted">
              {priorArt.surveyed} candidates surveyed
              {priorArt.keywords?.length ? `  ·  seed: ${priorArt.keywords.join(", ")}` : ""}
            </p>
            <div className="neighborgrid">
              {priorArt.neighbors.map((n: any, i: number) => (
                <a className="neighbor" key={i} href={n.url} target="_blank" rel="noopener">
                  {n.poster_url
                    ? <img className="neighbor-poster" src={n.poster_url} alt="" loading="lazy" />
                    : <div className="neighbor-poster neighbor-poster-blank">{(n.title || "?")[0]}</div>}
                  <div className="neighbor-title">{n.title} <span className="muted">{n.year}</span></div>
                  <div className="muted neighbor-tags">
                    {[n.pov, n.tone, n.engine].filter(Boolean).join(" · ")}
                  </div>
                  <div className="muted">similarity {Math.round((n.similarity ?? 0) * 100)}%</div>
                </a>
              ))}
            </div>
            {!!priorArt.unclaimed_angles?.length && (
              <>
                <h3>Unclaimed angles</h3>
                {priorArt.unclaimed_angles.map((a: any, i: number) => (
                  <div className="verdict angle" key={i}>
                    <div>{a.angle}</div>
                    {a.why && <div className="muted">{a.why}</div>}
                    {!!a.contrast_titles?.length && (
                      <div className="muted">checked against: {a.contrast_titles.join(", ")}</div>
                    )}
                    {a.prompt && <div className="muted">→ {a.prompt}</div>}
                  </div>
                ))}
              </>
            )}
            <button className="ghost" onClick={doSurvey} disabled={surveying}>
              {surveying ? "Surveying…" : "Re-survey"}
            </button>
          </>
        )}
        {priorArt && !priorArt.neighbors?.length && !surveying && (
          <>
            <p className="muted">No candidates found. Add a TMDB key on the backend and try again.</p>
            <button className="ghost" onClick={doSurvey}>Re-survey</button>
          </>
        )}
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
          <input value={q} onChange={(e) => setQ(e.target.value)} disabled={asking}
                 placeholder="What would our characters actually see and hear?"
                 onKeyDown={(e) => e.key === "Enter" && doAsk()} />
          <button onClick={doAsk} disabled={asking || !q.trim()}>{asking ? "Asking…" : "Ask"}</button>
        </div>
        {asking && <p className="muted">Consulting the index…</p>}
        {askErr && <p className="muted err">{askErr}</p>}
        {asked && !asking && !askErr && !answers.length && (
          <p className="muted">No matching evidence in the index.</p>
        )}
        {answers.map((a, i) => (
          <div className="answer" key={i} role="button" tabIndex={0}
               onClick={(ev) => { if (!isInteractiveClick(ev)) setModalEv(a); }}
               onKeyDown={(ev) => {
                 if ((ev.key === "Enter" || ev.key === " ") && !isInteractiveClick(ev)) setModalEv(a);
               }}>
            {a.modality && a.modality !== "text" && <MediaBit e={a} />}
            <Markdown>{a.text}</Markdown>
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
                      <button key={j} type="button" className="src-click" title={s.cite}
                              onClick={() => setModalEv(s)}>
                        <img className="ev-thumb" src={s.media_url || s.image_url} alt="" loading="lazy" />
                      </button>
                    );
                  }
                  if ((s.modality === "audio" || s.modality === "video" || s.modality === "pdf") && s.media_url) {
                    return (
                      <span key={j} className="beat-media"
                            onClick={(ev) => { if (!isInteractiveClick(ev)) setModalEv(s); }}>
                        <MediaBit e={s} /> <span className="muted">{s.cite}</span>
                      </span>
                    );
                  }
                  return <button key={j} type="button" className="src-link" onClick={() => setModalEv(s)}>{s.cite}</button>;
                })}
              </div>
            </div>
          ))}
        </section>
      )}

      <section className="card danger">
        <h3>Danger zone</h3>
        <div className="row">
          <span className="muted">Delete this project and everything in it. This cannot be undone.</span>
          {confirmDel ? (
            <>
              <button className="danger-btn" onClick={doDelete}>Delete for good</button>
              <button className="ghost" onClick={() => setConfirmDel(false)}>Cancel</button>
            </>
          ) : (
            <button className="ghost" onClick={() => setConfirmDel(true)}>Delete project</button>
          )}
        </div>
      </section>

      <EvidenceModal evidence={modalEv} boxName={boxName} onClose={() => setModalEv(null)} />
    </div>
  );
}
