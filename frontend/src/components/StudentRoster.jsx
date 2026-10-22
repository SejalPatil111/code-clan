import { useCallback, useEffect, useMemo, useState } from "react";
import { Search, RefreshCw, Zap } from "lucide-react";
import { fetchStudentRoster } from "../api";
import { EmptyState } from "./ui";
import { formatDate } from "./format";
import "./dashboard.css";

const SORTS = {
  xp: { label: "XP", fn: (a, b) => b.xp - a.xp },
  submissions: { label: "Submissions", fn: (a, b) => b.total_submissions - a.total_submissions },
  name: { label: "Name", fn: (a, b) => a.name.localeCompare(b.name) },
  inactive: {
    label: "Least active",
    fn: (a, b) => new Date(a.last_active || 0) - new Date(b.last_active || 0),
  },
};

export default function StudentRoster() {
  const [students, setStudents] = useState([]);
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState("xp");
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  // Async fetch: state updates happen in promise callbacks (effect-safe).
  const fetchData = useCallback(
    () =>
      fetchStudentRoster()
        .then((data) => {
          setStudents(data);
          setError(null);
        })
        .catch((err) => setError(err.message))
        .finally(() => setIsLoading(false)),
    []
  );

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const load = () => {
    setIsLoading(true);
    fetchData();
  };

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return students
      .filter((s) => !q || s.name.toLowerCase().includes(q) || s.email.toLowerCase().includes(q))
      .sort(SORTS[sortKey].fn);
  }, [students, query, sortKey]);

  const inactiveCount = students.filter((s) => !s.last_active).length;

  return (
    <div className="card">
      <div className="section-head" style={{ flexWrap: "wrap" }}>
        <div>
          <h3 style={{ fontSize: 18 }}>Student Roster &amp; Progress ({students.length})</h3>
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
            Live progress for every enrolled student.
            {inactiveCount > 0 && ` ${inactiveCount} student${inactiveCount > 1 ? "s have" : " has"} not submitted yet.`}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ position: "relative" }}>
            <Search size={14} style={{ position: "absolute", left: 10, top: 11, color: "var(--text-muted)" }} />
            <input
              className="form-input"
              style={{ paddingLeft: 30, width: 220 }}
              placeholder="Search name or email"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <select className="form-select" value={sortKey} onChange={(e) => setSortKey(e.target.value)}>
            {Object.entries(SORTS).map(([key, s]) => (
              <option key={key} value={key}>
                Sort: {s.label}
              </option>
            ))}
          </select>
          <button className="btn btn-outline" onClick={load} disabled={isLoading}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {error && <div className="auth-error">{error}</div>}

      {visible.length === 0 ? (
        <EmptyState>{isLoading ? "Loading students…" : "No students match your search."}</EmptyState>
      ) : (
        <div className="table-container">
          <table className="clan-table">
            <thead>
              <tr>
                <th>Student</th>
                <th>XP</th>
                <th>Tests Done</th>
                <th>Submissions</th>
                <th>Acceptance</th>
                <th>Problems Tried</th>
                <th>Assignments</th>
                <th>Last Active</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((s) => {
                const acceptance = s.total_submissions
                  ? Math.round((s.accepted_submissions / s.total_submissions) * 100)
                  : null;
                return (
                  <tr key={s.user_id}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{s.name}</div>
                      <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{s.email}</div>
                    </td>
                    <td>
                      <span style={{ fontWeight: 800, color: "var(--primary)", display: "inline-flex", gap: 4, alignItems: "center" }}>
                        <Zap size={13} /> {s.xp}
                      </span>
                    </td>
                    <td>{s.tests_completed}</td>
                    <td>{s.total_submissions}</td>
                    <td>{acceptance === null ? "—" : `${acceptance}%`}</td>
                    <td>{s.problems_attempted}</td>
                    <td>{s.assignments_assigned}</td>
                    <td>
                      {s.last_active ? (
                        <span style={{ fontSize: 12 }}>{formatDate(s.last_active, true)}</span>
                      ) : (
                        <span className="badge badge-hard">No activity</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
