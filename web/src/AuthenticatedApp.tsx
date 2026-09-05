import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth";
import { Projects } from "./pages/Projects";

const Project = lazy(() => import("./pages/Project").then((m) => ({ default: m.Project })));

export default function AuthenticatedApp() {
  return <AuthProvider><Suspense fallback={<div className="wrap"><p className="muted">Opening the archive…</p></div>}>
    <Routes>
      <Route path="/" element={<Projects />} />
      <Route path="/p/:pid" element={<Project />} />
    </Routes>
  </Suspense></AuthProvider>;
}
