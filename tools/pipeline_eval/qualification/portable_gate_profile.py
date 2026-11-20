"""Stage timing around the original portable receiver, including partial runs."""

import json
import runpy
import sys
from functools import wraps
from time import perf_counter, process_time

from leo.analysis.localization_v3 import discovery, family_cavity, history_policy, signed_context
from leo.analysis.localization_v3.conservative_recovery import conservative_recovery

from leo.application import localization_v3 as policy
from tools.pipeline_eval.variants import v5_core


def timed(original, name):
    @wraps(original)
    def call(*args, **kwargs):
        wall, cpu = perf_counter(), process_time()
        print(json.dumps(dict(stage=name, event="start", wall=wall, cpu=cpu)), file=sys.stderr)
        try:
            return original(*args, **kwargs)
        finally:
            print(
                json.dumps(dict(stage=name, event="end", wall=perf_counter(), cpu=process_time())),
                file=sys.stderr,
            )

    return call


def instrument(module, name):
    setattr(module, name, timed(getattr(module, name), name))


if __name__ == "__main__":
    for f in ("prepare_native_scan", "prepare_initial_sky", "prepare_phase_history"):
        instrument(policy, f)
    for f in ("initial_selection", "ranked_initial_nodes", "fit_initial_nodes", "scan_context"):
        instrument(v5_core, f)
    instrument(discovery, "fresh_discovery")
    instrument(history_policy, "history_policy")
    instrument(signed_context, "signed_context")
    instrument(family_cavity, "nominate_families")
    instrument(family_cavity, "fit_cavity_proposals")
    retention = sys.modules[conservative_recovery.__module__]
    for f in ("conservative_recovery", "fit_and_gate", "salvage"):
        instrument(retention, f)
    runpy.run_path("/worker/main.py", run_name="__main__")
