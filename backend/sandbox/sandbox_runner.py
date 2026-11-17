#!/usr/bin/env python3
"""
CodeClan sandbox runner (v2) - the ONLY command the policy proxy lets a sandbox container execute.

Modes (argv[1]); the JSON payload arrives on stdin:
  probe        Print kernel identity (/proc/version) so the grader can verify the actual runtime.
  compile      Validate/compile a project (one or many files). C/C++/Java emit a tar.gz artifact.
  run          Legacy competitive mode: bind stdin to fd 0, drop limits, os.execvpe() the program so
               its stdout/stderr/exit code ARE the container's.
  run_project  Supervisor mode: run the program as a child with limits, capture bounded stdout/stderr,
               collect generated files from /work/output, report resource usage, emit a JSON envelope.
  evaluate     Same supervisor, used for grader/teacher-owned evaluator scripts in a SEPARATE container
               that never holds student code (only student output data + hidden evaluation data).

Security notes:
  * No shell=True anywhere; fixed interpreters/arguments.
  * Environment is wiped before untrusted code runs.
  * All file paths from payloads are validated (relative, no '..', no symlinks/devices in archives).
  * The supervisor shares a PID namespace/UID with the student program (student can kill it). That only
    affects the student's own throw-away sandbox; envelope contents are treated as student-controlled data.
"""

import base64
import io
import json
import os
import posixpath
import re
import resource
import signal
import subprocess
import sys
import tarfile
import threading
import time

WORKDIR = "/work"
DATA_DIR = os.path.join(WORKDIR, "data")
OUTPUT_DIR = os.path.join(WORKDIR, "output")

BASE_ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": WORKDIR,
    "TMPDIR": WORKDIR,
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONUNBUFFERED": "1",
}
SAFE_ENV = dict(BASE_ENV)  # legacy name

MAX_FILES = 300
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_PROJECT_BYTES = 64 * 1024 * 1024

JAVA_CLASS_RE = re.compile(r"\bpublic\s+class\s+([A-Za-z_][A-Za-z0-9_]*)\b")
FALLBACK_CLASS_RE = re.compile(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)\b")
DEFAULT_NAMES = {"python": "solution.py", "javascript": "solution.js", "c": "solution.c", "cpp": "solution.cpp"}

HARNESS = r'''
import json, sys, os, importlib, traceback, io
cases = json.loads(sys.stdin.read() or "[]")
mod_name, fn_name = sys.argv[1], sys.argv[2]
real_out = sys.stdout
sys.stdout = sys.stderr            # student prints go to stderr, never into the result stream
results = []
try:
    sys.path.insert(0, os.getcwd())
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, fn_name)
except BaseException as e:
    real_out.write("\n@@CODECLAN_RESULTS@@" + json.dumps({"load_error": type(e).__name__ + ": " + str(e)[:300]}))
    sys.exit(0)
for c in cases:
    try:
        v = fn(*c.get("args", []), **c.get("kwargs", {}))
        json.dumps(v)
        results.append({"ok": True, "value": v})
    except BaseException as e:
        results.append({"ok": False, "error": type(e).__name__ + ": " + str(e)[:200]})
real_out.write("\n@@CODECLAN_RESULTS@@" + json.dumps({"results": results}))
real_out.flush()
'''


# ----------------------------------------------------------------------------- helpers
def _detect_java_class(code: str) -> str:
    m = JAVA_CLASS_RE.search(code)
    if m:
        return m.group(1)
    m2 = FALLBACK_CLASS_RE.search(code)
    return m2.group(1) if m2 else "Main"


