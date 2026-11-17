"""Flexible Automated Grading Engine for CodeClan.

Supports 7 evaluation strategies:
- Type A (`exact`)              : Standard normalized stdout comparison
- Type B (`numeric_tolerance`)  : Floating-point token comparison with abs/rel tolerance
- Type C (`structured_json`)    : JSON / matrix / object comparison with recursive float tolerance
- Type D (`file_based`)         : Generated file inspection in `/work/output/` (CSV, JSON, PNG/JPG, TXT)
- Type E (`function_harness`)   : Direct Python module/function invocation on test argument tuples
- Type F (`ml_metrics`)         : ML evaluation (accuracy, precision, recall, f1, mae, rmse, r2)
- Type G (`custom_script`)      : Isolated teacher evaluator script in separate `codeclan-evl-*` container
"""

from __future__ import annotations

import base64
import csv
import io
import json
import math
import re
import struct
from dataclasses import dataclass, field
from typing import Any

from .comparison import compare_outputs, normalize_output
from .sandbox import SandboxExecutor


SUPPORTED_EVALUATION_TYPES: tuple[str, ...] = (
    "exact",
    "numeric_tolerance",
    "structured_json",
    "file_based",
    "function_harness",
    "ml_metrics",
    "custom_script",
)


@dataclass
class EvaluationOutcome:
    passed: bool
    status: str = "Passed"
    score_fraction: float = 0.0  # 0.0 .. 1.0 (supports partial credit for ML / custom scripts)
    metrics: dict[str, Any] = field(default_factory=dict)
    feedback: str = ""
    actual_summary: str = ""


def parse_evaluation_config(raw_config: str | dict | None) -> dict[str, Any]:
    if not raw_config:
        return {}
    if isinstance(raw_config, dict):
        return dict(raw_config)
    try:
        parsed = json.loads(raw_config)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Type A: Exact Output Matching
# ---------------------------------------------------------------------------
def evaluate_exact(actual_stdout: str, expected_output: str) -> EvaluationOutcome:
    passed = compare_outputs(actual_stdout, expected_output)
    return EvaluationOutcome(
        passed=passed,
        status="Passed" if passed else "Failed",
        score_fraction=1.0 if passed else 0.0,
        actual_summary=normalize_output(actual_stdout)[:500],
    )


# ---------------------------------------------------------------------------
# Type B: Numeric Tolerance Matching
# ---------------------------------------------------------------------------
_NUMBER_TOKEN_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _extract_tokens(text: str) -> list[str]:
    cleaned = normalize_output(text).replace(",", " ").replace(";", " ")
    return [tok for tok in cleaned.split() if tok]


