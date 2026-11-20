"""Measure the bounded initial fit before compact conservative recovery."""

import json
import runpy
import signal
import sys
from importlib import import_module
from time import perf_counter, process_time
from unittest.mock import patch

from leo.analysis.localization_v3 import acceptance, position

from tools.pipeline_eval.variants import v5_core
from tools.pipeline_eval.variants.transfer_budget import RECOVERY_LIMIT_S, admits_recovery
from tools.pipeline_eval.variants.v5_secant_fit import bounded_secant


class StopRecovery(Exception):
    pass


def receipt(problem, fit, xy, stats):
    radius = float(problem.scan.search_region.half_width_km)
    xy = list(map(float, xy))
    axes = [i for i, offset in enumerate(xy) if abs(offset) >= radius - 0.02]
    outward = []
    loss = float(fit["fits"][0]["score"])
    for axis in axes:
        shifted = xy.copy()
        shifted[axis] += 0.1 if xy[axis] > 0 else -0.1
        r = problem.residual(shifted)
        outward.append(loss - float(r @ r))
    return dict(
        xy_km=xy,
        edge_axes=axes,
        outward_score_gain=outward,
        initial_loss=loss,
        accepted_points=stats["accepted_points"],
        accepted_tracks=int(stats["accepted_tracks"]),
        tracked_points=sum(row["points"] for row in stats["tracks"]),
        tracked_tracks=len(stats["tracks"]),
        accepted_rf_rms_hz=stats["accepted_native_rms_hz"],
        rejected_tracks=sum(not row["compatible"] for row in stats["tracks"]),
    )


def main(mode):
    original_initial, original_infer = v5_core.initial_selection, v5_core.infer
    original_metrics = acceptance.actual_metrics
    recovery_module = import_module("leo.analysis.localization_v3.conservative_recovery")
    original_recovery = recovery_module.conservative_recovery
    evidence = {}

    def initial(scan):
        def evaluated(problem, fit, arm, xy):
            stats = original_metrics(problem, fit, arm, xy)
            evidence.update(receipt(problem, fit, xy, stats))
            return stats

        start, cpu = perf_counter(), process_time()
        with patch.object(acceptance, "actual_metrics", evaluated):
            choice = original_initial(scan)
        evidence.update(initial_wall_s=perf_counter() - start, initial_cpu_s=process_time() - cpu)
        print(json.dumps(dict(stage="initial_evidence", **evidence)), file=sys.stderr, flush=True)
        if mode == "diagnostic":
            raise StopRecovery("diagnostic_only_before_conservative_recovery")
        if mode == "gate" and not admits_recovery(evidence):
            raise StopRecovery("initial_compatible_support_not_majority")
        return choice

    def alarm(*_):
        raise StopRecovery("conservative_recovery_work_budget_exhausted")

    def recover(*args, **kwargs):
        print(
            json.dumps(dict(stage="conservative_recovery", start_s=perf_counter())),
            file=sys.stderr,
            flush=True,
        )
        if mode != "gate":
            return original_recovery(*args, **kwargs)
        previous = signal.signal(signal.SIGALRM, alarm)
        signal.setitimer(signal.ITIMER_REAL, RECOVERY_LIMIT_S)
        start = perf_counter()
        try:
            return original_recovery(*args, **kwargs)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
            evidence["recovery_wall_s"] = perf_counter() - start

    def infer(prepared, region, bound, stages):
        try:
            result = original_infer(prepared, region, bound, stages)
        except StopRecovery as exc:
            result = dict(
                status="withheld",
                reason=str(exc),
                metrics={"stage_s": stages},
                arms={arm: {"latlon": None} for arm in ("c0", "fitted_c")},
            )
        result["metrics"]["initial_evidence"] = evidence
        return result

    with (
        patch.object(position, "bounded_gauss_newton", bounded_secant),
        patch.object(v5_core, "initial_selection", initial),
        patch.object(v5_core, "infer", infer),
        patch.object(recovery_module, "conservative_recovery", recover),
    ):
        runpy.run_path("/worker/main.py", run_name="__main__")


if __name__ == "__main__":
    main(sys.argv[2])