def _set_limits(cpu_sec, fsize_mb, memory_mb, nproc=0, nofile=64, is_jvm_or_node=False, address_space=True):
    def _try(res, val):
        try:
            resource.setrlimit(res, val)
        except Exception:
            pass

    _try(resource.RLIMIT_CORE, (0, 0))
    _try(resource.RLIMIT_CPU, (cpu_sec, cpu_sec + 1))
    fsize = fsize_mb * 1024 * 1024
    _try(resource.RLIMIT_FSIZE, (fsize, fsize))
    _try(resource.RLIMIT_NOFILE, (nofile, nofile))
    # RLIMIT_NPROC is accounted per HOST uid (shared by concurrent runc sandboxes) so it is opt-in;
    # the per-container cgroup pids-limit is the fork-bomb control.
    if nproc > 0 and hasattr(resource, "RLIMIT_NPROC"):
        cap = max(nproc, 48) if is_jvm_or_node else nproc
        _try(resource.RLIMIT_NPROC, (cap, cap))
    if address_space and not is_jvm_or_node and memory_mb > 0:
        _try(resource.RLIMIT_AS, (memory_mb * 1024 * 1024, memory_mb * 1024 * 1024))


def _safe_rel(path: str) -> str:
    p = posixpath.normpath(path.replace("\\", "/"))
    if p.startswith("/") or p == ".." or p.startswith("../") or "\x00" in p or p in (".", ""):
        raise ValueError(f"unsafe path: {path!r}")
    if len(p) > 200 or p.count("/") > 8:
        raise ValueError(f"path too long/deep: {path!r}")
    return p


def _materialize_files(files: dict, base: str = WORKDIR) -> list:
    """Write {relpath: base64} into base. Returns list of relative paths."""
    if len(files) > MAX_FILES:
        raise ValueError("too many files")
    total = 0
    written = []
    for rel, b64 in files.items():
        p = _safe_rel(rel)
        data = base64.b64decode(b64.encode("ascii"))
        total += len(data)
        if len(data) > MAX_FILE_BYTES or total > MAX_PROJECT_BYTES:
            raise ValueError("project too large")
        full = os.path.join(base, p)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(data)
        written.append(p)
    return written


def _payload_files(payload: dict) -> dict:
    """Return {relpath: b64}. Supports legacy single `code_b64`."""
    files = payload.get("files") or {}
    if files:
        return files
    code_b64 = payload.get("code_b64") or ""
    lang = payload.get("language")
    if not code_b64:
        return {}
    if lang == "java":
        code = base64.b64decode(code_b64).decode("utf-8", errors="replace")
        return {f"{_detect_java_class(code)}.java": code_b64}
    return {DEFAULT_NAMES.get(lang, "solution.txt"): code_b64}


def _pack_tree(rel_paths: list) -> str:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name in rel_paths:
            full = os.path.join(WORKDIR, name)
            if os.path.isfile(full):
                tf.add(full, arcname=name)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _pack_artifacts(filenames: list) -> str:  # legacy
    return _pack_tree(filenames)


def _safe_extract(raw: bytes, dest: str, max_total: int = MAX_PROJECT_BYTES) -> None:
    """Extract a tar.gz: regular files/dirs only; reject traversal, links, devices, oversize."""
    total = 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
        for m in tf.getmembers():
            if not (m.isfile() or m.isdir()):
                continue  # silently skip symlinks/hardlinks/devices/fifos
            name = _safe_rel(m.name)
            target = os.path.join(dest, name)
            if m.isdir():
                os.makedirs(target, exist_ok=True)
                continue
            total += m.size
            if total > max_total or m.size > MAX_FILE_BYTES * 8:
                raise ValueError("archive too large")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            src = tf.extractfile(m)
            with open(target, "wb") as out:
                out.write(src.read())
            os.chmod(target, 0o755 if (m.mode & 0o111) else 0o644)


def _unpack_artifacts(artifact_b64: str) -> None:
    _safe_extract(base64.b64decode(artifact_b64.encode("ascii")), WORKDIR)


def _collect_sources(exts: tuple) -> list:
    found = []
    for root, _dirs, names in os.walk(WORKDIR):
        for n in names:
            if n.endswith(exts):
                found.append(os.path.relpath(os.path.join(root, n), WORKDIR))
    return sorted(found)


def _run_tool(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, env=BASE_ENV, shell=False, cwd=WORKDIR)


