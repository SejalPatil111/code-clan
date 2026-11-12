"""
Output normalization, comparison policy, and supported language definitions.

Output Comparison Policy:
  1. Line endings are normalized (`\\r\\n` and `\\r` -> `\\n`).
  2. Trailing horizontal whitespace (spaces and tabs) on each line is stripped.
  3. Trailing empty lines at the end of the output are removed.
  4. Leading whitespace, internal whitespace, case, and line order are strictly preserved.
"""

from typing import Optional

# Supported submission statuses / verdicts
STATUS_PENDING = "Pending Evaluation"
STATUS_RUNNING = "Running"
STATUS_ACCEPTED = "Accepted"
STATUS_WRONG_ANSWER = "Wrong Answer"
STATUS_TLE = "Time Limit Exceeded"
STATUS_RUNTIME_ERROR = "Runtime Error"
STATUS_COMPILATION_ERROR = "Compilation Error"
STATUS_INTERNAL_ERROR = "Internal Evaluation Error"

TERMINAL_STATUSES = (
    STATUS_ACCEPTED,
    STATUS_WRONG_ANSWER,
    STATUS_TLE,
    STATUS_RUNTIME_ERROR,
    STATUS_COMPILATION_ERROR,
    STATUS_INTERNAL_ERROR,
)

PENDING_STATUSES = (STATUS_PENDING, STATUS_RUNNING)

LANGUAGE_ALIASES = {
    "python": "python",
    "python3": "python",
    "py": "python",
    "c": "c",
    "gcc": "c",
    "cpp": "cpp",
    "c++": "cpp",
    "g++": "cpp",
    "java": "java",
    "java17": "java",
    "javascript": "javascript",
    "js": "javascript",
    "node": "javascript",
    "nodejs": "javascript",
}

SUPPORTED_LANGUAGES = ("python", "c", "cpp", "java", "javascript")

MAX_SOURCE_CODE_BYTES = 64 * 1024  # 64 KB max source code size


def normalize_language(language: Optional[str]) -> Optional[str]:
    if not language:
        return None
    return LANGUAGE_ALIASES.get(language.strip().lower())


def normalize_output(text: Optional[str]) -> str:
    """
    Normalize program or testcase output according to the CodeClan comparison policy:
      - Unify CRLF / CR line endings to LF.
      - Strip trailing spaces/tabs per line.
      - Strip trailing blank lines at the end of the output.
      - Preserve leading whitespace, internal spaces, and character case.
    """
    if text is None:
        return ""
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in unified.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def compare_outputs(actual: Optional[str], expected: Optional[str]) -> bool:
    """Return True if normalized actual output matches normalized expected output."""
    return normalize_output(actual) == normalize_output(expected)
