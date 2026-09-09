import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { DEPT_LABEL } from "../departments";
import { MODALITY_GLYPH } from "./Media";
import type { Evidence, ResearchBox } from "../types";

const FOCUSABLE = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** What one research box is and why the agent opened it, with the evidence
 *  filed under it. Opened from the trace timeline. */
export function BoxModal({
  box, evidence, onClose, onOpenEvidence,
}: {
  box: ResearchBox | null;
  evidence: Evidence[];
  onClose: () => void;
  onOpenEvidence: (e: Evidence) => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!box) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { onClose(); return; }
      if (e.key !== "Tab" || !panelRef.current) return;
      const items = panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE);
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panelRef.current?.focus();
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
  }, [box, onClose]);

  if (!box) return null;
  const mine = evidence.filter((e) => e.objective_id === box.id);

  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-panel" role="dialog" aria-modal="true" aria-label={box.name}
           ref={panelRef} tabIndex={-1} onClick={(e) => e.stopPropagation()}>
        <button type="button" className="ghost modal-close" onClick={onClose} aria-label="Close">✕</button>
        <div className="modal-head">
          <div className="modal-title">{box.name}{box.emergent ? " ✦" : ""}</div>
          {box.emergent && <span className="modal-badge">agent opened this</span>}
        </div>

        {box.departments?.length ? (
          <div className="dept-bar">
            {box.departments.map((d) => (
              <span key={d} className="chip">{DEPT_LABEL[d] || d}</span>
            ))}
          </div>
        ) : null}

        {box.description && <p className="modal-text">{box.description}</p>}
        {box.rationale && (
          <div className="modal-meta">
            <div><span className="modal-meta-k">why</span>{box.rationale}</div>
          </div>
        )}
        {box.summary && <p className="modal-text">{box.summary}</p>}

        <div className="modal-meta">
          <div><span className="modal-meta-k">evidence</span>{mine.length} fragments</div>
          <div><span className="modal-meta-k">domains</span>{box.distinct_domains ?? 0}</div>
        </div>

        {mine.length > 0 && (
          <div className="round-ev-list box-modal-ev">
            {mine.slice(0, 40).map((e) => (
              <div role="button" tabIndex={0} className="ev-row-compact" key={e.id}
                   onClick={() => onOpenEvidence(e)}
                   onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") onOpenEvidence(e); }}>
                <span className="ev-row-modality">{MODALITY_GLYPH[e.modality || "text"] || "·"}</span>
                <span className="ev-row-cite">{e.title || e.source_domain || e.url}</span>
                <span className="ev-row-snip">{String(e.text || "").slice(0, 150)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
