"""
CodeClan Grader Worker & Universal Execution Queue Processor.

Responsibilities:
  - Atomically claim pending submissions using `SELECT ... FOR UPDATE SKIP LOCKED`.
  - Recover submissions left in `Running` state if a worker crashes or restarts.
  - Compile and evaluate student programs (single-file or multi-file projects) across
    all 8 preconfigured execution environments (`cp`, `datascience`, `ml`, `cv`, `nlp`,
    `dl-torch`, `dl-tf`, `scientific`) and all 7 evaluation modes (`exact`,
    `numeric_tolerance`, `structured_json`, `file_based`, `function_harness`,
    `ml_metrics`, `custom_script`) inside isolated ephemeral Docker containers.
  - Mount public/hidden datasets read-only at `/work/data` without leaking hidden
    datasets or hidden testcase values to students.
  - Persist per-testcase `SubmissionResult` rows and update `Submission` verdict, score,
    execution time, peak memory (`max_rss_kb`), evaluation metrics, and coding-test /
    assignment aggregates.
  - Serve internal-only HTTP endpoints (`/internal/run-samples`, `/internal/runtime-status`,
    and `/health`) on the Docker network.
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import logging
import os
import posixpath
import signal
import tarfile
import threading
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine, wait_for_db
from app.grading.comparison import (
    STATUS_ACCEPTED,
    STATUS_COMPILATION_ERROR,
    STATUS_INTERNAL_ERROR,
    STATUS_MEMORY_LIMIT,
    STATUS_OUTPUT_LIMIT,
    STATUS_PENDING,
    STATUS_RUNTIME_ERROR,
    STATUS_RUNNING,
    STATUS_TIME_LIMIT,
    STATUS_WRONG_ANSWER,
    TERMINAL_STATUSES,
    normalize_language,
)
from app.grading.environments import (
    Environment,
    effective_profile,
    get_environment,
)
from app.grading.evaluators import (
    EvaluationOutcome,
    evaluate_custom_script,
    evaluate_exact,
    evaluate_file_based,
    evaluate_ml_metrics,
    evaluate_numeric_tolerance,
    evaluate_structured_json,
    parse_evaluation_config,
)
from app.grading.sandbox import SandboxExecutor, list_active_sandbox_containers
from app.models import (
    AssignmentProblem,
    AssignmentStudent,
    CodingTestProblem,
    CodingTestStudent,
    Problem,
    ProblemDataset,
    Submission,
    SubmissionResult,
    TestCase,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("codeclan.grader")

POLL_INTERVAL_SECONDS = float(os.getenv("GRADER_POLL_INTERVAL", "1.0"))
STALE_RUNNING_SECONDS = int(os.getenv("GRADER_STALE_RUNNING_SECONDS", "120"))
MAX_GRADING_ATTEMPTS = int(os.getenv("GRADER_MAX_ATTEMPTS", "3"))
DEFAULT_PROBLEM_MAX_SCORE = float(os.getenv("DEFAULT_PROBLEM_MAX_SCORE", "10.0"))
INTERNAL_PORT = int(os.getenv("GRADER_INTERNAL_PORT", "8090"))
INTERNAL_TOKEN = os.getenv("SECRET_KEY", "code-clan-dev-secret-change-me")

_last_heartbeat: float = time.time()
_stop_event = threading.Event()
_global_executor: Optional[SandboxExecutor] = None

_telemetry_lock = threading.Lock()
_worker_telemetry: Dict[str, Any] = {
    "started_at": datetime.utcnow().isoformat() + "Z",
    "submissions_processed": 0,
    "sample_runs_processed": 0,
    "by_environment": {},
    "by_evaluation_type": {},
    "recent_latencies_ms": [],
}


def _record_telemetry(
    *,
    env_id: str,
    eval_type: str,
    elapsed_ms: float,
    is_sample: bool = False,
) -> None:
    with _telemetry_lock:
        if is_sample:
            _worker_telemetry["sample_runs_processed"] += 1
        else:
            _worker_telemetry["submissions_processed"] += 1
        by_env = _worker_telemetry["by_environment"]
        by_env[env_id] = by_env.get(env_id, 0) + 1
        by_eval = _worker_telemetry["by_evaluation_type"]
        by_eval[eval_type] = by_eval.get(eval_type, 0) + 1
        lat = _worker_telemetry["recent_latencies_ms"]
        lat.append(round(elapsed_ms, 2))
        if len(lat) > 100:
            del lat[:-100]


def get_worker_telemetry() -> Dict[str, Any]:
    with _telemetry_lock:
        lat = list(_worker_telemetry["recent_latencies_ms"])
        avg_ms = round(sum(lat) / len(lat), 2) if lat else 0.0
        return {
            "started_at": _worker_telemetry["started_at"],
            "submissions_processed": _worker_telemetry["submissions_processed"],
            "sample_runs_processed": _worker_telemetry["sample_runs_processed"],
            "by_environment": dict(_worker_telemetry["by_environment"]),
            "by_evaluation_type": dict(_worker_telemetry["by_evaluation_type"]),
            "avg_execution_latency_ms": avg_ms,
        }


def _get_executor() -> SandboxExecutor:
    global _global_executor
    if _global_executor is None:
        _global_executor = SandboxExecutor()
    return _global_executor


DEFAULT_ENTRY_FILE = {
    "python": "main.py",
    "c": "main.c",
    "cpp": "main.cpp",
    "java": "Main.java",
    "javascript": "main.js",
}


def _sanitize_relpath(path: str) -> Optional[str]:
    clean = (path or "").replace("\\", "/").strip().lstrip("/")
    if not clean:
        return None
    norm = posixpath.normpath(clean)
    if norm.startswith("..") or "/.." in norm or norm.startswith("/"):
        return None
    return norm


def _normalize_submission_files(
    code: str,
    raw_files: str | dict | None,
    norm_lang: str,
) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    if raw_files:
        if isinstance(raw_files, str):
            try:
                loaded = json.loads(raw_files)
                if isinstance(loaded, dict):
                    raw_files = loaded
                else:
                    raw_files = None
            except Exception:
                raw_files = None
        if isinstance(raw_files, dict):
            for k, v in raw_files.items():
                rel = _sanitize_relpath(str(k))
                if rel and isinstance(v, str):
                    parsed[rel] = v
                if len(parsed) >= 25:
                    break
    if not parsed:
        default_name = DEFAULT_ENTRY_FILE.get(norm_lang, "main.py")
        parsed[default_name] = code or ""
    return parsed


def _package_datasets_tar_b64(datasets: List[Any]) -> Optional[str]:
    """Package ProblemDataset rows or dicts into a base64 .tar.gz archive for /work/data."""
    if not datasets:
        return None
    buf = io.BytesIO()
    count = 0
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for ds in datasets:
            if isinstance(ds, dict):
                fname = _sanitize_relpath(str(ds.get("filename", "")))
                b64 = ds.get("content_b64") or ""
            else:
                fname = _sanitize_relpath(str(getattr(ds, "filename", "")))
                b64 = getattr(ds, "content_b64", "") or ""
            if not fname or not b64:
                continue
            try:
                raw = base64.b64decode(b64)
            except Exception:
                continue
            info = tarfile.TarInfo(name=fname)
            info.size = len(raw)
            info.mode = 0o444
            tf.addfile(info, io.BytesIO(raw))
            count += 1
    if count == 0:
        return None
    return base64.b64encode(buf.getvalue()).decode("ascii")


def get_submission_max_score(sub: Submission, db: Session, problem: Optional[Problem] = None) -> float:
    """Determine the maximum possible score for a submission in its context."""
    if sub.submission_type == "assignment" and sub.assignment_id:
        ap = (
            db.query(AssignmentProblem)
            .filter(
                AssignmentProblem.assignment_id == sub.assignment_id,
                AssignmentProblem.problem_id == sub.problem_id,
            )
            .first()
        )
        if ap and ap.marks and ap.marks > 0:
            return float(ap.marks)
    elif sub.submission_type == "coding_test" and sub.coding_test_id:
        ctp = (
            db.query(CodingTestProblem)
            .filter(
                CodingTestProblem.coding_test_id == sub.coding_test_id,
                CodingTestProblem.problem_id == sub.problem_id,
            )
            .first()
        )
        if ctp and ctp.marks and ctp.marks > 0:
            return float(ctp.marks)
    if problem and getattr(problem, "max_score", None) and float(problem.max_score) > 0:
        return float(problem.max_score)
    return DEFAULT_PROBLEM_MAX_SCORE


def recompute_coding_test_student_score(coding_test_id: int, student_id: int, db: Session) -> float:
    """
    Recompute a student's coding test score from their best evaluated submission
    for each problem in the coding test. Never awards points for unevaluated or
    0-score submissions.
    """
    test_probs = (
        db.query(CodingTestProblem)
        .filter(CodingTestProblem.coding_test_id == coding_test_id)
        .all()
    )
    allowed_problem_ids = {tp.problem_id for tp in test_probs}

    eval_subs = (
        db.query(Submission)
        .filter(
            Submission.coding_test_id == coding_test_id,
            Submission.user_id == student_id,
            Submission.submission_type == "coding_test",
            Submission.status.in_(TERMINAL_STATUSES),
        )
        .all()
    )

    best_by_problem: dict[int, float] = {}
    for s in eval_subs:
        if allowed_problem_ids and s.problem_id not in allowed_problem_ids:
            continue
        val = float(s.score or 0.0)
        if val > best_by_problem.get(s.problem_id, 0.0):
            best_by_problem[s.problem_id] = val

    total_score = round(sum(best_by_problem.values()), 2)

    record = (
        db.query(CodingTestStudent)
        .filter(
            CodingTestStudent.coding_test_id == coding_test_id,
            CodingTestStudent.student_id == student_id,
        )
        .first()
    )
    if record:
        record.score = total_score
    else:
        record = CodingTestStudent(
            coding_test_id=coding_test_id,
            student_id=student_id,
            started_at=datetime.utcnow(),
            score=total_score,
            status="in_progress",
        )
        db.add(record)

    return total_score


def update_assignment_student_status(assignment_id: int, student_id: int, db: Session) -> None:
    """Update AssignmentStudent status based on evaluated assignment submissions."""
    record = (
        db.query(AssignmentStudent)
        .filter(
            AssignmentStudent.assignment_id == assignment_id,
            AssignmentStudent.student_id == student_id,
        )
        .first()
    )
    if not record:
        return

    probs = (
        db.query(AssignmentProblem)
        .filter(AssignmentProblem.assignment_id == assignment_id)
        .all()
    )
    if not probs:
        return

    prob_ids = {p.problem_id for p in probs}
    accepted_ids = {
        row[0]
        for row in db.query(func.distinct(Submission.problem_id))
        .filter(
            Submission.assignment_id == assignment_id,
            Submission.user_id == student_id,
            Submission.status == STATUS_ACCEPTED,
        )
        .all()
    }
    if prob_ids.issubset(accepted_ids):
        record.status = "completed"
    else:
        record.status = "in_progress"


def recover_stale_submissions(db: Session) -> int:
    """
    Find submissions stuck in `Running` for longer than `STALE_RUNNING_SECONDS`
    (e.g. after a worker crash) and either re-queue them or mark them failed if
    they exceeded `MAX_GRADING_ATTEMPTS`.
    """
    cutoff = datetime.utcnow() - timedelta(seconds=STALE_RUNNING_SECONDS)
    stale = (
        db.query(Submission)
        .filter(
            Submission.status == STATUS_RUNNING,
            (Submission.started_at == None) | (Submission.started_at < cutoff),  # noqa: E711
        )
        .with_for_update(skip_locked=True)
        .all()
    )
    if not stale:
        return 0

    for sub in stale:
        attempts = sub.attempt_count or 0
        if attempts < MAX_GRADING_ATTEMPTS:
            logger.warning(
                "Recovering stale submission #%s (attempt %s/%s) -> Pending Evaluation",
                sub.id,
                attempts,
                MAX_GRADING_ATTEMPTS,
            )
            sub.status = STATUS_PENDING
            sub.error_message = "Recovered after worker interruption; re-queued for evaluation."
        else:
            logger.error(
                "Submission #%s exceeded max grading attempts (%s) -> Internal Evaluation Error",
                sub.id,
                attempts,
            )
            sub.status = STATUS_INTERNAL_ERROR
            sub.evaluated_at = datetime.utcnow()
            sub.error_message = "Evaluation exceeded maximum retry attempts."

    db.commit()
    return len(stale)


def claim_next_submission(db: Session) -> Optional[int]:
    """
    Atomically claim the oldest `Pending Evaluation` submission using
    `SELECT ... FOR UPDATE SKIP LOCKED`.
    """
    sub = (
        db.query(Submission)
        .filter(Submission.status == STATUS_PENDING)
        .order_by(Submission.submitted_at.asc(), Submission.id.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if not sub:
        return None

    sub.status = STATUS_RUNNING
    sub.started_at = datetime.utcnow()
    sub.attempt_count = (sub.attempt_count or 0) + 1
    sub_id = sub.id
    db.commit()
    return sub_id


def _evaluate_project_testcase(
    *,
    executor: SandboxExecutor,
    env: Environment,
    prof: Dict[str, Any],
    norm_lang: str,
    files_dict: Dict[str, str],
    entry_point: Optional[str],
    datasets_b64: Optional[str],
    tc_input: str,
    tc_expected: str,
    eval_type: str,
    eval_config: Dict[str, Any],
) -> Dict[str, Any]:
    """Run a single test case through `executor.run_project` and evaluate with `evaluators.py`."""
    harness_spec: Optional[Dict[str, Any]] = None
    stdin_payload = tc_input or ""

    if eval_type == "function_harness" and norm_lang == "python":
        fn_name = str(eval_config.get("function_name") or eval_config.get("function") or "solve").strip()
        mod_name = str(eval_config.get("module") or (entry_point or "main.py").removesuffix(".py")).strip()
        # Parse test case input as JSON args/kwargs or single value
        call_args: list[Any] = []
        call_kwargs: dict[str, Any] = {}
        raw_in = (tc_input or "").strip()
        if raw_in:
            try:
                parsed_in = json.loads(raw_in)
                if isinstance(parsed_in, dict) and ("args" in parsed_in or "kwargs" in parsed_in):
                    call_args = list(parsed_in.get("args", []))
                    call_kwargs = dict(parsed_in.get("kwargs", {}))
                elif isinstance(parsed_in, list):
                    call_args = parsed_in
                else:
                    call_args = [parsed_in]
            except Exception:
                call_args = [raw_in]
        harness_spec = {
            "module": mod_name,
            "function": fn_name,
            "calls": [{"args": call_args, "kwargs": call_kwargs}],
        }
        stdin_payload = ""

    proj_res = executor.run_project(
        language=norm_lang,
        files=files_dict,
        entry_point=entry_point,
        stdin_data=stdin_payload,
        datasets_b64=datasets_b64,
        harness=harness_spec,
        image=env.image,
        run_timeout=float(prof["wall_timeout_sec"]),
        compile_timeout=float(prof["compile_timeout_sec"]),
        memory_mb=int(prof["memory_mb"]),
        cpus=float(prof["cpus"]),
        pids_limit=int(prof["pids_limit"]),
        nofile_limit=int(prof["nofile_limit"]),
        fsize_mb=int(prof["fsize_mb"]),
        max_output_bytes=int(prof["max_output_bytes"]),
        env_vars=env.env_vars,
        apply_nproc_rlimit=(env.id == "cp"),
    )

    if proj_res.stage == "compile" and not proj_res.ok:
        return {
            "passed": False,
            "status": STATUS_COMPILATION_ERROR,
            "score_fraction": 0.0,
            "execution_time_ms": proj_res.execution_time_ms,
            "memory_kb": float(proj_res.max_rss_kb or 0),
            "actual_output": "",
            "error_message": (proj_res.stderr or "Compilation failed.")[:2000],
            "feedback": "Compilation failed.",
            "metrics": {},
            "output_files": [],
            "is_compile_error": True,
        }

    if proj_res.timed_out:
        return {
            "passed": False,
            "status": STATUS_TIME_LIMIT,
            "score_fraction": 0.0,
            "execution_time_ms": proj_res.execution_time_ms,
            "memory_kb": float(proj_res.max_rss_kb or 0),
            "actual_output": (proj_res.stdout or "")[:2000],
            "error_message": f"Execution exceeded time limit of {prof['wall_timeout_sec']:.1f}s.",
            "feedback": "Time Limit Exceeded",
            "metrics": {},
            "output_files": [],
            "is_compile_error": False,
        }

    if proj_res.oom_killed:
        return {
            "passed": False,
            "status": STATUS_MEMORY_LIMIT,
            "score_fraction": 0.0,
            "execution_time_ms": proj_res.execution_time_ms,
            "memory_kb": float(proj_res.max_rss_kb or 0),
            "actual_output": (proj_res.stdout or "")[:2000],
            "error_message": f"Memory limit ({prof['memory_mb']} MB) exceeded.",
            "feedback": "Memory Limit Exceeded",
            "metrics": {},
            "output_files": [],
            "is_compile_error": False,
        }

    if proj_res.output_limit_exceeded:
        return {
            "passed": False,
            "status": STATUS_OUTPUT_LIMIT,
            "score_fraction": 0.0,
            "execution_time_ms": proj_res.execution_time_ms,
            "memory_kb": float(proj_res.max_rss_kb or 0),
            "actual_output": (proj_res.stdout or "")[:2000],
            "error_message": "Program produced excessive output and was terminated.",
            "feedback": "Output Limit Exceeded",
            "metrics": {},
            "output_files": [],
            "is_compile_error": False,
        }

    if proj_res.exit_code != 0:
        err_detail = (proj_res.stderr or "").strip() or f"Process exited with code {proj_res.exit_code}."
        return {
            "passed": False,
            "status": STATUS_RUNTIME_ERROR,
            "score_fraction": 0.0,
            "execution_time_ms": proj_res.execution_time_ms,
            "memory_kb": float(proj_res.max_rss_kb or 0),
            "actual_output": (proj_res.stdout or "")[:2000],
            "error_message": err_detail[:2000],
            "feedback": "Runtime Error",
            "metrics": {},
            "output_files": [],
            "is_compile_error": False,
        }

    # Evaluate output according to evaluation_type
    stdout_to_eval = proj_res.stdout or ""
    if eval_type == "function_harness":
        h_results = proj_res.harness_results or []
        if not h_results:
            return {
                "passed": False,
                "status": STATUS_RUNTIME_ERROR,
                "score_fraction": 0.0,
                "execution_time_ms": proj_res.execution_time_ms,
                "memory_kb": float(proj_res.max_rss_kb or 0),
                "actual_output": stdout_to_eval[:2000],
                "error_message": "Function harness returned no results.",
                "feedback": "Function harness error",
                "metrics": {},
                "output_files": proj_res.output_files or [],
                "is_compile_error": False,
            }
        first_call = h_results[0]
        if not first_call.get("ok", False):
            return {
                "passed": False,
                "status": STATUS_RUNTIME_ERROR,
                "score_fraction": 0.0,
                "execution_time_ms": proj_res.execution_time_ms,
                "memory_kb": float(proj_res.max_rss_kb or 0),
                "actual_output": "",
                "error_message": str(first_call.get("error", "Exception in function"))[:2000],
                "feedback": str(first_call.get("error", "Exception in function"))[:300],
                "metrics": {},
                "output_files": proj_res.output_files or [],
                "is_compile_error": False,
            }
        ret_val = first_call.get("result")
        ret_json = json.dumps(ret_val)
        # Try structured JSON comparison first; fall back to exact/numeric string comparison
        try:
            json.loads(tc_expected)
            outcome = evaluate_structured_json(ret_json, tc_expected, proj_res.output_files or [], eval_config)
        except Exception:
            outcome = evaluate_exact(str(ret_val), tc_expected)
        actual_display = ret_json if not isinstance(ret_val, str) else ret_val
    elif eval_type == "numeric_tolerance":
        outcome = evaluate_numeric_tolerance(stdout_to_eval, tc_expected, eval_config)
        actual_display = stdout_to_eval
    elif eval_type == "structured_json":
        outcome = evaluate_structured_json(stdout_to_eval, tc_expected, proj_res.output_files or [], eval_config)
        actual_display = outcome.actual_summary or stdout_to_eval
    elif eval_type == "file_based":
        outcome = evaluate_file_based(stdout_to_eval, tc_expected, proj_res.output_files or [], eval_config)
        actual_display = outcome.actual_summary or stdout_to_eval
    elif eval_type == "ml_metrics":
        outcome = evaluate_ml_metrics(stdout_to_eval, tc_expected, proj_res.output_files or [], eval_config)
        actual_display = outcome.actual_summary or stdout_to_eval
    elif eval_type == "custom_script":
        script_code = str(eval_config.get("custom_evaluator_script") or eval_config.get("script") or "")
        outcome = evaluate_custom_script(
            executor,
            evaluator_script=script_code,
            student_stdout=stdout_to_eval,
            expected_output=tc_expected,
            output_files=proj_res.output_files or [],
            datasets_b64=datasets_b64,
            image=env.image,
        )
        actual_display = outcome.actual_summary or stdout_to_eval
    else:
        outcome = evaluate_exact(stdout_to_eval, tc_expected)
        actual_display = stdout_to_eval

    # Strip raw content_b64 from large binary files unless it's a small previewable PNG/CSV/JSON (<256KB)
    safe_out_files = []
    for f in (proj_res.output_files or []):
        f_copy = {
            "name": f.get("name"),
            "size_bytes": f.get("size_bytes", 0),
        }
        if int(f.get("size_bytes", 0)) <= 262144:
            f_copy["content_b64"] = f.get("content_b64")
        safe_out_files.append(f_copy)

    return {
        "passed": outcome.passed,
        "status": "Passed" if outcome.passed else (STATUS_WRONG_ANSWER if outcome.status == "Failed" else outcome.status),
        "score_fraction": outcome.score_fraction,
        "execution_time_ms": proj_res.execution_time_ms,
        "memory_kb": float(proj_res.max_rss_kb or 0),
        "actual_output": (actual_display or "")[:8000],
        "error_message": None if outcome.passed else (outcome.feedback or None),
        "feedback": outcome.feedback,
        "metrics": outcome.metrics,
        "output_files": safe_out_files,
        "is_compile_error": False,
    }


def evaluate_submission_by_id(
    submission_id: int,
    executor: Optional[SandboxExecutor] = None,
) -> Optional[Submission]:
    """
    Evaluate a claimed submission against all test cases of its problem,
    save `SubmissionResult` rows, and update `Submission` and related test/assignment scores.
    """
    executor = executor or SandboxExecutor()
    db = SessionLocal()
    t_start = time.perf_counter()
    try:
        sub = db.query(Submission).filter(Submission.id == submission_id).first()
        if not sub:
            return None

        if sub.status == STATUS_PENDING:
            sub.status = STATUS_RUNNING
            sub.started_at = datetime.utcnow()
            sub.attempt_count = (sub.attempt_count or 0) + 1
            db.commit()

        problem: Optional[Problem] = db.query(Problem).filter(Problem.id == sub.problem_id).first()
        test_cases: List[TestCase] = (
            db.query(TestCase)
            .filter(TestCase.problem_id == sub.problem_id)
            .order_by(TestCase.id.asc())
            .all()
        )
        datasets: List[ProblemDataset] = (
            db.query(ProblemDataset)
            .filter(ProblemDataset.problem_id == sub.problem_id)
            .order_by(ProblemDataset.id.asc())
            .all()
        )

        db.query(SubmissionResult).filter(SubmissionResult.submission_id == sub.id).delete(
            synchronize_session=False
        )
        db.flush()

        total_count = len(test_cases)
        if total_count == 0:
            sub.status = STATUS_INTERNAL_ERROR
            sub.score = 0.0
            sub.passed_count = 0
            sub.total_count = 0
            sub.execution_time = 0.0
            sub.error_message = "No test cases are configured for this problem."
            sub.evaluated_at = datetime.utcnow()
            db.commit()
            db.refresh(sub)
            return sub

        norm_lang = normalize_language(sub.language)
        if not norm_lang:
            sub.status = STATUS_COMPILATION_ERROR
            sub.score = 0.0
            sub.passed_count = 0
            sub.total_count = total_count
            sub.execution_time = 0.0
            sub.error_message = f"Unsupported language: {sub.language}"
            sub.evaluated_at = datetime.utcnow()
            db.commit()
            db.refresh(sub)
            return sub

        env_id = (getattr(problem, "environment_id", None) or "cp").strip()
        try:
            env = get_environment(env_id)
        except ValueError:
            env = get_environment("cp")

        if norm_lang not in env.languages:
            sub.status = STATUS_COMPILATION_ERROR
            sub.score = 0.0
            sub.passed_count = 0
            sub.total_count = total_count
            sub.execution_time = 0.0
            sub.error_message = (
                f"Language '{norm_lang}' is not supported in environment '{env.name}' "
                f"(allowed: {', '.join(env.languages)})."
            )
            sub.evaluated_at = datetime.utcnow()
            db.commit()
            db.refresh(sub)
            return sub

        eval_type = (getattr(problem, "evaluation_type", None) or "exact").strip()
        eval_config = parse_evaluation_config(getattr(problem, "evaluation_config", None))
        res_overrides = parse_evaluation_config(getattr(problem, "resource_overrides", None))
        prof = effective_profile(env, res_overrides)

        files_dict = _normalize_submission_files(sub.code, getattr(sub, "files_json", None), norm_lang)
        entry_point = (
            getattr(sub, "entry_point", None)
            or getattr(problem, "entry_point", None)
            or eval_config.get("entry_point")
        )
        datasets_b64 = _package_datasets_tar_b64(datasets)

        use_fast_cp_path = (
            env.id == "cp"
            and eval_type == "exact"
            and len(files_dict) == 1
            and not datasets_b64
            and not res_overrides
        )

        passed_count = 0
        total_time_ms = 0.0
        peak_memory_kb = 0.0
        score_fractions: List[float] = []
        aggregated_metrics: Dict[str, Any] = {}
        first_failure_status: Optional[str] = None
        first_error_message: Optional[str] = None

        if use_fast_cp_path:
            cmp_res = executor.compile_source(norm_lang, sub.code)
            if not cmp_res.ok:
                sub.status = cmp_res.status
                sub.score = 0.0
                sub.passed_count = 0
                sub.total_count = total_count
                sub.execution_time = 0.0
                sub.error_message = cmp_res.error_message
                sub.evaluated_at = datetime.utcnow()
                if sub.submission_type == "coding_test" and sub.coding_test_id:
                    recompute_coding_test_student_score(sub.coding_test_id, sub.user_id, db)
                db.commit()
                db.refresh(sub)
                return sub

            for tc in test_cases:
                run_res = executor.run_single_test(
                    language=norm_lang,
                    code=sub.code,
                    artifact_b64=cmp_res.artifact_b64,
                    test_input=tc.input,
                    expected_output=tc.expected_output,
                )
                total_time_ms += run_res.execution_time_ms
                if run_res.passed:
                    passed_count += 1
                    score_fractions.append(1.0)
                else:
                    score_fractions.append(0.0)
                    if first_failure_status is None:
                        first_failure_status = run_res.status
                    if first_error_message is None and run_res.error_message:
                        first_error_message = run_res.error_message

                sr = SubmissionResult(
                    submission_id=sub.id,
                    test_case_id=tc.id,
                    status=run_res.status,
                    execution_time=run_res.execution_time_ms,
                    actual_output=(run_res.actual_output or "")[:8000],
                    error_message=run_res.error_message,
                )
                db.add(sr)
        else:
            for tc in test_cases:
                tc_res = _evaluate_project_testcase(
                    executor=executor,
                    env=env,
                    prof=prof,
                    norm_lang=norm_lang,
                    files_dict=files_dict,
                    entry_point=entry_point,
                    datasets_b64=datasets_b64,
                    tc_input=tc.input,
                    tc_expected=tc.expected_output,
                    eval_type=eval_type,
                    eval_config=eval_config,
                )
                if tc_res.get("is_compile_error"):
                    sub.status = STATUS_COMPILATION_ERROR
                    sub.score = 0.0
                    sub.passed_count = 0
                    sub.total_count = total_count
                    sub.execution_time = 0.0
                    sub.error_message = tc_res.get("error_message")
                    sub.evaluated_at = datetime.utcnow()
                    if sub.submission_type == "coding_test" and sub.coding_test_id:
                        recompute_coding_test_student_score(sub.coding_test_id, sub.user_id, db)
                    db.commit()
                    db.refresh(sub)
                    return sub

                total_time_ms += float(tc_res["execution_time_ms"] or 0.0)
                peak_memory_kb = max(peak_memory_kb, float(tc_res.get("memory_kb") or 0.0))
                score_fractions.append(float(tc_res.get("score_fraction", 0.0)))

                if tc_res.get("metrics"):
                    aggregated_metrics = dict(tc_res["metrics"])

                if tc_res["passed"]:
                    passed_count += 1
                    sr_status = "Passed"
                else:
                    sr_status = tc_res["status"]
                    if first_failure_status is None:
                        first_failure_status = sr_status if sr_status != "Failed" else STATUS_WRONG_ANSWER
                    if first_error_message is None and tc_res.get("error_message"):
                        first_error_message = tc_res["error_message"]

                sr = SubmissionResult(
                    submission_id=sub.id,
                    test_case_id=tc.id,
                    status=sr_status if sr_status in {"Passed", "Failed"} else sr_status,
                    execution_time=tc_res["execution_time_ms"],
                    memory_used=tc_res.get("memory_kb"),
                    actual_output=(tc_res.get("actual_output") or "")[:8000],
                    error_message=tc_res.get("error_message"),
                )
                db.add(sr)

        max_score = get_submission_max_score(sub, db, problem=problem)
        sub.passed_count = passed_count
        sub.total_count = total_count
        sub.execution_time = round(total_time_ms, 2)
        if peak_memory_kb > 0:
            sub.memory_used = round(peak_memory_kb, 1)
        if aggregated_metrics:
            aggregated_metrics["environment_id"] = env.id
            aggregated_metrics["evaluation_type"] = eval_type
            sub.metrics_json = json.dumps(aggregated_metrics)
        sub.evaluated_at = datetime.utcnow()

        avg_fraction = (sum(score_fractions) / total_count) if score_fractions else (passed_count / total_count)
        if passed_count == total_count:
            sub.status = STATUS_ACCEPTED
            sub.score = round(max_score * max(avg_fraction, 1.0 if eval_type != "custom_script" else avg_fraction), 2)
            sub.error_message = None
        else:
            sub.status = first_failure_status or STATUS_WRONG_ANSWER
            sub.score = round(max_score * avg_fraction, 2)
            sub.error_message = first_error_message

        if sub.submission_type == "coding_test" and sub.coding_test_id:
            recompute_coding_test_student_score(sub.coding_test_id, sub.user_id, db)
        elif sub.submission_type == "assignment" and sub.assignment_id:
            update_assignment_student_status(sub.assignment_id, sub.user_id, db)

        db.commit()
        db.refresh(sub)

        _record_telemetry(
            env_id=env.id,
            eval_type=eval_type,
            elapsed_ms=(time.perf_counter() - t_start) * 1000.0,
            is_sample=False,
        )
        logger.info(
            "Graded submission #%s (user=%s, problem=%s, env=%s, eval=%s, lang=%s): %s (%s/%s, score=%s, time=%sms)",
            sub.id,
            sub.user_id,
            sub.problem_id,
            env.id,
            eval_type,
            norm_lang,
            sub.status,
            sub.passed_count,
            sub.total_count,
            sub.score,
            sub.execution_time,
        )
        return sub
    except Exception as exc:
        logger.exception("Unhandled error grading submission #%s: %s", submission_id, exc)
        try:
            db.rollback()
            sub = db.query(Submission).filter(Submission.id == submission_id).first()
            if sub:
                sub.status = STATUS_INTERNAL_ERROR
                sub.error_message = "Internal evaluation error."
                sub.evaluated_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass
        return None
    finally:
        db.close()


def execute_sample_cases(
    problem_id: int,
    language: str,
    code: str,
    public_test_cases: List[dict],
    executor: Optional[SandboxExecutor] = None,
    *,
    files: Optional[Dict[str, str]] = None,
    entry_point: Optional[str] = None,
    environment_id: str = "cp",
    evaluation_type: str = "exact",
    evaluation_config: Optional[Dict[str, Any]] = None,
    resource_overrides: Optional[Dict[str, Any]] = None,
    public_datasets: Optional[List[Dict[str, Any]]] = None,
) -> dict:
    """
    Execute ONLY public sample test cases inside isolated sandbox containers.
    Does not write to the database or award XP. Never mounts hidden datasets.
    """
    executor = executor or SandboxExecutor()
    t_start = time.perf_counter()
    norm_lang = normalize_language(language)
    if not norm_lang:
        err_msg = f"Unsupported language: {language}"
        return {
            "problem_id": problem_id,
            "language": language,
            "environment_id": environment_id,
            "evaluation_type": evaluation_type,
            "status": STATUS_COMPILATION_ERROR,
            "overall_status": STATUS_COMPILATION_ERROR,
            "passed_count": 0,
            "total_count": len(public_test_cases),
            "execution_time": 0.0,
            "error_message": err_msg,
            "compile_error": err_msg,
            "results": [],
        }

    try:
        env = get_environment(environment_id or "cp")
    except ValueError:
        env = get_environment("cp")

    if norm_lang not in env.languages:
        err_msg = (
            f"Language '{norm_lang}' is not supported in environment '{env.name}' "
            f"(allowed: {', '.join(env.languages)})."
        )
        return {
            "problem_id": problem_id,
            "language": norm_lang,
            "environment_id": env.id,
            "evaluation_type": evaluation_type,
            "status": STATUS_COMPILATION_ERROR,
            "overall_status": STATUS_COMPILATION_ERROR,
            "passed_count": 0,
            "total_count": len(public_test_cases),
            "execution_time": 0.0,
            "error_message": err_msg,
            "compile_error": err_msg,
            "results": [],
        }

    eval_cfg = parse_evaluation_config(evaluation_config)
    res_ovr = parse_evaluation_config(resource_overrides)
    prof = effective_profile(env, res_ovr)
    files_dict = _normalize_submission_files(code, files, norm_lang)
    datasets_b64 = _package_datasets_tar_b64(public_datasets or [])

    use_fast_cp_path = (
        env.id == "cp"
        and (evaluation_type or "exact") == "exact"
        and len(files_dict) == 1
        and not datasets_b64
        and not res_ovr
    )

    if use_fast_cp_path:
        cmp_res = executor.compile_source(norm_lang, code)
        if not cmp_res.ok:
            return {
                "problem_id": problem_id,
                "language": norm_lang,
                "environment_id": env.id,
                "evaluation_type": evaluation_type,
                "status": cmp_res.status,
                "overall_status": cmp_res.status,
                "passed_count": 0,
                "total_count": len(public_test_cases),
                "execution_time": 0.0,
                "error_message": cmp_res.error_message,
                "compile_error": cmp_res.error_message,
                "results": [],
            }

        results = []
        passed_count = 0
        total_time = 0.0
        first_fail_status: Optional[str] = None
        first_fail_error: Optional[str] = None

        for idx, tc in enumerate(public_test_cases, start=1):
            run_res = executor.run_single_test(
                language=norm_lang,
                code=code,
                artifact_b64=cmp_res.artifact_b64,
                test_input=tc.get("input", ""),
                expected_output=tc.get("expected_output", ""),
            )
            total_time += run_res.execution_time_ms
            if run_res.passed:
                passed_count += 1
            elif first_fail_status is None:
                first_fail_status = run_res.status
                first_fail_error = run_res.error_message

            results.append(
                {
                    "test_case_number": idx,
                    "test_case_id": int(tc.get("id", idx)),
                    "input": tc.get("input", ""),
                    "expected_output": tc.get("expected_output", ""),
                    "actual_output": run_res.actual_output[:4000],
                    "passed": run_res.passed,
                    "status": run_res.status,
                    "execution_time": run_res.execution_time_ms,
                    "error_message": run_res.error_message,
                }
            )

        total_count = len(public_test_cases)
        overall = STATUS_ACCEPTED if passed_count == total_count else (first_fail_status or STATUS_WRONG_ANSWER)
        _record_telemetry(
            env_id=env.id,
            eval_type="exact",
            elapsed_ms=(time.perf_counter() - t_start) * 1000.0,
            is_sample=True,
        )
        return {
            "problem_id": problem_id,
            "language": norm_lang,
            "environment_id": env.id,
            "evaluation_type": "exact",
            "status": overall,
            "overall_status": overall,
            "passed_count": passed_count,
            "total_count": total_count,
            "execution_time": round(total_time, 2),
            "error_message": first_fail_error,
            "compile_error": None,
            "results": results,
        }

    # Universal project / environment / evaluation path
    results = []
    passed_count = 0
    total_time = 0.0
    peak_mem_kb = 0.0
    first_fail_status: Optional[str] = None
    first_fail_error: Optional[str] = None

    for idx, tc in enumerate(public_test_cases, start=1):
        tc_res = _evaluate_project_testcase(
            executor=executor,
            env=env,
            prof=prof,
            norm_lang=norm_lang,
            files_dict=files_dict,
            entry_point=entry_point or eval_cfg.get("entry_point"),
            datasets_b64=datasets_b64,
            tc_input=tc.get("input", ""),
            tc_expected=tc.get("expected_output", ""),
            eval_type=evaluation_type or "exact",
            eval_config=eval_cfg,
        )
        if tc_res.get("is_compile_error"):
            return {
                "problem_id": problem_id,
                "language": norm_lang,
                "environment_id": env.id,
                "evaluation_type": evaluation_type,
                "status": STATUS_COMPILATION_ERROR,
                "overall_status": STATUS_COMPILATION_ERROR,
                "passed_count": 0,
                "total_count": len(public_test_cases),
                "execution_time": 0.0,
                "error_message": tc_res.get("error_message"),
                "compile_error": tc_res.get("error_message"),
                "results": [],
            }

        total_time += float(tc_res["execution_time_ms"] or 0.0)
        peak_mem_kb = max(peak_mem_kb, float(tc_res.get("memory_kb") or 0.0))
        if tc_res["passed"]:
            passed_count += 1
        elif first_fail_status is None:
            first_fail_status = tc_res["status"]
            first_fail_error = tc_res.get("error_message")

        results.append(
            {
                "test_case_number": idx,
                "test_case_id": int(tc.get("id", idx)),
                "input": tc.get("input", ""),
                "expected_output": tc.get("expected_output", ""),
                "actual_output": (tc_res.get("actual_output") or "")[:4000],
                "passed": tc_res["passed"],
                "status": tc_res["status"],
                "execution_time": tc_res["execution_time_ms"],
                "memory_used": tc_res.get("memory_kb"),
                "error_message": tc_res.get("error_message"),
                "feedback": tc_res.get("feedback"),
                "metrics": tc_res.get("metrics"),
                "output_files": tc_res.get("output_files"),
            }
        )

    total_count = len(public_test_cases)
    overall = STATUS_ACCEPTED if passed_count == total_count else (first_fail_status or STATUS_WRONG_ANSWER)
    _record_telemetry(
        env_id=env.id,
        eval_type=evaluation_type or "exact",
        elapsed_ms=(time.perf_counter() - t_start) * 1000.0,
        is_sample=True,
    )
    return {
        "problem_id": problem_id,
        "language": norm_lang,
        "environment_id": env.id,
        "evaluation_type": evaluation_type or "exact",
        "status": overall,
        "overall_status": overall,
        "passed_count": passed_count,
        "total_count": total_count,
        "execution_time": round(total_time, 2),
        "memory_used": round(peak_mem_kb, 1) if peak_mem_kb > 0 else None,
        "error_message": first_fail_error,
        "compile_error": None,
        "results": results,
    }


class _InternalGraderHandler(BaseHTTPRequestHandler):
    """Internal HTTP handler for health checks and sample runs from the backend container."""

    def log_message(self, format: str, *args) -> None:
        if "/health" not in (self.path or ""):
            logger.info("Internal RPC %s - %s", self.address_string(), format % args)

    def _send_json(self, status_code: int, data: dict) -> None:
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        executor = _get_executor()
        rt_status = executor.get_runtime_status()
        if self.path == "/health":
            age = round(time.time() - _last_heartbeat, 2)
            ok = age < 60.0 and not _stop_event.is_set() and not rt_status.blocked
            self._send_json(
                200 if ok else 503,
                {
                    "status": "ok" if ok else ("blocked" if rt_status.blocked else "stalled"),
                    "heartbeat_age_sec": age,
                    "runtime_security": rt_status.to_dict(),
                    "telemetry": get_worker_telemetry(),
                },
            )
        elif self.path == "/internal/runtime-status":
            token = self.headers.get("X-Internal-Token", "")
            if token != INTERNAL_TOKEN:
                self._send_json(403, {"detail": "Forbidden"})
                return
            payload = rt_status.to_dict()
            payload["active_sandbox_containers"] = list_active_sandbox_containers()
            payload["telemetry"] = get_worker_telemetry()
            self._send_json(200, payload)
        else:
            self._send_json(404, {"detail": "Not found"})

    def do_POST(self) -> None:
        if self.path != "/internal/run-samples":
            self._send_json(404, {"detail": "Not found"})
            return

        token = self.headers.get("X-Internal-Token", "")
        if token != INTERNAL_TOKEN:
            self._send_json(403, {"detail": "Forbidden"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            res = execute_sample_cases(
                problem_id=int(body["problem_id"]),
                language=str(body["language"]),
                code=str(body.get("code", "")),
                public_test_cases=list(body.get("public_test_cases", [])),
                executor=_get_executor(),
                files=body.get("files"),
                entry_point=body.get("entry_point"),
                environment_id=str(body.get("environment_id", "cp")),
                evaluation_type=str(body.get("evaluation_type", "exact")),
                evaluation_config=body.get("evaluation_config"),
                resource_overrides=body.get("resource_overrides"),
                public_datasets=body.get("public_datasets"),
            )
            self._send_json(200, res)
        except Exception as exc:
            logger.exception("Error in /internal/run-samples: %s", exc)
            self._send_json(500, {"detail": f"Sample execution failed: {exc}"})


def _ensure_worker_schema() -> None:
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "problems" in table_names:
        prob_cols = {c["name"] for c in inspector.get_columns("problems")}
        prob_alters = []
        if "environment_id" not in prob_cols:
            prob_alters.append("ADD COLUMN environment_id VARCHAR(40) NOT NULL DEFAULT 'cp'")
        if "problem_type" not in prob_cols:
            prob_alters.append("ADD COLUMN problem_type VARCHAR(40) NOT NULL DEFAULT 'competitive'")
        if "evaluation_type" not in prob_cols:
            prob_alters.append("ADD COLUMN evaluation_type VARCHAR(40) NOT NULL DEFAULT 'exact'")
        if "evaluation_config" not in prob_cols:
            prob_alters.append("ADD COLUMN evaluation_config TEXT NULL")
        if "resource_overrides" not in prob_cols:
            prob_alters.append("ADD COLUMN resource_overrides TEXT NULL")
        if "starter_files" not in prob_cols:
            prob_alters.append("ADD COLUMN starter_files TEXT NULL")
        if "entry_point" not in prob_cols:
            prob_alters.append("ADD COLUMN entry_point VARCHAR(120) NULL")
        if "max_score" not in prob_cols:
            prob_alters.append("ADD COLUMN max_score FLOAT NOT NULL DEFAULT 10.0")
        if prob_alters:
            with engine.begin() as conn:
                for stmt in prob_alters:
                    conn.execute(text(f"ALTER TABLE problems {stmt}"))
    if "submissions" in table_names:
        sub_cols = {c["name"] for c in inspector.get_columns("submissions")}
        alter_stmts = []
        if "files_json" not in sub_cols:
            alter_stmts.append("ADD COLUMN files_json TEXT NULL")
        if "entry_point" not in sub_cols:
            alter_stmts.append("ADD COLUMN entry_point VARCHAR(120) NULL")
        if "metrics_json" not in sub_cols:
            alter_stmts.append("ADD COLUMN metrics_json TEXT NULL")
        if alter_stmts:
            with engine.begin() as conn:
                for stmt in alter_stmts:
                    conn.execute(text(f"ALTER TABLE submissions {stmt}"))


def run_worker_forever() -> None:
    """Main entry point for the standalone `grader` Docker Compose service."""
    global _last_heartbeat
    logger.info("Waiting for database connectivity...")
    wait_for_db()
    _ensure_worker_schema()

    executor = _get_executor()

    def _handle_sig(signum, _frame):
        logger.info("Received signal %s; shutting down grader worker gracefully...", signum)
        _stop_event.set()

    signal.signal(signal.SIGTERM, _handle_sig)
    signal.signal(signal.SIGINT, _handle_sig)

    server = ThreadingHTTPServer(("0.0.0.0", INTERNAL_PORT), _InternalGraderHandler)
    srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
    srv_thread.start()
    logger.info("Grader internal RPC listening on 0.0.0.0:%s (not exposed on host)", INTERNAL_PORT)

    last_recovery_check = 0.0
    while not _stop_event.is_set():
        _last_heartbeat = time.time()
        try:
            db = SessionLocal()
            try:
                if time.time() - last_recovery_check >= 15.0:
                    recover_stale_submissions(db)
                    last_recovery_check = time.time()

                claimed_id = claim_next_submission(db)
            finally:
                db.close()

            if claimed_id is not None:
                evaluate_submission_by_id(claimed_id, executor=executor)
                continue
        except Exception as exc:
            logger.exception("Grader poll loop error: %s", exc)

        _stop_event.wait(POLL_INTERVAL_SECONDS)

    server.shutdown()
    logger.info("Grader worker stopped.")


if __name__ == "__main__":
    run_worker_forever()
