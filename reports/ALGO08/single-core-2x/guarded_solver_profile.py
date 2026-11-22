"""Profile an already verified saved solve using its frozen solver bindings."""

import argparse
import cProfile
import json
import runpy
from contextlib import ExitStack, nullcontext
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch


def worker(native, spec, archive, offer, output, profile, packed, private_width, likelihood_cache):
    from tools.pipeline_eval.variants.experimental import lean_startup

    install = lean_startup.install
    profiler = cProfile.Profile(timer=process_time_ns, timeunit=1e-9) if profile else nullcontext()
    counters = None

    with ExitStack() as stack:
        def install_then_profile():
            nonlocal counters
            install()
            from tools import algo08_position

            if packed is not None:
                source = Path(__file__).resolve().parents[3] / "tools/pipeline_eval/variants"
                module = runpy.run_path(str(source / "algo08_packed_residual.py"))
                overlay = module["packed_residual"]
                stack.enter_context(overlay(packed / "packed-bound.so", packed / "packed-grid.so"))
            if private_width is not None:
                source = Path(__file__).resolve().parents[3] / "tools/pipeline_eval/variants"
                module = runpy.run_path(str(source / "algo08_private_width.py"))
                counters = stack.enter_context(module["expand_unsupported_layout"](private_width))
            if likelihood_cache:
                source = Path(__file__).resolve().parents[3] / "tools/pipeline_eval/variants"
                module = runpy.run_path(str(source / "algo08_likelihood_reuse.py"))
                counters = stack.enter_context(module["ordinary_likelihood_reuse"]())
            solve = algo08_position.solve

            def profiled(*args, **kwargs):
                with profiler:
                    return solve(*args, **kwargs)

            stack.enter_context(patch.object(algo08_position, "solve", profiled))

        source = Path(__file__).with_name("residual_attribution_trial.py")
        stack.enter_context(patch.object(lean_startup, "install", install_then_profile))
        runpy.run_path(str(source))["worker"](native, spec, archive, offer, output,
                                             include_evidence=True)
    if profile:
        profiler.dump_stats(profile)
    if counters is not None:
        name = ".likelihood-cache.json" if likelihood_cache else ".private-width.json"
        with output.with_suffix(name).open("x") as stream:
            json.dump(counters, stream, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("native", "spec", "archive", "offer", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("profile", type=Path, nargs="?")
    variants = parser.add_mutually_exclusive_group()
    variants.add_argument("--packed", type=Path)
    variants.add_argument("--private-width", type=Path)
    variants.add_argument("--likelihood-cache", action="store_true")
    worker(**vars(parser.parse_args()))
