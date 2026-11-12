from collections import defaultdict
from datetime import datetime, timedelta
import json
import os
import threading
import time
from typing import List, Optional
import urllib.error
import urllib.request

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
    SUPPORTED_LANGUAGES,
    TERMINAL_STATUSES,
    normalize_language,
)
from app.grading.worker import (
    evaluate_submission_by_id,
    execute_sample_cases,
    get_submission_max_score,
    recompute_coding_test_student_score,
)
from app.models import (
    Assignment,
    AssignmentProblem,
    AssignmentStudent,
    CodingTest,
    CodingTestProblem,
    CodingTestStudent,
    Problem,
    Submission,
    SubmissionResult,
    TestCase,
    User,
)
from app.schemas import (
    AssignedProblemInfo,
    AssignedStudentInfo,
    AssignmentCreate,
    AssignmentResponse,
    AuthResponse,
    CodingTestCreate,
    CodingTestResponse,
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
    StudentOverview,
    StudentProgress,
    SubmissionCreate,
    SubmissionResponse,
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
        if alter_stmts:
            with engine.begin() as conn:
                for stmt in alter_stmts:
                    conn.execute(text(f"ALTER TABLE submissions {stmt}"))


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
# PROBLEM ENDPOINTS (WITH HIDDEN TEST CASE PROTECTION)
# =========================================================

def _build_public_problem_response(p: Problem) -> ProblemResponse:
    """
    Build a ProblemResponse containing ONLY public (`is_hidden == False`) test cases.
    Hidden test case inputs and expected outputs are never included.
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
        created_by=p.created_by,
        created_at=p.created_at,
        updated_at=p.updated_at,
        test_cases=public_tcs,
        hidden_test_count=hidden_count,
    )


@app.post("/problems", response_model=ProblemResponse, status_code=status.HTTP_201_CREATED, tags=["Problems"])
def create_problem(
    problem: ProblemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    problem.created_by = current_user.id

    new_problem = Problem(
        title=problem.title,
        description=problem.description,
        difficulty=problem.difficulty,
        topic=problem.topic,
        input_format=problem.input_format,
        output_format=problem.output_format,
        constraints=problem.constraints,
        examples=problem.examples,
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

    db.commit()
    db.refresh(new_problem)
    return _build_public_problem_response(new_problem)


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
    max_score = get_submission_max_score(s, db)

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

    return SubmissionResponse(
        id=s.id,
        user_id=s.user_id,
        user_name=u_name,
        problem_id=s.problem_id,
        code=s.code,
        language=s.language,
        status=s.status,
        score=round(float(s.score or 0.0), 2),
        max_score=max_score,
        passed_count=passed_count,
        total_count=total_count,
        execution_time=s.execution_time,
        memory_used=s.memory_used,
        error_message=s.error_message,
        submitted_at=s.submitted_at,
        evaluated_at=s.evaluated_at,
        attempt_count=s.attempt_count or 0,
        submission_type=s.submission_type,
        assignment_id=s.assignment_id,
        coding_test_id=s.coding_test_id,
        competition_id=s.competition_id,
        problem_title=p_title,
        public_results=public_results,
        hidden_summary=hidden_summary,
        teacher_hidden_results=teacher_hidden_results,
    )


@app.post("/submissions/run-samples", response_model=RunSamplesResponse, tags=["Submissions"])
def run_problem_samples(
    payload: RunSamplesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Execute student code against ONLY the public sample test cases of a problem.
    Never loads or executes hidden test cases, never creates a graded submission,
    and never awards XP.
    """
    _check_sample_rate_limit(current_user.id)

    norm_lang = normalize_language(payload.language)
    if not norm_lang:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported language '{payload.language}'. Supported: {', '.join(SUPPORTED_LANGUAGES)}.",
        )

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

    tc_dicts = [
        {"id": tc.id, "input": tc.input, "expected_output": tc.expected_output}
        for tc in public_tcs
    ]

    # Delegate execution to the isolated grader worker over internal network when configured
    if GRADER_URL:
        try:
            req_body = json.dumps(
                {
                    "problem_id": problem.id,
                    "language": norm_lang,
                    "code": payload.code,
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
            with urllib.request.urlopen(req, timeout=30) as resp:
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
        code=payload.code,
        public_test_cases=tc_dicts,
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
        ]
    )

    if sub.submission_type == "practice":
        if context_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Practice submissions must not have assignment, coding test, or competition context IDs.",
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

    total_tcs = len(problem.test_cases) if problem.test_cases else 0

    new_sub = Submission(
        user_id=target_user_id,
        problem_id=sub.problem_id,
        code=sub.code,
        language=norm_lang,
        status=STATUS_PENDING,
        score=0.0,
        passed_count=0,
        total_count=total_tcs,
        submission_type=sub.submission_type,
        assignment_id=sub.assignment_id,
        coding_test_id=sub.coding_test_id,
        competition_id=sub.competition_id,
    )
    db.add(new_sub)

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
            )
            db.add(record)

    db.commit()
    db.refresh(new_sub)

    # When running outside Docker without a separate `grader` service, optionally
    # trigger background evaluation so non-Docker local runs also evaluate automatically.
    if not GRADER_URL and INLINE_GRADING_FALLBACK:
        threading.Thread(target=evaluate_submission_by_id, args=(new_sub.id,), daemon=True).start()

    return _submission_to_response(new_sub, db, include_details=True, is_teacher=current_user.role in ("teacher", "admin"))


