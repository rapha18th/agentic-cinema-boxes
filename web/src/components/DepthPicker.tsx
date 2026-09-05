import type { DepthName } from "../types";

const DEPTHS: { id: DepthName; time: string; cost: string; output: string }[] = [
  { id: "scout", time: "2–4 minutes", cost: "Relative API cost · 1×", output: "5 boxes · fast reconnaissance · concise dossier" },
  { id: "production", time: "6–12 minutes", cost: "Relative API cost · 3×", output: "10 boxes · deeper extraction · department-ready briefs" },
  { id: "kubrick", time: "15–30 minutes", cost: "Relative API cost · 8×", output: "16 boxes · up to 6 follow-ups · obsessive evidence sweep" },
];

export function DepthPicker({ value, onChange, disabled = false }: {
  value: DepthName;
  onChange: (value: DepthName) => void;
  disabled?: boolean;
}) {
  return (
    <fieldset className="depth-picker" aria-label="Research depth">
      <legend className="sr-only">Research depth</legend>
      {DEPTHS.map((d) => {
        const tipId = `depth-${d.id}-tip`;
        return (
          <span className="depth-choice" key={d.id}>
            <button type="button" className={`depth-btn ${value === d.id ? "on" : ""}`}
                    aria-pressed={value === d.id} aria-describedby={tipId}
                    disabled={disabled} onClick={() => onChange(d.id)}>
              {d.id}
            </button>
            <span className="depth-tip" id={tipId} role="tooltip">
              <b>{d.time}</b>
              <span>{d.cost}</span>
              <span>{d.output}</span>
            </span>
          </span>
        );
      })}
    </fieldset>
  );
}
