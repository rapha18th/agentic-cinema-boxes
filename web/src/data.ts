import { useEffect, useState } from "react";
import {
  collection, doc, onSnapshot, query, orderBy,
} from "firebase/firestore";
import { db } from "./firebase";
import { useAuth } from "./auth";

function base(uid: string, pid: string) {
  return doc(db, "users", uid, "projects", pid);
}

export function useProject(pid: string) {
  const { user } = useAuth();
  const [p, setP] = useState<any>(null);
  useEffect(() => {
    if (!user) return;
    return onSnapshot(base(user.uid, pid), (s) => setP(s.exists() ? { id: s.id, ...s.data() } : null));
  }, [user, pid]);
  return p;
}

function useSub<T = any>(pid: string, name: string, ordering?: string): T[] {
  const { user } = useAuth();
  const [rows, setRows] = useState<T[]>([]);
  useEffect(() => {
    if (!user) return;
    const col = collection(base(user.uid, pid), name);
    const q = ordering ? query(col, orderBy(ordering)) : col;
    return onSnapshot(q, (snap) => setRows(snap.docs.map((d) => ({ id: d.id, ...d.data() } as T))));
  }, [user, pid, name, ordering]);
  return rows;
}

export const useBoxes = (pid: string) => useSub(pid, "boxes");
export const useRuns = (pid: string) => useSub(pid, "runs", "run");
export const useVerdicts = (pid: string) => useSub(pid, "verdicts");
export const useEvidence = (pid: string) => useSub(pid, "evidence");

export function useReel(pid: string) {
  const { user } = useAuth();
  const [beats, setBeats] = useState<any[]>([]);
  useEffect(() => {
    if (!user) return;
    return onSnapshot(doc(base(user.uid, pid), "meta", "reel"), (s) =>
      setBeats(s.exists() ? (s.data().beats ?? []) : []),
    );
  }, [user, pid]);
  return beats;
}

export function usePriorArt(pid: string) {
  const { user } = useAuth();
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    if (!user) return;
    return onSnapshot(doc(base(user.uid, pid), "meta", "prior_art"), (s) =>
      setData(s.exists() ? s.data() : null),
    );
  }, [user, pid]);
  return data;
}
