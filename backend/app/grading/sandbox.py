"""
Isolated sandbox execution engine using gVisor (`runsc`) or an explicit,
non-production Docker (`runc`) development fallback.

Every compilation and every single test case runs inside a brand-new, disposable
container launched from `codeclan-sandbox:latest` with:
  - `--runtime runsc` (gVisor user-space kernel on supported Linux hosts; or explicit
    `runc` development fallback when `EXECUTION_ENV=development` and
    `SANDBOX_ALLOW_DEV_FALLBACK=true`)
  - `--network none` (complete network isolation)
  - `--ipc none` (private/disabled IPC namespace)
  - `--read-only` root filesystem
  - `--tmpfs /work:rw,exec,nosuid,nodev,size=32m,mode=1777` (ephemeral RAM workspace)
  - `--tmpfs /tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777` (noexec scratch tmpfs)
  - `--memory 256m --memory-swap 256m` (hard memory ceiling, zero swap)
  - `--cpus 0.5` (CPU quota)
  - `--pids-limit 64` (cgroup fork-bomb ceiling)
  - `--ulimit nofile=64:64`, `--ulimit nproc=64:64`, `--ulimit fsize=16777216:16777216`, `--ulimit core=0:0`
  - `--cap-drop ALL` and `--security-opt no-new-privileges`
  - `--user 65534:65534` (unprivileged `nobody:nogroup`)
  - No host filesystem mounts (`-v` is never used)
  - No Docker socket or backend/database environment variables inside the sandbox
  - `shell=False` everywhere
  - Guaranteed container destruction in a `finally` block after every run
"""

import base64
from dataclasses import asdict, dataclass, field
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
NOFILE_LIMIT = int(os.getenv("SANDBOX_NOFILE_LIMIT", "64"))
FSIZE_LIMIT_MB = int(os.getenv("SANDBOX_FSIZE_MB", "16"))
MAX_OUTPUT_BYTES = int(os.getenv("SANDBOX_MAX_OUTPUT_BYTES", str(64 * 1024)))  # 64 KB
MAX_ERROR_CHARS = 4000

EXECUTION_ENV = os.getenv("EXECUTION_ENV", "development").strip().lower()
REQUESTED_RUNTIME = os.getenv("SANDBOX_RUNTIME", "runsc").strip() or "runsc"
REQUIRE_GVISOR = (
    os.getenv(
        "SANDBOX_REQUIRE_GVISOR",
        "true" if EXECUTION_ENV == "production" else "false",
    )
    .strip()
    .lower()
    == "true"
)
ALLOW_DEV_FALLBACK = (
    os.getenv(
        "SANDBOX_ALLOW_DEV_FALLBACK",
        "false" if EXECUTION_ENV == "production" else "true",
    )
    .strip()
    .lower()
    == "true"
)


@dataclass
class RuntimeSecurityStatus:
    execution_env: str
    requested_runtime: str
    active_runtime: str
    available_runtimes: List[str]
    host_kernel: str
    sandbox_kernel: str
    gvisor_verified: bool
    fallback_active: bool
    production_secure: bool
    blocked: bool
    security_mode: str
    message: str
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


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


def list_active_sandbox_containers() -> List[str]:
    """Return names of any existing `codeclan-sbx-*` containers (running or exited)."""
    try:
        res = subprocess.run(
            ["docker", "ps", "-a", "--filter", "name=codeclan-sbx-", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5,
            shell=False,
        )
        if res.returncode != 0:
            return []
        return [line.strip() for line in res.stdout.splitlines() if line.strip()]
    except Exception:
        return []


def _probe_runtime_kernel(runtime: str) -> tuple[bool, str, str]:
    """
    Launch a minimal ephemeral container with `--runtime <runtime>` to read
    `/proc/version` and verify whether the runtime works and whether the kernel
    is gVisor's user-space Sentry kernel.
    """
    probe_name = f"codeclan-sbx-probe-{uuid.uuid4().hex[:8]}"
    cmd = [
        "docker",
        "run",
        "--rm",
        "--name",
        probe_name,
        "--runtime",
        runtime,
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        "65534:65534",
        SANDBOX_IMAGE,
        "/bin/cat",
        "/proc/version",
    ]
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=8,
            shell=False,
        )
        if res.returncode != 0:
            return False, "", (res.stderr or res.stdout or f"exit {res.returncode}").strip()
        proc_version = (res.stdout or "").strip()
        return True, proc_version, ""
    except Exception as exc:
        return False, "", str(exc)
    finally:
        _force_remove_container(probe_name)


