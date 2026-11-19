import { useEffect, useRef, useState, useCallback } from "react";
import Editor, { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import { ShieldAlert, X } from "lucide-react";
import { getMonacoLanguage } from "./starterTemplates";

// Configure @monaco-editor/react to use the locally bundled monaco-editor instance
// so it loads offline without external CDN latency or network failures.
loader.config({ monaco });

/**
 * CodeClanMonacoEditor
 *
 * Monaco Editor wrapper with:
 * - Dynamic resizing (`automaticLayout: true`)
 * - Configurable font size (12px–22px)
 * - Multi-language syntax highlighting (Python, C, C++, Java, JavaScript)
 * - Context-aware copy/paste/drop restrictions at the editor level
 * - Non-intrusive inline toast notification when paste/copy is blocked
 */
export default function CodeClanMonacoEditor({
  code,
  onChange,
  language = "python",
  fileName = "",
  fontSize = 14,
  disablePaste = false,
  disableCopy = false,
  readOnly = false,
  placeholder = "",
}) {
  const editorRef = useRef(null);
  const monacoRef = useRef(null);
  const containerRef = useRef(null);
  const disablePasteRef = useRef(disablePaste);
  const disableCopyRef = useRef(disableCopy);
  const isRevertingPasteRef = useRef(false);
  const toastTimerRef = useRef(null);

  const [restrictionNotice, setRestrictionNotice] = useState(null);

  useEffect(() => {
    disablePasteRef.current = disablePaste;
    disableCopyRef.current = disableCopy;
    if (editorRef.current) {
      editorRef.current.updateOptions({
        contextmenu: !(disablePaste || disableCopy),
        fontSize,
        readOnly,
      });
    }
  }, [disablePaste, disableCopy, fontSize, readOnly]);

  const showRestrictionToast = useCallback((msg) => {
    setRestrictionNotice(
      msg || "Paste is disabled for this assessment. Please type your solution manually."
    );
    if (toastTimerRef.current) {
      clearTimeout(toastTimerRef.current);
    }
    toastTimerRef.current = setTimeout(() => {
      setRestrictionNotice(null);
    }, 3800);
  }, []);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    };
  }, []);

  // DOM-level capture listeners on the editor container for paste, copy, cut, and drag-and-drop
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const handlePaste = (e) => {
      if (disablePasteRef.current) {
        e.preventDefault();
        e.stopPropagation();
        showRestrictionToast(
          "Paste is disabled for this assessment. Please type your solution manually."
        );
      }
    };

    const handleDrop = (e) => {
      if (disablePasteRef.current) {
        e.preventDefault();
        e.stopPropagation();
        showRestrictionToast(
          "Drag-and-drop text input is disabled for this assessment. Please type your solution manually."
        );
      }
    };

    const handleCopy = (e) => {
      if (disableCopyRef.current) {
        e.preventDefault();
        e.stopPropagation();
        showRestrictionToast(
          "Copying code from the editor is disabled during this assessment."
        );
      }
    };

    const handleCut = (e) => {
      if (disableCopyRef.current) {
        e.preventDefault();
        e.stopPropagation();
        showRestrictionToast(
          "Cutting code from the editor is disabled during this assessment."
        );
      }
    };

    const handleContextMenu = (e) => {
      if (disablePasteRef.current || disableCopyRef.current) {
        e.preventDefault();
      }
    };

    el.addEventListener("paste", handlePaste, true);
    el.addEventListener("drop", handleDrop, true);
    el.addEventListener("copy", handleCopy, true);
    el.addEventListener("cut", handleCut, true);
    el.addEventListener("contextmenu", handleContextMenu, true);

    return () => {
      el.removeEventListener("paste", handlePaste, true);
      el.removeEventListener("drop", handleDrop, true);
      el.removeEventListener("copy", handleCopy, true);
      el.removeEventListener("cut", handleCut, true);
      el.removeEventListener("contextmenu", handleContextMenu, true);
    };
  }, [showRestrictionToast]);

  const handleEditorDidMount = (editor, monacoInstance) => {
    editorRef.current = editor;
    monacoRef.current = monacoInstance;

    // 1. Intercept keyboard shortcuts for Paste / Copy / Cut inside Monaco
    editor.onKeyDown((e) => {
      const keyCode = e.keyCode;
      const isCtrlOrCmd = e.ctrlKey || e.metaKey;
      const isShift = e.shiftKey;

      // KeyCode.KeyV = 52 in Monaco, KeyCode.Insert = 19
      const isKeyV = keyCode === monacoInstance.KeyCode.KeyV;
      const isKeyC = keyCode === monacoInstance.KeyCode.KeyC;
      const isKeyX = keyCode === monacoInstance.KeyCode.KeyX;
      const isInsert = keyCode === monacoInstance.KeyCode.Insert;

      // Block Paste: Ctrl+V, Cmd+V, Ctrl+Shift+V, Shift+Insert
      if (disablePasteRef.current) {
        if ((isCtrlOrCmd && isKeyV) || (isShift && isInsert)) {
          e.preventDefault();
          e.stopPropagation();
          showRestrictionToast(
            "Paste is disabled for this assessment. Please type your solution manually."
          );
          return;
        }
      }

      // Block Copy / Cut in strict assessment contexts: Ctrl+C, Cmd+C, Ctrl+X, Cmd+X, Ctrl+Insert
      if (disableCopyRef.current) {
        if ((isCtrlOrCmd && (isKeyC || isKeyX || isInsert))) {
          e.preventDefault();
          e.stopPropagation();
          showRestrictionToast(
            "Copy and cut shortcuts are disabled during this assessment."
          );
          return;
        }
      }
    });

    // 2. Defense-in-depth: if a paste operation ever reaches Monaco's internal buffer while disabled,
    // immediately revert it via undo and notify the student.
    editor.onDidPaste(() => {
      if (disablePasteRef.current && !isRevertingPasteRef.current) {
        isRevertingPasteRef.current = true;
        try {
          editor.trigger("codeclan-paste-guard", "undo", null);
        } finally {
          isRevertingPasteRef.current = false;
        }
        showRestrictionToast(
          "Paste is disabled for this assessment. Please type your solution manually."
        );
      }
    });
  };

  const monacoLanguage = getMonacoLanguage(language, fileName);

  return (
    <div
      ref={containerRef}
      className="codeclan-monaco-wrapper"
      data-testid="code-editor-container"
      data-paste-disabled={disablePaste ? "true" : "false"}
      style={{
        position: "relative",
        flex: 1,
        minHeight: 160,
        width: "100%",
        display: "flex",
        flexDirection: "column",
        backgroundColor: "#1e1e1e",
        overflow: "hidden",
      }}
    >
      {/* Non-intrusive Paste/Copy Restriction Notification Toast */}
      {restrictionNotice && (
        <div
          role="status"
          aria-live="polite"
          data-testid="paste-restriction-toast"
          style={{
            position: "absolute",
            top: 10,
            right: 16,
            left: 16,
            zIndex: 30,
            backgroundColor: "#7f1d1d",
            color: "#fef2f2",
            border: "1px solid #f87171",
            borderRadius: 8,
            padding: "8px 14px",
            fontSize: 12,
            fontWeight: 600,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 10,
            boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.4)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <ShieldAlert size={16} color="#fca5a5" style={{ flexShrink: 0 }} />
            <span>{restrictionNotice}</span>
          </div>
          <button
            type="button"
            onClick={() => setRestrictionNotice(null)}
            style={{
              background: "transparent",
              border: "none",
              color: "#fecaca",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              padding: 2,
            }}
            title="Dismiss notification"
          >
            <X size={14} />
          </button>
        </div>
      )}

      <Editor
        height="100%"
        width="100%"
        theme="vs-dark"
        path={fileName || `solution.${monacoLanguage}`}
        language={monacoLanguage}
        value={code ?? ""}
        onChange={(val) => {
          if (!isRevertingPasteRef.current && onChange) {
            onChange(val ?? "");
          }
        }}
        onMount={handleEditorDidMount}
        options={{
          fontSize,
          fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', Consolas, monospace",
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          automaticLayout: true,
          tabSize: 4,
          insertSpaces: true,
          wordWrap: "on",
          lineNumbers: "on",
          renderLineHighlight: "all",
          bracketPairColorization: { enabled: true },
          autoIndent: "full",
          formatOnType: true,
          contextmenu: !(disablePaste || disableCopy),
          dropIntoEditor: { enabled: !disablePaste },
          readOnly,
          padding: { top: 12, bottom: 12 },
          smoothScrolling: true,
          cursorBlinking: "smooth",
          placeholder: placeholder || undefined,
        }}
      />
    </div>
  );
}
