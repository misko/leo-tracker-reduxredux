"""Record kernel-enforced resources at the numerical stage boundaries of a capped job."""

import json
import os
import sys
from contextlib import ExitStack
from functools import wraps
from pathlib import Path
from time import monotonic
from unittest.mock import patch

from tools.pipeline_eval.variants import v5_bounded_cavity, v5_core


def binding(unit, cpu):
    entry = next(
        line[3:]
        for line in Path("/proc/self/cgroup").read_text().splitlines()
        if line.startswith("0::")
    )
    path = Path("/sys/fs/cgroup") / entry.lstrip("/")
    if (
        path.name != unit + ".service"
        or int((path / "memory.max").read_text()) != 512 * 1024**2
        or int((path / "memory.swap.max").read_text()) != 0
        or os.sched_getaffinity(0) != {cpu}
        or os.nice(0) < 10
    ):
        raise ValueError("worker did not acquire the requested cgroup or core")
    return path


def worker(unit, cpu, request, result, library):
    group = binding(unit, int(cpu))
    start = monotonic()

    def sample(name, event):
        def counters(file):
            return {k: int(v) for k, v in map(str.split, (group / file).read_text().splitlines())}

        row = dict(
            stage=name,
            event=event,
            wall_s=monotonic() - start,
            memory_bytes=int((group / "memory.current").read_text()),
            peak_bytes=int((group / "memory.peak").read_text()),
            swap_bytes=int((group / "memory.swap.current").read_text()),
            events=counters("memory.events"),
            cpu_s=counters("cpu.stat")["usage_usec"] * 1e-6,
            unit=unit,
            cpu=int(cpu),
        )
        print("sample " + json.dumps(row, allow_nan=False), flush=True)

    def observed(operation, name):
        @wraps(operation)
        def run(*args, **kwargs):
            sample(name, "enter")
            value = operation(*args, **kwargs)
            sample(name, "return")
            return value

        return run

    sample("worker", "enter")
    from leo.analysis.localization_v3 import (
        conservative_recovery,
        family_cavity,
        history_policy,
        signed_context,
    )

    from leo.application import localization_v3

    with ExitStack() as hooks:
        for owner, name in (
            (localization_v3, "prepare_native_scan"),
            (v5_core, "initial_selection"),
            (conservative_recovery, "conservative_recovery"),
            (history_policy, "history_policy"),
            (signed_context, "signed_context"),
            (family_cavity, "cavity_policy"),
        ):
            hooks.enter_context(patch.object(owner, name, observed(getattr(owner, name), name)))
        v5_bounded_cavity.worker(request, result, library)
    sample("worker", "return")


if __name__ == "__main__":
    worker(*sys.argv[1:])