def evaluate_numeric_tolerance(
    actual_stdout: str,
    expected_output: str,
    config: dict[str, Any],
) -> EvaluationOutcome:
    abs_tol = float(config.get("abs_tol", config.get("tolerance", 1e-5)))
    rel_tol = float(config.get("rel_tol", 1e-5))

    act_tokens = _extract_tokens(actual_stdout)
    exp_tokens = _extract_tokens(expected_output)

    if len(act_tokens) != len(exp_tokens):
        return EvaluationOutcome(
            passed=False,
            status="Failed",
            score_fraction=0.0,
            feedback=f"Token count mismatch: expected {len(exp_tokens)} value(s), got {len(act_tokens)}.",
            actual_summary=normalize_output(actual_stdout)[:500],
        )

    max_abs_err = 0.0
    for idx, (a_tok, e_tok) in enumerate(zip(act_tokens, exp_tokens)):
        try:
            e_val = float(e_tok)
            is_num = True
        except ValueError:
            is_num = False
            e_val = 0.0

        if is_num:
            try:
                a_val = float(a_tok)
            except ValueError:
                return EvaluationOutcome(
                    passed=False,
                    status="Failed",
                    score_fraction=0.0,
                    feedback=f"Token #{idx + 1} is not numeric: '{a_tok}'.",
                    actual_summary=normalize_output(actual_stdout)[:500],
                )
            if math.isnan(a_val) or math.isinf(a_val):
                return EvaluationOutcome(
                    passed=False,
                    status="Failed",
                    score_fraction=0.0,
                    feedback=f"Token #{idx + 1} is NaN or Inf.",
                    actual_summary=normalize_output(actual_stdout)[:500],
                )
            err = abs(a_val - e_val)
            max_abs_err = max(max_abs_err, err)
            if not math.isclose(a_val, e_val, rel_tol=rel_tol, abs_tol=abs_tol):
                return EvaluationOutcome(
                    passed=False,
                    status="Failed",
                    score_fraction=0.0,
                    metrics={"max_abs_error": round(max_abs_err, 8), "abs_tol": abs_tol},
                    feedback=f"Value #{idx + 1} out of tolerance (|actual - expected| = {err:.3e} > {abs_tol:.1e}).",
                    actual_summary=normalize_output(actual_stdout)[:500],
                )
        else:
            if a_tok != e_tok:
                return EvaluationOutcome(
                    passed=False,
                    status="Failed",
                    score_fraction=0.0,
                    feedback=f"Token #{idx + 1} mismatch.",
                    actual_summary=normalize_output(actual_stdout)[:500],
                )

    return EvaluationOutcome(
        passed=True,
        status="Passed",
        score_fraction=1.0,
        metrics={"max_abs_error": round(max_abs_err, 8), "abs_tol": abs_tol},
        feedback=f"All {len(exp_tokens)} numeric value(s) matched within tolerance {abs_tol:g}.",
        actual_summary=normalize_output(actual_stdout)[:500],
    )


# ---------------------------------------------------------------------------
# Type C: Structured JSON / Matrix Output Matching
# ---------------------------------------------------------------------------
def _compare_json_values(
    actual: Any,
    expected: Any,
    *,
    abs_tol: float,
    rel_tol: float,
    unordered_lists: bool,
    path: str = "$",
) -> tuple[bool, str]:
    if isinstance(expected, bool) or isinstance(actual, bool):
        if type(actual) is not type(expected) or actual != expected:
            return False, f"Boolean mismatch at {path}"
        return True, ""

    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        a_f = float(actual)
        e_f = float(expected)
        if math.isnan(a_f) or math.isinf(a_f):
            return False, f"NaN/Inf value at {path}"
        if not math.isclose(a_f, e_f, rel_tol=rel_tol, abs_tol=abs_tol):
            return False, f"Numeric mismatch at {path}: diff={abs(a_f - e_f):.3e} > tol={abs_tol:g}"
        return True, ""

    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False, f"Expected JSON object at {path}, got {type(actual).__name__}"
        missing = [k for k in expected.keys() if k not in actual]
        if missing:
            return False, f"Missing key(s) at {path}: {', '.join(str(k) for k in missing[:5])}"
        for k, exp_v in expected.items():
            ok, msg = _compare_json_values(
                actual[k],
                exp_v,
                abs_tol=abs_tol,
                rel_tol=rel_tol,
                unordered_lists=unordered_lists,
                path=f"{path}.{k}",
            )
            if not ok:
                return False, msg
        return True, ""

    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False, f"Expected JSON array at {path}, got {type(actual).__name__}"
        if len(actual) != len(expected):
            return False, f"Array length mismatch at {path}: expected {len(expected)}, got {len(actual)}"
        if unordered_lists and all(isinstance(x, (str, int, float, bool)) for x in expected):
            try:
                act_sorted = sorted(actual, key=lambda x: (str(type(x)), x))
                exp_sorted = sorted(expected, key=lambda x: (str(type(x)), x))
            except Exception:
                act_sorted, exp_sorted = actual, expected
        else:
            act_sorted, exp_sorted = actual, expected

        for idx, (a_item, e_item) in enumerate(zip(act_sorted, exp_sorted)):
            ok, msg = _compare_json_values(
                a_item,
                e_item,
                abs_tol=abs_tol,
                rel_tol=rel_tol,
                unordered_lists=unordered_lists,
                path=f"{path}[{idx}]",
            )
            if not ok:
                return False, msg
        return True, ""

    if actual != expected:
        return False, f"Value mismatch at {path}"
    return True, ""


