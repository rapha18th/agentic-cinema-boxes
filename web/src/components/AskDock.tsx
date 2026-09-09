import { useEffect, useRef, useState } from "react";
import { ask } from "../api";
import { Markdown } from "./Markdown";
import { MediaBit } from "./Media";
import type { AskResponse, Evidence, Verdict } from "../types";

type Turn = { q: string; res?: AskResponse; error?: string };

/** A grounded-answer chat, docked bottom-right on every tab. An answer shows
 *  its sources in full: a picture, a clip, or a document renders inline, and
 *  any two sources the run cross-examined are flagged as related. */
export function AskDock({
  pid, disabled, conflicts, boxName, onOpenEvidence,
}: {
  pid: string;
  disabled?: boolean;
  conflicts?: Record<string, Verdict>;
  boxName?: Record<string, string>;
  onOpenEvidence: (e: Evidence) => void;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [img, setImg] = useState<{ b64: string; mime: string; name: string } | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight });
  }, [turns, open]);

  const attach = (file: File) => {
    const rd = new FileReader();
    rd.onload = () => {
      const im = new Image();
      im.onload = () => {
        const scale = Math.min(1, 1024 / Math.max(im.width, im.height));
        const c = document.createElement("canvas");
        c.width = Math.round(im.width * scale); c.height = Math.round(im.height * scale);
        c.getContext("2d")!.drawImage(im, 0, 0, c.width, c.height);
        const url = c.toDataURL("image/jpeg", 0.82);
        setImg({ b64: url.split(",")[1], mime: "image/jpeg", name: file.name });
      };
      im.src = String(rd.result);
    };
    rd.readAsDataURL(file);
  };

  const send = async () => {
    const question = q.trim();
    if (!question || busy) return;
    const shot = img;
    setQ(""); setImg(null);
    setBusy(true);
    setTurns((t) => [...t, { q: shot ? `${question}  ·  📎 ${shot.name}` : question }]);
    try {
      const res = await ask(pid, question, shot ? { b64: shot.b64, mime: shot.mime } : null);
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, res } : x)));
    } catch (e) {
      const msg = String((e as Error)?.message || e);
      const error = /no research yet|409/i.test(msg)
        ? "Nothing is indexed yet. Run the research first."
        : "The index could not answer. Try again in a moment.";
      setTurns((t) => t.map((x, i) => (i === t.length - 1 ? { ...x, error } : x)));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button className="askdock-fab" aria-label={open ? "Close ask" : "Ask the boxes"}
              aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {open ? "✕" : "Ask ▸"}
      </button>

      {open && (
        <section className="askdock" aria-label="Ask the boxes">
          <header className="askdock-head">
            <span>Ask the boxes</span>
            <button className="ghost" onClick={() => setOpen(false)} aria-label="Close">✕</button>
          </header>

          <div className="askdock-body" ref={bodyRef}>
            {!turns.length && (
              <p className="muted askdock-hint">
                {disabled
                  ? "Run the research first, then ask what the crew can act on."
                  : "Grounded in this dossier's evidence. It cites or it abstains."}
              </p>
            )}
            {turns.map((t, i) => (
              <div className="askturn" key={i}>
                <p className="askturn-q">{t.q}</p>
                {t.error && <p className="form-error" role="alert">{t.error}</p>}
                {t.res && (
                  <div className="grounded-answer">
                    <span className={t.res.sufficient ? "source-badge primary" : "source-badge web"}>
                      {t.res.sufficient ? "grounded answer" : "insufficient evidence"}
                    </span>
                    <Markdown>{t.res.answer}</Markdown>
                    {t.res.query_parts?.includes("image") && (
                      <p className="askturn-meta">
                        query: text + image · prefix <code>{t.res.query_prefix}</code>
                      </p>
                    )}
                    <AnswerSources sources={t.res.sources} conflicts={conflicts}
                                   boxName={boxName} onOpen={onOpenEvidence} />
                  </div>
                )}
                {!t.res && !t.error && <p className="muted">Consulting the index…</p>}
              </div>
            ))}
          </div>

          {img && (
            <div className="askdock-attach">
              📎 {img.name}
              <button className="ghost" onClick={() => setImg(null)} aria-label="Remove image">✕</button>
            </div>
          )}
          <div className="askdock-compose">
            <button type="button" className="askdock-clip" aria-label="Attach a reference image"
                    onClick={() => fileRef.current?.click()} disabled={busy}>📎</button>
            <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" hidden
                   onChange={(e) => e.target.files?.[0] && attach(e.target.files[0])} />
            <input value={q} onChange={(e) => setQ(e.target.value)} disabled={busy}
                   placeholder={img ? "Describe what you want matched" : "What would our characters actually see and hear?"}
                   onKeyDown={(e) => e.key === "Enter" && send()} />
            <button onClick={send} disabled={busy || !q.trim()}>{busy ? "…" : "Ask"}</button>
          </div>
        </section>
      )}
    </>
  );
}

function AnswerSources({
  sources, conflicts, boxName, onOpen,
}: {
  sources: Evidence[];
  conflicts?: Record<string, Verdict>;
  boxName?: Record<string, string>;
  onOpen: (e: Evidence) => void;
}) {
  if (!sources?.length) return null;
  // Any cross-examination that touches two of the cited sources: the answer is
  // standing on contested ground, so say so.
  const links: { v: Verdict; a: number; b: number }[] = [];
  sources.forEach((s, a) => {
    const v = s.id ? conflicts?.[s.id] : undefined;
    if (!v) return;
    const b = sources.findIndex((o, j) => j !== a && (o.id === v.a_id || o.id === v.b_id));
    if (b > a) links.push({ v, a, b });
  });

  return (
    <div className="answer-sources">
      {sources.map((s, i) => (
        <div className="answer-source" key={s.id || i}>
          <button className="answer-source-head" onClick={() => onOpen(s)}>
            <span className="asrc-n">[{i + 1}]</span>
            <span className="asrc-cite">{s.title || s.source_domain || "source"}</span>
            {s.objective_id && boxName?.[s.objective_id] && (
              <span className="asrc-box">{boxName[s.objective_id]}</span>
            )}
          </button>
          {s.modality && s.modality !== "text" && (
            <div className="answer-source-media"><MediaBit e={s as any} size="full" /></div>
          )}
        </div>
      ))}
      {links.map(({ v, a, b }, k) => (
        <p className={`answer-rel ${v.relation}`} key={k}>
          [{a + 1}] {v.relation === "contradicts" ? "conflicts with" : "is contextualised by"} [{b + 1}]
          {v.explanation ? ` · ${v.explanation}` : ""}
        </p>
      ))}
    </div>
  );
}
