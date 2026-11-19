import { useState, useRef, useEffect, useCallback } from "react";
import {
  Search,
  Play,
  Send,
  Save,
  RotateCcw,
  Maximize2,
  Minimize2,
  Columns,
  PanelLeftClose,
  PanelLeftOpen,
  BookMarked,
  Terminal,
  Lock,
  Unlock,
  CheckCircle2,
  LayoutGrid,
} from "lucide-react";
import CodeClanMonacoEditor from "./CodeClanMonacoEditor";
import ExecutionResultsPanel from "./ExecutionResultsPanel";
import { SUPPORTED_EDITOR_LANGUAGES } from "./starterTemplates";

const LAYOUT_STORAGE_KEY = "codeclan_workspace_layout_v2";

const DEFAULT_LAYOUT = {
  leftWidth: 240,
  middlePercent: 34,
  outputHeight: 235,
  fontSize: 14,
  leftCollapsed: false,
};

function loadLayoutPrefs() {
  try {
    const raw = localStorage.getItem(LAYOUT_STORAGE_KEY);
    if (!raw) return DEFAULT_LAYOUT;
    const parsed = JSON.parse(raw);
    return {
      leftWidth: Math.max(180, Math.min(420, Number(parsed.leftWidth) || DEFAULT_LAYOUT.leftWidth)),
      middlePercent: Math.max(20, Math.min(60, Number(parsed.middlePercent) || DEFAULT_LAYOUT.middlePercent)),
      outputHeight: Math.max(130, Math.min(540, Number(parsed.outputHeight) || DEFAULT_LAYOUT.outputHeight)),
      fontSize: Math.max(12, Math.min(22, Number(parsed.fontSize) || DEFAULT_LAYOUT.fontSize)),
      leftCollapsed: Boolean(parsed.leftCollapsed),
    };
  } catch {
    return DEFAULT_LAYOUT;
  }
}

function saveLayoutPrefs(prefs) {
  try {
    localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // ignore storage errors
  }
}

/**
 * CodingWorkspace
 *
 * Reusable Resizable Three-Panel Student Coding Workspace used across:
 * 1. Practice Problems (`activityType = "practice"`)
 * 2. My Assignments & Academic Practicals (`activityType = "assignment"` | `"practical"`)
 * 3. Official Timed Coding Tests (`activityType = "coding_test"`)
 */