# ----------------------------------------------------------------------------- compile
def _handle_compile(payload: dict) -> int:
    lang = payload["language"]
    files = _payload_files(payload)
    if not files:
        sys.stderr.write("No source files provided.\n")
        return 2
    os.chdir(WORKDIR)
    try:
        written = _materialize_files(files)
    except Exception as exc:
        sys.stderr.write(f"Invalid project files: {exc}\n")
        return 2
    entry = payload.get("entry_point") or ""

    def ok(artifact="") -> int:
        sys.stdout.write(json.dumps({"ok": True, "artifact_b64": artifact}))
        return 0

    if lang == "python":
        srcs = [p for p in written if p.endswith(".py")]
        if not srcs:
            sys.stderr.write("No .py files found.\n")
            return 2
        res = _run_tool(["/usr/local/bin/python3", "-I", "-B", "-m", "py_compile", *srcs])
        if res.returncode != 0:
            sys.stderr.write(res.stderr or res.stdout or "Python syntax error\n")
            return res.returncode
        return ok()

    if lang == "javascript":
        for p in [p for p in written if p.endswith((".js", ".mjs", ".cjs"))]:
            res = _run_tool(["/usr/bin/node", "--check", p])
            if res.returncode != 0:
                sys.stderr.write(res.stderr or res.stdout or "JavaScript syntax error\n")
                return res.returncode
        return ok()

    if lang in ("c", "cpp"):
        exts = (".c",) if lang == "c" else (".cpp", ".cc", ".cxx")
        srcs = _collect_sources(exts)
        if not srcs:
            sys.stderr.write(f"No {'/'.join(exts)} source files found.\n")
            return 2
        cmd = (["/usr/bin/gcc", "-O2", "-std=c11", "-Wall", "-I.", *srcs, "-o", "solution", "-lm"] if lang == "c"
               else ["/usr/bin/g++", "-O2", "-std=c++17", "-Wall", "-I.", *srcs, "-o", "solution"])
        res = _run_tool(cmd)
        if res.returncode != 0:
            sys.stderr.write(res.stderr or res.stdout or "Compilation failed\n")
            return res.returncode
        os.chmod(os.path.join(WORKDIR, "solution"), 0o755)
        return ok(_pack_tree(["solution"]))

    if lang == "java":
        srcs = _collect_sources((".java",))
        if not srcs:
            sys.stderr.write("No .java files found.\n")
            return 2
        res = _run_tool(["/usr/bin/javac", "-J-Xmx128m", "-J-XX:+UseSerialGC", "-encoding", "UTF-8", "-d", WORKDIR, *srcs])
        if res.returncode != 0:
            sys.stderr.write(res.stderr or res.stdout or "Java compilation failed\n")
            return res.returncode
        if entry:
            main_class = entry[:-5] if entry.endswith(".java") else entry
            main_class = main_class.replace("/", ".")
        else:
            main_class = None
            for s in srcs:
                code = open(os.path.join(WORKDIR, s), encoding="utf-8", errors="replace").read()
                if "static void main" in code:
                    main_class = _detect_java_class(code)
                    break
            main_class = main_class or _detect_java_class(open(os.path.join(WORKDIR, srcs[0]), encoding="utf-8", errors="replace").read())
        with open(os.path.join(WORKDIR, ".main_class"), "w", encoding="utf-8") as f:
            f.write(main_class)
        class_files = _collect_sources((".class",)) + [".main_class"]
        return ok(_pack_tree(class_files))

    sys.stderr.write(f"Unsupported language: {lang}\n")
    return 2


