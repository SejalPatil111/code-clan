const API_BASE = "/api";

export async function fetchUsers(role = null) {
  const url = role ? `${API_BASE}/users?role=${role}` : `${API_BASE}/users`;
  const res = await fetch(url);
  if (!res.ok) throw new Error("Failed to fetch users");
  return res.json();
}

export async function fetchProblems(filters = {}) {
  const params = new URLSearchParams();
  if (filters.difficulty) params.append("difficulty", filters.difficulty);
  if (filters.topic) params.append("topic", filters.topic);
  if (filters.search) params.append("search", filters.search);

  const url = `${API_BASE}/problems${params.toString() ? `?${params.toString()}` : ""}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error("Failed to fetch problems");
  return res.json();
}

export async function fetchProblemById(id) {
  const res = await fetch(`${API_BASE}/problems/${id}`);
  if (!res.ok) throw new Error("Failed to fetch problem details");
  return res.json();
}

export async function createProblem(problemData) {
  const res = await fetch(`${API_BASE}/problems`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(problemData),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to create problem");
  }
  return res.json();
}

export async function fetchSubmissions(filters = {}) {
  const params = new URLSearchParams();
  if (filters.user_id) params.append("user_id", filters.user_id);
  if (filters.problem_id) params.append("problem_id", filters.problem_id);
  if (filters.submission_type) params.append("submission_type", filters.submission_type);

  const url = `${API_BASE}/submissions${params.toString() ? `?${params.toString()}` : ""}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error("Failed to fetch submissions");
  return res.json();
}

export async function createSubmission(submissionData) {
  const res = await fetch(`${API_BASE}/submissions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(submissionData),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to record submission");
  }
  return res.json();
}

export async function fetchAssignments(filters = {}) {
  const params = new URLSearchParams();
  if (filters.student_id) params.append("student_id", filters.student_id);
  if (filters.created_by) params.append("created_by", filters.created_by);

  const url = `${API_BASE}/assignments${params.toString() ? `?${params.toString()}` : ""}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error("Failed to fetch assignments");
  return res.json();
}

export async function createAssignment(assignmentData) {
  const res = await fetch(`${API_BASE}/assignments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(assignmentData),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to create assignment");
  }
  return res.json();
}

export async function fetchCodingTests() {
  const res = await fetch(`${API_BASE}/coding-tests`);
  if (!res.ok) throw new Error("Failed to fetch coding tests");
  return res.json();
}

export async function createCodingTest(testData) {
  const res = await fetch(`${API_BASE}/coding-tests`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(testData),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to create coding test");
  }
  return res.json();
}

export async function completeCodingTest(testId, studentId) {
  const res = await fetch(`${API_BASE}/coding-tests/${testId}/complete?student_id=${studentId}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to record test completion");
  return res.json();
}

export async function fetchLeaderboard() {
  const res = await fetch(`${API_BASE}/leaderboard`);
  if (!res.ok) throw new Error("Failed to fetch leaderboard");
  return res.json();
}
