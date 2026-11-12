"""
CodeClan Grader Worker & Queue Processor.

Responsibilities:
  - Atomically claim pending submissions using `SELECT ... FOR UPDATE SKIP LOCKED`.
  - Recover submissions left in `Running` state if a worker crashes or restarts.
  - Compile and evaluate student programs against all problem test cases (public + hidden)
    inside isolated ephemeral Docker containers via `SandboxExecutor`.
  - Persist per-testcase `SubmissionResult` rows and update `Submission` verdict, score,
    execution time, passed/total counts, and coding-test / assignment aggregates.
  - Serve an internal-only HTTP endpoint (`/internal/run-samples` and `/health`) on the
    Docker network (never exposed on host ports) so FastAPI can trigger sample runs
    without FastAPI ever having access to the Docker socket or executing student code.
"""

from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
import signal
import sys
import threading
import time
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import SessionLocal, wait_for_db
from app.grading.comparison import (
    STATUS_ACCEPTED,
    STATUS_COMPILATION_ERROR,
    STATUS_INTERNAL_ERROR,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_WRONG_ANSWER,
    TERMINAL_STATUSES,
    normalize_language,
)
from app.grading.sandbox import SandboxExecutor
from app.models import (
    AssignmentProblem,
    AssignmentStudent,
    CodingTestProblem,
    CodingTestStudent,
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
STALE_RUNNING_SECONDS = int(os.getenv("GRADER_STALE_RUNNING_SECONDS", "90"))
MAX_GRADING_ATTEMPTS = int(os.getenv("GRADER_MAX_ATTEMPTS", "3"))
DEFAULT_PROBLEM_MAX_SCORE = float(os.getenv("DEFAULT_PROBLEM_MAX_SCORE", "10.0"))
INTERNAL_PORT = int(os.getenv("GRADER_INTERNAL_PORT", "8090"))
INTERNAL_TOKEN = os.getenv("SECRET_KEY", "code-clan-dev-secret-change-me")

_last_heartbeat: float = time.time()
_stop_event = threading.Event()


def get_submission_max_score(sub: Submission, db: Session) -> float:
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
    try:
        sub = db.query(Submission).filter(Submission.id == submission_id).first()
        if not sub:
            return None

        # Ensure status is Running if called directly in tests
        if sub.status == STATUS_PENDING:
            sub.status = STATUS_RUNNING
            sub.started_at = datetime.utcnow()
            sub.attempt_count = (sub.attempt_count or 0) + 1
            db.commit()

        test_cases: List[TestCase] = (
            db.query(TestCase)
            .filter(TestCase.problem_id == sub.problem_id)
            .order_by(TestCase.id.asc())
            .all()
        )

        # Clear any old results from a previous interrupted attempt
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

        passed_count = 0
        total_time_ms = 0.0
        first_failure_status: Optional[str] = None
        first_error_message: Optional[str] = None

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
            else:
                if first_failure_status is None:
                    first_failure_status = run_res.status
                if first_error_message is None and run_res.error_message:
                    # Never include hidden testcase inputs or expected outputs in error_message
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

        max_score = get_submission_max_score(sub, db)
        sub.passed_count = passed_count
        sub.total_count = total_count
        sub.execution_time = round(total_time_ms, 2)
        sub.evaluated_at = datetime.utcnow()

        if passed_count == total_count:
            sub.status = STATUS_ACCEPTED
            sub.score = round(max_score, 2)
            sub.error_message = None
        else:
            sub.status = first_failure_status or STATUS_WRONG_ANSWER
            sub.score = round(max_score * (passed_count / total_count), 2)
            sub.error_message = first_error_message

        if sub.submission_type == "coding_test" and sub.coding_test_id:
            recompute_coding_test_student_score(sub.coding_test_id, sub.user_id, db)
        elif sub.submission_type == "assignment" and sub.assignment_id:
            update_assignment_student_status(sub.assignment_id, sub.user_id, db)

        db.commit()
        db.refresh(sub)
        logger.info(
            "Graded submission #%s (user=%s, problem=%s, lang=%s): %s (%s/%s, score=%s, time=%sms)",
            sub.id,
            sub.user_id,
            sub.problem_id,
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
) -> dict:
    """
    Execute ONLY public sample test cases inside isolated sandbox containers.
    Does not write to the database or award XP.
    """
    executor = executor or SandboxExecutor()
    norm_lang = normalize_language(language)
    if not norm_lang:
        err_msg = f"Unsupported language: {language}"
        return {
            "problem_id": problem_id,
            "language": language,
            "status": STATUS_COMPILATION_ERROR,
            "overall_status": STATUS_COMPILATION_ERROR,
            "passed_count": 0,
            "total_count": len(public_test_cases),
            "execution_time": 0.0,
            "error_message": err_msg,
            "compile_error": err_msg,
            "results": [],
        }

    cmp_res = executor.compile_source(norm_lang, code)
    if not cmp_res.ok:
        return {
            "problem_id": problem_id,
            "language": norm_lang,
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

    return {
        "problem_id": problem_id,
        "language": norm_lang,
        "status": overall,
        "overall_status": overall,
        "passed_count": passed_count,
        "total_count": total_count,
        "execution_time": round(total_time, 2),
        "error_message": first_fail_error,
        "compile_error": None,
        "results": results,
    }


class _InternalGraderHandler(BaseHTTPRequestHandler):
    """Internal HTTP handler for health checks and sample runs from the backend container."""

    def log_message(self, format: str, *args) -> None:
        # Suppress noisy healthcheck logs
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
        if self.path == "/health":
            age = round(time.time() - _last_heartbeat, 2)
            ok = age < 60.0 and not _stop_event.is_set()
            self._send_json(200 if ok else 503, {"status": "ok" if ok else "stalled", "heartbeat_age_sec": age})
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
                code=str(body["code"]),
                public_test_cases=list(body.get("public_test_cases", [])),
            )
            self._send_json(200, res)
        except Exception as exc:
            logger.exception("Error in /internal/run-samples: %s", exc)
            self._send_json(500, {"detail": f"Sample execution failed: {exc}"})


def run_worker_forever() -> None:
    """Main entry point for the standalone `grader` Docker Compose service."""
    global _last_heartbeat
    logger.info("Waiting for database connectivity...")
    wait_for_db()

    executor = SandboxExecutor()

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
