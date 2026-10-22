import { useCallback, useEffect, useState } from "react";
import {
  Users,
  FileCode2,
  BookOpen,
  Clock,
  Activity,
  PieChart,
  PlusCircle,
  Award,
  Trophy,
  Sparkles,
  ClipboardList,
  History,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { fetchTeacherOverview } from "../api";
import { StatCard, ToolCard, SectionCard, StatusBadge, EmptyState } from "./ui";
import { formatDate } from "./format";
import "./dashboard.css";

const DIFFICULTY_COLORS = { Easy: "#10b981", Medium: "#f59e0b", Hard: "#ef4444" };

export default function TeacherDashboard({ currentUser, usersList, onNavigate }) {
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  // Async fetch: state updates happen in promise callbacks (effect-safe).
  const fetchData = useCallback(
    () =>
      fetchTeacherOverview()
        .then((data) => {
          setOverview(data);
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

  const userName = (id) => usersList.find((u) => u.id === id)?.name || `User #${id}`;
  const firstName = currentUser.name.split(" ")[0];
  const o = overview;
  const totalByDifficulty = o ? Object.values(o.difficulty_breakdown).reduce((a, b) => a + b, 0) : 0;

  return (
    <div className="dash">
      {/* HERO */}
      <div className="dash-hero teacher">
        <div>
          <h2>Welcome back, {firstName} 👋</h2>
          <p>Your teaching command center: build content, run assessments, and track every student.</p>
          <div className="hero-actions" style={{ marginTop: 16 }}>
            <button className="btn btn-hero" onClick={() => onNavigate("teacher_workspace", "create_problem")}>
              <PlusCircle size={16} /> New Problem
            </button>
            <button className="btn btn-hero" onClick={() => onNavigate("teacher_workspace", "create_assignment")}>
              <BookOpen size={16} /> New Assignment
            </button>
            <button className="btn btn-hero" onClick={() => onNavigate("teacher_workspace", "create_test")}>
              <Clock size={16} /> New Coding Test
            </button>
          </div>
        </div>
        <div className="hero-metric">
          <div className="big">{o ? `${o.test_completion_rate}%` : "—"}</div>
          <div className="small">Class test completion</div>
        </div>
      </div>

      {error && <div className="auth-error">{error}</div>}

      {/* KPI CARDS */}
      <div className="stat-grid">
        <StatCard
          icon={Users}
          label="Enrolled Students"
          value={o ? o.total_students : "…"}
          hint="Click to open the student roster"
          color="#2563eb"
          onClick={() => onNavigate("students")}
        />
        <StatCard
          icon={FileCode2}
          label="Question Bank"
          value={o ? o.total_problems : "…"}
          hint={o ? `${o.my_problems} created by you` : ""}
          color="#8b5cf6"
          onClick={() => onNavigate("teacher_workspace", "manage")}
        />
        <StatCard
          icon={BookOpen}
          label="Assignments"
          value={o ? o.total_assignments : "…"}
          hint={o ? `${o.my_assignments} created by you` : ""}
          color="#0ea5e9"
          onClick={() => onNavigate("teacher_workspace", "manage")}
        />
        <StatCard
          icon={Clock}
          label="Coding Tests"
          value={o ? o.total_coding_tests : "…"}
          hint={o ? `${o.my_coding_tests} created by you` : ""}
          color="#f59e0b"
          onClick={() => onNavigate("teacher_workspace", "manage")}
        />
        <StatCard
          icon={Activity}
          label="Submissions (7 days)"
          value={o ? o.submissions_last_7_days : "…"}
          hint={o ? `${o.total_submissions} all-time` : ""}
          color="#10b981"
          onClick={() => onNavigate("submissions")}
        />
      </div>

      {/* TEACHING TOOLKIT */}
      <SectionCard title="Teaching Toolkit">
        <div className="tool-grid">
          <ToolCard
            icon={FileCode2}
            title="Question Bank"
            description="Write problem statements, constraints & sample test cases"
            color="#8b5cf6"
            onClick={() => onNavigate("teacher_workspace", "create_problem")}
          />
          <ToolCard
            icon={BookOpen}
            title="Assignments"
            description="Bundle problems and assign them to students with deadlines"
            color="#0ea5e9"
            onClick={() => onNavigate("teacher_workspace", "create_assignment")}
          />
          <ToolCard
            icon={ShieldCheck}
            title="Proctored Coding Tests"
            description="Timed exams with tab-switch detection & custom questions"
            color="#f59e0b"
            onClick={() => onNavigate("teacher_workspace", "create_test")}
          />
          <ToolCard
            icon={ClipboardList}
            title="Manage Activities"
            description="Track published tests, coursework and the question bank"
            color="#64748b"
            onClick={() => onNavigate("teacher_workspace", "manage")}
          />
          <ToolCard
            icon={Users}
            title="Student Analytics"
            description="Per-student XP, submissions, acceptance and activity"
            color="#2563eb"
            onClick={() => onNavigate("students")}
          />
          <ToolCard
            icon={History}
            title="Class Submissions"
            description="Review every code submission across the department"
            color="#10b981"
            onClick={() => onNavigate("submissions")}
          />
          <ToolCard
            icon={Award}
            title="Leaderboard"
            description="See how students rank by test XP"
            color="#d97706"
            onClick={() => onNavigate("leaderboard")}
          />
          <ToolCard
            icon={Trophy}
            title="Competitions"
            description="Department hackathons & contests"
            color="#dc2626"
            onClick={() => onNavigate("competitions")}
          />
          <ToolCard
            icon={Sparkles}
            title="AI Teaching Assistant"
            description="Auto-generate problems & test cases"
            color="#8b5cf6"
            badge="Coming soon"
            onClick={() => onNavigate("ai_mentor")}
          />
        </div>
      </SectionCard>

      <div className="dash-grid-2">
        {/* RECENT CLASS SUBMISSIONS */}
        <SectionCard
          title="Recent Class Submissions"
          action={
            <button className="btn btn-outline btn-sm" onClick={load} disabled={isLoading}>
              <RefreshCw size={13} /> Refresh
            </button>
          }
        >
          {!o || o.recent_submissions.length === 0 ? (
            <EmptyState>{isLoading ? "Loading…" : "No submissions from students yet."}</EmptyState>
          ) : (
            <div className="table-container">
              <table className="clan-table">
                <thead>
                  <tr>
                    <th>Student</th>
                    <th>Problem</th>
                    <th>Status</th>
                    <th>Context</th>
                    <th>When</th>
                  </tr>
                </thead>
                <tbody>
                  {o.recent_submissions.map((s) => (
                    <tr key={s.id}>
                      <td style={{ fontWeight: 600 }}>{userName(s.user_id)}</td>
                      <td>{s.problem_title}</td>
                      <td>
                        <StatusBadge status={s.status} />
                      </td>
                      <td style={{ textTransform: "capitalize" }}>{s.submission_type.replace("_", " ")}</td>
                      <td style={{ fontSize: 12, color: "var(--text-muted)" }}>{formatDate(s.submitted_at, true)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>

        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {/* TOP STUDENTS */}
          <SectionCard
            title="Top Performing Students"
            action={
              <button className="btn btn-outline btn-sm" onClick={() => onNavigate("students")}>
                View all
              </button>
            }
          >
            {!o || o.top_students.length === 0 ? (
              <EmptyState>{isLoading ? "Loading…" : "No students enrolled yet."}</EmptyState>
            ) : (
              o.top_students.map((s, idx) => (
                <div className="list-row" key={s.user_id}>
                  <div>
                    <div className="title">
                      #{idx + 1} {s.name}
                    </div>
                    <div className="meta">
                      {s.tests_completed} tests · {s.total_submissions} submissions
                    </div>
                  </div>
                  <span style={{ fontWeight: 800, color: "var(--primary)" }}>{s.xp} XP</span>
                </div>
              ))
            )}
          </SectionCard>

          {/* DIFFICULTY MIX */}
          <SectionCard
            title={
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <PieChart size={16} /> Question Bank Difficulty Mix
              </span>
            }
          >
            {!o || totalByDifficulty === 0 ? (
              <EmptyState>{isLoading ? "Loading…" : "No problems in the bank yet."}</EmptyState>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {Object.entries(o.difficulty_breakdown).map(([level, count]) => (
                  <div key={level}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
                      <span style={{ fontWeight: 600 }}>{level}</span>
                      <span style={{ color: "var(--text-muted)" }}>{count}</span>
                    </div>
                    <div className="progress-track">
                      <div
                        className="progress-fill"
                        style={{
                          width: `${(count / totalByDifficulty) * 100}%`,
                          backgroundColor: DIFFICULTY_COLORS[level],
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </SectionCard>
        </div>
      </div>
    </div>
  );
}
