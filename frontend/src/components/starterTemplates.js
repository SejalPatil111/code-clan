/**
 * Clean, beginner-friendly starter templates for each supported language in CodeClan.
 *
 * Rules:
 * - Never injects problem title, difficulty, topic, sample input, or sample output.
 * - Shows only the minimum required entry structure for the sandbox runner.
 * - Preserves function signature when a problem uses `function_harness` evaluation.
 */

export const SUPPORTED_EDITOR_LANGUAGES = [
  { id: "python", label: "Python 3", monacoLang: "python", defaultFile: "main.py" },
  { id: "c", label: "C (GCC)", monacoLang: "c", defaultFile: "main.c" },
  { id: "cpp", label: "C++ (GCC)", monacoLang: "cpp", defaultFile: "main.cpp" },
  { id: "java", label: "Java 17", monacoLang: "java", defaultFile: "Main.java" },
  { id: "javascript", label: "JavaScript (Node)", monacoLang: "javascript", defaultFile: "main.js" },
];

export function getDefaultFileNameForLang(lang) {
  const found = SUPPORTED_EDITOR_LANGUAGES.find((l) => l.id === lang);
  return found ? found.defaultFile : "main.py";
}

export function getMonacoLanguage(lang, fileName = "") {
  if (fileName) {
    const lower = fileName.toLowerCase();
    if (lower.endsWith(".py")) return "python";
    if (lower.endsWith(".cpp") || lower.endsWith(".cc") || lower.endsWith(".cxx") || lower.endsWith(".hpp")) return "cpp";
    if (lower.endsWith(".c") || lower.endsWith(".h")) return "c";
    if (lower.endsWith(".java")) return "java";
    if (lower.endsWith(".js") || lower.endsWith(".mjs") || lower.endsWith(".cjs")) return "javascript";
    if (lower.endsWith(".json")) return "json";
  }
  const found = SUPPORTED_EDITOR_LANGUAGES.find((l) => l.id === lang);
  return found ? found.monacoLang : "python";
}

export function getCleanStarterTemplate(language, problem = null) {
  if (language === "c") {
    return `#include <stdio.h>\n\nint main() {\n    // Write your solution here\n\n    return 0;\n}\n`;
  }
  if (language === "cpp") {
    return `#include <iostream>\nusing namespace std;\n\nint main() {\n    // Write your solution here\n\n    return 0;\n}\n`;
  }
  if (language === "java") {
    return `public class Main {\n    public static void main(String[] args) {\n        // Write your solution here\n\n    }\n}\n`;
  }
  if (language === "javascript") {
    return `// Write your solution here\n\n`;
  }

  // Python (check if problem requires a specific function signature for function_harness)
  if (problem && problem.evaluation_type === "function_harness") {
    const fnName =
      (problem.evaluation_config &&
        typeof problem.evaluation_config === "object" &&
        (problem.evaluation_config.function_name || problem.evaluation_config.function)) ||
      "solve";
    return `# Write your solution here\ndef ${fnName}(*args):\n    pass\n`;
  }

  return `# Write your solution here\n\n`;
}

/**
 * Resolve initial files & active file for a problem and language.
 */
export function getInitialFilesForProblem(problem, language) {
  if (
    problem &&
    problem.starter_files &&
    typeof problem.starter_files === "object" &&
    Object.keys(problem.starter_files).length > 0
  ) {
    const filesObj = { ...problem.starter_files };
    const firstKey =
      problem.entry_point && filesObj[problem.entry_point]
        ? problem.entry_point
        : Object.keys(filesObj)[0];
    return {
      files: filesObj,
      activeFileName: firstKey,
      code: filesObj[firstKey] || "",
    };
  }

  const fname = getDefaultFileNameForLang(language);
  const tpl = getCleanStarterTemplate(language, problem);
  return {
    files: { [fname]: tpl },
    activeFileName: fname,
    code: tpl,
  };
}

/**
 * Check if the student has written code that differs from the clean starter template.
 */
export function isCodeModifiedFromStarter(currentCode, currentFiles, language, problem = null) {
  const expected = getInitialFilesForProblem(problem, language);
  const norm = (s) => (s || "").replace(/\r\n/g, "\n").trim();

  const fileKeys = currentFiles ? Object.keys(currentFiles) : [];
  const expectedKeys = Object.keys(expected.files);
  if (fileKeys.length > 1 || fileKeys.length !== expectedKeys.length) {
    for (const k of fileKeys) {
      if (norm(currentFiles[k]) !== norm(expected.files[k] || "")) {
        return true;
      }
    }
  }

  const trimmedCurrent = norm(currentCode);
  if (!trimmedCurrent) return false;
  return trimmedCurrent !== norm(expected.code);
}

// =========================================================
// DRAFT PERSISTENCE (per user, context, problem, and language)
// =========================================================

const DRAFTS_STORAGE_KEY = "codeclan_code_drafts_v2";

function getDraftKey(userId, contextKey, problemId, language) {
  return `${userId || "anon"}:${contextKey || "practice"}:${problemId}:${language}`;
}

export function loadSavedDraft(userId, contextKey, problemId, language) {
  if (!problemId || !language) return null;
  try {
    const raw = localStorage.getItem(DRAFTS_STORAGE_KEY);
    if (!raw) return null;
    const all = JSON.parse(raw);
    const key = getDraftKey(userId, contextKey, problemId, language);
    const entry = all[key];
    if (!entry || !entry.files || typeof entry.files !== "object") return null;
    return entry;
  } catch {
    return null;
  }
}

export function saveCodeDraft(userId, contextKey, problemId, language, { files, activeFileName, code }) {
  if (!problemId || !language) return;
  try {
    const raw = localStorage.getItem(DRAFTS_STORAGE_KEY);
    const all = raw ? JSON.parse(raw) : {};
    const key = getDraftKey(userId, contextKey, problemId, language);
    all[key] = {
      files: { ...(files || {}), [activeFileName]: code },
      activeFileName,
      code,
      updatedAt: Date.now(),
    };
    localStorage.setItem(DRAFTS_STORAGE_KEY, JSON.stringify(all));
  } catch {
    // ignore storage quota errors
  }
}

export function clearSavedDraft(userId, contextKey, problemId, language) {
  if (!problemId || !language) return;
  try {
    const raw = localStorage.getItem(DRAFTS_STORAGE_KEY);
    if (!raw) return;
    const all = JSON.parse(raw);
    const key = getDraftKey(userId, contextKey, problemId, language);
    delete all[key];
    localStorage.setItem(DRAFTS_STORAGE_KEY, JSON.stringify(all));
  } catch {
    // ignore
  }
}
