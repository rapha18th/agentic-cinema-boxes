import { auth } from "./firebase";

const BASE = import.meta.env.VITE_API_BASE ?? "";

async function headers(): Promise<Record<string, string>> {
  const t = auth.currentUser ? await auth.currentUser.getIdToken() : null;
  return t ? { Authorization: `Bearer ${t}`, "Content-Type": "application/json" }
           : { "Content-Type": "application/json" };
}

export async function listProjects() {
  const r = await fetch(`${BASE}/api/projects`, { headers: await headers() });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()).projects as any[];
}

export async function createProject(premise: string, depth: string) {
  const r = await fetch(`${BASE}/api/projects`, {
    method: "POST", headers: await headers(), body: JSON.stringify({ premise, depth }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function updateProject(pid: string, patch: { premise?: string; depth?: string }) {
  const r = await fetch(`${BASE}/api/projects/${pid}`, {
    method: "PATCH", headers: await headers(), body: JSON.stringify(patch),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function deleteProject(pid: string) {
  const r = await fetch(`${BASE}/api/projects/${pid}`, {
    method: "DELETE", headers: await headers(),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

/** Fetch the PDF dossier with auth, then hand it to the browser to save. */
export async function downloadReport(pid: string) {
  const r = await fetch(`${BASE}/api/projects/${pid}/report.pdf`, { headers: await headers() });
  if (!r.ok) throw new Error(await r.text());
  const blob = await r.blob();
  const cd = r.headers.get("Content-Disposition") || "";
  const name = /filename="?([^"]+)"?/.exec(cd)?.[1] || `the-boxes-${pid}.pdf`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

export async function ask(pid: string, question: string) {
  const r = await fetch(`${BASE}/api/projects/${pid}/ask`, {
    method: "POST", headers: await headers(), body: JSON.stringify({ question }),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()).matches as any[];
}

export async function uploadResource(pid: string, file: File, objectiveId: string, note: string) {
  const t = auth.currentUser ? await auth.currentUser.getIdToken() : null;
  const fd = new FormData();
  fd.append("file", file);
  const qs = new URLSearchParams({ objective_id: objectiveId, note });
  const r = await fetch(`${BASE}/api/projects/${pid}/resources?${qs}`, {
    method: "POST", headers: t ? { Authorization: `Bearer ${t}` } : {}, body: fd,
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

/** Stream the research loop's server-sent events. */
export async function runProject(
  pid: string,
  onEvent: (ev: any) => void,
  signal?: AbortSignal,
) {
  const t = auth.currentUser ? await auth.currentUser.getIdToken() : null;
  const r = await fetch(`${BASE}/api/projects/${pid}/run`, {
    method: "POST",
    headers: t ? { Authorization: `Bearer ${t}` } : {},
    signal,
  });
  if (!r.ok || !r.body) throw new Error(await r.text());
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() ?? "";
    for (const p of parts) {
      const line = p.trim();
      if (line.startsWith("data:")) {
        try { onEvent(JSON.parse(line.slice(5).trim())); } catch { /* ignore */ }
      }
    }
  }
}
