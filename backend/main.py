import base64
from collections import defaultdict
from datetime import datetime, timedelta
import io
import json
import os
import posixpath
import threading
import time
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request
import zipfile

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, func, inspect, text
from sqlalchemy.orm import Session

from app.auth import (
    SECRET_KEY,
    create_access_token,
    get_current_user,
    hash_password,
    require_roles,
    require_teacher,
    verify_password,
)
from app.database import Base, engine, get_db, wait_for_db
from app.grading.comparison import (
    STATUS_ACCEPTED,
    STATUS_PENDING,
    STATUS_RUNNING,
    SUPPORTED_LANGUAGES,
    TERMINAL_STATUSES,
    normalize_language,
)
from app.grading.environments import (
    effective_profile,
    get_environment,
    list_environments,
)
from app.grading.evaluators import (
    SUPPORTED_EVALUATION_TYPES,
    parse_evaluation_config,
)
from app.grading.worker import (
    evaluate_submission_by_id,
    execute_sample_cases,
    get_submission_max_score,
    get_worker_telemetry,
    recompute_coding_test_student_score,
)
from app.models import (
    AcademicPractical,
    AcademicPracticalStudent,
    Assignment,
    AssignmentProblem,
    AssignmentStudent,
    CodingTest,
    CodingTestProblem,
    CodingTestStudent,
    Problem,
    ProblemDataset,
    Submission,
    SubmissionResult,
    TestCase,
    User,
)
from app.schemas import (
    AcademicPracticalBulkAssign,
    AcademicPracticalCreate,
    AcademicPracticalEvaluateRequest,
    AcademicPracticalResponse,
    AcademicPracticalStudentInfo,
    AcademicPracticalStudentSubmit,
    AssignedProblemInfo,
    AssignedStudentInfo,
    AssignmentCreate,
    AssignmentResponse,
    AuthResponse,
    CodingTestCreate,
    CodingTestResponse,
    DatasetCreate,
    DatasetPublicResponse,
    HiddenTestsSummary,
    LeaderboardEntry,
    LoginRequest,
    ProblemCreate,
    ProblemResponse,
    PublicSubmissionCaseResult,
    RegisterRequest,
    RunSamplesRequest,
    RunSamplesResponse,
    SampleTestCaseResult,
    StudentGroupedProblemSubmission,
    StudentOverview,
    StudentProgress,
    SubmissionCreate,
    SubmissionResponse,
    TeacherGroupedStudentSubmission,
    TeacherOverview,
    TestCaseCreate,
    TestCasePublic,
    TestCaseResponse,
    UserCreate,
    UserResponse,
)

# Retry briefly if MySQL is still starting (e.g. right after `docker compose up`).
wait_for_db()

Base.metadata.create_all(bind=engine)


def _run_lightweight_migrations():
    """create_all() does not add columns to existing tables, so add new ones safely here."""
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if "users" in table_names:
        user_cols = {c["name"] for c in inspector.get_columns("users")}
        if "password_hash" not in user_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NULL"))

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
        if "passed_count" not in sub_cols:
            alter_stmts.append("ADD COLUMN passed_count INT NOT NULL DEFAULT 0")
        if "total_count" not in sub_cols:
            alter_stmts.append("ADD COLUMN total_count INT NOT NULL DEFAULT 0")
        if "error_message" not in sub_cols:
            alter_stmts.append("ADD COLUMN error_message TEXT NULL")
        if "started_at" not in sub_cols:
            alter_stmts.append("ADD COLUMN started_at DATETIME NULL")
        if "evaluated_at" not in sub_cols:
            alter_stmts.append("ADD COLUMN evaluated_at DATETIME NULL")
        if "attempt_count" not in sub_cols:
            alter_stmts.append("ADD COLUMN attempt_count INT NOT NULL DEFAULT 0")
        if "files_json" not in sub_cols:
            alter_stmts.append("ADD COLUMN files_json TEXT NULL")
        if "entry_point" not in sub_cols:
            alter_stmts.append("ADD COLUMN entry_point VARCHAR(120) NULL")
        if "metrics_json" not in sub_cols:
            alter_stmts.append("ADD COLUMN metrics_json TEXT NULL")
        if "practical_id" not in sub_cols:
            alter_stmts.append("ADD COLUMN practical_id INT NULL")
        if alter_stmts:
            with engine.begin() as conn:
                for stmt in alter_stmts:
                    conn.execute(text(f"ALTER TABLE submissions {stmt}"))

    if "coding_test_students" in table_names:
        cts_cols = {c["name"] for c in inspector.get_columns("coding_test_students")}
        cts_alters = []
        if "xp_awarded" not in cts_cols:
            cts_alters.append("ADD COLUMN xp_awarded TINYINT(1) NOT NULL DEFAULT 0")
        if "xp_awarded_amount" not in cts_cols:
            cts_alters.append("ADD COLUMN xp_awarded_amount INT NOT NULL DEFAULT 0")
        if "xp_awarded_at" not in cts_cols:
            cts_alters.append("ADD COLUMN xp_awarded_at DATETIME NULL")
        if cts_alters:
            with engine.begin() as conn:
                for stmt in cts_alters:
                    conn.execute(text(f"ALTER TABLE coding_test_students {stmt}"))
                # Backfill existing completed test records so historical XP rewards are preserved
                conn.execute(
                    text(
                        "UPDATE coding_test_students "
                        "SET xp_awarded = 1, xp_awarded_amount = 10, xp_awarded_at = COALESCE(submitted_at, NOW()) "
                        "WHERE status IN ('submitted', 'completed') AND xp_awarded = 0"
                    )
                )

    if "assignments" in table_names:
        asgn_cols = {c["name"] for c in inspector.get_columns("assignments")}
        if "allow_copy_paste" not in asgn_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE assignments ADD COLUMN allow_copy_paste TINYINT(1) NOT NULL DEFAULT 1"))

    if "coding_tests" in table_names:
        ct_cols = {c["name"] for c in inspector.get_columns("coding_tests")}
        if "allow_copy_paste" not in ct_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE coding_tests ADD COLUMN allow_copy_paste TINYINT(1) NOT NULL DEFAULT 0"))


_run_lightweight_migrations()

app = FastAPI(
    title="Code Clan API",
    description="Backend API for Code Clan — Collaborative Coding & Learning Platform",
    version="2.0.0",
)

CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting state for /submissions/run-samples (per user_id, sliding 60s window)
SAMPLE_RUN_RATE_LIMIT = int(os.getenv("SAMPLE_RUN_RATE_LIMIT_PER_MIN", "15"))
_sample_run_timestamps: dict[int, list[float]] = defaultdict(list)
_rate_limit_lock = threading.Lock()

GRADER_URL = os.getenv("GRADER_URL", "").strip()
INLINE_GRADING_FALLBACK = os.getenv("INLINE_GRADING_FALLBACK", "true").lower() == "true"


def _check_sample_rate_limit(user_id: int) -> None:
    now = time.time()
    window_start = now - 60.0
    with _rate_limit_lock:
        recent = [ts for ts in _sample_run_timestamps[user_id] if ts > window_start]
        if len(recent) >= SAMPLE_RUN_RATE_LIMIT:
            _sample_run_timestamps[user_id] = recent
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded ({SAMPLE_RUN_RATE_LIMIT} sample runs per minute). Please wait a moment.",
            )
        recent.append(now)
        _sample_run_timestamps[user_id] = recent


@app.get("/", tags=["General"])
def root():
    return {
        "message": "Welcome to Code Clan API",
        "status": "healthy",
        "version": "2.0.0",
        "supported_languages": list(SUPPORTED_LANGUAGES),
    }


