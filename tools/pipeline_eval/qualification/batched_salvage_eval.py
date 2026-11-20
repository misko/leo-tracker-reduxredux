"""Measure compact v5 stage high-water RSS on the original stored detections."""

import argparse
import importlib
import json
import os
import sys
from contextlib import ExitStack
from functools import partial, wraps
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import perf_counter, process_time
from unittest.mock import patch

from tools.pipeline_eval.qualification.compact_finish_eval import verify_adapter
from tools.pipeline_eval.variants import (
    compact_finish,
    orbit_projector,
    v5_batched_salvage,
    v5_core,
    v5_lean,
)

STAGES = {
    "leo.application.localization_v3": (
        "prepare_native_scan",
        "prepare_additional_catalogue",
        "screen_reassociation_candidates",
        "fit_reassociation",
    ),
    "leo.analysis.localization_v3.conservative_recovery": ("conservative_recovery", "salvage"),
    "leo.analysis.localization_v3.history_policy": ("history_policy",),
    "leo.analysis.localization_v3.signed_context": ("signed_context",),
    "leo.analysis.localization_v3.family_cavity": ("nominate_families", "cavity_policy"),
    "leo.analysis.localization_v3.residual_screen": ("screen_candidates", "ecef_states"),
    "leo.analysis.localization_v3.reassociation_admission": ("prepare_catalogue", "screen"),
}


def observed(name, operation, events, **attributes):
    @wraps(operation)
    def run(*args, **kwargs):
        before = getrusage(RUSAGE_SELF).ru_maxrss
        wall, cpu = perf_counter(), process_time()
        try:
            return operation(*args, **kwargs)
        finally:
            row = dict(
                name=name,
                start_s=wall,
                wall_s=perf_counter() - wall,
                cpu_s=process_time() - cpu,
                before_peak_kib=before,
                after_peak_kib=getrusage(RUSAGE_SELF).ru_maxrss,
                **attributes,
            )
            print(json.dumps(row), file=events, flush=True)

    return run


def worker(request, result, library, log, mode):
    with Path(log).open("x") as events, ExitStack() as stack:

        def watch(module, names):
            for name in names:
                wrapper = observed(f"{module.__name__}.{name}", getattr(module, name), events)
                stack.enter_context(patch.object(module, name, wrapper))

        watch(v5_core, ("initial_selection", "scan_context", "infer"))
        for name, methods in STAGES.items():
            watch(importlib.import_module(name), methods)

        recovery = importlib.import_module("leo.analysis.localization_v3.conservative_recovery")
        profile = recovery.profile
        if mode == "batched":
            profile = partial(v5_batched_salvage.bounded_profile, profile)

        def profile_with_receipt(y, predictions, *args, **kwargs):
            if predictions.nbytes <= v5_batched_salvage.PREDICTION_BLOCK_BYTES:
                return profile(y, predictions, *args, **kwargs)
            call = observed(
                "salvage_profile",
                profile,
                events,
                prediction_shape=list(predictions.shape),
                prediction_bytes=predictions.nbytes,
            )
            return call(y, predictions, *args, **kwargs)

        stack.enter_context(patch.object(recovery, "profile", profile_with_receipt))
        compact_finish.worker(request, result, library)


def measure(output, mode):
    from tools.pipeline_eval.__main__ import (
        DEFAULT_OUT,
        ROOT,
        encoded,
        local_output,
        public_cases,
        references,
    )

    if len(os.sched_getaffinity(0)) != 1:
        raise ValueError("pin to one logical CPU for the bounded replay")
    output = local_output(output)
    output.mkdir(parents=True, exist_ok=False)
    panel, refs = references("ds26-common127", ["DS26-0036"])
    (case,) = public_cases(panel, refs, DEFAULT_OUT / "inputs")
    library = output / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    result = v5_lean.run_bound_worker(
        case,
        output / "worker",
        Path(__file__),
        worker_args=(str(library), str(output / "stages.jsonl"), mode),
    )
    baseline = ROOT / "reports/2026_11_19_receiver_streaming/finish/adapter/DS26-0036.json"
    prior = json.loads(baseline.read_bytes())
    fresh = dict(id=case["id"], input_sha256=sha256(encoded(case)).hexdigest(), result=result)
    verify_adapter(prior, fresh)
    (output / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=("control", "batched"), required=True)
    args = parser.parse_args()
    measure(args.out, args.mode)


if __name__ == "__main__":
    if len(sys.argv) == 6 and sys.argv[-1] in {"control", "batched"}:
        worker(*sys.argv[1:])
    else:
        main()
