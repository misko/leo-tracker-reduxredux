"""Emit stage boundaries from inside the existing memory-capped solver worker."""

import sys
from contextlib import ExitStack
from functools import wraps
from unittest.mock import patch

from tools.pipeline_eval.qualification import solver_memory_worker
from tools.pipeline_eval.variants import v5_core


def worker(*args):
    from leo.analysis.localization_v3 import conservative_recovery, discovery, history_policy

    from leo.application import localization_v3

    def watch(operation, name):
        @wraps(operation)
        def run(*args, **kwargs):
            print("stage: enter " + name, flush=True)
            value = operation(*args, **kwargs)
            print("stage: leave " + name, flush=True)
            return value

        return run

    with ExitStack() as stack:
        for module, names in (
            (
                localization_v3,
                (
                    "prepare_native_scan",
                    "prepare_tracks",
                    "prepare_initial_sky",
                    "prepare_phase_history",
                ),
            ),
            (v5_core, ("scan_context", "initial_selection", "ranked_initial_nodes")),
            (discovery, ("fresh_discovery", "explore")),
            (conservative_recovery, ("conservative_recovery", "salvage")),
            (history_policy, ("history_policy",)),
        ):
            for name in names:
                stack.enter_context(patch.object(module, name, watch(getattr(module, name), name)))
        solver_memory_worker.worker(*args)


if __name__ == "__main__":
    worker(*sys.argv[1:])
