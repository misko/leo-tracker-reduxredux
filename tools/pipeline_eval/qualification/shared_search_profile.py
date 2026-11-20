"""Profile the stock initial search and conservative recovery on stored detections."""

import argparse
import cProfile
import pstats
import sys
from pathlib import Path
from unittest.mock import patch

from tools.pipeline_eval.__main__ import (
    DEFAULT_OUT,
    local_output,
    public_cases,
    references,
    save_json,
)
from tools.pipeline_eval.variants import compact_finish, orbit_projector, v5_core, v5_lean


def measured(name, function, output):
    def invoke(*args, **kwargs):
        with cProfile.Profile() as profile:
            result = function(*args, **kwargs)
        table = pstats.Stats(profile)
        rows = [
            dict(file=path, line=line, function=f, calls=nc, self_s=tt, total_s=ct)
            for (path, line, f), (_, nc, tt, ct, _) in table.stats.items()
        ]
        save_json(
            output / f"{name}.json",
            dict(
                profiled_elapsed_s=table.total_tt,
                self_time=sorted(rows, key=lambda row: -row["self_s"])[:80],
                total_time=sorted(rows, key=lambda row: -row["total_s"])[:80],
            ),
        )
        return result

    return invoke


def worker(request, result, library, output):
    from leo.analysis.localization_v3 import conservative_recovery as recovery

    output = Path(output)
    with (
        patch.object(
            v5_core, "initial_selection", measured("initial", v5_core.initial_selection, output)
        ),
        patch.object(recovery, "salvage", measured("salvage", recovery.salvage, output)),
    ):
        compact_finish.worker(request, result, library)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    output = local_output(args.out)
    output.mkdir(parents=True, exist_ok=False)
    panel, refs = references("ds26-common127", ["DS26-0036"])
    (case,) = public_cases(panel, refs, DEFAULT_OUT / "inputs")
    library = output / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    result = v5_lean.run_bound_worker(
        case, output / "worker", Path(__file__), worker_args=(str(library), str(output))
    )
    save_json(output / "profiled-result.json", result)


if __name__ == "__main__":
    if len(sys.argv) == 5:
        worker(*sys.argv[1:])
    else:
        main()
