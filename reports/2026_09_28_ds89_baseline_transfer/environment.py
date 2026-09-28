"""Record installed public reader and numerical sources before export."""

import hashlib
import importlib
import inspect
import json
import platform
import sys
from pathlib import Path

names = [
    "leo.storage.scanner_tracking_source",
    "leo.operations.adaptive_tle_position_inputs",
    "leo.operations.tle_archive",
    "leo.application.scanner_trajectory",
    "leo.analysis.persistent_hop_trajectory",
    "leo.analysis.adaptive_tle_prediction",
    "leo.analysis.catalogue_eligibility",
    "leo.sky.propagation",
    "leo.sky.frames",
]
modules = {}
for name in names:
    module = importlib.import_module(name)
    path = Path(inspect.getfile(module)).resolve()
    modules[name] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
import numpy  # noqa: E402
import scipy  # noqa: E402

print(
    json.dumps(
        {
            "python": platform.python_version(),
            "executable": sys.executable,
            "executable_sha256": hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
            "numpy": numpy.__version__,
            "scipy": scipy.__version__,
            "modules": modules,
        },
        indent=2,
    )
)
