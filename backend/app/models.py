from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    Float,
    ForeignKey
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


# =========================================================
# USERS
# =========================================================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False, index=True)
    role = Column(String(20), nullable=False, default="student")
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    problems = relationship("Problem", back_populates="creator")
    submissions = relationship("Submission", back_populates="user")

    assignments_created = relationship(
        "Assignment",
        back_populates="creator"
    )

    assignments = relationship(
        "AssignmentStudent",
        back_populates="student"
    )

    coding_tests_created = relationship(
        "CodingTest",
        back_populates="creator"
    )

    coding_tests = relationship(
        "CodingTestStudent",
        back_populates="student"
    )

    competitions_created = relationship(
        "Competition",
        back_populates="creator"
    )

    competitions = relationship(
        "CompetitionParticipant",
        back_populates="student"
    )


# =========================================================
# PROBLEMS
# =========================================================

class Problem(Base):
    __tablename__ = "problems"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)

    difficulty = Column(String(20), nullable=False)
    topic = Column(String(100), nullable=False)

    input_format = Column(Text, nullable=True)
    output_format = Column(Text, nullable=True)
    constraints = Column(Text, nullable=True)
    examples = Column(Text, nullable=True)

    created_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    creator = relationship(
        "User",
        back_populates="problems"
    )

    test_cases = relationship(
        "TestCase",
        back_populates="problem",
        cascade="all, delete-orphan"
    )

    submissions = relationship(
        "Submission",
        back_populates="problem"
    )

    assignment_problems = relationship(
        "AssignmentProblem",
        back_populates="problem"
    )

    coding_test_problems = relationship(
        "CodingTestProblem",
        back_populates="problem"
    )

    competition_problems = relationship(
        "CompetitionProblem",
        back_populates="problem"
    )


# =========================================================
# TEST CASES
# =========================================================

