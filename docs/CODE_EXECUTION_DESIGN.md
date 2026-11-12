# Code Execution & Automated Grading — Architecture & Security Design

Status: **Implemented & Verified (Phase 2)**

## 1. Overview

Code Clan evaluates student programs using a dedicated, isolated **`grader`** worker service and ephemeral **`codeclan-sandbox:latest`** Docker containers.

Core invariants:

1. **Zero paid APIs:** All compilation and execution runs locally inside self-hosted Docker containers (no Judge0 Cloud, RapidAPI, or third-party paid services).
2. **Never execute student code inside FastAPI:** `backend` (`FastAPI`) only validates requests, persists `Submission` rows (`status="Pending Evaluation"`), and proxies sample-run RPC requests to `grader` over the internal Docker network. `backend` does **not** mount `/var/run/docker.sock`.
3. **Hidden test cases stay server-side:** Public endpoints (`GET /problems`, `GET /problems/{id}`, `POST /submissions/run-samples`, and student calls to `GET /submissions/{id}`) never expose hidden testcase inputs, expected outputs, or actual outputs. Students receive only aggregate hidden testcase counts (`passed / total`). Teachers can inspect full hidden testcase definitions (`GET /problems/{id}/test-cases`) and per-testcase hidden execution results (`teacher_hidden_results` on `GET /submissions/{id}`).
4. **Real evaluation before verdicts, scores, and XP:** Submissions start at `Pending Evaluation` (`score = 0.0`). Only the `grader` worker transitions a submission to `Running` and then to a terminal verdict (`Accepted`, `Wrong Answer`, `Time Limit Exceeded`, `Runtime Error`, `Compilation Error`, or `Internal Evaluation Error`) after running all test cases.

---

## 2. System Architecture

```
Browser (http://localhost:5173)
  │
  │  /api/* proxied by Vite
  ▼
backend (FastAPI, python:3.11-slim, non-root UID 10001, NO docker.sock)
  │
  ├──► POST /submissions ──► MySQL 8.4 (`submissions` table, status='Pending Evaluation')
  │                             ▲
  │                             │ Poll + Atomic Claim (`SELECT ... FOR UPDATE SKIP LOCKED`)
  │                             │ Write `submission_results` + update `submissions` & `coding_test_students`
  │                             ▼
  └──► POST /submissions/run-samples ──(internal HTTP :8090)──► grader (python -m app.grading.worker)
                                                                  │
                                                                  │ `docker run --rm -i --network none --read-only ...`
                                                                  ▼
                                                        codeclan-sandbox:latest
                                                        (/usr/local/bin/sandbox-runner, UID 65534:65534)
```

### Queue & Atomic Claiming

- Pending submissions live in the MySQL `submissions` table (`status = 'Pending Evaluation'`).
- The `grader` worker polls MySQL and claims one submission at a time inside a transaction using:
  ```sql
  SELECT * FROM submissions
  WHERE status = 'Pending Evaluation'
  ORDER BY submitted_at ASC, id ASC
  FOR UPDATE SKIP LOCKED
  LIMIT 1
  ```
- Upon claiming, the worker atomically sets `status = 'Running'`, increments `attempt_count`, and records `started_at = UTC_NOW()`.
- **Crash recovery (`recover_stale_submissions`):** Periodically (and on startup), `grader` scans for rows stuck in `Running` where `started_at` is older than `GRADER_STALE_SECONDS` (default `90s`). If `attempt_count < GRADER_MAX_ATTEMPTS` (default `3`), the submission is re-queued to `Pending Evaluation`; otherwise it is marked `Internal Evaluation Error` so no submission can remain permanently stuck.
- Before writing new `SubmissionResult` rows, `grader` deletes any partial `SubmissionResult` rows for that `submission_id`, guaranteeing idempotency across retries.

---

## 3. Ephemeral Sandbox Security Controls

Each compilation step and each testcase execution runs inside a fresh, disposable container created from `codeclan-sandbox:latest` (`backend/sandbox/Dockerfile`) with `shell=False`:

