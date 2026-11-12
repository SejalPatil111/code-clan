"""
CodeClan Phase 3 — Automated Security Verification Suite.

Verifies all 13 security, isolation, resource-limit, hidden-testcase,
cross-student authorization, cleanup, and runtime-honesty invariants against
the live Docker Compose stack.

Run from repository root:
    python backend/tests/test_security_verification.py
"""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE_URL = "http://localhost:8000"


def _req(method: str, path: str, token: str | None = None, body: dict | None = None) -> tuple[int, dict | list]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"detail": raw}


def _ensure_user(name: str, email: str, password: str, role: str) -> tuple[str, dict]:
    code, data = _req("POST", "/auth/login", body={"email": email, "password": password})
    if code == 200:
        return data["access_token"], data["user"]
    code, data = _req(
        "POST",
        "/auth/register",
        body={"name": name, "email": email, "password": password, "role": role},
    )
    assert code in (200, 201), f"Auth failed for {email}: {code} {data}"
    return data["access_token"], data["user"]


def _wait_for_submission(sub_id: int, token: str, timeout_sec: float = 30.0) -> dict:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        code, sub = _req("GET", f"/submissions/{sub_id}", token=token)
        assert code == 200, f"Failed polling submission {sub_id}: {code} {sub}"
        if sub["status"] not in ("Pending", "Running"):
            return sub
        time.sleep(0.6)
    raise TimeoutError(f"Submission {sub_id} did not finish within {timeout_sec}s")