@app.get("/health", tags=["General"])
def health(db: Session = Depends(get_db)):
    """Liveness + database connectivity check (used by the Docker health check)."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")
    return {"status": "ok", "database": "ok"}


@app.get("/execution/security-status", tags=["General"])
def execution_security_status():
    """
    Return verified sandbox isolation & runtime security status from the isolated
    grader worker. Never claims gVisor (`runsc`) is active unless verified.
    """
    if GRADER_URL:
        try:
            req = urllib.request.Request(
                f"{GRADER_URL.rstrip('/')}/internal/runtime-status",
                headers={"X-Internal-Token": SECRET_KEY},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            return {
                "execution_env": os.getenv("EXECUTION_ENV", "development"),
                "requested_runtime": "runsc",
                "active_runtime": "unreachable",
                "available_runtimes": [],
                "host_kernel": "unknown",
                "sandbox_kernel": "unknown",
                "gvisor_verified": False,
                "fallback_active": False,
                "production_secure": False,
                "blocked": True,
                "security_mode": "GRADER_WORKER_UNREACHABLE",
                "message": f"Isolated grader worker is unreachable: {exc}",
                "warnings": [str(exc)],
                "active_sandbox_containers": [],
            }
    return {
        "execution_env": os.getenv("EXECUTION_ENV", "development"),
        "requested_runtime": "runsc",
        "active_runtime": "unconfigured",
        "available_runtimes": [],
        "host_kernel": "unknown",
        "sandbox_kernel": "unknown",
        "gvisor_verified": False,
        "fallback_active": False,
        "production_secure": False,
        "blocked": True,
        "security_mode": "GRADER_URL_NOT_CONFIGURED",
        "message": "GRADER_URL is not configured on backend.",
        "warnings": ["GRADER_URL is not configured."],
        "active_sandbox_containers": [],
    }


@app.get("/environments", tags=["General"])
def get_execution_environments():
    """Return preconfigured execution environments and supported evaluation strategies."""
    return {
        "environments": list_environments(),
        "evaluation_types": list(SUPPORTED_EVALUATION_TYPES),
        "supported_languages": list(SUPPORTED_LANGUAGES),
    }


@app.get("/execution/metrics", tags=["General"])
def get_execution_metrics(db: Session = Depends(get_db)):
    """Return queue depth, submission status counts, and grader worker telemetry."""
    pending_count = db.query(Submission).filter(Submission.status == STATUS_PENDING).count()
    running_count = db.query(Submission).filter(Submission.status == STATUS_RUNNING).count()
    total_submissions = db.query(Submission).count()
    accepted_submissions = db.query(Submission).filter(Submission.status == STATUS_ACCEPTED).count()

    sec_status = execution_security_status()
    return {
        "queue": {
            "pending": pending_count,
            "running": running_count,
            "total_submissions": total_submissions,
            "accepted_submissions": accepted_submissions,
        },
        "worker_telemetry": sec_status.get("telemetry", get_worker_telemetry()),
        "runtime_security": {
            "active_runtime": sec_status.get("active_runtime"),
            "security_mode": sec_status.get("security_mode"),
            "gvisor_verified": sec_status.get("gvisor_verified", False),
            "containers_verified": sec_status.get("containers_verified", 0),
            "container_verification_failures": sec_status.get("container_verification_failures", 0),
            "active_sandbox_containers": sec_status.get("active_sandbox_containers", []),
        },
        "environments": list_environments(),
    }


# =========================================================
# AUTH ENDPOINTS
# =========================================================

def _normalize_email(email: str) -> str:
    return email.strip().lower()


@app.post("/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED, tags=["Auth"])
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    email = _normalize_email(payload.email)
    existing = db.query(User).filter(func.lower(User.email) == email).first()

    if existing:
        if existing.password_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email already exists. Please log in.",
            )
        existing.password_hash = hash_password(payload.password)
        existing.name = payload.name.strip() or existing.name
        db.commit()
        db.refresh(existing)
        user = existing
    else:
        user = User(
            name=payload.name.strip(),
            email=email,
            role=payload.role,
            password_hash=hash_password(payload.password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return AuthResponse(access_token=create_access_token(user), user=user)


@app.post("/auth/login", response_model=AuthResponse, tags=["Auth"])
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = _normalize_email(payload.email)
    user = db.query(User).filter(func.lower(User.email) == email).first()

    if user and not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This account has no password yet. Use Sign Up with the same email to set one.",
        )
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    return AuthResponse(access_token=create_access_token(user), user=user)


@app.get("/auth/me", response_model=UserResponse, tags=["Auth"])
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user


# =========================================================
# USER ENDPOINTS
# =========================================================

@app.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED, tags=["Users"])
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    _teacher: User = Depends(require_teacher),
):
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists.",
        )

    new_user = User(
        name=user.name,
        email=user.email,
        role=user.role,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.get("/users", response_model=List[UserResponse], tags=["Users"])
def list_users(
    role: Optional[str] = Query(None, pattern="^(student|teacher|admin)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    return query.offset(skip).limit(limit).all()


@app.get("/users/{user_id}", response_model=UserResponse, tags=["Users"])
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


# =========================================================
# PROBLEM & DATASET ENDPOINTS (WITH HIDDEN TEST/DATASET PROTECTION)
# =========================================================

MAX_DATASET_FILE_BYTES = 2 * 1024 * 1024  # 2 MB per dataset file


def _sanitize_dataset_filename(name: str) -> str:
    clean = (name or "").replace("\\", "/").strip().lstrip("/")
    norm = posixpath.normpath(clean)
    if not norm or norm.startswith("..") or "/.." in norm or norm.startswith("/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid dataset filename.")
    return norm


def _dataset_to_public_response(ds: ProblemDataset, include_content: bool = False) -> DatasetPublicResponse:
    preview: Optional[str] = None
    if ds.mime_type.startswith("text/") or ds.filename.endswith((".csv", ".json", ".txt", ".tsv", ".md")):
        try:
            raw = base64.b64decode(ds.content_b64 or "")
            preview = raw[:1200].decode("utf-8", errors="replace")
        except Exception:
            preview = None
    return DatasetPublicResponse(
        id=ds.id,
        problem_id=ds.problem_id,
        filename=ds.filename,
        visibility=ds.visibility,
        mime_type=ds.mime_type,
        size_bytes=ds.size_bytes,
        description=ds.description,
        preview_text=preview,
        content_b64=ds.content_b64 if include_content else None,
        created_at=ds.created_at,
    )


def _safe_json_loads(raw: Optional[str], default: Any = None) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _build_public_problem_response(p: Problem) -> ProblemResponse:
    """
    Build a ProblemResponse containing ONLY public (`is_hidden == False`) test cases
    and public (`visibility == 'public'`) datasets.
    Hidden test case inputs/outputs, hidden datasets, and custom teacher evaluator scripts
    are never exposed to students.
    """
    public_tcs = [
        TestCasePublic(
            id=tc.id,
            problem_id=tc.problem_id,
            input=tc.input,
            expected_output=tc.expected_output,
            is_hidden=False,
        )
        for tc in p.test_cases
        if not tc.is_hidden
    ]
    hidden_count = sum(1 for tc in p.test_cases if tc.is_hidden)

    all_datasets = list(getattr(p, "datasets", []) or [])
    public_ds = [
        _dataset_to_public_response(ds, include_content=False)
        for ds in all_datasets
        if ds.visibility == "public"
    ]
    hidden_ds_count = sum(1 for ds in all_datasets if ds.visibility != "public")

    env_id = getattr(p, "environment_id", None) or "cp"
    try:
        env_obj = get_environment(env_id)
    except ValueError:
        env_obj = get_environment("cp")

    eval_cfg = _safe_json_loads(getattr(p, "evaluation_config", None), {})
    if isinstance(eval_cfg, dict):
        # Never expose custom teacher evaluator script source on public problem endpoint
        public_eval_cfg = {
            k: v
            for k, v in eval_cfg.items()
            if k not in {"custom_evaluator_script", "script"}
        }
        if "custom_evaluator_script" in eval_cfg or "script" in eval_cfg:
            public_eval_cfg["has_custom_script"] = True
    else:
        public_eval_cfg = {}

    res_ovr = _safe_json_loads(getattr(p, "resource_overrides", None), {})
    starter = _safe_json_loads(getattr(p, "starter_files", None), None)

    return ProblemResponse(
        id=p.id,
        title=p.title,
        description=p.description,
        difficulty=p.difficulty,
        topic=p.topic,
        input_format=p.input_format,
        output_format=p.output_format,
        constraints=p.constraints,
        examples=p.examples,
        environment_id=env_obj.id,
        problem_type=getattr(p, "problem_type", None) or "competitive",
        evaluation_type=getattr(p, "evaluation_type", None) or "exact",
        evaluation_config=public_eval_cfg,
        resource_overrides=effective_profile(env_obj, res_ovr if isinstance(res_ovr, dict) else None),
        starter_files=starter,
        entry_point=getattr(p, "entry_point", None),
        max_score=float(getattr(p, "max_score", None) or 10.0),
        created_by=p.created_by,
        created_at=p.created_at,
        updated_at=p.updated_at,
        test_cases=public_tcs,
        hidden_test_count=hidden_count,
        datasets=public_ds,
        hidden_dataset_count=hidden_ds_count,
        environment_info=env_obj.to_public_dict(),
    )


def _serialize_json_field(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, str):
        return val
    return json.dumps(val)


@app.post("/problems", response_model=ProblemResponse, status_code=status.HTTP_201_CREATED, tags=["Problems"])
def create_problem(
    problem: ProblemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    problem.created_by = current_user.id

    env_id = (problem.environment_id or "cp").strip()
    try:
        env_obj = get_environment(env_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    eval_type = (problem.evaluation_type or "exact").strip()
    if eval_type not in SUPPORTED_EVALUATION_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported evaluation_type '{eval_type}'. Allowed: {', '.join(SUPPORTED_EVALUATION_TYPES)}.",
        )

    new_problem = Problem(
        title=problem.title,
        description=problem.description,
        difficulty=problem.difficulty,
        topic=problem.topic,
        input_format=problem.input_format,
        output_format=problem.output_format,
        constraints=problem.constraints,
        examples=problem.examples,
        environment_id=env_obj.id,
        problem_type=problem.problem_type or "competitive",
        evaluation_type=eval_type,
        evaluation_config=_serialize_json_field(problem.evaluation_config),
        resource_overrides=_serialize_json_field(problem.resource_overrides),
        starter_files=_serialize_json_field(problem.starter_files),
        entry_point=problem.entry_point,
        max_score=float(problem.max_score or 10.0),
        created_by=current_user.id,
    )
    db.add(new_problem)
    db.flush()

    if problem.test_cases:
        for tc in problem.test_cases:
            new_tc = TestCase(
                problem_id=new_problem.id,
                input=tc.input,
                expected_output=tc.expected_output,
                is_hidden=tc.is_hidden,
            )
            db.add(new_tc)

    if problem.datasets:
        for ds in problem.datasets:
            fname = _sanitize_dataset_filename(ds.filename)
            if ds.content_b64:
                try:
                    raw_bytes = base64.b64decode(ds.content_b64)
                except Exception:
                    raise HTTPException(status_code=400, detail=f"Invalid base64 dataset '{fname}'.")
                b64_str = ds.content_b64
            else:
                raw_bytes = (ds.content_text or "").encode("utf-8")
                b64_str = base64.b64encode(raw_bytes).decode("ascii")
            if len(raw_bytes) > MAX_DATASET_FILE_BYTES:
                raise HTTPException(status_code=400, detail=f"Dataset '{fname}' exceeds 2 MB limit.")
            db.add(
                ProblemDataset(
                    problem_id=new_problem.id,
                    filename=fname,
                    visibility=ds.visibility or "public",
                    mime_type=ds.mime_type or "text/plain",
                    size_bytes=len(raw_bytes),
                    content_b64=b64_str,
                    description=ds.description,
                )
            )

    db.commit()
    db.refresh(new_problem)
    return _build_public_problem_response(new_problem)


@app.post("/problems/{problem_id}/datasets", response_model=DatasetPublicResponse, status_code=status.HTTP_201_CREATED, tags=["Problems"])
def add_problem_dataset(
    problem_id: int,
    payload: DatasetCreate,
    db: Session = Depends(get_db),
    _teacher: User = Depends(require_teacher),
):
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found.")

    fname = _sanitize_dataset_filename(payload.filename)
    if payload.content_b64:
        try:
            raw_bytes = base64.b64decode(payload.content_b64)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid base64 dataset content.")
        b64_str = payload.content_b64
    else:
        raw_bytes = (payload.content_text or "").encode("utf-8")
        b64_str = base64.b64encode(raw_bytes).decode("ascii")

    if len(raw_bytes) > MAX_DATASET_FILE_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dataset exceeds 2 MB size limit.")

    ds = ProblemDataset(
        problem_id=problem.id,
        filename=fname,
        visibility=payload.visibility or "public",
        mime_type=payload.mime_type or "text/plain",
        size_bytes=len(raw_bytes),
        content_b64=b64_str,
        description=payload.description,
    )
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return _dataset_to_public_response(ds, include_content=True)


@app.get("/problems/{problem_id}/datasets", response_model=List[DatasetPublicResponse], tags=["Problems"])
def list_problem_datasets(
    problem_id: int,
    include_content: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found.")

    is_teacher = current_user.role in ("teacher", "admin")
    rows = (
        db.query(ProblemDataset)
        .filter(ProblemDataset.problem_id == problem_id)
        .order_by(ProblemDataset.id.asc())
        .all()
    )
    visible = rows if is_teacher else [r for r in rows if r.visibility == "public"]
    return [_dataset_to_public_response(r, include_content=include_content) for r in visible]


@app.delete("/problems/{problem_id}/datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Problems"])
def delete_problem_dataset(
    problem_id: int,
    dataset_id: int,
    db: Session = Depends(get_db),
    _teacher: User = Depends(require_teacher),
):
    ds = (
        db.query(ProblemDataset)
        .filter(ProblemDataset.id == dataset_id, ProblemDataset.problem_id == problem_id)
        .first()
    )
    if not ds:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    db.delete(ds)
    db.commit()
    return None


@app.get("/problems", response_model=List[ProblemResponse], tags=["Problems"])
def list_problems(
    difficulty: Optional[str] = Query(None, pattern="^(Easy|Medium|Hard)$"),
    topic: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(Problem)
    if difficulty:
        query = query.filter(Problem.difficulty == difficulty)
    if topic:
        query = query.filter(Problem.topic.ilike(f"%{topic}%"))
    if search:
        query = query.filter(Problem.title.ilike(f"%{search}%"))

    problems = query.offset(skip).limit(limit).all()
    return [_build_public_problem_response(p) for p in problems]


@app.get("/problems/{problem_id}", response_model=ProblemResponse, tags=["Problems"])
def get_problem(problem_id: int, db: Session = Depends(get_db)):
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found.")
    return _build_public_problem_response(problem)


@app.get("/problems/{problem_id}/test-cases", response_model=List[TestCaseResponse], tags=["Problems"])
def list_problem_test_cases_for_teacher(
    problem_id: int,
    db: Session = Depends(get_db),
    _teacher: User = Depends(require_teacher),
):
    """Teacher-only endpoint returning both public and hidden test cases for a problem."""
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found.")
    return problem.test_cases


@app.post("/problems/{problem_id}/test-cases", response_model=TestCaseResponse, status_code=status.HTTP_201_CREATED, tags=["Problems"])
def add_test_case(
    problem_id: int,
    test_case: TestCaseCreate,
    db: Session = Depends(get_db),
    _teacher: User = Depends(require_teacher),
):
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found.")

    new_tc = TestCase(
        problem_id=problem_id,
        input=test_case.input,
        expected_output=test_case.expected_output,
        is_hidden=test_case.is_hidden,
    )
    db.add(new_tc)
    db.commit()
    db.refresh(new_tc)
    return new_tc


# =========================================================
# SAMPLE EXECUTION & SUBMISSION ENDPOINTS
# =========================================================

def _submission_to_response(
    s: Submission,
    db: Session,
    include_details: bool = False,
    is_teacher: bool = False,
) -> SubmissionResponse:
    p_title = s.problem.title if s.problem else "Unknown Problem"
    u_name = s.user.name if s.user else f"User #{s.user_id}"
    max_score = get_submission_max_score(s, db, problem=s.problem)

    total_count = s.total_count or (len(s.problem.test_cases) if s.problem and s.problem.test_cases else 0)
    passed_count = s.passed_count or 0

    public_results: Optional[List[PublicSubmissionCaseResult]] = None
    hidden_summary: Optional[HiddenTestsSummary] = None
    teacher_hidden_results: Optional[List[PublicSubmissionCaseResult]] = None

    if include_details:
        pub_list: List[PublicSubmissionCaseResult] = []
        tch_hidden_list: List[PublicSubmissionCaseResult] = []
        hidden_total = 0
        hidden_passed = 0

        # Order results by testcase id
        sorted_results = sorted(s.results, key=lambda r: r.test_case_id)
        pub_idx = 0
        hid_idx = 0
        for r in sorted_results:
            tc = r.test_case
            is_hidden = bool(tc.is_hidden) if tc else False
            passed = r.status == STATUS_ACCEPTED
            if is_hidden:
                hid_idx += 1
                hidden_total += 1
                if passed:
                    hidden_passed += 1
                if is_teacher and tc:
                    tch_hidden_list.append(
                        PublicSubmissionCaseResult(
                            test_case_number=hid_idx,
                            test_case_id=r.test_case_id,
                            is_hidden=True,
                            input=tc.input,
                            expected_output=tc.expected_output,
                            actual_output=r.actual_output,
                            passed=passed,
                            status=r.status,
                            execution_time=r.execution_time,
                            memory_used=r.memory_used,
                            error_message=r.error_message,
                        )
                    )
            else:
                pub_idx += 1
                pub_list.append(
                    PublicSubmissionCaseResult(
                        test_case_number=pub_idx,
                        test_case_id=r.test_case_id,
                        is_hidden=False,
                        input=tc.input if tc else "",
                        expected_output=tc.expected_output if tc else "",
                        actual_output=r.actual_output or "",
                        passed=passed,
                        status=r.status,
                        execution_time=r.execution_time,
                        memory_used=r.memory_used,
                        error_message=r.error_message,
                    )
                )

        # If compilation failed or not yet evaluated, still report total hidden test count
        if hidden_total == 0 and s.problem and s.problem.test_cases:
            hidden_total = sum(1 for tc in s.problem.test_cases if tc.is_hidden)

        public_results = pub_list
        hidden_summary = HiddenTestsSummary(
            total=hidden_total,
            passed=hidden_passed,
            failed=max(0, hidden_total - hidden_passed) if s.status in TERMINAL_STATUSES else 0,
        )
        if is_teacher:
            teacher_hidden_results = tch_hidden_list

    files_dict = _safe_json_loads(getattr(s, "files_json", None), None)
    metrics_dict = _safe_json_loads(getattr(s, "metrics_json", None), None)
    env_id = (getattr(s.problem, "environment_id", None) if s.problem else None) or "cp"
    eval_type = (getattr(s.problem, "evaluation_type", None) if s.problem else None) or "exact"

    prac_id = getattr(s, "practical_id", None)
    if s.submission_type == "assignment" and s.assignment_id:
        asgn_title = s.assignment.title if getattr(s, "assignment", None) else f"#{s.assignment_id}"
        ctx_label = f"Assignment: {asgn_title}"
    elif s.submission_type == "coding_test" and s.coding_test_id:
        test_title = s.coding_test.title if getattr(s, "coding_test", None) else f"#{s.coding_test_id}"
        ctx_label = f"Coding Test: {test_title}"
    elif s.submission_type == "practical" and prac_id:
        prac_obj = getattr(s, "practical", None)
        ctx_label = (
            f"Practical #{prac_obj.practical_number}: {prac_obj.title}"
            if prac_obj
            else f"Practical #{prac_id}"
        )
    elif s.submission_type == "competition" and s.competition_id:
        ctx_label = f"Competition #{s.competition_id}"
    else:
        ctx_label = "Practice"

    return SubmissionResponse(
        id=s.id,
        user_id=s.user_id,
        user_name=u_name,
        problem_id=s.problem_id,
        code=s.code,
        files=files_dict if isinstance(files_dict, dict) else None,
        entry_point=getattr(s, "entry_point", None),
        language=s.language,
        environment_id=env_id,
        evaluation_type=eval_type,
        status=s.status,
        score=round(float(s.score or 0.0), 2),
        max_score=max_score,
        passed_count=passed_count,
        total_count=total_count,
        execution_time=s.execution_time,
        memory_used=s.memory_used,
        error_message=s.error_message,
        metrics=metrics_dict if isinstance(metrics_dict, dict) else None,
        submitted_at=s.submitted_at,
        evaluated_at=s.evaluated_at,
        attempt_count=s.attempt_count or 0,
        submission_type=s.submission_type,
        assignment_id=s.assignment_id,
        coding_test_id=s.coding_test_id,
        competition_id=s.competition_id,
        practical_id=prac_id,
        context_label=ctx_label,
        problem_title=p_title,
        public_results=public_results,
        hidden_summary=hidden_summary,
        teacher_hidden_results=teacher_hidden_results,
    )


def _validate_and_normalize_files(
    code: str,
    files: Optional[Dict[str, str]],
) -> tuple[str, Optional[Dict[str, str]]]:
    """Validate single-file code or multi-file dict; return (primary_code, sanitized_files_dict)."""
    if files:
        if len(files) > 25:
            raise HTTPException(status_code=400, detail="Maximum 25 source files allowed per submission.")
        sanitized: Dict[str, str] = {}
        total_bytes = 0
        for raw_name, content in files.items():
            clean = (raw_name or "").replace("\\", "/").strip().lstrip("/")
            norm = posixpath.normpath(clean)
            if not norm or norm.startswith("..") or "/.." in norm or norm.startswith("/"):
                raise HTTPException(status_code=400, detail=f"Invalid file path '{raw_name}'.")
            if not isinstance(content, str):
                raise HTTPException(status_code=400, detail=f"Invalid file content for '{norm}'.")
            total_bytes += len(content.encode("utf-8"))
            if total_bytes > 512 * 1024:
                raise HTTPException(status_code=400, detail="Total multi-file source size exceeds 512 KB.")
            sanitized[norm] = content
        if not sanitized:
            raise HTTPException(status_code=400, detail="Submission must include at least one non-empty file.")
        primary_code = code.strip() if code and code.strip() else next(iter(sanitized.values()))
        return primary_code, sanitized

    if not code or not code.strip():
        raise HTTPException(status_code=422, detail="Source code cannot be empty.")
    return code, None


@app.post("/submissions/run-samples", response_model=RunSamplesResponse, tags=["Submissions"])
def run_problem_samples(
    payload: RunSamplesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Execute student code against ONLY the public sample test cases and public datasets
    of a problem. Never loads or executes hidden test cases or hidden datasets,
    never creates a graded submission, and never awards XP.
    """
    _check_sample_rate_limit(current_user.id)

    norm_lang = normalize_language(payload.language)
    if not norm_lang:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported language '{payload.language}'. Supported: {', '.join(SUPPORTED_LANGUAGES)}.",
        )

    primary_code, files_dict = _validate_and_normalize_files(payload.code, payload.files)

    problem = db.query(Problem).filter(Problem.id == payload.problem_id).first()
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found.")

    public_tcs = (
        db.query(TestCase)
        .filter(TestCase.problem_id == problem.id, TestCase.is_hidden == False)  # noqa: E712
        .order_by(TestCase.id.asc())
        .all()
    )
    if not public_tcs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No public sample test cases are configured for this problem.",
        )

    public_ds = (
        db.query(ProblemDataset)
        .filter(ProblemDataset.problem_id == problem.id, ProblemDataset.visibility == "public")
        .order_by(ProblemDataset.id.asc())
        .all()
    )
    public_ds_dicts = [
        {"filename": ds.filename, "content_b64": ds.content_b64}
        for ds in public_ds
    ]

    tc_dicts = [
        {"id": tc.id, "input": tc.input, "expected_output": tc.expected_output}
        for tc in public_tcs
    ]

    env_id = getattr(problem, "environment_id", None) or "cp"
    eval_type = getattr(problem, "evaluation_type", None) or "exact"
    eval_cfg = _safe_json_loads(getattr(problem, "evaluation_config", None), {})
    res_ovr = _safe_json_loads(getattr(problem, "resource_overrides", None), {})
    entry_pt = payload.entry_point or getattr(problem, "entry_point", None)

    # Delegate execution to the isolated grader worker over internal network when configured
    if GRADER_URL:
        try:
            req_body = json.dumps(
                {
                    "problem_id": problem.id,
                    "language": norm_lang,
                    "code": primary_code,
                    "files": files_dict,
                    "entry_point": entry_pt,
                    "environment_id": env_id,
                    "evaluation_type": eval_type,
                    "evaluation_config": eval_cfg,
                    "resource_overrides": res_ovr,
                    "public_datasets": public_ds_dicts,
                    "public_test_cases": tc_dicts,
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                f"{GRADER_URL.rstrip('/')}/internal/run-samples",
                data=req_body,
                headers={
                    "Content-Type": "application/json",
                    "X-Internal-Token": SECRET_KEY,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=65) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return RunSamplesResponse(**data)
        except urllib.error.URLError as exc:
            if not INLINE_GRADING_FALLBACK:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Code execution worker is temporarily unavailable: {exc}",
                )

    data = execute_sample_cases(
        problem_id=problem.id,
        language=norm_lang,
        code=primary_code,
        public_test_cases=tc_dicts,
        files=files_dict,
        entry_point=entry_pt,
        environment_id=env_id,
        evaluation_type=eval_type,
        evaluation_config=eval_cfg,
        resource_overrides=res_ovr,
        public_datasets=public_ds_dicts,
    )
    return RunSamplesResponse(**data)


@app.post("/submissions", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED, tags=["Submissions"])
def create_submission(
    sub: SubmissionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Prevent student impersonation
    if sub.user_id is not None and sub.user_id != current_user.id:
        if current_user.role not in ("teacher", "admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot submit solutions on behalf of another user.",
            )
        target_user_id = sub.user_id
    else:
        target_user_id = current_user.id

    norm_lang = normalize_language(sub.language)
    if not norm_lang:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported language '{sub.language}'. Supported: {', '.join(SUPPORTED_LANGUAGES)}.",
        )

    primary_code, files_dict = _validate_and_normalize_files(sub.code, sub.files)

    user = db.query(User).filter(User.id == target_user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    problem = db.query(Problem).filter(Problem.id == sub.problem_id).first()
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found.")

    context_count = sum(
        [
            1 if sub.assignment_id is not None else 0,
            1 if sub.coding_test_id is not None else 0,
            1 if sub.competition_id is not None else 0,
            1 if sub.practical_id is not None else 0,
        ]
    )

    if sub.submission_type == "practice":
        if context_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Practice submissions must not have assignment, coding test, practical, or competition context IDs.",
            )
    elif sub.submission_type == "assignment":
        if sub.assignment_id is None or context_count != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Assignment submission requires an assignment_id and no other context IDs.",
            )
    elif sub.submission_type == "coding_test":
        if sub.coding_test_id is None or context_count != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Coding test submission requires a coding_test_id and no other context IDs.",
            )
    elif sub.submission_type == "competition":
        if sub.competition_id is None or context_count != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Competition submission requires a competition_id and no other context IDs.",
            )
    elif sub.submission_type == "practical":
        if sub.practical_id is None or context_count != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Academic practical submission requires a practical_id and no other context IDs.",
            )

    total_tcs = len(problem.test_cases) if problem.test_cases else 0

    new_sub = Submission(
        user_id=target_user_id,
        problem_id=sub.problem_id,
        code=primary_code,
        files_json=json.dumps(files_dict) if files_dict else None,
        entry_point=sub.entry_point or getattr(problem, "entry_point", None),
        language=norm_lang,
        status=STATUS_PENDING,
        score=0.0,
        passed_count=0,
        total_count=total_tcs,
        submission_type=sub.submission_type,
        assignment_id=sub.assignment_id,
        coding_test_id=sub.coding_test_id,
        competition_id=sub.competition_id,
        practical_id=sub.practical_id,
    )
    db.add(new_sub)
    db.flush()

    # Track participation in CodingTestStudent without awarding unearned points
    if sub.submission_type == "coding_test" and sub.coding_test_id:
        record = (
            db.query(CodingTestStudent)
            .filter(
                CodingTestStudent.coding_test_id == sub.coding_test_id,
                CodingTestStudent.student_id == target_user_id,
            )
            .first()
        )
        if not record:
            record = CodingTestStudent(
                coding_test_id=sub.coding_test_id,
                student_id=target_user_id,
                started_at=datetime.utcnow(),
                status="in_progress",
                score=0.0,
                xp_awarded=False,
                xp_awarded_amount=0,
            )
            db.add(record)

    # Track AcademicPracticalStudent submission status automatically when linked to a coding problem
    if sub.submission_type == "practical" and sub.practical_id:
        prac = db.query(AcademicPractical).filter(AcademicPractical.id == sub.practical_id).first()
        if prac:
            now_dt = datetime.utcnow()
            is_late = bool(prac.deadline and now_dt > prac.deadline)
            prac_status = "Late Submission" if is_late else "Submitted"
            ps_rec = (
                db.query(AcademicPracticalStudent)
                .filter(
                    AcademicPracticalStudent.practical_id == sub.practical_id,
                    AcademicPracticalStudent.student_id == target_user_id,
                )
                .first()
            )
            if ps_rec:
                ps_rec.submission_id = new_sub.id
                ps_rec.submitted_at = now_dt
                ps_rec.status = prac_status
            else:
                ps_rec = AcademicPracticalStudent(
                    practical_id=sub.practical_id,
                    student_id=target_user_id,
                    assigned_at=now_dt,
                    submitted_at=now_dt,
                    status=prac_status,
                    submission_id=new_sub.id,
                )
                db.add(ps_rec)

    db.commit()
    db.refresh(new_sub)

    # When running outside Docker without a separate `grader` service, optionally
    # trigger background evaluation so non-Docker local runs also evaluate automatically.
    if not GRADER_URL and INLINE_GRADING_FALLBACK:
        threading.Thread(target=evaluate_submission_by_id, args=(new_sub.id,), daemon=True).start()

    return _submission_to_response(new_sub, db, include_details=True, is_teacher=current_user.role in ("teacher", "admin"))


