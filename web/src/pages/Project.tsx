import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ResearchConsole, type Progress } from "../components/ResearchConsole";
import { ThemeToggle } from "../components/ThemeToggle";
import { DepthPicker } from "../components/DepthPicker";
import { EvidenceModal } from "../components/EvidenceModal";
import { Markdown } from "../components/Markdown";
import { useBoxes, useEvidence, usePriorArt, useProject, useReel, useRuns, useVerdicts } from "../data";
import { ask, deleteProject, downloadReport, runProject, surveyPriorArt, updateProject, uploadResource } from "../api";
import {
  DepartmentsTab, EvidenceTab, OverviewTab, PriorArtTab, TAB_IDS, TraceTab,
  conflictMap, pctOf, type TabId,
} from "../workspace/tabs";
import type { AskResponse, DepthName, Evidence, ResearchBox, ResearchRun, Verdict } from "../types";

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

  const [tab, setTab] = useState<TabId>("overview");
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
  const [dept, setDept] = useState<string | null>(null);
  const [uploadBox, setUploadBox] = useState("");
  const [uploading, setUploading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editPremise, setEditPremise] = useState("");
  const [editDepth, setEditDepth] = useState<DepthName>("scout");
  const [saving, setSaving] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const [surveying, setSurveying] = useState(false);
  const [priorArtLocal, setPriorArtLocal] = useState<Record<string, unknown> | null>(null);
  const [modalEv, setModalEv] = useState<Evidence | null>(null);
  const priorArt = (priorArtDoc || priorArtLocal) as any;

  const boxName = useMemo(() => Object.fromEntries(boxes.map((b) => [b.id, b.name])), [boxes]);
  const allEvidence = useMemo(() => {
    const seen = new Set(evidence.map((e) => e.id));
    return [...evidence, ...liveEv.filter((e) => !seen.has(e.id))];
  }, [evidence, liveEv]);
  const conflicts = useMemo(() => conflictMap(verdicts), [verdicts]);
  const highlights = useMemo(
    () => [...allEvidence].sort((a, b) => (b.quality_score ?? 0) - (a.quality_score ?? 0)).slice(0, 3),
    [allEvidence],
  );
  const primaryCount = allEvidence.filter((e) => e.source_tier === "primary").length;
  const domainCount = new Set(allEvidence.map((e) => e.source_domain).filter(Boolean)).size;
  const openRisks = (project?.unresolved_contradictions ?? 0) + boxes.filter((b) => (b.score ?? 0) < 0.65).length;
  const push = (s: string) => setActivity((a) => [...a.slice(-120), s]);
  const goto = (t: TabId, boxId?: string) => { setTab(t); if (boxId !== undefined) setSelBox(boxId); };

  const start = async () => {
    setRunning(true); setStreamLost(false); setActivity([]); setLiveEv([]); setTab("trace");
    setProgress({ phase: "planning" });
    try {
      await runProject(pid, (ev) => {
        if (ev.type === "progress") setProgress((p) => ({ ...p, ...ev }));
        else if (ev.type === "disconnect") { setStreamLost(true); push(`FEED LOST · ${ev.reason}; saved progress remains live`); }
        else if (ev.type === "evidence") { setLiveEv((cur) => [...cur, ...ev.items]); push(`KEPT    ${ev.items.length} fragments · ${ev.objective}`); }
        else if (ev.type === "search") push(`SEARCH  ${ev.objective} · ${ev.queries?.[0] || ""}`);
        else if (ev.type === "extract") push(`EXTRACT ${ev.objective} · ${ev.sources} sources · ${ev.rejected ?? 0} rejected`);
        else if (ev.type === "coverage") push(`MEASURE ${ev.summary}`);
        else if (ev.type === "emergent_gap") push(`DECIDE  opened ${ev.objective.name} · a recurring cross-box signal`);
        else if (ev.type === "contradiction") push(`VERIFY  ${ev.verdict.relation} · ${ev.verdict.a_cite} vs ${ev.verdict.b_cite}`);
        else if (ev.type === "stop") push(`STOP    ${ev.reason}`);
        else if (ev.type === "complete") { push(`DONE    ${ev.evidence} fragments · ${pctOf(ev.confidence)}`); setProgress((p) => ({ ...p, phase: "done" })); setTab("overview"); }
        else if (ev.type === "error") push(`ERROR   ${ev.error}`);
      });
    } catch (e) { push(`ERROR   ${String((e as Error)?.message || e)}`); }
    finally { setRunning(false); }
  };
  const doAsk = async () => {
    if (!q.trim() || asking) return;
    setAsking(true); setAskErr(""); setAnswer(null);
    try { setAnswer(await ask(pid, q.trim())); }
    catch (e) {
      const msg = String((e as Error)?.message || e);
      setAskErr(/no research yet|409/i.test(msg)
        ? "Nothing is indexed yet. Run the research first."
        : "The index could not answer. Try again in a moment.");
    } finally { setAsking(false); }
  };
  const beginEdit = () => { setEditPremise(project?.premise || ""); setEditDepth(project?.depth || "scout"); setEditing(true); };
  const saveEdit = async () => {
    if (!editPremise.trim() || saving) return;
    setSaving(true);
    try { await updateProject(pid, { premise: editPremise.trim(), depth: editDepth }); setEditing(false); }
    finally { setSaving(false); }
  };
  const getReport = async () => {
    if (reporting) return;
    setReporting(true);
    try { await downloadReport(pid); } catch { push("REPORT  build failed"); }
    finally { setReporting(false); }
  };
  const doSurvey = async () => {
    if (surveying) return;
    setSurveying(true);
    try { setPriorArtLocal(await surveyPriorArt(pid)); }
    catch (e) { push(`PRIOR   ${String((e as Error)?.message || e)}`); }
    finally { setSurveying(false); }
  };
  const doUpload = async (f: File) => {
    setUploading(true); push(`UPLOAD  ${f.name} → ${boxName[uploadBox] || "unfiled"}`);
    try { await uploadResource(pid, f, uploadBox, ""); push(`KEPT    ${f.name}`); }
    catch (e) { push(`REJECT  ${String((e as Error)?.message || e)}`); }
    finally { setUploading(false); }
  };

  if (!project) return (
    <div className="wrap">
      <header><Link to="/" className="ghost">← projects</Link><ThemeToggle /></header>
      <p className="muted">Opening the archive…</p>
    </div>
  );

  const shownProgress = streamLost ? { ...progress, ...(project.progress || {}) } as Progress : progress;
  const runDone = !running && (progress.phase === "done" || project.status === "done");

  return (
    <div className="wrap workspace">
      <header>
        <Link to="/" className="ghost">← THE BOXES</Link>
        <div className="head-actions">
          <span className={`status-pill ${project.status}`}>{project.status}</span>
          <ThemeToggle />
        </div>
      </header>

      {editing ? (
        <section className="card edit-card">
          <p className="eyebrow">Edit project</p>
          <textarea rows={3} value={editPremise} onChange={(e) => setEditPremise(e.target.value)} />
          <p className="edit-warning">Changing the premise starts a new research version. The existing archive stays available until the next run begins.</p>
          <div className="project-create-controls">
            <DepthPicker value={editDepth} onChange={setEditDepth} disabled={saving} />
            <div className="row">
              <button onClick={saveEdit} disabled={saving || !editPremise.trim()}>{saving ? "Saving…" : "Save"}</button>
              <button className="ghost" onClick={() => setEditing(false)}>Cancel</button>
            </div>
          </div>
        </section>
      ) : (
        <section className="project-hero">
          <div>
            <p className="eyebrow">Production research dossier</p>
            <h1 className="project-title">{project.title || "UNTITLED FILM"}</h1>
            <p className="premise">{project.premise}</p>
          </div>
          <div className="hero-actions">
            <button onClick={start} disabled={running}>{running ? "Researching…" : runs.length ? "Refresh research" : "Start research"}</button>
            <button className="ghost" onClick={getReport} disabled={reporting}>{reporting ? "Building…" : "Download dossier"}</button>
            <button className="ghost" onClick={beginEdit}>Edit</button>
          </div>
        </section>
      )}

      <div className="metric-grid" aria-label="Research summary">
        <div className="metric"><span>Readiness</span><b>{pctOf(project.confidence)}</b><small>research completeness</small></div>
        <div className="metric"><span>Evidence</span><b>{allEvidence.length}</b><small>{boxes.length} research boxes</small></div>
        <div className="metric"><span>Primary records</span><b>{primaryCount}</b><small>{domainCount} independent domains</small></div>
        <div className="metric"><span>Open risks</span><b>{openRisks}</b><small>{project.unresolved_contradictions || 0} factual conflicts</small></div>
      </div>

      <nav className="workspace-tabs" aria-label="Dossier sections">
        {TAB_IDS.map((id) => (
          <button key={id} className={tab === id ? "on" : ""} onClick={() => setTab(id)}>{id}</button>
        ))}
      </nav>

      {tab === "overview" && (
        <OverviewTab
          overview={project.overview}
          boxes={boxes}
          highlights={highlights}
          reel={reel}
          conflicts={conflicts}
          onOpen={setModalEv}
          onGoto={goto}
          sideSlot={
            <div className="card">
              <p className="eyebrow">Ask the boxes</p>
              <div className="ask-compose">
                <input value={q} onChange={(e) => setQ(e.target.value)} disabled={asking}
                       placeholder="What would our characters actually see and hear?"
                       onKeyDown={(e) => e.key === "Enter" && doAsk()} />
                <button onClick={doAsk} disabled={asking || !q.trim()}>{asking ? "Consulting…" : "Ask"}</button>
              </div>
              {askErr && <p className="form-error" role="alert">{askErr}</p>}
              {answer && (
                <div className="grounded-answer">
                  <span className={answer.sufficient ? "source-badge primary" : "source-badge web"}>
                    {answer.sufficient ? "grounded answer" : "insufficient evidence"}
                  </span>
                  <Markdown>{answer.answer}</Markdown>
                  <div className="answer-sources">
                    {answer.sources.map((s, i) => (
                      <button className="src-link" key={s.id || i} onClick={() => setModalEv(s)}>
                        [{i + 1}] {s.title || s.source_domain}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          }
        />
      )}

      {tab === "departments" && (
        <DepartmentsTab boxes={boxes} evidence={allEvidence} onOpen={setModalEv} conflicts={conflicts} />
      )}

      {tab === "evidence" && (
        <EvidenceTab
          boxes={boxes} evidence={allEvidence}
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
                <select value={uploadBox} onChange={(e) => setUploadBox(e.target.value)}>
                  <option value="">file under: unfiled</option>
                  {boxes.map((b) => <option key={b.id} value={b.id}>file under: {b.name}</option>)}
                </select>
                <input type="file" accept="text/plain,application/pdf,image/png,image/jpeg,image/webp"
                       disabled={uploading} onChange={(e) => e.target.files?.[0] && doUpload(e.target.files[0])} />
              </div>
              <p className="muted">
                {uploading ? "Embedding…" : "Text, PDF, PNG, JPEG, or WebP · up to 12 MB · embedded natively alongside the agent's findings."}
              </p>
            </section>
          }
        />
      )}

      {tab === "trace" && (
        <TraceTab
          runs={runs} verdicts={verdicts} boxes={boxes} evidence={allEvidence}
          onOpen={setModalEv}
          activityLines={activity}
          stopReason={project.stop_reason}
          consoleSlot={
            (running || streamLost || progress.phase === "done") ? (
              <ResearchConsole
                progress={shownProgress}
                log={activity}
                done={runDone}
                disconnected={streamLost && !runDone}
                errorText={project.status === "error" ? project.error || "see the decision log" : ""}
              />
            ) : null
          }
        />
      )}

      {tab === "prior-art" && (
        <PriorArtTab priorArt={priorArt} onSurvey={doSurvey} surveying={surveying} />
      )}

      <details className="danger-disclosure">
        <summary>Project settings</summary>
        <section className="card danger">
          <p className="eyebrow">Danger zone</p>
          <div className="row">
            <span className="muted">Delete this project and its archive.</span>
            {confirmDel ? (
              <>
                <button className="danger-btn" onClick={async () => { await deleteProject(pid); nav("/"); }}>Delete for good</button>
                <button className="ghost" onClick={() => setConfirmDel(false)}>Cancel</button>
              </>
            ) : (
              <button className="ghost" onClick={() => setConfirmDel(true)}>Delete project</button>
            )}
          </div>
        </section>
      </details>

      <EvidenceModal
        evidence={modalEv} boxName={boxName}
        conflict={modalEv ? conflicts[modalEv.id] : null}
        onClose={() => setModalEv(null)}
      />
    </div>
  );
}
