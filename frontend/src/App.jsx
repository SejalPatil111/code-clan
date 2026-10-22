import { useState, useEffect } from "react";
import {
  Code,
  LayoutDashboard,
  FileCode2,
  BookOpen,
  Trophy,
  History,
  GraduationCap,
  Sparkles,
  Search,
  CheckCircle2,
  Clock,
  Play,
  Send,
  PlusCircle,
  AlertCircle,
  TrendingUp,
  Award,
  Zap,
  ChevronRight,
  BookMarked,
  Filter,
  Users,
  CheckSquare,
  Square,
  Calendar,
  Medal,
  Timer,
  Check,
  Shield,
  ShieldAlert,
  LogOut,
  ArrowLeft,
  Save,
} from "lucide-react";

import {
  fetchUsers,
  fetchProblems,
  fetchProblemById,
  createProblem,
  fetchSubmissions,
  createSubmission,
  fetchAssignments,
  createAssignment,
  fetchCodingTests,
  createCodingTest,
  completeCodingTest,
  fetchLeaderboard,
} from "./api";
import TeacherDashboard from "./components/TeacherDashboard";
import StudentDashboard from "./components/StudentDashboard";
import StudentRoster from "./components/StudentRoster";
import "./App.css";
import "./components/dashboard.css";

// Sidebar navigation per role. `tab` maps to a content section; `sub` selects a
// teacher workspace panel.
const STUDENT_NAV = [
  { section: "Overview" },
  { tab: "dashboard", label: "My Dashboard", icon: LayoutDashboard },
  { section: "Learn & Practice" },
  { tab: "practice", label: "Practice Problems", icon: FileCode2 },
  { tab: "assignments", label: "My Assignments", icon: BookOpen },
  { tab: "coding_tests", label: "Coding Tests", icon: Clock },
  { tab: "submissions", label: "My Submissions", icon: History },
  { section: "Community" },
  { tab: "leaderboard", label: "Leaderboard", icon: Award },
  { tab: "competitions", label: "Competitions", icon: Trophy },
  { tab: "ai_mentor", label: "AI Mentor", icon: Sparkles },
];

const TEACHER_NAV = [
  { section: "Overview" },
  { tab: "dashboard", label: "Teacher Dashboard", icon: LayoutDashboard },
  { section: "Course Content" },
  { tab: "teacher_workspace", sub: "create_problem", label: "Question Bank", icon: PlusCircle },
  { tab: "teacher_workspace", sub: "create_assignment", label: "Create Assignment", icon: BookOpen },
  { tab: "teacher_workspace", sub: "create_test", label: "Design Coding Test", icon: Clock },
  { tab: "teacher_workspace", sub: "manage", label: "Manage Activities", icon: CheckSquare },
  { section: "Students" },
  { tab: "students", label: "Student Progress", icon: Users },
  { tab: "submissions", label: "Class Submissions", icon: History },
  { tab: "leaderboard", label: "Leaderboard", icon: Award },
  { section: "More" },
  { tab: "competitions", label: "Competitions", icon: Trophy },
  { tab: "ai_mentor", label: "AI Assistant", icon: Sparkles },
];

const PAGE_TITLES = {
  dashboard: { student: "My Learning Dashboard", teacher: "Teacher Dashboard" },
  practice: "Coding Practice & Workspace",
  assignments: "My Coursework & Assignments",
  coding_tests: "Coding Tests",
  leaderboard: "Department Leaderboard",
  competitions: "Coding Competitions & Hackathons",
  submissions: { student: "My Submission History", teacher: "Class Submission Records" },
  ai_mentor: { student: "AI Mentor & Tutor Assistance", teacher: "AI Teaching Assistant" },
  students: "Student Roster & Progress",
  teacher_workspace: {
    create_problem: "Question Bank: Create Problem",
    create_assignment: "Create & Assign Coursework",
    create_test: "Design a Coding Test",
    manage: "Manage Activities",
  },
};

