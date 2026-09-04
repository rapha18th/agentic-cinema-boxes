import { useMemo, useState } from "react";
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
}

// A filmic set: distinguishable per box, but harmonised and slightly
// desaturated so the canvas reads as one image rather than a legend.
const PALETTE = [
  "#e4572e", "#f6ae2d", "#d4b483", "#e0c1b3", "#c98986",
  "#8f6c4f", "#5b8a72", "#4c9f9f", "#5c7aa8", "#7b6d8d",
  "#9a6fb0", "#c25b7c", "#a7c957", "#6a994e", "#adb5bd",
];

/** A dark canvas of research. Each box is a cluster; each evidence fragment a
 *  dot. Images show as thumbnails. Click a box to focus it, a dot to open its
 *  source, hover for the citation. */
export function ResearchMap({
  boxes, evidence, selected, onSelect,
}: {
  boxes: Box[];
  evidence: Ev[];
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  const W = 720;
  const H = 460;
  const [hover, setHover] = useState<{ x: number; y: number; label: string } | null>(null);

  const { centers, dots } = useMemo(() => {
    const n = Math.max(boxes.length, 1);
    const cx = W / 2, cy = H / 2;
    const R = Math.min(W, H) * 0.34;
    const centers: Record<string, { x: number; y: number; color: string }> = {};
    boxes.forEach((b, i) => {
      const a = (i / n) * Math.PI * 2 - Math.PI / 2;
      centers[b.id] = { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a), color: PALETTE[i % PALETTE.length] };
    });
    const dots = evidence.map((e, i) => {
      const c = centers[e.objective_id ?? ""] ?? { x: cx, y: cy, color: "#666" };
      const seed = (i * 2654435761) % 997;
      const rad = 14 + (seed % 42);
      const ang = (seed * 0.618) % (Math.PI * 2);
      const thumb = e.image_url || (e.modality === "image" ? e.media_url : "");
      return {
        e,
        x: c.x + rad * Math.cos(ang),
        y: c.y + rad * Math.sin(ang),
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

  return (
    <div style={{ position: "relative" }}>
      <svg className="map" viewBox={`0 0 ${W} ${H}`} width="100%"
           onClick={() => onSelect(null)}>
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
               onClick={(ev) => { ev.stopPropagation(); onSelect(selected === b.id ? null : b.id); }}>
              {b.emergent && (
                <circle cx={c.x} cy={c.y} r={52} fill="none" stroke="var(--map-accent)" strokeWidth={1.5}>
                  <animate attributeName="r" values="30;58;30" dur="2.4s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.9;0.12;0.9" dur="2.4s" repeatCount="indefinite" />
                </circle>
              )}
              <circle cx={c.x} cy={c.y} r={Math.max(7, (b.score ?? 0) * 18)}
                      fill={c.color} opacity={selected === b.id ? 0.4 : 0.2}
                      stroke={selected === b.id ? c.color : "none"} strokeWidth={1.5} />
              <text x={c.x} y={c.y - 62} fill="var(--map-ink)" fontSize={10} textAnchor="middle"
                    fontWeight={selected === b.id ? 700 : 400}>
                {b.name}{b.emergent ? " ✦" : ""}
              </text>
            </g>
          );
        })}

        {dots.map((d, i) => {
          const dim = selected && selected !== d.e.objective_id;
          const label = `${d.e.title || d.e.modality || "evidence"}${d.director ? " · your upload" : ""}`;
          const common = {
            opacity: dim ? 0.15 : 1,
            style: { cursor: d.e.url ? "pointer" : "default" },
            onMouseEnter: () => setHover({ x: d.x, y: d.y, label }),
            onMouseLeave: () => setHover(null),
            onClick: (ev: React.MouseEvent) => {
              ev.stopPropagation();
              if (d.e.url) window.open(d.e.url, "_blank", "noopener");
            },
          };
          if (d.isImg) {
            return (
              <g key={i} {...common}>
                <image href={d.thumb} x={d.x - 9} y={d.y - 9} width={18} height={18}
                       clipPath={`url(#c-${d.e.id})`} preserveAspectRatio="xMidYMid slice" />
                <circle cx={d.x} cy={d.y} r={9} fill="none" stroke={d.color} strokeWidth={1} />
              </g>
            );
          }
          if (d.glyph) {
            return (
              <text key={i} x={d.x} y={d.y + 3} textAnchor="middle" fontSize={11}
                    fill={d.color} {...common}>{d.glyph}</text>
            );
          }
          return (
            <circle key={i} cx={d.x} cy={d.y} r={d.director ? 3.8 : 2.7}
                    fill={d.color} stroke={d.director ? "var(--map-accent)" : "none"} strokeWidth={d.director ? 1 : 0}
                    {...common} />
          );
        })}
      </svg>
      {hover && (
        <div className="maptip" style={{ left: `${(hover.x / W) * 100}%`, top: `${(hover.y / H) * 100}%` }}>
          {hover.label}
        </div>
      )}
    </div>
  );
}
