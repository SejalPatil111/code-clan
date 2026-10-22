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

    class Config:
        from_attributes = True


# =========================================================
# SUBMISSION SCHEMAS
# =========================================================

class SubmissionCreate(BaseModel):
    user_id: int
    problem_id: int
    code: str = Field(..., min_length=1)
    language: str = Field(..., max_length=30)
    submission_type: str = Field("practice", pattern="^(practice|assignment|coding_test|competition)$")
    assignment_id: Optional[int] = None
    coding_test_id: Optional[int] = None
    competition_id: Optional[int] = None


class SubmissionResponse(BaseModel):
    id: int
    user_id: int
    problem_id: int
    code: str
    language: str
    status: str
    score: Optional[float] = 0.0
    execution_time: Optional[float] = None
    memory_used: Optional[float] = None
    submitted_at: Optional[datetime] = None
    submission_type: str
    assignment_id: Optional[int] = None
    coding_test_id: Optional[int] = None
    competition_id: Optional[int] = None
    problem_title: Optional[str] = None

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


class CodingTestCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = None
    created_by: Optional[int] = None  # overridden by the authenticated teacher
    duration: int = Field(60, ge=5, le=360) # duration in minutes
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    problem_ids: List[int] = [] # existing question bank problem IDs
    custom_problems: Optional[List[NewCustomProblemInput]] = [] # uniquely created test questions


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
    total_submissions: int
    accepted_submissions: int
    problems_attempted: int
    total_problems: int
    assignments_assigned: int
    upcoming_deadlines: List[AssignmentResponse] = []
    pending_tests: List[CodingTestResponse] = []
    recent_submissions: List[SubmissionResponse] = []