def main() -> int:
    results: list[tuple[str, bool, str]] = []

    def record(name: str, passed: bool, detail: str) -> None:
        tag = "PASS" if passed else "FAIL"
        print(f"[{tag}] {name}: {detail}")
        results.append((name, passed, detail))

    print("=" * 78)
    print("CodeClan Phase 3 — Automated Sandbox & Deployment Security Verification")
    print("=" * 78)

    # Authenticate or register test accounts
    teacher_token, teacher_user = _ensure_user("Sec Teacher", "sec.teacher@codeclan.edu", "teacher123", "teacher")
    student1_token, student1_user = _ensure_user("Sec Student 1", "sec.student1@codeclan.edu", "student123", "student")
    student2_token, student2_user = _ensure_user("Sec Student 2", "sec.student2@codeclan.edu", "student123", "student")

    # Fetch problems and ensure Problem #1 has a known hidden test case
    code, problems = _req("GET", "/problems", token=student1_token)
    assert code == 200 and len(problems) > 0, "No problems found"
    prob_id = problems[0]["id"]

    # 1. Runtime Security Honesty & Fail-Closed Production Mode Verification
    code, sec_status = _req("GET", "/execution/security-status", token=student1_token)
    assert code == 200, f"/execution/security-status failed: {code} {sec_status}"
    if sec_status.get("active_runtime") == "runsc" and sec_status.get("gvisor_verified") is True:
        honesty_ok = (
            sec_status.get("production_secure") is True
            and sec_status.get("fallback_active") is False
            and sec_status.get("blocked") is False
        )
    else:
        # On Windows Docker Desktop (`runc`), must NEVER claim gVisor is verified or production-secure
        honesty_ok = (
            sec_status.get("gvisor_verified") is False
            and sec_status.get("fallback_active") is True
            and sec_status.get("production_secure") is False
            and "NOT_PRODUCTION_SECURE" in sec_status.get("security_mode", "")
        )
    record(
        "1. Runtime Security Status Honesty",
        honesty_ok,
        f"active_runtime={sec_status.get('active_runtime')}, gvisor_verified={sec_status.get('gvisor_verified')}, "
        f"production_secure={sec_status.get('production_secure')}, mode={sec_status.get('security_mode')}",
    )

    # Verify fail-closed behavior when EXECUTION_ENV=production & SANDBOX_REQUIRE_GVISOR=true on a non-gVisor host
    if not sec_status.get("gvisor_verified"):
        probe_py = (
            "from app.grading.sandbox import SandboxExecutor; "
            "ex = SandboxExecutor(execution_env='production', requested_runtime='runsc', require_gvisor=True, allow_dev_fallback=False); "
            "st = ex.get_runtime_status(); "
            "cmp = ex.compile_source('python', 'print(1)'); "
            "import json; "
            "print(json.dumps({'blocked': st.blocked, 'production_secure': st.production_secure, 'mode': st.security_mode, 'cmp_ok': cmp.ok, 'cmp_status': cmp.status}))"
        )
        proc = subprocess.run(
            ["docker", "compose", "exec", "-T", "grader", "python", "-c", probe_py],
            capture_output=True,
            text=True,
            timeout=20,
            shell=False,
        )
        fail_closed_data = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.returncode == 0 and proc.stdout.strip() else {}
        fail_closed_ok = (
            fail_closed_data.get("blocked") is True
            and fail_closed_data.get("production_secure") is False
            and fail_closed_data.get("cmp_ok") is False
            and "Internal" in (fail_closed_data.get("cmp_status") or "")
        )
        record(
            "2. Fail-Closed Production Mode Enforcement (when runsc unavailable)",
            fail_closed_ok,
            f"blocked={fail_closed_data.get('blocked')}, mode={fail_closed_data.get('mode')}, cmp_status={fail_closed_data.get('cmp_status')}",
        )
    else:
        record(
            "2. Fail-Closed Production Mode Enforcement",
            True,
            "Host has verified gVisor (runsc) active",
        )

    # 3. Network Access Attempts Blocked (External Internet + Internal Docker Services)
    net_code = """
import socket, sys
targets = [("1.1.1.1", 53), ("8.8.8.8", 80), ("mysql", 3306), ("backend", 8000), ("grader", 8090)]
for host, port in targets:
    try:
        s = socket.create_connection((host, port), timeout=1.0)
        s.close()
        print(f"BREACH:{host}:{port}")
        sys.exit(0)
    except Exception:
        pass
print("NETWORK_BLOCKED_OK")
"""
    code, net_res = _req(
        "POST",
        "/submissions/run-samples",
        token=student1_token,
        body={"problem_id": prob_id, "language": "python", "code": net_code},
    )
    assert code == 200, f"run-samples failed: {code} {net_res}"
    first_out = (net_res.get("results") or [{}])[0].get("actual_output", "").strip()
    net_ok = first_out == "NETWORK_BLOCKED_OK" and "BREACH" not in first_out
    record("3. Network Isolation (--network none, external & internal blocked)", net_ok, f"output={first_out!r}")

    # 4. Filesystem Read-Only Root, /tmp noexec, Non-Root UID 65534, Capabilities Dropped
    fs_code = """
import os, subprocess, sys
checks = []
# 1) UID/GID must be 65534 (nobody)
checks.append(f"uid={os.getuid()},gid={os.getgid()}")
# 2) Root filesystem must be read-only
for p in ["/etc/pwn_test", "/usr/local/bin/pwn_test", "/root/pwn_test"]:
    try:
        with open(p, "w") as f:
            f.write("x")
        checks.append(f"BREACH_WRITE:{p}")
    except Exception:
        checks.append(f"RO_OK:{p}")
# 3) /tmp must block executable scripts (noexec)
sh_path = "/tmp/evil.sh"
with open(sh_path, "w") as f:
    f.write("#!/bin/sh\\necho EVIL_EXEC\\n")
os.chmod(sh_path, 0o755)
try:
    subprocess.check_output([sh_path], stderr=subprocess.STDOUT)
    checks.append("BREACH_TMP_EXEC")
except PermissionError:
    checks.append("TMP_NOEXEC_OK")
except Exception as e:
    checks.append(f"TMP_NOEXEC_OK:{type(e).__name__}")
# 4) Verify CapEff == 0 and NoNewPrivs == 1
with open("/proc/self/status") as f:
    status_txt = f.read()
for line in status_txt.splitlines():
    if line.startswith(("CapEff:", "NoNewPrivs:")):
        checks.append(line.replace("\\t", "="))
print("|".join(checks))
"""
    code, fs_res = _req(
        "POST",
        "/submissions/run-samples",
        token=student1_token,
        body={"problem_id": prob_id, "language": "python", "code": fs_code},
    )
    fs_out = (fs_res.get("results") or [{}])[0].get("actual_output", "").strip()
    fs_ok = (
        "uid=65534,gid=65534" in fs_out
        and "BREACH" not in fs_out
        and "TMP_NOEXEC_OK" in fs_out
        and "CapEff:=0000000000000000" in fs_out
        and "NoNewPrivs:=1" in fs_out
    )
    record("4. Filesystem & Privilege Hardening (RO root, /tmp noexec, UID 65534, CapEff=0)", fs_ok, fs_out)

    # 5. Environment Variable Isolation (No DB Credentials or Secret Keys Leaked)
    env_code = """
import json, os
print(json.dumps(sorted(os.environ.keys())))
"""
    code, env_res = _req(
        "POST",
        "/submissions/run-samples",
        token=student1_token,
        body={"problem_id": prob_id, "language": "python", "code": env_code},
    )
    env_out = (env_res.get("results") or [{}])[0].get("actual_output", "").strip()
    env_keys = json.loads(env_out) if env_out.startswith("[") else []
    forbidden_keys = {"DATABASE_URL", "MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD", "SECRET_KEY", "GRADER_URL"}
    allowed_safe_keys = {"HOME", "LANG", "LC_ALL", "PATH", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED", "TMPDIR"}
    env_ok = len(env_keys) > 0 and forbidden_keys.isdisjoint(set(env_keys)) and set(env_keys) <= allowed_safe_keys
    record("5. Environment Variable Sanitization (Zero Secrets in Sandbox)", env_ok, f"keys={env_keys}")

    # 6. Infinite Loop Termination (Wall-Clock & CPU Timeout)
    tle_code = "while True:\n    pass\n"
    t0 = time.perf_counter()
    code, tle_res = _req(
        "POST",
        "/submissions/run-samples",
        token=student1_token,
        body={"problem_id": prob_id, "language": "python", "code": tle_code},
    )
    tle_elapsed = round(time.perf_counter() - t0, 2)
    tle_ok = code == 200 and tle_res.get("status") == "Time Limit Exceeded"
    record("6. Infinite Loop Containment (Time Limit Exceeded)", tle_ok, f"status={tle_res.get('status')}, wall={tle_elapsed}s")

    # 7. Memory Exhaustion Containment (256 MB Limit)
    mem_code = "x = bytearray(320 * 1024 * 1024)\nprint(len(x))\n"
    code, mem_res = _req(
        "POST",
        "/submissions/run-samples",
        token=student1_token,
        body={"problem_id": prob_id, "language": "python", "code": mem_code},
    )
    mem_ok = (
        code == 200
        and mem_res.get("status") == "Runtime Error"
        and ("Memory Limit Exceeded" in (mem_res.get("error_message") or "") or "MemoryError" in (mem_res.get("error_message") or ""))
    )
    record("7. Memory Exhaustion Containment (256 MB Cap)", mem_ok, f"status={mem_res.get('status')}, err={(mem_res.get('error_message') or '')[:80]!r}")

    # 8. Fork Bomb Containment (--pids-limit 64 & RLIMIT_NPROC=32)
    fork_code = """
import os
forked = 0
try:
    for _ in range(200):
        pid = os.fork()
        if pid == 0:
            os._exit(0)
        forked += 1
except BlockingIOError:
    print("FORK_BOMB_BLOCKED_EAGAIN")
except OSError as e:
    print(f"FORK_BOMB_BLOCKED_OSERROR:{e.errno}")
else:
    print(f"FORKED_ALL:{forked}")
"""
    code, fork_res = _req(
        "POST",
        "/submissions/run-samples",
        token=student1_token,
        body={"problem_id": prob_id, "language": "python", "code": fork_code},
    )
    fork_out = (fork_res.get("results") or [{}])[0].get("actual_output", "").strip()
    fork_ok = "FORK_BOMB_BLOCKED" in fork_out or fork_res.get("status") == "Runtime Error"
    record("8. Fork Bomb Containment (pids.max=64 & RLIMIT_NPROC=32)", fork_ok, f"status={fork_res.get('status')}, out={fork_out!r}")

    # 9. Excessive Output Containment (64 KB Cap)
    out_flood_code = """
import sys
chunk = "A" * 8192 + "\\n"
for _ in range(1024):
    sys.stdout.write(chunk)
    sys.stdout.flush()
"""
    code, flood_res = _req(
        "POST",
        "/submissions/run-samples",
        token=student1_token,
        body={"problem_id": prob_id, "language": "python", "code": out_flood_code},
    )
    flood_ok = (
        code == 200
        and flood_res.get("status") == "Runtime Error"
        and "Output Limit Exceeded" in (flood_res.get("error_message") or "")
    )
    record("9. Excessive Output Containment (64 KB Cap)", flood_ok, f"status={flood_res.get('status')}, err={flood_res.get('error_message')!r}")

    # 10. File Descriptor & Disk Write Limit Containment (RLIMIT_NOFILE=64 & RLIMIT_FSIZE)
    fd_code = """
fds = []
try:
    for i in range(200):
        fds.append(open(f"/work/f_{i}.txt", "w"))
    print("BREACH_FD_LIMIT")
except OSError:
    print(f"FD_LIMIT_ENFORCED:{len(fds)}")
finally:
    for f in fds:
        f.close()
"""
    code, fd_res = _req(
        "POST",
        "/submissions/run-samples",
        token=student1_token,
        body={"problem_id": prob_id, "language": "python", "code": fd_code},
    )
    fd_out = (fd_res.get("results") or [{}])[0].get("actual_output", "").strip()
    fd_ok = "FD_LIMIT_ENFORCED" in fd_out and "BREACH" not in fd_out
    record("10. File Descriptor Limit Enforcement (RLIMIT_NOFILE=64)", fd_ok, f"out={fd_out!r}")

    # 11. Isolation Between Consecutive Executions (Ephemeral Container State)
    write_state_code = """
with open("/work/persisted_secret.txt", "w") as f:
    f.write("TOP_SECRET_123")
with open("/tmp/persisted_secret.txt", "w") as f:
    f.write("TOP_SECRET_123")
print("WROTE_MARKER")
"""
    check_state_code = """
import os
leaked = os.path.exists("/work/persisted_secret.txt") or os.path.exists("/tmp/persisted_secret.txt")
print("LEAKED" if leaked else "CLEAN_ISOLATED_WORKSPACE")
"""
    _req("POST", "/submissions/run-samples", token=student1_token, body={"problem_id": prob_id, "language": "python", "code": write_state_code})
    code, iso_res = _req("POST", "/submissions/run-samples", token=student1_token, body={"problem_id": prob_id, "language": "python", "code": check_state_code})
    iso_out = (iso_res.get("results") or [{}])[0].get("actual_output", "").strip()
    iso_ok = iso_out == "CLEAN_ISOLATED_WORKSPACE"
    record("11. Isolation Between Consecutive Executions (Zero State Persistence)", iso_ok, f"out={iso_out!r}")

    # 12. Hidden Test Case Protection & Teacher-Only Visibility
    # Add a unique secret hidden test case as teacher, then submit a failing solution as student1
    secret_marker = f"HIDDEN_SECRET_MARKER_{int(time.time())}"
    _req(
        "POST",
        f"/problems/{prob_id}/test-cases",
        token=teacher_token,
        body={"input": secret_marker, "expected_output": "999999", "is_hidden": True},
    )
    # Check student problem endpoints
    _, prob_detail_student = _req("GET", f"/problems/{prob_id}", token=student1_token)
    student_tc_Check = secret_marker not in json.dumps(prob_detail_student)
    # Check student submission response
    _, sub_created = _req(
        "POST",
        "/submissions",
        token=student1_token,
        body={"problem_id": prob_id, "language": "python", "code": "print(input())", "submission_type": "practice"},
    )
    sub_final = _wait_for_submission(sub_created["id"], student1_token)
    sub_student_json = json.dumps(sub_final)
    hidden_safe = (
        student_tc_Check
        and secret_marker not in sub_student_json
        and "999999" not in sub_student_json
        and sub_final.get("teacher_hidden_results") is None
        and (sub_final.get("hidden_summary") or {}).get("total", 0) >= 1
    )
    record(
        "12. Hidden Test Case Confidentiality (Never Leaked to Student API)",
        hidden_safe,
        f"hidden_summary={sub_final.get('hidden_summary')}, leaked_in_json={secret_marker in sub_student_json}",
    )

    # 13. Cross-Student Submission Isolation (403 Forbidden)
    code_by_id, _ = _req("GET", f"/submissions/{sub_created['id']}", token=student2_token)
    code_by_filter, _ = _req("GET", f"/submissions?user_id={student1_user['id']}", token=student2_token)
    cross_ok = code_by_id == 403 and code_by_filter == 403
    record(
        "13. Cross-Student Submission Isolation (HTTP 403 Forbidden)",
        cross_ok,
        f"GET /submissions/{sub_created['id']} -> {code_by_id}, GET /submissions?user_id={student1_user['id']} -> {code_by_filter}",
    )

    # 14. Guaranteed Container Cleanup After All Failures & Timeouts
    time.sleep(0.5)
    _, sec_after = _req("GET", "/execution/security-status", token=student1_token)
    lingering = sec_after.get("active_sandbox_containers", [])
    cleanup_ok = len(lingering) == 0
    record(
        "14. Automatic Sandbox Container Cleanup After Failures & Timeouts",
        cleanup_ok,
        f"active_sandbox_containers={lingering}",
    )

    print("=" * 78)
    passed_all = all(ok for _, ok, _ in results)
    print(f"Summary: {sum(1 for _, ok, _ in results if ok)}/{len(results)} security checks PASSED")
    print("=" * 78)
    return 0 if passed_all else 1


if __name__ == "__main__":
    sys.exit(main())
