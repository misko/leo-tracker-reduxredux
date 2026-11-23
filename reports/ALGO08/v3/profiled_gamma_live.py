"""Bind the reviewed Gamma kernel to the saved fit, retaining the installed grid."""

from collections import Counter
from contextlib import contextmanager
from ctypes import CDLL
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
from unittest.mock import patch


OVERLAY = Path(__file__).resolve().parents[3] / "tools/pipeline_eval/variants/algo08_profiled_gamma.py"
PINNED = dict(pinned_source_sha256="40888d6143f385c2146e5e2cb28ea99a96b2f1bb791fab4c22b5afaaa2b3a23b",
              header_sha256="4abd194a879cdbc47d76f79d10e6547eb65e1b7943d71a185354f33fd20a966a",
              generated_sha256="6ea04d92bad3988b8399dc25a0e4c80eec1ba2fc495836b7b5caadb5b381b82e",
              binary_sha256="24c47f901a9fd18294d662caf70f0f61218b2b5aac8264e0fce636315cde164b")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def checked_library(path):
    manifest_path = path.with_suffix(".json")
    manifest = json.loads(manifest_path.read_bytes())
    if (any(manifest.get(key) != value for key, value in PINNED.items())
            or digest(path) != PINNED["binary_sha256"]
            or digest(OVERLAY.with_suffix(".h")) != PINNED["header_sha256"]):
        raise ValueError("Expected the reviewed profiled Gamma fit binary and build manifest")
    binary = CDLL(str(path))
    if not hasattr(binary, "nb_profiled_gamma") or hasattr(binary, "nb_run_posterior"):
        raise ValueError("Expected the ordinary Gamma ABI without a grid posterior export")
    return dict(manifest, overlay_sha256=digest(OVERLAY), manifest_sha256=digest(manifest_path),
                ordinary_abi="nb_profiled_gamma", grid_posterior="installed nb_run_posterior")


@contextmanager
def outside_grid(port, library):
    from leo.presentation import localization_v3

    provenance = checked_library(library)
    profile = run_path(str(OVERLAY))["profiled_gamma"]
    grid = localization_v3.sample_position_grid
    grid_depth = 0
    activity = Counter()

    def installed_grid(*args, **kwargs):
        nonlocal grid_depth
        grid_depth += 1
        try:
            return grid(*args, **kwargs)
        finally:
            grid_depth -= 1

    with (patch.object(localization_v3, "sample_position_grid", installed_grid),
          profile(port, library, allowed=lambda: grid_depth == 0, activity=activity) as counts):
        yield dict(provenance=provenance, activity=activity, counts=counts)
