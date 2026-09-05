import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { MODALITY_GLYPH } from "./Media";

interface Box {
  id: string;
  name: string;
  score?: number;
  evidence_count?: number;
  emergent?: boolean;
}
interface Ev {
  id: string;
  objective_id?: string;
  source?: string;
  modality?: string;
  image_url?: string;
  media_url?: string;
  url?: string;
  title?: string;
  map_x?: number;
  map_y?: number;
}

// A filmic set: distinguishable per box, but harmonised and slightly
// desaturated so the canvas reads as a single composed image.
const PALETTE = [
  "#e4572e", "#f6ae2d", "#d4b483", "#e0c1b3", "#c98986",
  "#8f6c4f", "#5b8a72", "#4c9f9f", "#5c7aa8", "#7b6d8d",
  "#9a6fb0", "#c25b7c", "#a7c957", "#6a994e", "#adb5bd",
];

const W = 720;
const H = 460;
const MIN_W = W * 0.2; // 5x zoom ceiling

type View = { x: number; y: number; w: number; h: number };
const FULL: View = { x: 0, y: 0, w: W, h: H };

function clampView(v: View): View {
  const w = Math.min(W, Math.max(MIN_W, v.w));
  const h = w * (H / W);
  const x = Math.min(Math.max(0, v.x), W - w);
  const y = Math.min(Math.max(0, v.y), H - h);
  return { x, y, w, h };
}

type Center = { x: number; y: number; color: string; lx: number; ly: number; anchor: "start" | "middle" | "end" };
type Dot = {
  e: Ev; x: number; y: number; color: string;
  isImg: boolean; thumb: string; glyph: string; director: boolean;
};

/** A dark canvas of research. Each box is a cluster; each evidence fragment a
 *  dot. Images show as thumbnails. Click a box to focus it, a dot to open it,
 *  drag to pan, wheel or the controls to zoom, ⤢ to expand to full screen. */
export function ResearchMap({
  boxes, evidence, selected, onSelect, onOpenEvidence, conflictIds,
}: {
  boxes: Box[];
  evidence: Ev[];
  selected: string | null;
  onSelect: (id: string | null) => void;
  onOpenEvidence: (e: Ev) => void;
  conflictIds?: Set<string>;
}) {
  const [expanded, setExpanded] = useState(false);

  const { centers, dots } = useMemo(() => {
    const n = Math.max(boxes.length, 1);
    const cx = W / 2, cy = H / 2;
    const R = Math.min(W, H) * 0.32;
    // Boxes sit on an even ring, so every label is readable and the spokes fan
    // out cleanly. Labels are pushed further along the same radial and pinned
    // to the near edge, so 11 of them do not stack.
    const centers: Record<string, Center> = {};
    boxes.forEach((b, i) => {
      const a = (i / n) * Math.PI * 2 - Math.PI / 2;
      const bx = cx + R * Math.cos(a);
      const by = cy + R * Math.sin(a);
      const cos = Math.cos(a);
      centers[b.id] = {
        x: bx, y: by, color: PALETTE[i % PALETTE.length],
        lx: Math.min(W - 6, Math.max(6, cx + (R + 34) * cos)),
        ly: cy + (R + 34) * Math.sin(a) + 3,
        anchor: cos < -0.25 ? "end" : cos > 0.25 ? "start" : "middle",
      };
    });

    // map_x / map_y place a dot relative to its own box, not on a global axis a
    // few outliers can dominate. Offsets are scaled and clamped inside the
    // cluster; fragments with no projection fall back to a stable hash scatter.
    const bc: Record<string, { x: number; y: number; n: number }> = {};
    evidence.forEach((e) => {
      if (e.map_x == null || e.map_y == null) return;
      const k = e.objective_id ?? "";
      const acc = (bc[k] ??= { x: 0, y: 0, n: 0 });
      acc.x += e.map_x; acc.y += e.map_y; acc.n += 1;
    });
    const SPREAD = 540;
    const MAXR = 44;
    const fallback = { x: cx, y: cy, color: "#666", lx: cx, ly: cy, anchor: "middle" as const };
    const dots: Dot[] = evidence.map((e) => {
      const c = centers[e.objective_id ?? ""] ?? fallback;
      const b = bc[e.objective_id ?? ""];
      let x: number, y: number;
      if (e.map_x != null && e.map_y != null && b && b.n > 1) {
        let ox = (e.map_x - b.x / b.n) * SPREAD;
        let oy = (e.map_y - b.y / b.n) * SPREAD;
        const d = Math.hypot(ox, oy) || 1;
        if (d > MAXR) { ox = (ox / d) * MAXR; oy = (oy / d) * MAXR; }
        x = c.x + ox; y = c.y + oy;
      } else {
        const seed = [...e.id].reduce((acc, ch) => ((acc * 31) + ch.charCodeAt(0)) >>> 0, 2166136261) % 997;
        const rad = 12 + (seed % 28);
        const ang = (seed * 0.618) % (Math.PI * 2);
        x = c.x + rad * Math.cos(ang); y = c.y + rad * Math.sin(ang);
      }
      const thumb = e.image_url || (e.modality === "image" ? e.media_url : "") || "";
      return {
        e, x, y,
        color: e.source === "director" ? "#ffffff" : c.color,
        isImg: e.modality === "image" && !!thumb,
        thumb,
        glyph: e.modality && e.modality !== "text" && e.modality !== "image"
          ? MODALITY_GLYPH[e.modality] : "",
        director: e.source === "director",
      };
    });
    return { centers, dots };
  }, [boxes, evidence]);

  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setExpanded(false); };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [expanded]);

  const shared = { boxes, centers, dots, selected, onSelect, onOpenEvidence, conflictIds };

  return (
    <>
      <MapCanvas {...shared} onExpand={() => setExpanded(true)} />
      {expanded && createPortal(
        <div className="map-fullscreen">
          <button type="button" className="ghost map-fs-close" onClick={() => setExpanded(false)}>
            Close ✕
          </button>
          <MapCanvas {...shared} fullscreen />
        </div>,
        document.body,
      )}
    </>
  );
}

