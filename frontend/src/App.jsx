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
  fetchGroupedSubmissionsByStudent,
  fetchGroupedSubmissionsByProblem,
  fetchSubmissionById,
  createSubmission,
  runSampleCases,
  fetchAssignments,
  createAssignment,
  fetchPracticals,
  createPractical,
  bulkAssignPracticals,
  startPractical,
  submitPractical,
  evaluateStudentPractical,
  fetchCodingTests,
  createCodingTest,
  completeCodingTest,
  fetchLeaderboard,
  fetchExecutionSecurityStatus,
  fetchEnvironments,
} from "./api";
import TeacherDashboard from "./components/TeacherDashboard";
import StudentDashboard from "./components/StudentDashboard";
import StudentRoster from "./components/StudentRoster";
import CodingWorkspace from "./components/CodingWorkspace";
import {
  getCleanStarterTemplate,
  getDefaultFileNameForLang,
  getInitialFilesForProblem,
  isCodeModifiedFromStarter,
  loadSavedDraft,
  saveCodeDraft,
  clearSavedDraft,
} from "./components/starterTemplates";
import { StatusBadge, AssignmentStatusBadge } from "./components/ui";
import "./App.css";
import "./components/dashboard.css";

function getLanguageTemplate(language, problem = null) {
  return getCleanStarterTemplate(language, problem);
}

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
  const [editorCode, setEditorCode] = useState("# Write your solution here\n\n");
  const [projectFiles, setProjectFiles] = useState({ "main.py": "# Write your solution here\n\n" });
  const [activeFileName, setActiveFileName] = useState("main.py");
  const [newFileNameInput, setNewFileNameInput] = useState("");
  const [selectedLanguage, setSelectedLanguage] = useState("python");
  const [practicePasteRestricted, setPracticePasteRestricted] = useState(false);
  const [environmentsCatalog, setEnvironmentsCatalog] = useState([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRunningSamples, setIsRunningSamples] = useState(false);
  const [sampleRunResult, setSampleRunResult] = useState(null);
  const [lastSubmissionResult, setLastSubmissionResult] = useState(null);
  const [activeAssignmentId, setActiveAssignmentId] = useState(null);
  const [activePracticalId, setActivePracticalId] = useState(null);
  const [selectedAssignmentWorkspace, setSelectedAssignmentWorkspace] = useState(null);
  const [selectedPracticalWorkspace, setSelectedPracticalWorkspace] = useState(null);
  const [selectedTestForDetails, setSelectedTestForDetails] = useState(null);
  const [isLoadingProblems, setIsLoadingProblems] = useState(false);
  const [networkError, setNetworkError] = useState(null);

  // Submissions history & detail review state (Grouped by Student for Teacher, Grouped by Problem for Student)
  const [submissions, setSubmissions] = useState([]);
  const [teacherGroupedStudents, setTeacherGroupedStudents] = useState([]);
  const [selectedTeacherStudent, setSelectedTeacherStudent] = useState(null);
  const [studentGroupedProblems, setStudentGroupedProblems] = useState([]);
  const [selectedStudentProblemGroup, setSelectedStudentProblemGroup] = useState(null);
  const [submissionFilters, setSubmissionFilters] = useState({
    student_search: "",
    problem_search: "",
    language: "",
    status: "",
    submission_type: "",
    date_from: "",
    date_to: "",
    sort_by: "latest",
  });
  const [selectedSubmissionDetail, setSelectedSubmissionDetail] = useState(null);
  const [isLoadingSubmissionDetail, setIsLoadingSubmissionDetail] = useState(false);

  // Assignments & Academic Practicals state
  const [assignments, setAssignments] = useState([]);
  const [practicals, setPracticals] = useState([]);
  const [courseworkSubTab, setCourseworkSubTab] = useState("regular_assignment"); // 'regular_assignment' | 'create_practical' | 'assign_practicals' | 'track_practicals'
  const [selectedPracticalForStudents, setSelectedPracticalForStudents] = useState(null);
  const [practicalStudentFilter, setPracticalStudentFilter] = useState("all"); // 'all' | 'pending' | 'submitted'
  const [evaluatingPracticalStudent, setEvaluatingPracticalStudent] = useState(null); // { practicalId, studentId, studentName, status, marks_obtained, teacher_feedback, max_marks }
  const [isEvaluatingPractical, setIsEvaluatingPractical] = useState(false);
  const [studentSubmittingPractical, setStudentSubmittingPractical] = useState(null); // practical object for manual/report submission modal
  const [practicalSubmissionDraft, setPracticalSubmissionDraft] = useState({
    submission_notes: "",
    attachment_filename: "",
    attachment_content_b64: "",
  });
  const [isSubmittingPracticalReport, setIsSubmittingPracticalReport] = useState(false);

  // Teacher Academic Practical Creation & Bulk Assign State
  const [newPractical, setNewPractical] = useState({
    practical_number: 1,
    title: "",
    subject_name: "",
    subject_code: "",
    semester: "",
    description: "",
    objectives: "",
    problem_id: "",
    start_date: "",
    deadline: "",
    max_marks: 10,
    selectedStudentIds: [],
  });
  const [isSubmittingNewPractical, setIsSubmittingNewPractical] = useState(false);
  const [practicalFormMsg, setPracticalFormMsg] = useState(null);

  const [bulkPracticalAssign, setBulkPracticalAssign] = useState({
    selectedPracticalIds: [],
    selectedStudentIds: [],
    deadline: "",
    objectives: "",
  });
  const [isSubmittingBulkPractical, setIsSubmittingBulkPractical] = useState(false);
  const [bulkPracticalMsg, setBulkPracticalMsg] = useState(null);

  // Manage Activities Search & Filter State
  const [manageSearchQuery, setManageSearchQuery] = useState("");
  const [manageTypeFilter, setManageTypeFilter] = useState("all"); // 'all' | 'coding_tests' | 'assignments' | 'practicals' | 'problems'
  const [manageDateFilter, setManageDateFilter] = useState("");

  // Optional fields toggle for simplified problem creation
  const [showOptionalProblemFields, setShowOptionalProblemFields] = useState(false);
  const [showOptionalTestProblemFields, setShowOptionalTestProblemFields] = useState(false);

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
    environment_id: "cp",
    problem_type: "competitive",
    evaluation_type: "exact",
    tolerance: "0.00001",
    ml_metric: "f1",
    ml_threshold: "0.80",
    target_file: "output.csv",
    function_name: "solve",
    custom_evaluator_script: "",
    dataset_filename: "",
    dataset_visibility: "public",
    dataset_content: "",
    sample_input: "",
    sample_output: "",
    hidden_input: "",
    hidden_output: "",
  });
  const [isSubmittingProblem, setIsSubmittingProblem] = useState(false);
  const [formMsg, setFormMsg] = useState(null);

  // Teacher Assignment Creation Form state
  const [newAssignment, setNewAssignment] = useState({
    title: "",
    description: "",
    start_date: "",
    deadline: "",
    allow_copy_paste: true,
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
    allow_copy_paste: false,
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
    hidden_input: "",
    hidden_output: "",
  });
  const [showAddCustomQuestion, setShowAddCustomQuestion] = useState(false);
  const [isSubmittingTest, setIsSubmittingTest] = useState(false);
  const [testFormMsg, setTestFormMsg] = useState(null);

  // Active Student Test Session (Proctored Environment)
  const [activeTestSession, setActiveTestSession] = useState(null); // { test, problemDetails, timeRemaining, activeProblemIndex, answers: { [probId]: code }, violationWarnings: 0, status: 'in_progress' | 'submitted' }
  const [testEditorLanguage, setTestEditorLanguage] = useState("python");
  const [testRunOutput, setTestRunOutput] = useState(null);
  const [testSampleResult, setTestSampleResult] = useState(null);
  const [testSubmissionResult, setTestSubmissionResult] = useState(null);
  const [isTestRunningSamples, setIsTestRunningSamples] = useState(false);
  const [isTestEvaluating, setIsTestEvaluating] = useState(false);
  const [tabSwitchAlert, setTabSwitchAlert] = useState(false);
  const [securityStatus, setSecurityStatus] = useState(null);

  // Load initial data
  useEffect(() => {
    loadUsers();
    loadProblems();
    loadSubmissions();
    loadAssignments();
    loadPracticals();
    loadCodingTests();
    loadLeaderboardData();
    fetchExecutionSecurityStatus()
      .then((st) => setSecurityStatus(st))
      .catch(() => {});
    fetchEnvironments()
      .then((res) => setEnvironmentsCatalog(res.environments || []))
      .catch(() => {});
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
  const loadSubmissions = async (overrideFilters = null) => {
    const activeFilters = overrideFilters || submissionFilters;
    try {
      const baseQuery = isTeacher
        ? {
            user_id: selectedTeacherStudent?.user_id || undefined,
            ...activeFilters,
          }
        : {
            user_id: currentUser.id,
            ...activeFilters,
          };
      const [subData, groupedData] = await Promise.all([
        fetchSubmissions(baseQuery),
        isTeacher
          ? fetchGroupedSubmissionsByStudent(activeFilters)
          : fetchGroupedSubmissionsByProblem({
              user_id: currentUser.id,
              submission_type: activeFilters.submission_type,
              problem_search: activeFilters.problem_search,
            }),
      ]);
      setSubmissions(subData);
      if (isTeacher) {
        setTeacherGroupedStudents(groupedData);
      } else {
        setStudentGroupedProblems(groupedData);
      }
    } catch (err) {
      console.error("Error loading submissions:", err);
    }
  };

  const loadAssignments = async () => {
    try {
      const data = await fetchAssignments(isTeacher ? {} : { student_id: currentUser.id });
      setAssignments(data);
      setSelectedAssignmentWorkspace((prev) => {
        if (!prev) return null;
        return data.find((a) => a.id === prev.id) || prev;
      });
    } catch (err) {
      console.error("Error loading assignments:", err);
    }
  };

  const loadPracticals = async () => {
    try {
      const data = await fetchPracticals(isTeacher ? {} : { student_id: currentUser.id });
      setPracticals(data);
      if (selectedPracticalForStudents) {
        const refreshed = data.find((p) => p.id === selectedPracticalForStudents.id);
        if (refreshed) setSelectedPracticalForStudents(refreshed);
      }
      setSelectedPracticalWorkspace((prev) => {
        if (!prev) return null;
        return data.find((p) => p.id === prev.id) || prev;
      });
    } catch (err) {
      console.error("Error loading academic practicals:", err);
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

  const getActiveContextKey = (overrideCtx = null) => {
    if (overrideCtx) return overrideCtx;
    if (activeTab === "assignments" && selectedAssignmentWorkspace) {
      return `assignment:${selectedAssignmentWorkspace.id}`;
    }
    if (activeTab === "assignments" && selectedPracticalWorkspace) {
      return `practical:${selectedPracticalWorkspace.id}`;
    }
    return "practice";
  };

  const openProblem = async (prob, langOverride = null, contextKeyOverride = null) => {
    const pid = prob?.id || prob?.problem_id;
    if (!pid) return;
    const ctxKey = getActiveContextKey(contextKeyOverride);
    try {
      const fullProb = await fetchProblemById(pid);
      const envId = fullProb.environment_id || "cp";
      const lang = envId !== "cp" ? "python" : (langOverride || selectedLanguage);
      if (envId !== "cp" && selectedLanguage !== "python") {
        setSelectedLanguage("python");
      }
      setSelectedProblem(fullProb);
      setLastSubmissionResult(null);
      setSampleRunResult(null);

      // Restore student's saved draft for this (user, context, problem, language) if present
      const savedDraft = loadSavedDraft(currentUser.id, ctxKey, fullProb.id, lang);
      if (savedDraft && savedDraft.files && Object.keys(savedDraft.files).length > 0) {
        const activeKey =
          savedDraft.activeFileName && savedDraft.files[savedDraft.activeFileName] !== undefined
            ? savedDraft.activeFileName
            : Object.keys(savedDraft.files)[0];
        setProjectFiles(savedDraft.files);
        setActiveFileName(activeKey);
        setEditorCode(savedDraft.files[activeKey] ?? "");
      } else {
        const init = getInitialFilesForProblem(fullProb, lang);
        setProjectFiles(init.files);
        setActiveFileName(init.activeFileName);
        setEditorCode(init.code);
      }
    } catch (err) {
      console.error("Error fetching problem details:", err);
      setSelectedProblem(prob);
    }
  };

  const handleLanguageChange = (newLang) => {
    if (newLang === selectedLanguage) return;
    const ctxKey = getActiveContextKey();
    const pid = selectedProblem?.id || selectedProblem?.problem_id;

    // Warn student and ask for confirmation if they have modified code in the current language
    if (
      selectedProblem &&
      isCodeModifiedFromStarter(editorCode, projectFiles, selectedLanguage, selectedProblem)
    ) {
      const confirmed = window.confirm(
        `You have written code in ${selectedLanguage.toUpperCase()}. Switching to ${newLang.toUpperCase()} will replace the editor contents with the ${newLang.toUpperCase()} template (your ${selectedLanguage.toUpperCase()} draft is saved if you switch back). Do you want to continue?`
      );
      if (!confirmed) return;
      saveCodeDraft(currentUser.id, ctxKey, pid, selectedLanguage, {
        files: projectFiles,
        activeFileName,
        code: editorCode,
      });
    }

    setSelectedLanguage(newLang);
    setSampleRunResult(null);
    if (selectedProblem) {
      const savedDraft = loadSavedDraft(currentUser.id, ctxKey, pid, newLang);
      if (savedDraft && savedDraft.files && Object.keys(savedDraft.files).length > 0) {
        const activeKey =
          savedDraft.activeFileName && savedDraft.files[savedDraft.activeFileName] !== undefined
            ? savedDraft.activeFileName
            : Object.keys(savedDraft.files)[0];
        setProjectFiles(savedDraft.files);
        setActiveFileName(activeKey);
        setEditorCode(savedDraft.files[activeKey] ?? "");
      } else {
        const init = getInitialFilesForProblem(selectedProblem, newLang);
        setProjectFiles(init.files);
        setActiveFileName(init.activeFileName);
        setEditorCode(init.code);
      }
    }
  };

  const handleResetCode = () => {
    if (!selectedProblem) return;
    const ctxKey = getActiveContextKey();
    const pid = selectedProblem.id || selectedProblem.problem_id;
    const modified = isCodeModifiedFromStarter(
      editorCode,
      projectFiles,
      selectedLanguage,
      selectedProblem
    );
    if (modified) {
      const confirmed = window.confirm(
        "Are you sure you want to reset your code to the default starter template? Your current edits in this language will be replaced."
      );
      if (!confirmed) return;
    }
    clearSavedDraft(currentUser.id, ctxKey, pid, selectedLanguage);
    const init = getInitialFilesForProblem(selectedProblem, selectedLanguage);
    setProjectFiles(init.files);
    setActiveFileName(init.activeFileName);
    setEditorCode(init.code);
  };

  const handleEditorCodeChange = (newCode) => {
    setEditorCode(newCode);
    const updatedFiles = {
      ...projectFiles,
      [activeFileName]: newCode,
    };
    setProjectFiles(updatedFiles);
    const pid = selectedProblem?.id || selectedProblem?.problem_id;
    if (pid) {
      saveCodeDraft(currentUser.id, getActiveContextKey(), pid, selectedLanguage, {
        files: updatedFiles,
        activeFileName,
        code: newCode,
      });
    }
  };

  const handleSelectProjectFile = (fname) => {
    setActiveFileName(fname);
    setEditorCode(projectFiles[fname] ?? "");
  };

  const handleAddProjectFile = () => {
    const clean = (newFileNameInput || "").trim().replace(/^\/+/, "");
    if (!clean) return;
    if (projectFiles[clean] !== undefined) {
      handleSelectProjectFile(clean);
      setNewFileNameInput("");
      return;
    }
    const stub = clean.endsWith(".py")
      ? `# ${clean}\n`
      : clean.endsWith(".h") || clean.endsWith(".hpp")
      ? `#pragma once\n`
      : `// ${clean}\n`;
    const nextFiles = { ...projectFiles, [clean]: stub };
    setProjectFiles(nextFiles);
    setActiveFileName(clean);
    setEditorCode(stub);
    setNewFileNameInput("");
    const pid = selectedProblem?.id || selectedProblem?.problem_id;
    if (pid) {
      saveCodeDraft(currentUser.id, getActiveContextKey(), pid, selectedLanguage, {
        files: nextFiles,
        activeFileName: clean,
        code: stub,
      });
    }
  };

  const handleDeleteProjectFile = (fname) => {
    const keys = Object.keys(projectFiles);
    if (keys.length <= 1) return;
    const next = { ...projectFiles };
    delete next[fname];
    const remainingKeys = Object.keys(next);
    const nextActive = remainingKeys[0];
    setProjectFiles(next);
    setActiveFileName(nextActive);
    setEditorCode(next[nextActive] || "");
    const pid = selectedProblem?.id || selectedProblem?.problem_id;
    if (pid) {
      saveCodeDraft(currentUser.id, getActiveContextKey(), pid, selectedLanguage, {
        files: next,
        activeFileName: nextActive,
        code: next[nextActive] || "",
      });
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

  const handleRunPracticeSamples = async () => {
    if (!selectedProblem) return;
    setIsRunningSamples(true);
    setSampleRunResult(null);
    const currentFiles = { ...projectFiles, [activeFileName]: editorCode };
    const isMultiFile = Object.keys(currentFiles).length > 1;
    try {
      const res = await runSampleCases({
        problem_id: selectedProblem.id,
        language: selectedLanguage,
        code: editorCode,
        files: isMultiFile ? currentFiles : undefined,
        entry_point: selectedProblem.entry_point || undefined,
      });
      setSampleRunResult(res);
    } catch (err) {
      setSampleRunResult({
        status: "Internal Evaluation Error",
        error_message: err.message,
        passed_count: 0,
        total_count: 0,
        results: [],
      });
    } finally {
      setIsRunningSamples(false);
    }
  };

  const handleSubmitSolution = async (explicitContext = null) => {
    const activeUserId = currentUser.id;
    if (!selectedProblem) return;
    setIsSubmitting(true);
    setLastSubmissionResult(null);
    const currentFiles = { ...projectFiles, [activeFileName]: editorCode };
    const isMultiFile = Object.keys(currentFiles).length > 1;

    try {
      let submissionType = "practice";
      let targetAssignmentId = undefined;
      let targetPracticalId = undefined;

      if (explicitContext?.type === "assignment" && explicitContext.assignmentId) {
        submissionType = "assignment";
        targetAssignmentId = explicitContext.assignmentId;
      } else if (explicitContext?.type === "practical" && explicitContext.practicalId) {
        submissionType = "practical";
        targetPracticalId = explicitContext.practicalId;
      } else if (activeTab === "assignments" && selectedAssignmentWorkspace) {
        submissionType = "assignment";
        targetAssignmentId = selectedAssignmentWorkspace.id;
      } else if (activeTab === "assignments" && selectedPracticalWorkspace) {
        submissionType = "practical";
        targetPracticalId = selectedPracticalWorkspace.id;
      } else if (activeTab === "practice") {
        // Practice Problems tab ALWAYS submits as independent practice
        submissionType = "practice";
      } else if (activePracticalId) {
        submissionType = "practical";
        targetPracticalId = activePracticalId;
      } else if (activeAssignmentId) {
        submissionType = "assignment";
        targetAssignmentId = activeAssignmentId;
      }

      const payload = {
        user_id: activeUserId,
        problem_id: selectedProblem.id,
        code: editorCode,
        files: isMultiFile ? currentFiles : undefined,
        entry_point: selectedProblem.entry_point || undefined,
        language: selectedLanguage,
        submission_type: submissionType,
        assignment_id: submissionType === "assignment" ? targetAssignmentId : undefined,
        practical_id: submissionType === "practical" ? targetPracticalId : undefined,
      };

      const result = await createSubmission(payload);
      setLastSubmissionResult(result);
      await loadSubmissions();
      if (submissionType === "assignment") await loadAssignments();
      if (submissionType === "practical") await loadPracticals();
    } catch (err) {
      alert("Submission error: " + err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Poll submission evaluation status while Pending Evaluation or Running
  useEffect(() => {
    if (
      !lastSubmissionResult ||
      !lastSubmissionResult.id ||
      (lastSubmissionResult.status !== "Pending Evaluation" && lastSubmissionResult.status !== "Running")
    ) {
      return;
    }

    const pollInterval = setInterval(async () => {
      try {
        const updated = await fetchSubmissionById(lastSubmissionResult.id);
        setLastSubmissionResult(updated);
        if (updated.status !== "Pending Evaluation" && updated.status !== "Running") {
          clearInterval(pollInterval);
          loadSubmissions();
          loadAssignments();
          loadPracticals();
          loadLeaderboardData();
        }
      } catch (err) {
        console.error("Error polling submission status:", err);
      }
    }, 1200);

    return () => clearInterval(pollInterval);
  }, [lastSubmissionResult?.id, lastSubmissionResult?.status]);

  // Poll inspected submission detail while Pending Evaluation or Running
  useEffect(() => {
    if (
      !selectedSubmissionDetail ||
      !selectedSubmissionDetail.id ||
      (selectedSubmissionDetail.status !== "Pending Evaluation" && selectedSubmissionDetail.status !== "Running")
    ) {
      return;
    }

    const pollInterval = setInterval(async () => {
      try {
        const updated = await fetchSubmissionById(selectedSubmissionDetail.id);
        setSelectedSubmissionDetail(updated);
        if (updated.status !== "Pending Evaluation" && updated.status !== "Running") {
          clearInterval(pollInterval);
          loadSubmissions();
        }
      } catch (err) {
        console.error("Error polling inspected submission:", err);
      }
    }, 1200);

    return () => clearInterval(pollInterval);
  }, [selectedSubmissionDetail?.id, selectedSubmissionDetail?.status]);

  const handleInspectSubmission = async (subId) => {
    setIsLoadingSubmissionDetail(true);
    try {
      const detail = await fetchSubmissionById(subId);
      setSelectedSubmissionDetail(detail);
    } catch (err) {
      alert("Unable to load submission details: " + err.message);
    } finally {
      setIsLoadingSubmissionDetail(false);
    }
  };

  const handleCreateProblemSubmit = async (e) => {
    e.preventDefault();
    setFormMsg(null);
    setIsSubmittingProblem(true);

    const activeUserId = currentUser.id;

    try {
      const testCases = [
        {
          input: newProblem.sample_input || "",
          expected_output: newProblem.sample_output || "",
          is_hidden: false,
        },
      ];
      if (newProblem.hidden_input?.trim() || newProblem.hidden_output?.trim()) {
        testCases.push({
          input: newProblem.hidden_input || "",
          expected_output: newProblem.hidden_output || "",
          is_hidden: true,
        });
      }

      const evalConfig = {};
      if (newProblem.evaluation_type === "numeric_tolerance") {
        evalConfig.abs_tol = parseFloat(newProblem.tolerance) || 1e-5;
      } else if (newProblem.evaluation_type === "ml_metrics") {
        evalConfig.metric = newProblem.ml_metric || "f1";
        evalConfig.threshold = parseFloat(newProblem.ml_threshold) || 0.8;
      } else if (newProblem.evaluation_type === "file_based") {
        evalConfig.target_file = newProblem.target_file || "output.csv";
      } else if (newProblem.evaluation_type === "function_harness") {
        evalConfig.function_name = newProblem.function_name || "solve";
      } else if (newProblem.evaluation_type === "custom_script") {
        evalConfig.custom_evaluator_script = newProblem.custom_evaluator_script || "";
      }

      const datasets = [];
      if (newProblem.dataset_filename?.trim() && newProblem.dataset_content?.trim()) {
        datasets.push({
          filename: newProblem.dataset_filename.trim(),
          visibility: newProblem.dataset_visibility || "public",
          mime_type: newProblem.dataset_filename.endsWith(".csv")
            ? "text/csv"
            : newProblem.dataset_filename.endsWith(".json")
            ? "application/json"
            : "text/plain",
          content_text: newProblem.dataset_content,
        });
      }

      const payload = {
        title: newProblem.title.trim(),
        description: newProblem.description.trim(),
        difficulty: newProblem.difficulty,
        topic: newProblem.topic.trim(),
        input_format: newProblem.input_format?.trim() || null,
        output_format: newProblem.output_format?.trim() || null,
        constraints: newProblem.constraints?.trim() || null,
        examples: newProblem.examples?.trim() || null,
        environment_id: newProblem.environment_id || "cp",
        problem_type: newProblem.problem_type || "competitive",
        evaluation_type: newProblem.evaluation_type || "exact",
        evaluation_config: Object.keys(evalConfig).length > 0 ? evalConfig : null,
        created_by: activeUserId,
        test_cases: testCases,
        datasets: datasets.length > 0 ? datasets : undefined,
      };

      const res = await createProblem(payload);
      setFormMsg({
        type: "success",
        text: `Problem "${res.title}" (Environment: ${res.environment_id}, Grading: ${res.evaluation_type}) created and published!`,
      });
      setNewProblem({
        title: "",
        difficulty: "Easy",
        topic: "Arithmetic Operations",
        description: "",
        input_format: "",
        output_format: "",
        constraints: "",
        examples: "",
        environment_id: "cp",
        problem_type: "competitive",
        evaluation_type: "exact",
        tolerance: "0.00001",
        ml_metric: "f1",
        ml_threshold: "0.80",
        target_file: "output.csv",
        function_name: "solve",
        custom_evaluator_script: "",
        dataset_filename: "",
        dataset_visibility: "public",
        dataset_content: "",
        sample_input: "",
        sample_output: "",
        hidden_input: "",
        hidden_output: "",
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
        allow_copy_paste: Boolean(newAssignment.allow_copy_paste),
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
        allow_copy_paste: true,
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
      hidden_input: "",
      hidden_output: "",
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
        allow_copy_paste: Boolean(newCodingTest.allow_copy_paste),
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
        allow_copy_paste: false,
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

    // Fetch full problem details (including public sample test cases)
    const problemDetails = {};
    const initialAnswers = {};
    const ctxKey = `coding_test:${test.id}`;
    for (const p of test.problems) {
      let detail = p;
      try {
        detail = await fetchProblemById(p.problem_id);
        problemDetails[p.problem_id] = detail;
      } catch {
        problemDetails[p.problem_id] = p;
      }
      const savedDraft = loadSavedDraft(currentUser.id, ctxKey, p.problem_id, testEditorLanguage);
      initialAnswers[p.problem_id] =
        savedDraft && savedDraft.code !== undefined
          ? savedDraft.code
          : getCleanStarterTemplate(testEditorLanguage, detail);
    }

    // Initialize timer in seconds (duration in minutes * 60)
    const initialSeconds = Math.max(test.duration * 60, 60);

    setSelectedTestForDetails(null);
    setActiveTestSession({
      test: test,
      problemDetails,
      timeRemaining: initialSeconds,
      activeProblemIndex: 0,
      answers: initialAnswers,
      violationWarnings: 0,
      status: "in_progress",
    });
    setTestRunOutput(null);
    setTestSampleResult(null);
    setTestSubmissionResult(null);
    setTabSwitchAlert(false);
  };

  const handleTestLanguageChange = (newLang) => {
    if (!activeTestSession || newLang === testEditorLanguage) return;
    const currentProb = activeTestSession.test.problems[activeTestSession.activeProblemIndex];
    if (!currentProb) return;
    const pid = currentProb.problem_id;
    const fullDetail = activeTestSession.problemDetails?.[pid] || currentProb;
    const currentCode = activeTestSession.answers[pid] || "";
    const ctxKey = `coding_test:${activeTestSession.test.id}`;

    if (
      isCodeModifiedFromStarter(
        currentCode,
        { [getDefaultFileNameForLang(testEditorLanguage)]: currentCode },
        testEditorLanguage,
        fullDetail
      )
    ) {
      const confirmed = window.confirm(
        `You have written code in ${testEditorLanguage.toUpperCase()}. Switching to ${newLang.toUpperCase()} will load the ${newLang.toUpperCase()} starter template for this question. Do you want to continue?`
      );
      if (!confirmed) return;
      saveCodeDraft(currentUser.id, ctxKey, pid, testEditorLanguage, {
        files: { [getDefaultFileNameForLang(testEditorLanguage)]: currentCode },
        activeFileName: getDefaultFileNameForLang(testEditorLanguage),
        code: currentCode,
      });
    }

    setTestEditorLanguage(newLang);
    setTestSampleResult(null);

    const nextAnswers = { ...activeTestSession.answers };
    for (const p of activeTestSession.test.problems) {
      const pDetail = activeTestSession.problemDetails?.[p.problem_id] || p;
      const savedDraft = loadSavedDraft(currentUser.id, ctxKey, p.problem_id, newLang);
      nextAnswers[p.problem_id] =
        savedDraft && savedDraft.code !== undefined
          ? savedDraft.code
          : getCleanStarterTemplate(newLang, pDetail);
    }
    setActiveTestSession((prev) => (prev ? { ...prev, answers: nextAnswers } : prev));
  };

  const handleResetTestCode = () => {
    if (!activeTestSession) return;
    const currentProb = activeTestSession.test.problems[activeTestSession.activeProblemIndex];
    if (!currentProb) return;
    const pid = currentProb.problem_id;
    const fullDetail = activeTestSession.problemDetails?.[pid] || currentProb;
    const currentCode = activeTestSession.answers[pid] || "";
    const ctxKey = `coding_test:${activeTestSession.test.id}`;

    if (
      isCodeModifiedFromStarter(
        currentCode,
        { [getDefaultFileNameForLang(testEditorLanguage)]: currentCode },
        testEditorLanguage,
        fullDetail
      )
    ) {
      const confirmed = window.confirm(
        "Are you sure you want to reset your code for this test question back to the starter template?"
      );
      if (!confirmed) return;
    }

    clearSavedDraft(currentUser.id, ctxKey, pid, testEditorLanguage);
    const tpl = getCleanStarterTemplate(testEditorLanguage, fullDetail);
    setActiveTestSession((prev) =>
      prev
        ? {
            ...prev,
            answers: {
              ...prev.answers,
              [pid]: tpl,
            },
          }
        : prev
    );
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

  // Run Test Samples in Real Isolated Sandbox
  const handleRunTestSampleCode = async (prob) => {
    const probId = prob.problem_id || prob.id;
    const code = activeTestSession.answers[probId] || "";
    setIsTestRunningSamples(true);
    setTestRunOutput(null);
    setTestSampleResult(null);

    try {
      const res = await runSampleCases({
        problem_id: probId,
        language: testEditorLanguage,
        code,
      });
      setTestSampleResult(res);
      const firstCase = res.results && res.results.length > 0 ? res.results[0] : null;
      setTestRunOutput({
        status: res.status,
        message: res.error_message
          ? res.error_message
          : `${res.passed_count}/${res.total_count} sample case(s) passed in ${res.execution_time || 0} ms.`,
        sampleInput: firstCase ? firstCase.input : "",
        expectedOutput: firstCase ? firstCase.expected_output : "",
        userOutput: firstCase ? firstCase.actual_output : "",
        passed: res.status === "Accepted",
        results: res.results || [],
      });
    } catch (err) {
      setTestSampleResult({
        status: "Internal Evaluation Error",
        error_message: err.message,
        passed_count: 0,
        total_count: 0,
        results: [],
      });
      setTestRunOutput({
        status: "Evaluation Error",
        message: err.message,
        passed: false,
      });
    } finally {
      setIsTestRunningSamples(false);
    }
  };

  // Save / Submit Individual Problem in Active Test & Poll Grader Verdict
  const handleSaveAndSubmitTestProblem = async (prob) => {
    const activeUserId = currentUser.id;
    const probId = prob.problem_id || prob.id;
    const code = activeTestSession.answers[probId] || "";
    setIsTestEvaluating(true);
    setTestSubmissionResult(null);
    setTestRunOutput({
      status: "Pending Evaluation",
      message: `Submitting "${prob.title}" to isolated grader...`,
      passed: false,
    });

    try {
      const created = await createSubmission({
        user_id: activeUserId,
        problem_id: probId,
        code: code,
        language: testEditorLanguage,
        submission_type: "coding_test",
        coding_test_id: activeTestSession.test.id,
      });
      setTestSubmissionResult(created);

      // Poll up to 12 times (~10 seconds) for grader evaluation
      let finalSub = created;
      for (let i = 0; i < 12; i++) {
        if (finalSub.status !== "Pending Evaluation" && finalSub.status !== "Running") break;
        await new Promise((r) => setTimeout(r, 900));
        finalSub = await fetchSubmissionById(created.id);
        setTestSubmissionResult(finalSub);
      }

      setTestRunOutput({
        status: finalSub.status,
        message: finalSub.error_message
          ? `${finalSub.status}: ${finalSub.error_message}`
          : `Verdict: ${finalSub.status} • Score: ${finalSub.score || 0}/${finalSub.max_score || 10} pts (${finalSub.passed_count || 0}/${finalSub.total_count || 0} test cases passed in ${finalSub.execution_time || 0} ms).`,
        passed: finalSub.status === "Accepted",
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
      const res = await completeCodingTest(testId, activeUserId);
      const testTitle = activeTestSession.test.title;
      setActiveTestSession(null);
      setTabSwitchAlert(false);

      if (isAutoSubmit) {
        alert(
          `⏰ Time is up! Your timed coding test "${testTitle}" has been submitted. Evaluated Score: ${res.score ?? 0}/${res.max_score ?? 0} pts • Total XP: ${res.xp ?? 0} XP.`
        );
      } else {
        setTestActionMsg({
          type: "success",
          text: `🎉 Test "${testTitle}" finalized! Evaluated Score: ${res.score ?? 0}/${res.max_score ?? 0} pts • Your Total XP is now ${res.xp ?? 0} XP.`,
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

  // Student Test Complete Handler
  const handleStudentCompleteTest = async (testId) => {
    const activeUserId = currentUser.id;
    setCompletingTestId(testId);
    setTestActionMsg(null);

    try {
      const res = await completeCodingTest(testId, activeUserId);
      setTestActionMsg({
        type: "success",
        text: `🎉 Test finalized! Evaluated Score: ${res.score ?? 0}/${res.max_score ?? 0} pts • Total XP: ${res.xp ?? 0} XP.`,
      });
      await loadCodingTests();
      await loadLeaderboardData();
    } catch (err) {
      setTestActionMsg({ type: "error", text: "Error: " + err.message });
    } finally {
      setCompletingTestId(null);
    }
  };

  // Academic Practical Creation & Tracking Handlers
  const togglePracticalStudentSelection = (id) => {
    setNewPractical((prev) => {
      const exists = prev.selectedStudentIds.includes(id);
      return {
        ...prev,
        selectedStudentIds: exists
          ? prev.selectedStudentIds.filter((s) => s !== id)
          : [...prev.selectedStudentIds, id],
      };
    });
  };

  const selectAllPracticalStudents = () => {
    const stuIds = usersList.filter((u) => u.role === "student").map((s) => s.id);
    setNewPractical((prev) => ({ ...prev, selectedStudentIds: stuIds }));
  };

  const handleCreatePracticalSubmit = async (e) => {
    e.preventDefault();
    setPracticalFormMsg(null);
    if (!newPractical.title.trim() || !newPractical.subject_name.trim()) {
      setPracticalFormMsg({ type: "error", text: "Please enter the Practical Title and Subject Name." });
      return;
    }

    setIsSubmittingNewPractical(true);
    try {
      const payload = {
        practical_number: parseInt(newPractical.practical_number, 10) || 1,
        title: newPractical.title.trim(),
        subject_name: newPractical.subject_name.trim(),
        subject_code: newPractical.subject_code?.trim() || null,
        semester: newPractical.semester?.trim() || null,
        description: newPractical.description?.trim() || null,
        objectives: newPractical.objectives?.trim() || null,
        problem_id: newPractical.problem_id ? parseInt(newPractical.problem_id, 10) : null,
        start_date: newPractical.start_date ? new Date(newPractical.start_date).toISOString() : null,
        deadline: newPractical.deadline ? new Date(newPractical.deadline).toISOString() : null,
        max_marks: parseFloat(newPractical.max_marks) || 10.0,
        student_ids: newPractical.selectedStudentIds,
      };
      const res = await createPractical(payload);
      setPracticalFormMsg({
        type: "success",
        text: `Practical #${res.practical_number}: "${res.title}" (${res.subject_name}) created and assigned to ${res.assigned_count} student(s)!`,
      });
      setNewPractical((prev) => ({
        practical_number: (parseInt(prev.practical_number, 10) || 1) + 1,
        title: "",
        subject_name: prev.subject_name,
        subject_code: prev.subject_code,
        semester: prev.semester,
        description: "",
        objectives: "",
        problem_id: "",
        start_date: "",
        deadline: "",
        max_marks: 10,
        selectedStudentIds: prev.selectedStudentIds,
      }));
      await loadPracticals();
    } catch (err) {
      setPracticalFormMsg({ type: "error", text: "Error creating practical: " + err.message });
    } finally {
      setIsSubmittingNewPractical(false);
    }
  };

  const toggleBulkPracticalId = (pid) => {
    setBulkPracticalAssign((prev) => {
      const exists = prev.selectedPracticalIds.includes(pid);
      return {
        ...prev,
        selectedPracticalIds: exists
          ? prev.selectedPracticalIds.filter((x) => x !== pid)
          : [...prev.selectedPracticalIds, pid],
      };
    });
  };

  const toggleBulkPracticalStudentId = (sid) => {
    setBulkPracticalAssign((prev) => {
      const exists = prev.selectedStudentIds.includes(sid);
      return {
        ...prev,
        selectedStudentIds: exists
          ? prev.selectedStudentIds.filter((x) => x !== sid)
          : [...prev.selectedStudentIds, sid],
      };
    });
  };

  const selectAllBulkPracticalStudents = () => {
    const stuIds = usersList.filter((u) => u.role === "student").map((s) => s.id);
    setBulkPracticalAssign((prev) => ({ ...prev, selectedStudentIds: stuIds }));
  };

  const handleBulkAssignPracticalsSubmit = async (e) => {
    e.preventDefault();
    setBulkPracticalMsg(null);
    if (bulkPracticalAssign.selectedPracticalIds.length === 0) {
      setBulkPracticalMsg({ type: "error", text: "Please select at least one practical to assign." });
      return;
    }
    if (bulkPracticalAssign.selectedStudentIds.length === 0) {
      setBulkPracticalMsg({ type: "error", text: "Please select at least one student." });
      return;
    }

    setIsSubmittingBulkPractical(true);
    try {
      const res = await bulkAssignPracticals({
        practical_ids: bulkPracticalAssign.selectedPracticalIds,
        student_ids: bulkPracticalAssign.selectedStudentIds,
        deadline: bulkPracticalAssign.deadline ? new Date(bulkPracticalAssign.deadline).toISOString() : null,
        objectives: bulkPracticalAssign.objectives?.trim() || null,
      });
      setBulkPracticalMsg({
        type: "success",
        text: `Successfully assigned ${res.length} practical(s) to ${bulkPracticalAssign.selectedStudentIds.length} student(s)!`,
      });
      setBulkPracticalAssign({
        selectedPracticalIds: [],
        selectedStudentIds: [],
        deadline: "",
        objectives: "",
      });
      await loadPracticals();
    } catch (err) {
      setBulkPracticalMsg({ type: "error", text: "Error assigning practicals: " + err.message });
    } finally {
      setIsSubmittingBulkPractical(false);
    }
  };

  const handleEvaluatePracticalStudentSubmit = async (e) => {
    e.preventDefault();
    if (!evaluatingPracticalStudent) return;
    setIsEvaluatingPractical(true);
    try {
      const updated = await evaluateStudentPractical(
        evaluatingPracticalStudent.practicalId,
        evaluatingPracticalStudent.studentId,
        {
          status: evaluatingPracticalStudent.status,
          marks_obtained:
            evaluatingPracticalStudent.marks_obtained !== "" && evaluatingPracticalStudent.marks_obtained !== null
              ? parseFloat(evaluatingPracticalStudent.marks_obtained)
              : null,
          teacher_feedback: evaluatingPracticalStudent.teacher_feedback || null,
        }
      );
      setSelectedPracticalForStudents(updated);
      setEvaluatingPracticalStudent(null);
      await loadPracticals();
    } catch (err) {
      alert("Error saving evaluation: " + err.message);
    } finally {
      setIsEvaluatingPractical(false);
    }
  };

  const handleStudentOpenAssignmentCoding = async (asgn, prob = null) => {
    if (!asgn || !asgn.problems || asgn.problems.length === 0) return;
    setSelectedPracticalWorkspace(null);
    setActivePracticalId(null);
    setSelectedAssignmentWorkspace(asgn);
    setActiveAssignmentId(asgn.id);
    setActiveTab("assignments");

    const chosen = prob || asgn.problems[0];
    const pid = chosen.id || chosen.problem_id;
    const targetProb =
      problems.find((p) => p.id === pid) || {
        id: pid,
        problem_id: pid,
        title: chosen.title,
        difficulty: chosen.difficulty || "Easy",
        topic: chosen.topic || "Coursework",
      };
    await openProblem(targetProb, null, `assignment:${asgn.id}`);
  };

  const handleStudentOpenPracticalCoding = async (prac) => {
    try {
      await startPractical(prac.id);
    } catch {
      // ignore if already started
    }
    setSelectedAssignmentWorkspace(null);
    setActiveAssignmentId(null);
    setSelectedPracticalWorkspace(prac);
    setActivePracticalId(prac.id);
    setActiveTab("assignments");
    if (prac.problem_id) {
      const targetProb =
        problems.find((p) => p.id === prac.problem_id) || {
          id: prac.problem_id,
          title: prac.problem_title || prac.title,
          difficulty: prac.problem_difficulty || "Medium",
          topic: prac.problem_topic || prac.subject_name,
        };
      await openProblem(targetProb, null, `practical:${prac.id}`);
    }
    await loadPracticals();
  };

  const handleStudentSubmitPracticalModal = async (e) => {
    e.preventDefault();
    if (!studentSubmittingPractical) return;
    setIsSubmittingPracticalReport(true);
    try {
      await submitPractical(studentSubmittingPractical.id, {
        submission_notes: practicalSubmissionDraft.submission_notes,
        attachment_filename: practicalSubmissionDraft.attachment_filename || null,
        attachment_content_b64: practicalSubmissionDraft.attachment_content_b64 || null,
      });
      setStudentSubmittingPractical(null);
      setPracticalSubmissionDraft({ submission_notes: "", attachment_filename: "", attachment_content_b64: "" });
      await loadPracticals();
    } catch (err) {
      alert("Error submitting practical: " + err.message);
    } finally {
      setIsSubmittingPracticalReport(false);
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
    if (tab === "practice") {
      setActiveAssignmentId(null);
      setActivePracticalId(null);
      setSelectedAssignmentWorkspace(null);
      setSelectedPracticalWorkspace(null);
      loadProblems();
    }
    if (tab === "assignments") {
      setSelectedAssignmentWorkspace(null);
      setSelectedPracticalWorkspace(null);
      loadAssignments();
      loadPracticals();
    }
    if (tab === "coding_tests") {
      setSelectedTestForDetails(null);
      loadCodingTests();
    }
    if (tab === "leaderboard") loadLeaderboardData();
    if (tab === "submissions") {
      loadSubmissions();
      loadUsers();
    }
    if (tab === "teacher_workspace") {
      loadProblems();
      loadAssignments();
      loadPracticals();
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
          {!isTeacher && activeTab === "practice" && (() => {
            const practiceStatusMap = {};
            submissions.forEach((s) => {
              if ((s.submission_type || "practice") === "practice") {
                const prev = practiceStatusMap[s.problem_id];
                if (!prev || s.status === "Accepted") {
                  practiceStatusMap[s.problem_id] = {
                    submitted: true,
                    status: s.status === "Accepted" ? "Accepted" : "Attempted",
                  };
                }
              }
            });

            return (
              <CodingWorkspace
                activityType="practice"
                activityTitle="Practice Problems"
                problems={problems}
                selectedProblem={selectedProblem}
                onSelectProblem={(p) => openProblem(p, null, "practice")}
                isLoadingProblems={isLoadingProblems}
                searchQuery={searchQuery}
                onSearchChange={handleSearchChange}
                difficultyFilter={difficultyFilter}
                onDifficultyFilterChange={handleFilterChange}
                showSearchAndFilters={true}
                problemStatusMap={practiceStatusMap}
                selectedLanguage={selectedLanguage}
                onLanguageChange={handleLanguageChange}
                editorCode={editorCode}
                onEditorCodeChange={handleEditorCodeChange}
                projectFiles={projectFiles}
                activeFileName={activeFileName}
                onSelectProjectFile={handleSelectProjectFile}
                newFileNameInput={newFileNameInput}
                onNewFileNameChange={setNewFileNameInput}
                onAddProjectFile={handleAddProjectFile}
                onDeleteProjectFile={handleDeleteProjectFile}
                onResetCode={handleResetCode}
                allowMultiFile={true}
                onRunSamples={handleRunPracticeSamples}
                onSubmitSolution={() => handleSubmitSolution({ type: "practice" })}
                isRunningSamples={isRunningSamples}
                isSubmitting={isSubmitting}
                sampleRunResult={sampleRunResult}
                lastSubmissionResult={lastSubmissionResult}
                submitButtonLabel="Submit Practice Solution"
                disablePaste={practicePasteRestricted}
                disableCopy={false}
                canTogglePracticePastePolicy={true}
                onTogglePracticePastePolicy={() => setPracticePasteRestricted((prev) => !prev)}
                securityStatus={securityStatus}
              />
            );
          })()}

          {/* ========================================================= */}
          {/* 3. ASSIGNMENTS & ACADEMIC PRACTICALS (STUDENT VIEW) */}
          {/* ========================================================= */}
          {!isTeacher && activeTab === "assignments" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
              {/* MANUAL / REPORT PRACTICAL SUBMISSION MODAL */}
              {studentSubmittingPractical && (
                <div className="card" style={{ border: "2px solid var(--primary)", backgroundColor: "#f8fafc" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                    <div>
                      <h4 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>
                        Submit Practical #{studentSubmittingPractical.practical_number}: {studentSubmittingPractical.title}
                      </h4>
                      <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
                        Subject: <strong>{studentSubmittingPractical.subject_name}</strong>
                        {studentSubmittingPractical.subject_code ? ` (${studentSubmittingPractical.subject_code})` : ""} • Max Marks:{" "}
                        <strong>{studentSubmittingPractical.max_marks || 10}</strong>
                      </div>
                    </div>
                    <button
                      type="button"
                      className="btn btn-outline btn-sm"
                      onClick={() => setStudentSubmittingPractical(null)}
                    >
                      Cancel
                    </button>
                  </div>

                  <form onSubmit={handleStudentSubmitPracticalModal}>
                    <div className="form-group">
                      <label className="form-label">Practical Implementation Summary / Observations / Code Notes *</label>
                      <textarea
                        rows={4}
                        className="form-textarea"
                        required
                        placeholder="Describe your practical implementation, algorithm steps, output summary, or paste your code/results..."
                        value={practicalSubmissionDraft.submission_notes}
                        onChange={(e) =>
                          setPracticalSubmissionDraft((prev) => ({
                            ...prev,
                            submission_notes: e.target.value,
                          }))
                        }
                      />
                    </div>

                    <div className="form-group">
                      <label className="form-label">Attach Practical File / Script / Report (Optional)</label>
                      <input
                        type="file"
                        className="form-input"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (!file) return;
                          const reader = new FileReader();
                          reader.onload = () => {
                            const resStr = String(reader.result || "");
                            const b64 = resStr.includes(",") ? resStr.split(",")[1] : "";
                            setPracticalSubmissionDraft((prev) => ({
                              ...prev,
                              attachment_filename: file.name,
                              attachment_content_b64: b64,
                            }));
                          };
                          reader.readAsDataURL(file);
                        }}
                      />
                      {practicalSubmissionDraft.attachment_filename && (
                        <div style={{ fontSize: 12, color: "#166534", marginTop: 4 }}>
                          Attached: <strong>{practicalSubmissionDraft.attachment_filename}</strong>
                        </div>
                      )}
                    </div>

                    <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
                      <button
                        type="button"
                        className="btn btn-outline"
                        onClick={() => setStudentSubmittingPractical(null)}
                      >
                        Cancel
                      </button>
                      <button type="submit" className="btn btn-primary" disabled={isSubmittingPracticalReport}>
                        <Send size={15} /> {isSubmittingPracticalReport ? "Submitting..." : "Submit Practical"}
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {/* VIEW A: DEDICATED ASSIGNMENT DETAILS & CODING WORKSPACE */}
              {selectedAssignmentWorkspace ? (
                (() => {
                  const asgn = selectedAssignmentWorkspace;
                  const asgnStatusMap = {};
                  submissions.forEach((s) => {
                    if (s.submission_type === "assignment" && s.assignment_id === asgn.id) {
                      const prev = asgnStatusMap[s.problem_id];
                      if (!prev || s.status === "Accepted") {
                        asgnStatusMap[s.problem_id] = {
                          submitted: true,
                          status: s.status === "Accepted" ? "Accepted" : "Submitted",
                        };
                      }
                    }
                  });
                  const pasteRestricted = asgn.allow_copy_paste === false;

                  return (
                    <div
                      data-testid="assignment-dedicated-workspace"
                      style={{ display: "flex", flexDirection: "column", gap: 14 }}
                    >
                      {/* Assignment Context Header Banner */}
                      <div
                        className="card"
                        style={{
                          padding: "14px 18px",
                          borderLeft: "4px solid var(--primary)",
                          backgroundColor: "#ffffff",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            flexWrap: "wrap",
                            gap: 12,
                          }}
                        >
                          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                            <button
                              type="button"
                              data-testid="back-to-assignments-btn"
                              className="btn btn-outline"
                              style={{ padding: "5px 10px", fontSize: 12 }}
                              onClick={() => {
                                setSelectedAssignmentWorkspace(null);
                                setActiveAssignmentId(null);
                              }}
                            >
                              <ArrowLeft size={14} /> Back to My Assignments
                            </button>

                            <div>
                              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                                <span
                                  style={{
                                    fontSize: 11,
                                    fontWeight: 700,
                                    textTransform: "uppercase",
                                    backgroundColor: "#eff6ff",
                                    color: "#1d4ed8",
                                    border: "1px solid #bfdbfe",
                                    padding: "2px 8px",
                                    borderRadius: 6,
                                  }}
                                >
                                  Assignment #{asgn.id}
                                </span>
                                <h3 style={{ fontSize: 17, fontWeight: 800, margin: 0 }}>
                                  {asgn.title}
                                </h3>
                                <AssignmentStatusBadge status={asgn.my_status || "Pending"} />
                              </div>
                              <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 3 }}>
                                <strong>Instructor:</strong> {asgn.creator_name || "Faculty"} •{" "}
                                <strong>Start Date:</strong>{" "}
                                {asgn.start_date
                                  ? new Date(asgn.start_date).toLocaleDateString()
                                  : "Immediate"}{" "}
                                • <strong>Deadline:</strong>{" "}
                                {asgn.deadline
                                  ? new Date(asgn.deadline).toLocaleDateString()
                                  : "No deadline"}{" "}
                                • <strong>Progress:</strong>{" "}
                                {asgn.progress_text ||
                                  `${asgn.submitted_problems_count || 0} of ${
                                    asgn.problems?.length || 0
                                  } problems submitted`}
                              </div>
                              {asgn.description && (
                                <div
                                  style={{
                                    fontSize: 12.5,
                                    color: "var(--text-main)",
                                    marginTop: 4,
                                  }}
                                >
                                  <strong>Instructions:</strong> {asgn.description}
                                </div>
                              )}
                            </div>
                          </div>

                          {/* Assigned Problems Switcher Pills */}
                          <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                            {asgn.problems.map((p, idx) => {
                              const isCurrent =
                                (selectedProblem?.id || selectedProblem?.problem_id) === p.problem_id;
                              const done = asgnStatusMap[p.problem_id]?.submitted;
                              return (
                                <button
                                  key={p.problem_id}
                                  type="button"
                                  onClick={() =>
                                    openProblem(
                                      {
                                        id: p.problem_id,
                                        problem_id: p.problem_id,
                                        title: p.title,
                                        difficulty: p.difficulty,
                                        topic: p.topic,
                                      },
                                      null,
                                      `assignment:${asgn.id}`
                                    )
                                  }
                                  className={`btn ${isCurrent ? "btn-primary" : "btn-outline"}`}
                                  style={{ padding: "4px 10px", fontSize: 12 }}
                                >
                                  {done && <CheckCircle2 size={12} />} P{idx + 1}: {p.title}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      </div>

                      {/* Assignment Coding Workspace */}
                      <CodingWorkspace
                        activityType="assignment"
                        activityTitle={`Assignment: ${asgn.title}`}
                        problems={asgn.problems}
                        selectedProblem={selectedProblem}
                        onSelectProblem={(p) =>
                          openProblem(
                            {
                              id: p.problem_id || p.id,
                              problem_id: p.problem_id || p.id,
                              title: p.title,
                              difficulty: p.difficulty,
                              topic: p.topic,
                            },
                            null,
                            `assignment:${asgn.id}`
                          )
                        }
                        isLoadingProblems={false}
                        showSearchAndFilters={false}
                        problemStatusMap={asgnStatusMap}
                        selectedLanguage={selectedLanguage}
                        onLanguageChange={handleLanguageChange}
                        editorCode={editorCode}
                        onEditorCodeChange={handleEditorCodeChange}
                        projectFiles={projectFiles}
                        activeFileName={activeFileName}
                        onSelectProjectFile={handleSelectProjectFile}
                        newFileNameInput={newFileNameInput}
                        onNewFileNameChange={setNewFileNameInput}
                        onAddProjectFile={handleAddProjectFile}
                        onDeleteProjectFile={handleDeleteProjectFile}
                        onResetCode={handleResetCode}
                        allowMultiFile={true}
                        onRunSamples={handleRunPracticeSamples}
                        onSubmitSolution={() =>
                          handleSubmitSolution({
                            type: "assignment",
                            assignmentId: asgn.id,
                          })
                        }
                        isRunningSamples={isRunningSamples}
                        isSubmitting={isSubmitting}
                        sampleRunResult={sampleRunResult}
                        lastSubmissionResult={lastSubmissionResult}
                        submitButtonLabel="Submit Assignment Solution"
                        disablePaste={pasteRestricted}
                        disableCopy={pasteRestricted}
                        securityStatus={securityStatus}
                      />
                    </div>
                  );
                })()
              ) : selectedPracticalWorkspace ? (
                /* VIEW B: DEDICATED ACADEMIC PRACTICAL CODING WORKSPACE */
                (() => {
                  const prac = selectedPracticalWorkspace;
                  const pracProblems = prac.problem_id
                    ? [
                        {
                          id: prac.problem_id,
                          problem_id: prac.problem_id,
                          title: prac.problem_title || prac.title,
                          difficulty: prac.problem_difficulty || "Medium",
                          topic: prac.problem_topic || prac.subject_name,
                        },
                      ]
                    : [];

                  return (
                    <div
                      data-testid="practical-dedicated-workspace"
                      style={{ display: "flex", flexDirection: "column", gap: 14 }}
                    >
                      <div
                        className="card"
                        style={{
                          padding: "14px 18px",
                          borderLeft: "4px solid #0ea5e9",
                          backgroundColor: "#ffffff",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            flexWrap: "wrap",
                            gap: 12,
                          }}
                        >
                          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                            <button
                              type="button"
                              className="btn btn-outline"
                              style={{ padding: "5px 10px", fontSize: 12 }}
                              onClick={() => {
                                setSelectedPracticalWorkspace(null);
                                setActivePracticalId(null);
                              }}
                            >
                              <ArrowLeft size={14} /> Back to My Assignments
                            </button>

                            <div>
                              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                                <span
                                  style={{
                                    fontSize: 11,
                                    fontWeight: 700,
                                    backgroundColor: "#e0f2fe",
                                    color: "#0369a1",
                                    border: "1px solid #bae6fd",
                                    padding: "2px 8px",
                                    borderRadius: 6,
                                  }}
                                >
                                  Practical #{prac.practical_number}
                                </span>
                                <h3 style={{ fontSize: 17, fontWeight: 800, margin: 0 }}>
                                  {prac.title}
                                </h3>
                                <AssignmentStatusBadge status={prac.my_status || "In Progress"} />
                              </div>
                              <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 3 }}>
                                <strong>Subject:</strong> {prac.subject_name}
                                {prac.subject_code ? ` (${prac.subject_code})` : ""} •{" "}
                                <strong>Deadline:</strong>{" "}
                                {prac.deadline
                                  ? new Date(prac.deadline).toLocaleDateString()
                                  : "No deadline"}{" "}
                                • <strong>Max Marks:</strong> {prac.max_marks || 10} pts
                              </div>
                              {prac.objectives && (
                                <div style={{ fontSize: 12, color: "var(--text-main)", marginTop: 3 }}>
                                  <strong>Objectives:</strong> {prac.objectives}
                                </div>
                              )}
                            </div>
                          </div>

                          <button
                            type="button"
                            className="btn btn-outline"
                            style={{ padding: "5px 12px", fontSize: 12 }}
                            onClick={() => {
                              setStudentSubmittingPractical(prac);
                              setPracticalSubmissionDraft({
                                submission_notes: prac.my_submission_notes || "",
                                attachment_filename: prac.my_attachment_filename || "",
                                attachment_content_b64: "",
                              });
                            }}
                          >
                            Attach Practical Notes / Report
                          </button>
                        </div>
                      </div>

                      <CodingWorkspace
                        activityType="practical"
                        activityTitle={`Practical #${prac.practical_number}: ${prac.title}`}
                        problems={pracProblems}
                        selectedProblem={selectedProblem}
                        onSelectProblem={(p) =>
                          openProblem(p, null, `practical:${prac.id}`)
                        }
                        isLoadingProblems={false}
                        showSearchAndFilters={false}
                        selectedLanguage={selectedLanguage}
                        onLanguageChange={handleLanguageChange}
                        editorCode={editorCode}
                        onEditorCodeChange={handleEditorCodeChange}
                        projectFiles={projectFiles}
                        activeFileName={activeFileName}
                        onSelectProjectFile={handleSelectProjectFile}
                        newFileNameInput={newFileNameInput}
                        onNewFileNameChange={setNewFileNameInput}
                        onAddProjectFile={handleAddProjectFile}
                        onDeleteProjectFile={handleDeleteProjectFile}
                        onResetCode={handleResetCode}
                        allowMultiFile={true}
                        onRunSamples={handleRunPracticeSamples}
                        onSubmitSolution={() =>
                          handleSubmitSolution({
                            type: "practical",
                            practicalId: prac.id,
                          })
                        }
                        isRunningSamples={isRunningSamples}
                        isSubmitting={isSubmitting}
                        sampleRunResult={sampleRunResult}
                        lastSubmissionResult={lastSubmissionResult}
                        submitButtonLabel="Submit Practical Solution"
                        disablePaste={false}
                        disableCopy={false}
                        securityStatus={securityStatus}
                      />
                    </div>
                  );
                })()
              ) : (
                <>
                  {/* SECTION A: ASSIGNED CODING COURSEWORK */}
                  <div className="card" data-testid="my-assignments-page">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                      <div>
                        <h3 style={{ fontSize: 18, fontWeight: 700 }}>
                          Teacher Assigned Coursework ({assignments.length})
                        </h3>
                        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                          Official coding assignments assigned by faculty. Open any assignment to view instructions and solve its problems in the dedicated assignment workspace.
                        </p>
                      </div>
                      <button
                        className="btn btn-outline"
                        onClick={() => {
                          loadAssignments();
                          loadPracticals();
                        }}
                      >
                        Refresh
                      </button>
                    </div>

                    {assignments.length === 0 ? (
                      <div style={{ textAlign: "center", padding: "32px 0", color: "var(--text-muted)" }}>
                        No coding assignments have been assigned to you yet.
                      </div>
                    ) : (
                      <div className="table-container">
                        <table className="clan-table">
                          <thead>
                            <tr>
                              <th>Assignment</th>
                              <th>Instructor</th>
                              <th>Assigned Problems (Click to Solve)</th>
                              <th>Start Date</th>
                              <th>Deadline</th>
                              <th>Progress</th>
                              <th>Status</th>
                              <th>Action</th>
                            </tr>
                          </thead>
                          <tbody>
                            {assignments.map((asgn) => (
                              <tr key={asgn.id}>
                                <td>
                                  <div style={{ fontWeight: 700, color: "var(--text-main)" }}>
                                    {asgn.title}
                                  </div>
                                  {asgn.description && (
                                    <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
                                      {asgn.description}
                                    </div>
                                  )}
                                </td>
                                <td>{asgn.creator_name}</td>
                                <td>
                                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                                    {asgn.problems.map((p) => (
                                      <button
                                        key={p.problem_id}
                                        type="button"
                                        onClick={() => handleStudentOpenAssignmentCoding(asgn, p)}
                                        style={{
                                          fontSize: 11,
                                          backgroundColor: "#eff6ff",
                                          color: "#1d4ed8",
                                          border: "1px solid #bfdbfe",
                                          padding: "3px 8px",
                                          borderRadius: 6,
                                          fontWeight: 600,
                                          cursor: "pointer",
                                        }}
                                        title={`Open "${p.title}" in the Assignment Coding Workspace`}
                                      >
                                        {p.title}
                                      </button>
                                    ))}
                                  </div>
                                </td>
                                <td style={{ whiteSpace: "nowrap", fontSize: 12, color: "var(--text-muted)" }}>
                                  {asgn.start_date
                                    ? new Date(asgn.start_date).toLocaleDateString()
                                    : "Immediate"}
                                </td>
                                <td style={{ whiteSpace: "nowrap", fontSize: 12 }}>
                                  {asgn.deadline
                                    ? new Date(asgn.deadline).toLocaleDateString()
                                    : "No deadline"}
                                </td>
                                <td style={{ fontSize: 12, color: "var(--text-muted)", fontWeight: 600 }}>
                                  {asgn.progress_text ||
                                    `${asgn.submitted_problems_count || 0} of ${asgn.problems.length} problems submitted`}
                                </td>
                                <td>
                                  <AssignmentStatusBadge status={asgn.my_status || "Pending"} />
                                </td>
                                <td>
                                  <button
                                    type="button"
                                    data-testid={`open-assignment-${asgn.id}`}
                                    className="btn btn-primary"
                                    style={{ padding: "5px 12px", fontSize: 12 }}
                                    onClick={() => handleStudentOpenAssignmentCoding(asgn)}
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

                  {/* SECTION B: ACADEMIC PRACTICALS (SYLLABUS PRACTICAL COURSEWORK) */}
                  <div className="card">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                      <div>
                        <h3 style={{ fontSize: 18, fontWeight: 700 }}>
                          Academic Curriculum Practicals ({practicals.length})
                        </h3>
                        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                          Subject-wise laboratory practicals assigned from your academic syllabus. Solve the linked coding problem or submit your practical completion record.
                        </p>
                      </div>
                    </div>

                    {practicals.length === 0 ? (
                      <div style={{ textAlign: "center", padding: "32px 0", color: "var(--text-muted)" }}>
                        No academic syllabus practicals assigned to you yet.
                      </div>
                    ) : (
                      <div className="table-container">
                        <table className="clan-table">
                          <thead>
                            <tr>
                              <th>Practical</th>
                              <th>Subject</th>
                              <th>Objectives / Instructions</th>
                              <th>Linked Problem</th>
                              <th>Deadline</th>
                              <th>Status</th>
                              <th>Marks</th>
                              <th>Action</th>
                            </tr>
                          </thead>
                          <tbody>
                            {practicals.map((prac) => (
                              <tr key={prac.id}>
                                <td>
                                  <div style={{ fontWeight: 700, color: "var(--text-main)" }}>
                                    Practical {prac.practical_number}: {prac.title}
                                  </div>
                                  {prac.description && (
                                    <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
                                      {prac.description}
                                    </div>
                                  )}
                                </td>
                                <td>
                                  <div style={{ fontWeight: 600 }}>{prac.subject_name}</div>
                                  <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                                    {[prac.subject_code, prac.semester].filter(Boolean).join(" • ")}
                                  </div>
                                </td>
                                <td style={{ maxWidth: 260, fontSize: 12, color: "var(--text-muted)" }}>
                                  {prac.objectives || "Follow standard lab instructions."}
                                  {prac.my_teacher_feedback && (
                                    <div style={{ marginTop: 4, color: "#1e40af", fontWeight: 600 }}>
                                      Feedback: {prac.my_teacher_feedback}
                                    </div>
                                  )}
                                </td>
                                <td>
                                  {prac.problem_id ? (
                                    <span
                                      style={{
                                        fontSize: 11,
                                        backgroundColor: "#eff6ff",
                                        color: "#1d4ed8",
                                        border: "1px solid #bfdbfe",
                                        padding: "2px 8px",
                                        borderRadius: 6,
                                        fontWeight: 600,
                                      }}
                                    >
                                      {prac.problem_title || `Problem #${prac.problem_id}`}
                                    </span>
                                  ) : (
                                    <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Lab / Manual</span>
                                  )}
                                </td>
                                <td style={{ whiteSpace: "nowrap", fontSize: 12 }}>
                                  {prac.deadline ? new Date(prac.deadline).toLocaleDateString() : "No deadline"}
                                </td>
                                <td>
                                  <AssignmentStatusBadge status={prac.my_status || "Not Started"} />
                                </td>
                                <td style={{ fontWeight: 700, fontSize: 12 }}>
                                  {prac.my_marks_obtained != null
                                    ? `${prac.my_marks_obtained}/${prac.max_marks || 10}`
                                    : `— / ${prac.max_marks || 10}`}
                                </td>
                                <td>
                                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                                    {prac.problem_id && (
                                      <button
                                        type="button"
                                        className="btn btn-primary"
                                        style={{ padding: "4px 10px", fontSize: 11 }}
                                        onClick={() => handleStudentOpenPracticalCoding(prac)}
                                      >
                                        Code & Run
                                      </button>
                                    )}
                                    <button
                                      type="button"
                                      className="btn btn-outline"
                                      style={{ padding: "4px 10px", fontSize: 11 }}
                                      onClick={() => {
                                        setStudentSubmittingPractical(prac);
                                        setPracticalSubmissionDraft({
                                          submission_notes: prac.my_submission_notes || "",
                                          attachment_filename: prac.my_attachment_filename || "",
                                          attachment_content_b64: "",
                                        });
                                      }}
                                    >
                                      {prac.my_status && prac.my_status !== "Not Started"
                                        ? "Update Submission"
                                        : "Submit Practical"}
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          )}

          {/* ========================================================= */}
          {/* 4. CODING TESTS SECTION */}
          {/* ========================================================= */}
          {!isTeacher && activeTab === "coding_tests" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {/* IF ACTIVE TEST SESSION IS RUNNING, SHOW SECURE PROCTORED TEST ENVIRONMENT */}
              {activeTestSession ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  {/* PROCTORED SECURITY BANNER */}
                  <div
                    style={{
                      backgroundColor: "#1e293b",
                      color: "white",
                      borderRadius: 12,
                      padding: "14px 20px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      flexWrap: "wrap",
                      gap: 12,
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
                        <Shield size={22} />
                      </div>
                      <div>
                        <div style={{ fontSize: 17, fontWeight: 800, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
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
                          Official Assessment Mode • Copy-paste restrictions and tab-switch monitoring are active.
                        </div>
                      </div>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                      {/* TIMER DISPLAY */}
                      <div
                        data-testid="coding-test-timer"
                        style={{
                          textAlign: "right",
                          backgroundColor: activeTestSession.timeRemaining < 300 ? "#7f1d1d" : "#0f172a",
                          padding: "6px 14px",
                          borderRadius: 8,
                          border: activeTestSession.timeRemaining < 300 ? "1px solid #ef4444" : "1px solid #334155",
                        }}
                      >
                        <div style={{ fontSize: 10, color: "#94a3b8", textTransform: "uppercase", fontWeight: 700 }}>
                          Remaining Time
                        </div>
                        <div
                          style={{
                            fontSize: 20,
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
                        type="button"
                        data-testid="finish-submit-test-btn"
                        className="btn btn-primary"
                        style={{
                          backgroundColor: "#16a34a",
                          borderColor: "#16a34a",
                          padding: "9px 16px",
                          fontWeight: 700,
                          fontSize: 13,
                        }}
                        onClick={() => {
                          if (
                            window.confirm(
                              "Are you sure you want to finish and submit this test? Your score and XP will be calculated from your evaluated solutions."
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
                        padding: "10px 14px",
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
                        type="button"
                        className="btn btn-outline"
                        style={{ padding: "2px 8px", fontSize: 11, color: "#991b1b", borderColor: "#fca5a5" }}
                        onClick={() => setTabSwitchAlert(false)}
                      >
                        Dismiss
                      </button>
                    </div>
                  )}

                  {/* UNIFIED THREE-PANEL CODING WORKSPACE FOR ACTIVE CODING TEST */}
                  {(() => {
                    const currentProb =
                      activeTestSession.test.problems[activeTestSession.activeProblemIndex];
                    if (!currentProb) return null;
                    const fullProblemDetail =
                      activeTestSession.problemDetails?.[currentProb.problem_id] ||
                      problems.find((p) => p.id === currentProb.problem_id) ||
                      currentProb;

                    const testStatusMap = {};
                    submissions.forEach((s) => {
                      if (
                        s.submission_type === "coding_test" &&
                        s.coding_test_id === activeTestSession.test.id
                      ) {
                        const prev = testStatusMap[s.problem_id];
                        if (!prev || s.status === "Accepted") {
                          testStatusMap[s.problem_id] = {
                            submitted: true,
                            status: s.status === "Accepted" ? "Accepted" : "Evaluated",
                          };
                        }
                      }
                    });

                    const isPasteBlocked =
                      activeTestSession.status === "in_progress" &&
                      activeTestSession.test.allow_copy_paste !== true;
                    const activeFname = getDefaultFileNameForLang(testEditorLanguage);
                    const currentAnswerCode =
                      activeTestSession.answers[currentProb.problem_id] || "";

                    return (
                      <CodingWorkspace
                        activityType="coding_test"
                        activityTitle={activeTestSession.test.title}
                        problems={activeTestSession.test.problems}
                        selectedProblem={fullProblemDetail}
                        onSelectProblem={(p, idx) => {
                          setActiveTestSession((prev) => ({
                            ...prev,
                            activeProblemIndex: idx,
                          }));
                          setTestRunOutput(null);
                          setTestSampleResult(null);
                          setTestSubmissionResult(null);
                        }}
                        isLoadingProblems={false}
                        showSearchAndFilters={false}
                        problemStatusMap={testStatusMap}
                        selectedLanguage={testEditorLanguage}
                        onLanguageChange={handleTestLanguageChange}
                        editorCode={currentAnswerCode}
                        onEditorCodeChange={(val) => {
                          setActiveTestSession((prev) => {
                            if (!prev) return prev;
                            return {
                              ...prev,
                              answers: {
                                ...prev.answers,
                                [currentProb.problem_id]: val,
                              },
                            };
                          });
                          saveCodeDraft(
                            currentUser.id,
                            `coding_test:${activeTestSession.test.id}`,
                            currentProb.problem_id,
                            testEditorLanguage,
                            {
                              files: { [activeFname]: val },
                              activeFileName: activeFname,
                              code: val,
                            }
                          );
                        }}
                        projectFiles={{ [activeFname]: currentAnswerCode }}
                        activeFileName={activeFname}
                        allowMultiFile={false}
                        onResetCode={handleResetTestCode}
                        onRunSamples={() => handleRunTestSampleCode(currentProb)}
                        onSubmitSolution={() => handleSaveAndSubmitTestProblem(currentProb)}
                        isRunningSamples={isTestRunningSamples}
                        isSubmitting={isTestEvaluating}
                        sampleRunResult={testSampleResult}
                        lastSubmissionResult={testSubmissionResult}
                        submitButtonLabel="Save & Evaluate Question"
                        submitButtonIcon="save"
                        disablePaste={isPasteBlocked}
                        disableCopy={isPasteBlocked}
                        securityStatus={securityStatus}
                      />
                    );
                  })()}
                </div>
              ) : selectedTestForDetails ? (
                /* VIEW 2: CODING TEST DETAILS PAGE BEFORE STARTING */
                <div className="card" data-testid="coding-test-details-card">
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "flex-start",
                      flexWrap: "wrap",
                      gap: 12,
                      marginBottom: 16,
                    }}
                  >
                    <div>
                      <button
                        type="button"
                        className="btn btn-outline"
                        style={{ padding: "4px 10px", fontSize: 12, marginBottom: 10 }}
                        onClick={() => setSelectedTestForDetails(null)}
                      >
                        <ArrowLeft size={14} /> Back to All Coding Tests
                      </button>
                      <h3 style={{ fontSize: 20, fontWeight: 800, margin: 0 }}>
                        {selectedTestForDetails.title}
                      </h3>
                      <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>
                        <strong>Designed by:</strong> {selectedTestForDetails.creator_name || "Faculty"} •{" "}
                        <strong>Duration:</strong> {selectedTestForDetails.duration} Minutes •{" "}
                        <strong>Questions:</strong> {selectedTestForDetails.problems?.length || 0} •{" "}
                        <strong>Reward:</strong> +{selectedTestForDetails.xp_reward || 10} XP
                      </div>
                    </div>

                    <button
                      type="button"
                      data-testid="confirm-start-test-btn"
                      className="btn btn-primary"
                      style={{
                        padding: "10px 20px",
                        fontSize: 14,
                        fontWeight: 700,
                        backgroundColor: "#2563eb",
                      }}
                      onClick={() => handleStartTest(selectedTestForDetails)}
                    >
                      <Play size={16} /> Start Timed Test ({selectedTestForDetails.duration}m)
                    </button>
                  </div>

                  {selectedTestForDetails.description && (
                    <div
                      style={{
                        backgroundColor: "#f8fafc",
                        border: "1px solid var(--border-light)",
                        borderRadius: 8,
                        padding: 14,
                        marginBottom: 16,
                        fontSize: 13.5,
                      }}
                    >
                      <strong>Instructions & Guidelines:</strong>
                      <div style={{ marginTop: 4, color: "#334155", whiteSpace: "pre-line" }}>
                        {selectedTestForDetails.description}
                      </div>
                    </div>
                  )}

                  <div
                    style={{
                      backgroundColor: "#fef2f2",
                      border: "1px solid #fecaca",
                      borderRadius: 8,
                      padding: 12,
                      marginBottom: 16,
                      fontSize: 12.5,
                      color: "#991b1b",
                    }}
                  >
                    <strong>Assessment Integrity Policy:</strong>{" "}
                    {selectedTestForDetails.allow_copy_paste
                      ? "Timer countdown and tab-switch monitoring are active during this test."
                      : "Strict copy-paste prevention is enabled in the code editor during this test. You must type your solution manually."}
                  </div>

                  <div>
                    <h4 style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>
                      Included Questions ({selectedTestForDetails.problems?.length || 0})
                    </h4>
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {(selectedTestForDetails.problems || []).map((p, idx) => (
                        <div
                          key={p.problem_id}
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            padding: "10px 14px",
                            borderRadius: 8,
                            border: "1px solid var(--border-light)",
                            backgroundColor: "#fafbfc",
                          }}
                        >
                          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                            <span style={{ fontWeight: 700, fontSize: 13 }}>
                              Q{idx + 1}: {p.title}
                            </span>
                            <span
                              className={`badge badge-${(p.difficulty || "Easy").toLowerCase()}`}
                              style={{ fontSize: 11 }}
                            >
                              {p.difficulty}
                            </span>
                            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                              {p.topic}
                            </span>
                          </div>
                          <span style={{ fontSize: 12, fontWeight: 700, color: "var(--primary)" }}>
                            {p.marks || 10} pts
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
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

                  {/* VIEW 1: AVAILABLE CODING TESTS */}
                  <div className="card" data-testid="coding-tests-page">
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
                                  {["submitted", "completed"].includes(t.my_status) && t.xp_awarded ? (
                                    <span
                                      style={{
                                        backgroundColor: "#dcfce7",
                                        color: "#166534",
                                        border: "1px solid #86efac",
                                        fontWeight: 700,
                                        fontSize: 12,
                                        padding: "4px 10px",
                                        borderRadius: 6,
                                        display: "inline-flex",
                                        alignItems: "center",
                                        gap: 5,
                                      }}
                                    >
                                      <CheckCircle2 size={13} color="#16a34a" /> +{t.xp_awarded_amount || 10} XP Awarded
                                    </span>
                                  ) : (
                                    <span
                                      style={{
                                        backgroundColor: "#fef3c7",
                                        color: "#92400e",
                                        border: "1px solid #fde68a",
                                        fontWeight: 700,
                                        fontSize: 12,
                                        padding: "3px 8px",
                                        borderRadius: 6,
                                        display: "inline-flex",
                                        alignItems: "center",
                                        gap: 4,
                                      }}
                                    >
                                      <Award size={13} /> +{t.xp_reward || 10} XP
                                    </span>
                                  )}
                                </td>
                                <td>
                                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                                    {["submitted", "completed"].includes(t.my_status) ? (
                                      <span
                                        className="badge badge-easy"
                                        style={{
                                          display: "inline-flex",
                                          alignItems: "center",
                                          gap: 5,
                                          backgroundColor: "#dcfce7",
                                          color: "#166534",
                                          border: "1px solid #86efac",
                                          fontWeight: 700,
                                          padding: "4px 10px",
                                        }}
                                      >
                                        <CheckCircle2 size={13} /> Completed
                                      </span>
                                    ) : (
                                      <>
                                        <button
                                          type="button"
                                          className="btn btn-outline"
                                          style={{ padding: "5px 10px", fontSize: 12 }}
                                          onClick={() => setSelectedTestForDetails(t)}
                                        >
                                          View Details
                                        </button>
                                        <button
                                          type="button"
                                          data-testid={`start-test-${t.id}`}
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
                                      </>
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
                </>
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
          {/* 6. SUBMISSIONS HISTORY & CODE / EVALUATION REVIEW */}
          {/* ========================================================= */}
          {activeTab === "submissions" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {selectedSubmissionDetail && (
                <div className="card" style={{ border: "2px solid var(--primary)", backgroundColor: "#f8fafc" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                        <h3 style={{ fontSize: 17, fontWeight: 800, margin: 0 }}>
                          Submission #{selectedSubmissionDetail.id} — {selectedSubmissionDetail.problem_title}
                        </h3>
                        <StatusBadge status={selectedSubmissionDetail.status} />
                        <span style={{ fontSize: 13, fontWeight: 700, color: "var(--primary)" }}>
                          Score: {selectedSubmissionDetail.score ?? 0}/{selectedSubmissionDetail.max_score ?? 10} pts
                        </span>
                        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                          • {selectedSubmissionDetail.passed_count ?? 0}/{selectedSubmissionDetail.total_count ?? 0} test cases passed
                        </span>
                        {selectedSubmissionDetail.execution_time != null && (
                          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                            • {selectedSubmissionDetail.execution_time} ms
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
                        {isTeacher && (
                          <>
                            <strong>Student:</strong> {userName(selectedSubmissionDetail.user_id)} •{" "}
                          </>
                        )}
                        <strong>Language:</strong> {selectedSubmissionDetail.language} •{" "}
                        <strong>Context:</strong> {selectedSubmissionDetail.submission_type} •{" "}
                        <strong>Submitted:</strong> {new Date(selectedSubmissionDetail.submitted_at).toLocaleString()}
                        {selectedSubmissionDetail.hidden_summary && (
                          <>
                            {" "}
                            • <strong>Hidden Tests:</strong> {selectedSubmissionDetail.hidden_summary.passed}/
                            {selectedSubmissionDetail.hidden_summary.total} passed
                          </>
                        )}
                      </div>
                    </div>
                    <button
                      type="button"
                      className="btn btn-outline"
                      onClick={() => setSelectedSubmissionDetail(null)}
                    >
                      Close Review
                    </button>
                  </div>

                  {selectedSubmissionDetail.error_message && (
                    <div style={{ marginBottom: 12 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: "#991b1b", marginBottom: 4 }}>
                        Compiler / Runtime / Sandbox Error Output:
                      </div>
                      <pre
                        style={{
                          backgroundColor: "#1e293b",
                          color: "#f87171",
                          padding: 10,
                          borderRadius: 8,
                          fontSize: 12,
                          whiteSpace: "pre-wrap",
                          margin: 0,
                        }}
                      >
                        {selectedSubmissionDetail.error_message}
                      </pre>
                    </div>
                  )}

                  <div style={{ marginBottom: 12 }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-main)", marginBottom: 4 }}>
                      Submitted Source Code ({selectedSubmissionDetail.language}):
                    </div>
                    <pre
                      style={{
                        backgroundColor: "#0f172a",
                        color: "#e2e8f0",
                        padding: 12,
                        borderRadius: 8,
                        fontSize: 12,
                        fontFamily: "var(--font-mono)",
                        whiteSpace: "pre-wrap",
                        maxHeight: 260,
                        overflowY: "auto",
                        margin: 0,
                      }}
                    >
                      {selectedSubmissionDetail.code}
                    </pre>
                  </div>

                  {selectedSubmissionDetail.public_results?.length > 0 && (
                    <div style={{ marginBottom: 12 }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-main)", marginBottom: 6 }}>
                        Public Test Case Results ({selectedSubmissionDetail.public_results.length}):
                      </div>
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 8 }}>
                        {selectedSubmissionDetail.public_results.map((pr, idx) => (
                          <div
                            key={pr.test_case_id || idx}
                            style={{
                              backgroundColor: "white",
                              border: "1px solid var(--border-light)",
                              borderRadius: 6,
                              padding: 8,
                              fontSize: 11,
                            }}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between", fontWeight: 700, marginBottom: 4 }}>
                              <span>Public Case #{idx + 1}</span>
                              <StatusBadge status={pr.status} />
                            </div>
                            <div style={{ fontFamily: "monospace" }}>
                              <div><strong>Input:</strong> {pr.input || "(empty)"}</div>
                              <div><strong>Expected:</strong> {pr.expected_output}</div>
                              <div><strong>Actual:</strong> {pr.actual_output ?? "(none)"}</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {isTeacher && selectedSubmissionDetail.teacher_hidden_results?.length > 0 && (
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 700, color: "#1e40af", marginBottom: 6 }}>
                        Teacher-Only Hidden Test Case Breakdown ({selectedSubmissionDetail.teacher_hidden_results.length}):
                      </div>
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 8 }}>
                        {selectedSubmissionDetail.teacher_hidden_results.map((hr, idx) => (
                          <div
                            key={hr.test_case_id || idx}
                            style={{
                              backgroundColor: "#eff6ff",
                              border: "1px solid #bfdbfe",
                              borderRadius: 6,
                              padding: 8,
                              fontSize: 11,
                            }}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between", fontWeight: 700, marginBottom: 4 }}>
                              <span>Hidden Case #{idx + 1}</span>
                              <StatusBadge status={hr.status} />
                            </div>
                            <div style={{ fontFamily: "monospace" }}>
                              <div><strong>Actual Output:</strong> {hr.actual_output ?? "(none)"}</div>
                              <div><strong>Runtime:</strong> {hr.execution_time ?? 0} ms</div>
                              {hr.error_message && <div style={{ color: "#b91c1c" }}>{hr.error_message}</div>}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              <div className="card">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 16 }}>
                  <div>
                    <h3 style={{ fontSize: 18, fontWeight: 700 }}>
                      {isTeacher
                        ? selectedTeacherStudent
                          ? `Submission History: ${selectedTeacherStudent.student_name}`
                          : `Class Submissions — Grouped by Student (${teacherGroupedStudents.length} Students)`
                        : selectedStudentProblemGroup
                        ? `Attempt History: ${selectedStudentProblemGroup.problem_title}`
                        : `My Submission History — Grouped by Problem (${studentGroupedProblems.length} Problems)`}
                    </h3>
                    <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                      {isTeacher
                        ? selectedTeacherStudent
                          ? `Showing all historical submissions for ${selectedTeacherStudent.student_name} (${selectedTeacherStudent.student_email || "Student"}). Click Review / Code on any attempt to inspect source code and test-case results.`
                          : "Consolidated submission summary per student. Click a student's name or View History to inspect all of their historical attempts."
                        : selectedStudentProblemGroup
                        ? `All of your previous attempts for "${selectedStudentProblemGroup.problem_title}" (${selectedStudentProblemGroup.context_label}). Click Review / Code to inspect your submitted code.`
                        : "Consolidated view of every unique problem you have attempted. Click a problem title or View History to inspect all your previous attempts."}
                    </p>
                  </div>

                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    {isTeacher && selectedTeacherStudent && (
                      <button
                        type="button"
                        className="btn btn-outline"
                        onClick={() => {
                          setSelectedTeacherStudent(null);
                          setSelectedSubmissionDetail(null);
                        }}
                      >
                        <ArrowLeft size={15} /> Back to All Students
                      </button>
                    )}
                    {!isTeacher && selectedStudentProblemGroup && (
                      <button
                        type="button"
                        className="btn btn-outline"
                        onClick={() => {
                          setSelectedStudentProblemGroup(null);
                          setSelectedSubmissionDetail(null);
                        }}
                      >
                        <ArrowLeft size={15} /> Back to Grouped Problems
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn btn-outline"
                      onClick={() => loadSubmissions()}
                    >
                      Refresh History
                    </button>
                  </div>
                </div>

                {/* FILTER & SORT CONTROLS BAR */}
                <div
                  style={{
                    backgroundColor: "#f8fafc",
                    border: "1px solid var(--border-light)",
                    borderRadius: 8,
                    padding: 12,
                    marginBottom: 16,
                    display: "flex",
                    flexDirection: "column",
                    gap: 10,
                  }}
                >
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: isTeacher
                        ? "repeat(auto-fit, minmax(150px, 1fr))"
                        : "repeat(auto-fit, minmax(170px, 1fr))",
                      gap: 10,
                    }}
                  >
                    {isTeacher && (
                      <div>
                        <label className="form-label" style={{ fontSize: 11, marginBottom: 3 }}>
                          Student Name / Email
                        </label>
                        <input
                          type="text"
                          className="form-input"
                          style={{ padding: "5px 9px", fontSize: 12 }}
                          placeholder="Filter by student..."
                          value={submissionFilters.student_search}
                          onChange={(e) => {
                            const next = { ...submissionFilters, student_search: e.target.value };
                            setSubmissionFilters(next);
                            loadSubmissions(next);
                          }}
                        />
                      </div>
                    )}

                    <div>
                      <label className="form-label" style={{ fontSize: 11, marginBottom: 3 }}>
                        Problem Title
                      </label>
                      <input
                        type="text"
                        className="form-input"
                        style={{ padding: "5px 9px", fontSize: 12 }}
                        placeholder="Filter by problem..."
                        value={submissionFilters.problem_search}
                        onChange={(e) => {
                          const next = { ...submissionFilters, problem_search: e.target.value };
                          setSubmissionFilters(next);
                          loadSubmissions(next);
                        }}
                      />
                    </div>

                    <div>
                      <label className="form-label" style={{ fontSize: 11, marginBottom: 3 }}>
                        Language
                      </label>
                      <select
                        className="form-select"
                        style={{ padding: "5px 9px", fontSize: 12 }}
                        value={submissionFilters.language}
                        onChange={(e) => {
                          const next = { ...submissionFilters, language: e.target.value };
                          setSubmissionFilters(next);
                          loadSubmissions(next);
                        }}
                      >
                        <option value="">All Languages</option>
                        <option value="python">Python</option>
                        <option value="c">C</option>
                        <option value="cpp">C++</option>
                        <option value="java">Java</option>
                        <option value="javascript">JavaScript</option>
                      </select>
                    </div>

                    <div>
                      <label className="form-label" style={{ fontSize: 11, marginBottom: 3 }}>
                        Verdict
                      </label>
                      <select
                        className="form-select"
                        style={{ padding: "5px 9px", fontSize: 12 }}
                        value={submissionFilters.status}
                        onChange={(e) => {
                          const next = { ...submissionFilters, status: e.target.value };
                          setSubmissionFilters(next);
                          loadSubmissions(next);
                        }}
                      >
                        <option value="">All Verdicts</option>
                        <option value="Accepted">Accepted</option>
                        <option value="Wrong Answer">Wrong Answer</option>
                        <option value="Runtime Error">Runtime Error</option>
                        <option value="Time Limit Exceeded">Time Limit Exceeded</option>
                        <option value="Compilation Error">Compilation Error</option>
                        <option value="Pending Evaluation">Pending Evaluation</option>
                      </select>
                    </div>

                    <div>
                      <label className="form-label" style={{ fontSize: 11, marginBottom: 3 }}>
                        Submission Context
                      </label>
                      <select
                        className="form-select"
                        style={{ padding: "5px 9px", fontSize: 12 }}
                        value={submissionFilters.submission_type}
                        onChange={(e) => {
                          const next = { ...submissionFilters, submission_type: e.target.value };
                          setSubmissionFilters(next);
                          loadSubmissions(next);
                        }}
                      >
                        <option value="">All Contexts</option>
                        <option value="practice">Practice</option>
                        <option value="assignment">Assignment</option>
                        <option value="coding_test">Coding Test</option>
                        <option value="practical">Academic Practical</option>
                        <option value="competition">Competition</option>
                      </select>
                    </div>

                    <div>
                      <label className="form-label" style={{ fontSize: 11, marginBottom: 3 }}>
                        From Date
                      </label>
                      <input
                        type="date"
                        className="form-input"
                        style={{ padding: "5px 9px", fontSize: 12 }}
                        value={submissionFilters.date_from}
                        onChange={(e) => {
                          const next = { ...submissionFilters, date_from: e.target.value };
                          setSubmissionFilters(next);
                          loadSubmissions(next);
                        }}
                      />
                    </div>

                    <div>
                      <label className="form-label" style={{ fontSize: 11, marginBottom: 3 }}>
                        To Date
                      </label>
                      <input
                        type="date"
                        className="form-input"
                        style={{ padding: "5px 9px", fontSize: 12 }}
                        value={submissionFilters.date_to}
                        onChange={(e) => {
                          const next = { ...submissionFilters, date_to: e.target.value };
                          setSubmissionFilters(next);
                          loadSubmissions(next);
                        }}
                      />
                    </div>

                    <div>
                      <label className="form-label" style={{ fontSize: 11, marginBottom: 3 }}>
                        Sort By
                      </label>
                      <select
                        className="form-select"
                        style={{ padding: "5px 9px", fontSize: 12 }}
                        value={submissionFilters.sort_by}
                        onChange={(e) => {
                          const next = { ...submissionFilters, sort_by: e.target.value };
                          setSubmissionFilters(next);
                          loadSubmissions(next);
                        }}
                      >
                        <option value="latest">Latest Submission</option>
                        <option value="highest_score">Highest Score</option>
                        <option value="execution_time">Fastest Execution Time</option>
                      </select>
                    </div>
                  </div>

                  {(submissionFilters.student_search ||
                    submissionFilters.problem_search ||
                    submissionFilters.language ||
                    submissionFilters.status ||
                    submissionFilters.submission_type ||
                    submissionFilters.date_from ||
                    submissionFilters.date_to ||
                    submissionFilters.sort_by !== "latest") && (
                    <div style={{ display: "flex", justifyContent: "flex-end" }}>
                      <button
                        type="button"
                        className="btn btn-outline btn-sm"
                        style={{ fontSize: 11, padding: "3px 10px" }}
                        onClick={() => {
                          const cleared = {
                            student_search: "",
                            problem_search: "",
                            language: "",
                            status: "",
                            submission_type: "",
                            date_from: "",
                            date_to: "",
                            sort_by: "latest",
                          };
                          setSubmissionFilters(cleared);
                          loadSubmissions(cleared);
                        }}
                      >
                        Clear All Filters
                      </button>
                    </div>
                  )}
                </div>

                {/* ========================================================= */}
                {/* TEACHER VIEW: GROUPED BY STUDENT OR DETAILED STUDENT HISTORY */}
                {/* ========================================================= */}
                {isTeacher ? (
                  !selectedTeacherStudent ? (
                    teacherGroupedStudents.length === 0 ? (
                      <div style={{ textAlign: "center", padding: "40px 0", color: "var(--text-muted)" }}>
                        No student submission records match your current filters.
                      </div>
                    ) : (
                      <div className="table-container">
                        <table className="clan-table">
                          <thead>
                            <tr>
                              <th>Student</th>
                              <th style={{ textAlign: "right" }}>Total Submissions</th>
                              <th style={{ textAlign: "right" }}>Problems Attempted</th>
                              <th style={{ textAlign: "right" }}>Accepted</th>
                              <th style={{ textAlign: "right" }}>Pending / Failed</th>
                              <th style={{ textAlign: "right" }}>Best Score</th>
                              <th>Latest Activity</th>
                              <th>Action</th>
                            </tr>
                          </thead>
                          <tbody>
                            {teacherGroupedStudents.map((stu) => (
                              <tr key={stu.user_id}>
                                <td>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setSelectedTeacherStudent(stu);
                                      fetchSubmissions({
                                        user_id: stu.user_id,
                                        ...submissionFilters,
                                      })
                                        .then((rows) => setSubmissions(rows))
                                        .catch(() => {});
                                    }}
                                    style={{
                                      background: "none",
                                      border: "none",
                                      padding: 0,
                                      textAlign: "left",
                                      cursor: "pointer",
                                      color: "var(--primary)",
                                      fontWeight: 700,
                                      fontSize: 13,
                                    }}
                                  >
                                    {stu.student_name}
                                  </button>
                                  {stu.student_email && (
                                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{stu.student_email}</div>
                                  )}
                                </td>
                                <td style={{ textAlign: "right", fontWeight: 700 }}>{stu.total_submissions}</td>
                                <td style={{ textAlign: "right", fontWeight: 600 }}>{stu.problems_attempted}</td>
                                <td style={{ textAlign: "right" }}>
                                  <span className="badge badge-status-accepted" style={{ fontWeight: 700 }}>
                                    {stu.accepted_count}
                                  </span>
                                </td>
                                <td style={{ textAlign: "right" }}>
                                  <span
                                    className="badge badge-hard"
                                    title={`${stu.pending_count} pending, ${stu.failed_count} failed`}
                                    style={{ fontWeight: 700 }}
                                  >
                                    {stu.pending_or_failed_count}
                                  </span>
                                </td>
                                <td style={{ textAlign: "right", fontWeight: 700, color: "var(--primary)" }}>
                                  {stu.best_score} pts
                                </td>
                                <td style={{ fontSize: 12, color: "var(--text-muted)" }}>
                                  {stu.latest_submitted_at
                                    ? new Date(stu.latest_submitted_at).toLocaleString()
                                    : "—"}
                                </td>
                                <td>
                                  <button
                                    type="button"
                                    className="btn btn-primary"
                                    style={{ padding: "4px 12px", fontSize: 12 }}
                                    onClick={() => {
                                      setSelectedTeacherStudent(stu);
                                      fetchSubmissions({
                                        user_id: stu.user_id,
                                        ...submissionFilters,
                                      })
                                        .then((rows) => setSubmissions(rows))
                                        .catch(() => {});
                                    }}
                                  >
                                    View History
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )
                  ) : (
                    (() => {
                      const studentSubs = submissions.filter(
                        (s) => s.user_id === selectedTeacherStudent.user_id
                      );
                      return studentSubs.length === 0 ? (
                        <div style={{ textAlign: "center", padding: "40px 0", color: "var(--text-muted)" }}>
                          No submissions found for {selectedTeacherStudent.student_name} under the selected filters.
                        </div>
                      ) : (
                        <div className="table-container">
                          <table className="clan-table">
                            <thead>
                              <tr>
                                <th>Sub ID</th>
                                <th>Problem Title</th>
                                <th>Language</th>
                                <th>Verdict</th>
                                <th>Test Cases Passed</th>
                                <th>Score</th>
                                <th>Exec Time</th>
                                <th>Context</th>
                                <th>Timestamp</th>
                                <th>Action</th>
                              </tr>
                            </thead>
                            <tbody>
                              {studentSubs.map((sub) => (
                                <tr key={sub.id}>
                                  <td>#{sub.id}</td>
                                  <td style={{ fontWeight: 600 }}>{sub.problem_title}</td>
                                  <td style={{ textTransform: "capitalize" }}>{sub.language}</td>
                                  <td>
                                    <StatusBadge status={sub.status} />
                                  </td>
                                  <td>
                                    {sub.passed_count ?? 0}/{sub.total_count ?? 0}
                                  </td>
                                  <td style={{ fontWeight: 600 }}>
                                    {sub.score ?? 0}/{sub.max_score ?? 10} pts
                                  </td>
                                  <td>{sub.execution_time != null ? `${sub.execution_time} ms` : "—"}</td>
                                  <td>
                                    <span
                                      style={{
                                        fontSize: 11,
                                        backgroundColor: "var(--bg-subtle)",
                                        padding: "2px 7px",
                                        borderRadius: 4,
                                        fontWeight: 600,
                                      }}
                                    >
                                      {sub.context_label || sub.submission_type}
                                    </span>
                                  </td>
                                  <td style={{ fontSize: 12 }}>
                                    {new Date(sub.submitted_at).toLocaleString()}
                                  </td>
                                  <td>
                                    <button
                                      type="button"
                                      className="btn btn-outline"
                                      style={{ padding: "3px 8px", fontSize: 11 }}
                                      onClick={() => handleInspectSubmission(sub.id)}
                                      disabled={isLoadingSubmissionDetail}
                                    >
                                      Review / Code
                                    </button>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      );
                    })()
                  )
                ) : (
                  /* ========================================================= */
                  /* STUDENT VIEW: GROUPED BY PROBLEM OR DETAILED PROBLEM ATTEMPTS */
                  /* ========================================================= */
                  !selectedStudentProblemGroup ? (
                    studentGroupedProblems.length === 0 ? (
                      <div style={{ textAlign: "center", padding: "40px 0", color: "var(--text-muted)" }}>
                        No submissions recorded for your account yet.
                      </div>
                    ) : (
                      <div className="table-container">
                        <table className="clan-table">
                          <thead>
                            <tr>
                              <th>Problem Title</th>
                              <th>Context</th>
                              <th style={{ textAlign: "right" }}>Total Attempts</th>
                              <th>Latest Verdict</th>
                              <th style={{ textAlign: "right" }}>Best Score</th>
                              <th>Latest Attempt</th>
                              <th>Action</th>
                            </tr>
                          </thead>
                          <tbody>
                            {studentGroupedProblems.map((grp) => (
                              <tr key={grp.group_key}>
                                <td>
                                  <button
                                    type="button"
                                    onClick={() => setSelectedStudentProblemGroup(grp)}
                                    style={{
                                      background: "none",
                                      border: "none",
                                      padding: 0,
                                      textAlign: "left",
                                      cursor: "pointer",
                                      color: "var(--primary)",
                                      fontWeight: 700,
                                      fontSize: 13,
                                    }}
                                  >
                                    {grp.problem_title}
                                  </button>
                                </td>
                                <td>
                                  <span
                                    style={{
                                      fontSize: 11,
                                      backgroundColor: "var(--bg-subtle)",
                                      padding: "2px 8px",
                                      borderRadius: 4,
                                      fontWeight: 600,
                                    }}
                                  >
                                    {grp.context_label}
                                  </span>
                                </td>
                                <td style={{ textAlign: "right", fontWeight: 700 }}>{grp.total_attempts}</td>
                                <td>
                                  <StatusBadge status={grp.latest_verdict} />
                                </td>
                                <td style={{ textAlign: "right", fontWeight: 700 }}>
                                  {grp.best_score}/{grp.max_score || 10}
                                </td>
                                <td style={{ fontSize: 12, color: "var(--text-muted)" }}>
                                  {grp.latest_submitted_at
                                    ? new Date(grp.latest_submitted_at).toLocaleString()
                                    : "—"}
                                </td>
                                <td>
                                  <button
                                    type="button"
                                    className="btn btn-primary"
                                    style={{ padding: "4px 12px", fontSize: 12 }}
                                    onClick={() => setSelectedStudentProblemGroup(grp)}
                                  >
                                    View History
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )
                  ) : (
                    (() => {
                      const problemAttempts = submissions.filter(
                        (s) =>
                          s.problem_id === selectedStudentProblemGroup.problem_id &&
                          (s.submission_type || "practice") ===
                            (selectedStudentProblemGroup.submission_type || "practice") &&
                          (s.assignment_id || null) ===
                            (selectedStudentProblemGroup.assignment_id || null) &&
                          (s.coding_test_id || null) ===
                            (selectedStudentProblemGroup.coding_test_id || null) &&
                          (s.practical_id || null) ===
                            (selectedStudentProblemGroup.practical_id || null)
                      );
                      return problemAttempts.length === 0 ? (
                        <div style={{ textAlign: "center", padding: "40px 0", color: "var(--text-muted)" }}>
                          No attempts match the selected filters for this problem.
                        </div>
                      ) : (
                        <div className="table-container">
                          <table className="clan-table">
                            <thead>
                              <tr>
                                <th>Sub ID</th>
                                <th>Problem Title</th>
                                <th>Language</th>
                                <th>Verdict</th>
                                <th>Test Cases</th>
                                <th>Score</th>
                                <th>Exec Time</th>
                                <th>Context</th>
                                <th>Timestamp</th>
                                <th>Action</th>
                              </tr>
                            </thead>
                            <tbody>
                              {problemAttempts.map((sub) => (
                                <tr key={sub.id}>
                                  <td>#{sub.id}</td>
                                  <td style={{ fontWeight: 600 }}>{sub.problem_title}</td>
                                  <td style={{ textTransform: "capitalize" }}>{sub.language}</td>
                                  <td>
                                    <StatusBadge status={sub.status} />
                                  </td>
                                  <td>
                                    {sub.passed_count ?? 0}/{sub.total_count ?? 0}
                                  </td>
                                  <td style={{ fontWeight: 600 }}>
                                    {sub.score ?? 0}/{sub.max_score ?? 10} pts
                                  </td>
                                  <td>{sub.execution_time != null ? `${sub.execution_time} ms` : "—"}</td>
                                  <td>
                                    <span
                                      style={{
                                        fontSize: 11,
                                        backgroundColor: "var(--bg-subtle)",
                                        padding: "2px 7px",
                                        borderRadius: 4,
                                        fontWeight: 600,
                                      }}
                                    >
                                      {sub.context_label || sub.submission_type}
                                    </span>
                                  </td>
                                  <td style={{ fontSize: 12 }}>
                                    {new Date(sub.submitted_at).toLocaleString()}
                                  </td>
                                  <td>
                                    <button
                                      type="button"
                                      className="btn btn-outline"
                                      style={{ padding: "3px 8px", fontSize: 11 }}
                                      onClick={() => handleInspectSubmission(sub.id)}
                                      disabled={isLoadingSubmissionDetail}
                                    >
                                      Review / Code
                                    </button>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      );
                    })()
                  )
                )}
              </div>
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

                    {/* UNIVERSAL EXECUTION ENVIRONMENT & EVALUATION STRATEGY */}
                    <div
                      style={{
                        backgroundColor: "#f8fafc",
                        border: "1px solid var(--border-light)",
                        borderRadius: 8,
                        padding: 14,
                        marginBottom: 16,
                      }}
                    >
                      <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10, color: "var(--text-main)" }}>
                        Execution Environment & Automated Grading Strategy
                      </div>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
                        <div className="form-group" style={{ marginBottom: 0 }}>
                          <label className="form-label">Execution Environment *</label>
                          <select
                            className="form-select"
                            value={newProblem.environment_id}
                            onChange={(e) => setNewProblem({ ...newProblem, environment_id: e.target.value })}
                          >
                            <option value="cp">Env A: Competitive Programming (Python/C/C++/Java/JS)</option>
                            <option value="datascience">Env B: Data Science (NumPy, Pandas, SciPy, Matplotlib)</option>
                            <option value="ml">Env C: Machine Learning (Scikit-learn, Pandas, NumPy)</option>
                            <option value="cv">Env D: Computer Vision (OpenCV, Pillow, Scikit-image)</option>
                            <option value="nlp">Env E: NLP (NLTK, spaCy, Scikit-learn)</option>
                            <option value="dl-torch">Env F1: Deep Learning (PyTorch CPU)</option>
                            <option value="dl-tf">Env F2: Deep Learning (TensorFlow CPU)</option>
                            <option value="scientific">Env G: Scientific Computing (SymPy, SciPy, NetworkX)</option>
                          </select>
                        </div>

                        <div className="form-group" style={{ marginBottom: 0 }}>
                          <label className="form-label">Assignment Category</label>
                          <select
                            className="form-select"
                            value={newProblem.problem_type}
                            onChange={(e) => setNewProblem({ ...newProblem, problem_type: e.target.value })}
                          >
                            <option value="competitive">Competitive / Algorithmic</option>
                            <option value="multifile">Multi-File Software Engineering</option>
                            <option value="data_science">Data Science & Analytics</option>
                            <option value="machine_learning">Machine Learning Model</option>
                            <option value="computer_vision">Computer Vision / Image Processing</option>
                            <option value="nlp">Natural Language Processing</option>
                            <option value="deep_learning">Deep Learning (Neural Networks)</option>
                            <option value="scientific">Scientific / Numerical Methods</option>
                          </select>
                        </div>

                        <div className="form-group" style={{ marginBottom: 0 }}>
                          <label className="form-label">Evaluation Strategy *</label>
                          <select
                            className="form-select"
                            value={newProblem.evaluation_type}
                            onChange={(e) => setNewProblem({ ...newProblem, evaluation_type: e.target.value })}
                          >
                            <option value="exact">Type A: Exact Output Matching</option>
                            <option value="numeric_tolerance">Type B: Numeric Tolerance (Floating-Point)</option>
                            <option value="structured_json">Type C: Structured JSON / Matrix</option>
                            <option value="file_based">Type D: Generated File Inspection (/work/output/)</option>
                            <option value="function_harness">Type E: Python Function Harness</option>
                            <option value="ml_metrics">Type F: ML Evaluation Metrics (F1 / Accuracy / RMSE)</option>
                            <option value="custom_script">Type G: Custom Teacher Evaluation Script</option>
                          </select>
                        </div>
                      </div>

                      {newProblem.evaluation_type === "numeric_tolerance" && (
                        <div style={{ marginTop: 12 }}>
                          <label className="form-label">Floating-Point Absolute Tolerance</label>
                          <input
                            type="text"
                            className="form-input"
                            style={{ maxWidth: 220 }}
                            value={newProblem.tolerance}
                            onChange={(e) => setNewProblem({ ...newProblem, tolerance: e.target.value })}
                          />
                        </div>
                      )}

                      {newProblem.evaluation_type === "ml_metrics" && (
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
                          <div>
                            <label className="form-label">ML Evaluation Metric</label>
                            <select
                              className="form-select"
                              value={newProblem.ml_metric}
                              onChange={(e) => setNewProblem({ ...newProblem, ml_metric: e.target.value })}
                            >
                              <option value="f1">Macro F1 Score (&gt;= threshold)</option>
                              <option value="accuracy">Classification Accuracy (&gt;= threshold)</option>
                              <option value="precision">Macro Precision (&gt;= threshold)</option>
                              <option value="recall">Macro Recall (&gt;= threshold)</option>
                              <option value="rmse">Regression RMSE (&lt;= threshold)</option>
                              <option value="mae">Regression MAE (&lt;= threshold)</option>
                            </select>
                          </div>
                          <div>
                            <label className="form-label">Pass Threshold</label>
                            <input
                              type="text"
                              className="form-input"
                              value={newProblem.ml_threshold}
                              onChange={(e) => setNewProblem({ ...newProblem, ml_threshold: e.target.value })}
                            />
                          </div>
                        </div>
                      )}

                      {newProblem.evaluation_type === "file_based" && (
                        <div style={{ marginTop: 12 }}>
                          <label className="form-label">Target Output File in /work/output/</label>
                          <input
                            type="text"
                            className="form-input"
                            style={{ maxWidth: 280 }}
                            placeholder="e.g. report.csv or plot.png"
                            value={newProblem.target_file}
                            onChange={(e) => setNewProblem({ ...newProblem, target_file: e.target.value })}
                          />
                        </div>
                      )}

                      {newProblem.evaluation_type === "function_harness" && (
                        <div style={{ marginTop: 12 }}>
                          <label className="form-label">Target Python Function Name</label>
                          <input
                            type="text"
                            className="form-input"
                            style={{ maxWidth: 280 }}
                            placeholder="e.g. solve"
                            value={newProblem.function_name}
                            onChange={(e) => setNewProblem({ ...newProblem, function_name: e.target.value })}
                          />
                        </div>
                      )}

                      {newProblem.evaluation_type === "custom_script" && (
                        <div style={{ marginTop: 12 }}>
                          <label className="form-label">Custom Teacher Evaluator Script (Runs in separate isolated container)</label>
                          <textarea
                            rows={4}
                            className="form-textarea"
                            placeholder="import json, os&#10;print(json.dumps({'passed': True, 'score_fraction': 1.0, 'feedback': 'OK'}))"
                            value={newProblem.custom_evaluator_script}
                            onChange={(e) => setNewProblem({ ...newProblem, custom_evaluator_script: e.target.value })}
                          />
                        </div>
                      )}

                      {/* OPTIONAL DATASET ATTACHMENT */}
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 2fr", gap: 12, marginTop: 12 }}>
                        <div>
                          <label className="form-label">Dataset Filename (/work/data/)</label>
                          <input
                            type="text"
                            className="form-input"
                            placeholder="e.g. dataset.csv"
                            value={newProblem.dataset_filename}
                            onChange={(e) => setNewProblem({ ...newProblem, dataset_filename: e.target.value })}
                          />
                        </div>
                        <div>
                          <label className="form-label">Dataset Visibility</label>
                          <select
                            className="form-select"
                            value={newProblem.dataset_visibility}
                            onChange={(e) => setNewProblem({ ...newProblem, dataset_visibility: e.target.value })}
                          >
                            <option value="public">Public Sample Dataset</option>
                            <option value="hidden">Hidden Grading Dataset</option>
                          </select>
                        </div>
                        <div>
                          <label className="form-label">Dataset Content (CSV / JSON / TXT)</label>
                          <textarea
                            rows={2}
                            className="form-textarea"
                            placeholder="x,y&#10;1,2&#10;3,6"
                            value={newProblem.dataset_content}
                            onChange={(e) => setNewProblem({ ...newProblem, dataset_content: e.target.value })}
                          />
                        </div>
                      </div>
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                      <div className="form-group">
                        <label className="form-label">Public Sample Test Input *</label>
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
                        <label className="form-label">Public Sample Test Expected Output *</label>
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

                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                      <div className="form-group">
                        <label className="form-label">Hidden Grading Test Input (Optional)</label>
                        <input
                          type="text"
                          className="form-input"
                          placeholder="e.g. 100 250 (never shown to students)"
                          value={newProblem.hidden_input || ""}
                          onChange={(e) => setNewProblem({ ...newProblem, hidden_input: e.target.value })}
                        />
                      </div>

                      <div className="form-group">
                        <label className="form-label">Hidden Grading Expected Output (Optional)</label>
                        <input
                          type="text"
                          className="form-input"
                          placeholder="e.g. 350"
                          value={newProblem.hidden_output || ""}
                          onChange={(e) => setNewProblem({ ...newProblem, hidden_output: e.target.value })}
                        />
                      </div>
                    </div>

                    {/* OPTIONAL CONSTRAINTS & EXAMPLES (COLLAPSED BY DEFAULT FOR SIMPLIFIED PROBLEM CREATION) */}
                    <div style={{ marginBottom: 14 }}>
                      <button
                        type="button"
                        className="btn btn-outline btn-sm"
                        style={{ fontSize: 12, padding: "4px 10px" }}
                        onClick={() => setShowOptionalProblemFields((prev) => !prev)}
                      >
                        {showOptionalProblemFields
                          ? "− Hide Optional Constraints & Examples"
                          : "+ Add Optional Constraints & Examples (Not Required)"}
                      </button>

                      {showOptionalProblemFields && (
                        <div
                          style={{
                            display: "grid",
                            gridTemplateColumns: "1fr 1fr",
                            gap: 16,
                            marginTop: 12,
                            padding: 12,
                            backgroundColor: "#f8fafc",
                            borderRadius: 8,
                            border: "1px solid var(--border-light)",
                          }}
                        >
                          <div className="form-group" style={{ marginBottom: 0 }}>
                            <label className="form-label">Constraints (Optional)</label>
                            <textarea
                              rows={2}
                              className="form-textarea"
                              placeholder="Optional, e.g. -10^9 <= a <= 10^9"
                              value={newProblem.constraints}
                              onChange={(e) => setNewProblem({ ...newProblem, constraints: e.target.value })}
                            />
                          </div>

                          <div className="form-group" style={{ marginBottom: 0 }}>
                            <label className="form-label">Additional Examples Note (Optional)</label>
                            <textarea
                              rows={2}
                              className="form-textarea"
                              placeholder="Optional (Sample Test Input/Output above is already shown to students)"
                              value={newProblem.examples}
                              onChange={(e) => setNewProblem({ ...newProblem, examples: e.target.value })}
                            />
                          </div>
                        </div>
                      )}
                    </div>

                    <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
                      <button type="submit" className="btn btn-primary" disabled={isSubmittingProblem}>
                        <PlusCircle size={16} /> {isSubmittingProblem ? "Publishing..." : "Publish Problem Statement"}
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {/* TAB 2: CREATE & ASSIGN COURSEWORK + ACADEMIC PRACTICAL TRACKING */}
              {teacherTab === "create_assignment" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                  {/* SUB-NAVIGATION BAR FOR COURSEWORK vs ACADEMIC PRACTICALS */}
                  <div
                    className="card"
                    style={{
                      padding: "12px 16px",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      flexWrap: "wrap",
                      gap: 12,
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 15, color: "var(--text-main)" }}>
                        Coursework & Academic Practical Management
                      </div>
                      <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                        Manage regular coding problem assignments alongside official curriculum laboratory practicals.
                      </div>
                    </div>

                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      {[
                        { id: "regular_assignment", label: "1. Regular Coding Assignment" },
                        { id: "create_practical", label: "2. Create Academic Practical" },
                        { id: "assign_practicals", label: "3. Assign Practicals" },
                        { id: "track_practicals", label: `4. Practical Tracking (${practicals.length})` },
                      ].map((st) => (
                        <button
                          key={st.id}
                          type="button"
                          className={`btn ${courseworkSubTab === st.id ? "btn-primary" : "btn-outline"}`}
                          style={{ padding: "6px 12px", fontSize: 12, fontWeight: 600 }}
                          onClick={() => setCourseworkSubTab(st.id)}
                        >
                          {st.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* SUB-TAB 1: REGULAR CODING PROBLEM ASSIGNMENT */}
                  {courseworkSubTab === "regular_assignment" && (
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
                              placeholder="e.g. Lab 02: Loops & Logic"
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

                        <div
                          style={{
                            marginBottom: 16,
                            padding: "10px 14px",
                            backgroundColor: "#f8fafc",
                            border: "1px solid var(--border-light)",
                            borderRadius: 8,
                            display: "flex",
                            alignItems: "center",
                            gap: 10,
                          }}
                        >
                          <input
                            id="assignment-allow-copy-paste"
                            type="checkbox"
                            checked={Boolean(newAssignment.allow_copy_paste)}
                            onChange={(e) =>
                              setNewAssignment({
                                ...newAssignment,
                                allow_copy_paste: e.target.checked,
                              })
                            }
                            style={{ width: 16, height: 16, cursor: "pointer" }}
                          />
                          <label
                            htmlFor="assignment-allow-copy-paste"
                            style={{ fontSize: 13, fontWeight: 600, cursor: "pointer", color: "var(--text-main)" }}
                          >
                            Allow Copy & Paste in Editor (Enabled by default for coursework; uncheck to require manual typing)
                          </label>
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

                  {/* SUB-TAB 2: CREATE ACADEMIC PRACTICAL */}
                  {courseworkSubTab === "create_practical" && (
                    <div className="card">
                      <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 6 }}>
                        Create Academic Practical Record
                      </h3>
                      <p style={{ color: "var(--text-muted)", fontSize: 13, marginBottom: 20 }}>
                        Add a curriculum practical based on your subject syllabus and optionally link an automated coding problem and assign enrolled students.
                      </p>

                      {practicalFormMsg && (
                        <div
                          style={{
                            padding: 12,
                            borderRadius: 8,
                            marginBottom: 16,
                            fontSize: 13,
                            backgroundColor: practicalFormMsg.type === "success" ? "#ecfdf5" : "#fef2f2",
                            color: practicalFormMsg.type === "success" ? "#065f46" : "#991b1b",
                            border: `1px solid ${practicalFormMsg.type === "success" ? "#a7f3d0" : "#fecaca"}`,
                          }}
                        >
                          {practicalFormMsg.text}
                        </div>
                      )}

                      <form onSubmit={handleCreatePracticalSubmit}>
                        <div style={{ display: "grid", gridTemplateColumns: "110px 2fr 1.5fr", gap: 16 }}>
                          <div className="form-group">
                            <label className="form-label">Practical # *</label>
                            <input
                              type="number"
                              min="1"
                              max="200"
                              required
                              className="form-input"
                              value={newPractical.practical_number}
                              onChange={(e) => setNewPractical({ ...newPractical, practical_number: e.target.value })}
                            />
                          </div>

                          <div className="form-group">
                            <label className="form-label">Practical Title *</label>
                            <input
                              type="text"
                              required
                              className="form-input"
                              placeholder="Enter syllabus practical title..."
                              value={newPractical.title}
                              onChange={(e) => setNewPractical({ ...newPractical, title: e.target.value })}
                            />
                          </div>

                          <div className="form-group">
                            <label className="form-label">Subject Name *</label>
                            <input
                              type="text"
                              required
                              className="form-input"
                              placeholder="Enter subject name..."
                              value={newPractical.subject_name}
                              onChange={(e) => setNewPractical({ ...newPractical, subject_name: e.target.value })}
                            />
                          </div>
                        </div>

                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr 1fr", gap: 14 }}>
                          <div className="form-group">
                            <label className="form-label">Subject Code (Optional)</label>
                            <input
                              type="text"
                              className="form-input"
                              placeholder="e.g. AIDS-701"
                              value={newPractical.subject_code}
                              onChange={(e) => setNewPractical({ ...newPractical, subject_code: e.target.value })}
                            />
                          </div>

                          <div className="form-group">
                            <label className="form-label">Academic Semester (Optional)</label>
                            <input
                              type="text"
                              className="form-input"
                              placeholder="e.g. Sem VII"
                              value={newPractical.semester}
                              onChange={(e) => setNewPractical({ ...newPractical, semester: e.target.value })}
                            />
                          </div>

                          <div className="form-group">
                            <label className="form-label">Start Date</label>
                            <input
                              type="date"
                              className="form-input"
                              value={newPractical.start_date}
                              onChange={(e) => setNewPractical({ ...newPractical, start_date: e.target.value })}
                            />
                          </div>

                          <div className="form-group">
                            <label className="form-label">Submission Deadline</label>
                            <input
                              type="date"
                              className="form-input"
                              value={newPractical.deadline}
                              onChange={(e) => setNewPractical({ ...newPractical, deadline: e.target.value })}
                            />
                          </div>

                          <div className="form-group">
                            <label className="form-label">Maximum Marks</label>
                            <input
                              type="number"
                              min="1"
                              max="500"
                              className="form-input"
                              value={newPractical.max_marks}
                              onChange={(e) => setNewPractical({ ...newPractical, max_marks: e.target.value })}
                            />
                          </div>
                        </div>

                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                          <div className="form-group">
                            <label className="form-label">Practical Description</label>
                            <textarea
                              rows={2}
                              className="form-textarea"
                              placeholder="Problem statement or syllabus scope for this practical..."
                              value={newPractical.description}
                              onChange={(e) => setNewPractical({ ...newPractical, description: e.target.value })}
                            />
                          </div>

                          <div className="form-group">
                            <label className="form-label">Objectives / Instructions</label>
                            <textarea
                              rows={2}
                              className="form-textarea"
                              placeholder="Learning objectives, dataset notes, or submission instructions..."
                              value={newPractical.objectives}
                              onChange={(e) => setNewPractical({ ...newPractical, objectives: e.target.value })}
                            />
                          </div>
                        </div>

                        <div className="form-group">
                          <label className="form-label">Associated Coding Problem (Optional — links automated code evaluation)</label>
                          <select
                            className="form-select"
                            value={newPractical.problem_id}
                            onChange={(e) => setNewPractical({ ...newPractical, problem_id: e.target.value })}
                          >
                            <option value="">— None (Manual / Lab Report Submission) —</option>
                            {problems.map((p) => (
                              <option key={p.id} value={p.id}>
                                #{p.id} — {p.title} ({p.difficulty} • {p.topic})
                              </option>
                            ))}
                          </select>
                        </div>

                        {/* ASSIGN STUDENTS */}
                        <div style={{ marginTop: 12, marginBottom: 20 }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                            <label className="form-label" style={{ margin: 0 }}>
                              Assign to Students ({newPractical.selectedStudentIds.length} Selected)
                            </label>
                            <button
                              type="button"
                              className="btn btn-outline"
                              style={{ padding: "2px 8px", fontSize: 11 }}
                              onClick={selectAllPracticalStudents}
                            >
                              Select All Enrolled Students
                            </button>
                          </div>

                          <div
                            style={{
                              display: "grid",
                              gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
                              gap: 10,
                              maxHeight: 170,
                              overflowY: "auto",
                              padding: 10,
                              backgroundColor: "#f8fafc",
                              borderRadius: 8,
                              border: "1px solid var(--border-light)",
                            }}
                          >
                            {studentUsers.map((stu) => {
                              const isSelected = newPractical.selectedStudentIds.includes(stu.id);
                              return (
                                <div
                                  key={stu.id}
                                  onClick={() => togglePracticalStudentSelection(stu.id)}
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
                                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{stu.email}</div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>

                        <div style={{ display: "flex", justifyContent: "flex-end" }}>
                          <button type="submit" className="btn btn-primary" disabled={isSubmittingNewPractical}>
                            <PlusCircle size={16} /> {isSubmittingNewPractical ? "Saving..." : "Create & Assign Academic Practical"}
                          </button>
                        </div>
                      </form>
                    </div>
                  )}

                  {/* SUB-TAB 3: BULK ASSIGN EXISTING PRACTICALS */}
                  {courseworkSubTab === "assign_practicals" && (
                    <div className="card">
                      <h3 style={{ fontSize: 18, fontWeight: 700, marginBottom: 6 }}>
                        Assign Academic Practicals to Students
                      </h3>
                      <p style={{ color: "var(--text-muted)", fontSize: 13, marginBottom: 20 }}>
                        Select one or more curriculum practicals, set a deadline or updated instructions, and assign them to selected or all enrolled students.
                      </p>

                      {bulkPracticalMsg && (
                        <div
                          style={{
                            padding: 12,
                            borderRadius: 8,
                            marginBottom: 16,
                            fontSize: 13,
                            backgroundColor: bulkPracticalMsg.type === "success" ? "#ecfdf5" : "#fef2f2",
                            color: bulkPracticalMsg.type === "success" ? "#065f46" : "#991b1b",
                            border: `1px solid ${bulkPracticalMsg.type === "success" ? "#a7f3d0" : "#fecaca"}`,
                          }}
                        >
                          {bulkPracticalMsg.text}
                        </div>
                      )}

                      <form onSubmit={handleBulkAssignPracticalsSubmit}>
                        <div style={{ marginBottom: 18 }}>
                          <label className="form-label">
                            1. Select Academic Practicals ({bulkPracticalAssign.selectedPracticalIds.length} Selected) *
                          </label>
                          {practicals.length === 0 ? (
                            <div style={{ padding: 16, backgroundColor: "#f8fafc", borderRadius: 8, color: "var(--text-muted)", fontSize: 13 }}>
                              No academic practicals created yet. Use "2. Create Academic Practical" first.
                            </div>
                          ) : (
                            <div
                              style={{
                                display: "grid",
                                gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
                                gap: 10,
                                maxHeight: 200,
                                overflowY: "auto",
                                padding: 10,
                                backgroundColor: "#f8fafc",
                                borderRadius: 8,
                                border: "1px solid var(--border-light)",
                              }}
                            >
                              {practicals.map((prac) => {
                                const isSel = bulkPracticalAssign.selectedPracticalIds.includes(prac.id);
                                return (
                                  <div
                                    key={prac.id}
                                    onClick={() => toggleBulkPracticalId(prac.id)}
                                    style={{
                                      padding: "10px 12px",
                                      borderRadius: 6,
                                      border: isSel ? "2px solid var(--primary)" : "1px solid var(--border-light)",
                                      backgroundColor: isSel ? "#eff6ff" : "white",
                                      cursor: "pointer",
                                      display: "flex",
                                      alignItems: "center",
                                      gap: 10,
                                    }}
                                  >
                                    {isSel ? (
                                      <CheckSquare size={18} color="var(--primary)" />
                                    ) : (
                                      <Square size={18} color="var(--text-muted)" />
                                    )}
                                    <div>
                                      <div style={{ fontSize: 13, fontWeight: 700 }}>
                                        Practical {prac.practical_number}: {prac.title}
                                      </div>
                                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                                        {prac.subject_name} • {prac.assigned_count} assigned
                                      </div>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>

                        <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 16, marginBottom: 16 }}>
                          <div>
                            <label className="form-label">Update Submission Deadline (Optional)</label>
                            <input
                              type="date"
                              className="form-input"
                              value={bulkPracticalAssign.deadline}
                              onChange={(e) => setBulkPracticalAssign({ ...bulkPracticalAssign, deadline: e.target.value })}
                            />
                          </div>
                          <div>
                            <label className="form-label">Additional Instructions (Optional)</label>
                            <input
                              type="text"
                              className="form-input"
                              placeholder="Optional instructions for assigned students..."
                              value={bulkPracticalAssign.objectives}
                              onChange={(e) => setBulkPracticalAssign({ ...bulkPracticalAssign, objectives: e.target.value })}
                            />
                          </div>
                        </div>

                        <div style={{ marginBottom: 18 }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                            <label className="form-label" style={{ margin: 0 }}>
                              2. Select Students ({bulkPracticalAssign.selectedStudentIds.length} Selected) *
                            </label>
                            <button
                              type="button"
                              className="btn btn-outline"
                              style={{ padding: "2px 8px", fontSize: 11 }}
                              onClick={selectAllBulkPracticalStudents}
                            >
                              Select All Enrolled Students
                            </button>
                          </div>

                          <div
                            style={{
                              display: "grid",
                              gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
                              gap: 10,
                              maxHeight: 170,
                              overflowY: "auto",
                              padding: 10,
                              backgroundColor: "#f8fafc",
                              borderRadius: 8,
                              border: "1px solid var(--border-light)",
                            }}
                          >
                            {studentUsers.map((stu) => {
                              const isSel = bulkPracticalAssign.selectedStudentIds.includes(stu.id);
                              return (
                                <div
                                  key={stu.id}
                                  onClick={() => toggleBulkPracticalStudentId(stu.id)}
                                  style={{
                                    padding: "8px 12px",
                                    borderRadius: 6,
                                    border: isSel ? "2px solid var(--primary)" : "1px solid var(--border-light)",
                                    backgroundColor: isSel ? "#eff6ff" : "white",
                                    cursor: "pointer",
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 10,
                                  }}
                                >
                                  {isSel ? (
                                    <CheckSquare size={18} color="var(--primary)" />
                                  ) : (
                                    <Square size={18} color="var(--text-muted)" />
                                  )}
                                  <div>
                                    <div style={{ fontSize: 13, fontWeight: 600 }}>{stu.name}</div>
                                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{stu.email}</div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>

                        <div style={{ display: "flex", justifyContent: "flex-end" }}>
                          <button type="submit" className="btn btn-primary" disabled={isSubmittingBulkPractical}>
                            <Send size={16} /> {isSubmittingBulkPractical ? "Assigning..." : "Assign Selected Practicals"}
                          </button>
                        </div>
                      </form>
                    </div>
                  )}

                  {/* SUB-TAB 4: TEACHER PRACTICAL TRACKING & STUDENT COMPLETION VIEW */}
                  {courseworkSubTab === "track_practicals" && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                      {evaluatingPracticalStudent && (
                        <div className="card" style={{ border: "2px solid var(--primary)", backgroundColor: "#f8fafc" }}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                            <h4 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>
                              Evaluate Practical Submission — {evaluatingPracticalStudent.studentName}
                            </h4>
                            <button
                              type="button"
                              className="btn btn-outline btn-sm"
                              onClick={() => setEvaluatingPracticalStudent(null)}
                            >
                              Close
                            </button>
                          </div>

                          <form onSubmit={handleEvaluatePracticalStudentSubmit}>
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 2fr", gap: 14 }}>
                              <div>
                                <label className="form-label">Status</label>
                                <select
                                  className="form-select"
                                  value={evaluatingPracticalStudent.status}
                                  onChange={(e) =>
                                    setEvaluatingPracticalStudent((prev) => ({
                                      ...prev,
                                      status: e.target.value,
                                    }))
                                  }
                                >
                                  <option value="Not Started">Not Started</option>
                                  <option value="In Progress">In Progress</option>
                                  <option value="Submitted">Submitted</option>
                                  <option value="Evaluated">Evaluated</option>
                                  <option value="Late Submission">Late Submission</option>
                                </select>
                              </div>

                              <div>
                                <label className="form-label">
                                  Marks Obtained (Max: {evaluatingPracticalStudent.max_marks || 10})
                                </label>
                                <input
                                  type="number"
                                  step="0.5"
                                  min="0"
                                  max={evaluatingPracticalStudent.max_marks || 100}
                                  className="form-input"
                                  value={evaluatingPracticalStudent.marks_obtained}
                                  onChange={(e) =>
                                    setEvaluatingPracticalStudent((prev) => ({
                                      ...prev,
                                      marks_obtained: e.target.value,
                                    }))
                                  }
                                />
                              </div>

                              <div>
                                <label className="form-label">Teacher Feedback / Remarks</label>
                                <input
                                  type="text"
                                  className="form-input"
                                  placeholder="Optional remarks for student..."
                                  value={evaluatingPracticalStudent.teacher_feedback}
                                  onChange={(e) =>
                                    setEvaluatingPracticalStudent((prev) => ({
                                      ...prev,
                                      teacher_feedback: e.target.value,
                                    }))
                                  }
                                />
                              </div>
                            </div>

                            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 12 }}>
                              <button
                                type="button"
                                className="btn btn-outline"
                                onClick={() => setEvaluatingPracticalStudent(null)}
                              >
                                Cancel
                              </button>
                              <button type="submit" className="btn btn-primary" disabled={isEvaluatingPractical}>
                                <Save size={15} /> {isEvaluatingPractical ? "Saving..." : "Save Evaluation"}
                              </button>
                            </div>
                          </form>
                        </div>
                      )}

                      <div className="card">
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                          <div>
                            <h3 style={{ fontSize: 18, fontWeight: 700 }}>
                              {selectedPracticalForStudents
                                ? `Practical ${selectedPracticalForStudents.practical_number}: ${selectedPracticalForStudents.title} — Student Completion Tracking`
                                : `Academic Practicals Completion Tracking (${practicals.length})`}
                            </h3>
                            <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                              {selectedPracticalForStudents
                                ? `${selectedPracticalForStudents.subject_name} • ${selectedPracticalForStudents.assigned_count} Assigned • ${selectedPracticalForStudents.submitted_count} Submitted • ${selectedPracticalForStudents.pending_count} Pending`
                                : "Click View Students on any practical to inspect individual student completion statuses, identify pending students, and evaluate submissions."}
                            </p>
                          </div>

                          <div style={{ display: "flex", gap: 8 }}>
                            {selectedPracticalForStudents && (
                              <button
                                type="button"
                                className="btn btn-outline"
                                onClick={() => {
                                  setSelectedPracticalForStudents(null);
                                  setEvaluatingPracticalStudent(null);
                                }}
                              >
                                <ArrowLeft size={15} /> Back to All Practicals
                              </button>
                            )}
                            <button type="button" className="btn btn-outline" onClick={loadPracticals}>
                              Refresh
                            </button>
                          </div>
                        </div>

                        {!selectedPracticalForStudents ? (
                          practicals.length === 0 ? (
                            <div style={{ textAlign: "center", padding: "36px 0", color: "var(--text-muted)" }}>
                              No academic practicals created yet.
                            </div>
                          ) : (
                            <div className="table-container">
                              <table className="clan-table">
                                <thead>
                                  <tr>
                                    <th>Practical</th>
                                    <th>Subject</th>
                                    <th>Linked Problem</th>
                                    <th>Deadline</th>
                                    <th style={{ textAlign: "right" }}>Assigned Students</th>
                                    <th style={{ textAlign: "right" }}>Submitted</th>
                                    <th style={{ textAlign: "right" }}>Pending</th>
                                    <th>Action</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {practicals.map((prac) => (
                                    <tr key={prac.id}>
                                      <td>
                                        <button
                                          type="button"
                                          onClick={() => setSelectedPracticalForStudents(prac)}
                                          style={{
                                            background: "none",
                                            border: "none",
                                            padding: 0,
                                            cursor: "pointer",
                                            color: "var(--primary)",
                                            fontWeight: 700,
                                            fontSize: 13,
                                            textAlign: "left",
                                          }}
                                        >
                                          Practical {prac.practical_number}: {prac.title}
                                        </button>
                                      </td>
                                      <td>
                                        <div style={{ fontWeight: 600 }}>{prac.subject_name}</div>
                                        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                                          {[prac.subject_code, prac.semester].filter(Boolean).join(" • ")}
                                        </div>
                                      </td>
                                      <td>
                                        {prac.problem_id ? (
                                          <span style={{ fontSize: 12, fontWeight: 600 }}>
                                            {prac.problem_title || `Problem #${prac.problem_id}`}
                                          </span>
                                        ) : (
                                          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Lab / Manual</span>
                                        )}
                                      </td>
                                      <td style={{ fontSize: 12 }}>
                                        {prac.deadline ? new Date(prac.deadline).toLocaleDateString() : "No deadline"}
                                      </td>
                                      <td style={{ textAlign: "right", fontWeight: 700 }}>{prac.assigned_count}</td>
                                      <td style={{ textAlign: "right" }}>
                                        <span className="badge badge-status-accepted" style={{ fontWeight: 700 }}>
                                          {prac.submitted_count}
                                        </span>
                                      </td>
                                      <td style={{ textAlign: "right" }}>
                                        <span className="badge badge-hard" style={{ fontWeight: 700 }}>
                                          {prac.pending_count}
                                        </span>
                                      </td>
                                      <td>
                                        <button
                                          type="button"
                                          className="btn btn-primary"
                                          style={{ padding: "4px 12px", fontSize: 12 }}
                                          onClick={() => setSelectedPracticalForStudents(prac)}
                                        >
                                          View Students
                                        </button>
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )
                        ) : (
                          <>
                            <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
                              {[
                                { id: "all", label: `All Assigned (${selectedPracticalForStudents.students?.length || 0})` },
                                {
                                  id: "pending",
                                  label: `Not Submitted / Pending (${
                                    (selectedPracticalForStudents.students || []).filter(
                                      (s) => s.status === "Not Started" || s.status === "In Progress"
                                    ).length
                                  })`,
                                },
                                {
                                  id: "submitted",
                                  label: `Submitted / Evaluated (${
                                    (selectedPracticalForStudents.students || []).filter(
                                      (s) =>
                                        s.status === "Submitted" ||
                                        s.status === "Evaluated" ||
                                        s.status === "Late Submission"
                                    ).length
                                  })`,
                                },
                              ].map((f) => (
                                <button
                                  key={f.id}
                                  type="button"
                                  className={`btn ${practicalStudentFilter === f.id ? "btn-primary" : "btn-outline"}`}
                                  style={{ padding: "4px 10px", fontSize: 12 }}
                                  onClick={() => setPracticalStudentFilter(f.id)}
                                >
                                  {f.label}
                                </button>
                              ))}
                            </div>

                            {(() => {
                              const allRows = selectedPracticalForStudents.students || [];
                              const filteredRows = allRows.filter((s) => {
                                if (practicalStudentFilter === "pending") {
                                  return s.status === "Not Started" || s.status === "In Progress";
                                }
                                if (practicalStudentFilter === "submitted") {
                                  return (
                                    s.status === "Submitted" ||
                                    s.status === "Evaluated" ||
                                    s.status === "Late Submission"
                                  );
                                }
                                return true;
                              });

                              return filteredRows.length === 0 ? (
                                <div style={{ textAlign: "center", padding: "32px 0", color: "var(--text-muted)" }}>
                                  No student records match this filter.
                                </div>
                              ) : (
                                <div className="table-container">
                                  <table className="clan-table">
                                    <thead>
                                      <tr>
                                        <th>Student Name</th>
                                        <th>Assigned Date</th>
                                        <th>Submission Date</th>
                                        <th>Deadline</th>
                                        <th>Status</th>
                                        <th>Submission / Notes</th>
                                        <th>Marks</th>
                                        <th>Action</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {filteredRows.map((st) => (
                                        <tr key={st.id}>
                                          <td>
                                            <div style={{ fontWeight: 700 }}>{st.student_name}</div>
                                            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{st.student_email}</div>
                                          </td>
                                          <td style={{ fontSize: 12 }}>
                                            {st.assigned_at ? new Date(st.assigned_at).toLocaleDateString() : "—"}
                                          </td>
                                          <td style={{ fontSize: 12 }}>
                                            {st.submitted_at ? new Date(st.submitted_at).toLocaleString() : "Not submitted"}
                                          </td>
                                          <td style={{ fontSize: 12 }}>
                                            {selectedPracticalForStudents.deadline
                                              ? new Date(selectedPracticalForStudents.deadline).toLocaleDateString()
                                              : "No deadline"}
                                          </td>
                                          <td>
                                            <AssignmentStatusBadge status={st.status} />
                                          </td>
                                          <td style={{ maxWidth: 240, fontSize: 12 }}>
                                            {st.submission_id && (
                                              <div>
                                                <button
                                                  type="button"
                                                  className="btn btn-outline"
                                                  style={{ padding: "2px 8px", fontSize: 11, marginBottom: 4 }}
                                                  onClick={() => {
                                                    setActiveTab("submissions");
                                                    handleInspectSubmission(st.submission_id);
                                                  }}
                                                >
                                                  Inspect Coding Sub #{st.submission_id}
                                                </button>
                                              </div>
                                            )}
                                            {st.submission_notes && (
                                              <div style={{ color: "var(--text-main)" }}>{st.submission_notes}</div>
                                            )}
                                            {st.attachment_filename && (
                                              <div style={{ fontSize: 11, color: "#1d4ed8", fontWeight: 600 }}>
                                                📎 {st.attachment_filename}
                                              </div>
                                            )}
                                            {!st.submission_id && !st.submission_notes && !st.attachment_filename && (
                                              <span style={{ color: "var(--text-muted)" }}>—</span>
                                            )}
                                          </td>
                                          <td style={{ fontWeight: 700, fontSize: 12 }}>
                                            {st.marks_obtained != null
                                              ? `${st.marks_obtained}/${selectedPracticalForStudents.max_marks || 10}`
                                              : `— / ${selectedPracticalForStudents.max_marks || 10}`}
                                          </td>
                                          <td>
                                            <button
                                              type="button"
                                              className="btn btn-outline"
                                              style={{ padding: "3px 8px", fontSize: 11 }}
                                              onClick={() =>
                                                setEvaluatingPracticalStudent({
                                                  practicalId: selectedPracticalForStudents.id,
                                                  studentId: st.student_id,
                                                  studentName: st.student_name,
                                                  status: st.status === "Not Started" ? "Evaluated" : st.status,
                                                  marks_obtained:
                                                    st.marks_obtained != null
                                                      ? st.marks_obtained
                                                      : selectedPracticalForStudents.max_marks || 10,
                                                  teacher_feedback: st.teacher_feedback || "",
                                                  max_marks: selectedPracticalForStudents.max_marks || 10,
                                                })
                                              }
                                            >
                                              Evaluate / Grade
                                            </button>
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              );
                            })()}
                          </>
                        )}
                      </div>
                    </div>
                  )}
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

                    <div
                      style={{
                        marginBottom: 16,
                        padding: "10px 14px",
                        backgroundColor: "#fef2f2",
                        border: "1px solid #fecaca",
                        borderRadius: 8,
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                      }}
                    >
                      <input
                        id="test-restrict-copy-paste"
                        type="checkbox"
                        checked={!newCodingTest.allow_copy_paste}
                        onChange={(e) =>
                          setNewCodingTest({
                            ...newCodingTest,
                            allow_copy_paste: !e.target.checked,
                          })
                        }
                        style={{ width: 16, height: 16, cursor: "pointer" }}
                      />
                      <label
                        htmlFor="test-restrict-copy-paste"
                        style={{ fontSize: 13, fontWeight: 600, cursor: "pointer", color: "#991b1b" }}
                      >
                        Enforce Strict Copy-Paste Prevention in Code Editor during Timed Assessment (Recommended)
                      </label>
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

                      {/* UNIQUE QUESTION CREATOR SUB-FORM (SIMPLIFIED — CONSTRAINTS & EXAMPLES OPTIONAL) */}
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
                            <div className="form-group" style={{ marginBottom: 0 }}>
                              <label className="form-label" style={{ fontSize: 13 }}>Sample Test Input *</label>
                              <input
                                type="text"
                                className="form-input"
                                placeholder="e.g. 5 10"
                                value={newTestCustomProblem.sample_input}
                                onChange={(e) => setNewTestCustomProblem({ ...newTestCustomProblem, sample_input: e.target.value })}
                              />
                            </div>

                            <div className="form-group" style={{ marginBottom: 0 }}>
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

                          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 14 }}>
                            <div className="form-group" style={{ marginBottom: 0 }}>
                              <label className="form-label" style={{ fontSize: 13 }}>Hidden Test Input (Optional)</label>
                              <input
                                type="text"
                                className="form-input"
                                placeholder="e.g. 100 250"
                                value={newTestCustomProblem.hidden_input}
                                onChange={(e) => setNewTestCustomProblem({ ...newTestCustomProblem, hidden_input: e.target.value })}
                              />
                            </div>

                            <div className="form-group" style={{ marginBottom: 0 }}>
                              <label className="form-label" style={{ fontSize: 13 }}>Hidden Expected Output (Optional)</label>
                              <input
                                type="text"
                                className="form-input"
                                placeholder="e.g. 350"
                                value={newTestCustomProblem.hidden_output}
                                onChange={(e) => setNewTestCustomProblem({ ...newTestCustomProblem, hidden_output: e.target.value })}
                              />
                            </div>
                          </div>

                          <div style={{ marginBottom: 14 }}>
                            <button
                              type="button"
                              className="btn btn-outline btn-sm"
                              style={{ fontSize: 11, padding: "3px 10px", backgroundColor: "white" }}
                              onClick={() => setShowOptionalTestProblemFields((prev) => !prev)}
                            >
                              {showOptionalTestProblemFields
                                ? "− Hide Optional Constraints & Examples"
                                : "+ Add Optional Constraints & Examples (Not Required)"}
                            </button>

                            {showOptionalTestProblemFields && (
                              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 10 }}>
                                <div className="form-group" style={{ marginBottom: 0 }}>
                                  <label className="form-label" style={{ fontSize: 12 }}>Constraints (Optional)</label>
                                  <textarea
                                    rows={2}
                                    className="form-textarea"
                                    placeholder="Optional, e.g. -10^9 <= a <= 10^9"
                                    value={newTestCustomProblem.constraints}
                                    onChange={(e) => setNewTestCustomProblem({ ...newTestCustomProblem, constraints: e.target.value })}
                                  />
                                </div>

                                <div className="form-group" style={{ marginBottom: 0 }}>
                                  <label className="form-label" style={{ fontSize: 12 }}>Examples (Optional)</label>
                                  <textarea
                                    rows={2}
                                    className="form-textarea"
                                    placeholder="Optional additional example notes"
                                    value={newTestCustomProblem.examples}
                                    onChange={(e) => setNewTestCustomProblem({ ...newTestCustomProblem, examples: e.target.value })}
                                  />
                                </div>
                              </div>
                            )}
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

              {/* TAB 4: MANAGE ASSIGNED ACTIVITIES & TESTS (WITH SEARCH & FILTER) */}
              {teacherTab === "manage" &&
                (() => {
                  const q = manageSearchQuery.trim().toLowerCase().replace(/^#/, "");
                  const matchesDate = (dateVal) => {
                    if (!manageDateFilter) return true;
                    if (!dateVal) return false;
                    return new Date(dateVal).toISOString().slice(0, 10) === manageDateFilter;
                  };

                  const filteredTests = codingTests.filter((t) => {
                    if (!matchesDate(t.created_at)) return false;
                    if (!q) return true;
                    const haystack = [
                      String(t.id),
                      t.title || "",
                      t.description || "",
                      t.creator_name || "",
                      ...(t.problems || []).map((p) => `${p.title || ""} ${p.topic || ""}`),
                    ]
                      .join(" ")
                      .toLowerCase();
                    return haystack.includes(q);
                  });

                  const filteredAssignments = assignments.filter((a) => {
                    if (!matchesDate(a.created_at)) return false;
                    if (!q) return true;
                    const haystack = [
                      String(a.id),
                      a.title || "",
                      a.description || "",
                      a.creator_name || "",
                      ...(a.problems || []).map((p) => `${p.title || ""} ${p.topic || ""}`),
                      ...(a.students || []).map((s) => `${s.name || ""} ${s.email || ""}`),
                    ]
                      .join(" ")
                      .toLowerCase();
                    return haystack.includes(q);
                  });

                  const filteredPracticals = practicals.filter((pr) => {
                    if (!matchesDate(pr.created_at)) return false;
                    if (!q) return true;
                    const haystack = [
                      String(pr.id),
                      `practical ${pr.practical_number}`,
                      String(pr.practical_number),
                      pr.title || "",
                      pr.subject_name || "",
                      pr.subject_code || "",
                      pr.semester || "",
                      pr.description || "",
                      pr.objectives || "",
                      pr.problem_title || "",
                      ...(pr.students || []).map((s) => `${s.student_name || ""} ${s.student_email || ""}`),
                    ]
                      .join(" ")
                      .toLowerCase();
                    return haystack.includes(q);
                  });

                  const filteredProblems = problems.filter((p) => {
                    if (!matchesDate(p.created_at)) return false;
                    if (!q) return true;
                    const haystack = [
                      String(p.id),
                      p.title || "",
                      p.description || "",
                      p.topic || "",
                      p.difficulty || "",
                    ]
                      .join(" ")
                      .toLowerCase();
                    return haystack.includes(q);
                  });

                  const showTests = manageTypeFilter === "all" || manageTypeFilter === "coding_tests";
                  const showAssignments = manageTypeFilter === "all" || manageTypeFilter === "assignments";
                  const showPracticals = manageTypeFilter === "all" || manageTypeFilter === "practicals";
                  const showProblems = manageTypeFilter === "all" || manageTypeFilter === "problems";

                  const totalMatched =
                    (showTests ? filteredTests.length : 0) +
                    (showAssignments ? filteredAssignments.length : 0) +
                    (showPracticals ? filteredPracticals.length : 0) +
                    (showProblems ? filteredProblems.length : 0);

                  return (
                    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                      {/* SEARCH & FILTER BAR FOR MANAGE ACTIVITIES */}
                      <div className="card" style={{ padding: "16px 20px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1, minWidth: 260 }}>
                            <Search size={18} color="var(--text-muted)" />
                            <input
                              type="text"
                              className="form-input"
                              placeholder="Search by test title, assignment title, practical, problem title, student name, topic, or #ID..."
                              value={manageSearchQuery}
                              onChange={(e) => setManageSearchQuery(e.target.value)}
                              style={{ flex: 1 }}
                            />
                            {manageSearchQuery && (
                              <button
                                type="button"
                                className="btn btn-outline btn-sm"
                                onClick={() => setManageSearchQuery("")}
                              >
                                Clear
                              </button>
                            )}
                          </div>

                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <select
                              className="form-select"
                              style={{ width: 190, fontSize: 13 }}
                              value={manageTypeFilter}
                              onChange={(e) => setManageTypeFilter(e.target.value)}
                            >
                              <option value="all">All Activity Types</option>
                              <option value="coding_tests">Designed Coding Tests</option>
                              <option value="assignments">Assigned Coursework</option>
                              <option value="practicals">Academic Practicals</option>
                              <option value="problems">Question Bank</option>
                            </select>

                            <input
                              type="date"
                              className="form-input"
                              style={{ width: 155, fontSize: 13 }}
                              value={manageDateFilter}
                              onChange={(e) => setManageDateFilter(e.target.value)}
                              title="Filter by creation date"
                            />

                            {(manageTypeFilter !== "all" || manageDateFilter) && (
                              <button
                                type="button"
                                className="btn btn-outline btn-sm"
                                onClick={() => {
                                  setManageTypeFilter("all");
                                  setManageDateFilter("");
                                }}
                              >
                                Reset Filters
                              </button>
                            )}
                          </div>
                        </div>
                      </div>

                      {totalMatched === 0 && (
                        <div className="card" style={{ textAlign: "center", padding: "36px 20px", color: "var(--text-muted)" }}>
                          No matching activities found for <strong>"{manageSearchQuery.trim()}"</strong>. Try clearing the search or adjusting filters.
                        </div>
                      )}

                      {showTests && (
                        <div className="card">
                          <h4 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
                            Designed Coding Tests ({filteredTests.length})
                          </h4>
                          {filteredTests.length === 0 ? (
                            <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                              {q || manageDateFilter ? "No coding tests match your search." : "No coding tests designed yet."}
                            </p>
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
                                  {filteredTests.map((t) => (
                                    <tr key={t.id}>
                                      <td>#{t.id}</td>
                                      <td>
                                        <strong>{t.title}</strong>
                                        {t.description && <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{t.description}</div>}
                                      </td>
                                      <td>{t.duration} mins</td>
                                      <td>{t.problems.map((p) => p.title).join(", ") || "None"}</td>
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
                      )}

                      {showAssignments && (
                        <div className="card">
                          <h4 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
                            Assigned Coursework Tracking ({filteredAssignments.length})
                          </h4>
                          {filteredAssignments.length === 0 ? (
                            <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                              {q || manageDateFilter ? "No assignments match your search." : "No assignments created yet."}
                            </p>
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
                                  {filteredAssignments.map((a) => (
                                    <tr key={a.id}>
                                      <td>#{a.id}</td>
                                      <td>
                                        <strong>{a.title}</strong>
                                        {a.description && <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{a.description}</div>}
                                      </td>
                                      <td>{a.problems.map((p) => p.title).join(", ") || "None"}</td>
                                      <td>
                                        <span className="badge badge-easy" title={a.students.map((s) => s.name).join(", ")}>
                                          {a.students.length} Students
                                        </span>
                                      </td>
                                      <td>{new Date(a.created_at).toLocaleDateString()}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </div>
                      )}

                      {showPracticals && (
                        <div className="card">
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                            <h4 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>
                              Academic Practicals Tracking ({filteredPracticals.length})
                            </h4>
                            <button
                              type="button"
                              className="btn btn-outline btn-sm"
                              onClick={() => {
                                setTeacherTab("create_assignment");
                                setCourseworkSubTab("track_practicals");
                              }}
                            >
                              Open Full Practical Tracker
                            </button>
                          </div>
                          {filteredPracticals.length === 0 ? (
                            <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                              {q || manageDateFilter ? "No academic practicals match your search." : "No academic practicals created yet."}
                            </p>
                          ) : (
                            <div className="table-container">
                              <table className="clan-table">
                                <thead>
                                  <tr>
                                    <th>ID</th>
                                    <th>Practical</th>
                                    <th>Subject</th>
                                    <th>Assigned Students</th>
                                    <th>Submitted / Pending</th>
                                    <th>Action</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {filteredPracticals.map((pr) => (
                                    <tr key={pr.id}>
                                      <td>#{pr.id}</td>
                                      <td>
                                        <strong>
                                          Practical {pr.practical_number}: {pr.title}
                                        </strong>
                                      </td>
                                      <td>{pr.subject_name}</td>
                                      <td>{pr.assigned_count} Students</td>
                                      <td>
                                        <span className="badge badge-status-accepted" style={{ marginRight: 6 }}>
                                          {pr.submitted_count} Submitted
                                        </span>
                                        <span className="badge badge-hard">{pr.pending_count} Pending</span>
                                      </td>
                                      <td>
                                        <button
                                          type="button"
                                          className="btn btn-outline"
                                          style={{ padding: "3px 10px", fontSize: 11 }}
                                          onClick={() => {
                                            setSelectedPracticalForStudents(pr);
                                            setTeacherTab("create_assignment");
                                            setCourseworkSubTab("track_practicals");
                                          }}
                                        >
                                          View Students
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

                      {showProblems && (
                        <div className="card">
                          <h4 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
                            Department Question Bank ({filteredProblems.length} Problems)
                          </h4>
                          {filteredProblems.length === 0 ? (
                            <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                              No problems match your search query.
                            </p>
                          ) : (
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
                                  {filteredProblems.map((p) => (
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
                          )}
                        </div>
                      )}
                    </div>
                  );
                })()}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
