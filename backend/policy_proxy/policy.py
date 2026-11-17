"""
CodeClan Docker API policy engine (pure functions, no I/O) used by the policy proxy.

Why this exists
---------------
Path/method-level Docker socket proxies (e.g. tecnativa/docker-socket-proxy) cannot inspect the JSON
body of `POST /containers/create`. With CONTAINERS=1 + POST=1 a compromised client can therefore create
privileged containers, bind-mount the host root, share the host PID/network namespace, add all
capabilities, pick any runtime/image, and manage unrelated containers. This policy validates the BODY.

Design rules
------------
* Default deny. Only the exact Docker API calls the grader needs are allowed.
* Container operations are restricted to containers whose NAME matches `codeclan-(sbx|evl)-...`.
* `POST /containers/create` bodies are validated against an allowlist of keys. Dangerous keys must be
  falsy; unknown keys are rejected. Go's encoding/json matches keys case-insensitively, so keys are
  compared lower-cased and case-colliding duplicates are rejected.
* The runtime, image, user, memory, pids, CPU, tmpfs and command are constrained.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
from typing import Any, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

Decision = Tuple[bool, str]

NAME_RE = re.compile(r"^codeclan-(sbx|evl)-[a-z0-9][a-z0-9-]{2,60}$")
NAME_FILTER_PREFIXES = ("codeclan-sbx-", "codeclan-evl-")
VERSION_PREFIX_RE = re.compile(r"^/v\d+\.\d+(?=/)")
RUNNER_PATH = "/usr/local/bin/sandbox-runner"
RUNNER_MODES = {"compile", "run", "run_project", "evaluate", "probe"}
ALLOWED_TMPFS_PATHS = {"/work", "/tmp", "/data"}
ALLOWED_ULIMITS = {"nofile", "nproc", "fsize", "core", "cpu", "as"}

_FALSY_HOSTCONFIG = {
    "binds", "volumesfrom", "capadd", "dns", "dnsoptions", "dnssearch", "extrahosts", "groupadd",
    "links", "portbindings", "publishallports", "privileged", "pidmode", "usernsmode", "utsmode",
    "cgroupparent", "cgroup", "devices", "devicecgrouprules", "devicerequests", "mounts", "sysctls",
    "volumedriver", "isolation", "containeridfile", "oomscoreadj", "cpushares", "cpuperiod",
    "cpuquota", "cpusetcpus", "cpusetmems", "blkioweight", "blkioweightdevice", "blkiodevicereadbps",
    "blkiodevicewritebps", "blkiodevicereadiops", "blkiodevicewriteiops", "kernelmemory",
    "kernelmemorytcp", "memoryreservation", "cpucount", "cpupercent", "iomaximumiops",
    "iomaximumbandwidth", "diskquota", "cpurealtimeperiod", "cpurealtimeruntime", "annotations",
    "storageopt", "oomkilldisable", "cpuquota", "cpusetcpus",
}
_ALLOWED_HOSTCONFIG = {
    "networkmode", "ipcmode", "readonlyrootfs", "capdrop", "securityopt", "tmpfs", "runtime",
    "memory", "memoryswap", "nanocpus", "pidslimit", "ulimits", "autoremove", "cgroupnsmode",
    "logconfig", "restartpolicy", "init", "shmsize", "consolesize", "memoryswappiness",
}
_FALSY_CONFIG = {"exposedports", "volumes", "healthcheck", "onbuild", "shell", "macaddress",
                 "networkdisabled", "argsescaped", "stopsignal"}
_ALLOWED_CONFIG = {
    "hostname", "domainname", "user", "attachstdin", "attachstdout", "attachstderr", "tty",
    "openstdin", "stdinonce", "env", "cmd", "image", "workingdir", "entrypoint", "labels",
    "hostconfig", "networkingconfig", "stoptimeout",
}
_ALLOWED_SECURITY_OPT = {"no-new-privileges", "no-new-privileges=true", "no-new-privileges:true"}


class Policy:
    def __init__(self) -> None:
        env = os.environ.get
        raw_rt = env("PROXY_ALLOWED_RUNTIMES") or env("POLICY_ALLOWED_RUNTIMES") or "runsc"
        raw_img = env("PROXY_ALLOWED_IMAGES") or env("POLICY_ALLOWED_IMAGES") or "codeclan-sandbox:latest,codeclan-env-*"
        self.allowed_runtimes = {r.strip() for r in raw_rt.split(",") if r.strip()}
        self.allowed_images = [p.strip() for p in raw_img.split(",") if p.strip()]
        self.allowed_users = {u.strip() for u in env("PROXY_ALLOWED_USERS", "65534:65534").split(",") if u.strip()}
        self.max_memory = int(env("PROXY_MAX_MEMORY_MB", "4096")) * 1024 * 1024
        self.max_pids = int(env("PROXY_MAX_PIDS", "512"))
        self.max_nano_cpus = int(float(env("PROXY_MAX_CPUS", "4")) * 1_000_000_000)
        self.max_tmpfs = int(env("PROXY_MAX_TMPFS_MB", "1024")) * 1024 * 1024
        self.owned_ids: set[str] = set()

    def register_owned_id(self, cid: str) -> None:
        clean = (cid or "").strip().lower()
        if len(clean) >= 12:
            self.owned_ids.add(clean)
            self.owned_ids.add(clean[:12])

    def is_allowed_container_ref(self, ref: str) -> bool:
        if NAME_RE.match(ref):
            return True
        low = (ref or "").strip().lower()
        return len(low) >= 12 and low in self.owned_ids

    # ------------------------------------------------------------------ helpers
    def image_allowed(self, image: str) -> bool:
        return isinstance(image, str) and any(fnmatch.fnmatchcase(image, p) for p in self.allowed_images)

    @staticmethod
    def _lower_keys(obj: Any, where: str) -> Tuple[Optional[dict], Optional[str]]:
        if obj is None:
            return {}, None
        if not isinstance(obj, dict):
            return None, f"{where} must be an object"
        out: dict = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in out:
                return None, f"{where}: duplicate/case-colliding key '{k}'"
            out[lk] = v
        return out, None

    @staticmethod
    def _falsy(v: Any) -> bool:
        return v in (None, "", 0, False, [], {}, "0")

    @staticmethod
    def _size_bytes(opt: str) -> Optional[int]:
        m = re.fullmatch(r"(\d+)([kmg]?)", opt.lower())
        if not m:
            return None
        return int(m.group(1)) * {"": 1, "k": 1024, "m": 1024 ** 2, "g": 1024 ** 3}[m.group(2)]

    # ------------------------------------------------------------- create body
    def validate_create(self, query: dict, body: bytes) -> Decision:
        names = query.get("name", [])
        if len(names) != 1 or not NAME_RE.match(names[0]):
            return False, "container name must match codeclan-(sbx|evl)-<id>"
        for q in query:
            if q not in ("name",):
                return False, f"query parameter '{q}' not allowed on create"
        try:
            data = json.loads(body.decode("utf-8")) if body else None
        except Exception:
            return False, "create body is not valid JSON"
        cfg, err = self._lower_keys(data, "config")
        if err or cfg is None:
            return False, err or "empty config"
        for k, v in cfg.items():
            if k in _FALSY_CONFIG:
                if not self._falsy(v):
                    return False, f"config.{k} must be empty"
            elif k not in _ALLOWED_CONFIG:
                return False, f"config key '{k}' not allowed"

        if not self.image_allowed(cfg.get("image", "")):
            return False, f"image '{cfg.get('image')}' is not an approved CodeClan environment image"
        if not self._falsy(cfg.get("env")):
            return False, "config.env must be empty (no environment injection)"
        if not self._falsy(cfg.get("entrypoint")):
            return False, "config.entrypoint must be empty"
        cmd = cfg.get("cmd")
        if not (isinstance(cmd, list) and len(cmd) == 2 and cmd[0] == RUNNER_PATH and cmd[1] in RUNNER_MODES):
            return False, f"command must be exactly [{RUNNER_PATH}, <{'|'.join(sorted(RUNNER_MODES))}>]"
        if cfg.get("user") not in self.allowed_users:
            return False, f"user must be one of {sorted(self.allowed_users)}"
        if cfg.get("workingdir") not in ("/work", "", None):
            return False, "workingdir must be /work"
        if cfg.get("tty"):
            return False, "tty not allowed"
        nc, err = self._lower_keys(cfg.get("networkingconfig"), "networkingconfig")
        if err or nc is None:
            return False, err or "bad networkingconfig"
        if nc:
            ep = nc.get("endpointsconfig")
            if not self._falsy(ep) and (not isinstance(ep, dict) or set(map(str, ep.keys())) - {"none"}):
                return False, "networkingconfig endpoints other than 'none' not allowed"

        hc, err = self._lower_keys(cfg.get("hostconfig"), "hostconfig")
        if err or not hc:
            return False, err or "hostconfig is required"
        for k, v in hc.items():
            if k in ("maskedpaths", "readonlypaths"):
                # The Docker CLI sends the default masked/read-only /proc,/sys paths. An EMPTY list
                # (`--security-opt systempaths=unconfined`) would remove that protection -> reject.
                if v is not None and not (isinstance(v, list) and v and all(isinstance(p, str) and p.startswith(("/proc", "/sys")) for p in v)):
                    return False, f"hostconfig.{k} must be the non-empty default list"
            elif k in _FALSY_HOSTCONFIG:
                if not self._falsy(v):
                    return False, f"hostconfig.{k} must be empty/false"
            elif k not in _ALLOWED_HOSTCONFIG:
                return False, f"hostconfig key '{k}' not allowed"

        if hc.get("networkmode") != "none":
            return False, "networkmode must be 'none'"
        if hc.get("ipcmode") != "none":
            return False, "ipcmode must be 'none'"
        if hc.get("readonlyrootfs") is not True:
            return False, "readonlyrootfs must be true"
        capdrop = [str(c).upper() for c in (hc.get("capdrop") or [])]
        if "ALL" not in capdrop:
            return False, "capdrop must contain ALL"
        secopt = hc.get("securityopt") or []
        if not isinstance(secopt, list) or not secopt or any(str(o) not in _ALLOWED_SECURITY_OPT for o in secopt):
            return False, "securityopt must be exactly no-new-privileges"
        runtime = hc.get("runtime")
        if runtime not in self.allowed_runtimes:
            return False, f"runtime '{runtime}' not allowed (allowed: {sorted(self.allowed_runtimes)})"
        mem = hc.get("memory")
        if not isinstance(mem, int) or mem <= 0 or mem > self.max_memory:
            return False, "memory must be set and within the cap"
        swap = hc.get("memoryswap")
        if not isinstance(swap, int) or swap != mem:
            return False, "memoryswap must equal memory (no swap)"
        pids = hc.get("pidslimit")
        if not isinstance(pids, int) or pids <= 0 or pids > self.max_pids:
            return False, "pidslimit must be set and within the cap"
        nano = hc.get("nanocpus")
        if not isinstance(nano, int) or nano <= 0 or nano > self.max_nano_cpus:
            return False, "nanocpus must be set and within the cap"
        tmpfs = hc.get("tmpfs") or {}
        if not isinstance(tmpfs, dict):
            return False, "tmpfs must be an object"
        for path, opts in tmpfs.items():
            if path not in ALLOWED_TMPFS_PATHS:
                return False, f"tmpfs path '{path}' not allowed"
            parts = [p for p in str(opts).split(",") if p]
            if "nosuid" not in parts or "nodev" not in parts:
                return False, f"tmpfs {path} must be nosuid,nodev"
            sizes = [self._size_bytes(p.split("=", 1)[1]) for p in parts if p.startswith("size=")]
            if not sizes or sizes[0] is None or sizes[0] > self.max_tmpfs:
                return False, f"tmpfs {path} needs a bounded size"
        for u in hc.get("ulimits") or []:
            ul, err = self._lower_keys(u, "ulimit")
            if err or not ul or str(ul.get("name")) not in ALLOWED_ULIMITS:
                return False, "ulimit not allowed"
        lc, err = self._lower_keys(hc.get("logconfig"), "logconfig")
        if err or lc is None or (lc.get("type") not in (None, "", "json-file", "local", "none")):
            return False, "logconfig not allowed"
        rp, err = self._lower_keys(hc.get("restartpolicy"), "restartpolicy")
        if err or rp is None or (rp.get("name") not in (None, "", "no")):
            return False, "restartpolicy not allowed"
        return True, "create ok"

    # --------------------------------------------------------------- routing
    def check_request(self, method: str, target: str, body: bytes = b"") -> Decision:
        if "%" in target or ".." in target or "//" in target.split("?", 1)[0] or "\\" in target:
            return False, "path contains forbidden characters"
        parts = urlsplit(target)
        path = VERSION_PREFIX_RE.sub("", parts.path)
        query = parse_qs(parts.query, keep_blank_values=True)
        method = method.upper()

        if path == "/_ping" and method in ("GET", "HEAD"):
            return True, "ping"
        if path == "/version" and method == "GET":
            return True, "version"

        if path == "/containers/create" and method == "POST":
            return self.validate_create(query, body)

        if path == "/containers/json" and method == "GET":
            raw = (query.get("filters") or [""])[0]
            try:
                filters = json.loads(raw) if raw else {}
            except Exception:
                return False, "bad filters"
            nf = filters.get("name") if isinstance(filters, dict) else None
            keys = list(nf.keys()) if isinstance(nf, dict) else (list(nf) if isinstance(nf, list) else [])
            if keys and all(str(k).startswith(NAME_FILTER_PREFIXES) for k in keys):
                return True, "list sandbox containers (name-filtered)"
            return False, "container listing requires a codeclan-sbx-/codeclan-evl- name filter"

        m = re.fullmatch(r"/containers/([^/]+)(?:/(json|start|attach|wait|kill|stop|resize))?", path)
        if m:
            name, action = m.group(1), m.group(2)
            if not self.is_allowed_container_ref(name):
                return False, "operation on non-CodeClan container denied"
            if action is None and method == "DELETE":
                return True, "remove sandbox container"
            if action == "json" and method == "GET":
                return True, "inspect sandbox container"
            if action in ("start", "attach", "wait", "kill", "stop", "resize") and method == "POST":
                return True, f"{action} sandbox container"
            return False, f"{method} /containers/<name>/{action or ''} not allowed"

        m = re.fullmatch(r"/images/([^/]+(?:/[^/]+)*)/json", path)
        if m and method == "GET":
            return (True, "inspect approved image") if self.image_allowed(m.group(1)) else (False, "image not approved")

        return False, f"{method} {path} is not permitted by CodeClan Docker policy"
