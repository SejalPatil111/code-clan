#!/usr/bin/env python3
"""
Isolated entrypoint helper inside the ephemeral codeclan-sandbox container.

Modes:
  - compile: Validates syntax (Python/JS) or compiles source (C/C++/Java) inside
             an isolated container. For compiled languages, emits a base64 tar of
             compiled artifacts on stdout so multiple test cases do not recompile.
  - run:     Materializes the program in /work, binds testcase stdin to fd 0 via
             an anonymous in-memory file descriptor, drops resource limits, wipes
             environment variables, and replaces this process image via os.execvpe()
             so student code runs as PID/child with zero access to the runner state.

Security guarantees:
  - Never uses shell=True.
  - Fixed executable paths and arguments only.
  - Clears environment variables before running student code.
"""

import base64
import io
import json
import os
import re
import resource
import subprocess
import sys
import tarfile

WORKDIR = "/work"

SAFE_ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": WORKDIR,
    "TMPDIR": WORKDIR,
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONUNBUFFERED": "1",
}

JAVA_CLASS_RE = re.compile(r"\bpublic\s+class\s+([A-Za-z_][A-Za-z0-9_]*)\b")
FALLBACK_CLASS_RE = re.compile(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)\b")


def _detect_java_class(code: str) -> str:
    m = JAVA_CLASS_RE.search(code)
    if m:
        return m.group(1)
    m2 = FALLBACK_CLASS_RE.search(code)
    if m2:
        return m2.group(1)
    return "Main"


def _set_limits(cpu_sec: int, fsize_mb: int, memory_mb: int, nproc: int = 32, nofile: int = 64, is_jvm_or_node: bool = False) -> None:
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except Exception:
        pass
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_sec, cpu_sec + 1))
    except Exception:
        pass
    try:
        fsize_bytes = fsize_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize_bytes, fsize_bytes))
    except Exception:
        pass
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (nofile, nofile))
    except Exception:
        pass
    if hasattr(resource, "RLIMIT_NPROC"):
        try:
            # JVM and Node require extra runtime threads; native/Python solutions need very few.
            proc_cap = max(nproc, 48) if is_jvm_or_node else nproc
            resource.setrlimit(resource.RLIMIT_NPROC, (proc_cap, proc_cap))
        except Exception:
            pass
    # JVM and V8 map large virtual address ranges (PROT_NONE) even when physical RSS is small.
    # For native/Python processes we also cap RLIMIT_AS in addition to the Docker cgroup limit.
    if not is_jvm_or_node and memory_mb > 0:
        try:
            as_bytes = memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (as_bytes, as_bytes))
        except Exception:
            pass


def _pack_artifacts(filenames: list[str]) -> str:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name in filenames:
            full = os.path.join(WORKDIR, name)
            if os.path.exists(full):
                tf.add(full, arcname=name)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _unpack_artifacts(artifact_b64: str) -> None:
    raw = base64.b64decode(artifact_b64.encode("ascii"))
    buf = io.BytesIO(raw)
    with tarfile.open(fileobj=buf, mode="r:gz") as tf:
        for member in tf.getmembers():
            # Prevent path traversal
            if member.name.startswith("/") or ".." in member.name:
                continue
            tf.extract(member, path=WORKDIR)


def _handle_compile(payload: dict) -> int:
    lang = payload["language"]
    code = base64.b64decode(payload["code_b64"].encode("ascii")).decode("utf-8", errors="replace")
    os.chdir(WORKDIR)

    if lang == "python":
        src = os.path.join(WORKDIR, "solution.py")
        with open(src, "w", encoding="utf-8") as f:
            f.write(code)
        res = subprocess.run(
            ["/usr/local/bin/python3", "-I", "-B", "-m", "py_compile", src],
            capture_output=True,
            text=True,
            env=SAFE_ENV,
            shell=False,
        )
        if res.returncode != 0:
            sys.stderr.write(res.stderr or res.stdout or "Python syntax error\n")
            return res.returncode
        sys.stdout.write(json.dumps({"ok": True, "artifact_b64": ""}))
        return 0

    if lang == "javascript":
        src = os.path.join(WORKDIR, "solution.js")
        with open(src, "w", encoding="utf-8") as f:
            f.write(code)
        res = subprocess.run(
            ["/usr/bin/node", "--check", src],
            capture_output=True,
            text=True,
            env=SAFE_ENV,
            shell=False,
        )
        if res.returncode != 0:
            sys.stderr.write(res.stderr or res.stdout or "JavaScript syntax error\n")
            return res.returncode
        sys.stdout.write(json.dumps({"ok": True, "artifact_b64": ""}))
        return 0

    if lang == "c":
        src = os.path.join(WORKDIR, "solution.c")
        out = os.path.join(WORKDIR, "solution")
        with open(src, "w", encoding="utf-8") as f:
            f.write(code)
        res = subprocess.run(
            ["/usr/bin/gcc", "-O2", "-std=c11", "-Wall", src, "-o", out, "-lm"],
            capture_output=True,
            text=True,
            env=SAFE_ENV,
            shell=False,
        )
        if res.returncode != 0:
            sys.stderr.write(res.stderr or res.stdout or "C compilation failed\n")
            return res.returncode
        os.chmod(out, 0o755)
        sys.stdout.write(json.dumps({"ok": True, "artifact_b64": _pack_artifacts(["solution"])}))
        return 0

    if lang == "cpp":
        src = os.path.join(WORKDIR, "solution.cpp")
        out = os.path.join(WORKDIR, "solution")
        with open(src, "w", encoding="utf-8") as f:
            f.write(code)
        res = subprocess.run(
            ["/usr/bin/g++", "-O2", "-std=c++17", "-Wall", src, "-o", out],
            capture_output=True,
            text=True,
            env=SAFE_ENV,
            shell=False,
        )
        if res.returncode != 0:
            sys.stderr.write(res.stderr or res.stdout or "C++ compilation failed\n")
            return res.returncode
        os.chmod(out, 0o755)
        sys.stdout.write(json.dumps({"ok": True, "artifact_b64": _pack_artifacts(["solution"])}))
        return 0

    if lang == "java":
        class_name = _detect_java_class(code)
        src = os.path.join(WORKDIR, f"{class_name}.java")
        with open(src, "w", encoding="utf-8") as f:
            f.write(code)
        res = subprocess.run(
            [
                "/usr/bin/javac",
                "-J-Xmx128m",
                "-J-XX:+UseSerialGC",
                "-encoding",
                "UTF-8",
                src,
            ],
            capture_output=True,
            text=True,
            env=SAFE_ENV,
            shell=False,
        )
        if res.returncode != 0:
            sys.stderr.write(res.stderr or res.stdout or "Java compilation failed\n")
            return res.returncode
        with open(os.path.join(WORKDIR, ".main_class"), "w", encoding="utf-8") as f:
            f.write(class_name)
        class_files = [fn for fn in os.listdir(WORKDIR) if fn.endswith(".class") or fn == ".main_class"]
        sys.stdout.write(json.dumps({"ok": True, "artifact_b64": _pack_artifacts(class_files)}))
        return 0

    sys.stderr.write(f"Unsupported language: {lang}\n")
    return 2