def evaluate_structured_json(
    actual_stdout: str,
    expected_output: str,
    output_files: list[dict[str, Any]],
    config: dict[str, Any],
) -> EvaluationOutcome:
    abs_tol = float(config.get("abs_tol", config.get("tolerance", 1e-5)))
    rel_tol = float(config.get("rel_tol", 1e-5))
    unordered_lists = bool(config.get("unordered_lists", False))
    target_file = str(config.get("target_file", "")).strip()

    raw_actual = actual_stdout.strip()
    if target_file:
        matched_file = _find_output_file(output_files, target_file)
        if matched_file is None:
            return EvaluationOutcome(
                passed=False,
                status="Failed",
                score_fraction=0.0,
                feedback=f"Required output file '{target_file}' was not generated in /work/output/.",
            )
        raw_actual = _decode_output_file_text(matched_file)

    try:
        actual_obj = json.loads(raw_actual)
    except Exception as exc:
        return EvaluationOutcome(
            passed=False,
            status="Failed",
            score_fraction=0.0,
            feedback=f"Output is not valid JSON: {exc}",
            actual_summary=raw_actual[:500],
        )

    try:
        expected_obj = json.loads(expected_output)
    except Exception as exc:
        return EvaluationOutcome(
            passed=False,
            status="Failed",
            score_fraction=0.0,
            feedback=f"Expected specification is not valid JSON: {exc}",
        )

    ok, msg = _compare_json_values(
        actual_obj,
        expected_obj,
        abs_tol=abs_tol,
        rel_tol=rel_tol,
        unordered_lists=unordered_lists,
    )
    return EvaluationOutcome(
        passed=ok,
        status="Passed" if ok else "Failed",
        score_fraction=1.0 if ok else 0.0,
        feedback="Structured JSON output matched." if ok else msg,
        actual_summary=json.dumps(actual_obj)[:500],
    )


# ---------------------------------------------------------------------------
# Type D: File-Based Evaluation (/work/output/*)
# ---------------------------------------------------------------------------
def _find_output_file(output_files: list[dict[str, Any]], target_name: str) -> dict[str, Any] | None:
    norm_target = target_name.strip().lstrip("/").removeprefix("work/output/").removeprefix("output/")
    for f in output_files or []:
        name = str(f.get("name", "")).strip().lstrip("/")
        if name == norm_target or name.endswith("/" + norm_target):
            return f
    return None


def _decode_output_file_bytes(file_entry: dict[str, Any]) -> bytes:
    b64 = file_entry.get("content_b64") or ""
    if not b64:
        return b""
    try:
        return base64.b64decode(b64)
    except Exception:
        return b""


def _decode_output_file_text(file_entry: dict[str, Any]) -> str:
    return _decode_output_file_bytes(file_entry).decode("utf-8", errors="replace")


def _inspect_png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        width, height = struct.unpack(">II", data[16:24])
        return int(width), int(height)
    return None