| Control | Flag / Mechanism | Purpose |
|---|---|---|
| Network isolation | `--network none` | Blocks all outbound/inbound TCP, UDP, DNS, and local network access (cannot reach `mysql`, `backend`, or the internet). |
| Read-only rootfs | `--read-only` | Prevents modifying system binaries, libraries, or writing outside `/work`. |
| Ephemeral workspace | `--tmpfs /work:rw,exec,nosuid,nodev,size=32m,mode=1777` | In-memory workspace wiped automatically when the container exits; no host bind mounts (`-v` is never used). |
| Non-root user | `--user 65534:65534` (`nobody:nogroup`) | Student code runs as an unprivileged user inside the container. |
| Capability drop | `--cap-drop ALL` | Drops all Linux capabilities (`CAP_NET_RAW`, `CAP_SYS_ADMIN`, etc.). |
| No privilege escalation | `--security-opt no-new-privileges` | Prevents setuid/setgid binaries from escalating privileges. |
| Memory limit | `--memory 256m --memory-swap 256m` | Caps RAM at 256 MB with zero swap; OOM kills are detected (`OOMKilled` / exit `137`). |
| CPU limit | `--cpus 0.5` | Prevents CPU starvation on the host. |
| Process / fork-bomb limit | `--pids-limit 64` | Caps concurrent processes/threads to contain fork bombs. |
| Kernel RLIMITs | `sandbox_runner.py` (`resource.setrlimit`) | Sets `RLIMIT_CORE=0`, `RLIMIT_CPU`, `RLIMIT_FSIZE=16MB`, `RLIMIT_NOFILE=64`, and `RLIMIT_AS` (for native/Python processes). |
| Environment scrubbing | `os.environ.clear()` in `sandbox_runner.py` | Only `PATH`, `HOME=/work`, `TMPDIR=/work`, `LANG=C.UTF-8`, and `PYTHONDONTWRITEBYTECODE=1` exist. Database credentials and `SECRET_KEY` are never present. |
| Stdin isolation | `os.memfd_create` in `sandbox_runner.py` | Payload is read from pipe, written into an anonymous in-memory fd, rewound, and bound to `fd 0` before `os.execvpe` — student code never sees the JSON framing or expected output. |
| Output truncation | Bounded stream reader (`MAX_OUTPUT_BYTES = 65536`) | Caps `stdout` and `stderr` at 64 KB each; programs flooding stdout are killed and flagged as `Runtime Error (Output Limit Exceeded)`. |
| Wall-clock timeout | `GRADER_RUN_TIMEOUT_SEC` (default `2.5s` per test case, `10s` compile) | Kills timed-out containers with `docker rm -f <container_name>` and returns `Time Limit Exceeded`. |

---

## 4. Supported Languages

| Language | Identifier | Compile Step (inside sandbox) | Execute Step (per testcase inside sandbox) |
|---|---|---|---|
| **Python 3.11** | `python` | `python3 -I -B -m py_compile /work/solution.py` | `python3 -I -B /work/solution.py` |
| **C (C11)** | `c` | `gcc -O2 -std=c11 -pipe /work/solution.c -lm -o /work/solution.out` | `/work/solution.out` |
| **C++ (C++17)** | `cpp` | `g++ -O2 -std=c++17 -pipe /work/solution.cpp -lm -o /work/solution.out` | `/work/solution.out` |
| **Java (OpenJDK)** | `java` | `javac -encoding UTF-8 -d /work /work/Main.java` (packaged to `solution.jar`) | `java -Xmx192m -XX:+UseSerialGC -cp /work Main` |
| **JavaScript (Node.js)** | `javascript` | `node --check /work/solution.js` | `node --max-old-space-size=192 /work/solution.js` |

Compiled artifacts (`/work/solution.out` or `/work/solution.jar`) are produced once per submission in a dedicated compile sandbox container, base64-transferred in memory to the worker, and injected into `/work` for each testcase run container.

---

## 5. Output Comparison Policy

Implemented in [`backend/app/grading/comparison.py`](../backend/app/grading/comparison.py):

1. Convert `\r\n` and `\r` line endings to `\n`.
2. Strip trailing spaces and tabs (`[ \t]+`) from the end of each line.
3. Strip trailing empty lines at the end of the output.
4. Preserve leading whitespace, internal whitespace, and character case.

---

## 6. Scoring & XP Formula

- **Submission Score:**
  $$\text{score} = \text{round}\left(\text{max\_score} \times \frac{\text{passed\_count}}{\text{total\_count}},\, 2\right)$$
  - Practice and assignment problems default to `max_score = 10.0`.
  - Coding-test problems use `CodingTestProblem.marks` (default `10.0`).
- **Coding Test Total Score:**
  - For each problem in a coding test, the student's **best evaluated score** among their `coding_test` submissions for that test is summed and saved in `CodingTestStudent.score`.
- **Student XP (`_compute_student_xp_and_stats`):**
  - **Practice / Assignment XP:** Sum of $\text{round}(10 \times \text{best\_pass\_ratio})$ across each distinct problem the student has evaluated outside coding tests.
  - **Coding Test XP:** Sum of $\text{round}(\text{best\_problem\_score})$ across each distinct coding-test problem the student has evaluated.
  - **Idempotency:** XP is computed deterministically from evaluated pass ratios and best problem scores. Re-submitting the same problem, retrying a worker job, or calling `POST /coding-tests/{id}/complete` multiple times never inflates XP. Submitting ungraded or zero-pass code awards `0 XP`.

---

## 7. Remaining Risks & Production Hardening Notes

While this architecture isolates student code from FastAPI, MySQL, and other students' submissions, **Docker containers share the host Linux kernel**:

- **`grader` Docker socket access:** The `grader` container mounts `/var/run/docker.sock` so it can launch sibling `codeclan-sandbox:latest` containers. Although `backend`, `frontend`, and `sandbox` do **not** have access to the Docker socket, a compromise of the `grader` process itself would grant access to the Docker daemon.
- **Recommended production upgrades:**
  1. Run `grader` on a dedicated isolated VM/host separate from the MySQL database and FastAPI server.
  2. Place a read/create-restricted Docker socket proxy (e.g. `tecnativa/docker-socket-proxy`) or use rootless Docker/Podman.
  3. Use a kernel-isolating container runtime (`--runtime=runsc` with **gVisor** or **Firecracker** microVMs) for untrusted public internet workloads.