def detect_and_verify_sandbox_runtime(
    execution_env: str = EXECUTION_ENV,
    requested_runtime: str = REQUESTED_RUNTIME,
    require_gvisor: bool = REQUIRE_GVISOR,
    allow_dev_fallback: bool = ALLOW_DEV_FALLBACK,
) -> RuntimeSecurityStatus:
    """
    Inspect the Docker daemon's registered OCI runtimes and actively verify
    whether gVisor (`runsc`) is operational.

    - Never claims gVisor is active unless `runsc` is registered AND a live probe
      container confirms execution under the gVisor Sentry kernel.
    - Fails closed (`blocked=True`) when `require_gvisor=True`, `execution_env == 'production'`,
      or `allow_dev_fallback=False` and `runsc` is unavailable.
    - Uses `runc` only as an explicit, non-production development fallback when allowed.
    """
    env_norm = (execution_env or "development").strip().lower()
    req_rt = (requested_runtime or "runsc").strip()
    must_have_gvisor = require_gvisor or (env_norm == "production") or (not allow_dev_fallback)

    available_runtimes: List[str] = []
    host_kernel = "unknown"
    daemon_os = "unknown"

    try:
        info_res = subprocess.run(
            [
                "docker",
                "info",
                "--format",
                "{{json .Runtimes}}|{{.KernelVersion}}|{{.OperatingSystem}}",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            shell=False,
        )
        if info_res.returncode == 0 and info_res.stdout.strip():
            parts = info_res.stdout.strip().split("|")
            if len(parts) >= 1 and parts[0]:
                rt_map = json.loads(parts[0])
                if isinstance(rt_map, dict):
                    available_runtimes = sorted(rt_map.keys())
            if len(parts) >= 2 and parts[1]:
                host_kernel = parts[1].strip()
            if len(parts) >= 3 and parts[2]:
                daemon_os = parts[2].strip()
        else:
            err_msg = (info_res.stderr or info_res.stdout or "docker info failed").strip()
            return RuntimeSecurityStatus(
                execution_env=env_norm,
                requested_runtime=req_rt,
                active_runtime="none",
                available_runtimes=[],
                host_kernel="unreachable",
                sandbox_kernel="unreachable",
                gvisor_verified=False,
                fallback_active=False,
                production_secure=False,
                blocked=True,
                security_mode="BLOCKED_DOCKER_DAEMON_UNAVAILABLE",
                message=f"Cannot inspect Docker daemon runtimes: {err_msg}",
                warnings=[err_msg],
            )
    except Exception as exc:
        return RuntimeSecurityStatus(
            execution_env=env_norm,
            requested_runtime=req_rt,
            active_runtime="none",
            available_runtimes=[],
            host_kernel="unreachable",
            sandbox_kernel="unreachable",
            gvisor_verified=False,
            fallback_active=False,
            production_secure=False,
            blocked=True,
            security_mode="BLOCKED_DOCKER_DAEMON_UNAVAILABLE",
            message=f"Docker daemon check failed: {exc}",
            warnings=[str(exc)],
        )

    # 1. If `runsc` is registered, actively verify it with a live probe container
    if "runsc" in available_runtimes and req_rt == "runsc":
        ok, proc_ver, err = _probe_runtime_kernel("runsc")
        # gVisor's Sentry kernel reports e.g. "Linux version 4.4.0 ..." (distinct from host kernel)
        is_gvisor_kernel = ok and (
            "4.4.0" in proc_ver
            or "gvisor" in proc_ver.lower()
            or (host_kernel != "unknown" and host_kernel not in proc_ver)
        )
        if ok and is_gvisor_kernel:
            logger.info(
                "Verified gVisor (runsc) sandbox isolation. Host kernel=%s, Sandbox kernel=%s",
                host_kernel,
                proc_ver,
            )
            return RuntimeSecurityStatus(
                execution_env=env_norm,
                requested_runtime=req_rt,
                active_runtime="runsc",
                available_runtimes=available_runtimes,
                host_kernel=host_kernel,
                sandbox_kernel=proc_ver,
                gvisor_verified=True,
                fallback_active=False,
                production_secure=True,
                blocked=False,
                security_mode="PRODUCTION_GVISOR_RUNSC_VERIFIED",
                message="Student code executes inside verified gVisor (runsc) user-space kernel sandboxes.",
                warnings=[],
            )
        probe_reason = err or f"Unexpected /proc/version under runsc: {proc_ver}"
    else:
        probe_reason = (
            f"OCI runtime 'runsc' (gVisor) is not registered with Docker daemon "
            f"(available runtimes: {', '.join(available_runtimes) or 'none'}; OS: {daemon_os})."
        )

    # 2. If gVisor is required (production mode or strict requirement), FAIL CLOSED
    if must_have_gvisor:
        block_msg = (
            f"EXECUTION BLOCKED: Production gVisor ('runsc') isolation is required "
            f"(execution_env={env_norm}, require_gvisor={require_gvisor}, allow_dev_fallback={allow_dev_fallback}), "
            f"but verification failed: {probe_reason}"
        )
        logger.error(block_msg)
        return RuntimeSecurityStatus(
            execution_env=env_norm,
            requested_runtime=req_rt,
            active_runtime="none",
            available_runtimes=available_runtimes,
            host_kernel=host_kernel,
            sandbox_kernel="none",
            gvisor_verified=False,
            fallback_active=False,
            production_secure=False,
            blocked=True,
            security_mode="BLOCKED_UNSAFE_RUNTIME_GVISOR_REQUIRED",
            message=block_msg,
            warnings=[probe_reason],
        )

    # 3. Development fallback to standard Docker `runc`
    fallback_rt = "runc" if "runc" in available_runtimes else (available_runtimes[0] if available_runtimes else "runc")
    ok_fb, fb_proc_ver, fb_err = _probe_runtime_kernel(fallback_rt)
    sandbox_kernel_str = fb_proc_ver if ok_fb else f"shared-host-kernel ({host_kernel})"
    warning_msg = (
        f"DEVELOPMENT FALLBACK ACTIVE (NOT PRODUCTION SECURE): {probe_reason} "
        f"Using standard Docker OCI runtime '{fallback_rt}' with hardened flags "
        f"(--network none, --ipc none, --read-only, --cap-drop ALL, no-new-privileges, "
        f"cgroups, rlimits, uid 65534). Student containers share the Linux kernel ({host_kernel}). "
        f"Do NOT expose this instance to untrusted public traffic without installing gVisor (runsc) on a Linux host."
    )
    logger.warning(warning_msg)
    return RuntimeSecurityStatus(
        execution_env=env_norm,
        requested_runtime=req_rt,
        active_runtime=fallback_rt,
        available_runtimes=available_runtimes,
        host_kernel=host_kernel,
        sandbox_kernel=sandbox_kernel_str,
        gvisor_verified=False,
        fallback_active=True,
        production_secure=False,
        blocked=False,
        security_mode="DEVELOPMENT_FALLBACK_DOCKER_RUNC (NOT_PRODUCTION_SECURE)",
        message=(
            f"Running in local development fallback mode with Docker '{fallback_rt}' runtime "
            f"(gVisor 'runsc' unavailable on {daemon_os}). NOT production-secure."
        ),
        warnings=[warning_msg] + ([fb_err] if fb_err else []),
    )


def _run_bounded_process(
    cmd: List[str],
    stdin_bytes: bytes,
    timeout_sec: float,
    max_output_bytes: int,
    container_name: str,
) -> dict:
    """
    Run `cmd` (`shell=False`), stream `stdin_bytes`, read stdout/stderr up to
    `max_output_bytes`, and enforce `timeout_sec`. Kills and removes the container
    if the wall-clock timeout or output cap is exceeded, and ALWAYS force-removes
    the container in a `finally` block so no sandbox container ever lingers.
    """
    start_ts = time.perf_counter()
    proc = None
    try:
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
    finally:
        # Guaranteed cleanup regardless of exit path (normal, error, OOM, timeout, output flood)
        _force_remove_container(container_name)


def _build_docker_run_cmd(container_name: str, mode: str, runtime: str = "runc") -> List[str]:
    fsize_bytes = FSIZE_LIMIT_MB * 1024 * 1024
    return [
        "docker",
        "run",
        "--rm",
        "-i",
        "--name",
        container_name,
        "--runtime",
        runtime,
        "--network",
        "none",
        "--ipc",
        "none",
        "--read-only",
        "--tmpfs",
        "/work:rw,exec,nosuid,nodev,size=32m,mode=1777",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777",
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
        "--ulimit",
        f"nofile={NOFILE_LIMIT}:{NOFILE_LIMIT}",
        "--ulimit",
        f"nproc={PIDS_LIMIT}:{PIDS_LIMIT}",
        "--ulimit",
        f"fsize={fsize_bytes}:{fsize_bytes}",
        "--ulimit",
        "core=0:0",
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
    """
    Executes compilation and individual test cases inside isolated containers
    using gVisor (`runsc`) in production or an explicitly marked `runc` fallback
    in local development.
    """

    def __init__(
        self,
        execution_env: str = EXECUTION_ENV,
        requested_runtime: str = REQUESTED_RUNTIME,
        require_gvisor: bool = REQUIRE_GVISOR,
        allow_dev_fallback: bool = ALLOW_DEV_FALLBACK,
    ):
        self.runtime_status: RuntimeSecurityStatus = detect_and_verify_sandbox_runtime(
            execution_env=execution_env,
            requested_runtime=requested_runtime,
            require_gvisor=require_gvisor,
            allow_dev_fallback=allow_dev_fallback,
        )

    def get_runtime_status(self, refresh: bool = False) -> RuntimeSecurityStatus:
        if refresh:
            self.runtime_status = detect_and_verify_sandbox_runtime(
                execution_env=self.runtime_status.execution_env,
                requested_runtime=self.runtime_status.requested_runtime,
                require_gvisor=REQUIRE_GVISOR,
                allow_dev_fallback=ALLOW_DEV_FALLBACK,
            )
        return self.runtime_status

    def compile_source(self, language: str, code: str) -> CompileResult:
        if self.runtime_status.blocked:
            return CompileResult(
                ok=False,
                error_message=self.runtime_status.message,
                status=STATUS_INTERNAL_ERROR,
            )

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
        cmd = _build_docker_run_cmd(container_name, "compile", runtime=self.runtime_status.active_runtime)
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
            if "Cannot connect to the Docker daemon" in err or "Unable to find image" in err or "Unknown runtime" in err:
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
        if self.runtime_status.blocked:
            return SingleTestExecutionResult(
                status=STATUS_INTERNAL_ERROR,
                passed=False,
                actual_output="",
                execution_time_ms=0.0,
                error_message=self.runtime_status.message,
            )

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
            "nproc_limit": 32,
            "nofile_limit": NOFILE_LIMIT,
        }
        cmd = _build_docker_run_cmd(container_name, "run", runtime=self.runtime_status.active_runtime)
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
            if "Cannot connect to the Docker daemon" in stderr_clean or "Unable to find image" in stderr_clean or "Unknown runtime" in stderr_clean:
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
