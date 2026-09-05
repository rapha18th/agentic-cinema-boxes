import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listProjects, createProject, deleteProject } from "../api";
import { useAuth } from "../auth";
import { Landing } from "./Landing";
import { ThemeToggle } from "../components/ThemeToggle";
import { DepthPicker } from "../components/DepthPicker";
import type { DepthName, ProjectRecord } from "../types";

export function Projects() {
  const { user, signIn, logout } = useAuth();
  const nav = useNavigate();
  const [rows, setRows] = useState<ProjectRecord[]>([]);
  const [premise, setPremise] = useState("");
  const [depth, setDepth] = useState<DepthName>("scout");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [delId, setDelId] = useState<string | null>(null);

  useEffect(() => { if (user) listProjects().then(setRows).catch(() => {}); }, [user]);

  const remove = async (id: string) => {
    setRows((rs) => rs.filter((r) => r.id !== id));
    setDelId(null);
    try { await deleteProject(id); } catch { listProjects().then(setRows).catch(() => {}); }
  };

  if (!user) return <Landing onSignIn={signIn} />;

  const start = async () => {
    if (!premise.trim()) return;
    setBusy(true);
    setError("");
    try {
      const p = await createProject(premise.trim(), depth);
      nav(`/p/${p.id}`);
    } catch {
      setError("Could not create the project. Check the connection and try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="wrap">
      <header>
        <h1>THE BOXES</h1>
        <div className="head-actions">
          <ThemeToggle />
          <button className="ghost" onClick={logout}>Sign out</button>
        </div>
      </header>

      <section className="card">
        <h2>New project</h2>
        <textarea
          rows={3}
          placeholder="A film premise. e.g. Vienna, 1929. Four bank employees find a flaw that lets them remove millions without opening the vault."
          value={premise}
          onChange={(e) => setPremise(e.target.value)}
        />
        <div className="project-create-controls">
          <DepthPicker value={depth} onChange={setDepth} disabled={busy} />
          <button onClick={start} disabled={busy}>{busy ? "Creating…" : "Build the world"}</button>
        </div>
        {error && <p className="form-error" role="alert">{error}</p>}
      </section>

      <section>
        <h2>Projects</h2>
        {rows.map((r) => (
          <div className="proj" key={r.id}>
            <Link className="proj-main" to={`/p/${r.id}`}>
              <span>{r.premise}</span>
              <span className="muted">{r.status} · {Math.round((r.confidence ?? 0) * 100)}%</span>
            </Link>
            {delId === r.id ? (
              <span className="proj-del">
                <button className="danger-btn" onClick={() => remove(r.id)}>Delete</button>
                <button className="linkish muted" onClick={() => setDelId(null)}>cancel</button>
              </span>
            ) : (
              <button className="proj-del linkish muted" title="Delete project"
                      onClick={() => setDelId(r.id)}>✕</button>
            )}
          </div>
        ))}
        {!rows.length && <p className="muted">None yet.</p>}
      </section>
    </div>
  );
}
