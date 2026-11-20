"""Keep one association result live for the repeated initial exploration probe."""

import json
import sys
from collections import Counter
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from unittest.mock import patch

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.variants import orbit_projector, v5_lean, v5_secant_fit

METHOD = "v5_discovery_memory"
BOUNDARY = "Native GLRT through compact secant v5 with one association result per discovery probe"
REUSABLE = {"receiver_smooth", "shared_phase"}


@contextmanager
def reuse_discovery_association():
    from leo.analysis.localization_v3 import discovery

    explore = discovery.explore
    counts = Counter()

    @wraps(explore)
    def single_probe(scan, state, anchor, method, *args, **kwargs):
        if method not in REUSABLE:
            return explore(scan, state, anchor, method, *args, **kwargs)
        association = scan.association
        previous = None
        counts["explorations"] += 1

        def associate(state, base, point, method, *, all_tracks=False):
            nonlocal previous
            if previous is not None:
                s, b, p, m, scope, result = previous
                previous = None
                if s is state and b is base and p is point and m == method and scope == all_tracks:
                    counts["reused_associations"] += 1
                    return result
                del result
            result = association(state, base, point, method, all_tracks=all_tracks)
            previous = state, base, point, method, all_tracks, result
            counts["computed_associations"] += 1
            return result

        with patch.object(scan, "association", associate):
            return explore(scan, state, anchor, method, *args, **kwargs)

    with patch.object(discovery, "explore", single_probe):
        yield counts


def worker(request, result, library):
    with reuse_discovery_association() as counts:
        v5_secant_fit.worker(request, result, library, "secant")
    path = Path(result)
    receipt = json.loads(path.read_bytes())
    receipt["boundary"] = BOUNDARY
    receipt["metrics"]["association_reuse"] = dict(counts)
    save_json(path, receipt)


def run(case, work_dir):
    work_dir = local_output(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    library = work_dir / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, work_dir, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