class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, index=True)

    problem_id = Column(
        Integer,
        ForeignKey("problems.id"),
        nullable=False
    )

    input = Column(Text, nullable=False)
    expected_output = Column(Text, nullable=False)

    is_hidden = Column(
        Boolean,
        default=False,
        nullable=False
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

    # Relationships
    problem = relationship(
        "Problem",
        back_populates="test_cases"
    )

    submission_results = relationship(
        "SubmissionResult",
        back_populates="test_case"
    )


# =========================================================
# SUBMISSIONS
# =========================================================

class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    problem_id = Column(
        Integer,
        ForeignKey("problems.id"),
        nullable=False
    )

    code = Column(Text, nullable=False)

    language = Column(String(30), nullable=False)

    status = Column(String(30), nullable=False)

    score = Column(Float, default=0)

    execution_time = Column(
        Float,
        nullable=True
    )

    memory_used = Column(
        Float,
        nullable=True
    )

    submitted_at = Column(
        DateTime,
        server_default=func.now()
    )

    # Submission context
    submission_type = Column(
        String(20),
        nullable=False,
        default="practice"
    )

    assignment_id = Column(
        Integer,
        ForeignKey("assignments.id"),
        nullable=True
    )

    coding_test_id = Column(
        Integer,
        ForeignKey("coding_tests.id"),
        nullable=True
    )

    competition_id = Column(
        Integer,
        ForeignKey("competitions.id"),
        nullable=True
    )

    # Relationships
    user = relationship(
        "User",
        back_populates="submissions"
    )

    problem = relationship(
        "Problem",
        back_populates="submissions"
    )

    assignment = relationship(
        "Assignment",
        back_populates="submissions"
    )

    coding_test = relationship(
        "CodingTest",
        back_populates="submissions"
    )

    competition = relationship(
        "Competition",
        back_populates="submissions"
    )

    results = relationship(
        "SubmissionResult",
        back_populates="submission",
        cascade="all, delete-orphan"
    )


# =========================================================
# SUBMISSION RESULTS
# =========================================================

class SubmissionResult(Base):
    __tablename__ = "submission_results"

    id = Column(Integer, primary_key=True, index=True)

    submission_id = Column(
        Integer,
        ForeignKey("submissions.id"),
        nullable=False
    )

    test_case_id = Column(
        Integer,
        ForeignKey("test_cases.id"),
        nullable=False
    )

    status = Column(
        String(30),
        nullable=False
    )

    execution_time = Column(
        Float,
        nullable=True
    )

    memory_used = Column(
        Float,
        nullable=True
    )

    actual_output = Column(
        Text,
        nullable=True
    )

    error_message = Column(
        Text,
        nullable=True
    )

    # Relationships
    submission = relationship(
        "Submission",
        back_populates="results"
    )

    test_case = relationship(
        "TestCase",
        back_populates="submission_results"
    )


# =========================================================
# ASSIGNMENTS
# =========================================================

class Assignment(Base):
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(
        String(200),
        nullable=False
    )

    description = Column(
        Text,
        nullable=True
    )

    created_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    start_date = Column(
        DateTime,
        nullable=True
    )

    deadline = Column(
        DateTime,
        nullable=True
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

    # Relationships
    creator = relationship(
        "User",
        back_populates="assignments_created"
    )

    problems = relationship(
        "AssignmentProblem",
        back_populates="assignment",
        cascade="all, delete-orphan"
    )

    students = relationship(
        "AssignmentStudent",
        back_populates="assignment",
        cascade="all, delete-orphan"
    )

    submissions = relationship(
        "Submission",
        back_populates="assignment"
    )


# =========================================================
# ASSIGNMENT PROBLEMS
# =========================================================

class AssignmentProblem(Base):
    __tablename__ = "assignment_problems"

    id = Column(Integer, primary_key=True, index=True)

    assignment_id = Column(
        Integer,
        ForeignKey("assignments.id"),
        nullable=False
    )

    problem_id = Column(
        Integer,
        ForeignKey("problems.id"),
        nullable=False
    )

    marks = Column(
        Float,
        nullable=False,
        default=0
    )

    # Relationships
    assignment = relationship(
        "Assignment",
        back_populates="problems"
    )

    problem = relationship(
        "Problem",
        back_populates="assignment_problems"
    )


# =========================================================
# ASSIGNMENT STUDENTS
# =========================================================

class AssignmentStudent(Base):
    __tablename__ = "assignment_students"

    id = Column(Integer, primary_key=True, index=True)

    assignment_id = Column(
        Integer,
        ForeignKey("assignments.id"),
        nullable=False
    )

    student_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    assigned_at = Column(
        DateTime,
        server_default=func.now()
    )

    status = Column(
        String(30),
        nullable=False,
        default="assigned"
    )

    # Relationships
    assignment = relationship(
        "Assignment",
        back_populates="students"
    )

    student = relationship(
        "User",
        back_populates="assignments"
    )


# =========================================================
# CODING TESTS
# =========================================================

class CodingTest(Base):
    __tablename__ = "coding_tests"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(
        String(200),
        nullable=False
    )

    description = Column(
        Text,
        nullable=True
    )

    created_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    start_time = Column(
        DateTime,
        nullable=True
    )

    end_time = Column(
        DateTime,
        nullable=True
    )

    duration = Column(
        Integer,
        nullable=True
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

    # Relationships
    creator = relationship(
        "User",
        back_populates="coding_tests_created"
    )

    problems = relationship(
        "CodingTestProblem",
        back_populates="coding_test",
        cascade="all, delete-orphan"
    )

    students = relationship(
        "CodingTestStudent",
        back_populates="coding_test",
        cascade="all, delete-orphan"
    )

    submissions = relationship(
        "Submission",
        back_populates="coding_test"
    )


# =========================================================
# CODING TEST PROBLEMS
# =========================================================

class CodingTestProblem(Base):
    __tablename__ = "coding_test_problems"

    id = Column(Integer, primary_key=True, index=True)

    coding_test_id = Column(
        Integer,
        ForeignKey("coding_tests.id"),
        nullable=False
    )

    problem_id = Column(
        Integer,
        ForeignKey("problems.id"),
        nullable=False
    )

    marks = Column(
        Float,
        nullable=False,
        default=0
    )

    # Relationships
    coding_test = relationship(
        "CodingTest",
        back_populates="problems"
    )

    problem = relationship(
        "Problem",
        back_populates="coding_test_problems"
    )


# =========================================================
# CODING TEST STUDENTS
# =========================================================

class CodingTestStudent(Base):
    __tablename__ = "coding_test_students"

    id = Column(Integer, primary_key=True, index=True)

    coding_test_id = Column(
        Integer,
        ForeignKey("coding_tests.id"),
        nullable=False
    )

    student_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    started_at = Column(
        DateTime,
        nullable=True
    )

    submitted_at = Column(
        DateTime,
        nullable=True
    )

    score = Column(
        Float,
        nullable=True
    )

    status = Column(
        String(30),
        nullable=False,
        default="not_started"
    )

    # Relationships
    coding_test = relationship(
        "CodingTest",
        back_populates="students"
    )

    student = relationship(
        "User",
        back_populates="coding_tests"
    )


# =========================================================
# COMPETITIONS
# =========================================================

class Competition(Base):
    __tablename__ = "competitions"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(
        String(200),
        nullable=False
    )

    description = Column(
        Text,
        nullable=True
    )

    created_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    start_time = Column(
        DateTime,
        nullable=True
    )

    end_time = Column(
        DateTime,
        nullable=True
    )

    type = Column(
        String(50),
        nullable=False
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

    # Relationships
    creator = relationship(
        "User",
        back_populates="competitions_created"
    )

    problems = relationship(
        "CompetitionProblem",
        back_populates="competition",
        cascade="all, delete-orphan"
    )

    participants = relationship(
        "CompetitionParticipant",
        back_populates="competition",
        cascade="all, delete-orphan"
    )

    submissions = relationship(
        "Submission",
        back_populates="competition"
    )


# =========================================================
# COMPETITION PROBLEMS
# =========================================================

class CompetitionProblem(Base):
    __tablename__ = "competition_problems"

    id = Column(Integer, primary_key=True, index=True)

    competition_id = Column(
        Integer,
        ForeignKey("competitions.id"),
        nullable=False
    )

    problem_id = Column(
        Integer,
        ForeignKey("problems.id"),
        nullable=False
    )

    marks = Column(
        Float,
        nullable=False,
        default=0
    )

    # Relationships
    competition = relationship(
        "Competition",
        back_populates="problems"
    )

    problem = relationship(
        "Problem",
        back_populates="competition_problems"
    )


# =========================================================
# COMPETITION PARTICIPANTS
# =========================================================

class CompetitionParticipant(Base):
    __tablename__ = "competition_participants"

    id = Column(Integer, primary_key=True, index=True)

    competition_id = Column(
        Integer,
        ForeignKey("competitions.id"),
        nullable=False
    )

    student_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    registered_at = Column(
        DateTime,
        server_default=func.now()
    )

    score = Column(
        Float,
        nullable=True
    )

    rank = Column(
        Integer,
        nullable=True
    )

    # Relationships
    competition = relationship(
        "Competition",
        back_populates="participants"
    )

    student = relationship(
        "User",
        back_populates="competitions"
    )