function MapCanvas({
  boxes, centers, dots, selected, onSelect, onOpenEvidence, onExpand, fullscreen, conflictIds,
}: {
  boxes: Box[];
  centers: Record<string, Center>;
  dots: Dot[];
  selected: string | null;
  onSelect: (id: string | null) => void;
  onOpenEvidence: (e: Ev) => void;
  onExpand?: () => void;
  fullscreen?: boolean;
  conflictIds?: Set<string>;
}) {
  const [view, setView] = useState<View>(FULL);
  const [hover, setHover] = useState<{ x: number; y: number; label: string } | null>(null);
  const [panning, setPanning] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ px: number; py: number; vx: number; vy: number; w: number; h: number; moved: boolean } | null>(null);
  const suppressClick = useRef(false);

  const zoomAt = useCallback((factor: number, fx = 0.5, fy = 0.5) => {
    setView((v) => {
      const w = Math.min(W, Math.max(MIN_W, v.w * factor));
      const cx = v.x + fx * v.w;
      const cy = v.y + fy * v.h;
      return clampView({ x: cx - fx * w, y: cy - fy * (w * (H / W)), w, h: w * (H / W) });
    });
  }, []);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      zoomAt(
        e.deltaY > 0 ? 1.15 : 1 / 1.15,
        (e.clientX - rect.left) / rect.width,
        (e.clientY - rect.top) / rect.height,
      );
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomAt]);

  const onPointerDown = (e: React.PointerEvent) => {
    (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
    drag.current = { px: e.clientX, py: e.clientY, vx: view.x, vy: view.y, w: view.w, h: view.h, moved: false };
    suppressClick.current = false;
    setPanning(true);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d || !wrapRef.current) return;
    const rect = wrapRef.current.getBoundingClientRect();
    if (Math.abs(e.clientX - d.px) + Math.abs(e.clientY - d.py) > 3) d.moved = true;
    const dx = ((e.clientX - d.px) / rect.width) * d.w;
    const dy = ((e.clientY - d.py) / rect.height) * d.h;
    setView(clampView({ x: d.vx - dx, y: d.vy - dy, w: d.w, h: d.h }));
    setHover(null);
  };
  const endPan = () => {
    const d = drag.current;
    drag.current = null;
    setPanning(false);
    if (!d) return;
    suppressClick.current = d.moved;
    if (!d.moved) onSelect(null);
  };

  const tip = hover && !panning
    ? { left: `${((hover.x - view.x) / view.w) * 100}%`, top: `${((hover.y - view.y) / view.h) * 100}%` }
    : null;

  return (
    <div className={`map-wrap${fullscreen ? " map-wrap-fs" : ""}`} ref={wrapRef}>
      <div className="map-controls">
        <button type="button" className="map-btn" title="Zoom in" aria-label="Zoom in"
                onClick={() => zoomAt(1 / 1.3)}>+</button>
        <button type="button" className="map-btn" title="Zoom out" aria-label="Zoom out"
                onClick={() => zoomAt(1.3)}>−</button>
        <button type="button" className="map-btn" title="Reset view" aria-label="Reset view"
                onClick={() => setView(FULL)}>⊙</button>
        {onExpand && (
          <button type="button" className="map-btn" title="Expand" aria-label="Expand map"
                  onClick={onExpand}>⤢</button>
        )}
      </div>

      <svg className={`map${panning ? " grabbing" : ""}`}
           viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`} width="100%"
           preserveAspectRatio="xMidYMid meet"
           onPointerDown={onPointerDown} onPointerMove={onPointerMove}
           onPointerUp={endPan} onPointerLeave={endPan}>
        <defs>
          <radialGradient id="map-depth" cx="50%" cy="50%" r="72%">
            <stop offset="55%" stopColor="var(--map-bg)" />
            <stop offset="100%" stopColor="var(--map-edge)" />
          </radialGradient>
          {dots.filter((d) => d.isImg).map((d) => (
            <clipPath id={`c-${d.e.id}`} key={d.e.id}><circle cx={d.x} cy={d.y} r={9} /></clipPath>
          ))}
        </defs>
        <rect x={0} y={0} width={W} height={H} fill="url(#map-depth)" rx={10} />

        {/* one plan, radiating into objectives — echoes the landing floor */}
        {boxes.map((b) => {
          const c = centers[b.id];
          return c ? (
            <line key={`spoke-${b.id}`} x1={W / 2} y1={H / 2} x2={c.x} y2={c.y}
                  stroke="var(--map-grid)" strokeWidth={1} />
          ) : null;
        })}
        <circle cx={W / 2} cy={H / 2} r={2.5} fill="var(--map-ink)" opacity={0.45} />

        {boxes.map((b) => {
          const c = centers[b.id];
          if (!c) return null;
          const dim = selected && selected !== b.id;
          return (
            <g key={b.id} opacity={dim ? 0.25 : 1} style={{ cursor: "pointer" }}
               role="button" tabIndex={0} aria-label={`${b.name} research box`}
               onKeyDown={(ev) => {
                 if (ev.key === "Enter" || ev.key === " ") onSelect(selected === b.id ? null : b.id);
               }}
               onClick={(ev) => {
                 ev.stopPropagation();
                 if (!suppressClick.current) onSelect(selected === b.id ? null : b.id);
               }}>
              {b.emergent && (
                <circle cx={c.x} cy={c.y} r={52} fill="none" stroke="var(--map-accent)" strokeWidth={1.5}>
                  <animate attributeName="r" values="30;58;30" dur="2.4s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.9;0.12;0.9" dur="2.4s" repeatCount="indefinite" />
                </circle>
              )}
              <circle cx={c.x} cy={c.y} r={Math.max(7, (b.score ?? 0) * 18)}
                      fill={c.color} opacity={selected === b.id ? 0.4 : 0.2}
                      stroke={selected === b.id ? c.color : "none"} strokeWidth={1.5} />
              <line x1={c.x} y1={c.y} x2={c.lx} y2={c.ly - 3} stroke="var(--map-grid)" strokeWidth={0.75} />
              <text x={c.lx} y={c.ly} fill="var(--map-ink)" fontSize={9.5} textAnchor={c.anchor}
                    fontWeight={selected === b.id ? 700 : 400} paintOrder="stroke"
                    stroke="var(--map-bg)" strokeWidth={2.5} strokeLinejoin="round">
                {b.name}{b.emergent ? " ✦" : ""}
              </text>
            </g>
          );
        })}

        {dots.map((d, i) => {
          const dim = selected && selected !== d.e.objective_id;
          const conflicted = conflictIds?.has(d.e.id);
          const label = `${d.e.title || d.e.modality || "evidence"}${conflicted ? " · cross-examined" : ""}${d.director ? " · your upload" : ""}`;
          const ring = conflicted ? (
            <circle cx={d.x} cy={d.y} r={d.isImg ? 12 : 6} fill="none"
                    stroke="var(--device-red)" strokeWidth={1.4} opacity={0.92} pointerEvents="none">
              <animate attributeName="opacity" values="0.92;0.3;0.92" dur="2.2s" repeatCount="indefinite" />
            </circle>
          ) : null;
          const common = {
            opacity: dim ? 0.15 : 1,
            style: { cursor: "pointer" },
            role: "button",
            tabIndex: 0,
            "aria-label": label,
            onMouseEnter: () => setHover({ x: d.x, y: d.y, label }),
            onMouseLeave: () => setHover(null),
            onClick: (ev: React.MouseEvent) => {
              ev.stopPropagation();
              if (!suppressClick.current) onOpenEvidence(d.e);
            },
            onKeyDown: (ev: React.KeyboardEvent) => {
              if (ev.key === "Enter" || ev.key === " ") onOpenEvidence(d.e);
            },
          };
          if (d.isImg) {
            return (
              <g key={i} {...common}>
                {ring}
                <image href={d.thumb} x={d.x - 9} y={d.y - 9} width={18} height={18}
                       clipPath={`url(#c-${d.e.id})`} preserveAspectRatio="xMidYMid slice" />
                <circle cx={d.x} cy={d.y} r={9} fill="none" stroke={d.color} strokeWidth={1} />
              </g>
            );
          }
          if (d.glyph) {
            return (
              <g key={i} {...common}>
                {ring}
                <text x={d.x} y={d.y + 3} textAnchor="middle" fontSize={11} fill={d.color}>{d.glyph}</text>
              </g>
            );
          }
          return (
            <g key={i} {...common}>
              {ring}
              <circle cx={d.x} cy={d.y} r={d.director ? 3.8 : 2.7}
                      fill={d.color} stroke={d.director ? "var(--map-accent)" : "none"} strokeWidth={d.director ? 1 : 0} />
            </g>
          );
        })}
      </svg>

      {tip && <div className="maptip" style={tip}>{hover!.label}</div>}
    </div>
  );
}
