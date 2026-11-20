"""Measure the compact worker boundaries without changing either position objective."""

import json
import sys
from contextlib import ExitStack
from functools import wraps
from pathlib import Path
from resource import RUSAGE_CHILDREN, RUSAGE_SELF, getrusage
from time import perf_counter, process_time
from unittest.mock import patch

from tools.pipeline_eval.variants import v5_core, v5_secant_fit


def cpu_s():
    children = getrusage(RUSAGE_CHILDREN)
    return process_time() + children.ru_utime + children.ru_stime


def stamp(wall, cpu):
    return dict(
        wall_s=perf_counter() - wall,
        cpu_s=cpu_s() - cpu,
        self_peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
        child_peak_rss_kib=getrusage(RUSAGE_CHILDREN).ru_maxrss,
    )


def measured(operation, name, stages):
    @wraps(operation)
    def run(*args, **kwargs):
        wall, cpu = perf_counter(), cpu_s()
        result = operation(*args, **kwargs)
        measurement = stamp(wall, cpu)
        previous = stages.get(name)
        if previous is not None:
            for key in ("wall_s", "cpu_s"):
                measurement[key] += previous[key]
        measurement["calls"] = 1 if previous is None else previous["calls"] + 1
        stages[name] = measurement
        return result

    return run


def worker(request, result, library, mode):
    from leo.analysis.localization_v3 import (
        conservative_recovery,
        family_cavity,
        history_policy,
        signed_context,
    )

    from leo.application import localization_v3
    from leo.operations import localization_v3_job

    native = json.loads(Path(request).read_bytes())["job"]["native_input"]
    read = localization_v3_job.read_bound
    stages = {}
    read_native = measured(read, "native_factor_decode", stages)

    def bound(record):
        return (read_native if record == native else read)(record)

    wall, cpu = perf_counter(), cpu_s()
    with ExitStack() as patches:
        patches.enter_context(patch.object(localization_v3_job, "read_bound", bound))
        for module, member, stage in (
            (localization_v3, "prepare_tracks", "graph_tracks"),
            (localization_v3, "prepare_native_scan", "native_plus_sky_history"),
            (v5_core, "infer", "compact_cavity_numerics"),
            (v5_core, "initial_selection", "initial_position"),
            (conservative_recovery, "conservative_recovery", "conservative_recovery"),
            (history_policy, "history_policy", "family_history"),
            (signed_context, "signed_context", "signed_context"),
            (family_cavity, "nominate_families", "cavity_nomination"),
            (family_cavity, "cavity_policy", "cavity_fit"),
        ):
            patches.enter_context(
                patch.object(module, member, measured(getattr(module, member), stage, stages))
            )
        v5_secant_fit.worker(request, result, library, mode)
    total = stamp(wall, cpu)
    data = json.loads(Path(result).read_bytes())
    if (
        data["status"] == "ok"
        and not {
            "native_factor_decode",
            "graph_tracks",
            "native_plus_sky_history",
            "compact_cavity_numerics",
        }
        <= stages.keys()
    ):
        raise ValueError("successful solver omitted measured stage boundaries")
    data["metrics"].update(compact_worker=total, measured_stages=stages)
    Path(result).write_text(json.dumps(data, allow_nan=False, sort_keys=True) + "\n")


if __name__ == "__main__":
    worker(*sys.argv[1:])