# ----------------------------------------------------------------------------- program command
def _program_cmd(payload: dict, written: list):
    """Return (cmd, is_jvm_or_node)."""
    lang = payload["language"]
    entry = payload.get("entry_point") or ""
    if lang == "python":
        cands = [entry] if entry else []
        cands += ["main.py", "solution.py"]
        script = next((c for c in cands if c and os.path.isfile(os.path.join(WORKDIR, _safe_rel(c)))), None)
        if not script:
            py = [w for w in written if w.endswith(".py")]
            script = py[0] if py else None
        if not script:
            raise ValueError("No Python entry point found")
        multi = len(written) > 1 or payload.get("project_mode")
        flags = ["-E", "-s", "-B"] if multi else ["-I", "-B"]
        return ["/usr/local/bin/python3", *flags, script], False
    if lang == "javascript":
        cands = [entry] if entry else []
        cands += ["main.js", "index.js", "solution.js"]
        script = next((c for c in cands if c and os.path.isfile(os.path.join(WORKDIR, _safe_rel(c)))), None)
        if not script:
            raise ValueError("No JavaScript entry point found")
        return ["/usr/bin/node", "--max-old-space-size=%d" % int(payload.get("node_heap_mb", 128)), script], True
    if lang in ("c", "cpp"):
        return [os.path.join(WORKDIR, "solution")], False
    if lang == "java":
        mc = os.path.join(WORKDIR, ".main_class")
        main_class = "Main"
        if os.path.exists(mc):
            main_class = open(mc, encoding="utf-8").read().strip() or "Main"
            os.remove(mc)
        heap = int(payload.get("java_heap_mb", 128))
        return ["/usr/bin/java", f"-Xmx{heap}m", "-Xms16m", "-XX:+UseSerialGC",
                "-XX:CompressedClassSpaceSize=32m", "-XX:MaxMetaspaceSize=64m", "-cp", WORKDIR, main_class], True
    raise ValueError(f"Unsupported language: {lang}")


def _prepare_workspace(payload: dict) -> list:
    """Materialize sources/artifacts/datasets. Returns written source paths."""
    os.chdir(WORKDIR)
    written = []
    files = _payload_files(payload)
    if files:
        written = _materialize_files(files)
    if payload.get("artifact_b64"):
        _unpack_artifacts(payload["artifact_b64"])
    ds = payload.get("datasets_b64") or ""
    if ds:
        os.makedirs(DATA_DIR, exist_ok=True)
        _safe_extract(base64.b64decode(ds.encode("ascii")), DATA_DIR)
        for root, dirs, names in os.walk(DATA_DIR):
            for n in names:
                try:
                    os.chmod(os.path.join(root, n), 0o444)
                except Exception:
                    pass
    return written


# ----------------------------------------------------------------------------- run (legacy exec)
def _handle_run(payload: dict) -> None:
    cpu_sec = int(payload.get("cpu_limit_sec", 3))
    fsize_mb = int(payload.get("fsize_limit_mb", 8))
    memory_mb = int(payload.get("memory_limit_mb", 256))
    nproc = int(payload.get("nproc_limit", 0))
    nofile = int(payload.get("nofile_limit", 64))
    stdin_bytes = base64.b64decode(payload.get("stdin_b64", "").encode("ascii"))
    try:
        written = _prepare_workspace(payload)
        cmd, is_jvm_or_node = _program_cmd(payload, written)
    except Exception as exc:
        sys.stderr.write(f"{exc}\n")
        sys.exit(2)
    for w in written:  # student sources become read-only
        try:
            os.chmod(os.path.join(WORKDIR, w), 0o400)
        except Exception:
            pass

    try:
        mem_fd = os.memfd_create("testcase_stdin", 0)
        if stdin_bytes:
            os.write(mem_fd, stdin_bytes)
        os.lseek(mem_fd, 0, os.SEEK_SET)
        os.dup2(mem_fd, 0)
        os.close(mem_fd)
    except OSError:
        stdin_tmp = "/tmp/.stdin_buf"
        with open(stdin_tmp, "wb") as tf:
            tf.write(stdin_bytes)
        tmp_fd = os.open(stdin_tmp, os.O_RDONLY)
        os.unlink(stdin_tmp)
        os.dup2(tmp_fd, 0)
        os.close(tmp_fd)

    os.environ.clear()
    os.environ.update(BASE_ENV)
    _set_limits(cpu_sec, fsize_mb, memory_mb, nproc, nofile, is_jvm_or_node)
    os.execvpe(cmd[0], cmd, BASE_ENV)