def _handle_run(payload: dict) -> None:
    lang = payload["language"]
    code_b64 = payload.get("code_b64", "")
    artifact_b64 = payload.get("artifact_b64", "")
    stdin_bytes = base64.b64decode(payload.get("stdin_b64", "").encode("ascii"))
    cpu_sec = int(payload.get("cpu_limit_sec", 3))
    fsize_mb = int(payload.get("fsize_limit_mb", 8))
    memory_mb = int(payload.get("memory_limit_mb", 256))
    nproc = int(payload.get("nproc_limit", 32))
    nofile = int(payload.get("nofile_limit", 64))

    os.chdir(WORKDIR)

    if lang == "python":
        code = base64.b64decode(code_b64.encode("ascii")).decode("utf-8", errors="replace")
        src = os.path.join(WORKDIR, "solution.py")
        with open(src, "w", encoding="utf-8") as f:
            f.write(code)
        os.chmod(src, 0o400)
        cmd = ["/usr/local/bin/python3", "-I", "-B", src]
        is_jvm_or_node = False

    elif lang == "javascript":
        code = base64.b64decode(code_b64.encode("ascii")).decode("utf-8", errors="replace")
        src = os.path.join(WORKDIR, "solution.js")
        with open(src, "w", encoding="utf-8") as f:
            f.write(code)
        os.chmod(src, 0o400)
        cmd = ["/usr/bin/node", "--max-old-space-size=128", src]
        is_jvm_or_node = True

    elif lang in ("c", "cpp"):
        _unpack_artifacts(artifact_b64)
        exe = os.path.join(WORKDIR, "solution")
        os.chmod(exe, 0o500)
        cmd = [exe]
        is_jvm_or_node = False

    elif lang == "java":
        _unpack_artifacts(artifact_b64)
        mc_path = os.path.join(WORKDIR, ".main_class")
        main_class = "Main"
        if os.path.exists(mc_path):
            with open(mc_path, "r", encoding="utf-8") as f:
                main_class = f.read().strip() or "Main"
            os.remove(mc_path)
        cmd = [
            "/usr/bin/java",
            "-Xmx128m",
            "-Xms16m",
            "-XX:+UseSerialGC",
            "-XX:CompressedClassSpaceSize=32m",
            "-XX:MaxMetaspaceSize=64m",
            "-cp",
            WORKDIR,
            main_class,
        ]
        is_jvm_or_node = True

    else:
        sys.stderr.write(f"Unsupported language: {lang}\n")
        sys.exit(2)

    # Bind testcase input to fd 0 via an anonymous in-memory file descriptor (with unlinked /tmp fallback)
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
            if stdin_bytes:
                tf.write(stdin_bytes)
        tmp_fd = os.open(stdin_tmp, os.O_RDONLY)
        os.unlink(stdin_tmp)
        os.dup2(tmp_fd, 0)
        os.close(tmp_fd)

    # Wipe environment and apply kernel rlimits before replacing process image
    os.environ.clear()
    os.environ.update(SAFE_ENV)
    _set_limits(
        cpu_sec=cpu_sec,
        fsize_mb=fsize_mb,
        memory_mb=memory_mb,
        is_jvm_or_node=is_jvm_or_node,
        nproc=nproc,
        nofile=nofile,
    )

    os.execvpe(cmd[0], cmd, SAFE_ENV)


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("compile", "run"):
        sys.stderr.write("Usage: sandbox-runner <compile|run>\n")
        sys.exit(2)

    mode = sys.argv[1]
    raw_input = sys.stdin.buffer.read()
    try:
        payload = json.loads(raw_input.decode("utf-8"))
    except Exception as exc:
        sys.stderr.write(f"Invalid runner payload: {exc}\n")
        sys.exit(2)

    if mode == "compile":
        rc = _handle_compile(payload)
        sys.exit(rc)
    else:
        _handle_run(payload)


if __name__ == "__main__":
    main()
