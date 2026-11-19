"""
CodeClan Feature Improvements & Workflow Enhancements — Phase 4 Verification Suite.

Tests all 20 scenarios across the 7 feature improvements against the live FastAPI +
MySQL + Isolated Grader + Docker Sandbox stack while preserving all existing
student/problem/submission records.

Run:
    docker compose exec -T backend python -m unittest tests/test_feature_improvements.py -v
"""

from __future__ import annotations

import json
import os
import time
import unittest
import urllib.error
import urllib.request


API_BASE = os.getenv("CODECLAN_API_URL", "http://localhost:8000")


def _api(
    method: str,
    path: str,
    body: dict | None = None,
    token: str | None = None,
    timeout: int = 60,
) -> tuple[int, dict | list]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"{API_BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"detail": raw}


class FeatureImprovementsVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ts = int(time.time())
        _, t_res = _api(
            "POST",
            "/auth/register",
            {
                "name": f"Prof. Feature Verifier {cls.ts}",
                "email": f"prof_feat_{cls.ts}@codeclan.edu",
                "password": "Password123!",
                "role": "teacher",
            },
        )
        cls.teacher_token = t_res["access_token"]
        cls.teacher_user = t_res["user"]

        _, s1_res = _api(
            "POST",
            "/auth/register",
            {
                "name": f"Aarav Test {cls.ts}",
                "email": f"aarav_feat_{cls.ts}@codeclan.edu",
                "password": "Password123!",
                "role": "student",
            },
        )
        cls.s1_token = s1_res["access_token"]
        cls.s1_user = s1_res["user"]

        _, s2_res = _api(
            "POST",
            "/auth/register",
            {
                "name": f"Priya Test {cls.ts}",
                "email": f"priya_feat_{cls.ts}@codeclan.edu",
                "password": "Password123!",
                "role": "student",
            },
        )
        cls.s2_token = s2_res["access_token"]
        cls.s2_user = s2_res["user"]

    def _wait_for_submission(self, sub_id: int, token: str, timeout_sec: float = 45.0) -> dict:
        deadline = time.time() + timeout_sec
        last = {}
        while time.time() < deadline:
            code, data = _api("GET", f"/submissions/{sub_id}", token=token)
            self.assertEqual(code, 200)
            last = data
            if data.get("status") not in ("Pending Evaluation", "Running"):
                return data
            time.sleep(0.6)
        self.fail(f"Submission #{sub_id} did not finish within {timeout_sec}s: {last}")

    # ------------------------------------------------------------------
    # Scenarios 5, 6, 7: Problem Creation Without/With Constraints & Examples + Public/Hidden Test Cases
    # ------------------------------------------------------------------
    def test_01_problem_creation_optional_constraints_examples_and_hidden_cases(self) -> None:
        # Scenario 5: Create problem WITHOUT constraints or examples
        code, p1 = _api(
            "POST",
            "/problems",
            {
                "title": f"Simplified Add Two Numbers {self.ts}",
                "description": "Read two integers and print their sum.",
                "difficulty": "Easy",
                "topic": "Arithmetic",
                "test_cases": [
                    {"input": "3 4", "expected_output": "7", "is_hidden": False},
                    {"input": "100 250", "expected_output": "350", "is_hidden": True},
                ],
            },
            token=self.teacher_token,
        )
        self.assertEqual(code, 201, p1)
        self.assertIsNone(p1["constraints"])
        self.assertIsNone(p1["examples"])
        self.assertEqual(len(p1["test_cases"]), 1)
        self.assertEqual(p1["hidden_test_count"], 1)
        type(self).prob1_id = p1["id"]

        # Scenario 6: Create problem WITH optional constraints and examples
        code, p2 = _api(
            "POST",
            "/problems",
            {
                "title": f"Multiply Two Numbers {self.ts}",
                "description": "Read two integers and print their product.",
                "difficulty": "Easy",
                "topic": "Arithmetic",
                "constraints": "-10^6 <= a, b <= 10^6",
                "examples": "Input: 6 7 -> Output: 42",
                "test_cases": [
                    {"input": "6 7", "expected_output": "42", "is_hidden": False},
                    {"input": "12 12", "expected_output": "144", "is_hidden": True},
                ],
            },
            token=self.teacher_token,
        )
        self.assertEqual(code, 201, p2)
        self.assertEqual(p2["constraints"], "-10^6 <= a, b <= 10^6")
        self.assertEqual(p2["examples"], "Input: 6 7 -> Output: 42")
        type(self).prob2_id = p2["id"]

    # ------------------------------------------------------------------
    # Scenarios 1, 2, 3, 14: Grouped Submissions (Teacher by Student, Student by Problem)
    # ------------------------------------------------------------------
    def test_02_grouped_submissions_teacher_and_student(self) -> None:
        # Student 1 makes 3 submissions to Problem 1 (1 wrong, 2 accepted) and 1 submission to Problem 2
        _, sub1 = _api(
            "POST",
            "/submissions",
            {
                "problem_id": self.prob1_id,
                "language": "python",
                "code": "print(0)\n",
                "submission_type": "practice",
            },
            token=self.s1_token,
        )
        self._wait_for_submission(sub1["id"], self.s1_token)

        _, sub2 = _api(
            "POST",
            "/submissions",
            {
                "problem_id": self.prob1_id,
                "language": "python",
                "code": "import sys\nprint(sum(map(int, sys.stdin.read().split())))\n",
                "submission_type": "practice",
            },
            token=self.s1_token,
        )
        graded2 = self._wait_for_submission(sub2["id"], self.s1_token)
        self.assertEqual(graded2["status"], "Accepted")
        self.assertEqual(graded2["passed_count"], 2)
        self.assertEqual(graded2["total_count"], 2)

        _, sub3 = _api(
            "POST",
            "/submissions",
            {
                "problem_id": self.prob2_id,
                "language": "python",
                "code": "import sys\na, b = map(int, sys.stdin.read().split())\nprint(a * b)\n",
                "submission_type": "practice",
            },
            token=self.s1_token,
        )
        graded3 = self._wait_for_submission(sub3["id"], self.s1_token)
        self.assertEqual(graded3["status"], "Accepted")

        # Student 2 submits Problem 1 once
        _, sub_s2 = _api(
            "POST",
            "/submissions",
            {
                "problem_id": self.prob1_id,
                "language": "python",
                "code": "import sys\nprint(sum(map(int, sys.stdin.read().split())))\n",
                "submission_type": "practice",
            },
            token=self.s2_token,
        )
        self._wait_for_submission(sub_s2["id"], self.s2_token)

        # Scenario 1 & 2: Teacher grouped view shows Student 1 and Student 2 as separate single consolidated rows
        code, teacher_groups = _api(
            "GET",
            f"/submissions/grouped/by-student?student_search={self.ts}",
            token=self.teacher_token,
        )
        self.assertEqual(code, 200, teacher_groups)
        by_uid = {g["user_id"]: g for g in teacher_groups}
        self.assertIn(self.s1_user["id"], by_uid)
        self.assertIn(self.s2_user["id"], by_uid)

        s1_grp = by_uid[self.s1_user["id"]]
        self.assertEqual(s1_grp["total_submissions"], 3)
        self.assertEqual(s1_grp["problems_attempted"], 2)
        self.assertEqual(s1_grp["accepted_count"], 2)
        self.assertEqual(s1_grp["pending_or_failed_count"], 1)

        s2_grp = by_uid[self.s2_user["id"]]
        self.assertEqual(s2_grp["total_submissions"], 1)
        self.assertEqual(s2_grp["problems_attempted"], 1)
        self.assertEqual(s2_grp["accepted_count"], 1)

        # Teacher can still inspect all 3 individual historical submissions for Student 1
        code, s1_history = _api(
            "GET",
            f"/submissions?user_id={self.s1_user['id']}",
            token=self.teacher_token,
        )
        self.assertEqual(code, 200)
        self.assertEqual(len(s1_history), 3)

        # Scenario 3 & 14: Student 1 grouped problem history shows 2 unique problems (Problem 1 with 2 attempts, Problem 2 with 1 attempt)
        code, stu_prob_groups = _api(
            "GET",
            "/submissions/grouped/by-problem",
            token=self.s1_token,
        )
        self.assertEqual(code, 200, stu_prob_groups)
        by_pid = {g["problem_id"]: g for g in stu_prob_groups}
        self.assertEqual(len(by_pid), 2)
        self.assertEqual(by_pid[self.prob1_id]["total_attempts"], 2)
        self.assertEqual(by_pid[self.prob1_id]["best_score"], 10.0)
        self.assertEqual(by_pid[self.prob1_id]["latest_verdict"], "Accepted")
        self.assertEqual(by_pid[self.prob2_id]["total_attempts"], 1)

    # ------------------------------------------------------------------
    # Scenarios 8, 9, 10: Academic Practical Creation, Student View, and Submission Tracking
    # ------------------------------------------------------------------
    def test_03_academic_practicals_workflow(self) -> None:
        # Scenario 8: Teacher creates and assigns an academic practical
        code, prac = _api(
            "POST",
            "/practicals",
            {
                "practical_number": 1,
                "title": f"Implement Linear Regression {self.ts}",
                "subject_name": "Machine Learning Lab",
                "subject_code": "AIDS-701",
                "semester": "Sem VII",
                "description": "Implement simple linear regression and report MSE.",
                "objectives": "Understand ordinary least squares fitting.",
                "problem_id": self.prob1_id,
                "max_marks": 20.0,
                "student_ids": [self.s1_user["id"], self.s2_user["id"]],
            },
            token=self.teacher_token,
        )
        self.assertEqual(code, 201, prac)
        self.assertEqual(prac["assigned_count"], 2)
        self.assertEqual(prac["submitted_count"], 0)
        self.assertEqual(prac["pending_count"], 2)
        prac_id = prac["id"]

        # Scenario 9: Student 1 views their assigned practicals (initial status: Not Started)
        code, stu_pracs = _api("GET", "/practicals", token=self.s1_token)
        self.assertEqual(code, 200, stu_pracs)
        my_prac = next((p for p in stu_pracs if p["id"] == prac_id), None)
        self.assertIsNotNone(my_prac)
        self.assertEqual(my_prac["my_status"], "Not Started")

        # Student 1 starts practical -> status becomes In Progress
        code, started = _api("POST", f"/practicals/{prac_id}/start", token=self.s1_token)
        self.assertEqual(code, 200, started)
        self.assertEqual(started["my_status"], "In Progress")

        # Scenario 10: Student 1 submits practical -> Teacher sees updated status
        code, submitted = _api(
            "POST",
            f"/practicals/{prac_id}/submit",
            {
                "submission_notes": "Implemented OLS Linear Regression with R2=0.98",
                "attachment_filename": "linear_regression_lab1.py",
            },
            token=self.s1_token,
        )
        self.assertEqual(code, 200, submitted)
        self.assertEqual(submitted["my_status"], "Submitted")

        code, teacher_prac = _api("GET", f"/practicals/{prac_id}", token=self.teacher_token)
        self.assertEqual(code, 200, teacher_prac)
        self.assertEqual(teacher_prac["submitted_count"], 1)
        self.assertEqual(teacher_prac["pending_count"], 1)

        # Teacher evaluates Student 1's practical -> status becomes Evaluated with 19/20 marks
        code, evaluated = _api(
            "POST",
            f"/practicals/{prac_id}/students/{self.s1_user['id']}/evaluate",
            {
                "status": "Evaluated",
                "marks_obtained": 19.0,
                "teacher_feedback": "Excellent implementation and report.",
            },
            token=self.teacher_token,
        )
        self.assertEqual(code, 200, evaluated)
        self.assertEqual(evaluated["evaluated_count"], 1)

    # ------------------------------------------------------------------
    # Scenarios 11, 12, 13: Multi-Problem Assignment Status on Student Dashboard
    # ------------------------------------------------------------------
    def test_04_multi_problem_assignment_status_logic(self) -> None:
        # Create an assignment with 2 problems assigned to Student 1
        code, asgn = _api(
            "POST",
            "/assignments",
            {
                "title": f"Multi-Problem Lab Assignment {self.ts}",
                "description": "Solve both problems to complete this assignment.",
                "problem_ids": [self.prob1_id, self.prob2_id],
                "student_ids": [self.s1_user["id"]],
            },
            token=self.teacher_token,
        )
        self.assertEqual(code, 201, asgn)
        asgn_id = asgn["id"]

        # Scenario 11: Unsubmitted assignment displays Pending (0 of 2 problems submitted)
        code, overview1 = _api("GET", "/student/overview", token=self.s1_token)
        self.assertEqual(code, 200, overview1)
        dash_asgn1 = next((a for a in overview1["upcoming_deadlines"] if a["id"] == asgn_id), None)
        self.assertIsNotNone(dash_asgn1)
        self.assertEqual(dash_asgn1["my_status"], "Pending")
        self.assertEqual(dash_asgn1["submitted_problems_count"], 0)
        self.assertEqual(dash_asgn1["total_problems_count"], 2)

        # Scenario 13: Submitting only 1 of 2 problems marks assignment as "In Progress" (NOT Submitted/Completed)
        _, sub_a1 = _api(
            "POST",
            "/submissions",
            {
                "problem_id": self.prob1_id,
                "language": "python",
                "code": "import sys\nprint(sum(map(int, sys.stdin.read().split())))\n",
                "submission_type": "assignment",
                "assignment_id": asgn_id,
            },
            token=self.s1_token,
        )
        self._wait_for_submission(sub_a1["id"], self.s1_token)

        code, overview2 = _api("GET", "/student/overview", token=self.s1_token)
        dash_asgn2 = next((a for a in overview2["upcoming_deadlines"] if a["id"] == asgn_id), None)
        self.assertEqual(dash_asgn2["my_status"], "In Progress")
        self.assertEqual(dash_asgn2["submitted_problems_count"], 1)
        self.assertIn("1 of 2", dash_asgn2["progress_text"])

        # Scenario 12: Submitting the 2nd problem completes all required problems -> Evaluated
        _, sub_a2 = _api(
            "POST",
            "/submissions",
            {
                "problem_id": self.prob2_id,
                "language": "python",
                "code": "import sys\na, b = map(int, sys.stdin.read().split())\nprint(a * b)\n",
                "submission_type": "assignment",
                "assignment_id": asgn_id,
            },
            token=self.s1_token,
        )
        self._wait_for_submission(sub_a2["id"], self.s1_token)

        code, overview3 = _api("GET", "/student/overview", token=self.s1_token)
        dash_asgn3 = next((a for a in overview3["upcoming_deadlines"] if a["id"] == asgn_id), None)
        self.assertEqual(dash_asgn3["my_status"], "Evaluated")
        self.assertEqual(dash_asgn3["submitted_problems_count"], 2)
        self.assertIn("2 of 2", dash_asgn3["progress_text"])

    # ------------------------------------------------------------------
    # Scenarios 4, 15, 16, 17: Activity Search & Coding Test XP Reward Status (Idempotent Single Award)
    # ------------------------------------------------------------------
    def test_05_activity_search_and_coding_test_xp_reward_idempotency(self) -> None:
        # Create a coding test with a custom question without constraints/examples
        code, test_obj = _api(
            "POST",
            "/coding-tests",
            {
                "title": f"Mid-Sem Assessment {self.ts}",
                "description": "Timed departmental test",
                "duration": 30,
                "problem_ids": [self.prob1_id],
            },
            token=self.teacher_token,
        )
        self.assertEqual(code, 201, test_obj)
        test_id = test_obj["id"]

        # Scenario 4: Teacher searches for activity by title and by ID
        code, search_by_title = _api("GET", f"/coding-tests?search=Mid-Sem%20Assessment%20{self.ts}", token=self.teacher_token)
        self.assertEqual(code, 200)
        self.assertTrue(any(t["id"] == test_id for t in search_by_title))

        code, search_by_id = _api("GET", f"/coding-tests?search={test_id}", token=self.teacher_token)
        self.assertEqual(code, 200)
        self.assertTrue(any(t["id"] == test_id for t in search_by_id))

        # Before completion: xp_awarded is False, my_status is not_started
        code, tests_before = _api("GET", f"/coding-tests?student_id={self.s1_user['id']}", token=self.s1_token)
        my_t_before = next(t for t in tests_before if t["id"] == test_id)
        self.assertFalse(my_t_before["xp_awarded"])
        self.assertEqual(my_t_before["my_status"], "not_started")

        # Complete coding test -> status becomes completed and +10 XP is awarded
        code, comp1 = _api("POST", f"/coding-tests/{test_id}/complete", token=self.s1_token)
        self.assertEqual(code, 200, comp1)
        self.assertTrue(comp1["xp_awarded"])
        self.assertEqual(comp1["xp_awarded_amount"], 10)
        xp_after_first = comp1["xp"]

        # Scenarios 15, 16, 17: Calling complete again (or refreshing) does NOT award duplicate XP
        code, comp2 = _api("POST", f"/coding-tests/{test_id}/complete", token=self.s1_token)
        self.assertEqual(code, 200, comp2)
        self.assertEqual(comp2["xp"], xp_after_first)
        self.assertTrue(comp2["xp_awarded"])
        self.assertEqual(comp2["xp_awarded_amount"], 10)

        code, tests_after = _api("GET", f"/coding-tests?student_id={self.s1_user['id']}", token=self.s1_token)
        my_t_after = next(t for t in tests_after if t["id"] == test_id)
        self.assertEqual(my_t_after["my_status"], "completed")
        self.assertTrue(my_t_after["xp_awarded"])
        self.assertEqual(my_t_after["xp_awarded_amount"], 10)

    # ------------------------------------------------------------------
    # Scenarios 18, 19, 20: Multi-Language Execution & Sandbox Security Unchanged
    # ------------------------------------------------------------------
    def test_06_multilanguage_execution_and_security_invariants(self) -> None:
        lang_snippets = {
            "python": "import sys\nprint(sum(map(int, sys.stdin.read().split())))\n",
            "c": "#include <stdio.h>\nint main(){long long a,b; if(scanf(\"%lld %lld\",&a,&b)==2) printf(\"%lld\\n\",a+b); return 0;}\n",
            "cpp": "#include <iostream>\nusing namespace std;\nint main(){long long a,b; if(cin>>a>>b) cout<<(a+b)<<\"\\n\"; return 0;}\n",
            "java": "import java.util.*;\npublic class Main{public static void main(String[] a){Scanner s=new Scanner(System.in); System.out.println(s.nextLong()+s.nextLong());}}\n",
            "javascript": "const fs=require('fs'); const p=fs.readFileSync(0,'utf8').trim().split(/\\s+/).map(Number); console.log(p[0]+p[1]);\n",
        }
        for lang, snippet in lang_snippets.items():
            code, res = _api(
                "POST",
                "/submissions/run-samples",
                {"problem_id": self.prob1_id, "language": lang, "code": snippet},
                token=self.s1_token,
            )
            self.assertEqual(code, 200, f"{lang} failed: {res}")
            self.assertEqual(res["status"], "Accepted", f"{lang} verdict: {res}")

        # Scenario 19: Security status & cross-student protection (403)
        code, sec = _api("GET", "/execution/security-status", token=self.s1_token)
        self.assertEqual(code, 200)
        self.assertEqual(sec.get("container_verification_failures", 0), 0)

        code_cross, _ = _api("GET", f"/submissions?user_id={self.s1_user['id']}", token=self.s2_token)
        self.assertEqual(code_cross, 403)


if __name__ == "__main__":
    unittest.main()
