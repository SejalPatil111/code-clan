from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, inspect, text

from app.database import Base, engine, get_db
from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    require_roles,
    require_teacher,
)
from app.models import (
    User,
    Problem,
    TestCase,
    Submission,
    SubmissionResult,
    Assignment,
    AssignmentProblem,
    AssignmentStudent,
    CodingTest,
    CodingTestProblem,
    CodingTestStudent,
)
from app.schemas import (
    UserCreate,
    UserResponse,
    ProblemCreate,
    ProblemResponse,
    TestCaseCreate,
    TestCaseResponse,
    TestCasePublic,
    SubmissionCreate,
    SubmissionResponse,
    AssignmentCreate,
    AssignmentResponse,
    AssignedProblemInfo,
    AssignedStudentInfo,
    CodingTestCreate,
    CodingTestResponse,
    LeaderboardEntry,
    RegisterRequest,
    LoginRequest,
    AuthResponse,
    StudentProgress,
    TeacherOverview,
    StudentOverview,
)

Base.metadata.create_all(bind=engine)


def _run_lightweight_migrations():
    """create_all() does not add columns to existing tables, so add new ones here."""
    inspector = inspect(engine)
    if "users" in inspector.get_table_names():
        user_cols = {c["name"] for c in inspector.get_columns("users")}
        if "password_hash" not in user_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NULL"))


_run_lightweight_migrations()

app = FastAPI(
    title="Code Clan API",
    description="Backend API for Code Clan — Collaborative Coding & Learning Platform",
    version="1.0.0",
)

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["General"])
def root():
    return {
        "message": "Welcome to Code Clan API",
        "status": "healthy",
        "version": "1.0.0",
    }


# =========================================================
# AUTH ENDPOINTS
# =========================================================

def _normalize_email(email: str) -> str:
    return email.strip().lower()


@app.post("/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED, tags=["Auth"])
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """
    Create a new account. If a legacy user with this email exists but has no password yet
    (created before authentication was added), the account is claimed and the password set;
    the existing role is kept.
    """
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
def create_user(user: UserCreate, db: Session = Depends(get_db)):
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
):
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    return query.offset(skip).limit(limit).all()


@app.get("/users/{user_id}", response_model=UserResponse, tags=["Users"])
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


# =========================================================
# PROBLEM ENDPOINTS
# =========================================================

