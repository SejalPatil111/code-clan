"""
Isolated sandbox execution engine using ephemeral Docker containers.

Every compilation and every single test case runs inside a brand-new, disposable
container launched from `codeclan-sandbox:latest` with:
  - `--network none` (complete network isolation)
  - `--read-only` root filesystem
  - `--tmpfs /work:rw,exec,nosuid,nodev,size=32m,mode=1777` (ephemeral RAM workspace)
  - `--memory 256m --memory-swap 256m` (hard memory ceiling, no swap)
  - `--cpus 0.5` (CPU quota)
  - `--pids-limit 64` (fork-bomb protection)
  - `--cap-drop ALL` and `--security-opt no-new-privileges`
  - `--user 65534:65534` (unprivileged `nobody:nogroup`)
  - No host filesystem mounts (`-v` is never used)
  - No Docker socket inside the sandbox
  - `shell=False` everywhere
"""

import base64
from dataclasses import dataclass
import json
import logging
import os
import subprocess
import threading
import time
from typing import List, Optional
import uuid

from app.grading.comparison import (
    MAX_SOURCE_CODE_BYTES,
    STATUS_ACCEPTED,
    STATUS_COMPILATION_ERROR,
    STATUS_INTERNAL_ERROR,
    STATUS_RUNTIME_ERROR,
    STATUS_TLE,
    STATUS_WRONG_ANSWER,
    compare_outputs,
    normalize_language,
)

logger = logging.getLogger("codeclan.sandbox")

SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "codeclan-sandbox:latest")
COMPILE_TIMEOUT_SECONDS = float(os.getenv("SANDBOX_COMPILE_TIMEOUT", "10.0"))
RUN_TIMEOUT_SECONDS = float(os.getenv("SANDBOX_RUN_TIMEOUT", "3.0"))
MEMORY_LIMIT_MB = int(os.getenv("SANDBOX_MEMORY_MB", "256"))
CPU_LIMIT = os.getenv("SANDBOX_CPUS", "0.5")
PIDS_LIMIT = int(os.getenv("SANDBOX_PIDS_LIMIT", "64"))
MAX_OUTPUT_BYTES = int(os.getenv("SANDBOX_MAX_OUTPUT_BYTES", str(64 * 1024)))  # 64 KB
MAX_ERROR_CHARS = 4000


@dataclass
class CompileResult:
    ok: bool
    artifact_b64: str = ""
    error_message: Optional[str] = None
    status: str = STATUS_ACCEPTED


@dataclass
class SingleTestExecutionResult:
    status: str
    passed: bool
    actual_output: str
    execution_time_ms: float
    error_message: Optional[str] = None


def _force_remove_container(container_name: str) -> None:
    try:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            shell=False,
        )
    except Exception:
        pass


def _run_bounded_process(
    cmd: List[str],
    stdin_bytes: bytes,
    timeout_sec: float,
    max_output_bytes: int,
    container_name: str,
) -> dict:
    """
    Run `cmd` (`shell=False`), stream `stdin_bytes`, read stdout/stderr up to
    `max_output_bytes`, and enforce `timeout_sec`. Kills the container if either
    the wall-clock timeout or the output cap is exceeded.
    """
    start_ts = time.perf_counter()
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
    except FileNotFoundError as exc:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Docker CLI not found: {exc}",
            "timed_out": False,
            "output_exceeded": False,
            "elapsed_ms": 0.0,
            "internal_error": True,
        }
    except Exception as exc:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Failed to start sandbox container: {exc}",
            "timed_out": False,
            "output_exceeded": False,
            "elapsed_ms": 0.0,
            "internal_error": True,
        }

    stdout_chunks: List[bytes] = []
    stderr_chunks: List[bytes] = []
    stdout_total = 0
    stderr_total = 0
    output_exceeded = False

    def _read_stream(pipe, chunks: List[bytes], is_stdout: bool):
        nonlocal stdout_total, stderr_total, output_exceeded
        try:
            while True:
                chunk = pipe.read(4096)
                if not chunk:
                    break
                if is_stdout:
                    if stdout_total < max_output_bytes:
                        take = min(len(chunk), max_output_bytes - stdout_total)
                        chunks.append(chunk[:take])
                    stdout_total += len(chunk)
                    if stdout_total > max_output_bytes and not output_exceeded:
                        output_exceeded = True
                        _force_remove_container(container_name)
                        try:
                            proc.kill()
                        except Exception:
                            pass
                        break
                else:
                    if stderr_total < max_output_bytes:
                        take = min(len(chunk), max_output_bytes - stderr_total)
                        chunks.append(chunk[:take])
                    stderr_total += len(chunk)
                    if stderr_total > max_output_bytes and not output_exceeded:
                        output_exceeded = True
                        _force_remove_container(container_name)
                        try:
                            proc.kill()
                        except Exception:
                            pass
                        break
        except Exception:
            pass
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    t_out = threading.Thread(target=_read_stream, args=(proc.stdout, stdout_chunks, True), daemon=True)
    t_err = threading.Thread(target=_read_stream, args=(proc.stderr, stderr_chunks, False), daemon=True)
    t_out.start()
    t_err.start()

    try:
        if proc.stdin:
            try:
                proc.stdin.write(stdin_bytes)
            except BrokenPipeError:
                pass
            finally:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
    except Exception:
        pass

    timed_out = False
    try:
        proc.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        timed_out = True
        _force_remove_container(container_name)
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            pass

    t_out.join(timeout=2)
    t_err.join(timeout=2)
    elapsed_ms = round((time.perf_counter() - start_ts) * 1000.0, 2)

    stdout_str = b"".join(stdout_chunks).decode("utf-8", errors="replace")
    stderr_str = b"".join(stderr_chunks).decode("utf-8", errors="replace")

    return {
        "returncode": proc.returncode if proc.returncode is not None else -1,
        "stdout": stdout_str,
        "stderr": stderr_str,
        "timed_out": timed_out,
        "output_exceeded": output_exceeded,
        "elapsed_ms": elapsed_ms,
        "internal_error": False,
    }


