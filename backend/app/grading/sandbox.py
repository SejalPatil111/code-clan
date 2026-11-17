"""
Isolated sandbox executor (gVisor `runsc` in production, labelled `runc` fallback in development).

Every container follows the same hardened lifecycle:

    docker create  (all isolation flags, approved image, fixed runner command)
    docker inspect (VERIFY the container that will run student code really has the expected runtime,
                    network=none, read-only rootfs, non-privileged, no bind mounts, user 65534)
    docker start -a -i  (stream stdin/stdout, bounded output, wall-clock timeout)
    docker rm -f   (ALWAYS, in `finally`)

Isolation flags: --runtime <runsc|runc> --network none --ipc none --read-only
  --tmpfs /work (exec) --tmpfs /tmp (noexec) --memory/--memory-swap --cpus --pids-limit
  --ulimit nofile/fsize/core --cap-drop ALL --security-opt no-new-privileges --user 65534:65534
No host mounts, no Docker socket, no environment variables are passed to the container.

`--ulimit nproc` is intentionally NOT used: RLIMIT_NPROC is accounted per *host UID*, so on runc several
concurrent sandboxes (all uid 65534) would starve each other. The cgroup `--pids-limit` is per container.
"""

import base64
from dataclasses import asdict, dataclass, field
import json
import logging
import os
import subprocess
import threading
import time
from typing import Dict, List, Optional, Tuple
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
from app.grading.environments import ENVIRONMENTS, Environment, effective_profile, get_environment

logger = logging.getLogger("codeclan.sandbox")

SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "codeclan-sandbox:latest")
COMPILE_TIMEOUT_SECONDS = float(os.getenv("SANDBOX_COMPILE_TIMEOUT", "10.0"))
RUN_TIMEOUT_SECONDS = float(os.getenv("SANDBOX_RUN_TIMEOUT", "3.0"))
MEMORY_LIMIT_MB = int(os.getenv("SANDBOX_MEMORY_MB", "256"))
CPU_LIMIT = os.getenv("SANDBOX_CPUS", "0.5")
PIDS_LIMIT = int(os.getenv("SANDBOX_PIDS_LIMIT", "64"))
NOFILE_LIMIT = int(os.getenv("SANDBOX_NOFILE_LIMIT", "64"))
FSIZE_LIMIT_MB = int(os.getenv("SANDBOX_FSIZE_MB", "16"))
MAX_OUTPUT_BYTES = int(os.getenv("SANDBOX_MAX_OUTPUT_BYTES", str(64 * 1024)))
MAX_ERROR_CHARS = 4000
STARTUP_ALLOWANCE_SECONDS = float(os.getenv("SANDBOX_STARTUP_ALLOWANCE", "6.0"))  # create+inspect+start overhead

EXECUTION_ENV = os.getenv("EXECUTION_ENV", "development").strip().lower()
REQUESTED_RUNTIME = os.getenv("SANDBOX_RUNTIME", "runsc").strip() or "runsc"
REQUIRE_GVISOR = os.getenv("SANDBOX_REQUIRE_GVISOR", "true" if EXECUTION_ENV == "production" else "false").strip().lower() == "true"
ALLOW_DEV_FALLBACK = os.getenv("SANDBOX_ALLOW_DEV_FALLBACK", "false" if EXECUTION_ENV == "production" else "true").strip().lower() == "true"


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
    # Evidence from REAL student/evaluator containers (not just a startup probe)
    containers_verified: Dict[str, int] = field(default_factory=dict)
    container_verification_failures: int = 0
    last_container_verified_runtime: str = ""
    runtime_check_method: str = "startup probe + per-container docker inspect (HostConfig.Runtime)"

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
    stderr: str = ""
    memory_kb: int = 0


@dataclass
class ProjectRunResult:
    ok: bool                       # container ran and returned a parsable envelope
    stage: str = "run"
    internal_error: bool = False
    error_message: Optional[str] = None
    setup_error: Optional[str] = None
    returncode: int = -1
    timed_out: bool = False
    output_exceeded: bool = False
    stdout: str = ""
    stderr: str = ""
    max_rss_kb: int = 0
    cpu_ms: float = 0.0
    wall_ms: float = 0.0
    files: Dict[str, bytes] = field(default_factory=dict)
    files_truncated: bool = False
    result_json: str = ""
    harness_results: List[dict] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return self.returncode

    @property
    def execution_time_ms(self) -> float:
        return self.wall_ms

    @property
    def oom_killed(self) -> bool:
        return (
            self.returncode == 137
            or "MemoryError" in self.stderr
            or "bad_alloc" in self.stderr
            or "OutOfMemoryError" in self.stderr
        )

    @property
    def output_limit_exceeded(self) -> bool:
        return self.output_exceeded

    @property
    def output_files(self) -> List[dict]:
        return [
            {
                "name": k,
                "size_bytes": len(v),
                "content_b64": base64.b64encode(v).decode("ascii"),
            }
            for k, v in self.files.items()
        ]

    @property
    def evaluation(self) -> dict:
        if not self.result_json:
            return {}
        try:
            parsed = json.loads(self.result_json)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}


