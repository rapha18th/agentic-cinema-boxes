import { useMemo } from "react";

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
}

const PALETTE = [
  "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4",
  "#46f0f0", "#f032e6", "#bcf60c", "#fabebe", "#008080",
  "#9a6324", "#800000", "#808000", "#000075", "#a9a9a9",
];

/** A dark canvas of research. Each box is a cluster; each evidence fragment a
 *  dot in it. Emergent boxes pulse. */
export function ResearchMap({ boxes, evidence }: { boxes: Box[]; evidence: Ev[] }) {
  const W = 720;
  const H = 460;

  const layout = useMemo(() => {
    const n = Math.max(boxes.length, 1);
    const cx = W / 2;
    const cy = H / 2;
    const R = Math.min(W, H) * 0.34;
    const centers: Record<string, { x: number; y: number; color: string }> = {};
    boxes.forEach((b, i) => {
      const a = (i / n) * Math.PI * 2 - Math.PI / 2;
      centers[b.id] = { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a), color: PALETTE[i % PALETTE.length] };
    });
    const dots = evidence.map((e, i) => {
      const c = centers[e.objective_id ?? ""] ?? { x: cx, y: cy, color: "#666" };
      const seed = (i * 2654435761) % 997;
      const rad = 14 + (seed % 40);
      const ang = (seed * 0.618) % (Math.PI * 2);
      return {
        x: c.x + rad * Math.cos(ang),
        y: c.y + rad * Math.sin(ang),
        color: e.source === "director" ? "#ffffff" : c.color,
        director: e.source === "director",
      };
    });
    return { centers, dots };
  }, [boxes, evidence]);

  return (
    <svg className="map" viewBox={`0 0 ${W} ${H}`} width="100%">
      <rect x={0} y={0} width={W} height={H} fill="#0b0d17" rx={10} />
      {boxes.map((b) => {
        const c = layout.centers[b.id];
        if (!c) return null;
        return (
          <g key={b.id}>
            {b.emergent && (
              <circle cx={c.x} cy={c.y} r={52} fill="none" stroke="#ffd166" strokeWidth={1.5} opacity={0.9}>
                <animate attributeName="r" values="30;58;30" dur="2.4s" repeatCount="indefinite" />
                <animate attributeName="opacity" values="0.9;0.15;0.9" dur="2.4s" repeatCount="indefinite" />
              </circle>
            )}
            <circle cx={c.x} cy={c.y} r={Math.max(6, (b.score ?? 0) * 16)} fill={c.color} opacity={0.22} />
            <text x={c.x} y={c.y - 60} fill="#c7ccd8" fontSize={10} textAnchor="middle">
              {b.name}
            </text>
          </g>
        );
      })}
      {layout.dots.map((d, i) => (
        <circle key={i} cx={d.x} cy={d.y} r={d.director ? 3.6 : 2.6}
                fill={d.color} stroke={d.director ? "#ffd166" : "none"} strokeWidth={d.director ? 1 : 0} />
      ))}
    </svg>
  );
}
