/* Shared presentational components used by the role-based dashboards. */
import { ChevronRight } from "lucide-react";

export function StatCard({ icon: Icon, label, value, hint, color = "var(--primary)", onClick }) {
  return (
    <div className={`stat-card ${onClick ? "clickable" : ""}`} onClick={onClick}>
      <div className="stat-icon" style={{ color, backgroundColor: `color-mix(in srgb, ${color} 12%, white)` }}>
        {Icon && <Icon size={20} />}
      </div>
      <div style={{ minWidth: 0 }}>
        <div className="stat-label">{label}</div>
        <div className="stat-value" style={{ color }}>
          {value}
        </div>
        {hint && <div className="stat-hint">{hint}</div>}
      </div>
    </div>
  );
}

export function ToolCard({ icon: Icon, title, description, color = "var(--primary)", onClick, badge }) {
  return (
    <button type="button" className="tool-card" onClick={onClick} disabled={!onClick}>
      <div className="tool-icon" style={{ color, backgroundColor: `color-mix(in srgb, ${color} 12%, white)` }}>
        {Icon && <Icon size={22} />}
      </div>
      <div style={{ flex: 1, minWidth: 0, textAlign: "left" }}>
        <div className="tool-title">
          {title}
          {badge && <span className="tool-badge">{badge}</span>}
        </div>
        <div className="tool-desc">{description}</div>
      </div>
      {onClick && <ChevronRight size={18} color="var(--text-light)" />}
    </button>
  );
}

export function SectionCard({ title, action, children }) {
  return (
    <div className="card">
      <div className="section-head">
        <h3>{title}</h3>
        {action}
      </div>
      {children}
    </div>
  );
}

export function StatusBadge({ status }) {
  return (
    <span className={`badge ${status === "Accepted" ? "badge-status-accepted" : "badge-status-pending"}`}>
      {status}
    </span>
  );
}

export function EmptyState({ children }) {
  return <p className="empty-state">{children}</p>;
}