@app.post("/problems", response_model=ProblemResponse, status_code=status.HTTP_201_CREATED, tags=["Problems"])
def create_problem(
    problem: ProblemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    problem.created_by = current_user.id
    creator = current_user
    if not creator:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with ID {problem.created_by} does not exist.",
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
        created_by=problem.created_by,
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
    return new_problem


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
    response_list = []
    for p in problems:
        public_tcs = [
            TestCasePublic(
                id=tc.id,
                problem_id=tc.problem_id,
                input=tc.input,
                expected_output=tc.expected_output if not tc.is_hidden else None,
                is_hidden=tc.is_hidden,
            )
            for tc in p.test_cases
            if not tc.is_hidden
        ]
        p_dict = {
            "id": p.id,
            "title": p.title,
            "description": p.description,
            "difficulty": p.difficulty,
            "topic": p.topic,
            "input_format": p.input_format,
            "output_format": p.output_format,
            "constraints": p.constraints,
            "examples": p.examples,
            "created_by": p.created_by,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
            "test_cases": public_tcs,
        }
        response_list.append(ProblemResponse(**p_dict))
    return response_list


@app.get("/problems/{problem_id}", response_model=ProblemResponse, tags=["Problems"])
def get_problem(problem_id: int, db: Session = Depends(get_db)):
    problem = db.query(Problem).filter(Problem.id == problem_id).first()
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found.")

    public_tcs = [
        TestCasePublic(
            id=tc.id,
            problem_id=tc.problem_id,
            input=tc.input,
            expected_output=tc.expected_output if not tc.is_hidden else None,
            is_hidden=tc.is_hidden,
        )
        for tc in problem.test_cases
        if not tc.is_hidden
    ]
    p_dict = {
        "id": problem.id,
        "title": problem.title,
        "description": problem.description,
        "difficulty": problem.difficulty,
        "topic": problem.topic,
        "input_format": problem.input_format,
        "output_format": problem.output_format,
        "constraints": problem.constraints,
        "examples": problem.examples,
        "created_by": problem.created_by,
        "created_at": problem.created_at,
        "updated_at": problem.updated_at,
        "test_cases": public_tcs,
    }
    return ProblemResponse(**p_dict)


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
# SUBMISSION ENDPOINTS
# =========================================================

@app.post("/submissions", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED, tags=["Submissions"])
def create_submission(sub: SubmissionCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == sub.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    problem = db.query(Problem).filter(Problem.id == sub.problem_id).first()
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found.")

    context_count = sum([
        1 if sub.assignment_id is not None else 0,
        1 if sub.coding_test_id is not None else 0,
        1 if sub.competition_id is not None else 0,
    ])

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

    new_sub = Submission(
        user_id=sub.user_id,
        problem_id=sub.problem_id,
        code=sub.code,
        language=sub.language,
        status="Pending Evaluation",
        score=0.0,
        submission_type=sub.submission_type,
        assignment_id=sub.assignment_id,
        coding_test_id=sub.coding_test_id,
        competition_id=sub.competition_id,
    )
    db.add(new_sub)

    # If it is a coding test submission, update CodingTestStudent record
    if sub.submission_type == "coding_test" and sub.coding_test_id:
        record = (
            db.query(CodingTestStudent)
            .filter(
                CodingTestStudent.coding_test_id == sub.coding_test_id,
                CodingTestStudent.student_id == sub.user_id,
            )
            .first()
        )
        if record:
            record.status = "submitted"
            record.score = 10.0 # 10 pts per test submission
        else:
            new_record = CodingTestStudent(
                coding_test_id=sub.coding_test_id,
                student_id=sub.user_id,
                status="submitted",
                score=10.0,
            )
            db.add(new_record)

    db.commit()
    db.refresh(new_sub)

    return SubmissionResponse(
        id=new_sub.id,
        user_id=new_sub.user_id,
        problem_id=new_sub.problem_id,
        code=new_sub.code,
        language=new_sub.language,
        status=new_sub.status,
        score=new_sub.score,
        execution_time=new_sub.execution_time,
        memory_used=new_sub.memory_used,
        submitted_at=new_sub.submitted_at,
        submission_type=new_sub.submission_type,
        assignment_id=new_sub.assignment_id,
        coding_test_id=new_sub.coding_test_id,
        competition_id=new_sub.competition_id,
        problem_title=problem.title,
    )


@app.get("/submissions", response_model=List[SubmissionResponse], tags=["Submissions"])
def list_submissions(
    user_id: Optional[int] = Query(None),
    problem_id: Optional[int] = Query(None),
    submission_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(Submission)
    if user_id:
        query = query.filter(Submission.user_id == user_id)
    if problem_id:
        query = query.filter(Submission.problem_id == problem_id)
    if submission_type:
        query = query.filter(Submission.submission_type == submission_type)

    submissions = query.order_by(desc(Submission.submitted_at)).offset(skip).limit(limit).all()
    results = []
    for s in submissions:
        p_title = s.problem.title if s.problem else "Unknown Problem"
        results.append(
            SubmissionResponse(
                id=s.id,
                user_id=s.user_id,
                problem_id=s.problem_id,
                code=s.code,
                language=s.language,
                status=s.status,
                score=s.score,
                execution_time=s.execution_time,
                memory_used=s.memory_used,
                submitted_at=s.submitted_at,
                submission_type=s.submission_type,
                assignment_id=s.assignment_id,
                coding_test_id=s.coding_test_id,
                competition_id=s.competition_id,
                problem_title=p_title,
            )
        )
    return results


@app.get("/submissions/{submission_id}", response_model=SubmissionResponse, tags=["Submissions"])
def get_submission(submission_id: int, db: Session = Depends(get_db)):
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found.")

    p_title = sub.problem.title if sub.problem else "Unknown Problem"
    return SubmissionResponse(
        id=sub.id,
        user_id=sub.user_id,
        problem_id=sub.problem_id,
        code=sub.code,
        language=sub.language,
        status=sub.status,
        score=sub.score,
        execution_time=sub.execution_time,
        memory_used=sub.memory_used,
        submitted_at=sub.submitted_at,
        submission_type=sub.submission_type,
        assignment_id=sub.assignment_id,
        coding_test_id=sub.coding_test_id,
        competition_id=sub.competition_id,
        problem_title=p_title,
    )


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
    creator = current_user
    if not creator:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Creator user not found.")

    new_assignment = Assignment(
        title=payload.title,
        description=payload.description,
        created_by=payload.created_by,
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
    if student_id is not None:
        mine = next((s for s in t.students if s.student_id == student_id), None)
        my_status = mine.status if mine else "not_started"
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
    )


@app.post("/coding-tests", response_model=CodingTestResponse, status_code=status.HTTP_201_CREATED, tags=["Coding Tests"])
def create_coding_test(
    payload: CodingTestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    payload.created_by = current_user.id
    creator = current_user
    if not creator:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Creator user not found.")

    new_test = CodingTest(
        title=payload.title,
        description=payload.description,
        created_by=payload.created_by,
        duration=payload.duration,
        start_time=payload.start_time,
        end_time=payload.end_time,
    )
    db.add(new_test)
    db.flush()

    # 1. Link selected existing problem IDs
    for pid in payload.problem_ids:
        prob = db.query(Problem).filter(Problem.id == pid).first()
        if prob:
            ctp = CodingTestProblem(coding_test_id=new_test.id, problem_id=prob.id, marks=10.0)
            db.add(ctp)

    # 2. Create brand-new unique questions designed by teacher for this test
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
                created_by=payload.created_by,
            )
            db.add(new_custom_prob)
            db.flush()

            # Add sample test case if provided
            if cp.sample_input or cp.sample_output:
                new_tc = TestCase(
                    problem_id=new_custom_prob.id,
                    input=cp.sample_input.strip() if cp.sample_input else "test_input",
                    expected_output=cp.sample_output.strip() if cp.sample_output else "test_output",
                    is_hidden=False,
                )
                db.add(new_tc)

            # Link uniquely created problem to the coding test
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
def complete_coding_test(test_id: int, student_id: int = Query(...), db: Session = Depends(get_db)):
    """Simulates completing a test or registers 10 XP completion for a student."""
    test = db.query(CodingTest).filter(CodingTest.id == test_id).first()
    if not test:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coding test not found.")

    record = (
        db.query(CodingTestStudent)
        .filter(
            CodingTestStudent.coding_test_id == test_id,
            CodingTestStudent.student_id == student_id,
        )
        .first()
    )
    if record:
        record.status = "submitted"
        record.score = 10.0
    else:
        record = CodingTestStudent(
            coding_test_id=test_id,
            student_id=student_id,
            status="submitted",
            score=10.0,
        )
        db.add(record)

    db.commit()
    return {"message": "Test completed! 10 XP awarded.", "test_id": test_id, "student_id": student_id, "xp": 10}


# =========================================================
# LEADERBOARD ENDPOINTS
# =========================================================

@app.get("/leaderboard", response_model=List[LeaderboardEntry], tags=["Leaderboard"])
def get_leaderboard(db: Session = Depends(get_db)):
    """
    Computes real-time leaderboard ranked by total XP earned:
    - 10 XP for each completed Coding Test (CodingTestStudent.status in ('submitted', 'completed'))
    - Ranked in descending order of XP (highest first).
    """
    students = db.query(User).filter(User.role == "student").all()
    results = []

    for stu in students:
        # Count coding tests completed by this student
        tests_done = (
            db.query(CodingTestStudent)
            .filter(
                CodingTestStudent.student_id == stu.id,
                CodingTestStudent.status.in_(["submitted", "completed"]),
            )
            .count()
        )
        xp = tests_done * 10

        results.append({
            "user_id": stu.id,
            "name": stu.name,
            "email": stu.email,
            "role": stu.role,
            "tests_completed": tests_done,
            "xp": xp,
        })

    # Sort in descending order of XP, then tests_completed, then alphabetically
    results.sort(key=lambda x: (x["xp"], x["tests_completed"]), reverse=True)

    # Assign ranks (1, 2, 3...)
    ranked_entries = []
    for idx, entry in enumerate(results, start=1):
        ranked_entries.append(
            LeaderboardEntry(
                rank=idx,
                user_id=entry["user_id"],
                name=entry["name"],
                email=entry["email"],
                role=entry["role"],
                tests_completed=entry["tests_completed"],
                xp=entry["xp"],
            )
        )

    return ranked_entries



# =========================================================
# ROLE-BASED DASHBOARD ENDPOINTS
# =========================================================

COMPLETED_TEST_STATUSES = ("submitted", "completed")
XP_PER_TEST = 10


def _submission_to_response(s: Submission) -> SubmissionResponse:
    return SubmissionResponse(
        id=s.id,
        user_id=s.user_id,
        problem_id=s.problem_id,
        code=s.code,
        language=s.language,
        status=s.status,
        score=s.score,
        execution_time=s.execution_time,
        memory_used=s.memory_used,
        submitted_at=s.submitted_at,
        submission_type=s.submission_type,
        assignment_id=s.assignment_id,
        coding_test_id=s.coding_test_id,
        competition_id=s.competition_id,
        problem_title=s.problem.title if s.problem else "Unknown Problem",
    )


def _student_progress(stu: User, db: Session) -> StudentProgress:
    tests_done = (
        db.query(CodingTestStudent)
        .filter(
            CodingTestStudent.student_id == stu.id,
            CodingTestStudent.status.in_(COMPLETED_TEST_STATUSES),
        )
        .count()
    )
    subs_q = db.query(Submission).filter(Submission.user_id == stu.id)
    total_subs = subs_q.count()
    accepted = subs_q.filter(Submission.status == "Accepted").count()
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
        xp=tests_done * XP_PER_TEST,
        tests_completed=tests_done,
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
    """Aggregated class analytics for the teacher dashboard."""
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
    recent = db.query(Submission).order_by(desc(Submission.submitted_at)).limit(8).all()

    progress = [_student_progress(s, db) for s in students]
    progress.sort(key=lambda p: (p.xp, p.total_submissions), reverse=True)

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
        recent_submissions=[_submission_to_response(s) for s in recent],
        top_students=progress[:5],
    )


@app.get("/teacher/students", response_model=List[StudentProgress], tags=["Teacher Dashboard"])
def teacher_student_roster(
    db: Session = Depends(get_db),
    _teacher: User = Depends(require_teacher),
):
    """Per-student progress for every enrolled student."""
    students = db.query(User).filter(User.role == "student").order_by(User.name).all()
    return [_student_progress(s, db) for s in students]


@app.get("/student/overview", response_model=StudentOverview, tags=["Student Dashboard"])
def student_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("student")),
):
    """Personal progress summary for the logged-in student."""
    me = _student_progress(current_user, db)

    # Rank among all students (same ordering as /leaderboard)
    ranking = [_student_progress(s, db) for s in db.query(User).filter(User.role == "student").all()]
    ranking.sort(key=lambda p: (p.xp, p.tests_completed), reverse=True)
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
        .order_by(desc(Submission.submitted_at))
        .limit(5)
        .all()
    )

    return StudentOverview(
        xp=me.xp,
        rank=rank,
        total_ranked=len(ranking),
        tests_completed=me.tests_completed,
        tests_available=len(tests),
        total_submissions=me.total_submissions,
        accepted_submissions=me.accepted_submissions,
        problems_attempted=me.problems_attempted,
        total_problems=db.query(Problem).count(),
        assignments_assigned=len(my_assignments),
        upcoming_deadlines=[_build_assignment_response(a) for a in upcoming],
        pending_tests=pending_tests,
        recent_submissions=[_submission_to_response(s) for s in recent],
    )
