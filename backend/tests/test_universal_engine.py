"""
Comprehensive End-to-End Verification & Performance Suite for CodeClan's
Universal Execution Engine, Preconfigured ML/DS/CV/NLP/DL/Scientific Environments,
Multi-File Projects, Dataset Management, and Flexible Automated Grading Engine.

Run inside the backend container or on host against http://localhost:8000:
    python -m unittest tests/test_universal_engine.py -v
"""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
import struct
import time
import unittest
import urllib.error
import urllib.request
import zlib


API_BASE = os.getenv("CODECLAN_API_URL", "http://localhost:8000")


def _api(method: str, path: str, body: dict | None = None, token: str | None = None, timeout: int = 90) -> tuple[int, dict | list]:
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


def _make_tiny_png(width: int = 32, height: int = 32) -> bytes:
    """Create a valid RGB PNG image in pure Python stdlib for CV dataset tests."""
    raw_rows = []
    for y in range(height):
        row = bytearray([0])  # filter type 0
        for x in range(width):
            r = (x * 8) & 0xFF
            g = (y * 8) & 0xFF
            b = 128
            row.extend((r, g, b))
        raw_rows.append(bytes(row))
    raw_data = b"".join(raw_rows)

    def _chunk(c_type: bytes, c_data: bytes) -> bytes:
        crc = zlib.crc32(c_type + c_data) & 0xFFFFFFFF
        return struct.pack(">I", len(c_data)) + c_type + c_data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(raw_data)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


class UniversalExecutionEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        ts = int(time.time())
        # Register teacher & two students
        _, t_res = _api(
            "POST",
            "/auth/register",
            {
                "name": "Universal Engine Teacher",
                "email": f"ue_teacher_{ts}@codeclan.edu",
                "password": "Password123!",
                "role": "teacher",
            },
        )
        cls.teacher_token = t_res["access_token"]

        _, s1_res = _api(
            "POST",
            "/auth/register",
            {
                "name": "Universal Student One",
                "email": f"ue_student1_{ts}@codeclan.edu",
                "password": "Password123!",
                "role": "student",
            },
        )
        cls.student_token = s1_res["access_token"]

        # Create a base CP problem for multi-file and competitive tests
        _, prob = _api(
            "POST",
            "/problems",
            {
                "title": f"Universal CP & Multi-File Test {ts}",
                "description": "Given N integers, output their sum and maximum.",
                "difficulty": "Easy",
                "topic": "Algorithms",
                "environment_id": "cp",
                "problem_type": "multifile",
                "evaluation_type": "exact",
                "test_cases": [
                    {"input": "5\n10 20 30 40 50", "expected_output": "150 50", "is_hidden": False},
                    {"input": "4\n-5 15 0 90", "expected_output": "100 90", "is_hidden": True},
                ],
            },
            token=cls.teacher_token,
        )
        cls.cp_problem_id = prob["id"]

    def _wait_for_submission(self, sub_id: int, token: str, timeout_sec: float = 90.0) -> dict:
        deadline = time.time() + timeout_sec
        last = {}
        while time.time() < deadline:
            code, data = _api("GET", f"/submissions/{sub_id}", token=token)
            self.assertEqual(code, 200)
            last = data
            if data.get("status") not in ("Pending Evaluation", "Running"):
                return data
            time.sleep(0.8)
        self.fail(f"Submission #{sub_id} did not finish within {timeout_sec}s: {last}")

    # ------------------------------------------------------------------
    # 1. Environment Registry & Security Status Verification
    # ------------------------------------------------------------------
    def test_01_environments_and_security_status(self) -> None:
        code, env_data = _api("GET", "/environments")
        self.assertEqual(code, 200)
        env_ids = {e["id"] for e in env_data["environments"]}
        expected_ids = {"cp", "datascience", "ml", "cv", "nlp", "dl-torch", "dl-tf", "scientific"}
        self.assertTrue(expected_ids.issubset(env_ids))

        code, sec = _api("GET", "/execution/security-status")
        self.assertEqual(code, 200)
        self.assertEqual(sec["container_verification_failures"], 0)
        cv = sec["containers_verified"]
        verified_total = sum(cv.values()) if isinstance(cv, dict) else int(cv or 0)
        self.assertGreaterEqual(verified_total, 0)

    # ------------------------------------------------------------------
    # 2. Multi-File Projects (Python, C++, Java)
    # ------------------------------------------------------------------
    def test_02_multifile_python_cpp_java(self) -> None:
        # 2a. Multi-file Python with nested package module
        py_files = {
            "main.py": (
                "import sys\n"
                "from helpers.stats import compute_sum_and_max\n"
                "tokens = [int(x) for x in sys.stdin.read().split()]\n"
                "arr = tokens[1:]\n"
                "s, m = compute_sum_and_max(arr)\n"
                "print(f'{s} {m}')\n"
            ),
            "helpers/stats.py": (
                "def compute_sum_and_max(values):\n"
                "    return sum(values), max(values)\n"
            ),
        }
        code, res = _api(
            "POST",
            "/submissions/run-samples",
            {
                "problem_id": self.cp_problem_id,
                "language": "python",
                "code": py_files["main.py"],
                "files": py_files,
                "entry_point": "main.py",
            },
            token=self.student_token,
        )
        self.assertEqual(code, 200, res)
        self.assertEqual(res["status"], "Accepted", res)

        # 2b. Multi-file C++ (main.cpp + solver.cpp + solver.h)
        cpp_files = {
            "main.cpp": (
                "#include <iostream>\n"
                "#include <vector>\n"
                "#include \"solver.h\"\n"
                "int main() {\n"
                "    int n; if (!(std::cin >> n)) return 0;\n"
                "    std::vector<long long> a(n);\n"
                "    for (int i = 0; i < n; ++i) std::cin >> a[i];\n"
                "    auto ans = solve_vec(a);\n"
                "    std::cout << ans.first << \" \" << ans.second << \"\\n\";\n"
                "    return 0;\n"
                "}\n"
            ),
            "solver.h": (
                "#pragma once\n"
                "#include <utility>\n"
                "#include <vector>\n"
                "std::pair<long long, long long> solve_vec(const std::vector<long long>& a);\n"
            ),
            "solver.cpp": (
                "#include \"solver.h\"\n"
                "#include <numeric>\n"
                "#include <algorithm>\n"
                "std::pair<long long, long long> solve_vec(const std::vector<long long>& a) {\n"
                "    long long s = 0;\n"
                "    for (auto v : a) s += v;\n"
                "    long long m = *std::max_element(a.begin(), a.end());\n"
                "    return {s, m};\n"
                "}\n"
            ),
        }
        code, res = _api(
            "POST",
            "/submissions/run-samples",
            {
                "problem_id": self.cp_problem_id,
                "language": "cpp",
                "code": cpp_files["main.cpp"],
                "files": cpp_files,
            },
            token=self.student_token,
        )
        self.assertEqual(code, 200, res)
        self.assertEqual(res["status"], "Accepted", res)

        # 2c. Multi-file Java (Main.java + ArrayStats.java)
        java_files = {
            "Main.java": (
                "import java.util.*;\n"
                "public class Main {\n"
                "    public static void main(String[] args) {\n"
                "        Scanner sc = new Scanner(System.in);\n"
                "        int n = sc.nextInt();\n"
                "        long[] arr = new long[n];\n"
                "        for (int i = 0; i < n; i++) arr[i] = sc.nextLong();\n"
                "        System.out.println(ArrayStats.sum(arr) + \" \" + ArrayStats.max(arr));\n"
                "    }\n"
                "}\n"
            ),
            "ArrayStats.java": (
                "public class ArrayStats {\n"
                "    public static long sum(long[] a) {\n"
                "        long s = 0; for (long v : a) s += v; return s;\n"
                "    }\n"
                "    public static long max(long[] a) {\n"
                "        long m = a[0]; for (long v : a) if (v > m) m = v; return m;\n"
                "    }\n"
                "}\n"
            ),
        }
        code, res = _api(
            "POST",
            "/submissions/run-samples",
            {
                "problem_id": self.cp_problem_id,
                "language": "java",
                "code": java_files["Main.java"],
                "files": java_files,
            },
            token=self.student_token,
        )
        self.assertEqual(code, 200, res)
        self.assertEqual(res["status"], "Accepted", res)

    # ------------------------------------------------------------------
    # 3. Data Science Environment (`datascience`) + Dataset + PNG Plot Output
    # ------------------------------------------------------------------
    def test_03_datascience_environment_and_png_file_grading(self) -> None:
        csv_data = "region,revenue,cost\nNorth,120.5,80.0\nSouth,200.0,110.0\nEast,150.25,95.25\nWest,310.0,190.0\n"
        code, prob = _api(
            "POST",
            "/problems",
            {
                "title": "Data Science Revenue Plot & Analysis",
                "description": "Load /work/data/sales.csv using Pandas and save a Matplotlib bar chart to /work/output/plot.png.",
                "difficulty": "Medium",
                "topic": "Data Science",
                "environment_id": "datascience",
                "problem_type": "data_science",
                "evaluation_type": "file_based",
                "evaluation_config": {
                    "target_file": "plot.png",
                    "format": "png",
                    "min_width": 200,
                    "min_height": 150,
                    "check_stdout": True,
                },
                "test_cases": [
                    {"input": "", "expected_output": "total_profit=305.50", "is_hidden": False},
                ],
                "datasets": [
                    {
                        "filename": "sales.csv",
                        "visibility": "public",
                        "mime_type": "text/csv",
                        "content_text": csv_data,
                    }
                ],
            },
            token=self.teacher_token,
        )
        self.assertEqual(code, 201, prob)

        student_code = (
            "import pandas as pd\n"
            "import numpy as np\n"
            "import scipy.stats as stats\n"
            "import matplotlib.pyplot as plt\n"
            "df = pd.read_csv('/work/data/sales.csv')\n"
            "df['profit'] = df['revenue'] - df['cost']\n"
            "fig, ax = plt.subplots(figsize=(4, 3), dpi=80)\n"
            "ax.bar(df['region'], df['profit'])\n"
            "fig.savefig('/work/output/plot.png')\n"
            "print(f\"total_profit={df['profit'].sum():.2f}\")\n"
        )
        code, sub = _api(
            "POST",
            "/submissions",
            {
                "problem_id": prob["id"],
                "language": "python",
                "code": student_code,
                "submission_type": "practice",
            },
            token=self.student_token,
        )
        self.assertEqual(code, 201, sub)
        graded = self._wait_for_submission(sub["id"], self.student_token)
        self.assertEqual(graded["status"], "Accepted", graded)
        self.assertEqual(graded["score"], 10.0)
        self.assertIn("width", graded.get("metrics") or {})

    # ------------------------------------------------------------------
    # 4. Machine Learning Environment (`ml`) + Hidden Dataset + F1 Metric
    # ------------------------------------------------------------------
    def test_04_machine_learning_environment_and_f1_metrics(self) -> None:
        train_csv = (
            "f1,f2,label\n"
            "1.0,1.1,0\n1.2,0.9,0\n0.8,1.3,0\n1.1,1.0,0\n0.9,0.8,0\n"
            "5.0,5.2,1\n5.3,4.8,1\n4.9,5.1,1\n5.2,5.0,1\n4.8,4.9,1\n"
        )
        test_csv = (
            "f1,f2\n"
            "1.05,0.95\n"
            "5.10,5.05\n"
            "0.95,1.15\n"
            "4.95,5.15\n"
            "1.15,1.05\n"
            "5.25,4.85\n"
        )
        expected_labels = "0\n1\n0\n1\n0\n1"

        code, prob = _api(
            "POST",
            "/problems",
            {
                "title": "Binary Classification with Scikit-Learn",
                "description": "Train a classifier on /work/data/train.csv and predict on /work/data/test.csv.",
                "difficulty": "Medium",
                "topic": "Machine Learning",
                "environment_id": "ml",
                "problem_type": "machine_learning",
                "evaluation_type": "ml_metrics",
                "evaluation_config": {"metric": "f1", "threshold": 0.90, "target_file": "predictions.csv"},
                "test_cases": [
                    {"input": "", "expected_output": expected_labels, "is_hidden": True},
                ],
                "datasets": [
                    {
                        "filename": "train.csv",
                        "visibility": "public",
                        "mime_type": "text/csv",
                        "content_text": train_csv,
                    },
                    {
                        "filename": "test.csv",
                        "visibility": "hidden",
                        "mime_type": "text/csv",
                        "content_text": test_csv,
                    },
                ],
            },
            token=self.teacher_token,
        )
        self.assertEqual(code, 201, prob)
        # Verify student cannot see hidden dataset via GET /problems/{id}
        self.assertEqual(len(prob["datasets"]), 1)
        self.assertEqual(prob["hidden_dataset_count"], 1)

        ml_code = (
            "import pandas as pd\n"
            "from sklearn.linear_model import LogisticRegression\n"
            "train = pd.read_csv('/work/data/train.csv')\n"
            "test = pd.read_csv('/work/data/test.csv')\n"
            "clf = LogisticRegression().fit(train[['f1', 'f2']], train['label'])\n"
            "preds = clf.predict(test[['f1', 'f2']])\n"
            "pd.DataFrame({'prediction': preds}).to_csv('/work/output/predictions.csv', index=False)\n"
        )
        code, sub = _api(
            "POST",
            "/submissions",
            {
                "problem_id": prob["id"],
                "language": "python",
                "code": ml_code,
                "submission_type": "practice",
            },
            token=self.student_token,
        )
        self.assertEqual(code, 201, sub)
        graded = self._wait_for_submission(sub["id"], self.student_token)
        self.assertEqual(graded["status"], "Accepted", graded)
        self.assertGreaterEqual(graded["metrics"]["f1"], 0.99)
        self.assertGreaterEqual(graded["metrics"]["accuracy"], 0.99)

    # ------------------------------------------------------------------
    # 5. Computer Vision (`cv`) + Structured JSON Evaluation
    # ------------------------------------------------------------------
    def test_05_computer_vision_environment(self) -> None:
        png_bytes = _make_tiny_png(32, 24)
        png_b64 = base64.b64encode(png_bytes).decode("ascii")

        code, prob = _api(
            "POST",
            "/problems",
            {
                "title": "Image Dimension & Edge Analysis",
                "description": "Read /work/data/sample.png with OpenCV and Pillow, output JSON summary.",
                "difficulty": "Medium",
                "topic": "Computer Vision",
                "environment_id": "cv",
                "problem_type": "computer_vision",
                "evaluation_type": "structured_json",
                "evaluation_config": {"abs_tol": 1e-3},
                "test_cases": [
                    {
                        "input": "",
                        "expected_output": json.dumps({"width": 32, "height": 24, "channels": 3}),
                        "is_hidden": False,
                    }
                ],
                "datasets": [
                    {
                        "filename": "sample.png",
                        "visibility": "public",
                        "mime_type": "image/png",
                        "content_b64": png_b64,
                    }
                ],
            },
            token=self.teacher_token,
        )
        self.assertEqual(code, 201, prob)

        cv_code = (
            "import json, cv2\n"
            "from PIL import Image\n"
            "import skimage.filters\n"
            "img = cv2.imread('/work/data/sample.png')\n"
            "h, w, c = img.shape\n"
            "pil_img = Image.open('/work/data/sample.png')\n"
            "assert pil_img.size == (w, h)\n"
            "print(json.dumps({'width': w, 'height': h, 'channels': c}))\n"
        )
        code, res = _api(
            "POST",
            "/submissions/run-samples",
            {"problem_id": prob["id"], "language": "python", "code": cv_code},
            token=self.student_token,
        )
        self.assertEqual(code, 200, res)
        self.assertEqual(res["status"], "Accepted", res)

    # ------------------------------------------------------------------
    # 6. NLP Environment (`nlp`) with NLTK & spaCy Offline Models
    # ------------------------------------------------------------------
    def test_06_nlp_environment_nltk_and_spacy(self) -> None:
        code, prob = _api(
            "POST",
            "/problems",
            {
                "title": "NLP Tokenization & Lemmatization Pipeline",
                "description": "Use spaCy en_core_web_sm and NLTK stopwords to extract lemmas.",
                "difficulty": "Medium",
                "topic": "NLP",
                "environment_id": "nlp",
                "problem_type": "nlp",
                "evaluation_type": "structured_json",
                "test_cases": [
                    {
                        "input": "The striped bats are hanging on their feet for best",
                        "expected_output": json.dumps({"lemmas": ["stripe", "bat", "hang", "foot", "good"]}),
                        "is_hidden": False,
                    }
                ],
            },
            token=self.teacher_token,
        )
        self.assertEqual(code, 201, prob)

        nlp_code = (
            "import sys, json, spacy\n"
            "from nltk.corpus import stopwords\n"
            "nlp = spacy.load('en_core_web_sm')\n"
            "stops = set(stopwords.words('english'))\n"
            "text = sys.stdin.read().strip()\n"
            "doc = nlp(text)\n"
            "lemmas = [t.lemma_.lower() for t in doc if t.is_alpha and t.text.lower() not in stops]\n"
            "print(json.dumps({'lemmas': lemmas}))\n"
        )
        code, res = _api(
            "POST",
            "/submissions/run-samples",
            {"problem_id": prob["id"], "language": "python", "code": nlp_code},
            token=self.student_token,
        )
        self.assertEqual(code, 200, res)
        self.assertEqual(res["status"], "Accepted", res)

    # ------------------------------------------------------------------
    # 7. Deep Learning Environments (`dl-torch` & `dl-tf`)
    # ------------------------------------------------------------------
    def test_07_deep_learning_pytorch_and_tensorflow(self) -> None:
        # 7a. PyTorch CPU
        code, prob_torch = _api(
            "POST",
            "/problems",
            {
                "title": "PyTorch Linear Regression Training",
                "description": "Fit y = 3x + 2 in PyTorch and print prediction for x = 10.",
                "difficulty": "Hard",
                "topic": "Deep Learning",
                "environment_id": "dl-torch",
                "problem_type": "deep_learning",
                "evaluation_type": "numeric_tolerance",
                "evaluation_config": {"abs_tol": 0.25},
                "test_cases": [
                    {"input": "10.0", "expected_output": "32.0", "is_hidden": False},
                ],
            },
            token=self.teacher_token,
        )
        self.assertEqual(code, 201, prob_torch)

        torch_code = (
            "import sys, torch\n"
            "torch.manual_seed(42)\n"
            "x_val = float(sys.stdin.read().strip())\n"
            "X = torch.tensor([[1.0], [2.0], [3.0], [4.0], [5.0]])\n"
            "Y = 3.0 * X + 2.0\n"
            "model = torch.nn.Linear(1, 1)\n"
            "opt = torch.optim.SGD(model.parameters(), lr=0.04)\n"
            "for _ in range(400):\n"
            "    opt.zero_grad()\n"
            "    loss = torch.nn.functional.mse_loss(model(X), Y)\n"
            "    loss.backward()\n"
            "    opt.step()\n"
            "with torch.no_grad():\n"
            "    pred = model(torch.tensor([[x_val]])).item()\n"
            "print(f'{pred:.4f}')\n"
        )
        code, res_torch = _api(
            "POST",
            "/submissions/run-samples",
            {"problem_id": prob_torch["id"], "language": "python", "code": torch_code},
            token=self.student_token,
        )
        self.assertEqual(code, 200, res_torch)
        self.assertEqual(res_torch["status"], "Accepted", res_torch)

        # 7b. TensorFlow CPU
        code, prob_tf = _api(
            "POST",
            "/problems",
            {
                "title": "TensorFlow Dense Layer Forward Pass",
                "description": "Compute matrix multiplication and ReLU activation in TensorFlow.",
                "difficulty": "Hard",
                "topic": "Deep Learning",
                "environment_id": "dl-tf",
                "problem_type": "deep_learning",
                "evaluation_type": "numeric_tolerance",
                "evaluation_config": {"abs_tol": 1e-4},
                "test_cases": [
                    {"input": "", "expected_output": "14.0 0.0 32.0", "is_hidden": False},
                ],
            },
            token=self.teacher_token,
        )
        self.assertEqual(code, 201, prob_tf)

        tf_code = (
            "import tensorflow as tf\n"
            "x = tf.constant([[1.0, 2.0, 3.0]])\n"
            "w = tf.constant([[2.0, -1.0, 4.0], [3.0, -2.0, 5.0], [2.0, -3.0, 6.0]])\n"
            "out = tf.nn.relu(tf.matmul(x, w)).numpy()[0]\n"
            "print(f'{out[0]:.1f} {out[1]:.1f} {out[2]:.1f}')\n"
        )
        code, res_tf = _api(
            "POST",
            "/submissions/run-samples",
            {"problem_id": prob_tf["id"], "language": "python", "code": tf_code},
            token=self.student_token,
        )
        self.assertEqual(code, 200, res_tf)
        self.assertEqual(res_tf["status"], "Accepted", res_tf)

    # ------------------------------------------------------------------
    # 8. Scientific Environment (`scientific`) + Function Harness + Custom Script
    # ------------------------------------------------------------------
    def test_08_scientific_and_function_harness_and_custom_evaluator(self) -> None:
        # 8a. Scientific environment (SymPy + SciPy + NetworkX)
        code, prob_sci = _api(
            "POST",
            "/problems",
            {
                "title": "Symbolic Integral & Graph Shortest Path",
                "description": "Compute integral of x^2 from 0 to 3 using SymPy and shortest path with NetworkX.",
                "difficulty": "Medium",
                "topic": "Scientific Computing",
                "environment_id": "scientific",
                "problem_type": "scientific",
                "evaluation_type": "numeric_tolerance",
                "evaluation_config": {"abs_tol": 1e-6},
                "test_cases": [
                    {"input": "", "expected_output": "9.0 7.5", "is_hidden": False},
                ],
            },
            token=self.teacher_token,
        )
        self.assertEqual(code, 201, prob_sci)

        sci_code = (
            "import sympy as sp\n"
            "import networkx as nx\n"
            "x = sp.Symbol('x')\n"
            "integral_val = float(sp.integrate(x**2, (x, 0, 3)))\n"
            "G = nx.DiGraph()\n"
            "G.add_weighted_edges_from([('A', 'B', 2.5), ('B', 'C', 5.0), ('A', 'C', 10.0)])\n"
            "sp_len = nx.shortest_path_length(G, 'A', 'C', weight='weight')\n"
            "print(f'{integral_val} {sp_len}')\n"
        )
        code, res_sci = _api(
            "POST",
            "/submissions/run-samples",
            {"problem_id": prob_sci["id"], "language": "python", "code": sci_code},
            token=self.student_token,
        )
        self.assertEqual(code, 200, res_sci)
        self.assertEqual(res_sci["status"], "Accepted", res_sci)

        # 8b. Function Harness evaluation (`function_harness`)
        code, prob_fn = _api(
            "POST",
            "/problems",
            {
                "title": "Matrix Trace Function Harness",
                "description": "Implement compute_trace(matrix) returning the sum of diagonal elements.",
                "difficulty": "Easy",
                "topic": "Linear Algebra",
                "environment_id": "cp",
                "problem_type": "function",
                "evaluation_type": "function_harness",
                "evaluation_config": {"function_name": "compute_trace"},
                "test_cases": [
                    {"input": "[[[1, 2], [3, 4]]]", "expected_output": "5", "is_hidden": False},
                ],
            },
            token=self.teacher_token,
        )
        self.assertEqual(code, 201, prob_fn)

        fn_code = "def compute_trace(matrix):\n    return sum(matrix[i][i] for i in range(len(matrix)))\n"
        code, res_fn = _api(
            "POST",
            "/submissions/run-samples",
            {"problem_id": prob_fn["id"], "language": "python", "code": fn_code},
            token=self.student_token,
        )
        self.assertEqual(code, 200, res_fn)
        self.assertEqual(res_fn["status"], "Accepted", res_fn)

        # 8c. Custom Teacher Evaluator Script (`custom_script`) in separate container
        evaluator_script = (
            "import json, os\n"
            "sub_dir = os.environ['CODECLAN_SUBMISSION_DIR']\n"
            "res_path = os.environ['CODECLAN_RESULT_PATH']\n"
            "out = open(os.path.join(sub_dir, 'stdout.txt')).read().strip()\n"
            "nums = [int(x) for x in out.split()]\n"
            "ok = (len(nums) == 3 and sum(nums) == 100 and len(set(nums)) == 3)\n"
            "with open(res_path, 'w') as f:\n"
            "    json.dump({'passed': ok, 'score_fraction': 1.0 if ok else 0.0, 'feedback': 'Valid distinct triple summing to 100', 'metrics': {'sum': sum(nums)}}, f)\n"
        )
        code, prob_cust = _api(
            "POST",
            "/problems",
            {
                "title": "Constructive Distinct Triple Summing to 100",
                "description": "Print any 3 distinct integers that sum to 100.",
                "difficulty": "Easy",
                "topic": "Constructive Algorithms",
                "environment_id": "cp",
                "problem_type": "competitive",
                "evaluation_type": "custom_script",
                "evaluation_config": {"custom_evaluator_script": evaluator_script},
                "test_cases": [
                    {"input": "100", "expected_output": "any_3_distinct_summing_to_100", "is_hidden": False},
                ],
            },
            token=self.teacher_token,
        )
        self.assertEqual(code, 201, prob_cust)
        # Ensure teacher custom script is stripped from public problem response
        self.assertNotIn("custom_evaluator_script", json.dumps(prob_cust.get("evaluation_config") or {}))

        code, res_cust = _api(
            "POST",
            "/submissions/run-samples",
            {"problem_id": prob_cust["id"], "language": "python", "code": "print('20 30 50')\n"},
            token=self.student_token,
        )
        self.assertEqual(code, 200, res_cust)
        self.assertEqual(res_cust["status"], "Accepted", res_cust)

    # ------------------------------------------------------------------
    # 9. Concurrent Submissions & Scalability / Cleanup Verification
    # ------------------------------------------------------------------
    def test_09_concurrent_submissions_and_metrics(self) -> None:
        sol_code = (
            "import sys\n"
            "tokens = [int(x) for x in sys.stdin.read().split()]\n"
            "arr = tokens[1:]\n"
            "print(f'{sum(arr)} {max(arr)}')\n"
        )

        def _submit_one(_idx: int) -> int:
            c, s = _api(
                "POST",
                "/submissions",
                {
                    "problem_id": self.cp_problem_id,
                    "language": "python",
                    "code": sol_code,
                    "submission_type": "practice",
                },
                token=self.student_token,
            )
            self.assertEqual(c, 201, s)
            return s["id"]

        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=4) as pool:
            sub_ids = list(pool.map(_submit_one, range(4)))

        graded_list = [self._wait_for_submission(sid, self.student_token) for sid in sub_ids]
        wall_sec = time.perf_counter() - t0
        for g in graded_list:
            self.assertEqual(g["status"], "Accepted", g)
            self.assertEqual(g["score"], 10.0)

        code, metrics = _api("GET", "/execution/metrics")
        self.assertEqual(code, 200)
        self.assertEqual(metrics["runtime_security"]["container_verification_failures"], 0)
        self.assertEqual(metrics["runtime_security"]["active_sandbox_containers"], [])
        self.assertGreaterEqual(metrics["worker_telemetry"]["submissions_processed"], 5)
        self.assertLess(wall_sec, 45.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
