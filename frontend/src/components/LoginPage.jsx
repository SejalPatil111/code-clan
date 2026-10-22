import { useState } from "react";
import { GraduationCap, BookOpen, LogIn, UserPlus, Users } from "lucide-react";
import { login, register } from "../api";
import "./dashboard.css";

export default function LoginPage({ onAuthenticated }) {
  const [mode, setMode] = useState("login"); // 'login' | 'register'
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "student" });
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  const update = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);
    try {
      const res =
        mode === "login"
          ? await login(form.email.trim(), form.password)
          : await register({
              name: form.name.trim(),
              email: form.email.trim(),
              password: form.password,
              role: form.role,
            });
      onAuthenticated(res.access_token, res.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const switchMode = (next) => {
    setMode(next);
    setError(null);
  };

  return (
    <div className="auth-page">
      <section className="auth-showcase">
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div className="brand-logo-icon">&lt;/&gt;</div>
            <div>
              <div className="brand-title">Code Clan</div>
              <div className="brand-subtitle">Department Workspace</div>
            </div>
          </div>
          <h1>
            One platform.
            <br />
            Built for every role.
          </h1>
          <p>
            Sign in and Code Clan opens the right workspace for you: tools for running classes if you
            teach, and practice, tests, and progress tracking if you're a student.
          </p>

          <div className="auth-role-preview">
            <div>
              <h4>
                <GraduationCap size={16} /> Teachers
              </h4>
              <ul>
                <li>• Class analytics dashboard</li>
                <li>• Question bank &amp; test cases</li>
                <li>• Assignments &amp; deadlines</li>
                <li>• Proctored coding tests</li>
                <li>• Student progress roster</li>
              </ul>
            </div>
            <div>
              <h4>
                <BookOpen size={16} /> Students
              </h4>
              <ul>
                <li>• Personal progress &amp; XP</li>
                <li>• Practice coding workspace</li>
                <li>• Assigned coursework</li>
                <li>• Timed coding tests</li>
                <li>• Leaderboard &amp; AI mentor</li>
              </ul>
            </div>
          </div>
        </div>
        <div style={{ fontSize: 12, color: "#64748b" }}>© {new Date().getFullYear()} Code Clan</div>
      </section>

      <section className="auth-form-wrap">
        <div className="auth-card">
          <h2>{mode === "login" ? "Welcome back" : "Create your account"}</h2>
          <p style={{ color: "var(--text-muted)", fontSize: 14 }}>
            {mode === "login"
              ? "Log in to open your dashboard."
              : "Choose your role. It decides which dashboard you see."}
          </p>

          <div className="auth-tabs">
            <button type="button" className={mode === "login" ? "active" : ""} onClick={() => switchMode("login")}>
              Log In
            </button>
            <button
              type="button"
              className={mode === "register" ? "active" : ""}
              onClick={() => switchMode("register")}
            >
              Sign Up
            </button>
          </div>

          {error && <div className="auth-error">{error}</div>}

          <form onSubmit={handleSubmit}>
            {mode === "register" && (
              <>
                <div className="form-group">
                  <label className="form-label">I am a</label>
                  <div className="role-picker">
                    <button
                      type="button"
                      className={form.role === "student" ? "active" : ""}
                      onClick={() => setForm({ ...form, role: "student" })}
                    >
                      <Users size={20} /> Student
                    </button>
                    <button
                      type="button"
                      className={form.role === "teacher" ? "active" : ""}
                      onClick={() => setForm({ ...form, role: "teacher" })}
                    >
                      <GraduationCap size={20} /> Teacher
                    </button>
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Full Name</label>
                  <input
                    className="form-input"
                    required
                    minLength={2}
                    placeholder="e.g. Aarav Sharma"
                    value={form.name}
                    onChange={update("name")}
                  />
                </div>
              </>
            )}

            <div className="form-group">
              <label className="form-label">Email</label>
              <input
                type="email"
                className="form-input"
                required
                placeholder="you@college.edu"
                value={form.email}
                onChange={update("email")}
                autoComplete="email"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Password</label>
              <input
                type="password"
                className="form-input"
                required
                minLength={mode === "register" ? 6 : 1}
                placeholder={mode === "register" ? "At least 6 characters" : "Your password"}
                value={form.password}
                onChange={update("password")}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
              />
            </div>

            <button type="submit" className="btn btn-primary" style={{ width: "100%", padding: 12 }} disabled={isLoading}>
              {mode === "login" ? <LogIn size={16} /> : <UserPlus size={16} />}
              {isLoading ? "Please wait..." : mode === "login" ? "Log In" : "Create Account"}
            </button>
          </form>

          {mode === "register" && (
            <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 14 }}>
              Already in the system without a password? Sign up with the same email to set one. Your
              existing role is kept.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