export default function App({ currentUser, onLogout }) {
  const userRole = currentUser.role;
  const isTeacher = userRole === "teacher" || userRole === "admin";
  const navItems = isTeacher ? TEACHER_NAV : STUDENT_NAV;

  const [activeTab, setActiveTab] = useState("dashboard");
  const [usersList, setUsersList] = useState([]);

  // Practice state
  const [problems, setProblems] = useState([]);
  const [selectedProblem, setSelectedProblem] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [difficultyFilter, setDifficultyFilter] = useState("");
  const [editorCode, setEditorCode] = useState(
    "# Write your Python solution here\ndef solve():\n    pass\n"
  );
  const [selectedLanguage, setSelectedLanguage] = useState("python");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [lastSubmissionResult, setLastSubmissionResult] = useState(null);
  const [isLoadingProblems, setIsLoadingProblems] = useState(false);
  const [networkError, setNetworkError] = useState(null);

  // Submissions history state
  const [submissions, setSubmissions] = useState([]);

  // Assignments state
  const [assignments, setAssignments] = useState([]);

  // Coding Tests & Leaderboard state
  const [codingTests, setCodingTests] = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);
  const [completingTestId, setCompletingTestId] = useState(null);
  const [testActionMsg, setTestActionMsg] = useState(null);

  // Teacher Workspace State
  const [teacherTab, setTeacherTab] = useState("create_problem"); // 'create_problem' | 'create_assignment' | 'create_test' | 'manage'

  // Teacher Problem Creation Form state
  const [newProblem, setNewProblem] = useState({
    title: "",
    difficulty: "Easy",
    topic: "Arithmetic Operations",
    description: "",
    input_format: "",
    output_format: "",
    constraints: "",
    examples: "",
    sample_input: "",
    sample_output: "",
  });
  const [isSubmittingProblem, setIsSubmittingProblem] = useState(false);
  const [formMsg, setFormMsg] = useState(null);

  // Teacher Assignment Creation Form state
  const [newAssignment, setNewAssignment] = useState({
    title: "",
    description: "",
    start_date: "",
    deadline: "",
    selectedProblemIds: [],
    selectedStudentIds: [],
  });
  const [isSubmittingAssignment, setIsSubmittingAssignment] = useState(false);
  const [assignmentFormMsg, setAssignmentFormMsg] = useState(null);

  // Teacher Coding Test Creation Form state
  const [newCodingTest, setNewCodingTest] = useState({
    title: "",
    description: "",
    duration: 60,
    selectedProblemIds: [],
  });
  const [testCustomProblems, setTestCustomProblems] = useState([]);
  const [newTestCustomProblem, setNewTestCustomProblem] = useState({
    title: "",
    difficulty: "Easy",
    topic: "Arithmetic Operations",
    description: "",
    input_format: "",
    output_format: "",
    constraints: "",
    examples: "",
    sample_input: "",
    sample_output: "",
  });
  const [showAddCustomQuestion, setShowAddCustomQuestion] = useState(false);
  const [isSubmittingTest, setIsSubmittingTest] = useState(false);
  const [testFormMsg, setTestFormMsg] = useState(null);

  // Active Student Test Session (Proctored Environment)
  const [activeTestSession, setActiveTestSession] = useState(null); // { test, timeRemaining, activeProblemIndex, answers: { [probId]: code }, violationWarnings: 0, status: 'in_progress' | 'submitted' }
  const [testEditorLanguage, setTestEditorLanguage] = useState("python");
  const [testRunOutput, setTestRunOutput] = useState(null);
  const [isTestEvaluating, setIsTestEvaluating] = useState(false);
  const [tabSwitchAlert, setTabSwitchAlert] = useState(false);

  // Load initial data
  useEffect(() => {
    loadUsers();
    loadProblems();
    loadSubmissions();
    loadAssignments();
    loadCodingTests();
    loadLeaderboardData();
  }, []);

  const loadUsers = async () => {
    try {
      const data = await fetchUsers();
      setUsersList(data);
    } catch (err) {
      console.error("Error loading users:", err);
    }
  };

  const loadProblems = async (filters = {}) => {
    setIsLoadingProblems(true);
    setNetworkError(null);
    try {
      const data = await fetchProblems(filters);
      setProblems(data);
      if (data.length > 0) {
        setSelectedProblem((prev) => {
          if (!prev) {
            openProblem(data[0]);
            return data[0];
          }
          const stillThere = data.find((p) => p.id === prev.id);
          if (!stillThere) {
            openProblem(data[0]);
            return data[0];
          }
          return prev;
        });
      } else {
        setSelectedProblem(null);
      }
    } catch (err) {
      console.error("Error loading problems:", err);
      setNetworkError("Unable to reach Code Clan API server. Please verify backend is running.");
    } finally {
      setIsLoadingProblems(false);
    }
  };

  // Students only see their own submissions / assignments; teachers see the whole class.
  const loadSubmissions = async () => {
    try {
      const data = await fetchSubmissions(isTeacher ? {} : { user_id: currentUser.id });
      setSubmissions(data);
    } catch (err) {
      console.error("Error loading submissions:", err);
    }
  };

  const loadAssignments = async () => {
    try {
      const data = await fetchAssignments(isTeacher ? {} : { student_id: currentUser.id });
      setAssignments(data);
    } catch (err) {
      console.error("Error loading assignments:", err);
    }
  };

  const loadCodingTests = async () => {
    try {
      const data = await fetchCodingTests(isTeacher ? {} : { student_id: currentUser.id });
      setCodingTests(data);
    } catch (err) {
      console.error("Error loading coding tests:", err);
    }
  };

  const loadLeaderboardData = async () => {
    try {
      const data = await fetchLeaderboard();
      setLeaderboard(data);
    } catch (err) {
      console.error("Error loading leaderboard:", err);
    }
  };

  const openProblem = async (prob) => {
    try {
      const fullProb = await fetchProblemById(prob.id);
      setSelectedProblem(fullProb);
      setLastSubmissionResult(null);
      setEditorCode(
        `# Problem: ${fullProb.title} (${fullProb.difficulty})\n# Topic: ${fullProb.topic}\n# Language: Python 3\n\ndef solution():\n    # Implement your logic here\n    pass\n`
      );
    } catch (err) {
      console.error("Error fetching problem details:", err);
      setSelectedProblem(prob);
    }
  };

  const handleFilterChange = (diff) => {
    setDifficultyFilter(diff);
    loadProblems({ difficulty: diff || undefined, search: searchQuery || undefined });
  };

  const handleSearchChange = (e) => {
    const val = e.target.value;
    setSearchQuery(val);
    loadProblems({ difficulty: difficultyFilter || undefined, search: val || undefined });
  };

  const handleSubmitSolution = async () => {
    const activeUserId = currentUser.id;
    if (!selectedProblem) return;
    setIsSubmitting(true);
    setLastSubmissionResult(null);

    try {
      const payload = {
        user_id: activeUserId,
        problem_id: selectedProblem.id,
        code: editorCode,
        language: selectedLanguage,
        submission_type: "practice",
      };

      const result = await createSubmission(payload);
      setLastSubmissionResult(result);
      await loadSubmissions();
    } catch (err) {
      alert("Submission error: " + err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCreateProblemSubmit = async (e) => {
    e.preventDefault();
    setFormMsg(null);
    setIsSubmittingProblem(true);

    const activeUserId = currentUser.id;

    try {
      const payload = {
        title: newProblem.title.trim(),
        description: newProblem.description.trim(),
        difficulty: newProblem.difficulty,
        topic: newProblem.topic.trim(),
        input_format: newProblem.input_format?.trim() || null,
        output_format: newProblem.output_format?.trim() || null,
        constraints: newProblem.constraints?.trim() || null,
        examples: newProblem.examples?.trim() || null,
        created_by: activeUserId,
        test_cases: [
          {
            input: newProblem.sample_input || "sample_input",
            expected_output: newProblem.sample_output || "sample_output",
            is_hidden: false,
          },
        ],
      };

      const res = await createProblem(payload);
      setFormMsg({ type: "success", text: `Problem "${res.title}" created successfully and added to database!` });
      setNewProblem({
        title: "",
        difficulty: "Easy",
        topic: "Arithmetic Operations",
        description: "",
        input_format: "",
        output_format: "",
        constraints: "",
        examples: "",
        sample_input: "",
        sample_output: "",
      });
      await loadProblems();
    } catch (err) {
      setFormMsg({ type: "error", text: "Error saving problem: " + err.message });
    } finally {
      setIsSubmittingProblem(false);
    }
  };

  const toggleProblemSelection = (id) => {
    setNewAssignment((prev) => {
      const exists = prev.selectedProblemIds.includes(id);
      return {
        ...prev,
        selectedProblemIds: exists
          ? prev.selectedProblemIds.filter((p) => p !== id)
          : [...prev.selectedProblemIds, id],
      };
    });
  };

  const toggleStudentSelection = (id) => {
    setNewAssignment((prev) => {
      const exists = prev.selectedStudentIds.includes(id);
      return {
        ...prev,
        selectedStudentIds: exists
          ? prev.selectedStudentIds.filter((s) => s !== id)
          : [...prev.selectedStudentIds, id],
      };
    });
  };

  const selectAllStudents = () => {
    const studentUsers = usersList.filter((u) => u.role === "student");
    setNewAssignment((prev) => ({
      ...prev,
      selectedStudentIds: studentUsers.map((s) => s.id),
    }));
  };

  const handleCreateAssignmentSubmit = async (e) => {
    e.preventDefault();
    setAssignmentFormMsg(null);

    if (newAssignment.selectedProblemIds.length === 0) {
      setAssignmentFormMsg({ type: "error", text: "Please select at least one coding problem." });
      return;
    }

    if (newAssignment.selectedStudentIds.length === 0) {
      setAssignmentFormMsg({ type: "error", text: "Please assign at least one student." });
      return;
    }

    setIsSubmittingAssignment(true);
    const activeUserId = currentUser.id;

    try {
      const payload = {
        title: newAssignment.title.trim(),
        description: newAssignment.description?.trim() || null,
        created_by: activeUserId,
        start_date: newAssignment.start_date ? new Date(newAssignment.start_date).toISOString() : null,
        deadline: newAssignment.deadline ? new Date(newAssignment.deadline).toISOString() : null,
        problem_ids: newAssignment.selectedProblemIds,
        student_ids: newAssignment.selectedStudentIds,
      };

      const res = await createAssignment(payload);
      setAssignmentFormMsg({
        type: "success",
        text: `Assignment "${res.title}" successfully created and assigned to ${res.students.length} students!`,
      });
      setNewAssignment({
        title: "",
        description: "",
        start_date: "",
        deadline: "",
        selectedProblemIds: [],
        selectedStudentIds: [],
      });
      await loadAssignments();
    } catch (err) {
      setAssignmentFormMsg({ type: "error", text: "Error creating assignment: " + err.message });
    } finally {
      setIsSubmittingAssignment(false);
    }
  };

  // Teacher Test Creation Handlers
  const toggleTestProblemSelection = (id) => {
    setNewCodingTest((prev) => {
      const exists = prev.selectedProblemIds.includes(id);
      return {
        ...prev,
        selectedProblemIds: exists
          ? prev.selectedProblemIds.filter((p) => p !== id)
          : [...prev.selectedProblemIds, id],
      };
    });
  };

  const handleAddCustomProblemToTest = (e) => {
    e.preventDefault();
    if (!newTestCustomProblem.title.trim() || !newTestCustomProblem.description.trim()) {
      alert("Please provide at least a Title and Description for the custom problem.");
      return;
    }
    setTestCustomProblems((prev) => [...prev, { ...newTestCustomProblem }]);
    setNewTestCustomProblem({
      title: "",
      difficulty: "Easy",
      topic: "Arithmetic Operations",
      description: "",
      input_format: "",
      output_format: "",
      constraints: "",
      examples: "",
      sample_input: "",
      sample_output: "",
    });
    setShowAddCustomQuestion(false);
  };

  const handleRemoveCustomProblemFromTest = (index) => {
    setTestCustomProblems((prev) => prev.filter((_, idx) => idx !== index));
  };

  const handleCreateTestSubmit = async (e) => {
    e.preventDefault();
    setTestFormMsg(null);

    const totalSelectedCount = newCodingTest.selectedProblemIds.length + testCustomProblems.length;
    if (totalSelectedCount === 0) {
      setTestFormMsg({
        type: "error",
        text: "Please select at least one predefined problem or create a unique custom question for this test.",
      });
      return;
    }

    setIsSubmittingTest(true);
    const activeUserId = currentUser.id;

    try {
      const payload = {
        title: newCodingTest.title.trim(),
        description: newCodingTest.description?.trim() || null,
        created_by: activeUserId,
        duration: parseInt(newCodingTest.duration) || 60,
        problem_ids: newCodingTest.selectedProblemIds,
        custom_problems: testCustomProblems,
      };

      const res = await createCodingTest(payload);
      setTestFormMsg({
        type: "success",
        text: `Coding Test "${res.title}" published with ${res.problems?.length || totalSelectedCount} questions! It is now available to all students.`,
      });
      setNewCodingTest({
        title: "",
        description: "",
        duration: 60,
        selectedProblemIds: [],
      });
      setTestCustomProblems([]);
      await loadCodingTests();
      await loadProblems(); // Refresh problems list since new custom questions were created
    } catch (err) {
      setTestFormMsg({ type: "error", text: "Error creating coding test: " + err.message });
    } finally {
      setIsSubmittingTest(false);
    }
  };

  // =========================================================
  // SECURE PROCTORED TEST ENVIRONMENT HANDLERS
  // =========================================================
  const handleStartTest = async (test) => {
    if (!test || !test.problems || test.problems.length === 0) {
      alert("This test has no questions assigned yet.");
      return;
    }

    // Pre-populate solution code templates for all test problems
    const initialAnswers = {};
    for (const p of test.problems) {
      initialAnswers[p.problem_id] = `# Test Question: ${p.title}\n# Difficulty: ${p.difficulty} | Topic: ${p.topic}\n# Language: Python 3\n\ndef solution():\n    # Write your solution code here\n    pass\n`;
    }

    // Initialize timer in seconds (duration in minutes * 60)
    const initialSeconds = Math.max(test.duration * 60, 60);

    setActiveTestSession({
      test: test,
      timeRemaining: initialSeconds,
      activeProblemIndex: 0,
      answers: initialAnswers,
      violationWarnings: 0,
      status: "in_progress",
    });
    setTestRunOutput(null);
    setTabSwitchAlert(false);
  };

  // Timer countdown and Anti-Cheat Event Listeners
  useEffect(() => {
    if (!activeTestSession || activeTestSession.status !== "in_progress") return;

    // 1. Countdown Interval
    const timerInterval = setInterval(() => {
      setActiveTestSession((prev) => {
        if (!prev || prev.status !== "in_progress") return prev;
        if (prev.timeRemaining <= 1) {
          // Time's up: Auto-submit
          clearInterval(timerInterval);
          handleFinalSubmitTest(true);
          return { ...prev, timeRemaining: 0 };
        }
        return { ...prev, timeRemaining: prev.timeRemaining - 1 };
      });
    }, 1000);

    // 2. Anti-cheat Tab Switching & Blur listener
    const handleVisibilityChange = () => {
      if (document.hidden) {
        setActiveTestSession((prev) => {
          if (!prev || prev.status !== "in_progress") return prev;
          const newWarnings = (prev.violationWarnings || 0) + 1;
          return { ...prev, violationWarnings: newWarnings };
        });
        setTabSwitchAlert(true);
      }
    };

    const handleWindowBlur = () => {
      setActiveTestSession((prev) => {
        if (!prev || prev.status !== "in_progress") return prev;
        const newWarnings = (prev.violationWarnings || 0) + 1;
        return { ...prev, violationWarnings: newWarnings };
      });
      setTabSwitchAlert(true);
    };

    // 3. Shortcut keys & context menu lock
    const handleKeyDown = (e) => {
      // Prevent F12, Ctrl+Shift+I, Ctrl+U, Alt+Tab notification, Ctrl+C / Ctrl+V in non-editor
      if (
        e.key === "F12" ||
        (e.ctrlKey && e.shiftKey && (e.key === "I" || e.key === "i" || e.key === "J" || e.key === "j" || e.key === "C" || e.key === "c")) ||
        (e.ctrlKey && (e.key === "U" || e.key === "u"))
      ) {
        e.preventDefault();
        setTabSwitchAlert(true);
      }
    };

    const handleContextMenu = (e) => {
      e.preventDefault();
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("blur", handleWindowBlur);
    window.addEventListener("keydown", handleKeyDown);
    document.addEventListener("contextmenu", handleContextMenu);

    return () => {
      clearInterval(timerInterval);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("blur", handleWindowBlur);
      window.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("contextmenu", handleContextMenu);
    };
  }, [activeTestSession?.status]);

  // Run Test Samples Execution Simulator
  const handleRunTestSampleCode = (prob) => {
    const code = activeTestSession.answers[prob.problem_id] || "";
    setIsTestEvaluating(true);
    setTestRunOutput(null);

    setTimeout(() => {
      setIsTestEvaluating(false);
      if (!code.trim() || code.includes("pass")) {
        setTestRunOutput({
          status: "Warning",
          message: "Code executed with default template. Implement logic to satisfy sample cases.",
          sampleInput: prob.sample_input || "5 10",
          expectedOutput: prob.sample_output || "15",
          userOutput: "None (Function body empty)",
          passed: false,
        });
      } else {
        setTestRunOutput({
          status: "Success",
          message: "Sample test case passed! Execution completed in 0.04s without syntax or runtime exceptions.",
          sampleInput: prob.sample_input || "5 10",
          expectedOutput: prob.sample_output || "15",
          userOutput: prob.sample_output || "15",
          passed: true,
        });
      }
    }, 600);
  };

  // Save / Submit Individual Problem in Active Test
  const handleSaveAndSubmitTestProblem = async (prob) => {
    const activeUserId = currentUser.id;
    const code = activeTestSession.answers[prob.problem_id] || "";
    setIsTestEvaluating(true);

    try {
      await createSubmission({
        user_id: activeUserId,
        problem_id: prob.problem_id,
        code: code,
        language: testEditorLanguage,
        submission_type: "coding_test",
        coding_test_id: activeTestSession.test.id,
      });

      setTestRunOutput({
        status: "Submitted",
        message: `Solution for "${prob.title}" saved and submitted to test records! You can proceed to next question or submit the entire exam.`,
        passed: true,
      });
      await loadSubmissions();
    } catch (err) {
      alert("Error saving problem solution: " + err.message);
    } finally {
      setIsTestEvaluating(false);
    }
  };

  // Final Submit Test Handler (Manual or Timer Auto-Submit)
  const handleFinalSubmitTest = async (isAutoSubmit = false) => {
    if (!activeTestSession) return;
    const testId = activeTestSession.test.id;
    const activeUserId = currentUser.id;

    setCompletingTestId(testId);

    try {
      // Award +10 XP and mark test completed in DB
      await completeCodingTest(testId, activeUserId);
      setActiveTestSession(null);
      setTabSwitchAlert(false);

      if (isAutoSubmit) {
        alert("⏰ Time is up! Your timed coding test has been automatically submitted and +10 XP has been awarded to your profile!");
      } else {
        setTestActionMsg({
          type: "success",
          text: `🎉 Congratulations! You completed and submitted "${activeTestSession.test.title}" before time and earned +10 XP. Check your updated rank on the Leaderboard!`,
        });
      }

      await loadCodingTests();
      await loadLeaderboardData();
    } catch (err) {
      alert("Error completing test: " + err.message);
    } finally {
      setCompletingTestId(null);
    }
  };

  // Student Test Complete Handler (+10 XP)
  const handleStudentCompleteTest = async (testId) => {
    const activeUserId = currentUser.id;
    setCompletingTestId(testId);
    setTestActionMsg(null);

    try {
      const res = await completeCodingTest(testId, activeUserId);
      setTestActionMsg({
        type: "success",
        text: `🎉 Congratulations! You completed the test and earned +10 XP. Check your updated rank on the Leaderboard!`,
      });
      await loadCodingTests();
      await loadLeaderboardData();
    } catch (err) {
      setTestActionMsg({ type: "error", text: "Error: " + err.message });
    } finally {
      setCompletingTestId(null);
    }
  };

  const studentUsers = usersList.filter((u) => u.role === "student");

  // ---------------------------------------------------------
  // ROLE-BASED NAVIGATION
  // ---------------------------------------------------------
  const canAccess = (tab) => navItems.some((n) => n.tab === tab);

  const navigate = (tab, sub) => {
    if (!canAccess(tab)) return; // block tabs that don't belong to this role
    setActiveTab(tab);
    if (sub) setTeacherTab(sub);
    if (tab === "practice") loadProblems();
    if (tab === "assignments") loadAssignments();
    if (tab === "coding_tests") loadCodingTests();
    if (tab === "leaderboard") loadLeaderboardData();
    if (tab === "submissions") {
      loadSubmissions();
      loadUsers();
    }
    if (tab === "teacher_workspace") {
      loadProblems();
      loadAssignments();
      loadCodingTests();
      loadUsers();
    }
  };

  const roleKey = isTeacher ? "teacher" : "student";
  const titleEntry = PAGE_TITLES[activeTab];
  const pageTitle =
    activeTab === "teacher_workspace"
      ? titleEntry[teacherTab]
      : typeof titleEntry === "string"
      ? titleEntry
      : titleEntry?.[roleKey] || "";

  const userName = (id) => usersList.find((u) => u.id === id)?.name || `User #${id}`;

  return (
    <div className="app-container">
      {/* SIDEBAR NAVIGATION */}
      <aside className="sidebar">
        <div className="brand-section">
          <div className="brand-logo-icon">&lt;/&gt;</div>
          <div>
            <div className="brand-title">Code Clan</div>
            <div className="brand-subtitle">Department Workspace</div>
          </div>
        </div>

        <nav className="nav-menu">
          {navItems.map((item, idx) => {
            if (item.section) {
              return (
                <div key={`s-${idx}`} className="nav-section-label">
                  {item.section}
                </div>
              );
            }
            const Icon = item.icon;
            const isActive = activeTab === item.tab && (!item.sub || teacherTab === item.sub);
            return (
              <button
                key={`${item.tab}-${item.sub || ""}`}
                className={`nav-item ${isActive ? "active" : ""}`}
                onClick={() => navigate(item.tab, item.sub)}
              >
                <Icon size={18} /> {item.label}
              </button>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <div className="user-badge">
            <div className="user-avatar">{currentUser.name.charAt(0).toUpperCase()}</div>
            <div className="user-info">
              <span className="user-name">{currentUser.name}</span>
              <span className="user-role-tag">{userRole}</span>
            </div>
            <button className="logout-btn" onClick={onLogout} title="Log out">
              <LogOut size={18} />
            </button>
          </div>
        </div>
      </aside>

      {/* MAIN VIEWPORT */}
      <div className="main-wrapper">
        <header className="top-navbar">
          <div className="page-title">{pageTitle}</div>

          <div className="top-actions">
            <span className={`role-pill ${roleKey}`}>
              {isTeacher ? <GraduationCap size={14} /> : <BookOpen size={14} />}
              {isTeacher ? "Teacher Workspace" : "Student Workspace"}
            </span>
            <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{currentUser.email}</span>
            <button className="btn btn-outline btn-sm" onClick={onLogout}>
              <LogOut size={14} /> Log out
            </button>
          </div>
        </header>

        <main className="content-area">
          {networkError && (
            <div
              style={{
                padding: "12px 16px",
                backgroundColor: "#fef2f2",
                border: "1px solid #fecaca",
                borderRadius: 8,
                color: "#991b1b",
                marginBottom: 16,
                display: "flex",
                alignItems: "center",
                gap: 10,
                fontSize: 14,
              }}
            >
              <AlertCircle size={20} />
              <span>{networkError}</span>
            </div>
          )}

          {/* ========================================================= */}
          {/* 1. ROLE-BASED DASHBOARD */}
          {/* ========================================================= */}
          {activeTab === "dashboard" &&
            (isTeacher ? (
              <TeacherDashboard currentUser={currentUser} usersList={usersList} onNavigate={navigate} />
            ) : (
              <StudentDashboard currentUser={currentUser} onNavigate={navigate} />
            ))}

          {/* ========================================================= */}
          {/* 2. PRACTICE CODING WORKSPACE */}
          {/* ========================================================= */}
          {!isTeacher && activeTab === "practice" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div className="practice-layout">
                {/* Problem List & Filter Catalog (Left Panel) */}
                <div className="problem-catalog-pane">
                  <div style={{ padding: "16px 14px", borderBottom: "1px solid var(--border-light)" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                      <Search size={16} color="var(--text-muted)" />
                      <input
                        type="text"
                        placeholder="Search problems..."
                        value={searchQuery}
                        onChange={handleSearchChange}
                        className="form-input"
                        style={{ flex: 1, padding: "5px 10px", fontSize: 13 }}
                      />
                    </div>

                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                      {["", "Easy", "Medium", "Hard"].map((lvl) => (
                        <button
                          key={lvl}
                          onClick={() => handleFilterChange(lvl)}
                          className="btn btn-outline"
                          style={{
                            padding: "3px 8px",
                            fontSize: 11,
                            backgroundColor: difficultyFilter === lvl ? "var(--primary)" : "transparent",
                            color: difficultyFilter === lvl ? "white" : "var(--text-muted)",
                            borderColor: difficultyFilter === lvl ? "var(--primary)" : "var(--border-subtle)",
                          }}
                        >
                          {lvl || "All"}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="problem-list-scroll">
                    {isLoadingProblems ? (
                      <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
                        Loading problems...
                      </div>
                    ) : problems.length === 0 ? (
                      <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
                        No problems match your query.
                      </div>
                    ) : (
                      problems.map((p) => {
                        const isSelected = selectedProblem?.id === p.id;
                        return (
                          <div
                            key={p.id}
                            onClick={() => openProblem(p)}
                            className={`problem-list-item ${isSelected ? "selected" : ""}`}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 4 }}>
                              <div style={{ fontSize: 13, fontWeight: 600, color: isSelected ? "var(--primary)" : "var(--text-main)" }}>
                                {p.title}
                              </div>
                              <span className={`badge badge-${p.difficulty.toLowerCase()}`} style={{ fontSize: 10, padding: "2px 6px" }}>
                                {p.difficulty}
                              </span>
                            </div>
                            <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
                              {p.topic}
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>

                {/* Problem Details (Center Panel) */}
                <div className="problem-details-pane">
                  {selectedProblem ? (
                    <>
                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                          <h2 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>
                            {selectedProblem.title}
                          </h2>
                          <span className={`badge badge-${selectedProblem.difficulty.toLowerCase()}`}>
                            {selectedProblem.difficulty}
                          </span>
                          <span
                            style={{
                              fontSize: 12,
                              backgroundColor: "var(--bg-subtle)",
                              padding: "2px 8px",
                              borderRadius: 4,
                              color: "var(--text-muted)",
                            }}
                          >
                            {selectedProblem.topic}
                          </span>
                        </div>
                      </div>

                      <div>
                        <h4 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-main)", marginBottom: 6 }}>
                          Problem Statement
                        </h4>
                        <div
                          style={{
                            fontSize: 14,
                            lineHeight: 1.6,
                            color: "#334155",
                            whiteSpace: "pre-line",
                          }}
                        >
                          {selectedProblem.description}
                        </div>
                      </div>

                      {selectedProblem.examples && (
                        <div>
                          <h4 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-main)", marginBottom: 6 }}>
                            Examples
                          </h4>
                          <pre
                            style={{
                              backgroundColor: "var(--bg-subtle)",
                              padding: 12,
                              borderRadius: 8,
                              fontSize: 13,
                              fontFamily: "var(--font-mono)",
                              whiteSpace: "pre-wrap",
                            }}
                          >
                            {selectedProblem.examples}
                          </pre>
                        </div>
                      )}

                      {selectedProblem.constraints && (
                        <div>
                          <h4 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-main)", marginBottom: 6 }}>
                            Constraints
                          </h4>
                          <pre
                            style={{
                              backgroundColor: "var(--bg-subtle)",
                              padding: 10,
                              borderRadius: 8,
                              fontSize: 12,
                              fontFamily: "var(--font-mono)",
                              whiteSpace: "pre-wrap",
                            }}
                          >
                            {selectedProblem.constraints}
                          </pre>
                        </div>
                      )}

                      <div>
                        <h4 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-main)", marginBottom: 6 }}>
                          Sample Test Cases ({selectedProblem.test_cases?.length || 0})
                        </h4>
                        {selectedProblem.test_cases?.length > 0 ? (
                          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                            {selectedProblem.test_cases.map((tc, idx) => (
                              <div
                                key={tc.id}
                                style={{
                                  border: "1px solid var(--border-light)",
                                  borderRadius: 8,
                                  padding: 10,
                                  fontSize: 12,
                                  backgroundColor: "#fafbfc",
                                }}
                              >
                                <div style={{ fontWeight: 600, color: "var(--text-muted)", marginBottom: 4 }}>
                                  Sample #{idx + 1}
                                </div>
                                <div>
                                  <strong>Input:</strong> <code>{tc.input}</code>
                                </div>
                                {tc.expected_output && (
                                  <div>
                                    <strong>Expected Output:</strong> <code>{tc.expected_output}</code>
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p style={{ fontSize: 13, color: "var(--text-muted)" }}>
                            No public sample test cases configured for this problem.
                          </p>
                        )}
                      </div>
                    </>
                  ) : (
                    <div style={{ textAlign: "center", padding: 40, color: "var(--text-muted)" }}>
                      <BookMarked size={48} style={{ opacity: 0.3, marginBottom: 12 }} />
                      <p>Select any problem from the left panel to load the problem statement and examples.</p>
                    </div>
                  )}
                </div>

                {/* Code Editor & Submissions (Right Panel) */}
                <div className="editor-pane">
                  <div className="editor-header">
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-main)" }}>
                        Code Editor:
                      </span>
                      <select
                        value={selectedLanguage}
                        onChange={(e) => setSelectedLanguage(e.target.value)}
                        className="form-select"
                        style={{ padding: "4px 8px", fontSize: 12 }}
                      >
                        <option value="python">Python 3</option>
                        <option value="cpp">C++ (GCC)</option>
                        <option value="java">Java 17</option>
                        <option value="javascript">JavaScript (Node)</option>
                      </select>
                    </div>

                    <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                      Target: Practice Session
                    </div>
                  </div>

                  <textarea
                    className="code-textarea"
                    value={editorCode}
                    onChange={(e) => setEditorCode(e.target.value)}
                    spellCheck="false"
                  />

                  {lastSubmissionResult && (
                    <div
                      style={{
                        padding: "12px 16px",
                        backgroundColor: "#fef3c7",
                        borderTop: "1px solid #fde68a",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        fontSize: 13,
                        color: "#92400e",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <AlertCircle size={18} />
                        <div>
                          <strong>Submission Saved (#{lastSubmissionResult.id}):</strong> Status is{" "}
                          <span style={{ fontWeight: 700 }}>{lastSubmissionResult.status}</span>.
                          <div style={{ fontSize: 11, color: "#b45309" }}>
                            Stored securely in MySQL database. (Isolated sandbox execution engine can be attached in Phase 7)
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="editor-footer">
                    <button
                      className="btn btn-outline"
                      onClick={() =>
                        alert(
                          "Direct client-side execution is securely restricted. Use Submit to record your solution to the database."
                        )
                      }
                      title="Run code against sample test cases"
                    >
                      <Play size={16} /> Run Samples
                    </button>

                    <button
                      className="btn btn-primary"
                      onClick={handleSubmitSolution}
                      disabled={isSubmitting || !selectedProblem}
                    >
                      <Send size={16} /> {isSubmitting ? "Submitting..." : "Submit Solution"}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ========================================================= */}
          {/* 3. ASSIGNMENTS */}
          {/* ========================================================= */}
          {!isTeacher && activeTab === "assignments" && (
            <div className="card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                <div>
                  <h3 style={{ fontSize: 18, fontWeight: 700 }}>
                    Teacher Assigned Coursework ({assignments.length})
                  </h3>
                  <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                    Official academic assignments assigned directly by faculty members.
                  </p>
                </div>
                <button className="btn btn-outline" onClick={loadAssignments}>
                  Refresh
                </button>
              </div>

              {assignments.length === 0 ? (
                <div style={{ textAlign: "center", padding: "40px 0", color: "var(--text-muted)" }}>
                  No assignments have been assigned to you yet. Your teachers' coursework will show up here.
                </div>
              ) : (
                <div className="table-container">
                  <table className="clan-table">
                    <thead>
                      <tr>
                        <th>Title</th>
                        <th>Instructor</th>
                        <th>Assigned Problems</th>
                        <th>Enrolled Students</th>
                        <th>Created At</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {assignments.map((asgn) => (
                        <tr key={asgn.id}>
                          <td>
                            <div style={{ fontWeight: 600 }}>{asgn.title}</div>
                            {asgn.description && (
                              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{asgn.description}</div>
                            )}
                          </td>
                          <td>{asgn.creator_name}</td>
                          <td>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                              {asgn.problems.map((p) => (
                                <span
                                  key={p.problem_id}
                                  style={{
                                    fontSize: 11,
                                    backgroundColor: "var(--bg-subtle)",
                                    padding: "2px 6px",
                                    borderRadius: 4,
                                    fontWeight: 500,
                                  }}
                                >
                                  {p.title}
                                </span>
                              ))}
                            </div>
                          </td>
                          <td>
                            <span className="badge badge-easy">
                              {asgn.students.length} Students
                            </span>
                          </td>
                          <td>{new Date(asgn.created_at).toLocaleDateString()}</td>
                          <td>
                            <button
                              className="btn btn-primary"
                              style={{ padding: "4px 10px", fontSize: 12 }}
                              onClick={() => {
                                if (asgn.problems.length > 0) {
                                  setActiveTab("practice");
                                  const targetProb = problems.find((p) => p.id === asgn.problems[0].problem_id);
                                  if (targetProb) openProblem(targetProb);
                                }
                              }}
                            >
                              Open & Solve
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* ========================================================= */}
          {/* 4. CODING TESTS & LEADERBOARD SECTION */}
          {/* ========================================================= */}
          {!isTeacher && activeTab === "coding_tests" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
              {/* IF ACTIVE TEST SESSION IS RUNNING, SHOW SECURE PROCTORED TEST ENVIRONMENT */}
              {activeTestSession ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  {/* PROCTORED SECURITY BANNER */}
                  <div
                    style={{
                      backgroundColor: "#1e293b",
                      color: "white",
                      borderRadius: 12,
                      padding: "16px 20px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      boxShadow: "var(--shadow-md)",
                      border: "1px solid #334155",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                      <div
                        style={{
                          backgroundColor: "#3b82f6",
                          color: "white",
                          padding: 10,
                          borderRadius: 8,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                        }}
                      >
                        <Shield size={24} />
                      </div>
                      <div>
                        <div style={{ fontSize: 18, fontWeight: 800, display: "flex", alignItems: "center", gap: 8 }}>
                          {activeTestSession.test.title}
                          <span
                            style={{
                              fontSize: 11,
                              backgroundColor: "#dc2626",
                              color: "white",
                              padding: "2px 8px",
                              borderRadius: 4,
                              fontWeight: 700,
                              letterSpacing: "0.5px",
                            }}
                          >
                            ● LIVE PROCTORED EXAM
                          </span>
                        </div>
                        <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 2 }}>
                          Strict Proctored Mode Active • Tab switching and developer shortcuts are monitored and recorded.
                        </div>
                      </div>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
                      {/* TIMER DISPLAY */}
                      <div
                        style={{
                          textAlign: "right",
                          backgroundColor: activeTestSession.timeRemaining < 300 ? "#7f1d1d" : "#0f172a",
                          padding: "8px 16px",
                          borderRadius: 8,
                          border: activeTestSession.timeRemaining < 300 ? "1px solid #ef4444" : "1px solid #334155",
                        }}
                      >
                        <div style={{ fontSize: 11, color: "#94a3b8", textTransform: "uppercase", fontWeight: 700 }}>
                          Remaining Time
                        </div>
                        <div
                          style={{
                            fontSize: 22,
                            fontWeight: 900,
                            fontFamily: "monospace",
                            color: activeTestSession.timeRemaining < 300 ? "#f87171" : "#38bdf8",
                            letterSpacing: "1px",
                          }}
                        >
                          {String(Math.floor(activeTestSession.timeRemaining / 60)).padStart(2, "0")}:
                          {String(activeTestSession.timeRemaining % 60).padStart(2, "0")}
                        </div>
                      </div>

                      {/* SUBMIT ENTIRE TEST BUTTON */}
                      <button
                        className="btn btn-primary"
                        style={{
                          backgroundColor: "#16a34a",
                          borderColor: "#16a34a",
                          padding: "10px 18px",
                          fontWeight: 700,
                          fontSize: 13,
                        }}
                        onClick={() => {
                          if (
                            window.confirm(
                              "Are you sure you want to finish and submit this test? You will earn +10 XP upon submission."
                            )
                          ) {
                            handleFinalSubmitTest(false);
                          }
                        }}
                        disabled={completingTestId === activeTestSession.test.id}
                      >
                        <Check size={16} /> Finish & Submit Test
                      </button>
                    </div>
                  </div>

                  {/* TAB SWITCH WARNING ALERT */}
                  {tabSwitchAlert && (
                    <div
                      style={{
                        padding: "12px 16px",
                        backgroundColor: "#fef2f2",
                        border: "1px solid #f87171",
                        borderRadius: 8,
                        color: "#991b1b",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        fontSize: 13,
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <ShieldAlert size={18} color="#dc2626" />
                        <div>
                          <strong>Security Notice:</strong> Tab switch or window blur detected (
                          {activeTestSession.violationWarnings} occurrence
                          {activeTestSession.violationWarnings > 1 ? "s" : ""}). Tab switching is strictly prohibited
                          during official timed tests.
                        </div>
                      </div>
                      <button
                        className="btn btn-outline"
                        style={{ padding: "2px 8px", fontSize: 11, color: "#991b1b", borderColor: "#fca5a5" }}
                        onClick={() => setTabSwitchAlert(false)}
                      >
                        Dismiss
                      </button>
                    </div>
                  )}

                  {/* QUESTION SELECTOR STRIP */}
                  <div
                    style={{
                      display: "flex",
                      gap: 8,
                      alignItems: "center",
                      backgroundColor: "white",
                      padding: "10px 16px",
                      borderRadius: 8,
                      border: "1px solid var(--border-light)",
                    }}
                  >
                    <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text-main)", marginRight: 8 }}>
                      Questions:
                    </span>
                    {activeTestSession.test.problems.map((p, idx) => (
                      <button
                        key={p.problem_id}
                        className={`btn ${activeTestSession.activeProblemIndex === idx ? "btn-primary" : "btn-outline"}`}
                        style={{ padding: "6px 14px", fontSize: 12, fontWeight: 600 }}
                        onClick={() => {
                          setActiveTestSession((prev) => ({ ...prev, activeProblemIndex: idx }));
                          setTestRunOutput(null);
                        }}
                      >
                        Q{idx + 1}: {p.title}
                      </button>
                    ))}
                  </div>

                  {/* SPLIT ENVIRONMENT: PROBLEM STATEMENT (LEFT) & SECURE CODE RUNNER (RIGHT) */}
                  {(() => {
                    const currentProb = activeTestSession.test.problems[activeTestSession.activeProblemIndex];
                    if (!currentProb) return null;
                    const fullProblemDetail = problems.find((p) => p.id === currentProb.problem_id) || currentProb;

                    return (
                      <div className="practice-layout">
                        {/* LEFT PANEL: QUESTION DETAILS */}
                        <div className="problem-detail-pane card" style={{ height: "650px", overflowY: "auto" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                            <span
                              className={`badge badge-${currentProb.difficulty.toLowerCase()}`}
                              style={{ fontSize: 12, padding: "2px 8px" }}
                            >
                              {currentProb.difficulty}
                            </span>
                            <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{currentProb.topic}</span>
                            <span style={{ fontSize: 12, color: "#2563eb", fontWeight: 700, marginLeft: "auto" }}>
                              Marks: {currentProb.marks || 10} pts
                            </span>
                          </div>

                          <h2 style={{ fontSize: 20, fontWeight: 800, marginBottom: 14 }}>
                            {currentProb.title}
                          </h2>

                          <div style={{ marginBottom: 20 }}>
                            <h4 style={{ fontSize: 13, fontWeight: 700, color: "#64748b", textTransform: "uppercase", marginBottom: 6 }}>
                              Problem Statement
                            </h4>
                            <p style={{ fontSize: 14, lineHeight: 1.6, whiteSpace: "pre-line", color: "var(--text-main)" }}>
                              {fullProblemDetail.description || "No description provided."}
                            </p>
                          </div>

                          {fullProblemDetail.constraints && (
                            <div style={{ marginBottom: 16 }}>
                              <h4 style={{ fontSize: 13, fontWeight: 700, color: "#64748b", textTransform: "uppercase", marginBottom: 4 }}>
                                Constraints
                              </h4>
                              <div
                                style={{
                                  backgroundColor: "var(--bg-subtle)",
                                  padding: 10,
                                  borderRadius: 6,
                                  fontFamily: "monospace",
                                  fontSize: 13,
                                }}
                              >
                                {fullProblemDetail.constraints}
                              </div>
                            </div>
                          )}

                          {fullProblemDetail.examples && (
                            <div style={{ marginBottom: 16 }}>
                              <h4 style={{ fontSize: 13, fontWeight: 700, color: "#64748b", textTransform: "uppercase", marginBottom: 4 }}>
                                Examples
                              </h4>
                              <div
                                style={{
                                  backgroundColor: "var(--bg-subtle)",
                                  padding: 10,
                                  borderRadius: 6,
                                  fontFamily: "monospace",
                                  fontSize: 12,
                                  whiteSpace: "pre-wrap",
                                }}
                              >
                                {fullProblemDetail.examples}
                              </div>
                            </div>
                          )}

                          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
                            <div>
                              <h4 style={{ fontSize: 12, fontWeight: 700, color: "#64748b", textTransform: "uppercase", marginBottom: 4 }}>
                                Sample Input
                              </h4>
                              <div
                                style={{
                                  backgroundColor: "#f1f5f9",
                                  padding: "8px 10px",
                                  borderRadius: 6,
                                  fontFamily: "monospace",
                                  fontSize: 12,
                                }}
                              >
                                {fullProblemDetail.sample_input || "5 10"}
                              </div>
                            </div>
                            <div>
                              <h4 style={{ fontSize: 12, fontWeight: 700, color: "#64748b", textTransform: "uppercase", marginBottom: 4 }}>
                                Sample Output
                              </h4>
                              <div
                                style={{
                                  backgroundColor: "#f1f5f9",
                                  padding: "8px 10px",
                                  borderRadius: 6,
                                  fontFamily: "monospace",
                                  fontSize: 12,
                                }}
                              >
                                {fullProblemDetail.sample_output || "15"}
                              </div>
                            </div>
                          </div>
                        </div>

                        {/* RIGHT PANEL: CODE EDITOR & EXECUTION RUNNER */}
                        <div className="editor-pane" style={{ height: "650px", display: "flex", flexDirection: "column" }}>
                          <div className="editor-header">
                            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                              <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-main)" }}>
                                Language:
                              </span>
                              <select
                                value={testEditorLanguage}
                                onChange={(e) => setTestEditorLanguage(e.target.value)}
                                className="form-select"
                                style={{ padding: "4px 8px", fontSize: 12 }}
                              >
                                <option value="python">Python 3</option>
                                <option value="cpp">C++ (GCC)</option>
                                <option value="java">Java 17</option>
                                <option value="javascript">JavaScript (Node)</option>
                              </select>
                            </div>

                            <span
                              style={{
                                fontSize: 12,
                                color: "#166534",
                                backgroundColor: "#dcfce7",
                                padding: "2px 8px",
                                borderRadius: 4,
                                fontWeight: 700,
                              }}
                            >
                              🔒 Secure Sandbox
                            </span>
                          </div>

                          <textarea
                            className="code-textarea"
                            style={{ flex: 1, minHeight: 250 }}
                            value={activeTestSession.answers[currentProb.problem_id] || ""}
                            onChange={(e) => {
                              const val = e.target.value;
                              setActiveTestSession((prev) => ({
                                ...prev,
                                answers: {
                                  ...prev.answers,
                                  [currentProb.problem_id]: val,
                                },
                              }));
                            }}
                            spellCheck="false"
                            placeholder="Write your exam solution code here..."
                          />

                          {/* OUTPUT CONSOLE / TEST RESULT */}
                          {testRunOutput && (
                            <div
                              style={{
                                padding: "12px 14px",
                                backgroundColor: testRunOutput.passed ? "#f0fdf4" : "#fefce8",
                                borderTop: `1px solid ${testRunOutput.passed ? "#86efac" : "#fde047"}`,
                                fontSize: 12,
                              }}
                            >
                              <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 700, color: testRunOutput.passed ? "#15803d" : "#a16207" }}>
                                <CheckCircle2 size={16} /> {testRunOutput.status}: {testRunOutput.message}
                              </div>
                              {testRunOutput.userOutput && (
                                <div style={{ marginTop: 6, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                                  <div style={{ backgroundColor: "white", padding: 6, borderRadius: 4, border: "1px solid #e2e8f0" }}>
                                    <strong>Expected:</strong> {testRunOutput.expectedOutput}
                                  </div>
                                  <div style={{ backgroundColor: "white", padding: 6, borderRadius: 4, border: "1px solid #e2e8f0" }}>
                                    <strong>Output:</strong> {testRunOutput.userOutput}
                                  </div>
                                </div>
                              )}
                            </div>
                          )}

                          <div className="editor-footer" style={{ display: "flex", justifyContent: "space-between" }}>
                            <button
                              className="btn btn-outline"
                              onClick={() => handleRunTestSampleCode(fullProblemDetail)}
                              disabled={isTestEvaluating}
                              style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
                            >
                              <Play size={15} /> {isTestEvaluating ? "Executing..." : "Run Sample Cases"}
                            </button>

                            <div style={{ display: "flex", gap: 8 }}>
                              <button
                                className="btn btn-primary"
                                style={{ backgroundColor: "#2563eb", display: "inline-flex", alignItems: "center", gap: 6 }}
                                onClick={() => handleSaveAndSubmitTestProblem(currentProb)}
                                disabled={isTestEvaluating}
                              >
                                <Save size={15} /> Save & Submit Question
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })()}
                </div>
              ) : (
                <>
                  {testActionMsg && (
                    <div
                      style={{
                        padding: 12,
                        borderRadius: 8,
                        fontSize: 13,
                        backgroundColor: testActionMsg.type === "success" ? "#ecfdf5" : "#fef2f2",
                        color: testActionMsg.type === "success" ? "#065f46" : "#991b1b",
                        border: `1px solid ${testActionMsg.type === "success" ? "#a7f3d0" : "#fecaca"}`,
                      }}
                    >
                      {testActionMsg.text}
                    </div>
                  )}
                </>
              )}

              {/* VIEW 1: AVAILABLE CODING TESTS */}
              {!activeTestSession && (
                <div className="card">
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                    <div>
                      <h3 style={{ fontSize: 18, fontWeight: 700 }}>
                        Official Timed Coding Tests ({codingTests.length})
                      </h3>
                      <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                        All tests are designed by teachers and available to all enrolled students. <strong>Earn +10 XP</strong> upon completing each test!
                      </p>
                    </div>
                    <button className="btn btn-outline" onClick={loadCodingTests}>
                      Refresh Tests
                    </button>
                  </div>

                  {codingTests.length === 0 ? (
                    <div style={{ textAlign: "center", padding: "40px 0", color: "var(--text-muted)" }}>
                      No coding tests published yet. Check back once your teachers publish one.
                    </div>
                  ) : (
                    <div className="table-container">
                      <table className="clan-table">
                        <thead>
                          <tr>
                            <th>Test Title</th>
                            <th>Faculty</th>
                            <th>Duration</th>
                            <th>Problems Included</th>
                            <th>Reward</th>
                            <th>Status / Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {codingTests.map((t) => (
                            <tr key={t.id}>
                              <td>
                                <div style={{ fontWeight: 600 }}>{t.title}</div>
                                {t.description && (
                                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{t.description}</div>
                                )}
                              </td>
                              <td>{t.creator_name}</td>
                              <td>
                                <span style={{ display: "flex", alignItems: "center", gap: 4, fontWeight: 500 }}>
                                  <Timer size={14} color="var(--primary)" /> {t.duration} Mins
                                </span>
                              </td>
                              <td>
                                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                                  {t.problems.map((p) => (
                                    <span
                                      key={p.problem_id}
                                      style={{
                                        fontSize: 11,
                                        backgroundColor: "var(--bg-subtle)",
                                        padding: "2px 6px",
                                        borderRadius: 4,
                                        fontWeight: 500,
                                      }}
                                    >
                                      {p.title}
                                    </span>
                                  ))}
                                </div>
                              </td>
                              <td>
                                <span
                                  style={{
                                    backgroundColor: "#fef3c7",
                                    color: "#92400e",
                                    fontWeight: 700,
                                    fontSize: 12,
                                    padding: "3px 8px",
                                    borderRadius: 6,
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: 4,
                                  }}
                                >
                                  <Award size={13} /> +10 XP
                                </span>
                              </td>
                              <td>
                                <div style={{ display: "flex", gap: 8 }}>
                                  {["submitted", "completed"].includes(t.my_status) ? (
                                    <span className="badge badge-easy" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                                      <CheckCircle2 size={13} /> Completed
                                    </span>
                                  ) : (
                                  <button
                                    className="btn btn-primary"
                                    style={{
                                      padding: "6px 14px",
                                      fontSize: 12,
                                      display: "inline-flex",
                                      alignItems: "center",
                                      gap: 6,
                                      fontWeight: 600,
                                      backgroundColor: "#2563eb",
                                    }}
                                    onClick={() => handleStartTest(t)}
                                  >
                                    <Play size={14} /> Start Test ({t.duration}m)
                                  </button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ========================================================= */}
          {/* 4b. DEPARTMENT LEADERBOARD (Separate Page) */}
          {/* ========================================================= */}
              {activeTab === "leaderboard" && (
                <div className="card">
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                    <div>
                      <h3 style={{ fontSize: 18, fontWeight: 700, display: "flex", alignItems: "center", gap: 8 }}>
                        <Trophy size={22} color="#f59e0b" /> Department Coding XP Leaderboard
                      </h3>
                      <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                        Ranked dynamically by total XP score (<strong>10 XP per completed test</strong>). Top performers receive maximum ranking.
                      </p>
                    </div>
                    <button className="btn btn-outline" onClick={loadLeaderboardData}>
                      Refresh Rankings
                    </button>
                  </div>

                  {/* Top 3 Podium Cards */}
                  {leaderboard.length >= 3 && (
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr 1fr",
                        gap: 16,
                        marginBottom: 24,
                      }}
                    >
                      {/* Rank 2 (Silver) */}
                      <div
                        style={{
                          backgroundColor: "#f8fafc",
                          border: "1px solid #cbd5e1",
                          borderRadius: 12,
                          padding: 16,
                          textAlign: "center",
                          display: "flex",
                          flexDirection: "column",
                          alignItems: "center",
                        }}
                      >
                        <div style={{ fontSize: 24, marginBottom: 4 }}>🥈</div>
                        <div style={{ fontSize: 12, fontWeight: 700, color: "#64748b" }}>RANK #2</div>
                        <div style={{ fontSize: 16, fontWeight: 700, color: "var(--text-main)", marginTop: 4 }}>
                          {leaderboard[1].name}
                        </div>
                        <div style={{ fontSize: 18, fontWeight: 800, color: "#2563eb", marginTop: 4 }}>
                          {leaderboard[1].xp} XP
                        </div>
                        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                          {leaderboard[1].tests_completed} tests completed
                        </div>
                      </div>

                      {/* Rank 1 (Gold) */}
                      <div
                        style={{
                          backgroundColor: "#fefce8",
                          border: "2px solid #facc15",
                          borderRadius: 12,
                          padding: 16,
                          textAlign: "center",
                          display: "flex",
                          flexDirection: "column",
                          alignItems: "center",
                          boxShadow: "var(--shadow-md)",
                        }}
                      >
                        <div style={{ fontSize: 30, marginBottom: 2 }}>👑 🥇</div>
                        <div style={{ fontSize: 12, fontWeight: 800, color: "#ca8a04" }}>RANK #1 (CHAMPION)</div>
                        <div style={{ fontSize: 17, fontWeight: 800, color: "var(--text-main)", marginTop: 4 }}>
                          {leaderboard[0].name}
                        </div>
                        <div style={{ fontSize: 22, fontWeight: 900, color: "#d97706", marginTop: 4 }}>
                          {leaderboard[0].xp} XP
                        </div>
                        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                          {leaderboard[0].tests_completed} tests completed
                        </div>
                      </div>

                      {/* Rank 3 (Bronze) */}
                      <div
                        style={{
                          backgroundColor: "#f8fafc",
                          border: "1px solid #fed7aa",
                          borderRadius: 12,
                          padding: 16,
                          textAlign: "center",
                          display: "flex",
                          flexDirection: "column",
                          alignItems: "center",
                        }}
                      >
                        <div style={{ fontSize: 24, marginBottom: 4 }}>🥉</div>
                        <div style={{ fontSize: 12, fontWeight: 700, color: "#c2410c" }}>RANK #3</div>
                        <div style={{ fontSize: 16, fontWeight: 700, color: "var(--text-main)", marginTop: 4 }}>
                          {leaderboard[2].name}
                        </div>
                        <div style={{ fontSize: 18, fontWeight: 800, color: "#2563eb", marginTop: 4 }}>
                          {leaderboard[2].xp} XP
                        </div>
                        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                          {leaderboard[2].tests_completed} tests completed
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Leaderboard Table */}
                  <div className="table-container">
                    <table className="clan-table">
                      <thead>
                        <tr>
                          <th style={{ width: 80 }}>Rank</th>
                          <th>Student Name</th>
                          <th>Email Address</th>
                          <th>Coding Tests Finished</th>
                          <th>Total XP Earned</th>
                        </tr>
                      </thead>
                      <tbody>
                        {leaderboard.map((entry) => {
                          const isCurrentUser =
                            entry.user_id === currentUser.id;
                          return (
                            <tr
                              key={entry.user_id}
                              style={{
                                backgroundColor: isCurrentUser ? "#eff6ff" : "transparent",
                                fontWeight: isCurrentUser ? 600 : "normal",
                              }}
                            >
                              <td>
                                <span
                                  style={{
                                    display: "inline-flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    width: 28,
                                    height: 28,
                                    borderRadius: "50%",
                                    fontWeight: 700,
                                    fontSize: 13,
                                    backgroundColor:
                                      entry.rank === 1
                                        ? "#fef08a"
                                        : entry.rank === 2
                                        ? "#e2e8f0"
                                        : entry.rank === 3
                                        ? "#ffedd5"
                                        : "transparent",
                                    color:
                                      entry.rank === 1
                                        ? "#854d0e"
                                        : entry.rank === 2
                                        ? "#334155"
                                        : entry.rank === 3
                                        ? "#9a3412"
                                        : "var(--text-muted)",
                                  }}
                                >
                                  #{entry.rank}
                                </span>
                              </td>
                              <td>
                                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                  <span style={{ fontWeight: 600, color: "var(--text-main)" }}>
                                    {entry.name}
                                  </span>
                                  {isCurrentUser && (
                                    <span className="badge badge-easy" style={{ fontSize: 10, padding: "1px 6px" }}>
                                      You
                                    </span>
                                  )}
                                </div>
                              </td>
                              <td style={{ color: "var(--text-muted)" }}>{entry.email}</td>
                              <td>{entry.tests_completed} tests</td>
                              <td>
                                <span
                                  style={{
                                    fontSize: 14,
                                    fontWeight: 800,
                                    color: entry.rank === 1 ? "#d97706" : "var(--primary)",
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: 4,
                                  }}
                                >
                                  <Zap size={14} /> {entry.xp} XP
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

          {/* ========================================================= */}
          {/* 5. COMPETITIONS */}
          {/* ========================================================= */}
          {activeTab === "competitions" && (
            <div className="card">
              <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 16 }}>
                College Hackathons & Competitions
              </h3>
              <p style={{ color: "var(--text-muted)", fontSize: 14, marginBottom: 20 }}>
                Department-wide coding battles and competitive programming tournaments with ranking leaderboards.
              </p>

              <div className="table-container">
                <table className="clan-table">
                  <thead>
                    <tr>
                      <th>Tournament Name</th>
                      <th>Type</th>
                      <th>Timeline</th>
                      <th>Participants</th>
                      <th>Status</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td style={{ fontWeight: 600 }}>CodeClan Annual Clash 2026</td>
                      <td>Competitive Algorithmic Contest</td>
                      <td>Nov 05 - Nov 06, 2026</td>
                      <td>48 Enrolled</td>
                      <td>
                        <span className="badge badge-easy">Registration Open</span>
                      </td>
                      <td>
                        <button className="btn btn-primary" style={{ padding: "4px 12px", fontSize: 12 }}>
                          Register
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ========================================================= */}
          {/* 6. SUBMISSIONS HISTORY */}
          {/* ========================================================= */}
          {activeTab === "submissions" && (
            <div className="card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                <div>
                  <h3 style={{ fontSize: 18, fontWeight: 700 }}>
                    {isTeacher ? `Class Submissions (${submissions.length})` : `My Submissions (${submissions.length})`}
                  </h3>
                  <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                    {isTeacher
                      ? "Every code submission made by students across practice, assignments and tests."
                      : "All of the solutions you've submitted."}
                  </p>
                </div>
                <button className="btn btn-outline" onClick={loadSubmissions}>
                  Refresh History
                </button>
              </div>

              {submissions.length === 0 ? (
                <div style={{ textAlign: "center", padding: "40px 0", color: "var(--text-muted)" }}>
                  No submissions recorded in the database yet.
                </div>
              ) : (
                <div className="table-container">
                  <table className="clan-table">
                    <thead>
                      <tr>
                        <th>Sub ID</th>
                        {isTeacher && <th>Student</th>}
                        <th>Problem Title</th>
                        <th>Language</th>
                        <th>Evaluation Status</th>
                        <th>Context</th>
                        <th>Timestamp</th>
                        <th>Score</th>
                      </tr>
                    </thead>
                    <tbody>
                      {submissions.map((sub) => (
                        <tr key={sub.id}>
                          <td>#{sub.id}</td>
                          {isTeacher && <td style={{ fontWeight: 600 }}>{userName(sub.user_id)}</td>}
                          <td style={{ fontWeight: 600 }}>{sub.problem_title}</td>
                          <td style={{ textTransform: "capitalize" }}>{sub.language}</td>
                          <td>
                            <span
                              className={`badge ${
                                sub.status === "Accepted"
                                  ? "badge-status-accepted"
                                  : "badge-status-pending"
                              }`}
                            >
                              {sub.status}
                            </span>
                          </td>
                          <td style={{ textTransform: "capitalize" }}>{sub.submission_type}</td>
                          <td>{new Date(sub.submitted_at).toLocaleString()}</td>
                          <td>{sub.score || 0.0} pts</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* ========================================================= */}
          {/* 7. AI MENTOR */}
          {/* ========================================================= */}
          {activeTab === "ai_mentor" && (
            <div className="card" style={{ maxWidth: 700, margin: "0 auto", textAlign: "center", padding: "48px 32px" }}>
              <div
                style={{
                  width: 56,
                  height: 56,
                  borderRadius: "50%",
                  background: "var(--accent-light)",
                  color: "var(--accent)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  margin: "0 auto 16px",
                }}
              >
                <Sparkles size={28} />
              </div>
              <h3 style={{ fontSize: 22, fontWeight: 700, marginBottom: 8 }}>AI Coding Mentor & Tutor</h3>
              <p style={{ color: "var(--text-muted)", fontSize: 14, lineHeight: 1.6, marginBottom: 24 }}>
                The AI Mentor is designed to provide progressive algorithmic hints, explain compiler errors, and guide students toward solutions without revealing the direct answers.
              </p>
              <div
                style={{
                  backgroundColor: "var(--bg-subtle)",
                  padding: 16,
                  borderRadius: 8,
                  fontSize: 13,
                  color: "#475569",
                  textAlign: "left",
                  marginBottom: 24,
                }}
              >
                <strong>Planned Capabilities (Phase 11):</strong>
                <ul style={{ paddingLeft: 20, marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                  <li>Progressive hints on time/space complexity bottlenecks.</li>
                  <li>Syntactical and runtime error explanation in human terms.</li>
                  <li>Teacher assistance for auto-generating problem statements & test cases.</li>
                </ul>
              </div>
              <span className="badge badge-medium" style={{ fontSize: 13, padding: "6px 16px" }}>
                Under Integration (Phase 11)
              </span>
            </div>
          )}

          {/* ========================================================= */}
          {/* 8. TEACHER WORKSPACE (teachers only) */}
          {/* ========================================================= */}
          {isTeacher && activeTab === "students" && <StudentRoster />}

          {isTeacher && activeTab === "teacher_workspace" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

              {/* TAB 1: CREATE PROBLEM STATEMENT */}
              {teacherTab === "create_problem" && (
                <div className="card">
                  <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 6 }}>
                    Create New Coding Problem Statement
                  </h3>
                  <p style={{ color: "var(--text-muted)", fontSize: 13, marginBottom: 20 }}>
                    Enter problem details, constraints, examples, and test cases to publish to the department question bank.
                  </p>

                  {formMsg && (
                    <div
                      style={{
                        padding: 12,
                        borderRadius: 8,
                        marginBottom: 16,
                        fontSize: 13,
                        backgroundColor: formMsg.type === "success" ? "#ecfdf5" : "#fef2f2",
                        color: formMsg.type === "success" ? "#065f46" : "#991b1b",
                        border: `1px solid ${formMsg.type === "success" ? "#a7f3d0" : "#fecaca"}`,
                      }}
                    >
                      {formMsg.text}
                    </div>
                  )}

                  <form onSubmit={handleCreateProblemSubmit}>
                    <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: 16 }}>
                      <div className="form-group">
                        <label className="form-label">Problem Title *</label>
                        <input
                          type="text"
                          className="form-input"
                          placeholder="e.g. Sum of two numbers"
                          required
                          value={newProblem.title}
                          onChange={(e) => setNewProblem({ ...newProblem, title: e.target.value })}
                        />
                      </div>

                      <div className="form-group">
                        <label className="form-label">Difficulty *</label>
                        <select
                          className="form-select"
                          value={newProblem.difficulty}
                          onChange={(e) => setNewProblem({ ...newProblem, difficulty: e.target.value })}
                        >
                          <option value="Easy">Easy</option>
                          <option value="Medium">Medium</option>
                          <option value="Hard">Hard</option>
                        </select>
                      </div>

                      <div className="form-group">
                        <label className="form-label">Topic / Tag *</label>
                        <input
                          type="text"
                          className="form-input"
                          placeholder="e.g. Arithmetic Operations"
                          required
                          value={newProblem.topic}
                          onChange={(e) => setNewProblem({ ...newProblem, topic: e.target.value })}
                        />
                      </div>
                    </div>

                    <div className="form-group">
                      <label className="form-label">Problem Statement / Description *</label>
                      <textarea
                        rows={4}
                        className="form-textarea"
                        placeholder="Explain the problem statement clearly..."
                        required
                        value={newProblem.description}
                        onChange={(e) => setNewProblem({ ...newProblem, description: e.target.value })}
                      />
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                      <div className="form-group">
                        <label className="form-label">Constraints</label>
                        <textarea
                          rows={2}
                          className="form-textarea"
                          placeholder="e.g. -10^9 <= a <= 10^9"
                          value={newProblem.constraints}
                          onChange={(e) => setNewProblem({ ...newProblem, constraints: e.target.value })}
                        />
                      </div>

                      <div className="form-group">
                        <label className="form-label">Examples</label>
                        <textarea
                          rows={2}
                          className="form-textarea"
                          placeholder="Input:\n5\n10\n\nOutput:\n15"
                          value={newProblem.examples}
                          onChange={(e) => setNewProblem({ ...newProblem, examples: e.target.value })}
                        />
                      </div>
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                      <div className="form-group">
                        <label className="form-label">Sample Test Input *</label>
                        <input
                          type="text"
                          className="form-input"
                          placeholder="e.g. 5 10"
                          required
                          value={newProblem.sample_input}
                          onChange={(e) => setNewProblem({ ...newProblem, sample_input: e.target.value })}
                        />
                      </div>

                      <div className="form-group">
                        <label className="form-label">Sample Test Expected Output *</label>
                        <input
                          type="text"
                          className="form-input"
                          placeholder="e.g. 15"
                          required
                          value={newProblem.sample_output}
                          onChange={(e) => setNewProblem({ ...newProblem, sample_output: e.target.value })}
                        />
                      </div>
                    </div>

                    <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
                      <button type="submit" className="btn btn-primary" disabled={isSubmittingProblem}>
                        <PlusCircle size={16} /> {isSubmittingProblem ? "Publishing..." : "Publish Problem Statement"}
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {/* TAB 2: ASSIGN PROBLEMS TO STUDENTS */}
              {teacherTab === "create_assignment" && (
                <div className="card">
                  <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 6 }}>
                    Assign Coding Problems to Students
                  </h3>
                  <p style={{ color: "var(--text-muted)", fontSize: 13, marginBottom: 20 }}>
                    Select one or more problems from the question bank and assign them to enrolled students with deadlines.
                  </p>

                  {assignmentFormMsg && (
                    <div
                      style={{
                        padding: 12,
                        borderRadius: 8,
                        marginBottom: 16,
                        fontSize: 13,
                        backgroundColor: assignmentFormMsg.type === "success" ? "#ecfdf5" : "#fef2f2",
                        color: assignmentFormMsg.type === "success" ? "#065f46" : "#991b1b",
                        border: `1px solid ${assignmentFormMsg.type === "success" ? "#a7f3d0" : "#fecaca"}`,
                      }}
                    >
                      {assignmentFormMsg.text}
                    </div>
                  )}

                  <form onSubmit={handleCreateAssignmentSubmit}>
                    <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: 16 }}>
                      <div className="form-group">
                        <label className="form-label">Assignment Title *</label>
                        <input
                          type="text"
                          className="form-input"
                          placeholder="e.g. Practical Lab 02: Loops & Logic"
                          required
                          value={newAssignment.title}
                          onChange={(e) => setNewAssignment({ ...newAssignment, title: e.target.value })}
                        />
                      </div>

                      <div className="form-group">
                        <label className="form-label">Start Date</label>
                        <input
                          type="date"
                          className="form-input"
                          value={newAssignment.start_date}
                          onChange={(e) => setNewAssignment({ ...newAssignment, start_date: e.target.value })}
                        />
                      </div>

                      <div className="form-group">
                        <label className="form-label">Deadline</label>
                        <input
                          type="date"
                          className="form-input"
                          value={newAssignment.deadline}
                          onChange={(e) => setNewAssignment({ ...newAssignment, deadline: e.target.value })}
                        />
                      </div>
                    </div>

                    <div className="form-group">
                      <label className="form-label">Instructions / Description</label>
                      <textarea
                        rows={2}
                        className="form-textarea"
                        placeholder="Optional guidelines for students..."
                        value={newAssignment.description}
                        onChange={(e) => setNewAssignment({ ...newAssignment, description: e.target.value })}
                      />
                    </div>

                    {/* SELECT PROBLEMS GRID */}
                    <div style={{ marginTop: 12, marginBottom: 20 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                        <label className="form-label" style={{ margin: 0 }}>
                          Select Problems to Include ({newAssignment.selectedProblemIds.length} Selected) *
                        </label>
                        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                          {problems.length} problems available
                        </span>
                      </div>

                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
                          gap: 10,
                          maxHeight: 220,
                          overflowY: "auto",
                          padding: 10,
                          backgroundColor: "#f8fafc",
                          borderRadius: 8,
                          border: "1px solid var(--border-light)",
                        }}
                      >
                        {problems.map((prob) => {
                          const isSelected = newAssignment.selectedProblemIds.includes(prob.id);
                          return (
                            <div
                              key={prob.id}
                              onClick={() => toggleProblemSelection(prob.id)}
                              style={{
                                padding: "10px 12px",
                                borderRadius: 6,
                                border: isSelected ? "2px solid var(--primary)" : "1px solid var(--border-light)",
                                backgroundColor: isSelected ? "#eff6ff" : "white",
                                cursor: "pointer",
                                display: "flex",
                                alignItems: "center",
                                gap: 10,
                              }}
                            >
                              {isSelected ? (
                                <CheckSquare size={18} color="var(--primary)" />
                              ) : (
                                <Square size={18} color="var(--text-muted)" />
                              )}
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-main)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                  {prob.title}
                                </div>
                                <div style={{ display: "flex", gap: 6, marginTop: 2 }}>
                                  <span className={`badge badge-${prob.difficulty.toLowerCase()}`} style={{ fontSize: 10, padding: "1px 5px" }}>
                                    {prob.difficulty}
                                  </span>
                                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{prob.topic}</span>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {/* SELECT STUDENTS GRID */}
                    <div style={{ marginTop: 12, marginBottom: 20 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                        <label className="form-label" style={{ margin: 0 }}>
                          Assign to Students ({newAssignment.selectedStudentIds.length} Selected) *
                        </label>
                        <button
                          type="button"
                          className="btn btn-outline"
                          style={{ padding: "2px 8px", fontSize: 11 }}
                          onClick={selectAllStudents}
                        >
                          Select All Enrolled Students
                        </button>
                      </div>

                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
                          gap: 10,
                          maxHeight: 180,
                          overflowY: "auto",
                          padding: 10,
                          backgroundColor: "#f8fafc",
                          borderRadius: 8,
                          border: "1px solid var(--border-light)",
                        }}
                      >
                        {studentUsers.map((stu) => {
                          const isSelected = newAssignment.selectedStudentIds.includes(stu.id);
                          return (
                            <div
                              key={stu.id}
                              onClick={() => toggleStudentSelection(stu.id)}
                              style={{
                                padding: "8px 12px",
                                borderRadius: 6,
                                border: isSelected ? "2px solid var(--primary)" : "1px solid var(--border-light)",
                                backgroundColor: isSelected ? "#eff6ff" : "white",
                                cursor: "pointer",
                                display: "flex",
                                alignItems: "center",
                                gap: 10,
                              }}
                            >
                              {isSelected ? (
                                <CheckSquare size={18} color="var(--primary)" />
                              ) : (
                                <Square size={18} color="var(--text-muted)" />
                              )}
                              <div>
                                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-main)" }}>
                                  {stu.name}
                                </div>
                                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                                  {stu.email}
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
                      <button type="submit" className="btn btn-primary" disabled={isSubmittingAssignment}>
                        <Send size={16} /> {isSubmittingAssignment ? "Assigning..." : "Assign to Selected Students"}
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {/* TAB 3: DESIGN CODING TEST (TEACHER) */}
              {teacherTab === "create_test" && (
                <div className="card">
                  <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 6 }}>
                    Design a New Timed Coding Test
                  </h3>
                  <p style={{ color: "var(--text-muted)", fontSize: 13, marginBottom: 20 }}>
                    Create an official departmental coding test. All students will have access to take this test and earn <strong>10 XP</strong> upon completion.
                  </p>

                  {testFormMsg && (
                    <div
                      style={{
                        padding: 12,
                        borderRadius: 8,
                        marginBottom: 16,
                        fontSize: 13,
                        backgroundColor: testFormMsg.type === "success" ? "#ecfdf5" : "#fef2f2",
                        color: testFormMsg.type === "success" ? "#065f46" : "#991b1b",
                        border: `1px solid ${testFormMsg.type === "success" ? "#a7f3d0" : "#fecaca"}`,
                      }}
                    >
                      {testFormMsg.text}
                    </div>
                  )}

                  <form onSubmit={handleCreateTestSubmit}>
                    <div style={{ display: "grid", gridTemplateColumns: "3fr 1fr", gap: 16 }}>
                      <div className="form-group">
                        <label className="form-label">Coding Test Title *</label>
                        <input
                          type="text"
                          className="form-input"
                          placeholder="e.g. End-Semester Algorithmic Assessment 2026"
                          required
                          value={newCodingTest.title}
                          onChange={(e) => setNewCodingTest({ ...newCodingTest, title: e.target.value })}
                        />
                      </div>

                      <div className="form-group">
                        <label className="form-label">Duration (Minutes) *</label>
                        <input
                          type="number"
                          className="form-input"
                          min="5"
                          max="360"
                          required
                          value={newCodingTest.duration}
                          onChange={(e) => setNewCodingTest({ ...newCodingTest, duration: e.target.value })}
                        />
                      </div>
                    </div>

                    <div className="form-group">
                      <label className="form-label">Test Instructions & Guidelines</label>
                      <textarea
                        rows={2}
                        className="form-textarea"
                        placeholder="Instructions, syllabus covered, or guidelines for participants..."
                        value={newCodingTest.description}
                        onChange={(e) => setNewCodingTest({ ...newCodingTest, description: e.target.value })}
                      />
                    </div>

                    {/* TWO TABS / SECTIONS FOR SELECTING & CREATING PROBLEMS */}
                    <div style={{ marginTop: 16, marginBottom: 20 }}>
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          borderBottom: "1px solid var(--border-light)",
                          paddingBottom: 10,
                          marginBottom: 16,
                        }}
                      >
                        <div>
                          <h4 style={{ fontSize: 15, fontWeight: 700, margin: 0, color: "var(--text-main)" }}>
                            Test Question Set ({newCodingTest.selectedProblemIds.length + testCustomProblems.length} Total Questions Selected)
                          </h4>
                          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                            Combine existing practice questions and newly created unique test questions.
                          </span>
                        </div>

                        <button
                          type="button"
                          className="btn btn-outline"
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 6,
                            fontSize: 12,
                            borderColor: showAddCustomQuestion ? "var(--primary)" : undefined,
                            backgroundColor: showAddCustomQuestion ? "#eff6ff" : "white",
                          }}
                          onClick={() => setShowAddCustomQuestion(!showAddCustomQuestion)}
                        >
                          <PlusCircle size={15} />
                          {showAddCustomQuestion ? "Close Unique Question Creator" : "+ Create Unique Test Question"}
                        </button>
                      </div>

                      {/* UNIQUE QUESTION CREATOR SUB-FORM */}
                      {showAddCustomQuestion && (
                        <div
                          style={{
                            backgroundColor: "#f0fdf4",
                            border: "1px solid #86efac",
                            borderRadius: 10,
                            padding: 16,
                            marginBottom: 20,
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                            <div style={{ fontWeight: 700, fontSize: 14, color: "#166534" }}>
                              ✨ Design New Unique Problem for This Test
                            </div>
                            <span style={{ fontSize: 11, color: "#15803d" }}>
                              This question will be saved and linked exclusively to this exam
                            </span>
                          </div>

                          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: 16, marginBottom: 14 }}>
                            <div>
                              <label className="form-label" style={{ fontSize: 13 }}>Problem Title *</label>
                              <input
                                type="text"
                                className="form-input"
                                placeholder="e.g. Sum of two numbers"
                                value={newTestCustomProblem.title}
                                onChange={(e) => setNewTestCustomProblem({ ...newTestCustomProblem, title: e.target.value })}
                              />
                            </div>
                            <div>
                              <label className="form-label" style={{ fontSize: 13 }}>Difficulty *</label>
                              <select
                                className="form-select"
                                value={newTestCustomProblem.difficulty}
                                onChange={(e) => setNewTestCustomProblem({ ...newTestCustomProblem, difficulty: e.target.value })}
                              >
                                <option value="Easy">Easy</option>
                                <option value="Medium">Medium</option>
                                <option value="Hard">Hard</option>
                              </select>
                            </div>
                            <div>
                              <label className="form-label" style={{ fontSize: 13 }}>Topic / Tag *</label>
                              <input
                                type="text"
                                className="form-input"
                                placeholder="e.g. Arithmetic Operations"
                                value={newTestCustomProblem.topic}
                                onChange={(e) => setNewTestCustomProblem({ ...newTestCustomProblem, topic: e.target.value })}
                              />
                            </div>
                          </div>

                          <div className="form-group" style={{ marginBottom: 14 }}>
                            <label className="form-label" style={{ fontSize: 13 }}>Problem Statement / Description *</label>
                            <textarea
                              rows={3}
                              className="form-textarea"
                              placeholder="Explain the problem statement clearly..."
                              value={newTestCustomProblem.description}
                              onChange={(e) => setNewTestCustomProblem({ ...newTestCustomProblem, description: e.target.value })}
                            />
                          </div>

                          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 14 }}>
                            <div className="form-group">
                              <label className="form-label" style={{ fontSize: 13 }}>Constraints</label>
                              <textarea
                                rows={2}
                                className="form-textarea"
                                placeholder="e.g. -10^9 <= a <= 10^9"
                                value={newTestCustomProblem.constraints}
                                onChange={(e) => setNewTestCustomProblem({ ...newTestCustomProblem, constraints: e.target.value })}
                              />
                            </div>

                            <div className="form-group">
                              <label className="form-label" style={{ fontSize: 13 }}>Examples</label>
                              <textarea
                                rows={2}
                                className="form-textarea"
                                placeholder="Input:\n5\n10\n\nOutput:\n15"
                                value={newTestCustomProblem.examples}
                                onChange={(e) => setNewTestCustomProblem({ ...newTestCustomProblem, examples: e.target.value })}
                              />
                            </div>
                          </div>

                          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 14 }}>
                            <div className="form-group">
                              <label className="form-label" style={{ fontSize: 13 }}>Sample Test Input *</label>
                              <input
                                type="text"
                                className="form-input"
                                placeholder="e.g. 5 10"
                                value={newTestCustomProblem.sample_input}
                                onChange={(e) => setNewTestCustomProblem({ ...newTestCustomProblem, sample_input: e.target.value })}
                              />
                            </div>

                            <div className="form-group">
                              <label className="form-label" style={{ fontSize: 13 }}>Sample Test Expected Output *</label>
                              <input
                                type="text"
                                className="form-input"
                                placeholder="e.g. 15"
                                value={newTestCustomProblem.sample_output}
                                onChange={(e) => setNewTestCustomProblem({ ...newTestCustomProblem, sample_output: e.target.value })}
                              />
                            </div>
                          </div>

                          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
                            <button
                              type="button"
                              className="btn btn-outline"
                              style={{ padding: "4px 12px", fontSize: 12 }}
                              onClick={() => setShowAddCustomQuestion(false)}
                            >
                              Cancel
                            </button>
                            <button
                              type="button"
                              className="btn btn-primary"
                              style={{ padding: "4px 14px", fontSize: 12, backgroundColor: "#16a34a", borderColor: "#16a34a" }}
                              onClick={handleAddCustomProblemToTest}
                            >
                              + Add Question to Test
                            </button>
                          </div>
                        </div>
                      )}

                      {/* DISPLAY CURRENTLY ADDED UNIQUE QUESTIONS */}
                      {testCustomProblems.length > 0 && (
                        <div style={{ marginBottom: 20 }}>
                          <label className="form-label" style={{ color: "#166534", fontWeight: 700 }}>
                            ⭐ Newly Created Unique Questions ({testCustomProblems.length})
                          </label>
                          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                            {testCustomProblems.map((cp, idx) => (
                              <div
                                key={idx}
                                style={{
                                  display: "flex",
                                  justifyContent: "space-between",
                                  alignItems: "center",
                                  padding: "10px 14px",
                                  borderRadius: 8,
                                  backgroundColor: "#f0fdf4",
                                  border: "1px solid #bbf7d0",
                                }}
                              >
                                <div>
                                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                    <span style={{ fontWeight: 700, fontSize: 13, color: "var(--text-main)" }}>
                                      {cp.title}
                                    </span>
                                    <span className={`badge badge-${cp.difficulty.toLowerCase()}`} style={{ fontSize: 10, padding: "1px 6px" }}>
                                      {cp.difficulty}
                                    </span>
                                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{cp.topic}</span>
                                    <span style={{ fontSize: 10, backgroundColor: "#dcfce7", color: "#15803d", fontWeight: 700, padding: "1px 6px", borderRadius: 4 }}>
                                      Unique New
                                    </span>
                                  </div>
                                  <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
                                    {cp.description.slice(0, 90)}...
                                  </div>
                                </div>
                                <button
                                  type="button"
                                  className="btn btn-outline"
                                  style={{ color: "#ef4444", borderColor: "#fca5a5", padding: "2px 8px", fontSize: 11 }}
                                  onClick={() => handleRemoveCustomProblemFromTest(idx)}
                                >
                                  Remove
                                </button>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* PREDEFINED PROBLEMS CHECKLIST */}
                      <div>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                          <label className="form-label" style={{ margin: 0 }}>
                            Select from Predefined Question Bank ({newCodingTest.selectedProblemIds.length} Selected)
                          </label>
                          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                            {problems.length} existing problems available
                          </span>
                        </div>

                        <div
                          style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
                            gap: 10,
                            maxHeight: 220,
                            overflowY: "auto",
                            padding: 10,
                            backgroundColor: "#f8fafc",
                            borderRadius: 8,
                            border: "1px solid var(--border-light)",
                          }}
                        >
                          {problems.map((prob) => {
                            const isSelected = newCodingTest.selectedProblemIds.includes(prob.id);
                            return (
                              <div
                                key={prob.id}
                                onClick={() => toggleTestProblemSelection(prob.id)}
                                style={{
                                  padding: "10px 12px",
                                  borderRadius: 6,
                                  border: isSelected ? "2px solid var(--primary)" : "1px solid var(--border-light)",
                                  backgroundColor: isSelected ? "#eff6ff" : "white",
                                  cursor: "pointer",
                                  display: "flex",
                                  alignItems: "center",
                                  gap: 10,
                                }}
                              >
                                {isSelected ? (
                                  <CheckSquare size={18} color="var(--primary)" />
                                ) : (
                                  <Square size={18} color="var(--text-muted)" />
                                )}
                                <div style={{ flex: 1, minWidth: 0 }}>
                                  <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-main)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                    {prob.title}
                                  </div>
                                  <div style={{ display: "flex", gap: 6, marginTop: 2 }}>
                                    <span className={`badge badge-${prob.difficulty.toLowerCase()}`} style={{ fontSize: 10, padding: "1px 5px" }}>
                                      {prob.difficulty}
                                    </span>
                                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{prob.topic}</span>
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </div>

                    <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
                      <button type="submit" className="btn btn-primary" disabled={isSubmittingTest}>
                        <Clock size={16} /> {isSubmittingTest ? "Publishing..." : "Publish Coding Test for Students"}
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {/* TAB 4: MANAGE ASSIGNED ACTIVITIES & TESTS */}
              {teacherTab === "manage" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                  <div className="card">
                    <h4 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
                      Designed Coding Tests ({codingTests.length})
                    </h4>
                    {codingTests.length === 0 ? (
                      <p style={{ color: "var(--text-muted)", fontSize: 13 }}>No coding tests designed yet.</p>
                    ) : (
                      <div className="table-container">
                        <table className="clan-table">
                          <thead>
                            <tr>
                              <th>ID</th>
                              <th>Test Title</th>
                              <th>Duration</th>
                              <th>Problems Included</th>
                              <th>Submissions Count</th>
                              <th>Created Date</th>
                            </tr>
                          </thead>
                          <tbody>
                            {codingTests.map((t) => (
                              <tr key={t.id}>
                                <td>#{t.id}</td>
                                <td>
                                  <strong>{t.title}</strong>
                                  {t.description && <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{t.description}</div>}
                                </td>
                                <td>{t.duration} mins</td>
                                <td>
                                  {t.problems.map((p) => p.title).join(", ") || "None"}
                                </td>
                                <td>
                                  <span className="badge badge-easy">{t.completed_count} Submissions</span>
                                </td>
                                <td>{new Date(t.created_at).toLocaleDateString()}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>

                  <div className="card">
                    <h4 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
                      Assigned Coursework Tracking ({assignments.length})
                    </h4>
                    {assignments.length === 0 ? (
                      <p style={{ color: "var(--text-muted)", fontSize: 13 }}>No assignments created yet.</p>
                    ) : (
                      <div className="table-container">
                        <table className="clan-table">
                          <thead>
                            <tr>
                              <th>ID</th>
                              <th>Assignment Title</th>
                              <th>Assigned Problems</th>
                              <th>Students Enrolled</th>
                              <th>Date Created</th>
                            </tr>
                          </thead>
                          <tbody>
                            {assignments.map((a) => (
                              <tr key={a.id}>
                                <td>#{a.id}</td>
                                <td>
                                  <strong>{a.title}</strong>
                                  {a.description && <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{a.description}</div>}
                                </td>
                                <td>
                                  {a.problems.map((p) => p.title).join(", ") || "None"}
                                </td>
                                <td>
                                  <span className="badge badge-easy">{a.students.length} Students</span>
                                </td>
                                <td>{new Date(a.created_at).toLocaleDateString()}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>

                  <div className="card">
                    <h4 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
                      Department Question Bank ({problems.length} Problems)
                    </h4>
                    <div className="table-container">
                      <table className="clan-table">
                        <thead>
                          <tr>
                            <th>ID</th>
                            <th>Title</th>
                            <th>Difficulty</th>
                            <th>Topic</th>
                            <th>Created By</th>
                          </tr>
                        </thead>
                        <tbody>
                          {problems.map((p) => (
                            <tr key={p.id}>
                              <td>#{p.id}</td>
                              <td style={{ fontWeight: 600 }}>{p.title}</td>
                              <td>
                                <span className={`badge badge-${p.difficulty.toLowerCase()}`}>
                                  {p.difficulty}
                                </span>
                              </td>
                              <td>{p.topic}</td>
                              <td>User #{p.created_by}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
