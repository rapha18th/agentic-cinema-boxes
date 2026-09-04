import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listProjects, createProject } from "../api";
import { useAuth } from "../auth";
import { Landing } from "./Landing";
import { ThemeToggle } from "../components/ThemeToggle";

export function Projects() {
  const { user, signIn, logout } = useAuth();
  const nav = useNavigate();
  const [rows, setRows] = useState<any[]>([]);
  const [premise, setPremise] = useState("");
  const [depth, setDepth] = useState("scout");
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (user) listProjects().then(setRows).catch(() => {}); }, [user]);

  if (!user) return <Landing onSignIn={signIn} />;

  const start = async () => {
    if (!premise.trim()) return;
    setBusy(true);
    try {
      const p = await createProject(premise.trim(), depth);
      nav(`/p/${p.id}`);
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
        <div className="row">
          <select value={depth} onChange={(e) => setDepth(e.target.value)}>
            <option value="scout">Scout · minutes</option>
            <option value="production">Production · deeper</option>
            <option value="kubrick">Kubrick · obsessive</option>
          </select>
          <button onClick={start} disabled={busy}>{busy ? "Creating…" : "Build the world"}</button>
        </div>
      </section>

      <section>
        <h2>Projects</h2>
        {rows.map((r) => (
          <Link className="proj" key={r.id} to={`/p/${r.id}`}>
            <span>{r.premise}</span>
            <span className="muted">{r.status} · {Math.round((r.confidence ?? 0) * 100)}%</span>
          </Link>
        ))}
        {!rows.length && <p className="muted">None yet.</p>}
      </section>
    </div>
  );
}
