import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { MediaBit } from "./Media";

/** Clicks landing on nested interactive controls (a citation link, an audio
 *  scrubber, a button) should operate normally, not also open the modal. */
export function isInteractiveClick(ev: { target: EventTarget | null }): boolean {
  return !!(ev.target as HTMLElement).closest?.("a, audio, video, button, input, select");
}

function citationLabel(e: any): string {
  return e.citation || e.cite
    || [e.title || e.source_domain, e.publish_date].filter(Boolean).join(" · ")
    || e.url || "Evidence";
}

const FOCUSABLE = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function EvidenceModal({
  evidence, boxName, onClose,
}: {
  evidence: any | null;
  boxName?: Record<string, string>;
  onClose: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!evidence) return;
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
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panelRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [evidence, onClose]);

  if (!evidence) return null;

  const title = citationLabel(evidence);
  const boxLabel = evidence.objective_id ? boxName?.[evidence.objective_id] : undefined;

  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-panel" role="dialog" aria-modal="true" aria-label={title}
           ref={panelRef} tabIndex={-1} onClick={(e) => e.stopPropagation()}>
        <button type="button" className="ghost modal-close" onClick={onClose} aria-label="Close">✕</button>
        <div className="modal-head">
          <div className="modal-title">{title}</div>
          {evidence.source === "director" && <span className="modal-badge">your upload</span>}
        </div>

        {evidence.modality && evidence.modality !== "text" && (
          <div className="modal-media"><MediaBit e={evidence} size="full" /></div>
        )}
        {evidence.text && <p className="modal-text">{evidence.text}</p>}

        <div className="modal-meta">
          {evidence.source_domain && <div><span className="modal-meta-k">source</span>{evidence.source_domain}</div>}
          {evidence.publish_date && <div><span className="modal-meta-k">published</span>{evidence.publish_date}</div>}
          {boxLabel && <div><span className="modal-meta-k">box</span>{boxLabel}</div>}
          {evidence.round != null && (
            <div><span className="modal-meta-k">round</span>{String(evidence.round).padStart(3, "0")}</div>
          )}
          {evidence.license_note && <div><span className="modal-meta-k">license</span>{evidence.license_note}</div>}
        </div>

        {evidence.url && (
          <div className="modal-foot">
            <a className="ghost" href={evidence.url} target="_blank" rel="noopener">Open original source ↗</a>
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
