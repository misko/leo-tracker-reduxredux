"""Use two orbital phase linearizations in the early compact-v5 position fits."""

import json
import sys
from collections import Counter
from contextlib import ExitStack, contextmanager
from functools import wraps
from pathlib import Path
from unittest.mock import patch

from tools.pipeline_eval.variants import orbit_projector, v5_lean

ROUNDS = 2
BOUNDARY = "Complete native GLRT through compact v5 with two early orbit phase fits"


def limit_rounds(original, name, counts):
    @wraps(original)
    def limited(*args, **kwargs):
        requested = kwargs.get("rounds", 5)
        if isinstance(requested, bool) or not isinstance(requested, int) or requested < 1:
            raise ValueError("a positive integer phase-fit budget is required")
        used = min(requested, ROUNDS)
        result = original(*args, **dict(kwargs, rounds=used))
        counts[name + "_calls"] += 1
        counts[name + "_rounds"] += used
        return result

    return limited


@contextmanager
def early_phase_policy():
    from leo.analysis.localization_v3 import conservative_recovery, history_policy, position

    counts = Counter()
    targets = (
        (position, "refreshed", "initial"),
        (conservative_recovery, "fit_position", "conservative"),
        (conservative_recovery, "repaired_fit", "salvage"),
        (history_policy, "refit", "curved_family"),
        (history_policy, "linear_refit", "linear_family"),
    )
    with ExitStack() as patches:
        for module, attribute, name in targets:
            limited = limit_rounds(getattr(module, attribute), name, counts)
            patches.enter_context(patch.object(module, attribute, limited))
        yield counts


def worker(request, output, library):
    from tools.pipeline_eval.__main__ import save_json

    with early_phase_policy() as counts:
        orbit_projector.worker(request, output, library)
    out = json.loads(Path(output).read_bytes())
    out["boundary"] = BOUNDARY
    out["metrics"].update(outer_phase_limit=ROUNDS, phase_fit_counts=dict(counts))
    save_json(Path(output), out)


def run(case, work_dir):
    library = Path(work_dir) / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, work_dir, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
