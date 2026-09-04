import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type ThemePref = "light" | "dark" | "system";
type Effective = "light" | "dark";

const KEY = "boxes-theme";
const mql = () => window.matchMedia("(prefers-color-scheme: dark)");

function readPref(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch { /* private mode, blocked storage */ }
  return "system";
}

function resolve(pref: ThemePref): Effective {
  if (pref === "system") return mql().matches ? "dark" : "light";
  return pref;
}

function paint(pref: ThemePref) {
  document.documentElement.dataset.theme = resolve(pref);
}

interface ThemeCtx {
  pref: ThemePref;
  theme: Effective;
  setPref: (p: ThemePref) => void;
}

const Ctx = createContext<ThemeCtx>({ pref: "system", theme: "dark", setPref: () => {} });

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [pref, setPref] = useState<ThemePref>(readPref);
  const [theme, setTheme] = useState<Effective>(() => resolve(readPref()));

  useEffect(() => {
    paint(pref);
    setTheme(resolve(pref));
    try { localStorage.setItem(KEY, pref); } catch { /* ignore */ }
    if (pref !== "system") return;
    const m = mql();
    const onChange = () => { paint("system"); setTheme(resolve("system")); };
    m.addEventListener("change", onChange);
    return () => m.removeEventListener("change", onChange);
  }, [pref]);

  return <Ctx.Provider value={{ pref, theme, setPref }}>{children}</Ctx.Provider>;
}

export const useTheme = () => useContext(Ctx);
