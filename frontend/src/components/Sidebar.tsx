import { ActivityIcon, StoreIcon } from "./Icons";
import type { ViewName } from "../types";

interface SidebarProps {
  active: ViewName;
  onChange: (view: ViewName) => void;
}

const navItems = [
  { id: "sellers" as const, label: "Продавцы", icon: StoreIcon },
  { id: "operations" as const, label: "Обработка", icon: ActivityIcon },
];

export function Sidebar({ active, onChange }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand__mark" aria-hidden="true">
          <span>M</span>
        </div>
        <div>
          <strong>Megamarket</strong>
          <span>control panel</span>
        </div>
      </div>

      <nav className="sidebar__nav" aria-label="Основная навигация">
        <p className="sidebar__caption">Рабочая область</p>
        {navItems.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            className={`nav-item ${active === id ? "nav-item--active" : ""}`}
            onClick={() => onChange(id)}
          >
            <Icon />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar__footer">
        <span className="connection-dot" />
        <div>
          <strong>API подключён</strong>
          <span>FastAPI · PostgreSQL</span>
        </div>
      </div>
    </aside>
  );
}
