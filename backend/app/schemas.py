from typing import Optional, List
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


class ProblemCreate(ProblemBase):
    created_by: Optional[int] = None  # overridden by the authenticated teacher
    test_cases: Optional[List[TestCaseCreate]] = None


class ProblemResponse(ProblemBase):
    id: int
    created_by: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    test_cases: Optional[List[TestCasePublic]] = []
    hidden_test_count: int = 0

    class Config:
        from_attributes = True


# =========================================================
# SUBMISSION & EXECUTION SCHEMAS
# =========================================================

class RunSamplesRequest(BaseModel):
    problem_id: int
    language: str = Field(..., min_length=1, max_length=30)
    code: str = Field(..., min_length=1, max_length=65536)


class SampleTestCaseResult(BaseModel):
    test_case_number: int
    test_case_id: int
    input: str
    expected_output: str
    actual_output: str
    passed: bool
    status: str
    execution_time: Optional[float] = None
    error_message: Optional[str] = None


class RunSamplesResponse(BaseModel):
    problem_id: int
    language: str
    status: str
    overall_status: str
    passed_count: int
    total_count: int
    execution_time: Optional[float] = None
    error_message: Optional[str] = None
    compile_error: Optional[str] = None
    results: List[SampleTestCaseResult] = []


class SubmissionCreate(BaseModel):
    # Optional for backwards compatibility; derived from authenticated user token on backend.
    user_id: Optional[int] = None
    problem_id: int
    code: str = Field(..., min_length=1, max_length=65536)
    language: str = Field(..., min_length=1, max_length=30)
    submission_type: str = Field("practice", pattern="^(practice|assignment|coding_test|competition)$")
    assignment_id: Optional[int] = None
    coding_test_id: Optional[int] = None
    competition_id: Optional[int] = None


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
    error_message: Optional[str] = None


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
    language: str
    status: str
    score: Optional[float] = 0.0
    max_score: float = 10.0
    passed_count: int = 0
    total_count: int = 0
    execution_time: Optional[float] = None
    memory_used: Optional[float] = None
    error_message: Optional[str] = None
    submitted_at: Optional[datetime] = None
    evaluated_at: Optional[datetime] = None
    attempt_count: int = 0
    submission_type: str
    assignment_id: Optional[int] = None
    coding_test_id: Optional[int] = None
    competition_id: Optional[int] = None
    problem_title: Optional[str] = None
    public_results: Optional[List[PublicSubmissionCaseResult]] = None
    hidden_summary: Optional[HiddenTestsSummary] = None
    teacher_hidden_results: Optional[List[PublicSubmissionCaseResult]] = None

    class Config:
        from_attributes = True


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
    created_at: Optional[datetime] = None
    problems: List[AssignedProblemInfo] = []
    students: List[AssignedStudentInfo] = []

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
    created_at: Optional[datetime] = None
    problems: List[AssignedProblemInfo] = []
    enrolled_count: int = 0
    completed_count: int = 0
    my_status: Optional[str] = None  # populated when requested for a specific student
    my_score: Optional[float] = None

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
