import React, { lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { ThemeProvider } from "./theme";
import "./styles.css";

const Demo = lazy(() => import("./pages/Demo").then((m) => ({ default: m.Demo })));
const AuthenticatedApp = lazy(() => import("./AuthenticatedApp"));

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider>
      <BrowserRouter>
        <Suspense fallback={<div className="wrap"><p className="muted">Opening THE BOXES…</p></div>}>
          <Routes>
            <Route path="/demo" element={<Demo />} />
            <Route path="*" element={<AuthenticatedApp />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </ThemeProvider>
  </React.StrictMode>,
);