def _apply_submission_filters(
    query,
    *,
    user_id: Optional[int] = None,
    problem_id: Optional[int] = None,
    submission_type: Optional[str] = None,
    student_search: Optional[str] = None,
    problem_search: Optional[str] = None,
    language: Optional[str] = None,
    status_filter: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    if user_id is not None:
        query = query.filter(Submission.user_id == user_id)
    if problem_id is not None:
        query = query.filter(Submission.problem_id == problem_id)
    if submission_type:
        query = query.filter(Submission.submission_type == submission_type.strip().lower())
    if language:
        norm_l = normalize_language(language) or language.strip().lower()
        query = query.filter(func.lower(Submission.language) == norm_l)
    if status_filter:
        sf = status_filter.strip()
        if sf.lower() == "pending_or_failed":
            query = query.filter(Submission.status != STATUS_ACCEPTED)
        else:
            query = query.filter(Submission.status == sf)
    if student_search and student_search.strip():
        sq = f"%{student_search.strip()}%"
        query = query.join(User, Submission.user_id == User.id).filter(
            (User.name.ilike(sq)) | (User.email.ilike(sq))
        )
    if problem_search and problem_search.strip():
        pq = f"%{problem_search.strip()}%"
        query = query.join(Problem, Submission.problem_id == Problem.id).filter(
            Problem.title.ilike(pq)
        )
    if date_from and date_from.strip():
        try:
            dt_from = datetime.fromisoformat(date_from.strip().replace("Z", ""))
            query = query.filter(Submission.submitted_at >= dt_from)
        except ValueError:
            pass
    if date_to and date_to.strip():
        try:
            raw_to = date_to.strip().replace("Z", "")
            dt_to = datetime.fromisoformat(raw_to)
            if len(raw_to) <= 10:
                dt_to = dt_to + timedelta(days=1) - timedelta(microseconds=1)
            query = query.filter(Submission.submitted_at <= dt_to)
        except ValueError:
            pass
    return query


@app.get("/submissions", response_model=List[SubmissionResponse], tags=["Submissions"])
def list_submissions(
    user_id: Optional[int] = Query(None),
    problem_id: Optional[int] = Query(None),
    submission_type: Optional[str] = Query(None),
    student_search: Optional[str] = Query(None),
    problem_search: Optional[str] = Query(None),
    language: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    sort_by: Optional[str] = Query("latest", pattern="^(latest|highest_score|execution_time)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    is_teacher = current_user.role in ("teacher", "admin")
    query = db.query(Submission)

    if not is_teacher:
        if user_id is not None and user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Students may only view their own submissions.",
            )
        target_uid = current_user.id
    else:
        target_uid = user_id

    query = _apply_submission_filters(
        query,
        user_id=target_uid,
        problem_id=problem_id,
        submission_type=submission_type,
        student_search=student_search if is_teacher else None,
        problem_search=problem_search,
        language=language,
        status_filter=status_filter,
        date_from=date_from,
        date_to=date_to,
    )

    if sort_by == "highest_score":
        query = query.order_by(desc(Submission.score), desc(Submission.submitted_at), desc(Submission.id))
    elif sort_by == "execution_time":
        query = query.order_by(
            Submission.execution_time.is_(None),
            Submission.execution_time.asc(),
            desc(Submission.submitted_at),
            desc(Submission.id),
        )
    else:
        query = query.order_by(desc(Submission.submitted_at), desc(Submission.id))

    submissions = query.offset(skip).limit(limit).all()
    return [_submission_to_response(s, db, include_details=False, is_teacher=is_teacher) for s in submissions]


@app.get(
    "/submissions/grouped/by-student",
    response_model=List[TeacherGroupedStudentSubmission],
    tags=["Submissions"],
)
def list_grouped_submissions_by_student(
    student_search: Optional[str] = Query(None),
    problem_search: Optional[str] = Query(None),
    problem_id: Optional[int] = Query(None),
    submission_type: Optional[str] = Query(None),
    language: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    sort_by: Optional[str] = Query("latest", pattern="^(latest|highest_score|execution_time|total_submissions)$"),
    db: Session = Depends(get_db),
    _teacher: User = Depends(require_teacher),
):
    """
    Consolidated student submission records for the Teacher Class Submissions view.
    Groups all historical attempts by student without deleting or merging distinct student records.
    """
    query = db.query(Submission)
    query = _apply_submission_filters(
        query,
        problem_id=problem_id,
        submission_type=submission_type,
        student_search=student_search,
        problem_search=problem_search,
        language=language,
        status_filter=status_filter,
        date_from=date_from,
        date_to=date_to,
    )
    subs = query.order_by(desc(Submission.submitted_at), desc(Submission.id)).all()

    by_student: Dict[int, List[Submission]] = defaultdict(list)
    for s in subs:
        by_student[s.user_id].append(s)

    user_ids = list(by_student.keys())
    users_map = (
        {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()}
        if user_ids
        else {}
    )

    grouped: List[TeacherGroupedStudentSubmission] = []
    for uid, student_subs in by_student.items():
        u = users_map.get(uid)
        s_name = u.name if u else f"User #{uid}"
        s_email = u.email if u else ""
        total_cnt = len(student_subs)
        distinct_probs = len({s.problem_id for s in student_subs})
        accepted_cnt = sum(1 for s in student_subs if s.status == STATUS_ACCEPTED)
        pending_cnt = sum(1 for s in student_subs if s.status in (STATUS_PENDING, STATUS_RUNNING))
        failed_cnt = total_cnt - accepted_cnt - pending_cnt
        pending_or_failed = total_cnt - accepted_cnt
        best_sc = round(max((float(s.score or 0.0) for s in student_subs), default=0.0), 2)
        latest = student_subs[0]

        grouped.append(
            TeacherGroupedStudentSubmission(
                user_id=uid,
                student_name=s_name,
                student_email=s_email,
                total_submissions=total_cnt,
                problems_attempted=distinct_probs,
                accepted_count=accepted_cnt,
                pending_or_failed_count=pending_or_failed,
                pending_count=pending_cnt,
                failed_count=failed_cnt,
                best_score=best_sc,
                latest_submitted_at=latest.submitted_at,
                latest_verdict=latest.status,
            )
        )

    if sort_by == "highest_score":
        grouped.sort(key=lambda g: (g.best_score, g.accepted_count, g.total_submissions), reverse=True)
    elif sort_by == "total_submissions":
        grouped.sort(key=lambda g: (g.total_submissions, g.accepted_count), reverse=True)
    else:
        grouped.sort(
            key=lambda g: (g.latest_submitted_at is not None, g.latest_submitted_at or datetime.min),
            reverse=True,
        )

    return grouped


@app.get(
    "/submissions/grouped/by-problem",
    response_model=List[StudentGroupedProblemSubmission],
    tags=["Submissions"],
)
def list_grouped_submissions_by_problem(
    user_id: Optional[int] = Query(None),
    submission_type: Optional[str] = Query(None),
    problem_search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Consolidated submission history grouped by unique (problem_id, context) for the Student
    My Submission History view. Preserves every historical attempt in MySQL.
    """
    is_teacher = current_user.role in ("teacher", "admin")
    if not is_teacher:
        if user_id is not None and user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Students may only view their own submission history.",
            )
        target_uid = current_user.id
    else:
        target_uid = user_id or current_user.id

    query = db.query(Submission).filter(Submission.user_id == target_uid)
    query = _apply_submission_filters(
        query,
        submission_type=submission_type,
        problem_search=problem_search,
    )
    subs = query.order_by(desc(Submission.submitted_at), desc(Submission.id)).all()

    # Group by (problem_id, submission_type, assignment_id, coding_test_id, practical_id, competition_id)
    groups: Dict[tuple, List[Submission]] = defaultdict(list)
    for s in subs:
        prac_id = getattr(s, "practical_id", None)
        key = (
            s.problem_id,
            s.submission_type or "practice",
            s.assignment_id,
            s.coding_test_id,
            prac_id,
            s.competition_id,
        )
        groups[key].append(s)

    result: List[StudentGroupedProblemSubmission] = []
    for key, attempts in groups.items():
        pid, stype, aid, ctid, prac_id, comp_id = key
        latest = attempts[0]
        p_title = latest.problem.title if latest.problem else f"Problem #{pid}"
        max_sc = get_submission_max_score(latest, db, problem=latest.problem)
        best_sc = round(max((float(a.score or 0.0) for a in attempts), default=0.0), 2)
        best_passed = max((int(a.passed_count or 0) for a in attempts), default=0)
        total_tcs = max(
            (int(a.total_count or 0) for a in attempts),
            default=(len(latest.problem.test_cases) if latest.problem and latest.problem.test_cases else 0),
        )
        exec_times = [float(a.execution_time) for a in attempts if a.execution_time is not None]
        best_exec = round(min(exec_times), 2) if exec_times else None

        if stype == "assignment" and aid:
            asgn_title = latest.assignment.title if getattr(latest, "assignment", None) else f"#{aid}"
            ctx_label = f"Assignment: {asgn_title}"
        elif stype == "coding_test" and ctid:
            test_title = latest.coding_test.title if getattr(latest, "coding_test", None) else f"#{ctid}"
            ctx_label = f"Coding Test: {test_title}"
        elif stype == "practical" and prac_id:
            prac_obj = getattr(latest, "practical", None)
            ctx_label = (
                f"Practical #{prac_obj.practical_number}: {prac_obj.title}"
                if prac_obj
                else f"Practical #{prac_id}"
            )
        elif stype == "competition" and comp_id:
            ctx_label = f"Competition #{comp_id}"
        else:
            ctx_label = "Practice"

        g_key = f"{pid}:{stype}:{aid or 0}:{ctid or 0}:{prac_id or 0}:{comp_id or 0}"
        result.append(
            StudentGroupedProblemSubmission(
                group_key=g_key,
                problem_id=pid,
                problem_title=p_title,
                submission_type=stype,
                context_label=ctx_label,
                assignment_id=aid,
                coding_test_id=ctid,
                practical_id=prac_id,
                competition_id=comp_id,
                total_attempts=len(attempts),
                latest_submission_id=latest.id,
                latest_verdict=latest.status,
                latest_language=latest.language,
                latest_submitted_at=latest.submitted_at,
                best_score=best_sc,
                max_score=max_sc,
                best_passed_count=best_passed,
                total_test_cases=total_tcs,
                best_execution_time=best_exec,
            )
        )

    result.sort(
        key=lambda r: (r.latest_submitted_at is not None, r.latest_submitted_at or datetime.min),
        reverse=True,
    )
    return result


@app.get("/submissions/{submission_id}", response_model=SubmissionResponse, tags=["Submissions"])
def get_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found.")

    is_teacher = current_user.role in ("teacher", "admin")
    if not is_teacher and sub.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access another student's submission.",
        )

    return _submission_to_response(sub, db, include_details=True, is_teacher=is_teacher)


# =========================================================
# ASSIGNMENT ENDPOINTS
# =========================================================

def _compute_student_assignment_status(
    a: Assignment,
    student_id: int,
    db: Session,
) -> dict:
    """
    Determine a student's status on an assignment from actual database records:
      - Pending: student has not submitted anything for this assignment.
      - In Progress: student has submitted some (but not all) required problems, or started working.
      - Late: all required problems submitted, and submitted after the assignment deadline.
      - Submitted: all required problems submitted on time, but evaluation is still pending/running.
      - Evaluated: all required problems have been submitted and evaluated on time.
    """
    required_pids = [ap.problem_id for ap in a.problems if ap.problem]
    total_probs = len(required_pids)

    subs = (
        db.query(Submission)
        .filter(
            Submission.assignment_id == a.id,
            Submission.user_id == student_id,
            Submission.submission_type == "assignment",
        )
        .order_by(desc(Submission.submitted_at), desc(Submission.id))
        .all()
    )

    submitted_pids = {s.problem_id for s in subs if s.problem_id in required_pids} if required_pids else {s.problem_id for s in subs}
    evaluated_pids = {
        s.problem_id
        for s in subs
        if s.status in TERMINAL_STATUSES and (not required_pids or s.problem_id in required_pids)
    }
    sub_count = len(submitted_pids)
    eval_count = len(evaluated_pids)
    latest_sub_at = subs[0].submitted_at if subs else None

    ast_rec = next((st for st in a.students if st.student_id == student_id), None)
    ast_raw_status = (ast_rec.status or "assigned").lower() if ast_rec else "assigned"

    if total_probs == 0:
        if not subs:
            status_label = "In Progress" if ast_raw_status == "in_progress" else "Pending"
        else:
            is_late = bool(a.deadline and latest_sub_at and latest_sub_at > a.deadline)
            if is_late:
                status_label = "Late"
            elif any(s.status in TERMINAL_STATUSES for s in subs):
                status_label = "Evaluated"
            else:
                status_label = "Submitted"
        progress_txt = "Submitted" if subs else "No problems attached"
    else:
        if sub_count == 0:
            status_label = "In Progress" if ast_raw_status == "in_progress" else "Pending"
        elif sub_count < total_probs:
            status_label = "In Progress"
        else:
            # All required problems have at least one submission
            is_late = bool(a.deadline and latest_sub_at and latest_sub_at > a.deadline)
            if is_late:
                status_label = "Late"
            elif eval_count >= total_probs:
                status_label = "Evaluated"
            else:
                status_label = "Submitted"
        progress_txt = f"{sub_count} of {total_probs} problem{'s' if total_probs != 1 else ''} submitted"

    return {
        "my_status": status_label,
        "submitted_problems_count": sub_count,
        "evaluated_problems_count": eval_count,
        "total_problems_count": total_probs,
        "progress_text": progress_txt,
        "my_submitted_at": latest_sub_at,
    }


def _build_assignment_response(
    a: Assignment,
    db: Optional[Session] = None,
    student_id: Optional[int] = None,
) -> AssignmentResponse:
    prob_list = [
        AssignedProblemInfo(
            problem_id=ap.problem.id,
            title=ap.problem.title,
            difficulty=ap.problem.difficulty,
            topic=ap.problem.topic,
            marks=ap.marks,
        )
        for ap in a.problems
        if ap.problem
    ]
    stud_list = []
    for ast in a.students:
        if not ast.student:
            continue
        computed_st = ast.status
        if db is not None:
            st_info = _compute_student_assignment_status(a, ast.student.id, db)
            computed_st = st_info["my_status"]
        stud_list.append(
            AssignedStudentInfo(
                id=ast.id,
                student_id=ast.student.id,
                name=ast.student.name,
                email=ast.student.email,
                status=computed_st,
                assigned_at=ast.assigned_at,
            )
        )

    my_info = (
        _compute_student_assignment_status(a, student_id, db)
        if (db is not None and student_id is not None)
        else {
            "my_status": None,
            "submitted_problems_count": 0,
            "evaluated_problems_count": 0,
            "total_problems_count": len(prob_list),
            "progress_text": f"0 of {len(prob_list)} problems submitted",
            "my_submitted_at": None,
        }
    )

    return AssignmentResponse(
        id=a.id,
        title=a.title,
        description=a.description,
        created_by=a.created_by,
        creator_name=a.creator.name if a.creator else "Instructor",
        start_date=a.start_date,
        deadline=a.deadline,
        allow_copy_paste=bool(getattr(a, "allow_copy_paste", True) if getattr(a, "allow_copy_paste", None) is not None else True),
        created_at=a.created_at,
        problems=prob_list,
        students=stud_list,
        my_status=my_info["my_status"],
        submitted_problems_count=my_info["submitted_problems_count"],
        evaluated_problems_count=my_info["evaluated_problems_count"],
        total_problems_count=my_info["total_problems_count"],
        progress_text=my_info["progress_text"],
        my_submitted_at=my_info["my_submitted_at"],
    )


@app.post("/assignments", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED, tags=["Assignments"])
def create_assignment(
    payload: AssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    payload.created_by = current_user.id

    new_assignment = Assignment(
        title=payload.title,
        description=payload.description,
        created_by=current_user.id,
        start_date=payload.start_date,
        deadline=payload.deadline,
        allow_copy_paste=bool(payload.allow_copy_paste if payload.allow_copy_paste is not None else True),
    )
    db.add(new_assignment)
    db.flush()

    seen_pids: set[int] = set()
    for pid in payload.problem_ids:
        if pid in seen_pids:
            continue
        seen_pids.add(pid)
        prob = db.query(Problem).filter(Problem.id == pid).first()
        if prob:
            ap = AssignmentProblem(assignment_id=new_assignment.id, problem_id=prob.id, marks=10.0)
            db.add(ap)

    seen_sids: set[int] = set()
    for sid in payload.student_ids:
        if sid in seen_sids:
            continue
        seen_sids.add(sid)
        student = db.query(User).filter(User.id == sid).first()
        if student:
            ast = AssignmentStudent(assignment_id=new_assignment.id, student_id=student.id, status="assigned")
            db.add(ast)

    db.commit()
    db.refresh(new_assignment)
    return _build_assignment_response(new_assignment, db=db)


@app.get("/assignments", response_model=List[AssignmentResponse], tags=["Assignments"])
def list_assignments(
    student_id: Optional[int] = Query(None),
    created_by: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Assignment)
    if created_by:
        query = query.filter(Assignment.created_by == created_by)
    if student_id:
        query = query.join(AssignmentStudent).filter(AssignmentStudent.student_id == student_id)

    assignments = query.order_by(desc(Assignment.created_at)).all()
    responses = [_build_assignment_response(a, db=db, student_id=student_id) for a in assignments]

    if search and search.strip():
        q = search.strip().lower().lstrip("#")
        filtered = []
        for r in responses:
            haystack = " ".join(
                [
                    str(r.id),
                    r.title or "",
                    r.description or "",
                    r.creator_name or "",
                    " ".join(p.title or "" for p in r.problems),
                    " ".join(p.topic or "" for p in r.problems),
                    " ".join(s.name or "" for s in r.students),
                    " ".join(s.email or "" for s in r.students),
                ]
            ).lower()
            if q in haystack:
                filtered.append(r)
        return filtered

    return responses


@app.get("/assignments/{assignment_id}", response_model=AssignmentResponse, tags=["Assignments"])
def get_assignment(
    assignment_id: int,
    student_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    a = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not a:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found.")
    return _build_assignment_response(a, db=db, student_id=student_id)


# =========================================================
# ACADEMIC PRACTICALS ENDPOINTS (Curriculum Practical Tracking)
# =========================================================

def _refresh_practical_student_status_from_submissions(
    p: AcademicPractical,
    ps: AcademicPracticalStudent,
    db: Session,
) -> None:
    """
    Ensure student practical status stays synchronized if they submitted a coding solution
    for the linked problem.
    """
    if not p.problem_id:
        return

    sub = None
    if ps.submission_id:
        sub = db.query(Submission).filter(Submission.id == ps.submission_id).first()
    if not sub:
        sub = (
            db.query(Submission)
            .filter(
                Submission.user_id == ps.student_id,
                Submission.problem_id == p.problem_id,
                (Submission.practical_id == p.id) | (Submission.submission_type == "practical"),
            )
            .order_by(desc(Submission.submitted_at), desc(Submission.id))
            .first()
        )
    if not sub:
        return

    changed = False
    if ps.submission_id != sub.id:
        ps.submission_id = sub.id
        changed = True
    if not ps.submitted_at and sub.submitted_at:
        ps.submitted_at = sub.submitted_at
        changed = True

    is_late = bool(p.deadline and ps.submitted_at and ps.submitted_at > p.deadline)
    if sub.status in TERMINAL_STATUSES:
        sub_max = get_submission_max_score(sub, db, problem=p.problem)
        scaled_marks = round((float(sub.score or 0.0) / max(sub_max, 1.0)) * float(p.max_marks or 10.0), 2)
        if ps.marks_obtained is None or scaled_marks > float(ps.marks_obtained or 0.0):
            ps.marks_obtained = scaled_marks
            changed = True
        if not ps.evaluated_at:
            ps.evaluated_at = sub.evaluated_at or datetime.utcnow()
            changed = True
        target_st = "Late Submission" if is_late else "Evaluated"
        if ps.status in ("Not Started", "In Progress", "Submitted"):
            ps.status = target_st
            changed = True
    else:
        target_st = "Late Submission" if is_late else "Submitted"
        if ps.status in ("Not Started", "In Progress"):
            ps.status = target_st
            changed = True

    if changed:
        db.flush()


def _build_practical_response(
    p: AcademicPractical,
    db: Session,
    *,
    student_id: Optional[int] = None,
    include_student_list: bool = True,
) -> AcademicPracticalResponse:
    stud_infos: List[AcademicPracticalStudentInfo] = []
    submitted_cnt = 0
    evaluated_cnt = 0
    late_cnt = 0
    pending_cnt = 0

    for ps in p.students:
        if not ps.student:
            continue
        _refresh_practical_student_status_from_submissions(p, ps, db)
        st = ps.status or "Not Started"
        if st in ("Submitted", "Evaluated", "Late Submission"):
            submitted_cnt += 1
        else:
            pending_cnt += 1
        if st == "Evaluated":
            evaluated_cnt += 1
        if st == "Late Submission":
            late_cnt += 1

        if include_student_list:
            stud_infos.append(
                AcademicPracticalStudentInfo(
                    id=ps.id,
                    practical_id=ps.practical_id,
                    student_id=ps.student_id,
                    student_name=ps.student.name,
                    student_email=ps.student.email,
                    assigned_at=ps.assigned_at,
                    submitted_at=ps.submitted_at,
                    evaluated_at=ps.evaluated_at,
                    status=st,
                    submission_id=ps.submission_id,
                    submission_notes=ps.submission_notes,
                    attachment_filename=ps.attachment_filename,
                    attachment_content_b64=None,
                    marks_obtained=ps.marks_obtained,
                    teacher_feedback=ps.teacher_feedback,
                )
            )

    stud_infos.sort(key=lambda x: x.student_name.lower())

    my_status = None
    my_submitted_at = None
    my_marks = None
    my_feedback = None
    my_sub_id = None
    my_notes = None
    my_fname = None

    if student_id is not None:
        mine = next((ps for ps in p.students if ps.student_id == student_id), None)
        if mine:
            my_status = mine.status or "Not Started"
            my_submitted_at = mine.submitted_at
            my_marks = mine.marks_obtained
            my_feedback = mine.teacher_feedback
            my_sub_id = mine.submission_id
            my_notes = mine.submission_notes
            my_fname = mine.attachment_filename
        else:
            my_status = "Not Started"

    return AcademicPracticalResponse(
        id=p.id,
        practical_number=p.practical_number,
        title=p.title,
        subject_name=p.subject_name,
        subject_code=p.subject_code,
        semester=p.semester,
        description=p.description,
        objectives=p.objectives,
        problem_id=p.problem_id,
        problem_title=p.problem.title if p.problem else None,
        problem_difficulty=p.problem.difficulty if p.problem else None,
        problem_topic=p.problem.topic if p.problem else None,
        start_date=p.start_date,
        deadline=p.deadline,
        max_marks=float(p.max_marks or 10.0),
        created_by=p.created_by,
        creator_name=p.creator.name if p.creator else "Faculty",
        created_at=p.created_at,
        updated_at=p.updated_at,
        assigned_count=len(p.students),
        submitted_count=submitted_cnt,
        evaluated_count=evaluated_cnt,
        pending_count=pending_cnt,
        late_count=late_cnt,
        students=stud_infos if include_student_list else [],
        my_status=my_status,
        my_submitted_at=my_submitted_at,
        my_marks_obtained=my_marks,
        my_teacher_feedback=my_feedback,
        my_submission_id=my_sub_id,
        my_submission_notes=my_notes,
        my_attachment_filename=my_fname,
    )


@app.post("/practicals", response_model=AcademicPracticalResponse, status_code=status.HTTP_201_CREATED, tags=["Academic Practicals"])
def create_academic_practical(
    payload: AcademicPracticalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    if payload.problem_id is not None:
        prob = db.query(Problem).filter(Problem.id == payload.problem_id).first()
        if not prob:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associated coding problem not found.")

    prac = AcademicPractical(
        practical_number=payload.practical_number,
        title=payload.title.strip(),
        subject_name=payload.subject_name.strip(),
        subject_code=payload.subject_code.strip() if payload.subject_code else None,
        semester=payload.semester.strip() if payload.semester else None,
        description=payload.description.strip() if payload.description else None,
        objectives=payload.objectives.strip() if payload.objectives else None,
        problem_id=payload.problem_id,
        start_date=payload.start_date,
        deadline=payload.deadline,
        max_marks=float(payload.max_marks or 10.0),
        created_by=current_user.id,
    )
    db.add(prac)
    db.flush()

    seen_sids: set[int] = set()
    for sid in payload.student_ids:
        if sid in seen_sids:
            continue
        seen_sids.add(sid)
        stu = db.query(User).filter(User.id == sid, User.role == "student").first()
        if stu:
            db.add(
                AcademicPracticalStudent(
                    practical_id=prac.id,
                    student_id=stu.id,
                    status="Not Started",
                )
            )

    db.commit()
    db.refresh(prac)
    return _build_practical_response(prac, db, include_student_list=True)


@app.post("/practicals/assign", response_model=List[AcademicPracticalResponse], tags=["Academic Practicals"])
def bulk_assign_practicals(
    payload: AcademicPracticalBulkAssign,
    db: Session = Depends(get_db),
    _teacher: User = Depends(require_teacher),
):
    """
    Assign one or more existing academic practicals to selected students (or all enrolled students),
    optionally updating deadline and instructions, while preventing duplicate student assignments.
    """
    updated_practicals: List[AcademicPractical] = []
    valid_students = (
        db.query(User)
        .filter(User.id.in_(payload.student_ids), User.role == "student")
        .all()
    )
    if not valid_students:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid student IDs supplied.")

    for pid in payload.practical_ids:
        prac = db.query(AcademicPractical).filter(AcademicPractical.id == pid).first()
        if not prac:
            continue
        if payload.deadline is not None:
            prac.deadline = payload.deadline
        if payload.objectives is not None and payload.objectives.strip():
            prac.objectives = payload.objectives.strip()

        existing_sids = {ps.student_id for ps in prac.students}
        for stu in valid_students:
            if stu.id not in existing_sids:
                db.add(
                    AcademicPracticalStudent(
                        practical_id=prac.id,
                        student_id=stu.id,
                        status="Not Started",
                    )
                )
                existing_sids.add(stu.id)
        updated_practicals.append(prac)

    db.commit()
    for p in updated_practicals:
        db.refresh(p)
    return [_build_practical_response(p, db, include_student_list=True) for p in updated_practicals]


@app.get("/practicals", response_model=List[AcademicPracticalResponse], tags=["Academic Practicals"])
def list_academic_practicals(
    student_id: Optional[int] = Query(None),
    subject_name: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    is_teacher = current_user.role in ("teacher", "admin")
    query = db.query(AcademicPractical)

    if not is_teacher:
        target_sid = current_user.id
        query = query.join(AcademicPracticalStudent).filter(AcademicPracticalStudent.student_id == target_sid)
    elif student_id is not None:
        target_sid = student_id
        query = query.join(AcademicPracticalStudent).filter(AcademicPracticalStudent.student_id == target_sid)
    else:
        target_sid = None

    if subject_name and subject_name.strip():
        query = query.filter(AcademicPractical.subject_name.ilike(f"%{subject_name.strip()}%"))

    practicals = query.order_by(AcademicPractical.practical_number.asc(), desc(AcademicPractical.created_at)).all()
    responses = [
        _build_practical_response(
            p,
            db,
            student_id=target_sid,
            include_student_list=is_teacher,
        )
        for p in practicals
    ]
    db.commit()

    if search and search.strip():
        q = search.strip().lower().lstrip("#")
        filtered = []
        for r in responses:
            haystack = " ".join(
                [
                    str(r.id),
                    f"practical {r.practical_number}",
                    str(r.practical_number),
                    r.title or "",
                    r.subject_name or "",
                    r.subject_code or "",
                    r.semester or "",
                    r.description or "",
                    r.objectives or "",
                    r.problem_title or "",
                    " ".join(s.student_name or "" for s in r.students),
                ]
            ).lower()
            if q in haystack:
                filtered.append(r)
        return filtered

    return responses


@app.get("/practicals/{practical_id}", response_model=AcademicPracticalResponse, tags=["Academic Practicals"])
def get_academic_practical(
    practical_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prac = db.query(AcademicPractical).filter(AcademicPractical.id == practical_id).first()
    if not prac:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Academic practical not found.")
    is_teacher = current_user.role in ("teacher", "admin")
    res = _build_practical_response(
        prac,
        db,
        student_id=None if is_teacher else current_user.id,
        include_student_list=is_teacher,
    )
    db.commit()
    return res


@app.post("/practicals/{practical_id}/start", response_model=AcademicPracticalResponse, tags=["Academic Practicals"])
def start_academic_practical(
    practical_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prac = db.query(AcademicPractical).filter(AcademicPractical.id == practical_id).first()
    if not prac:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Academic practical not found.")

    rec = (
        db.query(AcademicPracticalStudent)
        .filter(
            AcademicPracticalStudent.practical_id == practical_id,
            AcademicPracticalStudent.student_id == current_user.id,
        )
        .first()
    )
    if not rec:
        rec = AcademicPracticalStudent(
            practical_id=practical_id,
            student_id=current_user.id,
            status="In Progress",
        )
        db.add(rec)
    elif rec.status == "Not Started":
        rec.status = "In Progress"

    db.commit()
    db.refresh(prac)
    return _build_practical_response(prac, db, student_id=current_user.id, include_student_list=False)


@app.post("/practicals/{practical_id}/submit", response_model=AcademicPracticalResponse, tags=["Academic Practicals"])
def submit_academic_practical(
    practical_id: int,
    payload: AcademicPracticalStudentSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Submit an academic practical (manual completion report / file attachment or linked coding submission).
    """
    prac = db.query(AcademicPractical).filter(AcademicPractical.id == practical_id).first()
    if not prac:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Academic practical not found.")

    rec = (
        db.query(AcademicPracticalStudent)
        .filter(
            AcademicPracticalStudent.practical_id == practical_id,
            AcademicPracticalStudent.student_id == current_user.id,
        )
        .first()
    )
    now = datetime.utcnow()
    is_late = bool(prac.deadline and now > prac.deadline)

    if not rec:
        rec = AcademicPracticalStudent(
            practical_id=practical_id,
            student_id=current_user.id,
            assigned_at=now,
        )
        db.add(rec)

    if payload.submission_notes is not None:
        rec.submission_notes = payload.submission_notes.strip()
    if payload.attachment_filename:
        rec.attachment_filename = _sanitize_dataset_filename(payload.attachment_filename)
    if payload.attachment_content_b64:
        rec.attachment_content_b64 = payload.attachment_content_b64
    if payload.submission_id is not None:
        sub = (
            db.query(Submission)
            .filter(Submission.id == payload.submission_id, Submission.user_id == current_user.id)
            .first()
        )
        if sub:
            rec.submission_id = sub.id
            sub.practical_id = prac.id
            if sub.status in TERMINAL_STATUSES:
                sub_max = get_submission_max_score(sub, db, problem=prac.problem)
                rec.marks_obtained = round((float(sub.score or 0.0) / max(sub_max, 1.0)) * float(prac.max_marks or 10.0), 2)
                rec.evaluated_at = sub.evaluated_at or now

    rec.submitted_at = now
    if is_late:
        rec.status = "Late Submission"
    elif rec.evaluated_at is not None:
        rec.status = "Evaluated"
    else:
        rec.status = "Submitted"

    db.commit()
    db.refresh(prac)
    return _build_practical_response(prac, db, student_id=current_user.id, include_student_list=False)


@app.post(
    "/practicals/{practical_id}/students/{student_id}/evaluate",
    response_model=AcademicPracticalResponse,
    tags=["Academic Practicals"],
)
def evaluate_student_practical(
    practical_id: int,
    student_id: int,
    payload: AcademicPracticalEvaluateRequest,
    db: Session = Depends(get_db),
    _teacher: User = Depends(require_teacher),
):
    prac = db.query(AcademicPractical).filter(AcademicPractical.id == practical_id).first()
    if not prac:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Academic practical not found.")

    rec = (
        db.query(AcademicPracticalStudent)
        .filter(
            AcademicPracticalStudent.practical_id == practical_id,
            AcademicPracticalStudent.student_id == student_id,
        )
        .first()
    )
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student assignment record not found for this practical.")

    rec.status = payload.status
    if payload.marks_obtained is not None:
        rec.marks_obtained = min(float(payload.marks_obtained), float(prac.max_marks or 100.0))
    if payload.teacher_feedback is not None:
        rec.teacher_feedback = payload.teacher_feedback.strip()
    if payload.status == "Evaluated":
        rec.evaluated_at = datetime.utcnow()

    db.commit()
    db.refresh(prac)
    return _build_practical_response(prac, db, include_student_list=True)


# =========================================================
# CODING TEST ENDPOINTS
# =========================================================

def _build_coding_test_response(t: CodingTest, student_id: Optional[int] = None) -> CodingTestResponse:
    prob_list = [
        AssignedProblemInfo(
            problem_id=ctp.problem.id,
            title=ctp.problem.title,
            difficulty=ctp.problem.difficulty,
            topic=ctp.problem.topic,
            marks=ctp.marks,
        )
        for ctp in t.problems
        if ctp.problem
    ]
    enrolled = len(t.students)
    completed = sum(1 for s in t.students if s.status in ("submitted", "completed"))
    my_status = None
    my_score = None
    xp_awarded = False
    xp_awarded_amount = 0
    xp_awarded_at = None

    if student_id is not None:
        mine = next((s for s in t.students if s.student_id == student_id), None)
        my_status = mine.status if mine else "not_started"
        my_score = round(float(mine.score or 0.0), 2) if mine else 0.0
        if mine:
            xp_awarded = bool(getattr(mine, "xp_awarded", False))
            xp_awarded_amount = int(getattr(mine, "xp_awarded_amount", 0) or 0)
            xp_awarded_at = getattr(mine, "xp_awarded_at", None)

    return CodingTestResponse(
        id=t.id,
        title=t.title,
        description=t.description,
        created_by=t.created_by,
        creator_name=t.creator.name if t.creator else "Faculty",
        duration=t.duration or 60,
        start_time=t.start_time,
        end_time=t.end_time,
        allow_copy_paste=bool(getattr(t, "allow_copy_paste", False) if getattr(t, "allow_copy_paste", None) is not None else False),
        created_at=t.created_at,
        problems=prob_list,
        enrolled_count=enrolled,
        completed_count=completed,
        my_status=my_status,
        my_score=my_score,
        xp_reward=10,
        xp_awarded=xp_awarded,
        xp_awarded_amount=xp_awarded_amount,
        xp_awarded_at=xp_awarded_at,
    )


@app.post("/coding-tests", response_model=CodingTestResponse, status_code=status.HTTP_201_CREATED, tags=["Coding Tests"])
def create_coding_test(
    payload: CodingTestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    payload.created_by = current_user.id

    new_test = CodingTest(
        title=payload.title,
        description=payload.description,
        created_by=current_user.id,
        duration=payload.duration,
        start_time=payload.start_time,
        end_time=payload.end_time,
        allow_copy_paste=bool(payload.allow_copy_paste if payload.allow_copy_paste is not None else False),
    )
    db.add(new_test)
    db.flush()

    for pid in payload.problem_ids:
        prob = db.query(Problem).filter(Problem.id == pid).first()
        if prob:
            ctp = CodingTestProblem(coding_test_id=new_test.id, problem_id=prob.id, marks=10.0)
            db.add(ctp)

    if payload.custom_problems:
        for cp in payload.custom_problems:
            if not cp.title or not cp.description:
                continue
            new_custom_prob = Problem(
                title=cp.title.strip(),
                description=cp.description.strip(),
                difficulty=cp.difficulty or "Medium",
                topic=cp.topic.strip() if cp.topic else "Assessment",
                constraints=cp.constraints.strip() if cp.constraints else None,
                examples=cp.examples.strip() if cp.examples else None,
                created_by=current_user.id,
            )
            db.add(new_custom_prob)
            db.flush()

            if cp.sample_input or cp.sample_output:
                new_tc = TestCase(
                    problem_id=new_custom_prob.id,
                    input=cp.sample_input.strip() if cp.sample_input else "",
                    expected_output=cp.sample_output.strip() if cp.sample_output else "",
                    is_hidden=False,
                )
                db.add(new_tc)

            if cp.hidden_input or cp.hidden_output:
                hidden_tc = TestCase(
                    problem_id=new_custom_prob.id,
                    input=cp.hidden_input.strip() if cp.hidden_input else "",
                    expected_output=cp.hidden_output.strip() if cp.hidden_output else "",
                    is_hidden=True,
                )
                db.add(hidden_tc)

            ctp = CodingTestProblem(coding_test_id=new_test.id, problem_id=new_custom_prob.id, marks=10.0)
            db.add(ctp)

    db.commit()
    db.refresh(new_test)
    return _build_coding_test_response(new_test)


@app.get("/coding-tests", response_model=List[CodingTestResponse], tags=["Coding Tests"])
def list_coding_tests(
    student_id: Optional[int] = Query(None, description="Include this student's status as my_status"),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    tests = db.query(CodingTest).order_by(desc(CodingTest.created_at)).all()
    responses = [_build_coding_test_response(t, student_id) for t in tests]

    if search and search.strip():
        q = search.strip().lower().lstrip("#")
        filtered = []
        for r in responses:
            haystack = " ".join(
                [
                    str(r.id),
                    r.title or "",
                    r.description or "",
                    r.creator_name or "",
                    " ".join(p.title or "" for p in r.problems),
                    " ".join(p.topic or "" for p in r.problems),
                ]
            ).lower()
            if q in haystack:
                filtered.append(r)
        return filtered

    return responses


@app.get("/coding-tests/{test_id}", response_model=CodingTestResponse, tags=["Coding Tests"])
def get_coding_test(
    test_id: int,
    student_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    t = db.query(CodingTest).filter(CodingTest.id == test_id).first()
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coding test not found.")
    return _build_coding_test_response(t, student_id=student_id)


@app.post("/coding-tests/{test_id}/complete", tags=["Coding Tests"])
def complete_coding_test(
    test_id: int,
    student_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Finalize a coding test session for the authenticated student.
    Awards the +10 XP test completion reward exactly once per student per test
    when completion criteria are met, preventing duplicate awards on retries/refreshes.
    """
    if student_id is not None and student_id != current_user.id:
        if current_user.role not in ("teacher", "admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot complete a coding test on behalf of another student.",
            )
        target_student_id = student_id
    else:
        target_student_id = current_user.id

    test = db.query(CodingTest).filter(CodingTest.id == test_id).first()
    if not test:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coding test not found.")

    evaluated_score = recompute_coding_test_student_score(test_id, target_student_id, db)

    pending_count = (
        db.query(Submission)
        .filter(
            Submission.coding_test_id == test_id,
            Submission.user_id == target_student_id,
            Submission.submission_type == "coding_test",
            ~Submission.status.in_(TERMINAL_STATUSES),
        )
        .count()
    )

    record = (
        db.query(CodingTestStudent)
        .filter(
            CodingTestStudent.coding_test_id == test_id,
            CodingTestStudent.student_id == target_student_id,
        )
        .first()
    )
    now = datetime.utcnow()
    already_awarded = bool(record and getattr(record, "xp_awarded", False))

    if record:
        record.status = "completed"
        if not record.submitted_at:
            record.submitted_at = now
        record.score = evaluated_score
    else:
        record = CodingTestStudent(
            coding_test_id=test_id,
            student_id=target_student_id,
            started_at=now,
            submitted_at=now,
            status="completed",
            score=evaluated_score,
            xp_awarded=False,
            xp_awarded_amount=0,
        )
        db.add(record)

    # Award +10 XP exactly once when the test is completed and no submissions are stuck pending
    if not already_awarded and pending_count == 0:
        record.xp_awarded = True
        record.xp_awarded_amount = 10
        record.xp_awarded_at = now

    max_test_score = round(sum(float(ctp.marks or 10.0) for ctp in test.problems), 2)
    db.commit()
    db.refresh(record)
    student_stats = _compute_student_xp_and_stats(target_student_id, db)
    return {
        "message": (
            f"Test submitted! Evaluated score so far: {evaluated_score}/{max_test_score} pts "
            f"({pending_count} submission(s) still being graded)."
            if pending_count > 0
            else f"Test completed! +10 XP Awarded • Final evaluated score: {evaluated_score}/{max_test_score} pts."
        ),
        "test_id": test_id,
        "student_id": target_student_id,
        "status": record.status,
        "score": evaluated_score,
        "max_score": max_test_score,
        "xp_awarded": bool(record.xp_awarded),
        "xp_awarded_amount": int(record.xp_awarded_amount or 0),
        "xp_awarded_at": record.xp_awarded_at,
        "test_xp": int(record.xp_awarded_amount or round(evaluated_score)),
        "xp": student_stats["xp"],
        "pending_submissions": pending_count,
    }


# =========================================================
# SCORING, XP & LEADERBOARD LOGIC
# =========================================================

COMPLETED_TEST_STATUSES = ("submitted", "completed")
XP_PER_PROBLEM = 10.0


def _compute_student_xp_and_stats(stu_id: int, db: Session) -> dict:
    """
    Compute a student's XP and progress metrics deterministically from actual
    evaluated submissions and completed coding tests in the database:
      - Practice / Assignment / Practical problems: up to 10 XP per unique problem based on the
        student's highest evaluated pass ratio (`passed_count / total_count`).
      - Coding Tests: awards the persisted CodingTestStudent XP reward (`xp_awarded_amount`, default 10 XP)
        once per completed test, or the student's evaluated coding-test score if higher.
      - Unevaluated (`Pending Evaluation` / `Running`) or merely opened tests (`in_progress`) award 0 XP.
      - Repeated submissions or repeated `/complete` calls never award duplicate XP.
    """
    eval_subs = (
        db.query(Submission)
        .filter(
            Submission.user_id == stu_id,
            Submission.status.in_(TERMINAL_STATUSES),
        )
        .all()
    )

    best_practice_ratio: dict[int, float] = {}
    best_test_score_by_prob: dict[tuple[int, int], float] = {}
    solved_problems: set[int] = set()

    for s in eval_subs:
        if s.status == STATUS_ACCEPTED:
            solved_problems.add(s.problem_id)

        if s.submission_type == "coding_test" and s.coding_test_id:
            key = (s.coding_test_id, s.problem_id)
            score_val = float(s.score or 0.0)
            if score_val > best_test_score_by_prob.get(key, 0.0):
                best_test_score_by_prob[key] = score_val
        else:
            if s.total_count and s.total_count > 0 and s.passed_count and s.passed_count > 0:
                ratio = min(1.0, float(s.passed_count) / float(s.total_count))
            elif s.status == STATUS_ACCEPTED:
                ratio = 1.0
            else:
                ratio = 0.0
            if ratio > best_practice_ratio.get(s.problem_id, 0.0):
                best_practice_ratio[s.problem_id] = ratio

    practice_xp = sum(XP_PER_PROBLEM * r for r in best_practice_ratio.values())

    eval_score_per_test: dict[int, float] = defaultdict(float)
    for (tid, _pid), sc in best_test_score_by_prob.items():
        eval_score_per_test[tid] += sc

    completed_test_rows = (
        db.query(CodingTestStudent)
        .filter(
            CodingTestStudent.student_id == stu_id,
            CodingTestStudent.status.in_(COMPLETED_TEST_STATUSES),
        )
        .all()
    )

    awarded_test_xp_by_test: dict[int, float] = {}
    for tid, sc in eval_score_per_test.items():
        awarded_test_xp_by_test[tid] = sc

    for cts in completed_test_rows:
        if getattr(cts, "xp_awarded", False):
            amt = float(getattr(cts, "xp_awarded_amount", 10) or 10)
            awarded_test_xp_by_test[cts.coding_test_id] = max(
                awarded_test_xp_by_test.get(cts.coding_test_id, 0.0),
                amt,
            )

    test_xp = sum(awarded_test_xp_by_test.values())
    total_xp = int(round(practice_xp + test_xp))
    tests_done = len({cts.coding_test_id for cts in completed_test_rows})

    return {
        "xp": total_xp,
        "tests_completed": tests_done,
        "problems_solved": len(solved_problems),
    }


@app.get("/leaderboard", response_model=List[LeaderboardEntry], tags=["Leaderboard"])
def get_leaderboard(db: Session = Depends(get_db)):
    students = db.query(User).filter(User.role == "student").all()
    results = []

    for stu in students:
        stats = _compute_student_xp_and_stats(stu.id, db)
        results.append(
            {
                "user_id": stu.id,
                "name": stu.name,
                "email": stu.email,
                "role": stu.role,
                "tests_completed": stats["tests_completed"],
                "problems_solved": stats["problems_solved"],
                "xp": stats["xp"],
            }
        )

    results.sort(key=lambda x: (x["xp"], x["problems_solved"], x["tests_completed"]), reverse=True)

    return [
        LeaderboardEntry(
            rank=idx,
            user_id=entry["user_id"],
            name=entry["name"],
            email=entry["email"],
            role=entry["role"],
            tests_completed=entry["tests_completed"],
            problems_solved=entry["problems_solved"],
            xp=entry["xp"],
        )
        for idx, entry in enumerate(results, start=1)
    ]


# =========================================================
# ROLE-BASED DASHBOARD ENDPOINTS
# =========================================================

def _student_progress(stu: User, db: Session) -> StudentProgress:
    stats = _compute_student_xp_and_stats(stu.id, db)
    subs_q = db.query(Submission).filter(Submission.user_id == stu.id)
    total_subs = subs_q.count()
    accepted = subs_q.filter(Submission.status == STATUS_ACCEPTED).count()
    attempted = (
        db.query(func.count(func.distinct(Submission.problem_id)))
        .filter(Submission.user_id == stu.id)
        .scalar()
        or 0
    )
    last_sub = subs_q.order_by(desc(Submission.submitted_at)).first()
    assigned = db.query(AssignmentStudent).filter(AssignmentStudent.student_id == stu.id).count()

    return StudentProgress(
        user_id=stu.id,
        name=stu.name,
        email=stu.email,
        joined_at=stu.created_at,
        xp=stats["xp"],
        tests_completed=stats["tests_completed"],
        problems_solved=stats["problems_solved"],
        total_submissions=total_subs,
        accepted_submissions=accepted,
        problems_attempted=attempted,
        assignments_assigned=assigned,
        last_active=last_sub.submitted_at if last_sub else None,
    )


@app.get("/teacher/overview", response_model=TeacherOverview, tags=["Teacher Dashboard"])
def teacher_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    students = db.query(User).filter(User.role == "student").all()
    total_students = len(students)
    total_tests = db.query(CodingTest).count()

    completed_pairs = (
        db.query(CodingTestStudent)
        .filter(CodingTestStudent.status.in_(COMPLETED_TEST_STATUSES))
        .count()
    )
    possible_pairs = total_students * total_tests
    completion_rate = round((completed_pairs / possible_pairs) * 100, 1) if possible_pairs else 0.0

    difficulty_breakdown = {
        level: db.query(Problem).filter(Problem.difficulty == level).count()
        for level in ("Easy", "Medium", "Hard")
    }

    week_ago = datetime.utcnow() - timedelta(days=7)
    recent = db.query(Submission).order_by(desc(Submission.submitted_at), desc(Submission.id)).limit(8).all()

    progress = [_student_progress(s, db) for s in students]
    progress.sort(key=lambda p: (p.xp, p.problems_solved, p.total_submissions), reverse=True)

    return TeacherOverview(
        total_students=total_students,
        total_teachers=db.query(User).filter(User.role.in_(["teacher", "admin"])).count(),
        total_problems=db.query(Problem).count(),
        my_problems=db.query(Problem).filter(Problem.created_by == current_user.id).count(),
        total_assignments=db.query(Assignment).count(),
        my_assignments=db.query(Assignment).filter(Assignment.created_by == current_user.id).count(),
        total_coding_tests=total_tests,
        my_coding_tests=db.query(CodingTest).filter(CodingTest.created_by == current_user.id).count(),
        total_submissions=db.query(Submission).count(),
        submissions_last_7_days=db.query(Submission).filter(Submission.submitted_at >= week_ago).count(),
        test_completion_rate=completion_rate,
        difficulty_breakdown=difficulty_breakdown,
        recent_submissions=[_submission_to_response(s, db, include_details=False, is_teacher=True) for s in recent],
        top_students=progress[:5],
    )


@app.get("/teacher/students", response_model=List[StudentProgress], tags=["Teacher Dashboard"])
def teacher_student_roster(
    db: Session = Depends(get_db),
    _teacher: User = Depends(require_teacher),
):
    students = db.query(User).filter(User.role == "student").order_by(User.name).all()
    return [_student_progress(s, db) for s in students]


@app.get("/student/overview", response_model=StudentOverview, tags=["Student Dashboard"])
def student_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("student")),
):
    me = _student_progress(current_user, db)

    ranking = [_student_progress(s, db) for s in db.query(User).filter(User.role == "student").all()]
    ranking.sort(key=lambda p: (p.xp, p.problems_solved, p.tests_completed), reverse=True)
    rank = next((idx for idx, p in enumerate(ranking, start=1) if p.user_id == current_user.id), None)

    my_assignments = (
        db.query(Assignment)
        .join(AssignmentStudent)
        .filter(AssignmentStudent.student_id == current_user.id)
        .all()
    )
    now = datetime.utcnow()
    # Sort upcoming deadlines first, followed by past deadlines or open-ended assignments
    sorted_assignments = sorted(
        my_assignments,
        key=lambda a: (
            0 if (a.deadline is not None and a.deadline >= now) else (1 if a.deadline is None else 2),
            a.deadline or now,
        ),
    )[:8]

    tests = db.query(CodingTest).order_by(desc(CodingTest.created_at)).all()
    test_responses = [_build_coding_test_response(t, current_user.id) for t in tests]
    pending_tests = [t for t in test_responses if t.my_status not in COMPLETED_TEST_STATUSES][:5]

    recent = (
        db.query(Submission)
        .filter(Submission.user_id == current_user.id)
        .order_by(desc(Submission.submitted_at), desc(Submission.id))
        .limit(5)
        .all()
    )

    return StudentOverview(
        xp=me.xp,
        rank=rank,
        total_ranked=len(ranking),
        tests_completed=me.tests_completed,
        tests_available=len(tests),
        problems_solved=me.problems_solved,
        total_submissions=me.total_submissions,
        accepted_submissions=me.accepted_submissions,
        problems_attempted=me.problems_attempted,
        total_problems=db.query(Problem).count(),
        assignments_assigned=len(my_assignments),
        upcoming_deadlines=[_build_assignment_response(a, db=db, student_id=current_user.id) for a in sorted_assignments],
        pending_tests=pending_tests,
        recent_submissions=[_submission_to_response(s, db, include_details=False, is_teacher=False) for s in recent],
    )