# ----------------------------------------------------------------------------- supervisor
def _supervise(cmd: list, payload: dict, is_jvm_or_node: bool, extra_env: dict, stdin_bytes: bytes) -> dict:
    cpu_sec = int(payload.get("cpu_limit_sec", 10))
    fsize_mb = int(payload.get("fsize_limit_mb", 16))
    memory_mb = int(payload.get("memory_limit_mb", 512))
    nproc = int(payload.get("nproc_limit", 0))
    nofile = int(payload.get("nofile_limit", 128))
    wall = float(payload.get("wall_timeout_sec", 10))
    out_cap = int(payload.get("max_output_bytes", 65536))
    threads = str(int(payload.get("threads", 1)))
    address_space = bool(payload.get("limit_address_space", False))

    env = dict(BASE_ENV)
    env.update({
        "CODECLAN_DATA_DIR": DATA_DIR, "CODECLAN_OUTPUT_DIR": OUTPUT_DIR,
        "OMP_NUM_THREADS": threads, "OPENBLAS_NUM_THREADS": threads, "MKL_NUM_THREADS": threads,
        "NUMEXPR_NUM_THREADS": threads, "TF_NUM_INTRAOP_THREADS": threads, "TF_NUM_INTEROP_THREADS": threads,
        "MPLBACKEND": "Agg", "MPLCONFIGDIR": "/tmp", "NLTK_DATA": "/opt/nltk_data",
        "TF_CPP_MIN_LOG_LEVEL": "2", "NUMBA_CACHE_DIR": "/tmp", "XDG_CACHE_HOME": "/tmp",
    })
    env.update(extra_env or {})

    def preexec():
        os.setsid()
        _set_limits(cpu_sec, fsize_mb, memory_mb, nproc, nofile, is_jvm_or_node, address_space)

    t0 = time.perf_counter()
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            cwd=WORKDIR, env=env, preexec_fn=preexec, shell=False)
    bufs = {"out": bytearray(), "err": bytearray()}
    flags = {"exceeded": False}

    def kill_group():
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def reader(pipe, key):
        try:
            while True:
                chunk = pipe.read(8192)
                if not chunk:
                    break
                room = out_cap - len(bufs[key])
                if room > 0:
                    bufs[key].extend(chunk[:room])
                if len(chunk) > room and not flags["exceeded"]:
                    flags["exceeded"] = True
                    kill_group()
                    break
        except Exception:
            pass

    def writer():
        try:
            proc.stdin.write(stdin_bytes)
        except Exception:
            pass
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass

    ts = [threading.Thread(target=reader, args=(proc.stdout, "out"), daemon=True),
          threading.Thread(target=reader, args=(proc.stderr, "err"), daemon=True),
          threading.Thread(target=writer, daemon=True)]
    for t in ts:
        t.start()
    timed_out = False
    try:
        proc.wait(timeout=wall)
    except subprocess.TimeoutExpired:
        timed_out = True
        kill_group()
        try:
            proc.wait(timeout=3)
        except Exception:
            pass
    for t in ts[:2]:
        t.join(timeout=2)
    wall_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    ru = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {
        "returncode": proc.returncode if proc.returncode is not None else -9,
        "timed_out": timed_out,
        "output_exceeded": flags["exceeded"],
        "stdout_b64": base64.b64encode(bytes(bufs["out"])).decode("ascii"),
        "stderr_b64": base64.b64encode(bytes(bufs["err"])).decode("ascii"),
        "max_rss_kb": int(ru.ru_maxrss),
        "cpu_ms": round((ru.ru_utime + ru.ru_stime) * 1000.0, 2),
        "wall_ms": wall_ms,
    }


def _collect_output_files(payload: dict) -> tuple:
    max_files = int(payload.get("max_output_files", 20))
    max_total = int(payload.get("max_output_files_bytes", 4 * 1024 * 1024))
    files, total, truncated = {}, 0, False
    if not os.path.isdir(OUTPUT_DIR):
        return files, truncated
    for root, _dirs, names in os.walk(OUTPUT_DIR):
        for n in sorted(names):
            full = os.path.join(root, n)
            rel = os.path.relpath(full, OUTPUT_DIR).replace("\\", "/")
            try:
                if os.path.islink(full):
                    continue
                fd = os.open(full, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, "rb") as f:
                    data = f.read(max_total - total + 1)
            except Exception:
                continue
            if len(files) >= max_files or total + len(data) > max_total:
                truncated = True
                continue
            total += len(data)
            files[rel] = base64.b64encode(data).decode("ascii")
    return files, truncated


