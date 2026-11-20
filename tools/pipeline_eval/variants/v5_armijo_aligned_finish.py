"""Finish the Armijo v5 fit with verified catalogue-indexed phase initializers."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

from tools.pipeline_eval.variants import orbit_projector, v5_armijo_finish, v5_lean

BOUNDARY = (
    "Capture-era native detections to both Armijo v5 final positions with ordered phase seeds"
)


def run(case, work_dir):
    from tools.pipeline_eval.__main__ import local_output

    directory = local_output(work_dir)
    directory.mkdir(parents=True, exist_ok=True)
    library = directory / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    result = v5_lean.run_bound_worker(case, directory, Path(__file__), worker_args=(str(library),))
    result["boundary"] = BOUNDARY
    return result


def worker(request, target, library):
    from leo.analysis.localization_v3 import reassociation_context, reassociation_recovery

    from tools.pipeline_eval.__main__ import save_json
    from tools.pipeline_eval.qualification.armijo_finish_phase_retry import prepare_remap

    addition = reassociation_context.add_target
    remap = reassociation_recovery.remap
    prefix, added_norad = None, None
    aligned, equal_length = [], 0

    def add_target(context, *args, **kwargs):
        nonlocal prefix, added_norad
        original = tuple(map(int, context["scan"].norads))
        entry = addition(context, *args, **kwargs)
        current = tuple(map(int, context["scan"].norads))
        if current != original:
            number = int(entry["norad"])
            if current != (*original, number) or entry["candidate_index"] != len(original):
                raise ValueError("residual addition changed the ordered sky identities")
            prefix, added_norad = original, number
        return entry

    def aligned_remap(context, hypothesis, ledger):
        nonlocal equal_length
        adapted, receipt = prepare_remap(context, prefix, added_norad)
        if receipt is None:
            equal_length += 1
        else:
            aligned.append(
                dict(
                    hypothesis=hypothesis["name"],
                    added_norad=receipt["added_norad"],
                    catalogue_index=receipt["added_catalogue_index"],
                    initializer_seconds=receipt["added_phase_initial_seconds"],
                )
            )
        return remap(adapted, hypothesis, ledger)

    with (
        patch.object(reassociation_context, "add_target", add_target),
        patch.object(reassociation_recovery, "remap", aligned_remap),
    ):
        v5_armijo_finish.worker(request, target, library)
    result = json.loads(Path(target).read_bytes())
    result["boundary"] = BOUNDARY
    result["metrics"]["ordered_phase_seeds"] = dict(aligned=aligned, equal_length=equal_length)
    save_json(Path(target), result)


if __name__ == "__main__":
    worker(*sys.argv[1:])
