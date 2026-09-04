import { useCallback, useEffect, useState } from "react";
import { OperationsView } from "./components/OperationsView";
import { SellersView } from "./components/SellersView";
import { Sidebar } from "./components/Sidebar";
import type { ViewName } from "./types";

interface ToastState {
  message: string;
  kind: "success" | "error";
  key: number;
}

export default function App() {
  const [view, setView] = useState<ViewName>("operations");
  const [toast, setToast] = useState<ToastState | null>(null);

  const notify = useCallback((message: string, kind: "success" | "error" = "success") => {
    setToast({ message, kind, key: Date.now() });
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timeout = window.setTimeout(() => setToast(null), 4800);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  return (
    <div className="app-shell">
      <Sidebar active={view} onChange={setView} />
      <main className="main-content">
        <div className="mobile-topbar">
          <div className="brand__mark"><span>M</span></div>
          <strong>Megamarket Control</strong>
          <div className="mobile-nav">
            <button className={view === "sellers" ? "active" : ""} onClick={() => setView("sellers")}>Продавцы</button>
            <button className={view === "operations" ? "active" : ""} onClick={() => setView("operations")}>Задачи</button>
          </div>
        </div>
        <div className="content-wrap">
          {view === "sellers" ? <SellersView notify={notify} /> : <OperationsView notify={notify} />}
        </div>
      </main>

      {toast ? (
        <div key={toast.key} className={`toast toast--${toast.kind}`} role="status">
          <span>{toast.kind === "success" ? "✓" : "!"}</span>
          <div>
            <strong>{toast.kind === "success" ? "Готово" : "Ошибка"}</strong>
            <p>{toast.message}</p>
          </div>
          <button type="button" onClick={() => setToast(null)} aria-label="Закрыть">×</button>
        </div>
      ) : null}
    </div>
  );
}
