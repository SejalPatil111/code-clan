// Defaults to "/api", which the Vite dev server proxies to FastAPI (see vite.config.js).
// VITE_* variables are embedded in browser code: never put secrets in them.
const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";
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

export function addProblemTestCase(problemId, testCaseData) {
  return request(`/problems/${problemId}/test-cases`, {
    method: "POST",
    body: testCaseData,
    errorMessage: "Failed to add test case",
  });
}

export function fetchProblemTestCases(problemId) {
  return request(`/problems/${problemId}/test-cases`, {
    errorMessage: "Failed to fetch problem test cases",
  });
}

export function fetchEnvironments() {
  return request("/environments", {
    errorMessage: "Failed to fetch execution environments",
  });
}

export function fetchProblemDatasets(problemId, includeContent = false) {
  return request(withQuery(`/problems/${problemId}/datasets`, { include_content: includeContent }), {
    errorMessage: "Failed to fetch problem datasets",
  });
}

export function addProblemDataset(problemId, datasetData) {
  return request(`/problems/${problemId}/datasets`, {
    method: "POST",
    body: datasetData,
    errorMessage: "Failed to upload dataset",
  });
}

export function deleteProblemDataset(problemId, datasetId) {
  return request(`/problems/${problemId}/datasets/${datasetId}`, {
    method: "DELETE",
    errorMessage: "Failed to delete dataset",
  });
}

export function runSampleCases({ problem_id, language, code, files, entry_point }) {
  return request("/submissions/run-samples", {
    method: "POST",
    body: { problem_id, language, code, files, entry_point },
    errorMessage: "Sample execution failed",
  });
}

export function fetchSubmissions(filters = {}) {
  return request(
    withQuery("/submissions", {
      user_id: filters.user_id,
      problem_id: filters.problem_id,
      submission_type: filters.submission_type,
      student_search: filters.student_search,
      problem_search: filters.problem_search,
      language: filters.language,
      status: filters.status,
      date_from: filters.date_from,
      date_to: filters.date_to,
      sort_by: filters.sort_by,
      limit: filters.limit || 250,
    }),
    { errorMessage: "Failed to fetch submissions" }
  );
}

export function fetchGroupedSubmissionsByStudent(filters = {}) {
  return request(
    withQuery("/submissions/grouped/by-student", {
      student_search: filters.student_search,
      problem_search: filters.problem_search,
      problem_id: filters.problem_id,
      submission_type: filters.submission_type,
      language: filters.language,
      status: filters.status,
      date_from: filters.date_from,
      date_to: filters.date_to,
      sort_by: filters.sort_by,
    }),
    { errorMessage: "Failed to fetch grouped student submissions" }
  );
}

export function fetchGroupedSubmissionsByProblem(filters = {}) {
  return request(
    withQuery("/submissions/grouped/by-problem", {
      user_id: filters.user_id,
      submission_type: filters.submission_type,
      problem_search: filters.problem_search,
    }),
    { errorMessage: "Failed to fetch grouped problem submissions" }
  );
}

export function fetchSubmissionById(submissionId) {
  return request(`/submissions/${submissionId}`, {
    errorMessage: "Failed to fetch submission details",
  });
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
    withQuery("/assignments", {
      student_id: filters.student_id,
      created_by: filters.created_by,
      search: filters.search,
    }),
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

export function fetchPracticals(filters = {}) {
  return request(
    withQuery("/practicals", {
      student_id: filters.student_id,
      subject_name: filters.subject_name,
      search: filters.search,
    }),
    { errorMessage: "Failed to fetch academic practicals" }
  );
}

export function createPractical(practicalData) {
  return request("/practicals", {
    method: "POST",
    body: practicalData,
    errorMessage: "Failed to create academic practical",
  });
}

export function bulkAssignPracticals(payload) {
  return request("/practicals/assign", {
    method: "POST",
    body: payload,
    errorMessage: "Failed to assign practicals to students",
  });
}

export function startPractical(practicalId) {
  return request(`/practicals/${practicalId}/start`, {
    method: "POST",
    errorMessage: "Failed to start practical",
  });
}

export function submitPractical(practicalId, payload) {
  return request(`/practicals/${practicalId}/submit`, {
    method: "POST",
    body: payload,
    errorMessage: "Failed to submit practical",
  });
}

export function evaluateStudentPractical(practicalId, studentId, payload) {
  return request(`/practicals/${practicalId}/students/${studentId}/evaluate`, {
    method: "POST",
    body: payload,
    errorMessage: "Failed to evaluate student practical",
  });
}

export function fetchCodingTests(filters = {}) {
  return request(
    withQuery("/coding-tests", {
      student_id: filters.student_id,
      search: filters.search,
    }),
    { errorMessage: "Failed to fetch coding tests" }
  );
}

export function createCodingTest(testData) {
  return request("/coding-tests", { method: "POST", body: testData, errorMessage: "Failed to create coding test" });
}

export function completeCodingTest(testId) {
  return request(`/coding-tests/${testId}/complete`, {
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

export function fetchExecutionSecurityStatus() {
  return request("/execution/security-status", { errorMessage: "Failed to load execution security status" });
}

export function fetchExecutionMetrics() {
  return request("/execution/metrics", { errorMessage: "Failed to load execution metrics" });
}
