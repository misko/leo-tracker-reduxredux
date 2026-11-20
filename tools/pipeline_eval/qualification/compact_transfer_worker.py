"""Apply the established secant optimizer inside the arbitrary-tile portable worker."""

import json
import runpy
import sys
from importlib import import_module
from time import perf_counter
from unittest.mock import patch

from leo.analysis.localization_v3 import position

from tools.pipeline_eval.variants import v5_core
from tools.pipeline_eval.variants.v5_secant_fit import bounded_secant


def traced(operation):
    def call(*args, **kwargs):
        print(
            json.dumps({"stage": operation.__name__, "start_s": perf_counter()}),
            file=sys.stderr,
            flush=True,
        )
        return operation(*args, **kwargs)

    return call


if __name__ == "__main__":
    module = import_module("leo.analysis.localization_v3.conservative_recovery")
    initial = traced(v5_core.initial_selection)
    recovery = traced(module.conservative_recovery)
    with (
        patch.object(position, "bounded_gauss_newton", bounded_secant),
        patch.object(v5_core, "initial_selection", initial),
        patch.object(module, "conservative_recovery", recovery),
    ):
        runpy.run_path("/worker/main.py", run_name="__main__")