def evaluate_file_based(
    actual_stdout: str,
    expected_output: str,
    output_files: list[dict[str, Any]],
    config: dict[str, Any],
) -> EvaluationOutcome:
    target_file = str(config.get("target_file") or config.get("filename") or "output.txt").strip()
    file_format = str(config.get("format") or "").strip().lower()
    if not file_format:
        if target_file.endswith(".csv"):
            file_format = "csv"
        elif target_file.endswith(".json"):
            file_format = "json"
        elif target_file.endswith(".png"):
            file_format = "png"
        else:
            file_format = "text"

    entry = _find_output_file(output_files, target_file)
    if entry is None:
        generated = [str(f.get("name")) for f in (output_files or [])]
        return EvaluationOutcome(
            passed=False,
            status="Failed",
            score_fraction=0.0,
            feedback=(
                f"Expected file '/work/output/{target_file}' was not generated. "
                f"Generated files: {generated or 'none'}."
            ),
            actual_summary=normalize_output(actual_stdout)[:300],
        )

    raw_bytes = _decode_output_file_bytes(entry)
    size_bytes = int(entry.get("size_bytes", len(raw_bytes)))

    if file_format == "png":
        dims = _inspect_png_dimensions(raw_bytes)
        if dims is None:
            return EvaluationOutcome(
                passed=False,
                status="Failed",
                score_fraction=0.0,
                feedback=f"File '{target_file}' is not a valid PNG image.",
            )
        w, h = dims
        min_w = int(config.get("min_width", 50))
        min_h = int(config.get("min_height", 50))
        if w < min_w or h < min_h:
            return EvaluationOutcome(
                passed=False,
                status="Failed",
                score_fraction=0.0,
                metrics={"width": w, "height": h, "size_bytes": size_bytes},
                feedback=f"PNG dimensions {w}x{h} are smaller than required {min_w}x{min_h}.",
            )
        # If expected_output has stdout check too, optionally verify it
        if expected_output.strip() and config.get("check_stdout", False):
            if not compare_outputs(actual_stdout, expected_output):
                return EvaluationOutcome(
                    passed=False,
                    status="Failed",
                    score_fraction=0.5,
                    metrics={"width": w, "height": h, "size_bytes": size_bytes},
                    feedback=f"PNG '{target_file}' ({w}x{h}) valid, but stdout summary did not match.",
                    actual_summary=normalize_output(actual_stdout)[:300],
                )
        return EvaluationOutcome(
            passed=True,
            status="Passed",
            score_fraction=1.0,
            metrics={"filename": target_file, "width": w, "height": h, "size_bytes": size_bytes},
            feedback=f"Verified generated PNG '{target_file}' ({w}x{h} px, {size_bytes} bytes).",
            actual_summary=f"PNG {w}x{h} ({size_bytes} B)",
        )

    if file_format == "json":
        return evaluate_structured_json(
            actual_stdout,
            expected_output,
            output_files,
            {**config, "target_file": target_file},
        )

    text_content = _decode_output_file_text(entry)
    if file_format == "csv":
        abs_tol = float(config.get("abs_tol", config.get("tolerance", 1e-4)))
        act_rows = [
            [cell.strip() for cell in row]
            for row in csv.reader(io.StringIO(normalize_output(text_content)))
            if any(cell.strip() for cell in row)
        ]
        exp_rows = [
            [cell.strip() for cell in row]
            for row in csv.reader(io.StringIO(normalize_output(expected_output)))
            if any(cell.strip() for cell in row)
        ]
        if not exp_rows:
            min_rows = int(config.get("min_rows", 1))
            passed = len(act_rows) >= min_rows
            return EvaluationOutcome(
                passed=passed,
                status="Passed" if passed else "Failed",
                score_fraction=1.0 if passed else 0.0,
                metrics={"rows": len(act_rows), "size_bytes": size_bytes},
                feedback=f"CSV '{target_file}' has {len(act_rows)} row(s).",
                actual_summary=text_content[:400],
            )
        if len(act_rows) != len(exp_rows):
            return EvaluationOutcome(
                passed=False,
                status="Failed",
                score_fraction=0.0,
                metrics={"actual_rows": len(act_rows), "expected_rows": len(exp_rows)},
                feedback=f"CSV row count mismatch in '{target_file}': expected {len(exp_rows)}, got {len(act_rows)}.",
                actual_summary=text_content[:400],
            )
        for r_idx, (a_row, e_row) in enumerate(zip(act_rows, exp_rows)):
            if len(a_row) != len(e_row):
                return EvaluationOutcome(
                    passed=False,
                    status="Failed",
                    score_fraction=0.0,
                    feedback=f"CSV column count mismatch on row {r_idx + 1}: expected {len(e_row)}, got {len(a_row)}.",
                    actual_summary=text_content[:400],
                )
            for c_idx, (a_cell, e_cell) in enumerate(zip(a_row, e_row)):
                try:
                    e_num = float(e_cell)
                    a_num = float(a_cell)
                    if not math.isclose(a_num, e_num, abs_tol=abs_tol, rel_tol=1e-5):
                        return EvaluationOutcome(
                            passed=False,
                            status="Failed",
                            score_fraction=0.0,
                            feedback=f"CSV cell ({r_idx + 1}, {c_idx + 1}) out of tolerance.",
                            actual_summary=text_content[:400],
                        )
                except ValueError:
                    if a_cell != e_cell:
                        return EvaluationOutcome(
                            passed=False,
                            status="Failed",
                            score_fraction=0.0,
                            feedback=f"CSV cell ({r_idx + 1}, {c_idx + 1}) mismatch.",
                            actual_summary=text_content[:400],
                        )
        return EvaluationOutcome(
            passed=True,
            status="Passed",
            score_fraction=1.0,
            metrics={"filename": target_file, "rows": len(act_rows), "size_bytes": size_bytes},
            feedback=f"CSV '{target_file}' ({len(act_rows)} rows) matched expected table.",
            actual_summary=text_content[:400],
        )

    # Default text file comparison (with optional numeric tolerance)
    if config.get("numeric_tolerance"):
        return evaluate_numeric_tolerance(text_content, expected_output, config)
    passed = compare_outputs(text_content, expected_output)
    return EvaluationOutcome(
        passed=passed,
        status="Passed" if passed else "Failed",
        score_fraction=1.0 if passed else 0.0,
        metrics={"filename": target_file, "size_bytes": size_bytes},
        feedback=f"File '{target_file}' matched expected content." if passed else f"File '{target_file}' content mismatch.",
        actual_summary=normalize_output(text_content)[:400],
    )


