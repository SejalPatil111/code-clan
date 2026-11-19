from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


# =========================================================
# USER SCHEMAS
# =========================================================

class UserBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., max_length=150)
    role: str = Field("student", pattern="^(student|teacher|admin)$")


class UserCreate(UserBase):
    pass


class UserResponse(UserBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# =========================================================
# AUTH SCHEMAS
# =========================================================

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., min_length=3, max_length=150)
    password: str = Field(..., min_length=6, max_length=128)
    role: str = Field("student", pattern="^(student|teacher)$")


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=150)
    password: str = Field(..., min_length=1, max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# =========================================================
# TEST CASE SCHEMAS
# =========================================================

class TestCaseBase(BaseModel):
    input: str
    expected_output: str
    is_hidden: bool = False


class TestCaseCreate(TestCaseBase):
    pass


class TestCaseResponse(TestCaseBase):
    id: int
    problem_id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TestCasePublic(BaseModel):
    id: int
    problem_id: int
    input: str
    expected_output: Optional[str] = None
    is_hidden: bool

    class Config:
        from_attributes = True


# =========================================================
# DATASET SCHEMAS
# =========================================================

class DatasetCreate(BaseModel):
    filename: str = Field(..., min_length=1, max_length=160)
    visibility: str = Field("public", pattern="^(public|hidden)$")
    mime_type: str = Field("text/plain", max_length=80)
    content_b64: Optional[str] = None
    content_text: Optional[str] = None
    description: Optional[str] = Field(None, max_length=255)


class DatasetPublicResponse(BaseModel):
    id: int
    problem_id: int
    filename: str
    visibility: str
    mime_type: str
    size_bytes: int
    description: Optional[str] = None
    preview_text: Optional[str] = None
    content_b64: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# =========================================================
# PROBLEM SCHEMAS
# =========================================================

class ProblemBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str
    difficulty: str = Field(..., pattern="^(Easy|Medium|Hard)$")
    topic: str = Field(..., max_length=100)
    input_format: Optional[str] = None
    output_format: Optional[str] = None
    constraints: Optional[str] = None
    examples: Optional[str] = None
    environment_id: str = Field("cp", max_length=40)
    problem_type: str = Field("competitive", max_length=40)
    evaluation_type: str = Field("exact", max_length=40)
    evaluation_config: Optional[Any] = None
    resource_overrides: Optional[Any] = None
    starter_files: Optional[Any] = None
    entry_point: Optional[str] = Field(None, max_length=120)
    max_score: float = 10.0


class ProblemCreate(ProblemBase):
    created_by: Optional[int] = None  # overridden by the authenticated teacher
    test_cases: Optional[List[TestCaseCreate]] = None
    datasets: Optional[List[DatasetCreate]] = None


class ProblemResponse(ProblemBase):
    id: int
    created_by: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    test_cases: Optional[List[TestCasePublic]] = []
    hidden_test_count: int = 0
    datasets: Optional[List[DatasetPublicResponse]] = []
    hidden_dataset_count: int = 0
    environment_info: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


# =========================================================
# SUBMISSION & EXECUTION SCHEMAS
# =========================================================

class RunSamplesRequest(BaseModel):
    problem_id: int
    language: str = Field(..., min_length=1, max_length=30)
    code: str = Field("", max_length=262144)
    files: Optional[Dict[str, str]] = None
    entry_point: Optional[str] = Field(None, max_length=120)


class SampleTestCaseResult(BaseModel):
    test_case_number: int
    test_case_id: int
    input: str
    expected_output: str
    actual_output: str
    passed: bool
    status: str
    execution_time: Optional[float] = None
    memory_used: Optional[float] = None
    error_message: Optional[str] = None
    feedback: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    output_files: Optional[List[Dict[str, Any]]] = None


class RunSamplesResponse(BaseModel):
    problem_id: int
    language: str
    environment_id: Optional[str] = "cp"
    evaluation_type: Optional[str] = "exact"
    status: str
    overall_status: str
    passed_count: int
    total_count: int
    execution_time: Optional[float] = None
    memory_used: Optional[float] = None
    error_message: Optional[str] = None
    compile_error: Optional[str] = None
    results: List[SampleTestCaseResult] = []


class SubmissionCreate(BaseModel):
    # Optional for backwards compatibility; derived from authenticated user token on backend.
    user_id: Optional[int] = None
    problem_id: int
    code: str = Field("", max_length=262144)
    files: Optional[Dict[str, str]] = None
    entry_point: Optional[str] = Field(None, max_length=120)
    language: str = Field(..., min_length=1, max_length=30)
    submission_type: str = Field("practice", pattern="^(practice|assignment|coding_test|competition|practical)$")
    assignment_id: Optional[int] = None
    coding_test_id: Optional[int] = None
    competition_id: Optional[int] = None
    practical_id: Optional[int] = None


class PublicSubmissionCaseResult(BaseModel):
    test_case_number: int
    test_case_id: int
    is_hidden: bool = False
    input: Optional[str] = None
    expected_output: Optional[str] = None
    actual_output: Optional[str] = None
    passed: bool
    status: str
    execution_time: Optional[float] = None
    memory_used: Optional[float] = None
    error_message: Optional[str] = None
    feedback: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None


class HiddenTestsSummary(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0


class SubmissionResponse(BaseModel):
    id: int
    user_id: int
    user_name: Optional[str] = None
    problem_id: int
    code: str
    files: Optional[Dict[str, str]] = None
    entry_point: Optional[str] = None
    language: str
    environment_id: Optional[str] = "cp"
    evaluation_type: Optional[str] = "exact"
    status: str
    score: Optional[float] = 0.0
    max_score: float = 10.0
    passed_count: int = 0
    total_count: int = 0
    execution_time: Optional[float] = None
    memory_used: Optional[float] = None
    error_message: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    submitted_at: Optional[datetime] = None
    evaluated_at: Optional[datetime] = None
    attempt_count: int = 0
    submission_type: str
    assignment_id: Optional[int] = None
    coding_test_id: Optional[int] = None
    competition_id: Optional[int] = None
    practical_id: Optional[int] = None
    context_label: Optional[str] = None
    problem_title: Optional[str] = None
    public_results: Optional[List[PublicSubmissionCaseResult]] = None
    hidden_summary: Optional[HiddenTestsSummary] = None
    teacher_hidden_results: Optional[List[PublicSubmissionCaseResult]] = None

    class Config:
        from_attributes = True


class TeacherGroupedStudentSubmission(BaseModel):
    user_id: int
    student_name: str
    student_email: str
    total_submissions: int = 0
    problems_attempted: int = 0
    accepted_count: int = 0
    pending_or_failed_count: int = 0
    pending_count: int = 0
    failed_count: int = 0
    best_score: float = 0.0
    latest_submitted_at: Optional[datetime] = None
    latest_verdict: Optional[str] = None


class StudentGroupedProblemSubmission(BaseModel):
    group_key: str
    problem_id: int
    problem_title: str
    submission_type: str
    context_label: str
    assignment_id: Optional[int] = None
    coding_test_id: Optional[int] = None
    practical_id: Optional[int] = None
    competition_id: Optional[int] = None
    total_attempts: int = 0
    latest_submission_id: int
    latest_verdict: str
    latest_language: str
    latest_submitted_at: Optional[datetime] = None
    best_score: float = 0.0
    max_score: float = 10.0
    best_passed_count: int = 0
    total_test_cases: int = 0
    best_execution_time: Optional[float] = None


# =========================================================
# ASSIGNMENT SCHEMAS
# =========================================================

class AssignmentProblemItem(BaseModel):
    problem_id: int
    marks: float = 10.0


class AssignmentCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = None
    created_by: Optional[int] = None  # overridden by the authenticated teacher
    start_date: Optional[datetime] = None
    deadline: Optional[datetime] = None
    allow_copy_paste: bool = True
    problem_ids: List[int] = []
    student_ids: List[int] = []


class AssignedStudentInfo(BaseModel):
    id: int
    student_id: int
    name: str
    email: str
    status: str
    assigned_at: Optional[datetime] = None


class AssignedProblemInfo(BaseModel):
    problem_id: int
    title: str
    difficulty: str
    topic: str
    marks: float


class AssignmentResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    created_by: int
    creator_name: Optional[str] = None
    start_date: Optional[datetime] = None
    deadline: Optional[datetime] = None
    allow_copy_paste: bool = True
    created_at: Optional[datetime] = None
    problems: List[AssignedProblemInfo] = []
    students: List[AssignedStudentInfo] = []
    # Populated when requested for a specific student (or on Student Dashboard / My Assignments)
    my_status: Optional[str] = None
    submitted_problems_count: int = 0
    evaluated_problems_count: int = 0
    total_problems_count: int = 0
    progress_text: Optional[str] = None
    my_submitted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# =========================================================
# ACADEMIC PRACTICAL SCHEMAS
# =========================================================

class AcademicPracticalCreate(BaseModel):
    practical_number: int = Field(..., ge=1, le=200)
    title: str = Field(..., min_length=2, max_length=200)
    subject_name: str = Field(..., min_length=2, max_length=150)
    subject_code: Optional[str] = Field(None, max_length=50)
    semester: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    objectives: Optional[str] = None
    problem_id: Optional[int] = None
    start_date: Optional[datetime] = None
    deadline: Optional[datetime] = None
    max_marks: float = Field(10.0, gt=0, le=500)
    student_ids: List[int] = []


class AcademicPracticalBulkAssign(BaseModel):
    practical_ids: List[int] = Field(..., min_length=1)
    student_ids: List[int] = Field(..., min_length=1)
    deadline: Optional[datetime] = None
    objectives: Optional[str] = None


class AcademicPracticalStudentSubmit(BaseModel):
    submission_notes: Optional[str] = None
    attachment_filename: Optional[str] = Field(None, max_length=200)
    attachment_content_b64: Optional[str] = None
    submission_id: Optional[int] = None


class AcademicPracticalEvaluateRequest(BaseModel):
    status: str = Field("Evaluated", pattern="^(Not Started|In Progress|Submitted|Evaluated|Late Submission)$")
    marks_obtained: Optional[float] = Field(None, ge=0)
    teacher_feedback: Optional[str] = None


class AcademicPracticalStudentInfo(BaseModel):
    id: int
    practical_id: int
    student_id: int
    student_name: str
    student_email: str
    assigned_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    evaluated_at: Optional[datetime] = None
    status: str
    submission_id: Optional[int] = None
    submission_notes: Optional[str] = None
    attachment_filename: Optional[str] = None
    attachment_content_b64: Optional[str] = None
    marks_obtained: Optional[float] = None
    teacher_feedback: Optional[str] = None

    class Config:
        from_attributes = True


class AcademicPracticalResponse(BaseModel):
    id: int
    practical_number: int
    title: str
    subject_name: str
    subject_code: Optional[str] = None
    semester: Optional[str] = None
    description: Optional[str] = None
    objectives: Optional[str] = None
    problem_id: Optional[int] = None
    problem_title: Optional[str] = None
    problem_difficulty: Optional[str] = None
    problem_topic: Optional[str] = None
    start_date: Optional[datetime] = None
    deadline: Optional[datetime] = None
    max_marks: float = 10.0
    created_by: int
    creator_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    assigned_count: int = 0
    submitted_count: int = 0
    evaluated_count: int = 0
    pending_count: int = 0
    late_count: int = 0
    students: List[AcademicPracticalStudentInfo] = []
    # Populated when requested for a specific student
    my_status: Optional[str] = None
    my_submitted_at: Optional[datetime] = None
    my_marks_obtained: Optional[float] = None
    my_teacher_feedback: Optional[str] = None
    my_submission_id: Optional[int] = None
    my_submission_notes: Optional[str] = None
    my_attachment_filename: Optional[str] = None

    class Config:
        from_attributes = True


# =========================================================
# CODING TEST SCHEMAS
# =========================================================

class NewCustomProblemInput(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str
    difficulty: str = Field("Medium", pattern="^(Easy|Medium|Hard)$")
    topic: str = Field("Assessment", max_length=100)
    constraints: Optional[str] = None
    examples: Optional[str] = None
    sample_input: Optional[str] = None
    sample_output: Optional[str] = None
    hidden_input: Optional[str] = None
    hidden_output: Optional[str] = None


class CodingTestCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = None
    created_by: Optional[int] = None  # overridden by the authenticated teacher
    duration: int = Field(60, ge=5, le=360)  # duration in minutes
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    allow_copy_paste: bool = False
    problem_ids: List[int] = []  # existing question bank problem IDs
    custom_problems: Optional[List[NewCustomProblemInput]] = []  # uniquely created test questions


class CodingTestResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    created_by: int
    creator_name: Optional[str] = None
    duration: Optional[int] = 60
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    allow_copy_paste: bool = False
    created_at: Optional[datetime] = None
    problems: List[AssignedProblemInfo] = []
    enrolled_count: int = 0
    completed_count: int = 0
    my_status: Optional[str] = None  # populated when requested for a specific student
    my_score: Optional[float] = None
    xp_reward: int = 10
    xp_awarded: bool = False
    xp_awarded_amount: int = 0
    xp_awarded_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# =========================================================
# LEADERBOARD SCHEMAS
# =========================================================

class LeaderboardEntry(BaseModel):
    rank: int
    user_id: int
    name: str
    email: str
    role: str
    tests_completed: int
    problems_solved: int = 0
    xp: int

    class Config:
        from_attributes = True


# =========================================================
# DASHBOARD SCHEMAS
# =========================================================

class StudentProgress(BaseModel):
    user_id: int
    name: str
    email: str
    joined_at: Optional[datetime] = None
    xp: int = 0
    tests_completed: int = 0
    problems_solved: int = 0
    total_submissions: int = 0
    accepted_submissions: int = 0
    problems_attempted: int = 0
    assignments_assigned: int = 0
    last_active: Optional[datetime] = None


class TeacherOverview(BaseModel):
    total_students: int
    total_teachers: int
    total_problems: int
    my_problems: int
    total_assignments: int
    my_assignments: int
    total_coding_tests: int
    my_coding_tests: int
    total_submissions: int
    submissions_last_7_days: int
    test_completion_rate: float  # percentage of (student x test) pairs completed
    difficulty_breakdown: dict
    recent_submissions: List[SubmissionResponse] = []
    top_students: List[StudentProgress] = []


class StudentOverview(BaseModel):
    xp: int
    rank: Optional[int] = None
    total_ranked: int
    tests_completed: int
    tests_available: int
    problems_solved: int = 0
    total_submissions: int
    accepted_submissions: int
    problems_attempted: int
    total_problems: int
    assignments_assigned: int
    upcoming_deadlines: List[AssignmentResponse] = []
    pending_tests: List[CodingTestResponse] = []
    recent_submissions: List[SubmissionResponse] = []
