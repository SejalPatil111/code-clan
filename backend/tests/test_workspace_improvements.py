"""
CodeClan Phase 6 — Student Coding Workspace UI/UX & Functionality Verification Suite.

Verifies backend APIs, multi-language execution (Python, C, C++, Java, JavaScript),
multi-file submissions, Runtime Error & Compilation Error recovery, separate
Practice / Assignment / Coding Test submission contexts, teacher-configurable
copy-paste policies, hidden test case protection, and Docker sandbox grading.

Run:
    docker compose exec -T backend python -m unittest tests/test_workspace_improvements.py -v
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
    timeout: int = 65,
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


class WorkspaceImprovementsVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ts = int(time.time())
        code, t_res = _api(
            "POST",
            "/auth/register",
            {
                "name": f"Prof. Workspace Verifier {cls.ts}",
                "email": f"prof_ws_{cls.ts}@codeclan.edu",
                "password": "Password123!",
                "role": "teacher",
            },
        )
        assert code in (200, 201), f"Teacher register failed: {code} {t_res}"
        cls.teacher_token = t_res["access_token"]
        cls.teacher_user = t_res["user"]

        code, s_res = _api(
            "POST",
            "/auth/register",
            {
                "name": f"Student Workspace Verifier {cls.ts}",
                "email": f"student_ws_{cls.ts}@codeclan.edu",
                "password": "Password123!",
                "role": "student",
            },
        )
        assert code in (200, 201), f"Student register failed: {code} {s_res}"
        cls.student_token = s_res["access_token"]
        cls.student_user = s_res["user"]

        # Create a standard problem with public and hidden test cases
        code, prob = _api(
            "POST",
            "/problems",
            {
                "title": f"Sum Two Integers {cls.ts}",
                "description": "Read two space-separated integers a and b from standard input and print their sum (a + b).",
                "difficulty": "Easy",
                "topic": "Math",
                "constraints": "-10^9 <= a, b <= 10^9",
                "examples": "Input: 10 25 -> Output: 35",
                "environment_id": "cp",
                "problem_type": "competitive",
                "evaluation_type": "exact",
                "test_cases": [
                    {"input": "10 25", "expected_output": "35", "is_hidden": False},
                    {"input": "100 250", "expected_output": "350", "is_hidden": True},
                ],
            },
            token=cls.teacher_token,
        )
        assert code == 201, f"Problem creation failed: {code} {prob}"
        cls.problem_id = prob["id"]

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

    def test_01_all_five_languages_run_samples(self) -> None:
        """Verify Python, C, C++, Java, and JavaScript execute properly in the Docker sandbox."""
        solutions = {
            "python": "# Write your solution here\nimport sys\nprint(sum(map(int, sys.stdin.read().split())))\n",
            "c": "#include <stdio.h>\nint main() {\n    long long a, b;\n    if (scanf(\"%lld %lld\", &a, &b) == 2) printf(\"%lld\\n\", a + b);\n    return 0;\n}\n",
            "cpp": "#include <iostream>\nusing namespace std;\nint main() {\n    long long a, b;\n    if (cin >> a >> b) cout << (a + b) << endl;\n    return 0;\n}\n",
            "java": "import java.util.*;\npublic class Main {\n    public static void main(String[] args) {\n        Scanner sc = new Scanner(System.in);\n        if (sc.hasNextLong()) {\n            long a = sc.nextLong(), b = sc.nextLong();\n            System.out.println(a + b);\n        }\n    }\n}\n",
            "javascript": "// Write your solution here\nconst fs = require('fs');\nconst parts = fs.readFileSync(0, 'utf8').trim().split(/\\s+/).map(Number);\nconsole.log(parts[0] + parts[1]);\n",
        }
        for lang, src in solutions.items():
            with self.subTest(language=lang):
                code, res = _api(
                    "POST",
                    "/submissions/run-samples",
                    {
                        "problem_id": self.problem_id,
                        "language": lang,
                        "code": src,
                    },
                    token=self.student_token,
                )
                self.assertEqual(code, 200, f"{lang} failed: {res}")
                self.assertEqual(res["status"], "Accepted", f"{lang} verdict: {res}")
                self.assertEqual(res["passed_count"], 1)
                self.assertEqual(res["total_count"], 1)
                # Ensure hidden test case was NOT executed or exposed in Run Samples
                self.assertEqual(len(res["results"]), 1)
                self.assertEqual(res["results"][0]["expected_output"], "35")

    def test_02_runtime_error_and_compilation_error_recovery(self) -> None:
        """Verify Runtime Error (long traceback) and Compilation Error return detailed messages and allow immediate re-run."""
        # 1. Python Runtime Error
        code, rt_res = _api(
            "POST",
            "/submissions/run-samples",
            {
                "problem_id": self.problem_id,
                "language": "python",
                "code": "def level1():\n    return level2()\ndef level2():\n    return 1 / 0\nlevel1()\n",
            },
            token=self.student_token,
        )
        self.assertEqual(code, 200)
        self.assertEqual(rt_res["status"], "Runtime Error")
        self.assertIn("ZeroDivisionError", rt_res.get("error_message", ""))

        # 2. C++ Compilation Error
        code, ce_res = _api(
            "POST",
            "/submissions/run-samples",
            {
                "problem_id": self.problem_id,
                "language": "cpp",
                "code": "#include <iostream>\nint main() { missing_semicolon_error return 0; }\n",
            },
            token=self.student_token,
        )
        self.assertEqual(code, 200)
        self.assertEqual(ce_res["status"], "Compilation Error")
        self.assertTrue(ce_res.get("compile_error") or ce_res.get("error_message"))

        # 3. Immediate recovery run on the same problem
        code, ok_res = _api(
            "POST",
            "/submissions/run-samples",
            {
                "problem_id": self.problem_id,
                "language": "python",
                "code": "import sys\nprint(sum(map(int, sys.stdin.read().split())))\n",
            },
            token=self.student_token,
        )
        self.assertEqual(code, 200)
        self.assertEqual(ok_res["status"], "Accepted")

    def test_03_multi_file_submission_preserved(self) -> None:
        """Verify multi-file projects still compile, run samples, and grade properly."""
        files = {
            "main.py": "import sys\nfrom helper import add_two\na, b = map(int, sys.stdin.read().split())\nprint(add_two(a, b))\n",
            "helper.py": "def add_two(x, y):\n    return x + y\n",
        }
        code, run_res = _api(
            "POST",
            "/submissions/run-samples",
            {
                "problem_id": self.problem_id,
                "language": "python",
                "code": files["main.py"],
                "files": files,
                "entry_point": "main.py",
            },
            token=self.student_token,
        )
        self.assertEqual(code, 200)
        self.assertEqual(run_res["status"], "Accepted")

    def test_04_separate_practice_assignment_and_coding_test_contexts_and_copy_paste_policy(self) -> None:
        """
        Verify Practice, Assignment, and Coding Test contexts remain strictly separate
        and persist teacher-configured copy-paste policies.
        """
        # 1. Create an Assignment with default allow_copy_paste=True and another with allow_copy_paste=False
        code, asgn_open = _api(
            "POST",
            "/assignments",
            {
                "title": f"Coursework Assignment Open Paste {self.ts}",
                "description": "Solve the assigned problem.",
                "allow_copy_paste": True,
                "problem_ids": [self.problem_id],
                "student_ids": [self.student_user["id"]],
            },
            token=self.teacher_token,
        )
        self.assertEqual(code, 201, asgn_open)
        self.assertTrue(asgn_open["allow_copy_paste"])
        asgn_id = asgn_open["id"]

        code, asgn_strict = _api(
            "POST",
            "/assignments",
            {
                "title": f"Strict Lab Assignment {self.ts}",
                "description": "Manual typing required.",
                "allow_copy_paste": False,
                "problem_ids": [self.problem_id],
                "student_ids": [self.student_user["id"]],
            },
            token=self.teacher_token,
        )
        self.assertEqual(code, 201, asgn_strict)
        self.assertFalse(asgn_strict["allow_copy_paste"])

        # 2. Create a Coding Test (default allow_copy_paste=False)
        code, test_obj = _api(
            "POST",
            "/coding-tests",
            {
                "title": f"Official Proctored Test {self.ts}",
                "description": "Strict timed test.",
                "duration": 45,
                "problem_ids": [self.problem_id],
            },
            token=self.teacher_token,
        )
        self.assertEqual(code, 201, test_obj)
        self.assertFalse(test_obj["allow_copy_paste"])
        test_id = test_obj["id"]

        sol_code = "import sys\nprint(sum(map(int, sys.stdin.read().split())))\n"

        # 3. Submit in PRACTICE context
        code, sub_prac = _api(
            "POST",
            "/submissions",
            {
                "problem_id": self.problem_id,
                "language": "python",
                "code": sol_code,
                "submission_type": "practice",
            },
            token=self.student_token,
        )
        self.assertEqual(code, 201, sub_prac)
        graded_prac = self._wait_for_submission(sub_prac["id"], self.student_token)
        self.assertEqual(graded_prac["status"], "Accepted")
        self.assertEqual(graded_prac["submission_type"], "practice")
        self.assertIsNone(graded_prac["assignment_id"])
        self.assertIsNone(graded_prac["coding_test_id"])
        self.assertEqual(graded_prac["context_label"], "Practice")

        # 4. Submit in ASSIGNMENT context
        code, sub_asgn = _api(
            "POST",
            "/submissions",
            {
                "problem_id": self.problem_id,
                "language": "python",
                "code": sol_code,
                "submission_type": "assignment",
                "assignment_id": asgn_id,
            },
            token=self.student_token,
        )
        self.assertEqual(code, 201, sub_asgn)
        graded_asgn = self._wait_for_submission(sub_asgn["id"], self.student_token)
        self.assertEqual(graded_asgn["status"], "Accepted")
        self.assertEqual(graded_asgn["submission_type"], "assignment")
        self.assertEqual(graded_asgn["assignment_id"], asgn_id)
        self.assertIn("Assignment:", graded_asgn["context_label"])

        # Verify assignment status for student updated to Evaluated (1 of 1 problem submitted)
        code, stu_asgns = _api(
            "GET",
            f"/assignments?student_id={self.student_user['id']}",
            token=self.student_token,
        )
        self.assertEqual(code, 200)
        matched_asgn = next((a for a in stu_asgns if a["id"] == asgn_id), None)
        self.assertIsNotNone(matched_asgn)
        self.assertEqual(matched_asgn["my_status"], "Evaluated")
        self.assertEqual(matched_asgn["submitted_problems_count"], 1)

        # 5. Submit in CODING TEST context
        code, sub_test = _api(
            "POST",
            "/submissions",
            {
                "problem_id": self.problem_id,
                "language": "python",
                "code": sol_code,
                "submission_type": "coding_test",
                "coding_test_id": test_id,
            },
            token=self.student_token,
        )
        self.assertEqual(code, 201, sub_test)
        graded_test = self._wait_for_submission(sub_test["id"], self.student_token)
        self.assertEqual(graded_test["status"], "Accepted")
        self.assertEqual(graded_test["submission_type"], "coding_test")
        self.assertEqual(graded_test["coding_test_id"], test_id)
        self.assertIn("Coding Test:", graded_test["context_label"])

        # Complete the Coding Test and verify XP reward
        code, done_test = _api(
            "POST",
            f"/coding-tests/{test_id}/complete",
            token=self.student_token,
        )
        self.assertEqual(code, 200, done_test)
        self.assertEqual(done_test["status"], "completed")
        self.assertTrue(done_test["xp_awarded"])

        # 6. Verify My Submission History groups the 3 contexts separately even for the same problem_id
        code, grouped = _api(
            "GET",
            "/submissions/grouped/by-problem",
            token=self.student_token,
        )
        self.assertEqual(code, 200, grouped)
        prob_groups = [g for g in grouped if g["problem_id"] == self.problem_id]
        ctx_types = {g["submission_type"] for g in prob_groups}
        self.assertEqual(ctx_types, {"practice", "assignment", "coding_test"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