# ---------------------------------------------------------------------------
# Type F: Machine Learning Evaluation Metrics
# ---------------------------------------------------------------------------
def _parse_prediction_vector(raw_text: str, column: str | None = None) -> list[Any]:
    text = raw_text.strip()
    if not text:
        return []
    # 1. Try JSON list or {"predictions": [...]}
    if text.startswith("[") or text.startswith("{"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                for key in (column, "predictions", "y_pred", "y_true", "labels", "target", "output"):
                    if key and key in parsed and isinstance(parsed[key], list):
                        return parsed[key]
        except Exception:
            pass

    # 2. Try CSV with header or multi-column rows
    lines = [ln.strip() for ln in normalize_output(text).split("\n") if ln.strip()]
    if not lines:
        return []

    if "," in lines[0]:
        reader = list(csv.reader(io.StringIO("\n".join(lines))))
        if not reader:
            return []
        header = [h.strip() for h in reader[0]]
        col_idx = -1
        if column and column in header:
            col_idx = header.index(column)
            data_rows = reader[1:]
        else:
            # Check if first row is non-numeric header
            first_last = header[-1]
            try:
                float(first_last)
                data_rows = reader
            except ValueError:
                if first_last.lower() in {"prediction", "predictions", "label", "target", "y_pred", "y_true", "class", "value"}:
                    data_rows = reader[1:]
                else:
                    data_rows = reader
            col_idx = -1
        values: list[Any] = []
        for row in data_rows:
            if not row:
                continue
            cell = row[col_idx].strip() if len(row) > abs(col_idx) else row[-1].strip()
            values.append(cell)
        return values

    # 3. Whitespace/newline separated tokens (or single-column CSV with header)
    tokens = [tok.strip() for ln in lines for tok in ln.split() if tok.strip()]
    if len(tokens) > 1:
        first_tok = tokens[0].lower()
        header_names = {"prediction", "predictions", "label", "labels", "target", "y_pred", "y_true", "class", "value"}
        if column:
            header_names.add(str(column).strip().lower())
        if first_tok in header_names:
            tokens = tokens[1:]
    return tokens


def _compute_classification_metrics(y_true: list[Any], y_pred: list[Any]) -> dict[str, float]:
    n = len(y_true)
    if n == 0:
        return {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0}

    norm_true = [str(v).strip() for v in y_true]
    norm_pred = [str(v).strip() for v in y_pred]
    # Normalize float-like integer labels ("1.0" -> "1")
    for lst in (norm_true, norm_pred):
        for i, val in enumerate(lst):
            try:
                fval = float(val)
                if fval.is_integer():
                    lst[i] = str(int(fval))
            except ValueError:
                pass

    correct = sum(1 for t, p in zip(norm_true, norm_pred) if t == p)
    accuracy = correct / n

    labels = sorted(set(norm_true) | set(norm_pred))
    precisions: list[float] = []
    recalls: list[float] = []
    f1s: list[float] = []

    # Macro-averaged precision, recall, F1 (or binary positive class "1" if binary {"0","1"} configured)
    for lbl in labels:
        tp = sum(1 for t, p in zip(norm_true, norm_pred) if t == lbl and p == lbl)
        fp = sum(1 for t, p in zip(norm_true, norm_pred) if t != lbl and p == lbl)
        fn = sum(1 for t, p in zip(norm_true, norm_pred) if t == lbl and p != lbl)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
        precisions.append(prec)
        recalls.append(rec)
        f1s.append(f1)

    k = len(labels) or 1
    return {
        "accuracy": round(accuracy, 6),
        "precision": round(sum(precisions) / k, 6),
        "recall": round(sum(recalls) / k, 6),
        "f1": round(sum(f1s) / k, 6),
        "samples": n,
    }


def _compute_regression_metrics(y_true: list[Any], y_pred: list[Any]) -> dict[str, float]:
    n = len(y_true)
    if n == 0:
        return {"mae": float("inf"), "rmse": float("inf"), "r2": 0.0}
    t_floats = [float(v) for v in y_true]
    p_floats = [float(v) for v in y_pred]
    abs_errs = [abs(t - p) for t, p in zip(t_floats, p_floats)]
    sq_errs = [(t - p) ** 2 for t, p in zip(t_floats, p_floats)]
    mae = sum(abs_errs) / n
    rmse = math.sqrt(sum(sq_errs) / n)
    mean_t = sum(t_floats) / n
    ss_tot = sum((t - mean_t) ** 2 for t in t_floats)
    ss_res = sum(sq_errs)
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 1e-12 else (1.0 if ss_res < 1e-12 else 0.0)
    return {
        "mae": round(mae, 6),
        "rmse": round(rmse, 6),
        "r2": round(r2, 6),
        "samples": n,
    }


def evaluate_ml_metrics(
    actual_stdout: str,
    expected_output: str,
    output_files: list[dict[str, Any]],
    config: dict[str, Any],
) -> EvaluationOutcome:
    metric_name = str(config.get("metric", "f1")).strip().lower()
    target_file = str(config.get("target_file", "")).strip()
    pred_col = config.get("prediction_column")

    raw_pred_source = actual_stdout
    if target_file:
        f_entry = _find_output_file(output_files, target_file)
        if f_entry is not None:
            raw_pred_source = _decode_output_file_text(f_entry)
        elif not raw_pred_source.strip():
            return EvaluationOutcome(
                passed=False,
                status="Failed",
                score_fraction=0.0,
                feedback=f"Required prediction file '/work/output/{target_file}' was not found.",
            )
    else:
        # Auto-detect /work/output/predictions.csv or predictions.json if stdout has no predictions
        for candidate in ("predictions.csv", "predictions.json", "submission.csv"):
            f_entry = _find_output_file(output_files, candidate)
            if f_entry is not None:
                raw_pred_source = _decode_output_file_text(f_entry)
                break

    y_pred = _parse_prediction_vector(raw_pred_source, column=pred_col)
    y_true = _parse_prediction_vector(expected_output, column=config.get("target_column"))

    if not y_true:
        return EvaluationOutcome(
            passed=False,
            status="Failed",
            score_fraction=0.0,
            feedback="Ground-truth target vector is empty.",
        )
    if len(y_pred) != len(y_true):
        return EvaluationOutcome(
            passed=False,
            status="Failed",
            score_fraction=0.0,
            metrics={"predicted_count": len(y_pred), "expected_count": len(y_true)},
            feedback=f"Prediction length mismatch: expected {len(y_true)} predictions, got {len(y_pred)}.",
            actual_summary=f"{len(y_pred)} predictions",
        )

    is_regression = metric_name in {"mae", "rmse", "mse", "r2"}
    try:
        if is_regression:
            metrics = _compute_regression_metrics(y_true, y_pred)
        else:
            metrics = _compute_classification_metrics(y_true, y_pred)
    except Exception as exc:
        return EvaluationOutcome(
            passed=False,
            status="Failed",
            score_fraction=0.0,
            feedback=f"Failed to parse numeric predictions: {exc}",
        )

    val = float(metrics.get(metric_name, 0.0))
    lower_is_better = metric_name in {"mae", "rmse", "mse"}
    threshold = float(config.get("threshold", 0.5 if lower_is_better else 0.8))

    if lower_is_better:
        passed = val <= threshold
        # Partial credit up to 2x threshold
        if passed:
            score_fraction = 1.0
        elif val <= threshold * 2.0 and threshold > 0:
            score_fraction = max(0.0, round(1.0 - ((val - threshold) / threshold), 4))
        else:
            score_fraction = 0.0
        comp_str = f"{metric_name.upper()} = {val:.4f} (required <= {threshold:.4f})"
    else:
        passed = val >= threshold
        min_baseline = float(config.get("baseline", 0.5))
        if passed:
            score_fraction = 1.0
        elif val > min_baseline and threshold > min_baseline:
            score_fraction = max(0.0, round((val - min_baseline) / (threshold - min_baseline) * 0.8, 4))
        else:
            score_fraction = 0.0
        comp_str = f"{metric_name.upper()} = {val:.4f} (required >= {threshold:.4f})"

    metrics["primary_metric"] = metric_name
    metrics["primary_value"] = val
    metrics["threshold"] = threshold
    metrics["passed_threshold"] = passed

    return EvaluationOutcome(
        passed=passed,
        status="Passed" if passed else "Failed",
        score_fraction=score_fraction,
        metrics=metrics,
        feedback=comp_str,
        actual_summary=comp_str,
    )


# ---------------------------------------------------------------------------
# Type G: Custom Teacher Evaluation Script (Separate Isolated Container)
# ---------------------------------------------------------------------------
def evaluate_custom_script(
    executor: SandboxExecutor,
    *,
    evaluator_script: str,
    student_stdout: str,
    expected_output: str,
    output_files: list[dict[str, Any]],
    datasets_b64: str | None,
    image: str,
) -> EvaluationOutcome:
    submission_files: list[dict[str, Any]] = list(output_files or [])
    submission_files.append(
        {
            "name": "stdout.txt",
            "content_b64": base64.b64encode((student_stdout or "").encode("utf-8")).decode("ascii"),
        }
    )
    submission_files.append(
        {
            "name": "expected.txt",
            "content_b64": base64.b64encode((expected_output or "").encode("utf-8")).decode("ascii"),
        }
    )

    res = executor.run_evaluator(
        evaluator_code=evaluator_script,
        submission_files=submission_files,
        hidden_b64=datasets_b64,
        image=image,
        timeout=15.0,
        memory_mb=512,
        cpus=1.0,
    )
    if res.timed_out:
        return EvaluationOutcome(
            passed=False,
            status="Evaluation Timeout",
            score_fraction=0.0,
            feedback="Custom teacher evaluation script timed out.",
        )

    ev = res.evaluation or {}
    if not ev and res.stdout.strip():
        try:
            ev = json.loads(res.stdout.strip().splitlines()[-1])
        except Exception:
            ev = {}

    if not isinstance(ev, dict) or not ev:
        return EvaluationOutcome(
            passed=False,
            status="Evaluation Error",
            score_fraction=0.0,
            feedback=f"Custom evaluator did not emit a valid JSON result. Stderr: {(res.stderr or '')[:250]}",
        )

    passed = bool(ev.get("passed", False))
    score_fraction = float(ev.get("score_fraction", 1.0 if passed else 0.0))
    score_fraction = max(0.0, min(1.0, score_fraction))
    metrics = ev.get("metrics") if isinstance(ev.get("metrics"), dict) else {}
    feedback = str(ev.get("feedback", "Evaluated by teacher script."))
    return EvaluationOutcome(
        passed=passed,
        status="Passed" if passed else "Failed",
        score_fraction=score_fraction,
        metrics=metrics,
        feedback=feedback,
        actual_summary=feedback[:300],
    )
