import { useRef, useEffect } from "react";
import {
  ChevronDown,
  ChevronUp,
  Maximize2,
  Minimize2,
  X,
  Terminal,
  CheckCircle2,
  Loader2,
  GripHorizontal,
} from "lucide-react";
import { StatusBadge } from "./ui";

/**
 * ExecutionResultsPanel
 *
 * IDE-style output & submission results panel docked below the Monaco Code Editor.
 * Supports:
 * - Draggable top horizontal divider for resizing height
 * - Minimize into a compact status bar ("Last Run: <Verdict> | View Results")
 * - Expand / Restore height
 * - Close without losing result data or editor code
 * - Scrollable output for long tracebacks and multiple test cases
 * - Distinct tabs for "Run Samples" (public samples) and "Submit Solution" (graded verdict)
 */
export default function ExecutionResultsPanel({
  activeMode, // 'sample' | 'submission'
  onSelectMode,
  isRunningSamples = false,
  isSubmitting = false,
  sampleRunResult = null,
  lastSubmissionResult = null,
  panelState = "open", // 'open' | 'minimized' | 'expanded' | 'closed'
  onChangePanelState,
  height = 240,
  onChangeHeight,
}) {
  const isDraggingRef = useRef(false);
  const startYRef = useRef(0);
  const startHeightRef = useRef(height);

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isDraggingRef.current) return;
      const deltaY = startYRef.current - e.clientY;
      const nextHeight = Math.max(130, Math.min(560, startHeightRef.current + deltaY));
      if (onChangeHeight) onChangeHeight(nextHeight);
    };

    const handleMouseUp = () => {
      if (isDraggingRef.current) {
        isDraggingRef.current = false;
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
  }, [onChangeHeight]);

  const handleResizeStart = (e) => {
    e.preventDefault();
    isDraggingRef.current = true;
    startYRef.current = e.clientY;
    startHeightRef.current = panelState === "expanded" ? 440 : height;
    if (panelState === "minimized" || panelState === "expanded") {
      onChangePanelState("open");
    }
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
  };

  const hasAnyResult = Boolean(
    isRunningSamples || isSubmitting || sampleRunResult || lastSubmissionResult
  );

  if (!hasAnyResult || panelState === "closed") {
    return null;
  }

  // Determine active summary for minimized status bar and header indicator
  const showingSample = activeMode === "sample";
  const currentStatus = isRunningSamples
    ? "Running Samples..."
    : isSubmitting
    ? "Submitting & Grading..."
    : showingSample
    ? sampleRunResult?.status || lastSubmissionResult?.status || "Ready"
    : lastSubmissionResult?.status || sampleRunResult?.status || "Ready";

  const getStatusColor = (st) => {
    if (!st) return { bg: "#f8fafc", border: "#e2e8f0", text: "#334155" };
    if (st === "Accepted" || st === "Passed" || st === "Completed" || st === "Evaluated") {
      return { bg: "#ecfdf5", border: "#86efac", text: "#15803d" };
    }
    if (
      st.includes("Running") ||
      st.includes("Pending") ||
      st.includes("Submitting") ||
      st.includes("Grading")
    ) {
      return { bg: "#fffbeb", border: "#fde68a", text: "#b45309" };
    }
    return { bg: "#fef2f2", border: "#fecaca", text: "#b91c1c" };
  };

  const statusTheme = getStatusColor(currentStatus);

  // MINIMIZED COMPACT STATUS BAR
  if (panelState === "minimized") {
    const summaryLabel = isRunningSamples
      ? "Running Sample Test Cases..."
      : isSubmitting
      ? "Submitting Solution to Grader..."
      : showingSample && sampleRunResult
      ? `Last Run: ${sampleRunResult.status} (${sampleRunResult.passed_count ?? 0}/${
          sampleRunResult.total_count ?? 0
        } public samples)`
      : lastSubmissionResult
      ? `Last Submission #${lastSubmissionResult.id}: ${lastSubmissionResult.status} (${
          lastSubmissionResult.score ?? 0
        }/${lastSubmissionResult.max_score ?? 10} pts)`
      : sampleRunResult
      ? `Last Run: ${sampleRunResult.status}`
      : "Execution Results";

    return (
      <div
        data-testid="execution-results-minimized-bar"
        onClick={() => onChangePanelState("open")}
        style={{
          padding: "8px 14px",
          backgroundColor: statusTheme.bg,
          borderTop: `2px solid ${statusTheme.border}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          cursor: "pointer",
          fontSize: 12,
          fontWeight: 600,
          color: statusTheme.text,
          userSelect: "none",
        }}
        title="Click to reopen the execution results panel"
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Terminal size={14} />
          <span>{summaryLabel}</span>
          <span style={{ color: "var(--primary)", textDecoration: "underline", marginLeft: 4 }}>
            | View Results
          </span>
        </div>

        <div
          style={{ display: "flex", alignItems: "center", gap: 6 }}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            className="btn btn-outline"
            style={{ padding: "2px 8px", fontSize: 11, backgroundColor: "white" }}
            onClick={() => onChangePanelState("open")}
            title="Restore results panel"
          >
            <ChevronUp size={13} /> Restore
          </button>
          <button
            type="button"
            className="btn btn-outline"
            style={{ padding: "2px 6px", fontSize: 11, backgroundColor: "white" }}
            onClick={() => onChangePanelState("closed")}
            title="Close results panel"
          >
            <X size={13} />
          </button>
        </div>
      </div>
    );
  }

  const effectiveHeight = panelState === "expanded" ? 440 : height;

  return (
    <div
      className="execution-results-panel"
      data-testid="execution-results-panel"
      style={{
        height: effectiveHeight,
        minHeight: 130,
        maxHeight: "72%",
        display: "flex",
        flexDirection: "column",
        backgroundColor: "#ffffff",
        borderTop: "1px solid var(--border-light)",
        flexShrink: 0,
      }}
    >
      {/* DRAGGABLE HORIZONTAL RESIZE DIVIDER */}
      <div
        data-testid="results-panel-resize-handle"
        onMouseDown={handleResizeStart}
        title="Drag up or down to resize output panel"
        style={{
          height: 7,
          backgroundColor: "#f1f5f9",
          borderTop: "1px solid #cbd5e1",
          borderBottom: "1px solid #e2e8f0",
          cursor: "row-resize",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        <GripHorizontal size={14} color="#94a3b8" />
      </div>

      {/* PANEL HEADER: TABS + WINDOW CONTROLS (Minimize / Expand / Restore / Close) */}
      <div
        style={{
          padding: "6px 12px",
          backgroundColor: "#f8fafc",
          borderBottom: "1px solid var(--border-light)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          flexWrap: "wrap",
          flexShrink: 0,
        }}
      >
        {/* Left: Mode Tabs (Run Samples vs Submit Solution) */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <button
            type="button"
            data-testid="tab-sample-results"
            onClick={() => onSelectMode("sample")}
            style={{
              padding: "4px 10px",
              fontSize: 12,
              fontWeight: activeMode === "sample" ? 700 : 500,
              borderRadius: 6,
              border:
                activeMode === "sample"
                  ? "1px solid var(--primary)"
                  : "1px solid transparent",
              backgroundColor: activeMode === "sample" ? "#eff6ff" : "transparent",
              color: activeMode === "sample" ? "var(--primary)" : "var(--text-muted)",
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <Terminal size={13} />
            <span>Sample Run Output</span>
            {sampleRunResult && !isRunningSamples && (
              <span
                style={{
                  fontSize: 10,
                  padding: "1px 6px",
                  borderRadius: 999,
                  backgroundColor:
                    sampleRunResult.status === "Accepted" ? "#dcfce7" : "#fee2e2",
                  color: sampleRunResult.status === "Accepted" ? "#166534" : "#991b1b",
                  fontWeight: 700,
                }}
              >
                {sampleRunResult.passed_count ?? 0}/{sampleRunResult.total_count ?? 0}
              </span>
            )}
          </button>

          <button
            type="button"
            data-testid="tab-submission-results"
            onClick={() => onSelectMode("submission")}
            style={{
              padding: "4px 10px",
              fontSize: 12,
              fontWeight: activeMode === "submission" ? 700 : 500,
              borderRadius: 6,
              border:
                activeMode === "submission"
                  ? "1px solid var(--primary)"
                  : "1px solid transparent",
              backgroundColor: activeMode === "submission" ? "#eff6ff" : "transparent",
              color: activeMode === "submission" ? "var(--primary)" : "var(--text-muted)",
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <CheckCircle2 size={13} />
            <span>Submission Verdict</span>
            {lastSubmissionResult && !isSubmitting && (
              <span
                style={{
                  fontSize: 10,
                  padding: "1px 6px",
                  borderRadius: 999,
                  backgroundColor:
                    lastSubmissionResult.status === "Accepted"
                      ? "#dcfce7"
                      : lastSubmissionResult.status === "Pending Evaluation" ||
                        lastSubmissionResult.status === "Running"
                      ? "#fef3c7"
                      : "#fee2e2",
                  color:
                    lastSubmissionResult.status === "Accepted"
                      ? "#166534"
                      : lastSubmissionResult.status === "Pending Evaluation" ||
                        lastSubmissionResult.status === "Running"
                      ? "#92400e"
                      : "#991b1b",
                  fontWeight: 700,
                }}
              >
                #{lastSubmissionResult.id}
              </span>
            )}
          </button>
        </div>

        {/* Right: Minimize, Expand/Restore, Close controls */}
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <button
            type="button"
            data-testid="results-minimize-btn"
            className="btn btn-outline"
            style={{ padding: "3px 8px", fontSize: 11 }}
            onClick={() => onChangePanelState("minimized")}
            title="Minimize results panel to status bar"
          >
            <ChevronDown size={13} /> Minimize
          </button>

          {panelState === "expanded" ? (
            <button
              type="button"
              data-testid="results-restore-btn"
              className="btn btn-outline"
              style={{ padding: "3px 8px", fontSize: 11 }}
              onClick={() => onChangePanelState("open")}
              title="Restore results panel height"
            >
              <Minimize2 size={13} /> Restore
            </button>
          ) : (
            <button
              type="button"
              data-testid="results-expand-btn"
              className="btn btn-outline"
              style={{ padding: "3px 8px", fontSize: 11 }}
              onClick={() => onChangePanelState("expanded")}
              title="Expand results panel height"
            >
              <Maximize2 size={13} /> Expand
            </button>
          )}

          <button
            type="button"
            data-testid="results-close-btn"
            className="btn btn-outline"
            style={{ padding: "3px 8px", fontSize: 11, color: "#64748b" }}
            onClick={() => onChangePanelState("closed")}
            title="Close results panel and return space to editor (results are preserved)"
          >
            <X size={13} /> Close
          </button>
        </div>
      </div>

      {/* SCROLLABLE OUTPUT BODY */}
      <div
        data-testid="execution-results-scroll-body"
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "12px 16px",
          fontSize: 12,
        }}
      >
        {/* --------------------------------------------------------- */}
        {/* TAB 1: RUN SAMPLES VIEW (Public Sample Test Cases Only) */}
        {/* --------------------------------------------------------- */}
        {activeMode === "sample" && (
          <>
            {isRunningSamples ? (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "20px 12px",
                  color: "#1e40af",
                  backgroundColor: "#eff6ff",
                  borderRadius: 8,
                  border: "1px solid #bfdbfe",
                  fontWeight: 600,
                }}
              >
                <Loader2 size={18} className="spin-icon" />
                <span>
                  Executing your code against public sample test cases in an isolated sandbox container...
                </span>
              </div>
            ) : !sampleRunResult ? (
              <div style={{ padding: "18px 8px", color: "var(--text-muted)", textAlign: "center" }}>
                Click <strong>Run Samples</strong> below to test your code against public sample test cases.
              </div>
            ) : (
              <div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    flexWrap: "wrap",
                    gap: 8,
                    padding: "8px 12px",
                    borderRadius: 8,
                    backgroundColor:
                      sampleRunResult.status === "Accepted" ? "#f0fdf4" : "#fef2f2",
                    border: `1px solid ${
                      sampleRunResult.status === "Accepted" ? "#86efac" : "#fecaca"
                    }`,
                    marginBottom: 10,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <strong>Sample Run Verdict:</strong>
                    <StatusBadge status={sampleRunResult.status} />
                    <span style={{ color: "var(--text-main)", fontWeight: 600 }}>
                      {sampleRunResult.passed_count ?? 0}/{sampleRunResult.total_count ?? 0} public
                      sample test case(s) passed
                    </span>
                    {sampleRunResult.execution_time != null && (
                      <span style={{ color: "var(--text-muted)" }}>
                        • {sampleRunResult.execution_time} ms
                      </span>
                    )}
                    {sampleRunResult.memory_used != null && (
                      <span style={{ color: "var(--text-muted)" }}>
                        • {Math.round(sampleRunResult.memory_used)} KB
                      </span>
                    )}
                  </div>
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    Public Samples Only (Hidden tests run on Submit)
                  </span>
                </div>

                {/* Compiler / Runtime Error Traceback */}
                {(sampleRunResult.compile_error || sampleRunResult.error_message) && (
                  <div style={{ marginBottom: 10 }}>
                    <div
                      style={{
                        fontSize: 11,
                        fontWeight: 700,
                        color: "#991b1b",
                        marginBottom: 4,
                        textTransform: "uppercase",
                      }}
                    >
                      {sampleRunResult.status === "Compilation Error"
                        ? "Compiler Error Output:"
                        : "Execution Error / Traceback:"}
                    </div>
                    <pre
                      data-testid="sample-error-traceback"
                      style={{
                        backgroundColor: "#0f172a",
                        color: "#f87171",
                        padding: "10px 12px",
                        borderRadius: 8,
                        fontSize: 11.5,
                        fontFamily: "var(--font-mono)",
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                        maxHeight: 240,
                        overflowY: "auto",
                        margin: 0,
                      }}
                    >
                      {sampleRunResult.compile_error || sampleRunResult.error_message}
                    </pre>
                  </div>
                )}

                {/* Per-Sample Test Case Cards */}
                {sampleRunResult.results?.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {sampleRunResult.results.map((r, idx) => (
                      <div
                        key={r.test_case_id || idx}
                        style={{
                          backgroundColor: "#f8fafc",
                          border: `1px solid ${r.passed ? "#bbf7d0" : "#fecaca"}`,
                          borderRadius: 8,
                          padding: "10px 12px",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            fontWeight: 700,
                            marginBottom: 6,
                          }}
                        >
                          <span>Public Sample #{idx + 1}</span>
                          <span
                            style={{
                              color: r.passed ? "#15803d" : "#b91c1c",
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 6,
                            }}
                          >
                            <StatusBadge status={r.status} />
                            <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 500 }}>
                              {r.execution_time ?? 0} ms
                              {r.memory_used ? ` • ${Math.round(r.memory_used)} KB` : ""}
                            </span>
                          </span>
                        </div>

                        <div
                          style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
                            gap: 8,
                            fontFamily: "var(--font-mono)",
                            fontSize: 11,
                          }}
                        >
                          <div
                            style={{
                              backgroundColor: "white",
                              padding: 8,
                              borderRadius: 6,
                              border: "1px solid var(--border-light)",
                            }}
                          >
                            <div style={{ color: "var(--text-muted)", fontWeight: 700, marginBottom: 2 }}>
                              Input:
                            </div>
                            <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                              {r.input || "(empty)"}
                            </pre>
                          </div>

                          <div
                            style={{
                              backgroundColor: "white",
                              padding: 8,
                              borderRadius: 6,
                              border: "1px solid var(--border-light)",
                            }}
                          >
                            <div style={{ color: "var(--text-muted)", fontWeight: 700, marginBottom: 2 }}>
                              Expected Output:
                            </div>
                            <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                              {r.expected_output ?? "(empty)"}
                            </pre>
                          </div>

                          <div
                            style={{
                              backgroundColor: "white",
                              padding: 8,
                              borderRadius: 6,
                              border: `1px solid ${r.passed ? "#bbf7d0" : "#fecaca"}`,
                            }}
                          >
                            <div style={{ color: "var(--text-muted)", fontWeight: 700, marginBottom: 2 }}>
                              Actual Output:
                            </div>
                            <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                              {r.actual_output !== undefined && r.actual_output !== ""
                                ? r.actual_output
                                : "(empty)"}
                            </pre>
                          </div>
                        </div>

                        {r.feedback && (
                          <div style={{ color: "#1e40af", fontSize: 11, marginTop: 6 }}>
                            <strong>Evaluator Feedback:</strong> {r.feedback}
                          </div>
                        )}

                        {r.metrics && Object.keys(r.metrics).length > 0 && (
                          <div
                            style={{
                              display: "flex",
                              gap: 6,
                              flexWrap: "wrap",
                              marginTop: 6,
                              fontSize: 11,
                            }}
                          >
                            {Object.entries(r.metrics).map(([mk, mv]) => (
                              <span
                                key={mk}
                                style={{
                                  backgroundColor: "#eff6ff",
                                  border: "1px solid #bfdbfe",
                                  padding: "2px 6px",
                                  borderRadius: 4,
                                  color: "#1e3a8a",
                                }}
                              >
                                <strong>{mk}:</strong> {String(mv)}
                              </span>
                            ))}
                          </div>
                        )}

                        {r.output_files?.length > 0 && (
                          <div style={{ marginTop: 6, fontSize: 11 }}>
                            <strong>Generated Files (/work/output/):</strong>{" "}
                            {r.output_files.map((of, fIdx) => (
                              <span key={fIdx} style={{ marginRight: 8 }}>
                                <code>{of.name}</code> ({of.size_bytes} B)
                                {of.name?.endsWith(".png") && of.content_b64 && (
                                  <img
                                    src={`data:image/png;base64,${of.content_b64}`}
                                    alt={of.name}
                                    style={{
                                      display: "block",
                                      maxWidth: 240,
                                      maxHeight: 140,
                                      marginTop: 4,
                                      border: "1px solid var(--border-light)",
                                      borderRadius: 4,
                                    }}
                                  />
                                )}
                              </span>
                            ))}
                          </div>
                        )}

                        {r.error_message && (
                          <pre
                            style={{
                              backgroundColor: "#0f172a",
                              color: "#f87171",
                              padding: 8,
                              borderRadius: 6,
                              fontSize: 11,
                              marginTop: 6,
                              marginBottom: 0,
                              whiteSpace: "pre-wrap",
                              wordBreak: "break-word",
                              fontFamily: "var(--font-mono)",
                            }}
                          >
                            {r.error_message}
                          </pre>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {/* --------------------------------------------------------- */}
        {/* TAB 2: SUBMIT SOLUTION VIEW (Graded Final Verdict)        */}
        {/* --------------------------------------------------------- */}
        {activeMode === "submission" && (
          <>
            {isSubmitting && !lastSubmissionResult ? (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "20px 12px",
                  color: "#92400e",
                  backgroundColor: "#fffbeb",
                  borderRadius: 8,
                  border: "1px solid #fde68a",
                  fontWeight: 600,
                }}
              >
                <Loader2 size={18} className="spin-icon" />
                <span>
                  Submitting your solution to the isolated grader worker for automated evaluation...
                </span>
              </div>
            ) : !lastSubmissionResult ? (
              <div style={{ padding: "18px 8px", color: "var(--text-muted)", textAlign: "center" }}>
                Click <strong>Submit Solution</strong> below to evaluate your solution against all public and hidden test cases.
              </div>
            ) : (
              <div>
                <div
                  style={{
                    padding: "10px 14px",
                    borderRadius: 8,
                    backgroundColor:
                      lastSubmissionResult.status === "Accepted"
                        ? "#ecfdf5"
                        : lastSubmissionResult.status === "Pending Evaluation" ||
                          lastSubmissionResult.status === "Running"
                        ? "#fffbeb"
                        : "#fef2f2",
                    border: `1px solid ${
                      lastSubmissionResult.status === "Accepted"
                        ? "#86efac"
                        : lastSubmissionResult.status === "Pending Evaluation" ||
                          lastSubmissionResult.status === "Running"
                        ? "#fde68a"
                        : "#fecaca"
                    }`,
                    marginBottom: 10,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      flexWrap: "wrap",
                      gap: 8,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <strong>
                        {lastSubmissionResult.id
                          ? `Submission #${lastSubmissionResult.id}:`
                          : "Submission Verdict:"}
                      </strong>
                      <StatusBadge status={lastSubmissionResult.status} />
                      <span style={{ fontWeight: 800, color: "var(--text-main)" }}>
                        Score: {lastSubmissionResult.score ?? 0}/{lastSubmissionResult.max_score ?? 10} pts
                      </span>
                      <span style={{ color: "var(--text-muted)", fontWeight: 600 }}>
                        ({lastSubmissionResult.passed_count ?? 0}/{lastSubmissionResult.total_count ?? 0}{" "}
                        test cases passed
                        {lastSubmissionResult.execution_time != null
                          ? ` • ${lastSubmissionResult.execution_time} ms`
                          : ""}
                        {lastSubmissionResult.memory_used != null
                          ? ` • ${Math.round(lastSubmissionResult.memory_used)} KB`
                          : ""}
                        )
                      </span>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                      {lastSubmissionResult.context_label && (
                        <span
                          style={{
                            fontSize: 11,
                            backgroundColor: "white",
                            border: "1px solid var(--border-light)",
                            padding: "2px 8px",
                            borderRadius: 6,
                            fontWeight: 600,
                          }}
                        >
                          {lastSubmissionResult.context_label}
                        </span>
                      )}
                      {lastSubmissionResult.hidden_summary &&
                        lastSubmissionResult.hidden_summary.total > 0 && (
                          <span className="badge badge-medium" style={{ fontSize: 11 }}>
                            Hidden Tests: {lastSubmissionResult.hidden_summary.passed}/
                            {lastSubmissionResult.hidden_summary.total} Passed
                          </span>
                        )}
                    </div>
                  </div>

                  {(lastSubmissionResult.status === "Pending Evaluation" ||
                    lastSubmissionResult.status === "Running") && (
                    <div style={{ fontSize: 11.5, color: "#92400e", marginTop: 6, fontWeight: 600 }}>
                      ⏳ Isolated grader worker is evaluating your submission against public and hidden test cases...
                    </div>
                  )}
                </div>

                {/* Submission Metrics */}
                {lastSubmissionResult.metrics &&
                  Object.keys(lastSubmissionResult.metrics).length > 0 && (
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
                      {Object.entries(lastSubmissionResult.metrics).map(([mk, mv]) => (
                        <span
                          key={mk}
                          style={{
                            fontSize: 11,
                            backgroundColor: "#eff6ff",
                            border: "1px solid #bfdbfe",
                            padding: "2px 8px",
                            borderRadius: 4,
                            color: "#1e3a8a",
                          }}
                        >
                          <strong>{mk}:</strong> {String(mv)}
                        </span>
                      ))}
                    </div>
                  )}

                {/* Submission Error / Traceback */}
                {lastSubmissionResult.error_message && (
                  <div style={{ marginBottom: 10 }}>
                    <div
                      style={{
                        fontSize: 11,
                        fontWeight: 700,
                        color: "#991b1b",
                        marginBottom: 4,
                        textTransform: "uppercase",
                      }}
                    >
                      Error Details / Traceback:
                    </div>
                    <pre
                      data-testid="submission-error-traceback"
                      style={{
                        backgroundColor: "#0f172a",
                        color: "#f87171",
                        padding: "10px 12px",
                        borderRadius: 8,
                        fontSize: 11.5,
                        fontFamily: "var(--font-mono)",
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                        maxHeight: 240,
                        overflowY: "auto",
                        margin: 0,
                      }}
                    >
                      {lastSubmissionResult.error_message}
                    </pre>
                  </div>
                )}

                {/* Public Test Case Breakdown from Submission */}
                {lastSubmissionResult.public_results?.length > 0 && (
                  <div>
                    <div
                      style={{
                        fontSize: 11,
                        fontWeight: 700,
                        color: "var(--text-muted)",
                        textTransform: "uppercase",
                        marginBottom: 6,
                      }}
                    >
                      Public Test Cases Breakdown ({lastSubmissionResult.public_results.length})
                    </div>
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
                        gap: 8,
                      }}
                    >
                      {lastSubmissionResult.public_results.map((pr, idx) => (
                        <div
                          key={pr.test_case_id || idx}
                          style={{
                            backgroundColor: "#f8fafc",
                            border: `1px solid ${pr.passed ? "#bbf7d0" : "#fecaca"}`,
                            borderRadius: 6,
                            padding: 8,
                            fontSize: 11,
                          }}
                        >
                          <div
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              fontWeight: 700,
                              marginBottom: 4,
                            }}
                          >
                            <span>Public Case #{idx + 1}</span>
                            <StatusBadge status={pr.status} />
                          </div>
                          <div style={{ fontFamily: "var(--font-mono)", fontSize: 10.5 }}>
                            <div>
                              <strong>Input:</strong> {pr.input || "(empty)"}
                            </div>
                            <div>
                              <strong>Expected:</strong> {pr.expected_output ?? "(empty)"}
                            </div>
                            <div>
                              <strong>Actual:</strong> {pr.actual_output ?? "(none)"}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
