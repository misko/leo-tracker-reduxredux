"""Compose the qualified secant position optimizer and two-refresh phase budget."""

import json
import sys
from hashlib import sha256
from pathlib import Path

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.variants import orbit_projector, v5_lean, v5_secant_fit, v5_two_refresh

BOUNDARY = "Complete stored native GLRT to compact v5 cavity with secant and two phase refreshes"
DEPENDENCIES = {
    "v5_secant_fit.py": "17a5fbaf1d535115d69572fadacf5fa9427663d2622f33000ecf994303b1ddee",
    "v5_two_refresh.py": "21ab3e51b09efcaf039f0735a8e8de06d6264c6f1daa7bc96532f9b7ae3e9d57",
}


def verified_sources():
    actual = {
        path.name: sha256(path.read_bytes()).hexdigest()
        for path in (Path(v5_secant_fit.__file__), Path(v5_two_refresh.__file__))
    }
    if actual != DEPENDENCIES:
        raise ValueError("combined fit dependency differs from its locked scientific source")
    return actual


def worker(request, result, library):
    sources = verified_sources()
    # The secant worker wraps the already-limited refresh so both changes apply.
    with v5_two_refresh.early_phase_policy() as counts:
        v5_secant_fit.worker(request, result, library, "secant")
    value = json.loads(Path(result).read_bytes())
    value["boundary"] = BOUNDARY
    value["metrics"].update(
        phase_fit_counts=dict(counts),
        outer_phase_limit=v5_two_refresh.ROUNDS,
        combined_source_sha256=sources,
    )
    save_json(Path(result), value)


def run(case, work_dir):
    verified_sources()
    work_dir = local_output(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    library = work_dir / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, work_dir, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
