import { useCallback, useEffect, useState } from "react";
import {
  Zap,
  Award,
  Clock,
  Target,
  CheckCircle2,
  BookOpen,
  FileCode2,
  Trophy,
  Sparkles,
  History,
  Play,
  Calendar,
  RefreshCw,
} from "lucide-react";
import { fetchStudentOverview } from "../api";
import { StatCard, ToolCard, SectionCard, StatusBadge, EmptyState } from "./ui";
import { formatDate } from "./format";
import "./dashboard.css";

export default function StudentDashboard({ currentUser, onNavigate }) {
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  // Async fetch: state updates happen in promise callbacks (effect-safe).
  const fetchData = useCallback(
    () =>
      fetchStudentOverview()
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

  const o = overview;
  const firstName = currentUser.name.split(" ")[0];
  const acceptance = o && o.total_submissions ? Math.round((o.accepted_submissions / o.total_submissions) * 100) : 0;
  const testProgress = o && o.tests_available ? (o.tests_completed / o.tests_available) * 100 : 0;

  return (
    <div className="dash">
      {/* HERO */}
      <div className="dash-hero student">
        <div>
          <h2>Hi {firstName}, ready to code? 🚀</h2>
          <p>
            {o && o.pending_tests.length > 0
              ? `You have ${o.pending_tests.length} coding test${o.pending_tests.length > 1 ? "s" : ""} waiting. Each one is worth +10 XP.`
              : "Keep your streak going: solve a practice problem or check your assignments."}
          </p>
          <div className="hero-actions" style={{ marginTop: 16 }}>
            <button className="btn btn-hero" onClick={() => onNavigate("practice")}>
              <FileCode2 size={16} /> Practice Now
            </button>
            <button className="btn btn-hero" onClick={() => onNavigate("coding_tests")}>
              <Clock size={16} /> Take a Test
            </button>
          </div>
        </div>
        <div className="hero-metric">
          <div className="big">{o ? `${o.xp} XP` : "—"}</div>
          <div className="small">{o && o.rank ? `Rank #${o.rank} of ${o.total_ranked}` : "Unranked"}</div>
        </div>
      </div>

      {error && <div className="auth-error">{error}</div>}

      {/* KPI CARDS */}
      <div className="stat-grid">
        <StatCard
          icon={Zap}
          label="Total XP"
          value={o ? o.xp : "…"}
          hint="+10 XP per completed test"
          color="#8b5cf6"
        />
        <StatCard
          icon={Award}
          label="Leaderboard Rank"
          value={o && o.rank ? `#${o.rank}` : "—"}
          hint={o ? `out of ${o.total_ranked} students` : ""}
          color="#2563eb"
          onClick={() => onNavigate("leaderboard")}
        />
        <StatCard
          icon={Clock}
          label="Tests Completed"
          value={o ? `${o.tests_completed}/${o.tests_available}` : "…"}
          hint="Official timed tests"
          color="#f59e0b"
          onClick={() => onNavigate("coding_tests")}
        />
        <StatCard
          icon={Target}
          label="Problems Attempted"
          value={o ? `${o.problems_attempted}/${o.total_problems}` : "…"}
          hint="Unique problems you've submitted"
          color="#0ea5e9"
          onClick={() => onNavigate("practice")}
        />
        <StatCard
          icon={CheckCircle2}
          label="Submissions"
          value={o ? o.total_submissions : "…"}
          hint={o ? `${acceptance}% accepted` : ""}
          color="#10b981"
          onClick={() => onNavigate("submissions")}
        />
      </div>

      <div className="dash-grid-2">
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {/* PENDING TESTS */}
          <SectionCard
            title="Coding Tests Waiting for You"
            action={
              <button className="btn btn-outline btn-sm" onClick={load} disabled={isLoading}>
                <RefreshCw size={13} /> Refresh
              </button>
            }
          >
            <div style={{ marginBottom: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
                <span style={{ color: "var(--text-muted)" }}>Overall test progress</span>
                <span style={{ fontWeight: 700 }}>{Math.round(testProgress)}%</span>
              </div>
              <div className="progress-track">
                <div className="progress-fill" style={{ width: `${testProgress}%`, backgroundColor: "#f59e0b" }} />
              </div>
            </div>
            {!o || o.pending_tests.length === 0 ? (
              <EmptyState>{isLoading ? "Loading…" : "🎉 You're all caught up! No pending tests."}</EmptyState>
            ) : (
              o.pending_tests.map((t) => (
                <div className="list-row" key={t.id}>
                  <div>
                    <div className="title">{t.title}</div>
                    <div className="meta">
                      {t.duration} mins · {t.problems.length} questions · by {t.creator_name}
                    </div>
                  </div>
                  <button className="btn btn-primary btn-sm" onClick={() => onNavigate("coding_tests")}>
                    <Play size={13} /> Start
                  </button>
                </div>
              ))
            )}
          </SectionCard>

          {/* RECENT SUBMISSIONS */}
          <SectionCard
            title="My Recent Submissions"
            action={
              <button className="btn btn-outline btn-sm" onClick={() => onNavigate("submissions")}>
                View all
              </button>
            }
          >
            {!o || o.recent_submissions.length === 0 ? (
              <EmptyState>
                {isLoading ? "Loading…" : "No submissions yet. Head to Practice to write your first solution!"}
              </EmptyState>
            ) : (
              <div className="table-container">
                <table className="clan-table">
                  <thead>
                    <tr>
                      <th>Problem</th>
                      <th>Language</th>
                      <th>Status</th>
                      <th>When</th>
                    </tr>
                  </thead>
                  <tbody>
                    {o.recent_submissions.map((s) => (
                      <tr key={s.id}>
                        <td style={{ fontWeight: 600 }}>{s.problem_title}</td>
                        <td style={{ textTransform: "capitalize" }}>{s.language}</td>
                        <td>
                          <StatusBadge status={s.status} />
                        </td>
                        <td style={{ fontSize: 12, color: "var(--text-muted)" }}>{formatDate(s.submitted_at, true)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </SectionCard>
        </div>

        {/* ASSIGNMENTS & DEADLINES */}
        <SectionCard
          title={
            <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Calendar size={16} /> My Assignments ({o ? o.assignments_assigned : 0})
            </span>
          }
          action={
            <button className="btn btn-outline btn-sm" onClick={() => onNavigate("assignments")}>
              Open
            </button>
          }
        >
          {!o || o.upcoming_deadlines.length === 0 ? (
            <EmptyState>{isLoading ? "Loading…" : "No upcoming assignments from your teachers."}</EmptyState>
          ) : (
            o.upcoming_deadlines.map((a) => (
              <div className="list-row" key={a.id}>
                <div style={{ minWidth: 0 }}>
                  <div className="title">{a.title}</div>
                  <div className="meta">
                    {a.problems.length} problems · {a.creator_name}
                  </div>
                </div>
                <span
                  className={`badge ${a.deadline ? "badge-medium" : "badge-easy"}`}
                  style={{ whiteSpace: "nowrap" }}
                >
                  {a.deadline ? `Due ${formatDate(a.deadline)}` : "No deadline"}
                </span>
              </div>
            ))
          )}
        </SectionCard>
      </div>

      {/* LEARNING TOOLS */}
      <SectionCard title="Learning Tools">
        <div className="tool-grid">
          <ToolCard
            icon={FileCode2}
            title="Practice Workspace"
            description="Browse problems by difficulty and code in the editor"
            color="#2563eb"
            onClick={() => onNavigate("practice")}
          />
          <ToolCard
            icon={BookOpen}
            title="My Assignments"
            description="Coursework your teachers assigned to you"
            color="#0ea5e9"
            onClick={() => onNavigate("assignments")}
          />
          <ToolCard
            icon={Clock}
            title="Coding Tests"
            description="Timed, proctored exams that award XP"
            color="#f59e0b"
            onClick={() => onNavigate("coding_tests")}
          />
          <ToolCard
            icon={Award}
            title="Leaderboard"
            description="See where you rank in the department"
            color="#d97706"
            onClick={() => onNavigate("leaderboard")}
          />
          <ToolCard
            icon={History}
            title="My Submissions"
            description="Your complete submission history"
            color="#10b981"
            onClick={() => onNavigate("submissions")}
          />
          <ToolCard
            icon={Trophy}
            title="Competitions"
            description="Join hackathons & coding contests"
            color="#dc2626"
            onClick={() => onNavigate("competitions")}
          />
          <ToolCard
            icon={Sparkles}
            title="AI Mentor"
            description="Hints & error explanations"
            color="#8b5cf6"
            badge="Coming soon"
            onClick={() => onNavigate("ai_mentor")}
          />
        </div>
      </SectionCard>
    </div>
  );
}