@app.get("/submissions", response_model=List[SubmissionResponse], tags=["Submissions"])
def list_submissions(
    user_id: Optional[int] = Query(None),
    problem_id: Optional[int] = Query(None),
    submission_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
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
        query = query.filter(Submission.user_id == current_user.id)
    elif user_id is not None:
        query = query.filter(Submission.user_id == user_id)

    if problem_id:
        query = query.filter(Submission.problem_id == problem_id)
    if submission_type:
        query = query.filter(Submission.submission_type == submission_type)

    submissions = query.order_by(desc(Submission.submitted_at), desc(Submission.id)).offset(skip).limit(limit).all()
    return [_submission_to_response(s, db, include_details=False, is_teacher=is_teacher) for s in submissions]


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

def _build_assignment_response(a: Assignment) -> AssignmentResponse:
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
    stud_list = [
        AssignedStudentInfo(
            id=ast.id,
            student_id=ast.student.id,
            name=ast.student.name,
            email=ast.student.email,
            status=ast.status,
            assigned_at=ast.assigned_at,
        )
        for ast in a.students
        if ast.student
    ]
    return AssignmentResponse(
        id=a.id,
        title=a.title,
        description=a.description,
        created_by=a.created_by,
        creator_name=a.creator.name if a.creator else "Instructor",
        start_date=a.start_date,
        deadline=a.deadline,
        created_at=a.created_at,
        problems=prob_list,
        students=stud_list,
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
    )
    db.add(new_assignment)
    db.flush()

    for pid in payload.problem_ids:
        prob = db.query(Problem).filter(Problem.id == pid).first()
        if prob:
            ap = AssignmentProblem(assignment_id=new_assignment.id, problem_id=prob.id, marks=10.0)
            db.add(ap)

    for sid in payload.student_ids:
        student = db.query(User).filter(User.id == sid).first()
        if student:
            ast = AssignmentStudent(assignment_id=new_assignment.id, student_id=student.id, status="assigned")
            db.add(ast)

    db.commit()
    db.refresh(new_assignment)
    return _build_assignment_response(new_assignment)


@app.get("/assignments", response_model=List[AssignmentResponse], tags=["Assignments"])
def list_assignments(
    student_id: Optional[int] = Query(None),
    created_by: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Assignment)
    if created_by:
        query = query.filter(Assignment.created_by == created_by)
    if student_id:
        query = query.join(AssignmentStudent).filter(AssignmentStudent.student_id == student_id)

    assignments = query.order_by(desc(Assignment.created_at)).all()
    return [_build_assignment_response(a) for a in assignments]


@app.get("/assignments/{assignment_id}", response_model=AssignmentResponse, tags=["Assignments"])
def get_assignment(assignment_id: int, db: Session = Depends(get_db)):
    a = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not a:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found.")
    return _build_assignment_response(a)


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
    if student_id is not None:
        mine = next((s for s in t.students if s.student_id == student_id), None)
        my_status = mine.status if mine else "not_started"
        my_score = round(float(mine.score or 0.0), 2) if mine else 0.0
    return CodingTestResponse(
        id=t.id,
        title=t.title,
        description=t.description,
        created_by=t.created_by,
        creator_name=t.creator.name if t.creator else "Faculty",
        duration=t.duration or 60,
        start_time=t.start_time,
        end_time=t.end_time,
        created_at=t.created_at,
        problems=prob_list,
        enrolled_count=enrolled,
        completed_count=completed,
        my_status=my_status,
        my_score=my_score,
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
    db: Session = Depends(get_db),
):
    tests = db.query(CodingTest).order_by(desc(CodingTest.created_at)).all()
    return [_build_coding_test_response(t, student_id) for t in tests]


@app.get("/coding-tests/{test_id}", response_model=CodingTestResponse, tags=["Coding Tests"])
def get_coding_test(test_id: int, db: Session = Depends(get_db)):
    t = db.query(CodingTest).filter(CodingTest.id == test_id).first()
    if not t:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coding test not found.")
    return _build_coding_test_response(t)


@app.post("/coding-tests/{test_id}/complete", tags=["Coding Tests"])
def complete_coding_test(
    test_id: int,
    student_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Finalize a coding test session for the authenticated student.
    Score and XP are computed strictly from evaluated coding-test submissions
    (never awarded merely for clicking Complete).
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

    record = (
        db.query(CodingTestStudent)
        .filter(
            CodingTestStudent.coding_test_id == test_id,
            CodingTestStudent.student_id == target_student_id,
        )
        .first()
    )
    if record:
        record.status = "submitted"
        record.submitted_at = datetime.utcnow()
        record.score = evaluated_score
    else:
        record = CodingTestStudent(
            coding_test_id=test_id,
            student_id=target_student_id,
            started_at=datetime.utcnow(),
            submitted_at=datetime.utcnow(),
            status="submitted",
            score=evaluated_score,
        )
        db.add(record)

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

    max_test_score = round(sum(float(ctp.marks or 10.0) for ctp in test.problems), 2)
    db.commit()
    student_stats = _compute_student_xp_and_stats(target_student_id, db)
    return {
        "message": (
            f"Test submitted! Evaluated score so far: {evaluated_score}/{max_test_score} pts "
            f"({pending_count} submission(s) still being graded)."
            if pending_count > 0
            else f"Test completed! Final evaluated score: {evaluated_score}/{max_test_score} pts."
        ),
        "test_id": test_id,
        "student_id": target_student_id,
        "score": evaluated_score,
        "max_score": max_test_score,
        "test_xp": int(round(evaluated_score)),
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
    evaluated submissions in the database:
      - Practice / Assignment problems: up to 10 XP per unique problem based on the
        student's highest evaluated pass ratio (`passed_count / total_count`).
      - Coding Tests: up to `marks` (default 10) XP per unique problem within each
        coding test based on the student's highest evaluated coding-test submission score.
      - Unevaluated (`Pending Evaluation` / `Running`) or 0-pass submissions award 0 XP.
      - Repeated submissions to the same problem only improve XP up to the per-problem cap,
        preventing XP farming or duplicate retry awards.
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
    best_test_score: dict[tuple[int, int], float] = {}
    solved_problems: set[int] = set()

    for s in eval_subs:
        if s.status == STATUS_ACCEPTED:
            solved_problems.add(s.problem_id)

        if s.submission_type == "coding_test" and s.coding_test_id:
            key = (s.coding_test_id, s.problem_id)
            score_val = float(s.score or 0.0)
            if score_val > best_test_score.get(key, 0.0):
                best_test_score[key] = score_val
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
    test_xp = sum(best_test_score.values())
    total_xp = int(round(practice_xp + test_xp))

    tests_done = (
        db.query(CodingTestStudent)
        .filter(
            CodingTestStudent.student_id == stu_id,
            CodingTestStudent.status.in_(COMPLETED_TEST_STATUSES),
        )
        .count()
    )

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
    upcoming = sorted(
        [a for a in my_assignments if a.deadline is None or a.deadline >= now],
        key=lambda a: (a.deadline is None, a.deadline or now),
    )[:5]

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
        upcoming_deadlines=[_build_assignment_response(a) for a in upcoming],
        pending_tests=pending_tests,
        recent_submissions=[_submission_to_response(s, db, include_details=False, is_teacher=False) for s in recent],
    )
