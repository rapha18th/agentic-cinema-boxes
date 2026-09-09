import { useEffect, useState } from "react";
import { getWatch, setWatch } from "../api";

/** Keep watching a finished topic. Parallel Monitor re-runs the research
 *  question on a schedule and surfaces what changed. A frozen archive becomes
 *  a living one. Degrades to a disabled control if Monitor is not on this key. */
export function WatchToggle({ pid, disabled }: { pid: string; disabled?: boolean }) {
  const [state, setState] = useState<{ enabled: boolean; updates: any[]; unavailable?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    getWatch(pid).then((s) => live && setState({ enabled: s.enabled, updates: s.updates || [] }))
      .catch(() => live && setState({ enabled: false, updates: [] }));
    return () => { live = false; };
  }, [pid]);

  const toggle = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const next = !state?.enabled;
      const res = await setWatch(pid, next);
      if (next && !res.monitor_id) { setState((s) => ({ ...(s || { updates: [] }), enabled: false, unavailable: true })); }
      else {
        const s = await getWatch(pid);
        setState({ enabled: s.enabled, updates: s.updates || [] });
      }
    } catch { setState((s) => ({ ...(s || { updates: [] }), enabled: false, unavailable: true })); }
    finally { setBusy(false); }
  };

  if (!state) return null;
  if (state.unavailable) {
    return <span className="watch-toggle muted" title="Parallel Monitor is not enabled on this key">Monitor API access pending</span>;
  }
  return (
    <button type="button" className={`ghost watch-toggle${state.enabled ? " on" : ""}`}
            onClick={toggle} disabled={busy || disabled}>
      {state.enabled
        ? `Watching · ${state.updates.length} update${state.updates.length === 1 ? "" : "s"}`
        : "Watch this topic"}
    </button>
  );
}
