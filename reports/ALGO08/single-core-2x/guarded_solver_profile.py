"""Profile an already verified saved solve using its frozen solver bindings."""

import argparse
import cProfile
import runpy
from contextlib import ExitStack, nullcontext
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch


def worker(native, spec, archive, offer, output, profile, packed):
    from tools.pipeline_eval.variants.experimental import lean_startup

    install = lean_startup.install
    profiler = cProfile.Profile(timer=process_time_ns, timeunit=1e-9) if profile else nullcontext()

    with ExitStack() as stack:
        def install_then_profile():
            install()
            from tools import algo08_position

            if packed is not None:
                source = Path(__file__).resolve().parents[3] / "tools/pipeline_eval/variants"
                module = runpy.run_path(str(source / "algo08_packed_residual.py"))
                overlay = module["packed_residual"]
                stack.enter_context(overlay(packed / "packed-bound.so", packed / "packed-grid.so"))
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("native", "spec", "archive", "offer", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("profile", type=Path, nargs="?")
    parser.add_argument("--packed", type=Path)
    worker(**vars(parser.parse_args()))
