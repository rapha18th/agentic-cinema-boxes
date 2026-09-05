import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ResearchMap } from "../components/ResearchMap";
import { Ledger } from "../components/Ledger";
import { MediaBit } from "../components/Media";
import { ResearchConsole, type Progress } from "../components/ResearchConsole";
import { ThemeToggle } from "../components/ThemeToggle";
import { DepthPicker } from "../components/DepthPicker";
import { EvidenceModal, isInteractiveClick } from "../components/EvidenceModal";
import { Markdown } from "../components/Markdown";
import { useBoxes, useEvidence, usePriorArt, useProject, useReel, useRuns, useVerdicts } from "../data";
import { ask, deleteProject, downloadReport, runProject, surveyPriorArt, updateProject, uploadResource } from "../api";
import { DEPARTMENTS, DEPT_LABEL } from "../departments";
import type { AskResponse, DepthName, Evidence, ResearchBox, ResearchRun, Verdict } from "../types";

const pct = (x?: number) => `${Math.round((x ?? 0) * 100)}%`;
type Tab = "overview" | "departments" | "evidence" | "trace" | "prior-art";

function EvidenceCards({ items, onOpen }: { items: Evidence[]; onOpen: (e: Evidence) => void }) {
  return <div className="evgrid">{items.map((e) => (
    <div className="evcard" key={e.id} role="button" tabIndex={0}
         onClick={(ev) => { if (!isInteractiveClick(ev)) onOpen(e); }}
         onKeyDown={(ev) => { if ((ev.key === "Enter" || ev.key === " ") && !isInteractiveClick(ev)) onOpen(e); }}>
      <span className={`source-badge ${e.source_tier || "web"}`}>{e.source_tier || "web source"}</span>
      {e.modality && e.modality !== "text" ? <MediaBit e={e} size="full" /> : <div className="evtext">{(e.text || "").slice(0, 260)}</div>}
      <div className="muted">{e.url ? <a href={e.url} target="_blank" rel="noopener">{[e.title || e.source_domain, e.publish_date].filter(Boolean).join(" · ")}</a> : [e.title || e.source_domain, e.publish_date].filter(Boolean).join(" · ")}{e.source === "director" ? " · your upload" : ""}</div>
    </div>
  ))}</div>;
}

