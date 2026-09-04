import { useTheme, type ThemePref } from "../theme";

const OPTS: { key: ThemePref; glyph: string; label: string }[] = [
  { key: "light", glyph: "☀", label: "Light" },
  { key: "system", glyph: "◐", label: "System" },
  { key: "dark", glyph: "☾", label: "Dark" },
];

export function ThemeToggle({ bare = false }: { bare?: boolean }) {
  const { pref, setPref } = useTheme();
  return (
    <div className={`theme-toggle${bare ? " bare" : ""}`} role="group" aria-label="Theme">
      {OPTS.map((o) => (
        <button
          key={o.key}
          type="button"
          className={pref === o.key ? "on" : ""}
          aria-pressed={pref === o.key}
          title={`${o.label} theme`}
          onClick={() => setPref(o.key)}
        >
          <span aria-hidden="true">{o.glyph}</span>
        </button>
      ))}
    </div>
  );
}
