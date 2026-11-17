"""
Execution environment registry.

Teachers pick an environment_id; the grader resolves it to an APPROVED, pre-built image and a resource
profile. Students (and teachers) can never supply a Docker image name or Docker flags. The Docker policy
proxy independently enforces the image allowlist (`codeclan-sandbox:latest`, `codeclan-env-*`).

Images are built ahead of time (scripts/build-envs.ps1 | build-envs.sh). Nothing is installed at
execution time. `expected_libraries` documents what each Dockerfile installs; the *actual* installed
versions are read from each image's /opt/codeclan-manifest.json at verification time
(see tests/test_execution_environments.py).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

# Hard ceilings no override can exceed (also enforced by the Docker policy proxy).
GLOBAL_MAX = {
    "memory_mb": 4096,
    "cpus": 4.0,
    "pids": 512,
    "wall_timeout_sec": 300.0,
    "fsize_mb": 256,
    "max_output_bytes": 4 * 1024 * 1024,
    "tmpfs_work_mb": 1024,
    "max_dataset_mb": 256,
    "max_source_bytes": 5 * 1024 * 1024,
}

# Keys a teacher may override (always clamped to the environment's own maximum).
OVERRIDABLE = (
    "memory_mb", "cpus", "wall_timeout_sec", "max_output_bytes", "pids", "fsize_mb",
    "tmpfs_work_mb", "max_source_bytes", "max_dataset_mb",
)


@dataclass(frozen=True)
class Environment:
    id: str
    display_name: str
    image: str
    version: str
    description: str
    languages: List[str]
    expected_libraries: List[str]
    default_profile: Dict[str, float]
    max_profile: Dict[str, float]
    supports_datasets: bool = True
    supports_multifile: bool = True
    category: str = "general"
    notes: str = ""
    compatibility: Dict[str, str] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.display_name

    @property
    def libraries(self) -> List[str]:
        return self.expected_libraries

    @property
    def env_vars(self) -> Dict[str, str]:
        return {
            "OMP_NUM_THREADS": str(int(self.default_profile.get("threads", 1))),
            "OPENBLAS_NUM_THREADS": str(int(self.default_profile.get("threads", 1))),
            "MKL_NUM_THREADS": str(int(self.default_profile.get("threads", 1))),
            "MPLBACKEND": "Agg",
            "MPLCONFIGDIR": "/tmp",
            "NLTK_DATA": "/opt/nltk_data",
            "TF_CPP_MIN_LOG_LEVEL": "2",
        }

    def public_dict(self) -> dict:
        d = asdict(self)
        d.pop("image", None)  # image names are internal
        d["name"] = self.display_name
        d["libraries"] = list(self.expected_libraries)
        return d

    def to_public_dict(self) -> dict:
        return self.public_dict()


def _p(**kw) -> Dict[str, float]:
    base = {
        "memory_mb": 256, "cpus": 0.5, "pids": 64, "nofile": 64, "fsize_mb": 16, "tmpfs_work_mb": 32,
        "tmpfs_tmp_mb": 16, "wall_timeout_sec": 3.0, "compile_timeout_sec": 10.0, "max_output_bytes": 65536,
        "threads": 1, "limit_address_space": 1, "max_output_files": 0, "max_output_files_bytes": 0,
        "max_dataset_mb": 0, "max_source_bytes": 262144,
    }
    base.update(kw)
    return base


_CP = Environment(
    id="cp", display_name="Competitive Programming", image="codeclan-sandbox:latest", version="2.0",
    description="Python 3.11, GCC/G++ (C11/C++17), OpenJDK, Node.js. Small, fast start-up.",
    languages=["python", "c", "cpp", "java", "javascript"],
    expected_libraries=["python3.11 (stdlib)", "gcc", "g++", "openjdk-headless", "nodejs"],
    default_profile=_p(),
    max_profile=_p(memory_mb=1024, cpus=2.0, pids=128, wall_timeout_sec=30.0, fsize_mb=64, max_output_bytes=1048576,
                    tmpfs_work_mb=128, max_output_files=5, max_output_files_bytes=1048576, max_dataset_mb=32,
                    max_source_bytes=1048576, nofile=256),
    category="competitive",
    compatibility={"python": "3.11"},
)


def _py_env(env_id, name, desc, libs, default_mem, max_mem, wall, max_wall, cpus=1.0, category="python", notes="", threads=1,
            version="1.0") -> Environment:
    return Environment(
        id=env_id, display_name=name, image=f"codeclan-env-{env_id}:{version}", version=version, description=desc,
        languages=["python"], expected_libraries=libs,
        default_profile=_p(memory_mb=default_mem, cpus=cpus, pids=128, nofile=256, fsize_mb=64, tmpfs_work_mb=256,
                           tmpfs_tmp_mb=64, wall_timeout_sec=wall, compile_timeout_sec=20.0, max_output_bytes=262144,
                           threads=threads, limit_address_space=0, max_output_files=20,
                           max_output_files_bytes=4 * 1024 * 1024, max_dataset_mb=64, max_source_bytes=1048576),
        max_profile=_p(memory_mb=max_mem, cpus=4.0, pids=256, nofile=512, fsize_mb=256, tmpfs_work_mb=1024,
                       tmpfs_tmp_mb=128, wall_timeout_sec=max_wall, compile_timeout_sec=30.0,
                       max_output_bytes=1048576, threads=4, limit_address_space=0, max_output_files=50,
                       max_output_files_bytes=16 * 1024 * 1024, max_dataset_mb=256, max_source_bytes=2097152),
        category=category, notes=notes, compatibility={"python": "3.11"},
    )


_REGISTRY_LIST = [
    _CP,
    _py_env("datascience", "Python Data Science",
            "NumPy, Pandas, SciPy, Matplotlib, Seaborn for data processing, statistics and visualization.",
            ["numpy", "pandas", "scipy", "matplotlib", "seaborn"], 1024, 3072, 30.0, 120.0, category="data-science"),
    _py_env("ml", "Python Machine Learning",
            "Scikit-learn on top of the data-science stack: classification, regression, clustering, evaluation.",
            ["numpy", "pandas", "scipy", "scikit-learn", "matplotlib", "seaborn"], 2048, 4096, 60.0, 180.0, cpus=2.0,
            category="machine-learning", threads=2),
    _py_env("cv", "Computer Vision",
            "OpenCV (headless), Pillow, scikit-image for image processing and classical vision.",
            ["numpy", "opencv-python-headless", "pillow", "scikit-image"], 2048, 4096, 60.0, 180.0,
            category="computer-vision", notes="opencv-python-headless: no GUI (imshow) support."),
    _py_env("nlp", "Natural Language Processing",
            "NLTK, spaCy (en_core_web_sm), scikit-learn, Pandas for text preprocessing and classification.",
            ["numpy", "pandas", "nltk", "spacy", "en_core_web_sm", "scikit-learn"], 2048, 4096, 60.0, 180.0,
            category="nlp", notes="Only NLTK data bundled at build time (punkt, stopwords, wordnet) is available offline."),
    _py_env("dl-torch", "Deep Learning (PyTorch, CPU)",
            "PyTorch CPU build with NumPy. CPU only - no GPU.", ["torch (cpu)", "numpy"], 3072, 4096, 120.0, 300.0,
            cpus=2.0, category="deep-learning", threads=2, notes="CPU only. No GPU runtime is configured or tested."),
    _py_env("dl-tf", "Deep Learning (TensorFlow, CPU)",
            "TensorFlow CPU build (Keras) with NumPy. CPU only - no GPU.", ["tensorflow-cpu", "numpy"], 3072, 4096,
            120.0, 300.0, cpus=2.0, category="deep-learning", threads=2,
            notes="CPU only. No GPU runtime is configured or tested."),
    _py_env("scientific", "Scientific Computing",
            "NumPy, SciPy, SymPy, mpmath, NetworkX for numerical algorithms, optimization and modelling.",
            ["numpy", "scipy", "sympy", "mpmath", "networkx"], 1024, 3072, 30.0, 120.0, category="scientific"),
]

REGISTRY: Dict[str, Environment] = {e.id: e for e in _REGISTRY_LIST}
ENVIRONMENTS = REGISTRY
DEFAULT_ENVIRONMENT_ID = "cp"


def get_environment(env_id: Optional[str]) -> Environment:
    """Resolve an environment id to an approved Environment. Unknown ids raise ValueError."""
    key = (env_id or DEFAULT_ENVIRONMENT_ID).strip().lower()
    if key not in REGISTRY:
        raise ValueError(f"Unknown execution environment '{env_id}'")
    return REGISTRY[key]


def list_environments() -> List[dict]:
    return [e.public_dict() for e in REGISTRY.values()]


def is_valid_environment(env_id: str) -> bool:
    return (env_id or "").strip().lower() in REGISTRY


def parse_overrides(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def effective_profile(env: Environment, overrides: Optional[dict] = None) -> Dict[str, float]:
    """Merge teacher overrides into the environment default, clamped to env.max_profile and GLOBAL_MAX."""
    prof = dict(env.default_profile)
    for k, v in (overrides or {}).items():
        if k not in OVERRIDABLE:
            continue
        try:
            val = float(v)
        except (TypeError, ValueError):
            continue
        if val <= 0:
            continue
        ceiling = min(float(env.max_profile.get(k, val)), float(GLOBAL_MAX.get(k, val)))
        prof[k] = min(val, ceiling)
    # tmpfs for /work must hold datasets + outputs
    prof["tmpfs_work_mb"] = max(prof["tmpfs_work_mb"], min(prof["tmpfs_work_mb"] + prof.get("max_dataset_mb", 0), GLOBAL_MAX["tmpfs_work_mb"]))
    prof["pids_limit"] = int(prof.get("pids", 128))
    prof["nofile_limit"] = int(prof.get("nofile", 256))
    return prof
