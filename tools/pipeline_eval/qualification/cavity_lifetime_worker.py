"""Capture real cgroup charges while measuring compact phase-problem lifetimes."""

import json
import sys
from contextlib import ExitStack
from functools import wraps
from threading import Event, Thread
from time import monotonic
from unittest.mock import patch

from tools.pipeline_eval.qualification.bounded_cavity_worker import binding
from tools.pipeline_eval.variants import v5_cavity_lifetime, v5_core


def worker(unit, cpu, request, result, library, mode):
    from leo.analysis.localization_v3 import conservative_recovery, family_cavity, history_policy

    from leo.application import localization_v3

    group = binding(unit, int(cpu))
    start = monotonic()
    stop = Event()

    def counters(name):
        return {k: int(v) for k, v in map(str.split, (group / name).read_text().splitlines())}

    def sample(stage, event, **fields):
        stats = counters("memory.stat")
        value = dict(
            stage=stage,
            event=event,
            unit=unit,
            cpu=int(cpu),
            wall_s=monotonic() - start,
            memory_bytes=int((group / "memory.current").read_text()),
            peak_bytes=int((group / "memory.peak").read_text()),
            swap_bytes=int((group / "memory.swap.current").read_text()),
            anon_bytes=stats["anon"],
            file_bytes=stats["file"],
            kernel_bytes=stats["kernel"],
            cpu_s=counters("cpu.stat")["usage_usec"] * 1e-6,
            events=counters("memory.events"),
            **fields,
        )
        print("sample " + json.dumps(value, allow_nan=False), flush=True)

    def poll():
        while not stop.wait(1.0):
            sample("periodic", "tick")

    def observed(function, name):
        @wraps(function)
        def run(*args, **kwargs):
            sample(name, "enter")
            value = function(*args, **kwargs)
            sample(name, "return")
            return value

        return run

    sample("worker", "enter")
    sampler = Thread(target=poll, daemon=True)
    sampler.start()
    try:
        with ExitStack() as hooks:
            for owner, name in (
                (localization_v3, "prepare_native_scan"),
                (v5_core, "initial_selection"),
                (conservative_recovery, "conservative_recovery"),
                (history_policy, "history_policy"),
            ):
                hooks.enter_context(patch.object(owner, name, observed(getattr(owner, name), name)))
            # The bounded variant installs its own nomination geometry function.
            # The candidacy wrappers leave that original stage composition in place.
            hooks.enter_context(
                patch.object(
                    family_cavity, "family_data", observed(family_cavity.family_data, "family_data")
                )
            )
            v5_cavity_lifetime.worker(request, result, library, sample, direct=mode == "direct")
    finally:
        stop.set()
        sampler.join()
    sample("worker", "return")


if __name__ == "__main__":
    worker(*sys.argv[1:])