# ------------------------------------------------------------------ docker helpers
def _docker(args: List[str], timeout: float = 15.0, input_bytes: Optional[bytes] = None) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, timeout=timeout, shell=False, input=input_bytes)


def _force_remove_container(container_name: str) -> None:
    try:
        subprocess.run(["docker", "rm", "-f", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=8, shell=False)
    except Exception:
        pass


def list_active_sandbox_containers() -> List[str]:
    """Names of existing `codeclan-sbx-*` / `codeclan-evl-*` containers (running or exited)."""
    names: List[str] = []
    for prefix in ("codeclan-sbx-", "codeclan-evl-"):
        try:
            res = subprocess.run(["docker", "ps", "-a", "--filter", f"name={prefix}", "--format", "{{.Names}}"],
                                 capture_output=True, text=True, timeout=8, shell=False)
            if res.returncode == 0:
                names += [ln.strip() for ln in res.stdout.splitlines() if ln.strip()]
        except Exception:
            pass
    return names


def build_create_command(name: str, image: str, mode: str, runtime: str, prof: Dict[str, float], kind: str = "sbx") -> List[str]:
    """`docker create` argv for one sandbox. All values come from the registry/profile, never from students."""
    mem = int(prof["memory_mb"])
    fsize = int(prof.get("fsize_mb", FSIZE_LIMIT_MB)) * 1024 * 1024
    nofile = int(prof.get("nofile", NOFILE_LIMIT))
    return [
        "create", "--pull", "never", "--name", name, "--runtime", runtime,
        "--network", "none", "--ipc", "none", "--read-only",
        "--tmpfs", f"/work:rw,exec,nosuid,nodev,size={int(prof['tmpfs_work_mb'])}m,mode=1777",
        "--tmpfs", f"/tmp:rw,noexec,nosuid,nodev,size={int(prof.get('tmpfs_tmp_mb', 16))}m,mode=1777",
        "--workdir", "/work",
        "--memory", f"{mem}m", "--memory-swap", f"{mem}m",
        "--cpus", str(prof["cpus"]), "--pids-limit", str(int(prof["pids"])),
        "--ulimit", f"nofile={nofile}:{nofile}",
        "--ulimit", f"fsize={fsize}:{fsize}",
        "--ulimit", "core=0:0",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--user", "65534:65534", "-i",
        image, "/usr/local/bin/sandbox-runner", mode,
    ]


def _verify_container(name: str, expected_runtime: str) -> Tuple[bool, str, str]:
    """Inspect the CREATED container and confirm it has the isolation settings we require."""
    fmt = ("{{.HostConfig.Runtime}}|{{.HostConfig.Privileged}}|{{.HostConfig.NetworkMode}}|"
           "{{.HostConfig.ReadonlyRootfs}}|{{len .HostConfig.Binds}}|{{.Config.User}}|{{len .HostConfig.Devices}}")
    try:
        res = _docker(["inspect", "-f", fmt, name], timeout=10)
    except Exception as exc:
        return False, "", f"inspect failed: {exc}"
    if res.returncode != 0:
        return False, "", (res.stderr or b"").decode("utf-8", "replace").strip()[:300]
    got = res.stdout.decode("utf-8", "replace").strip()
    parts = got.split("|")
    expected = [expected_runtime, "false", "none", "true", "0", "65534:65534", "0"]
    if len(parts) != 7 or parts != expected:
        return False, parts[0] if parts else "", f"container settings mismatch: got {got!r}, expected {'|'.join(expected)!r}"
    return True, parts[0], ""


def _run_bounded_process(cmd: List[str], stdin_bytes: bytes, timeout_sec: float, max_output_bytes: int, container_name: str) -> dict:
    """Run `docker start -a -i`, enforce wall-clock timeout & output caps. Always removes the container."""
    start_ts = time.perf_counter()
    proc = None
    try:
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
        except Exception as exc:
            return {"returncode": -1, "stdout": "", "stderr": f"Failed to start sandbox container: {exc}",
                    "timed_out": False, "output_exceeded": False, "elapsed_ms": 0.0, "internal_error": True}

        chunks = {"out": [], "err": []}
        totals = {"out": 0, "err": 0}
        state = {"exceeded": False}

        def _read(pipe, key):
            try:
                while True:
                    chunk = pipe.read(8192)
                    if not chunk:
                        break
                    if totals[key] < max_output_bytes:
                        take = min(len(chunk), max_output_bytes - totals[key])
                        chunks[key].append(chunk[:take])
                    totals[key] += len(chunk)
                    if totals[key] > max_output_bytes and not state["exceeded"]:
                        state["exceeded"] = True
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

        t_out = threading.Thread(target=_read, args=(proc.stdout, "out"), daemon=True)
        t_err = threading.Thread(target=_read, args=(proc.stderr, "err"), daemon=True)
        t_out.start()
        t_err.start()

        def _feed():
            try:
                proc.stdin.write(stdin_bytes)
            except Exception:
                pass
            finally:
                try:
                    proc.stdin.close()
                except Exception:
                    pass

        t_in = threading.Thread(target=_feed, daemon=True)
        t_in.start()

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
                proc.wait(timeout=3)
            except Exception:
                pass
        t_out.join(timeout=3)
        t_err.join(timeout=3)
        return {
            "returncode": proc.returncode if proc.returncode is not None else -1,
            "stdout": b"".join(chunks["out"]).decode("utf-8", errors="replace"),
            "stderr": b"".join(chunks["err"]).decode("utf-8", errors="replace"),
            "timed_out": timed_out, "output_exceeded": state["exceeded"],
            "elapsed_ms": round((time.perf_counter() - start_ts) * 1000.0, 2), "internal_error": False,
        }
    finally:
        _force_remove_container(container_name)


def _probe_runtime(runtime: str, image: str = SANDBOX_IMAGE) -> Tuple[bool, dict, str]:
    """Create + inspect-verify + start a throw-away container in `runtime`; return runner probe JSON."""
    name = f"codeclan-sbx-probe-{uuid.uuid4().hex[:10]}"
    prof = effective_profile(get_environment("cp"))
    try:
        res = _docker(build_create_command(name, image, "probe", runtime, prof), timeout=30)
        if res.returncode != 0:
            return False, {}, (res.stderr or res.stdout or b"").decode("utf-8", "replace").strip()[:400]
        ok, _rt, why = _verify_container(name, runtime)
        if not ok:
            return False, {}, why
        run = _docker(["start", "-a", "-i", name], timeout=30, input_bytes=b"")
        if run.returncode != 0:
            return False, {}, (run.stderr or run.stdout or b"").decode("utf-8", "replace").strip()[:400]
        return True, json.loads(run.stdout.decode("utf-8", "replace")), ""
    except Exception as exc:
        return False, {}, str(exc)
    finally:
        _force_remove_container(name)


def _status(env, req, active, avail, hk, sk, gv, fb, ps, blocked, mode, msg, warnings=None) -> RuntimeSecurityStatus:
    return RuntimeSecurityStatus(execution_env=env, requested_runtime=req, active_runtime=active, available_runtimes=avail,
                                 host_kernel=hk, sandbox_kernel=sk, gvisor_verified=gv, fallback_active=fb,
                                 production_secure=ps, blocked=blocked, security_mode=mode, message=msg,
                                 warnings=warnings or [])


def detect_and_verify_sandbox_runtime(
    execution_env: str = EXECUTION_ENV,
    requested_runtime: str = REQUESTED_RUNTIME,
    require_gvisor: bool = REQUIRE_GVISOR,
    allow_dev_fallback: bool = ALLOW_DEV_FALLBACK,
) -> RuntimeSecurityStatus:
    """
    Decide which runtime student code will use, VERIFIED by actually creating/inspecting/starting a container.
    `docker info` is optional (the production policy proxy denies it); it is only used for display.
    Fails closed when gVisor is required and cannot be verified.
    """
    env_norm = (execution_env or "development").strip().lower()
    req_rt = (requested_runtime or "runsc").strip()
    must = require_gvisor or env_norm == "production" or not allow_dev_fallback

    available: List[str] = []
    host_kernel = "unknown (docker info unavailable)"
    info_known = False
    try:
        info = _docker(["info", "--format", "{{json .Runtimes}}|{{.KernelVersion}}"], timeout=10)
        if info.returncode == 0 and info.stdout.strip():
            a, _, k = info.stdout.decode().strip().partition("|")
            available = sorted(json.loads(a).keys())
            host_kernel = k.strip() or host_kernel
            info_known = True
    except Exception:
        pass

    probe_reason = ""
    if req_rt == "runsc" and (not info_known or "runsc" in available):
        ok, data, err = _probe_runtime("runsc")
        pv = (data or {}).get("proc_version", "")
        is_gv = ok and ("4.4.0" in pv or "gvisor" in pv.lower() or (info_known and host_kernel not in pv))
        if ok and is_gv:
            return RuntimeSecurityStatus(
                execution_env=env_norm, requested_runtime=req_rt, active_runtime="runsc", available_runtimes=available,
                host_kernel=host_kernel, sandbox_kernel=pv, gvisor_verified=True, fallback_active=False,
                production_secure=True, blocked=False, security_mode="PRODUCTION_GVISOR_RUNSC_VERIFIED",
                message="Student code executes in containers created with runtime 'runsc'; the probe container "
                        "reports a gVisor-style kernel identity.",
                warnings=["Kernel identity is a heuristic; the authoritative checks are HostConfig.Runtime=runsc "
                          "(verified on every container) and the gVisor runtime installed on the host."],
            )
        probe_reason = err or f"runsc started but kernel identity does not look like gVisor: {pv!r}"
    else:
        probe_reason = (f"runtime 'runsc' is not registered with the Docker daemon (registered: {', '.join(available) or 'none'})"
                        if info_known else f"requested runtime {req_rt!r} is not runsc")

    if must:
        msg = (f"EXECUTION BLOCKED: gVisor (runsc) is required (env={env_norm}, require_gvisor={require_gvisor}, "
               f"allow_dev_fallback={allow_dev_fallback}) but could not be verified: {probe_reason}")
        logger.error(msg)
        return _status(env_norm, req_rt, "none", available, host_kernel, "none", False, False, False, True,
                       "BLOCKED_UNSAFE_RUNTIME_GVISOR_REQUIRED", msg, [probe_reason])

    ok, data, err = _probe_runtime("runc")
    if not ok:
        msg = f"Docker 'runc' fallback probe failed: {err}"
        return _status(env_norm, req_rt, "none", available, host_kernel, "none", False, False, False, True,
                       "BLOCKED_NO_USABLE_RUNTIME", msg, [probe_reason, err])
    warn = (f"DEVELOPMENT FALLBACK ACTIVE (NOT PRODUCTION SECURE): {probe_reason}. Using Docker 'runc' with hardened "
            f"flags; sandboxes share the host Linux kernel ({host_kernel}). Do not expose to untrusted public users.")
    logger.warning(warn)
    return _status(env_norm, req_rt, "runc", available, host_kernel, (data or {}).get("proc_version", "shared host kernel"),
                   False, True, False, False, "DEVELOPMENT_FALLBACK_DOCKER_RUNC (NOT_PRODUCTION_SECURE)",
                   "Local development fallback with Docker 'runc'. NOT production-secure.", [warn])


class SandboxExecutor:
    """Runs compilation, tests, projects and evaluators in verified, ephemeral containers."""

    def __init__(self, execution_env: str = EXECUTION_ENV, requested_runtime: str = REQUESTED_RUNTIME,
                 require_gvisor: bool = REQUIRE_GVISOR, allow_dev_fallback: bool = ALLOW_DEV_FALLBACK):
        self._lock = threading.Lock()
        self.runtime_status = detect_and_verify_sandbox_runtime(execution_env, requested_runtime, require_gvisor, allow_dev_fallback)

    def get_runtime_status(self, refresh: bool = False) -> RuntimeSecurityStatus:
        if refresh:
            old = self.runtime_status
            new = detect_and_verify_sandbox_runtime(old.execution_env, old.requested_runtime, REQUIRE_GVISOR, ALLOW_DEV_FALLBACK)
            new.containers_verified, new.container_verification_failures = old.containers_verified, old.container_verification_failures
            self.runtime_status = new
        return self.runtime_status

    # ----------------------------------------------------------- core container lifecycle
    def _container(self, env: Environment, mode: str, payload: dict, prof: Dict[str, float], wall_timeout: float,
                   max_output_bytes: int, kind: str = "sbx") -> dict:
        st = self.runtime_status
        if st.blocked:
            return {"returncode": -1, "stdout": "", "stderr": st.message, "timed_out": False, "output_exceeded": False,
                    "elapsed_ms": 0.0, "internal_error": True}
        runtime = st.active_runtime
        name = f"codeclan-{kind}-{mode.replace('_', '')[:7]}-{uuid.uuid4().hex[:12]}"
        t0 = time.perf_counter()
        try:
            cr = _docker(build_create_command(name, env.image, mode, runtime, prof, kind), timeout=40)
            if cr.returncode != 0:
                err = (cr.stderr or cr.stdout or b"").decode("utf-8", "replace").strip()
                if "No such image" in err or "pull access denied" in err:
                    err = f"Execution environment image '{env.id}' is not built on this host. Run scripts/build-envs. ({err[:200]})"
                return {"returncode": -1, "stdout": "", "stderr": f"Sandbox create failed: {err[:MAX_ERROR_CHARS]}",
                        "timed_out": False, "output_exceeded": False, "elapsed_ms": 0.0, "internal_error": True}
            ok, got_rt, why = _verify_container(name, runtime)
            if not ok:
                with self._lock:
                    st.container_verification_failures += 1
                    if got_rt and got_rt != runtime and st.execution_env == "production":
                        st.blocked = True
                        st.security_mode = "BLOCKED_RUNTIME_MISMATCH_DETECTED"
                        st.message = f"Container reported runtime {got_rt!r}, expected {runtime!r}. Execution blocked."
                logger.error("Sandbox verification failed for %s: %s", name, why)
                return {"returncode": -1, "stdout": "", "stderr": f"Sandbox verification failed: {why}", "timed_out": False,
                        "output_exceeded": False, "elapsed_ms": 0.0, "internal_error": True}
            with self._lock:
                st.containers_verified[got_rt] = st.containers_verified.get(got_rt, 0) + 1
                st.last_container_verified_runtime = got_rt
            remaining = max(1.0, wall_timeout + STARTUP_ALLOWANCE_SECONDS - (time.perf_counter() - t0))
            res = _run_bounded_process(["docker", "start", "-a", "-i", name], json.dumps(payload).encode("utf-8"),
                                       remaining, max_output_bytes, name)
            return res
        except subprocess.TimeoutExpired:
            return {"returncode": -1, "stdout": "", "stderr": "Docker daemon did not respond in time.", "timed_out": False,
                    "output_exceeded": False, "elapsed_ms": 0.0, "internal_error": True}
        finally:
            _force_remove_container(name)

    @staticmethod
    def _encode_files_b64(files: Optional[Dict[str, str]], *, already_b64: bool = False) -> Tuple[Dict[str, str], int]:
        if not files:
            return {}, 0
        encoded: Dict[str, str] = {}
        total_raw = 0
        for rel, val in files.items():
            if already_b64:
                encoded[rel] = val
                total_raw += len(val) * 3 // 4
            else:
                raw_bytes = (val or "").encode("utf-8")
                total_raw += len(raw_bytes)
                encoded[rel] = base64.b64encode(raw_bytes).decode("ascii")
        return encoded, total_raw

    @staticmethod
    def _resolve_env(env: Optional[Environment] = None, image: Optional[str] = None) -> Environment:
        if env is not None:
            return env
        if image:
            for candidate in ENVIRONMENTS.values():
                if candidate.image == image or candidate.id == image:
                    return candidate
        return get_environment("cp")

    # ----------------------------------------------------------- compile
    def compile_source(self, language: str, code: str = "", *, env: Optional[Environment] = None,
                       files: Optional[Dict[str, str]] = None, entry_point: str = "",
                       profile: Optional[Dict[str, float]] = None,
                       files_are_b64: bool = False) -> CompileResult:
        """`files` maps relative path -> source text (or base64 when `files_are_b64=True`)."""
        norm_lang = normalize_language(language)
        if not norm_lang:
            return CompileResult(False, error_message=f"Unsupported language: {language}", status=STATUS_COMPILATION_ERROR)
        env = env or get_environment("cp")
        if norm_lang not in env.languages:
            return CompileResult(False, error_message=f"Language '{norm_lang}' is not supported by environment '{env.id}'.",
                                 status=STATUS_COMPILATION_ERROR)
        prof = profile or effective_profile(env)
        payload = {"language": norm_lang, "entry_point": entry_point or ""}
        if files:
            b64_files, total = self._encode_files_b64(files, already_b64=files_are_b64)
            payload["files"] = b64_files
        else:
            if len(code.encode("utf-8")) > MAX_SOURCE_CODE_BYTES:
                return CompileResult(False, error_message=f"Source code exceeds maximum allowed size ({MAX_SOURCE_CODE_BYTES} bytes).",
                                     status=STATUS_COMPILATION_ERROR)
            payload["code_b64"] = base64.b64encode(code.encode("utf-8")).decode("ascii")
            total = len(code)
        if total > int(prof.get("max_source_bytes", 262144)) * 4:
            return CompileResult(False, error_message="Project exceeds the maximum allowed source size.", status=STATUS_COMPILATION_ERROR)

        res = self._container(env, "compile", payload, prof, float(prof.get("compile_timeout_sec", COMPILE_TIMEOUT_SECONDS)),
                              max(MAX_OUTPUT_BYTES * 4, 4 * 1024 * 1024))
        if res["internal_error"]:
            return CompileResult(False, error_message=res["stderr"][:MAX_ERROR_CHARS], status=STATUS_INTERNAL_ERROR)
        if res["timed_out"]:
            return CompileResult(False, error_message=f"Compilation timed out after {prof.get('compile_timeout_sec', COMPILE_TIMEOUT_SECONDS)}s.",
                                 status=STATUS_COMPILATION_ERROR)
        if res["returncode"] != 0:
            err = (res["stderr"] or res["stdout"] or "Compilation failed.").strip()
            if "Cannot connect to the Docker daemon" in err or "Unable to find image" in err or "Unknown runtime" in err:
                return CompileResult(False, error_message=f"Sandbox unavailable: {err[:MAX_ERROR_CHARS]}", status=STATUS_INTERNAL_ERROR)
            return CompileResult(False, error_message=err[:MAX_ERROR_CHARS], status=STATUS_COMPILATION_ERROR)
        try:
            return CompileResult(True, artifact_b64=json.loads(res["stdout"]).get("artifact_b64", ""))
        except Exception as exc:
            return CompileResult(False, error_message=f"Invalid compiler output from sandbox: {exc}", status=STATUS_INTERNAL_ERROR)

    # ----------------------------------------------------------- legacy competitive run (stdout comparison)
    def run_single_test(self, language: str, code: str, artifact_b64: str, test_input: str, expected_output: str,
                        timeout_sec: Optional[float] = None, *, env: Optional[Environment] = None,
                        files: Optional[Dict[str, str]] = None, entry_point: str = "",
                        profile: Optional[Dict[str, float]] = None, comparator=None,
                        files_are_b64: bool = False) -> SingleTestExecutionResult:
        norm_lang = normalize_language(language)
        if not norm_lang:
            return SingleTestExecutionResult(STATUS_COMPILATION_ERROR, False, "", 0.0, f"Unsupported language: {language}")
        env = env or get_environment("cp")
        prof = profile or effective_profile(env)
        wall = timeout_sec if timeout_sec is not None else float(prof.get("wall_timeout_sec", RUN_TIMEOUT_SECONDS))
        payload = {
            "language": norm_lang, "artifact_b64": artifact_b64, "entry_point": entry_point or "",
            "stdin_b64": base64.b64encode((test_input or "").encode("utf-8")).decode("ascii"),
            "cpu_limit_sec": max(1, int(wall) + 1), "fsize_limit_mb": 4, "memory_limit_mb": int(prof["memory_mb"]),
            "nofile_limit": int(prof.get("nofile", NOFILE_LIMIT)),
        }
        if files:
            b64_files, _ = self._encode_files_b64(files, already_b64=files_are_b64)
            payload["files"] = b64_files
        elif norm_lang in ("python", "javascript"):
            payload["code_b64"] = base64.b64encode(code.encode("utf-8")).decode("ascii")
        max_out = int(prof.get("max_output_bytes", MAX_OUTPUT_BYTES))
        res = self._container(env, "run", payload, prof, wall, max_out)
        mem_label = f"{int(prof['memory_mb'])} MB"

        if res["internal_error"]:
            return SingleTestExecutionResult(STATUS_INTERNAL_ERROR, False, "", res["elapsed_ms"], res["stderr"][:MAX_ERROR_CHARS])
        if res["output_exceeded"]:
            return SingleTestExecutionResult(STATUS_RUNTIME_ERROR, False, res["stdout"][:2000], res["elapsed_ms"],
                                             f"Output Limit Exceeded: program produced more than {max_out // 1024} KB of output.")
        if res["timed_out"] or res["returncode"] == 152:
            return SingleTestExecutionResult(STATUS_TLE, False, res["stdout"][:2000], round(wall * 1000.0, 2),
                                             f"Time Limit Exceeded (>{wall:.1f}s).")
        rc = res["returncode"]
        stderr_clean = (res["stderr"] or "").strip()
        if rc != 0:
            if "Cannot connect to the Docker daemon" in stderr_clean or "Unable to find image" in stderr_clean or "Unknown runtime" in stderr_clean:
                return SingleTestExecutionResult(STATUS_INTERNAL_ERROR, False, "", res["elapsed_ms"], f"Sandbox unavailable: {stderr_clean[:MAX_ERROR_CHARS]}")
            if rc == 137 or "MemoryError" in stderr_clean or "bad_alloc" in stderr_clean or "OutOfMemoryError" in stderr_clean:
                msg = f"Memory Limit Exceeded ({mem_label})."
                if stderr_clean:
                    msg = f"{msg}\n{stderr_clean[:MAX_ERROR_CHARS]}"
                return SingleTestExecutionResult(STATUS_RUNTIME_ERROR, False, res["stdout"][:2000], res["elapsed_ms"], msg, stderr=stderr_clean)
            if rc == 153:
                return SingleTestExecutionResult(STATUS_RUNTIME_ERROR, False, res["stdout"][:2000], res["elapsed_ms"], "Output / file size limit exceeded.")
            return SingleTestExecutionResult(STATUS_RUNTIME_ERROR, False, res["stdout"][:2000], res["elapsed_ms"],
                                             (stderr_clean or f"Process exited with non-zero code {rc}")[:MAX_ERROR_CHARS], stderr=stderr_clean)
        cmp = comparator or compare_outputs
        matched = bool(cmp(res["stdout"], expected_output))
        return SingleTestExecutionResult(STATUS_ACCEPTED if matched else STATUS_WRONG_ANSWER, matched, res["stdout"], res["elapsed_ms"], None)

    # ----------------------------------------------------------- project run (supervisor envelope)
    def run_project(
        self,
        env: Optional[Environment] = None,
        language: str = "python",
        *,
        files: Optional[Dict[str, str]] = None,
        artifact_b64: str = "",
        entry_point: Optional[str] = "",
        stdin_text: str = "",
        stdin_data: Optional[str] = None,
        datasets_b64: Optional[str] = "",
        profile: Optional[Dict[str, float]] = None,
        harness: Optional[dict] = None,
        wall_timeout: Optional[float] = None,
        image: Optional[str] = None,
        run_timeout: Optional[float] = None,
        compile_timeout: Optional[float] = None,
        memory_mb: Optional[int] = None,
        cpus: Optional[float] = None,
        pids_limit: Optional[int] = None,
        nofile_limit: Optional[int] = None,
        fsize_mb: Optional[int] = None,
        max_output_bytes: Optional[int] = None,
        env_vars: Optional[Dict[str, str]] = None,
        apply_nproc_rlimit: bool = False,
        files_are_b64: bool = False,
    ) -> ProjectRunResult:
        env = self._resolve_env(env, image)
        norm_lang = normalize_language(language)
        if not norm_lang or norm_lang not in env.languages:
            return ProjectRunResult(
                ok=False,
                stage="compile",
                returncode=2,
                stderr=f"Language '{language}' is not supported by environment '{env.id}'.",
                error_message=f"Language '{language}' is not supported by environment '{env.id}'.",
            )
        prof = dict(profile or effective_profile(env))
        if run_timeout is not None:
            prof["wall_timeout_sec"] = float(run_timeout)
        if compile_timeout is not None:
            prof["compile_timeout_sec"] = float(compile_timeout)
        if memory_mb is not None:
            prof["memory_mb"] = int(memory_mb)
        if cpus is not None:
            prof["cpus"] = float(cpus)
        if pids_limit is not None:
            prof["pids"] = int(pids_limit)
        if nofile_limit is not None:
            prof["nofile"] = int(nofile_limit)
        if fsize_mb is not None:
            prof["fsize_mb"] = int(fsize_mb)
        if max_output_bytes is not None:
            prof["max_output_bytes"] = int(max_output_bytes)

        b64_files, _ = self._encode_files_b64(files, already_b64=files_are_b64)

        # Compile first when running compiled languages (C, C++, Java) without prebuilt artifact_b64
        if norm_lang in ("c", "cpp", "java") and not artifact_b64:
            cmp_res = self.compile_source(
                norm_lang,
                "",
                env=env,
                files=b64_files,
                entry_point=entry_point or "",
                profile=prof,
                files_are_b64=True,
            )
            if not cmp_res.ok:
                return ProjectRunResult(
                    ok=False,
                    stage="compile",
                    returncode=1,
                    stderr=cmp_res.error_message or "Compilation failed.",
                    error_message=cmp_res.error_message or "Compilation failed.",
                )
            artifact_b64 = cmp_res.artifact_b64

        wall = float(wall_timeout if wall_timeout is not None else prof["wall_timeout_sec"])
        out_cap = int(prof["max_output_bytes"])

        effective_stdin = stdin_data if stdin_data is not None else stdin_text
        if harness and isinstance(harness, dict) and harness.get("calls") is not None:
            effective_stdin = json.dumps(harness["calls"])

        payload = {
            "language": norm_lang,
            "files": b64_files,
            "artifact_b64": artifact_b64 or "",
            "entry_point": entry_point or "",
            "stdin_b64": base64.b64encode((effective_stdin or "").encode("utf-8")).decode("ascii"),
            "datasets_b64": datasets_b64 or "",
            "harness": harness,
            "project_mode": True,
            "cpu_limit_sec": max(1, int(wall * float(prof["cpus"])) + 2),
            "fsize_limit_mb": int(prof["fsize_mb"]),
            "memory_limit_mb": int(prof["memory_mb"]),
            "nofile_limit": int(prof.get("nofile", 128)),
            "wall_timeout_sec": wall,
            "max_output_bytes": out_cap,
            "threads": int(prof.get("threads", 1)),
            "limit_address_space": bool(prof.get("limit_address_space", 0)),
            "max_output_files": int(prof.get("max_output_files", 20)),
            "max_output_files_bytes": int(prof.get("max_output_files_bytes", 4 * 1024 * 1024)),
        }
        env_cap = int((2 * out_cap + int(prof.get("max_output_files_bytes", 0))) * 4 / 3) + 128 * 1024
        res = self._container(env, "run_project", payload, prof, wall, env_cap)
        return self._parse_envelope(res, wall)

    def run_evaluator(
        self,
        env: Optional[Environment] = None,
        script: Optional[bytes | str] = None,
        submission_files: Optional[Dict[str, bytes] | List[dict]] = None,
        hidden_tar_b64: str = "",
        config: Optional[dict] = None,
        profile: Optional[Dict[str, float]] = None,
        wall_timeout: float = 30.0,
        *,
        evaluator_code: Optional[str | bytes] = None,
        hidden_b64: Optional[str] = None,
        image: Optional[str] = None,
        timeout: Optional[float] = None,
        memory_mb: Optional[int] = None,
        cpus: Optional[float] = None,
    ) -> ProjectRunResult:
        """Run an evaluator script in a SEPARATE container that contains NO student code, only the student's
        output data and the hidden evaluation data."""
        env = self._resolve_env(env, image)
        prof = dict(profile or effective_profile(env))
        if memory_mb is not None:
            prof["memory_mb"] = int(memory_mb)
        if cpus is not None:
            prof["cpus"] = float(cpus)
        wt = float(timeout if timeout is not None else wall_timeout)

        raw_script = evaluator_code if evaluator_code is not None else (script or b"")
        script_bytes = raw_script.encode("utf-8") if isinstance(raw_script, str) else bytes(raw_script)

        sub_map_b64: Dict[str, str] = {}
        if isinstance(submission_files, list):
            for item in submission_files:
                if isinstance(item, dict) and item.get("name"):
                    if item.get("content_b64") is not None:
                        sub_map_b64[str(item["name"])] = str(item["content_b64"])
                    elif item.get("content") is not None:
                        raw_c = item["content"]
                        cb = raw_c.encode("utf-8") if isinstance(raw_c, str) else bytes(raw_c)
                        sub_map_b64[str(item["name"])] = base64.b64encode(cb).decode("ascii")
        elif isinstance(submission_files, dict):
            for k, v in submission_files.items():
                if isinstance(v, bytes):
                    sub_map_b64[k] = base64.b64encode(v).decode("ascii")
                else:
                    sub_map_b64[k] = str(v)

        hid = hidden_b64 if hidden_b64 is not None else (hidden_tar_b64 or "")
        payload = {
            "script_b64": base64.b64encode(script_bytes).decode("ascii"),
            "submission_files": sub_map_b64,
            "hidden_b64": hid or "",
            "config": config or {},
            "wall_timeout_sec": wt,
            "cpu_limit_sec": max(1, int(wt)) + 2,
            "fsize_limit_mb": int(prof["fsize_mb"]),
            "memory_limit_mb": int(prof["memory_mb"]),
            "nofile_limit": int(prof.get("nofile", 128)),
            "max_output_bytes": 65536,
            "threads": int(prof.get("threads", 1)),
        }
        res = self._container(env, "evaluate", payload, prof, wt, 4 * 1024 * 1024, kind="evl")
        return self._parse_envelope(res, wt)

    @staticmethod
    def _parse_envelope(res: dict, wall: float) -> ProjectRunResult:
        if res["internal_error"]:
            return ProjectRunResult(ok=False, internal_error=True, error_message=res["stderr"][:MAX_ERROR_CHARS])
        if res["timed_out"]:
            return ProjectRunResult(ok=True, timed_out=True, wall_ms=wall * 1000.0, returncode=-9)
        if res["output_exceeded"]:
            return ProjectRunResult(ok=True, output_exceeded=True, wall_ms=res["elapsed_ms"])
        if res["returncode"] == 137 or not res["stdout"].strip():
            stderr = (res["stderr"] or "").strip()
            return ProjectRunResult(ok=True, returncode=res["returncode"], wall_ms=res["elapsed_ms"],
                                    stderr=stderr[:MAX_ERROR_CHARS], error_message="Process was killed (memory limit or sandbox terminated).")
        try:
            env = json.loads(res["stdout"])
        except Exception as exc:
            return ProjectRunResult(ok=False, internal_error=True, error_message=f"Invalid envelope from sandbox: {exc}")
        if env.get("setup_error"):
            return ProjectRunResult(ok=True, setup_error=str(env["setup_error"])[:1000], stderr=str(env["setup_error"])[:1000], returncode=2)
        dec = lambda k: base64.b64decode(env.get(k, "") or b"").decode("utf-8", errors="replace")
        files = {}
        for n, b in (env.get("files") or {}).items():
            try:
                files[n] = base64.b64decode(b)
            except Exception:
                pass
        stdout_str = dec("stdout_b64")
        stderr_str = dec("stderr_b64")
        harness_results: List[dict] = []
        if "@@CODECLAN_RESULTS@@" in stdout_str:
            stdout_str, _, raw_h = stdout_str.rpartition("@@CODECLAN_RESULTS@@")
            try:
                h_obj = json.loads(raw_h.strip())
                if h_obj.get("load_error"):
                    harness_results = [{"ok": False, "error": str(h_obj["load_error"])}]
                else:
                    for item in h_obj.get("results", []):
                        harness_results.append(
                            {
                                "ok": bool(item.get("ok", False)),
                                "result": item.get("value"),
                                "value": item.get("value"),
                                "error": item.get("error"),
                            }
                        )
            except Exception as exc:
                harness_results = [{"ok": False, "error": f"Invalid harness JSON: {exc}"}]

        return ProjectRunResult(
            ok=True, returncode=int(env.get("returncode", -1)), timed_out=bool(env.get("timed_out")),
            output_exceeded=bool(env.get("output_exceeded")), stdout=stdout_str, stderr=stderr_str,
            max_rss_kb=int(env.get("max_rss_kb", 0)), cpu_ms=float(env.get("cpu_ms", 0)), wall_ms=float(env.get("wall_ms", res["elapsed_ms"])),
            files=files, files_truncated=bool(env.get("files_truncated")), result_json=env.get("result_json", ""),
            harness_results=harness_results,
        )