def _handle_run_project(payload: dict) -> int:
    try:
        written = _prepare_workspace(payload)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        stdin_bytes = base64.b64decode(payload.get("stdin_b64", "").encode("ascii"))
        harness = payload.get("harness")
        if harness and payload["language"] == "python":
            hpath = os.path.join(WORKDIR, ".codeclan_harness.py")
            with open(hpath, "w", encoding="utf-8") as f:
                f.write(HARNESS)
            mod = _safe_rel(harness["module"]).replace("/", ".")
            mod = mod[:-3] if mod.endswith(".py") else mod
            cmd = ["/usr/local/bin/python3", "-E", "-s", "-B", hpath, mod, harness["function"]]
            is_jvm = False
        else:
            cmd, is_jvm = _program_cmd(payload, written)
    except Exception as exc:
        sys.stdout.write(json.dumps({"setup_error": str(exc)[:500]}))
        return 0
    env = _supervise(cmd, payload, is_jvm, {}, stdin_bytes)
    files, truncated = _collect_output_files(payload)
    env["files"] = files
    env["files_truncated"] = truncated
    sys.stdout.write(json.dumps(env))
    return 0


def _handle_evaluate(payload: dict) -> int:
    """Run a grader/teacher evaluator script. Layout: /work/submission, /work/hidden, /work/evaluator.py"""
    try:
        os.chdir(WORKDIR)
        sub_dir, hid_dir = os.path.join(WORKDIR, "submission"), os.path.join(WORKDIR, "hidden")
        os.makedirs(sub_dir, exist_ok=True)
        os.makedirs(hid_dir, exist_ok=True)
        _materialize_files(payload.get("submission_files") or {}, sub_dir)
        if payload.get("hidden_b64"):
            _safe_extract(base64.b64decode(payload["hidden_b64"].encode("ascii")), hid_dir)
        script = os.path.join(WORKDIR, "evaluator.py")
        with open(script, "wb") as f:
            f.write(base64.b64decode(payload["script_b64"].encode("ascii")))
        with open(os.path.join(WORKDIR, "config.json"), "w", encoding="utf-8") as f:
            json.dump(payload.get("config") or {}, f)
    except Exception as exc:
        sys.stdout.write(json.dumps({"setup_error": str(exc)[:500]}))
        return 0
    result_path = os.path.join(WORKDIR, "result.json")
    extra = {"CODECLAN_SUBMISSION_DIR": sub_dir, "CODECLAN_HIDDEN_DIR": hid_dir,
             "CODECLAN_CONFIG": os.path.join(WORKDIR, "config.json"), "CODECLAN_RESULT_PATH": result_path}
    env = _supervise(["/usr/local/bin/python3", "-E", "-s", "-B", script], payload, False, extra, b"")
    try:
        with open(result_path, "rb") as f:
            env["result_json"] = f.read(65536).decode("utf-8", errors="replace")
    except Exception:
        env["result_json"] = ""
    sys.stdout.write(json.dumps(env))
    return 0


def _handle_probe() -> int:
    try:
        ver = open("/proc/version", encoding="utf-8").read().strip()
    except Exception as exc:
        ver = f"unreadable: {exc}"
    manifest = None
    try:
        manifest = json.load(open("/opt/codeclan-manifest.json", encoding="utf-8"))
    except Exception:
        pass
    sys.stdout.write(json.dumps({"proc_version": ver, "uname": " ".join(os.uname()), "uid": os.getuid(),
                                 "env_id": os.environ.get("CODECLAN_ENV_ID"), "manifest": manifest}))
    return 0


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("compile", "run", "run_project", "evaluate", "probe"):
        sys.stderr.write("Usage: sandbox-runner <compile|run|run_project|evaluate|probe>\n")
        sys.exit(2)
    mode = sys.argv[1]
    if mode == "probe":
        sys.exit(_handle_probe())
    raw = sys.stdin.buffer.read()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        sys.stderr.write(f"Invalid payload: {exc}\n")
        sys.exit(2)
    if mode == "compile":
        sys.exit(_handle_compile(payload))
    if mode == "run":
        _handle_run(payload)
        return
    if mode == "run_project":
        sys.exit(_handle_run_project(payload))
    if mode == "evaluate":
        sys.exit(_handle_evaluate(payload))


if __name__ == "__main__":
    main()
