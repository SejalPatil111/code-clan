const API_BASE = "/api";
const TOKEN_KEY = "codeclan_token";
const USER_KEY = "codeclan_user";

// =========================================================
// SESSION HELPERS
// =========================================================

export function getStoredSession() {
  const token = localStorage.getItem(TOKEN_KEY);
  const userRaw = localStorage.getItem(USER_KEY);
  if (!token || !userRaw) return null;
  try {
    return { token, user: JSON.parse(userRaw) };
  } catch {
    return null;
  }
}

export function storeSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

// Called when the API rejects the token (expired / invalid) so the UI can log out.
let unauthorizedHandler = null;
export function setUnauthorizedHandler(fn) {
  unauthorizedHandler = fn;
}

async function request(path, { method = "GET", body, errorMessage = "Request failed" } = {}) {
  const headers = {};
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    if (res.status === 401 && token && unauthorizedHandler) unauthorizedHandler();
    const detail = Array.isArray(errorData.detail)
      ? errorData.detail.map((d) => d.msg).join(", ")
      : errorData.detail;
    throw new Error(detail || errorMessage);
  }
  return res.json();
}

function withQuery(path, params) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") qs.append(k, v);
  });
  const s = qs.toString();
  return s ? `${path}?${s}` : path;
}

// =========================================================
// AUTH
// =========================================================

export function login(email, password) {
  return request("/auth/login", { method: "POST", body: { email, password }, errorMessage: "Login failed" });
}

export function register({ name, email, password, role }) {
  return request("/auth/register", {
    method: "POST",
    body: { name, email, password, role },
    errorMessage: "Registration failed",
  });
}

export function fetchMe() {
  return request("/auth/me", { errorMessage: "Session expired" });
}

// =========================================================
// CORE RESOURCES
// =========================================================

export function fetchUsers(role = null) {
  return request(withQuery("/users", { role }), { errorMessage: "Failed to fetch users" });
}

export function fetchProblems(filters = {}) {
  return request(
    withQuery("/problems", { difficulty: filters.difficulty, topic: filters.topic, search: filters.search }),
    { errorMessage: "Failed to fetch problems" }
  );
}

export function fetchProblemById(id) {
  return request(`/problems/${id}`, { errorMessage: "Failed to fetch problem details" });
}

export function createProblem(problemData) {
  return request("/problems", { method: "POST", body: problemData, errorMessage: "Failed to create problem" });
}

export function fetchSubmissions(filters = {}) {
  return request(
    withQuery("/submissions", {
      user_id: filters.user_id,
      problem_id: filters.problem_id,
      submission_type: filters.submission_type,
    }),
    { errorMessage: "Failed to fetch submissions" }
  );
}

export function createSubmission(submissionData) {
  return request("/submissions", {
    method: "POST",
    body: submissionData,
    errorMessage: "Failed to record submission",
  });
}

export function fetchAssignments(filters = {}) {
  return request(
    withQuery("/assignments", { student_id: filters.student_id, created_by: filters.created_by }),
    { errorMessage: "Failed to fetch assignments" }
  );
}

export function createAssignment(assignmentData) {
  return request("/assignments", {
    method: "POST",
    body: assignmentData,
    errorMessage: "Failed to create assignment",
  });
}

export function fetchCodingTests(filters = {}) {
  return request(withQuery("/coding-tests", { student_id: filters.student_id }), {
    errorMessage: "Failed to fetch coding tests",
  });
}

export function createCodingTest(testData) {
  return request("/coding-tests", { method: "POST", body: testData, errorMessage: "Failed to create coding test" });
}

export function completeCodingTest(testId, studentId) {
  return request(`/coding-tests/${testId}/complete?student_id=${studentId}`, {
    method: "POST",
    errorMessage: "Failed to record test completion",
  });
}

export function fetchLeaderboard() {
  return request("/leaderboard", { errorMessage: "Failed to fetch leaderboard" });
}

// =========================================================
// ROLE-BASED DASHBOARDS
// =========================================================

export function fetchTeacherOverview() {
  return request("/teacher/overview", { errorMessage: "Failed to load teacher dashboard" });
}

export function fetchStudentRoster() {
  return request("/teacher/students", { errorMessage: "Failed to load student roster" });
}

export function fetchStudentOverview() {
  return request("/student/overview", { errorMessage: "Failed to load student dashboard" });
}