def _build_docker_run_cmd(container_name: str, mode: str) -> List[str]:
    return [
        "docker",
        "run",
        "--rm",
        "-i",
        "--name",
        container_name,
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/work:rw,exec,nosuid,nodev,size=32m,mode=1777",
        "--workdir",
        "/work",
        "--memory",
        f"{MEMORY_LIMIT_MB}m",
        "--memory-swap",
        f"{MEMORY_LIMIT_MB}m",
        "--cpus",
        str(CPU_LIMIT),
        "--pids-limit",
        str(PIDS_LIMIT),
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        "65534:65534",
        SANDBOX_IMAGE,
        "/usr/local/bin/sandbox-runner",
        mode,
    ]


class SandboxExecutor:
    """Executes compilation and individual test cases inside isolated Docker containers."""

    def compile_source(self, language: str, code: str) -> CompileResult:
        norm_lang = normalize_language(language)
        if not norm_lang:
            return CompileResult(
                ok=False,
                error_message=f"Unsupported language: {language}",
                status=STATUS_COMPILATION_ERROR,
            )

        if len(code.encode("utf-8")) > MAX_SOURCE_CODE_BYTES:
            return CompileResult(
                ok=False,
                error_message=f"Source code exceeds maximum allowed size ({MAX_SOURCE_CODE_BYTES} bytes).",
                status=STATUS_COMPILATION_ERROR,
            )

        container_name = f"codeclan-sbx-cmp-{uuid.uuid4().hex[:12]}"
        payload = {
            "language": norm_lang,
            "code_b64": base64.b64encode(code.encode("utf-8")).decode("ascii"),
        }
        cmd = _build_docker_run_cmd(container_name, "compile")
        res = _run_bounded_process(
            cmd=cmd,
            stdin_bytes=json.dumps(payload).encode("utf-8"),
            timeout_sec=COMPILE_TIMEOUT_SECONDS,
            max_output_bytes=MAX_OUTPUT_BYTES * 4,  # allow base64 compiled binary tar
            container_name=container_name,
        )

        if res["internal_error"]:
            return CompileResult(
                ok=False,
                error_message=res["stderr"][:MAX_ERROR_CHARS],
                status=STATUS_INTERNAL_ERROR,
            )

        if res["timed_out"]:
            return CompileResult(
                ok=False,
                error_message=f"Compilation timed out after {COMPILE_TIMEOUT_SECONDS}s.",
                status=STATUS_COMPILATION_ERROR,
            )

        if res["returncode"] != 0:
            err = (res["stderr"] or res["stdout"] or "Compilation failed.").strip()
            if "Cannot connect to the Docker daemon" in err or "Unable to find image" in err:
                return CompileResult(
                    ok=False,
                    error_message=f"Sandbox unavailable: {err[:MAX_ERROR_CHARS]}",
                    status=STATUS_INTERNAL_ERROR,
                )
            return CompileResult(
                ok=False,
                error_message=err[:MAX_ERROR_CHARS],
                status=STATUS_COMPILATION_ERROR,
            )

        try:
            data = json.loads(res["stdout"])
            return CompileResult(ok=True, artifact_b64=data.get("artifact_b64", ""))
        except Exception as exc:
            return CompileResult(
                ok=False,
                error_message=f"Invalid compiler output from sandbox: {exc}",
                status=STATUS_INTERNAL_ERROR,
            )

    def run_single_test(
        self,
        language: str,
        code: str,
        artifact_b64: str,
        test_input: str,
        expected_output: str,
        timeout_sec: Optional[float] = None,
    ) -> SingleTestExecutionResult:
        norm_lang = normalize_language(language)
        if not norm_lang:
            return SingleTestExecutionResult(
                status=STATUS_COMPILATION_ERROR,
                passed=False,
                actual_output="",
                execution_time_ms=0.0,
                error_message=f"Unsupported language: {language}",
            )

        wall_timeout = timeout_sec if timeout_sec is not None else RUN_TIMEOUT_SECONDS
        cpu_limit_int = max(1, int(wall_timeout) + 1)

        container_name = f"codeclan-sbx-run-{uuid.uuid4().hex[:12]}"
        payload = {
            "language": norm_lang,
            "code_b64": base64.b64encode(code.encode("utf-8")).decode("ascii") if norm_lang in ("python", "javascript") else "",
            "artifact_b64": artifact_b64,
            "stdin_b64": base64.b64encode((test_input or "").encode("utf-8")).decode("ascii"),
            "cpu_limit_sec": cpu_limit_int,
            "fsize_limit_mb": 4,
            "memory_limit_mb": MEMORY_LIMIT_MB,
        }
        cmd = _build_docker_run_cmd(container_name, "run")
        res = _run_bounded_process(
            cmd=cmd,
            stdin_bytes=json.dumps(payload).encode("utf-8"),
            timeout_sec=wall_timeout,
            max_output_bytes=MAX_OUTPUT_BYTES,
            container_name=container_name,
        )

        if res["internal_error"]:
            return SingleTestExecutionResult(
                status=STATUS_INTERNAL_ERROR,
                passed=False,
                actual_output="",
                execution_time_ms=res["elapsed_ms"],
                error_message=res["stderr"][:MAX_ERROR_CHARS],
            )

        if res["output_exceeded"]:
            return SingleTestExecutionResult(
                status=STATUS_RUNTIME_ERROR,
                passed=False,
                actual_output=res["stdout"][:2000],
                execution_time_ms=res["elapsed_ms"],
                error_message=f"Output Limit Exceeded: program produced more than {MAX_OUTPUT_BYTES // 1024} KB of output.",
            )

        if res["timed_out"] or res["returncode"] == 152:  # 152 = 128 + SIGXCPU(24)
            return SingleTestExecutionResult(
                status=STATUS_TLE,
                passed=False,
                actual_output=res["stdout"][:2000],
                execution_time_ms=round(wall_timeout * 1000.0, 2),
                error_message=f"Time Limit Exceeded (>{wall_timeout:.1f}s).",
            )

        rc = res["returncode"]
        stderr_clean = (res["stderr"] or "").strip()

        if rc != 0:
            if "Cannot connect to the Docker daemon" in stderr_clean or "Unable to find image" in stderr_clean:
                return SingleTestExecutionResult(
                    status=STATUS_INTERNAL_ERROR,
                    passed=False,
                    actual_output="",
                    execution_time_ms=res["elapsed_ms"],
                    error_message=f"Sandbox unavailable: {stderr_clean[:MAX_ERROR_CHARS]}",
                )
            if rc == 137 or "MemoryError" in stderr_clean or "bad_alloc" in stderr_clean or "OutOfMemoryError" in stderr_clean:
                msg = "Memory Limit Exceeded (256 MB)."
                if stderr_clean:
                    msg = f"{msg}\n{stderr_clean[:MAX_ERROR_CHARS]}"
                return SingleTestExecutionResult(
                    status=STATUS_RUNTIME_ERROR,
                    passed=False,
                    actual_output=res["stdout"][:2000],
                    execution_time_ms=res["elapsed_ms"],
                    error_message=msg,
                )
            if rc == 153:  # SIGXFSZ
                return SingleTestExecutionResult(
                    status=STATUS_RUNTIME_ERROR,
                    passed=False,
                    actual_output=res["stdout"][:2000],
                    execution_time_ms=res["elapsed_ms"],
                    error_message="Output / file size limit exceeded.",
                )
            return SingleTestExecutionResult(
                status=STATUS_RUNTIME_ERROR,
                passed=False,
                actual_output=res["stdout"][:2000],
                execution_time_ms=res["elapsed_ms"],
                error_message=(stderr_clean or f"Process exited with non-zero code {rc}")[:MAX_ERROR_CHARS],
            )

        matched = compare_outputs(res["stdout"], expected_output)
        return SingleTestExecutionResult(
            status=STATUS_ACCEPTED if matched else STATUS_WRONG_ANSWER,
            passed=matched,
            actual_output=res["stdout"],
            execution_time_ms=res["elapsed_ms"],
            error_message=None,
        )