export function Project() {
  const { pid = "" } = useParams();
  const nav = useNavigate();
  const project = useProject(pid);
  const boxes = useBoxes(pid) as ResearchBox[];
  const evidence = useEvidence(pid) as Evidence[];
  const runs = useRuns(pid) as ResearchRun[];
  const verdicts = useVerdicts(pid) as Verdict[];
  const reel = useReel(pid);
  const priorArtDoc = usePriorArt(pid);
  const [tab, setTab] = useState<Tab>("overview");
  const [activity, setActivity] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [streamLost, setStreamLost] = useState(false);
  const [progress, setProgress] = useState<Progress>({});
  const [liveEv, setLiveEv] = useState<Evidence[]>([]);
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [asking, setAsking] = useState(false);
  const [askErr, setAskErr] = useState("");
  const [selBox, setSelBox] = useState<string | null>(null);
  const [uploadBox, setUploadBox] = useState("");
  const [uploading, setUploading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editPremise, setEditPremise] = useState("");
  const [editDepth, setEditDepth] = useState<DepthName>("scout");
  const [saving, setSaving] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const [dept, setDept] = useState<string | null>(null);
  const [surveying, setSurveying] = useState(false);
  const [priorArtLocal, setPriorArtLocal] = useState<Record<string, unknown> | null>(null);
  const [modalEv, setModalEv] = useState<Evidence | null>(null);
  const priorArt = (priorArtDoc || priorArtLocal) as any;

  const boxName = useMemo(() => Object.fromEntries(boxes.map((b) => [b.id, b.name])), [boxes]);
  const allEvidence = useMemo(() => { const seen = new Set(evidence.map((e) => e.id)); return [...evidence, ...liveEv.filter((e) => !seen.has(e.id))]; }, [evidence, liveEv]);
  const selEvidence = useMemo(() => selBox ? allEvidence.filter((e) => e.objective_id === selBox) : [], [selBox, allEvidence]);
  const sortedBoxes = useMemo(() => [...boxes].sort((a, b) => (a.score ?? 0) - (b.score ?? 0)), [boxes]);
  const highlights = useMemo(() => [...allEvidence].sort((a, b) => (b.quality_score ?? 0) - (a.quality_score ?? 0)).slice(0, 3), [allEvidence]);
  const deptsPresent = useMemo(() => { const set = new Set<string>(); boxes.forEach((b) => (b.departments || []).forEach((d) => set.add(d))); return DEPARTMENTS.filter((d) => set.has(d)); }, [boxes]);
  const filteredBoxes = useMemo(() => dept ? boxes.filter((b) => (b.departments || []).includes(dept)) : boxes, [boxes, dept]);
  const filteredEvidence = useMemo(() => { if (!dept) return allEvidence; const ids = new Set(filteredBoxes.map((b) => b.id)); return allEvidence.filter((e) => ids.has(e.objective_id || "")); }, [allEvidence, dept, filteredBoxes]);
  const primaryCount = allEvidence.filter((e) => e.source_tier === "primary").length;
  const openRisks = (project?.unresolved_contradictions ?? 0) + boxes.filter((b) => (b.score ?? 0) < .65).length;
  const push = (s: string) => setActivity((a) => [...a.slice(-120), s]);

  const start = async () => {
    setRunning(true); setStreamLost(false); setActivity([]); setLiveEv([]); setTab("trace"); setProgress({ phase: "planning" });
    try { await runProject(pid, (ev) => {
      if (ev.type === "progress") setProgress((p) => ({ ...p, ...ev }));
      else if (ev.type === "disconnect") { setStreamLost(true); push(`FEED LOST — ${ev.reason}; saved progress remains live`); }
      else if (ev.type === "evidence") { setLiveEv((cur) => [...cur, ...ev.items]); push(`KEPT    ${ev.items.length} fragments · ${ev.objective}`); }
      else if (ev.type === "search") push(`SEARCH  ${ev.objective} · ${ev.queries?.[0] || ""}`);
      else if (ev.type === "extract") push(`EXTRACT ${ev.objective} · ${ev.sources} sources · ${ev.rejected ?? 0} rejected`);
      else if (ev.type === "coverage") push(`MEASURE ${ev.summary}`);
      else if (ev.type === "emergent_gap") push(`DECIDE  opened ${ev.objective.name} · recurring cross-box signal`);
      else if (ev.type === "contradiction") push(`VERIFY  ${ev.verdict.relation} · ${ev.verdict.a_cite} vs ${ev.verdict.b_cite}`);
      else if (ev.type === "stop") push(`STOP    ${ev.reason}`);
      else if (ev.type === "complete") { push(`DONE    ${ev.evidence} fragments · ${pct(ev.confidence)}`); setProgress((p) => ({ ...p, phase: "done" })); setTab("overview"); }
      else if (ev.type === "error") push(`ERROR   ${ev.error}`);
    }); } catch (e) { push(`ERROR   ${String((e as Error)?.message || e)}`); } finally { setRunning(false); }
  };
  const doAsk = async () => { if (!q.trim() || asking) return; setAsking(true); setAskErr(""); setAnswer(null); try { setAnswer(await ask(pid, q.trim())); } catch (e) { const msg = String((e as Error)?.message || e); setAskErr(/no research yet|409/i.test(msg) ? "Nothing is indexed yet. Run the research first." : "The index could not answer. Try again in a moment."); } finally { setAsking(false); } };
  const beginEdit = () => { setEditPremise(project?.premise || ""); setEditDepth(project?.depth || "scout"); setEditing(true); };
  const saveEdit = async () => { if (!editPremise.trim() || saving) return; setSaving(true); try { await updateProject(pid, { premise: editPremise.trim(), depth: editDepth }); setEditing(false); } finally { setSaving(false); } };
  const getReport = async () => { if (reporting) return; setReporting(true); try { await downloadReport(pid); } catch { push("REPORT  build failed"); } finally { setReporting(false); } };
  const doSurvey = async () => { if (surveying) return; setSurveying(true); try { setPriorArtLocal(await surveyPriorArt(pid)); } catch (e) { push(`PRIOR   ${String((e as Error)?.message || e)}`); } finally { setSurveying(false); } };
  const doUpload = async (f: File) => { setUploading(true); push(`UPLOAD  ${f.name} → ${boxName[uploadBox] || "unfiled"}`); try { await uploadResource(pid, f, uploadBox, ""); push(`KEPT    ${f.name}`); } catch (e) { push(`REJECT  ${String((e as Error)?.message || e)}`); } finally { setUploading(false); } };

  if (!project) return <div className="wrap"><header><Link to="/" className="ghost">← projects</Link><ThemeToggle /></header><p className="muted">Opening the archive…</p></div>;
  const shownProgress = streamLost ? { ...progress, ...(project.progress || {}) } as Progress : progress;
  const runDone = !running && (progress.phase === "done" || project.status === "done");

  return <div className="wrap workspace">
    <header><Link to="/" className="ghost">← THE BOXES</Link><div className="head-actions"><span className={`status-pill ${project.status}`}>{project.status}</span><ThemeToggle /></div></header>
    {editing ? <section className="card edit-card"><p className="eyebrow">Edit project</p><textarea rows={3} value={editPremise} onChange={(e) => setEditPremise(e.target.value)} /><p className="edit-warning">Changing the premise starts a new research version. The existing archive remains available until the next run begins.</p><div className="project-create-controls"><DepthPicker value={editDepth} onChange={setEditDepth} disabled={saving} /><div className="row"><button onClick={saveEdit} disabled={saving || !editPremise.trim()}>{saving ? "Saving…" : "Save"}</button><button className="ghost" onClick={() => setEditing(false)}>Cancel</button></div></div></section> : <section className="project-hero"><div><p className="eyebrow">Production research dossier</p><h1 className="project-title">{project.title || "UNTITLED FILM"}</h1><p className="premise">{project.premise}</p></div><div className="hero-actions"><button onClick={start} disabled={running}>{running ? "Researching…" : runs.length ? "Refresh research" : "Start research"}</button><button className="ghost" onClick={getReport} disabled={reporting}>{reporting ? "Building…" : "Download dossier"}</button><button className="ghost" onClick={beginEdit}>Edit</button></div></section>}
    <div className="metric-grid"><div className="metric"><span>Readiness</span><b>{pct(project.confidence)}</b><small>research completeness</small></div><div className="metric"><span>Evidence</span><b>{allEvidence.length}</b><small>{boxes.length} research boxes</small></div><div className="metric"><span>Primary records</span><b>{primaryCount}</b><small>{new Set(allEvidence.map((e) => e.source_domain).filter(Boolean)).size} independent domains</small></div><div className="metric"><span>Open risks</span><b>{openRisks}</b><small>{project.unresolved_contradictions || 0} factual conflicts</small></div></div>
    <nav className="workspace-tabs" aria-label="Dossier sections">{(["overview", "departments", "evidence", "trace", "prior-art"] as Tab[]).map((id) => <button key={id} className={tab === id ? "on" : ""} onClick={() => setTab(id)}>{id}</button>)}</nav>

    {tab === "overview" && <><section className="brief-lead"><div><p className="eyebrow">The research picture</p><h2 className="display-heading">{project.overview || (boxes.length ? "The archive is ready to turn evidence into production decisions." : "Start a research run to build the world behind this premise.")}</h2></div><aside className="decision-card"><span className="signal">Next decision</span><b>{sortedBoxes[0]?.name || "Draw the research plan"}</b><p>{sortedBoxes[0]?.rationale || sortedBoxes[0]?.description || "The agent will identify the first evidence gap and pursue it."}</p></aside></section>{!!highlights.length && <section className="card"><div className="section-head"><div><p className="eyebrow">Strongest evidence</p><h2 className="display-heading small">What the crew can use now</h2></div><button className="ghost" onClick={() => setTab("evidence")}>Audit evidence →</button></div><EvidenceCards items={highlights} onOpen={setModalEv} /></section>}<section className="risk-grid"><div className="card"><p className="eyebrow">Thin research boxes</p>{sortedBoxes.slice(0, 3).map((b) => <button className="risk-row" key={b.id} onClick={() => { setSelBox(b.id); setTab("evidence"); }}><span>{b.name}</span><b>{pct(b.score)}</b><small>{b.distinct_domains ?? 0} independent domains</small></button>)}{!boxes.length && <p className="muted">The first run will make gaps explicit.</p>}</div><div className="card"><p className="eyebrow">Ask the boxes</p><div className="ask-compose"><input value={q} onChange={(e) => setQ(e.target.value)} disabled={asking} placeholder="What would our characters actually see and hear?" onKeyDown={(e) => e.key === "Enter" && doAsk()} /><button onClick={doAsk} disabled={asking || !q.trim()}>{asking ? "Consulting…" : "Ask"}</button></div>{askErr && <p className="form-error" role="alert">{askErr}</p>}{answer && <div className="grounded-answer"><span className={answer.sufficient ? "source-badge primary" : "source-badge web"}>{answer.sufficient ? "grounded answer" : "insufficient evidence"}</span><Markdown>{answer.answer}</Markdown><div className="answer-sources">{answer.sources.map((s, i) => <button className="src-link" key={s.id || i} onClick={() => setModalEv(s)}>[{i + 1}] {s.title || s.source_domain}</button>)}</div></div>}</div></section></>}
    {tab === "departments" && <section className="department-grid">{deptsPresent.map((d) => { const mine = boxes.filter((b) => b.departments?.includes(d)); return <article className="card department-card" key={d}><p className="eyebrow">{DEPT_LABEL[d] || d}</p>{mine.map((b) => <div key={b.id}><b>{b.name} <span className="muted">{pct(b.score)}</span></b><p>{b.summary || b.description}</p></div>)}</article>; })}{!deptsPresent.length && <div className="card"><p className="muted">Department packets appear after the plan is drawn.</p></div>}</section>}
    {tab === "evidence" && <><section className="card"><div className="section-head"><div><p className="eyebrow">Semantic evidence space</p><h2 className="display-heading small">Every claim remains inspectable</h2></div><span className="muted">click a box or fragment</span></div>{!!deptsPresent.length && <div className="dept-bar"><button className={`chip ${!dept ? "on" : ""}`} onClick={() => { setDept(null); setSelBox(null); }}>All</button>{deptsPresent.map((d) => <button key={d} className={`chip ${dept === d ? "on" : ""}`} onClick={() => { setDept(dept === d ? null : d); setSelBox(null); }}>{DEPT_LABEL[d] || d}</button>)}</div>}<ResearchMap boxes={filteredBoxes} evidence={filteredEvidence} selected={selBox} onSelect={setSelBox} onOpenEvidence={setModalEv} /><div className="boxwrap">{[...filteredBoxes].sort((a, b) => (a.score ?? 0) - (b.score ?? 0)).map((b) => { const count = allEvidence.filter((e) => e.objective_id === b.id).length; return <button className={`box ${selBox === b.id ? "on" : ""}`} key={b.id} onClick={() => setSelBox(selBox === b.id ? null : b.id)}><div className="box-name">{b.name}{b.emergent ? " ✦" : ""}</div><div className="bar"><span style={{ width: `${(b.score ?? 0) * 100}%` }} /></div><div className="muted">{Math.max(b.evidence_count ?? 0, count)} items · {b.distinct_domains ?? 0} domains</div></button>; })}</div></section>{selBox && <section className="card"><h3>{boxName[selBox]} · {selEvidence.length} items</h3><EvidenceCards items={selEvidence} onOpen={setModalEv} /></section>}<section className="card"><p className="eyebrow">Add your own reference</p><div className="upload-row"><select value={uploadBox} onChange={(e) => setUploadBox(e.target.value)}><option value="">unfiled</option>{boxes.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select><input type="file" accept="text/plain,application/pdf,image/png,image/jpeg,image/webp" disabled={uploading} onChange={(e) => e.target.files?.[0] && doUpload(e.target.files[0])} /></div><p className="muted">Text, PDF, PNG, JPEG, or WebP · maximum 12 MB · embedded natively into the same evidence space.</p></section></>}
    {tab === "trace" && <>{(running || streamLost || progress.phase === "done") && <ResearchConsole progress={shownProgress} log={activity} done={runDone} disconnected={streamLost && !runDone} errorText={project.status === "error" ? project.error || "see the decision log" : ""} />}<section className="trace-grid"><div className="card"><p className="eyebrow">Agent decisions</p><div className="decision-timeline">{activity.length ? activity.map((line, i) => <div key={i}><b>{String(i + 1).padStart(2, "0")}</b><p>{line}</p></div>) : <div><b>Standing by</b><p>Start a run to see every search, rejection, gap, verification, and stopping decision.</p></div>}</div></div><div className="card"><p className="eyebrow">Research ledger</p><Ledger runs={runs} evidence={evidence} onOpenEvidence={setModalEv} /></div></section><section className="card"><p className="eyebrow">Cross-examined sources</p>{verdicts.map((v, i) => <div className={`verdict ${v.relation}`} key={v.id || i}><b>{v.relation}</b> — {v.explanation}<div className="muted">A: {v.a_cite}</div><div className="muted">B: {v.b_cite}</div></div>)}{!verdicts.length && <p className="muted">No unresolved conflicts found yet.</p>}</section></>}
    {tab === "prior-art" && <section className="card"><div className="section-head"><div><p className="eyebrow">Prior art</p><h2 className="display-heading small">Where this premise remains unclaimed</h2></div>{priorArt && <button className="ghost" onClick={doSurvey} disabled={surveying}>{surveying ? "Surveying…" : "Re-survey"}</button>}</div>{!priorArt && !surveying && <><p className="muted">Survey films with a similar premise, ranked by meaning rather than genre.</p><button onClick={doSurvey}>Survey prior art</button></>}{surveying && <p className="muted">Surveying TMDB and the live web…</p>}{priorArt?.neighbors?.length && <><p className="muted">{priorArt.surveyed} candidates surveyed</p><div className="neighborgrid">{priorArt.neighbors.map((n: any, i: number) => <a className="neighbor" key={i} href={n.url} target="_blank" rel="noopener">{n.poster_url ? <img className="neighbor-poster" src={n.poster_url} alt="" loading="lazy" /> : <div className="neighbor-poster neighbor-poster-blank">{(n.title || "?")[0]}</div>}<div className="neighbor-title">{n.title} <span className="muted">{n.year}</span></div><div className="muted">similarity {pct(n.similarity)}</div></a>)}</div>{priorArt.unclaimed_angles?.map((a: any, i: number) => <div className="verdict angle" key={i}><b>{a.angle}</b>{a.why && <p>{a.why}</p>}<div className="muted">checked against: {(a.contrast_titles || []).join(", ")}</div></div>)}</>}</section>}
    {!!reel.length && tab === "overview" && <section className="card"><p className="eyebrow">Reference sequence</p>{reel.map((b: any, i: number) => <div className="beat" key={i}><div><b>{b.t}</b> {b.title} — {b.note}</div><div className="beat-src">{(b.sources || []).map((s: Evidence, j: number) => <button key={j} className="src-link" onClick={() => setModalEv(s)}>{s.cite || s.title || `source ${j + 1}`}</button>)}</div></div>)}</section>}
    <details className="danger-disclosure"><summary>Project settings</summary><section className="card danger"><p className="eyebrow">Danger zone</p><div className="row"><span className="muted">Delete this project and its archive.</span>{confirmDel ? <><button className="danger-btn" onClick={async () => { await deleteProject(pid); nav("/"); }}>Delete for good</button><button className="ghost" onClick={() => setConfirmDel(false)}>Cancel</button></> : <button className="ghost" onClick={() => setConfirmDel(true)}>Delete project</button>}</div></section></details>
    <EvidenceModal evidence={modalEv} boxName={boxName} onClose={() => setModalEv(null)} />
  </div>;
}