export default function CodingWorkspace({
  activityType = "practice", // 'practice' | 'assignment' | 'practical' | 'coding_test'
  activityTitle = "Practice Problems",
  problems = [],
  selectedProblem = null,
  onSelectProblem,
  isLoadingProblems = false,
  searchQuery = "",
  onSearchChange,
  difficultyFilter = "",
  onDifficultyFilterChange,
  showSearchAndFilters = true,
  problemStatusMap = {}, // optional { [problemId]: { submitted: bool, status: string, marks: number } }

  // Editor & Multi-file state
  selectedLanguage = "python",
  onLanguageChange,
  editorCode = "",
  onEditorCodeChange,
  projectFiles = {},
  activeFileName = "main.py",
  onSelectProjectFile,
  newFileNameInput = "",
  onNewFileNameChange,
  onAddProjectFile,
  onDeleteProjectFile,
  onResetCode,
  allowMultiFile = true,

  // Execution & Grading
  onRunSamples,
  onSubmitSolution,
  isRunningSamples = false,
  isSubmitting = false,
  sampleRunResult = null,
  lastSubmissionResult = null,
  submitButtonLabel = "Submit Solution",
  submitButtonIcon = "send", // 'send' | 'save'

  // Clipboard & Security Policy
  disablePaste = false,
  disableCopy = false,
  canTogglePracticePastePolicy = false,
  onTogglePracticePastePolicy,
  securityStatus = null,
}) {
  const [layout, setLayout] = useState(() => loadLayoutPrefs());
  const [editorExpansion, setEditorExpansion] = useState("normal"); // 'normal' | 'expanded' | 'fullscreen'
  const [resultsMode, setResultsMode] = useState("sample"); // 'sample' | 'submission'
  const [resultsPanelState, setResultsPanelState] = useState("closed"); // 'open' | 'minimized' | 'expanded' | 'closed'
  const [mobileActiveTab, setMobileActiveTab] = useState("editor"); // 'list' | 'description' | 'editor'
  const [isCompactScreen, setIsCompactScreen] = useState(
    typeof window !== "undefined" ? window.innerWidth < 1024 : false
  );

  const workspaceRef = useRef(null);
  const draggingSplitterRef = useRef(null); // 'left' | 'middle' | null

  // Save layout preferences whenever changed
  useEffect(() => {
    saveLayoutPrefs(layout);
  }, [layout]);

  // Responsive viewport listener
  useEffect(() => {
    const handleResize = () => {
      setIsCompactScreen(window.innerWidth < 1024);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const handleTriggerRunSamples = () => {
    setResultsMode("sample");
    setResultsPanelState((prev) => (prev === "closed" || prev === "minimized" ? "open" : prev));
    if (onRunSamples) onRunSamples();
  };

  const handleTriggerSubmitSolution = () => {
    setResultsMode("submission");
    setResultsPanelState((prev) => (prev === "closed" || prev === "minimized" ? "open" : prev));
    if (onSubmitSolution) onSubmitSolution();
  };

  // Exit fullscreen on Escape key
  useEffect(() => {
    if (editorExpansion !== "fullscreen") return;
    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        setEditorExpansion("normal");
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [editorExpansion]);

  // Vertical splitter drag handlers
  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!draggingSplitterRef.current || !workspaceRef.current) return;
      const rect = workspaceRef.current.getBoundingClientRect();
      if (rect.width <= 0) return;

      if (draggingSplitterRef.current === "left") {
        const newLeft = Math.max(180, Math.min(420, e.clientX - rect.left));
        setLayout((prev) => ({ ...prev, leftWidth: Math.round(newLeft), leftCollapsed: false }));
      } else if (draggingSplitterRef.current === "middle") {
        const effectiveLeft =
          layout.leftCollapsed || editorExpansion === "expanded" ? 0 : layout.leftWidth;
        const remainingWidth = rect.width - effectiveLeft;
        if (remainingWidth <= 200) return;
        const offsetFromMiddleStart = e.clientX - rect.left - effectiveLeft;
        const pct = Math.max(18, Math.min(62, (offsetFromMiddleStart / remainingWidth) * 100));
        setLayout((prev) => ({ ...prev, middlePercent: Math.round(pct * 10) / 10 }));
        if (editorExpansion === "expanded") {
          setEditorExpansion("normal");
        }
      }
    };

    const handleMouseUp = () => {
      if (draggingSplitterRef.current) {
        draggingSplitterRef.current = null;
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      }
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [layout.leftCollapsed, layout.leftWidth, editorExpansion]);

  const startLeftDrag = (e) => {
    e.preventDefault();
    draggingSplitterRef.current = "left";
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  const startMiddleDrag = (e) => {
    e.preventDefault();
    draggingSplitterRef.current = "middle";
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  const handleRestoreDefaultLayout = useCallback(() => {
    setLayout(DEFAULT_LAYOUT);
    setEditorExpansion("normal");
    if (sampleRunResult || lastSubmissionResult) {
      setResultsPanelState("open");
    }
  }, [sampleRunResult, lastSubmissionResult]);

  const handleToggleExpandEditor = () => {
    setEditorExpansion((prev) => (prev === "expanded" ? "normal" : "expanded"));
  };

  const handleToggleFullscreenEditor = () => {
    setEditorExpansion((prev) => (prev === "fullscreen" ? "normal" : "fullscreen"));
  };

  const adjustFontSize = (delta) => {
    setLayout((prev) => ({
      ...prev,
      fontSize: Math.max(12, Math.min(22, prev.fontSize + delta)),
    }));
  };

  const isNonCpEnv =
    selectedProblem &&
    selectedProblem.environment_id &&
    selectedProblem.environment_id !== "cp";

  const hasSavedResults = Boolean(sampleRunResult || lastSubmissionResult);

  // Compute panel visibility and dimensions
  const isFullscreen = editorExpansion === "fullscreen";
  const isExpanded = editorExpansion === "expanded";
  const showLeftPane = !isFullscreen && !isExpanded && !layout.leftCollapsed;
  const showMiddlePane = !isFullscreen;
  const effectiveMiddlePercent = isExpanded ? 24 : layout.middlePercent;

  return (
    <div
      className={`coding-workspace-shell ${isFullscreen ? "workspace-fullscreen" : ""}`}
      data-testid="coding-workspace"
      data-activity-type={activityType}
      data-editor-expansion={editorExpansion}
      style={
        isFullscreen
          ? {
              position: "fixed",
              inset: 0,
              zIndex: 1000,
              backgroundColor: "var(--bg-app)",
              padding: 12,
              display: "flex",
              flexDirection: "column",
            }
          : {
              display: "flex",
              flexDirection: "column",
              gap: 10,
            }
      }
    >
      {/* MOBILE / TABLET RESPONSIVE PANEL SWITCHER (< 1024px) */}
      {isCompactScreen && !isFullscreen && (
        <div
          data-testid="responsive-panel-tabs"
          style={{
            display: "flex",
            gap: 6,
            backgroundColor: "white",
            padding: 6,
            borderRadius: 10,
            border: "1px solid var(--border-light)",
          }}
        >
          {[
            { id: "list", label: `1. Problems (${problems.length})` },
            { id: "description", label: "2. Problem Description" },
            { id: "editor", label: "3. Code Editor & Output" },
          ].map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setMobileActiveTab(t.id)}
              className={`btn ${mobileActiveTab === t.id ? "btn-primary" : "btn-outline"}`}
              style={{ flex: 1, padding: "6px 10px", fontSize: 12 }}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}

      {/* MAIN THREE-PANEL RESIZABLE CONTAINER */}
      <div
        ref={workspaceRef}
        className="resizable-three-panel-layout"
        style={{
          display: "flex",
          flexDirection: isCompactScreen && !isFullscreen ? "column" : "row",
          height: isFullscreen ? "100%" : "calc(100vh - 118px)",
          minHeight: 580,
          width: "100%",
          gap: 0,
          overflow: "hidden",
        }}
      >
        {/* ========================================================= */}
        {/* LEFT PANEL: PROBLEM LIST                                  */}
        {/* ========================================================= */}
        {((!isCompactScreen && showLeftPane) || (isCompactScreen && mobileActiveTab === "list")) && (
          <div
            className="problem-catalog-pane"
            data-testid="workspace-left-panel"
            style={{
              width: isCompactScreen ? "100%" : layout.leftWidth,
              minWidth: isCompactScreen ? "100%" : 180,
              maxWidth: isCompactScreen ? "100%" : 420,
              height: "100%",
              flexShrink: 0,
              display: "flex",
              flexDirection: "column",
              backgroundColor: "var(--bg-card)",
              border: "1px solid var(--border-light)",
              borderRadius: 12,
              overflow: "hidden",
            }}
          >
            {/* Left Panel Header */}
            <div
              style={{
                padding: "10px 12px",
                borderBottom: "1px solid var(--border-light)",
                backgroundColor: "#f8fafc",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 6,
              }}
            >
              <span
                title={activityTitle}
                style={{ fontSize: 12, fontWeight: 700, color: "var(--text-main)" }}
              >
                {activityType === "coding_test"
                  ? `Test Questions (${problems.length})`
                  : activityType === "assignment"
                  ? `Assigned Problems (${problems.length})`
                  : activityType === "practical"
                  ? `Practical Problem`
                  : `Problems (${problems.length})`}
              </span>
              {!isCompactScreen && (
                <button
                  type="button"
                  onClick={() => setLayout((prev) => ({ ...prev, leftCollapsed: true }))}
                  className="btn btn-outline"
                  style={{ padding: "2px 6px", fontSize: 11 }}
                  title="Collapse problem list to give more room to editor"
                >
                  <PanelLeftClose size={13} />
                </button>
              )}
            </div>

            {/* Search & Difficulty Filter (Practice Mode) */}
            {showSearchAndFilters && (
              <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--border-light)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                  <Search size={14} color="var(--text-muted)" />
                  <input
                    type="text"
                    placeholder="Search problems..."
                    value={searchQuery}
                    onChange={onSearchChange}
                    className="form-input"
                    style={{ flex: 1, padding: "5px 8px", fontSize: 12 }}
                  />
                </div>

                <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                  {["", "Easy", "Medium", "Hard"].map((lvl) => (
                    <button
                      key={lvl}
                      type="button"
                      onClick={() => onDifficultyFilterChange && onDifficultyFilterChange(lvl)}
                      className="btn btn-outline"
                      style={{
                        padding: "2px 7px",
                        fontSize: 11,
                        backgroundColor: difficultyFilter === lvl ? "var(--primary)" : "transparent",
                        color: difficultyFilter === lvl ? "white" : "var(--text-muted)",
                        borderColor:
                          difficultyFilter === lvl ? "var(--primary)" : "var(--border-subtle)",
                      }}
                    >
                      {lvl || "All"}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Scrollable Problem Items */}
            <div className="problem-list-scroll" style={{ flex: 1, overflowY: "auto" }}>
              {isLoadingProblems ? (
                <div
                  style={{
                    padding: 20,
                    textAlign: "center",
                    color: "var(--text-muted)",
                    fontSize: 12,
                  }}
                >
                  Loading problems...
                </div>
              ) : problems.length === 0 ? (
                <div
                  style={{
                    padding: 20,
                    textAlign: "center",
                    color: "var(--text-muted)",
                    fontSize: 12,
                  }}
                >
                  No problems match your query.
                </div>
              ) : (
                problems.map((p, idx) => {
                  const pid = p.id || p.problem_id;
                  const isSelected =
                    (selectedProblem?.id || selectedProblem?.problem_id) === pid;
                  const statusInfo = problemStatusMap[pid];
                  const diff = (p.difficulty || "Easy").toLowerCase();

                  return (
                    <div
                      key={pid}
                      onClick={() => {
                        if (onSelectProblem) onSelectProblem(p, idx);
                        if (isCompactScreen) setMobileActiveTab("description");
                      }}
                      className={`problem-list-item ${isSelected ? "selected" : ""}`}
                      style={{ padding: "10px 12px" }}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "flex-start",
                          gap: 6,
                        }}
                      >
                        <div
                          style={{
                            fontSize: 12.5,
                            fontWeight: 600,
                            color: isSelected ? "var(--primary)" : "var(--text-main)",
                            lineHeight: 1.35,
                          }}
                        >
                          {activityType === "coding_test" ? `Q${idx + 1}: ${p.title}` : p.title}
                        </div>
                        <span
                          className={`badge badge-${diff}`}
                          style={{ fontSize: 10, padding: "1px 6px", flexShrink: 0 }}
                        >
                          {p.difficulty || "Easy"}
                        </span>
                      </div>

                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          fontSize: 11,
                          color: "var(--text-muted)",
                          marginTop: 4,
                        }}
                      >
                        <span>{p.topic}</span>
                        {statusInfo?.status && (
                          <span
                            style={{
                              fontSize: 10,
                              fontWeight: 700,
                              color:
                                statusInfo.status === "Accepted" ||
                                statusInfo.status === "Submitted"
                                  ? "#15803d"
                                  : "#64748b",
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 3,
                            }}
                          >
                            {statusInfo.status === "Accepted" && <CheckCircle2 size={11} />}
                            {statusInfo.status}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        )}

        {/* VERTICAL SPLITTER 1: BETWEEN LEFT PANEL AND MIDDLE PANEL */}
        {!isCompactScreen && showLeftPane && showMiddlePane && (
          <div
            data-testid="splitter-left-middle"
            onMouseDown={startLeftDrag}
            title="Drag to resize Problem List width"
            style={{
              width: 10,
              cursor: "col-resize",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
              userSelect: "none",
            }}
          >
            <div
              style={{
                width: 3,
                height: 44,
                borderRadius: 999,
                backgroundColor: "#cbd5e1",
              }}
            />
          </div>
        )}

        {/* ========================================================= */}
        {/* MIDDLE PANEL: PROBLEM DESCRIPTION & SAMPLES               */}
        {/* ========================================================= */}
        {((!isCompactScreen && showMiddlePane) ||
          (isCompactScreen && mobileActiveTab === "description")) && (
          <div
            className="problem-details-pane"
            data-testid="workspace-middle-panel"
            style={{
              width: isCompactScreen ? "100%" : `${effectiveMiddlePercent}%`,
              minWidth: isCompactScreen ? "100%" : 230,
              height: "100%",
              flexShrink: 0,
              padding: "18px 20px",
              overflowY: "auto",
              display: "flex",
              flexDirection: "column",
              gap: 16,
              backgroundColor: "var(--bg-card)",
              border: "1px solid var(--border-light)",
              borderRadius: 12,
            }}
          >
            {/* Button to reopen collapsed Left Panel */}
            {!isCompactScreen && (layout.leftCollapsed || isExpanded) && (
              <div>
                <button
                  type="button"
                  onClick={() => {
                    setLayout((prev) => ({ ...prev, leftCollapsed: false }));
                    if (isExpanded) setEditorExpansion("normal");
                  }}
                  className="btn btn-outline"
                  style={{ padding: "3px 8px", fontSize: 11 }}
                  title="Show Problem List panel"
                >
                  <PanelLeftOpen size={13} /> Show Problem List
                </button>
              </div>
            )}

            {selectedProblem ? (
              <>
                <div>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      flexWrap: "wrap",
                      marginBottom: 8,
                    }}
                  >
                    <h2 style={{ fontSize: 20, fontWeight: 800, margin: 0 }}>
                      {selectedProblem.title}
                    </h2>
                    {selectedProblem.difficulty && (
                      <span
                        className={`badge badge-${selectedProblem.difficulty.toLowerCase()}`}
                      >
                        {selectedProblem.difficulty}
                      </span>
                    )}
                    {selectedProblem.topic && (
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
                    )}
                    <span
                      style={{
                        fontSize: 11,
                        fontWeight: 600,
                        backgroundColor: "#eff6ff",
                        color: "#1d4ed8",
                        border: "1px solid #bfdbfe",
                        padding: "2px 8px",
                        borderRadius: 6,
                      }}
                    >
                      Env:{" "}
                      {selectedProblem.environment_info?.name ||
                        selectedProblem.environment_id ||
                        "cp"}
                    </span>
                    {selectedProblem.evaluation_type &&
                      selectedProblem.evaluation_type !== "exact" && (
                        <span
                          style={{
                            fontSize: 11,
                            fontWeight: 600,
                            backgroundColor: "#f3e8ff",
                            color: "#6b21a8",
                            border: "1px solid #e9d5ff",
                            padding: "2px 8px",
                            borderRadius: 6,
                          }}
                        >
                          Eval: {selectedProblem.evaluation_type}
                        </span>
                      )}
                  </div>

                  {selectedProblem.environment_info?.libraries?.length > 0 && (
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>
                      <strong>Preinstalled Libraries:</strong>{" "}
                      {selectedProblem.environment_info.libraries.join(" • ")}
                    </div>
                  )}
                </div>

                <div>
                  <h4
                    style={{
                      fontSize: 13,
                      fontWeight: 700,
                      color: "var(--text-main)",
                      textTransform: "uppercase",
                      letterSpacing: "0.3px",
                      marginBottom: 6,
                    }}
                  >
                    Problem Statement
                  </h4>
                  <div
                    style={{
                      fontSize: 14,
                      lineHeight: 1.65,
                      color: "#334155",
                      whiteSpace: "pre-line",
                    }}
                  >
                    {selectedProblem.description || "No description provided."}
                  </div>
                </div>

                {selectedProblem.input_format && (
                  <div>
                    <h4
                      style={{
                        fontSize: 13,
                        fontWeight: 700,
                        color: "var(--text-main)",
                        marginBottom: 4,
                      }}
                    >
                      Input Format
                    </h4>
                    <div style={{ fontSize: 13, color: "#475569", whiteSpace: "pre-line" }}>
                      {selectedProblem.input_format}
                    </div>
                  </div>
                )}

                {selectedProblem.output_format && (
                  <div>
                    <h4
                      style={{
                        fontSize: 13,
                        fontWeight: 700,
                        color: "var(--text-main)",
                        marginBottom: 4,
                      }}
                    >
                      Output Format
                    </h4>
                    <div style={{ fontSize: 13, color: "#475569", whiteSpace: "pre-line" }}>
                      {selectedProblem.output_format}
                    </div>
                  </div>
                )}

                {selectedProblem.examples && (
                  <div>
                    <h4
                      style={{
                        fontSize: 13,
                        fontWeight: 700,
                        color: "var(--text-main)",
                        marginBottom: 6,
                      }}
                    >
                      Examples
                    </h4>
                    <pre
                      style={{
                        backgroundColor: "var(--bg-subtle)",
                        padding: 12,
                        borderRadius: 8,
                        fontSize: 12.5,
                        fontFamily: "var(--font-mono)",
                        whiteSpace: "pre-wrap",
                        margin: 0,
                      }}
                    >
                      {selectedProblem.examples}
                    </pre>
                  </div>
                )}

                {selectedProblem.constraints && (
                  <div>
                    <h4
                      style={{
                        fontSize: 13,
                        fontWeight: 700,
                        color: "var(--text-main)",
                        marginBottom: 6,
                      }}
                    >
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
                        margin: 0,
                      }}
                    >
                      {selectedProblem.constraints}
                    </pre>
                  </div>
                )}

                {selectedProblem.datasets?.length > 0 && (
                  <div>
                    <h4
                      style={{
                        fontSize: 13,
                        fontWeight: 700,
                        color: "var(--text-main)",
                        marginBottom: 6,
                      }}
                    >
                      Mounted Read-Only Datasets (/work/data/)
                    </h4>
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {selectedProblem.datasets.map((ds) => (
                        <div
                          key={ds.id}
                          style={{
                            border: "1px solid #bfdbfe",
                            borderRadius: 8,
                            padding: 10,
                            fontSize: 12,
                            backgroundColor: "#f8fafc",
                          }}
                        >
                          <div
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              fontWeight: 600,
                            }}
                          >
                            <code>/work/data/{ds.filename}</code>
                            <span style={{ color: "var(--text-muted)", fontSize: 11 }}>
                              {ds.size_bytes} bytes • {ds.mime_type}
                            </span>
                          </div>
                          {ds.description && (
                            <div
                              style={{
                                fontSize: 11,
                                color: "var(--text-muted)",
                                marginTop: 2,
                              }}
                            >
                              {ds.description}
                            </div>
                          )}
                          {ds.preview_text && (
                            <pre
                              style={{
                                marginTop: 6,
                                marginBottom: 0,
                                padding: 6,
                                backgroundColor: "#f1f5f9",
                                borderRadius: 4,
                                fontSize: 11,
                                maxHeight: 90,
                                overflowY: "auto",
                                whiteSpace: "pre-wrap",
                              }}
                            >
                              {ds.preview_text}
                            </pre>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div>
                  <h4
                    style={{
                      fontSize: 13,
                      fontWeight: 700,
                      color: "var(--text-main)",
                      marginBottom: 6,
                    }}
                  >
                    Sample Test Cases ({selectedProblem.test_cases?.length || 0})
                  </h4>
                  {selectedProblem.test_cases?.length > 0 ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      {selectedProblem.test_cases.map((tc, idx) => (
                        <div
                          key={tc.id || idx}
                          style={{
                            border: "1px solid var(--border-light)",
                            borderRadius: 8,
                            padding: 10,
                            fontSize: 12,
                            backgroundColor: "#fafbfc",
                          }}
                        >
                          <div
                            style={{
                              fontWeight: 700,
                              color: "var(--text-muted)",
                              marginBottom: 4,
                            }}
                          >
                            Sample #{idx + 1}
                          </div>
                          <div style={{ marginBottom: 4 }}>
                            <strong>Input:</strong>{" "}
                            <code
                              style={{
                                backgroundColor: "#f1f5f9",
                                padding: "2px 6px",
                                borderRadius: 4,
                              }}
                            >
                              {tc.input || "(empty)"}
                            </code>
                          </div>
                          {tc.expected_output !== undefined && (
                            <div>
                              <strong>Expected Output:</strong>{" "}
                              <code
                                style={{
                                  backgroundColor: "#f1f5f9",
                                  padding: "2px 6px",
                                  borderRadius: 4,
                                }}
                              >
                                {tc.expected_output}
                              </code>
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
                <p>
                  Select any problem from the left panel to load the problem statement and
                  examples.
                </p>
              </div>
            )}
          </div>
        )}

        {/* VERTICAL SPLITTER 2: BETWEEN MIDDLE PANEL AND RIGHT PANEL */}
        {!isCompactScreen && showMiddlePane && (
          <div
            data-testid="splitter-middle-right"
            onMouseDown={startMiddleDrag}
            title="Drag to resize Problem Description and Code Editor widths"
            style={{
              width: 10,
              cursor: "col-resize",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
              userSelect: "none",
            }}
          >
            <div
              style={{
                width: 3,
                height: 44,
                borderRadius: 999,
                backgroundColor: "#cbd5e1",
              }}
            />
          </div>
        )}

        {/* ========================================================= */}
        {/* RIGHT PANEL: MONACO CODE EDITOR & DOCKED RESULTS PANEL    */}
        {/* ========================================================= */}
        {(!isCompactScreen || mobileActiveTab === "editor" || isFullscreen) && (
          <div
            className="editor-pane"
            data-testid="workspace-right-panel"
            style={{
              flex: 1,
              minWidth: isCompactScreen ? "100%" : 340,
              height: "100%",
              display: "flex",
              flexDirection: "column",
              backgroundColor: "var(--bg-card)",
              border: "1px solid var(--border-light)",
              borderRadius: 12,
              overflow: "hidden",
            }}
          >
            {/* EDITOR HEADER / TOOLBAR */}
            <div
              className="editor-header"
              style={{
                padding: "8px 12px",
                borderBottom: "1px solid var(--border-light)",
                backgroundColor: "#f8fafc",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                flexWrap: "wrap",
                gap: 8,
              }}
            >
              {/* Left Toolbar Group: Language Selector + Font Size + Reset Code */}
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <label
                    htmlFor="workspace-language-select"
                    style={{ fontSize: 12, fontWeight: 700, color: "var(--text-main)" }}
                  >
                    Language:
                  </label>
                  <select
                    id="workspace-language-select"
                    data-testid="language-selector"
                    value={selectedLanguage}
                    onChange={(e) => onLanguageChange && onLanguageChange(e.target.value)}
                    disabled={Boolean(isNonCpEnv)}
                    className="form-select"
                    style={{ padding: "4px 8px", fontSize: 12 }}
                    title={
                      isNonCpEnv
                        ? "Specialized data science / ML environments run Python 3"
                        : "Select programming language"
                    }
                  >
                    {SUPPORTED_EDITOR_LANGUAGES.map((lang) => (
                      <option
                        key={lang.id}
                        value={lang.id}
                        disabled={Boolean(isNonCpEnv && lang.id !== "python")}
                      >
                        {lang.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Adjustable Font Size Controls */}
                <div
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: 6,
                    backgroundColor: "white",
                    overflow: "hidden",
                  }}
                  title="Adjust editor font size"
                >
                  <button
                    type="button"
                    data-testid="font-decrease-btn"
                    onClick={() => adjustFontSize(-1)}
                    style={{
                      border: "none",
                      background: "transparent",
                      padding: "3px 7px",
                      fontSize: 11,
                      fontWeight: 700,
                      cursor: "pointer",
                      color: "var(--text-main)",
                    }}
                  >
                    A-
                  </button>
                  <span
                    data-testid="editor-font-size-label"
                    style={{
                      fontSize: 11,
                      padding: "0 6px",
                      color: "var(--text-muted)",
                      borderLeft: "1px solid var(--border-light)",
                      borderRight: "1px solid var(--border-light)",
                    }}
                  >
                    {layout.fontSize}px
                  </span>
                  <button
                    type="button"
                    data-testid="font-increase-btn"
                    onClick={() => adjustFontSize(1)}
                    style={{
                      border: "none",
                      background: "transparent",
                      padding: "3px 7px",
                      fontSize: 11,
                      fontWeight: 700,
                      cursor: "pointer",
                      color: "var(--text-main)",
                    }}
                  >
                    A+
                  </button>
                </div>

                {/* Reset Code / Restore Starter Template Button */}
                {onResetCode && (
                  <button
                    type="button"
                    data-testid="reset-code-btn"
                    onClick={onResetCode}
                    className="btn btn-outline"
                    style={{ padding: "4px 8px", fontSize: 11, backgroundColor: "white" }}
                    title="Restore the clean starter template for the current language"
                  >
                    <RotateCcw size={12} /> Reset Code
                  </button>
                )}
              </div>

              {/* Right Toolbar Group: Paste Policy Badge + Expand / Fullscreen / Restore Layout */}
              <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                {/* Clipboard Policy Indicator */}
                {disablePaste ? (
                  <span
                    data-testid="paste-policy-badge"
                    onClick={
                      canTogglePracticePastePolicy ? onTogglePracticePastePolicy : undefined
                    }
                    style={{
                      fontSize: 11,
                      fontWeight: 700,
                      padding: "3px 8px",
                      borderRadius: 6,
                      backgroundColor: "#fef2f2",
                      color: "#991b1b",
                      border: "1px solid #fecaca",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                      cursor: canTogglePracticePastePolicy ? "pointer" : "default",
                    }}
                    title={
                      canTogglePracticePastePolicy
                        ? "Strict Paste Restriction Active (Click to allow paste in Practice)"
                        : "Paste is disabled for this assessment. Please type your solution manually."
                    }
                  >
                    <Lock size={11} /> Paste Disabled
                  </span>
                ) : (
                  <span
                    data-testid="paste-policy-badge"
                    onClick={
                      canTogglePracticePastePolicy ? onTogglePracticePastePolicy : undefined
                    }
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      padding: "3px 8px",
                      borderRadius: 6,
                      backgroundColor: "#f0fdf4",
                      color: "#166534",
                      border: "1px solid #bbf7d0",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4,
                      cursor: canTogglePracticePastePolicy ? "pointer" : "default",
                    }}
                    title={
                      canTogglePracticePastePolicy
                        ? "Normal Copy-Paste Allowed (Click to test strict exam paste lock)"
                        : "Copy-paste is enabled in this workspace"
                    }
                  >
                    <Unlock size={11} /> Copy-Paste Allowed
                  </span>
                )}

                {!isCompactScreen && (
                  <>
                    <button
                      type="button"
                      data-testid="expand-editor-btn"
                      onClick={handleToggleExpandEditor}
                      className="btn btn-outline"
                      style={{
                        padding: "4px 8px",
                        fontSize: 11,
                        backgroundColor: isExpanded ? "#eff6ff" : "white",
                        borderColor: isExpanded ? "var(--primary)" : undefined,
                        color: isExpanded ? "var(--primary)" : undefined,
                      }}
                      title="Allocate more horizontal screen space to the code editor"
                    >
                      <Columns size={12} /> {isExpanded ? "Standard Width" : "Expand Editor"}
                    </button>

                    <button
                      type="button"
                      data-testid="fullscreen-editor-btn"
                      onClick={handleToggleFullscreenEditor}
                      className="btn btn-outline"
                      style={{
                        padding: "4px 8px",
                        fontSize: 11,
                        backgroundColor: isFullscreen ? "#1e293b" : "white",
                        color: isFullscreen ? "white" : undefined,
                      }}
                      title={
                        isFullscreen
                          ? "Exit fullscreen editor (Esc)"
                          : "Open editor in fullscreen mode"
                      }
                    >
                      {isFullscreen ? (
                        <>
                          <Minimize2 size={12} /> Exit Fullscreen
                        </>
                      ) : (
                        <>
                          <Maximize2 size={12} /> Fullscreen
                        </>
                      )}
                    </button>

                    <button
                      type="button"
                      data-testid="restore-layout-btn"
                      onClick={handleRestoreDefaultLayout}
                      className="btn btn-outline"
                      style={{ padding: "4px 8px", fontSize: 11, backgroundColor: "white" }}
                      title="Restore default three-panel layout sizes"
                    >
                      <LayoutGrid size={12} /> Restore Default Layout
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* MULTI-FILE PROJECT TAB BAR */}
            {allowMultiFile && projectFiles && Object.keys(projectFiles).length > 0 && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 8,
                  padding: "6px 12px",
                  backgroundColor: "#f8fafc",
                  borderBottom: "1px solid var(--border-light)",
                  flexWrap: "wrap",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                  {Object.keys(projectFiles).map((fname) => {
                    const active = fname === activeFileName;
                    return (
                      <div
                        key={fname}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                          padding: "3px 8px",
                          borderRadius: 6,
                          fontSize: 12,
                          fontWeight: active ? 700 : 500,
                          backgroundColor: active ? "var(--primary)" : "white",
                          color: active ? "white" : "var(--text-main)",
                          border: `1px solid ${
                            active ? "var(--primary)" : "var(--border-light)"
                          }`,
                          cursor: "pointer",
                        }}
                        onClick={() => onSelectProjectFile && onSelectProjectFile(fname)}
                      >
                        <span>{fname}</span>
                        {Object.keys(projectFiles).length > 1 && onDeleteProjectFile && (
                          <span
                            title={`Remove ${fname}`}
                            style={{ marginLeft: 4, opacity: 0.85, fontWeight: 700 }}
                            onClick={(e) => {
                              e.stopPropagation();
                              onDeleteProjectFile(fname);
                            }}
                          >
                            ×
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>

                {onAddProjectFile && (
                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <input
                      type="text"
                      placeholder="Add file (e.g. utils.py)"
                      value={newFileNameInput}
                      onChange={(e) =>
                        onNewFileNameChange && onNewFileNameChange(e.target.value)
                      }
                      className="form-input"
                      style={{ padding: "2px 8px", fontSize: 11, width: 145 }}
                    />
                    <button
                      type="button"
                      className="btn btn-outline"
                      style={{ padding: "2px 8px", fontSize: 11, backgroundColor: "white" }}
                      onClick={onAddProjectFile}
                    >
                      + Add File
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* MONACO CODE EDITOR */}
            <CodeClanMonacoEditor
              code={editorCode}
              onChange={onEditorCodeChange}
              language={selectedLanguage}
              fileName={activeFileName}
              fontSize={layout.fontSize}
              disablePaste={disablePaste}
              disableCopy={disableCopy}
            />

            {/* DOCKED EXECUTION RESULTS PANEL (Resizable, Minimizable, Closable, Scrollable) */}
            <ExecutionResultsPanel
              activeMode={resultsMode}
              onSelectMode={setResultsMode}
              isRunningSamples={isRunningSamples}
              isSubmitting={isSubmitting}
              sampleRunResult={sampleRunResult}
              lastSubmissionResult={lastSubmissionResult}
              panelState={resultsPanelState}
              onChangePanelState={setResultsPanelState}
              height={layout.outputHeight}
              onChangeHeight={(h) => setLayout((prev) => ({ ...prev, outputHeight: h }))}
            />

            {/* EDITOR FOOTER: RUN SAMPLES, REOPEN RESULTS, SUBMIT SOLUTION */}
            <div
              className="editor-footer"
              style={{
                padding: "10px 14px",
                borderTop: "1px solid var(--border-light)",
                backgroundColor: "#f8fafc",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 10,
                flexWrap: "wrap",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <button
                  type="button"
                  data-testid="run-samples-btn"
                  className="btn btn-outline"
                  style={{ backgroundColor: "white" }}
                  onClick={handleTriggerRunSamples}
                  disabled={isRunningSamples || isSubmitting || !selectedProblem}
                  title="Execute code against public sample test cases in isolated sandbox"
                >
                  <Play size={15} />{" "}
                  {isRunningSamples ? "Running Samples..." : "Run Samples"}
                </button>

                {/* Reopen Results Button when the Output Panel is closed */}
                {resultsPanelState === "closed" && hasSavedResults && (
                  <button
                    type="button"
                    data-testid="reopen-results-btn"
                    className="btn btn-outline"
                    style={{
                      padding: "6px 12px",
                      fontSize: 12,
                      backgroundColor: "#eff6ff",
                      borderColor: "#93c5fd",
                      color: "#1d4ed8",
                    }}
                    onClick={() => setResultsPanelState("open")}
                    title="Reopen the most recent execution or submission results"
                  >
                    <Terminal size={14} /> View Last Results
                  </button>
                )}
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                {securityStatus && (
                  <span
                    title={securityStatus.message}
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      padding: "3px 8px",
                      borderRadius: 6,
                      backgroundColor: securityStatus.gvisor_verified
                        ? "#dcfce7"
                        : "#f1f5f9",
                      color: securityStatus.gvisor_verified ? "#166534" : "#475569",
                      border: `1px solid ${
                        securityStatus.gvisor_verified ? "#86efac" : "#cbd5e1"
                      }`,
                    }}
                  >
                    {securityStatus.gvisor_verified
                      ? "🛡️ gVisor (runsc) Sandbox"
                      : "🔒 Isolated Docker Sandbox"}
                  </span>
                )}

                <button
                  type="button"
                  data-testid="submit-solution-btn"
                  className="btn btn-primary"
                  onClick={handleTriggerSubmitSolution}
                  disabled={isSubmitting || isRunningSamples || !selectedProblem}
                >
                  {submitButtonIcon === "save" ? <Save size={15} /> : <Send size={15} />}{" "}
                  {isSubmitting ? "Submitting..." : submitButtonLabel}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
