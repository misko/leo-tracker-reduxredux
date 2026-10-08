"""Frozen stage sequence and convergence fallbacks for the drift-50 candidate."""

import sys
from pathlib import Path

import numpy as np

REPORTS = Path(__file__).resolve().parent.parent
sys.path[:0] = [
    str(REPORTS / name)
    for name in (
        "2026_10_08_position_error_iter19",
        "2026_10_08_position_error_iter10",
        "2026_10_08_position_error_iter04",
        "2026_10_08_position_error_iter06",
        "2026_10_08_position_error_iter01",
        "2026_10_08_hard60_bounded_recovery",
    )
]
from additive_policy import select  # noqa: E402
from dynamic_rf import DynamicRFObjective  # noqa: E402
from dynamic_rf import fit as rf_fit  # noqa: E402
from experiment import reduce_bank  # noqa: E402
from inputs import json_value  # noqa: E402
from joint_clock import JointClockObjective as InitialClockObjective  # noqa: E402
from joint_clock import fit as initial_fit  # noqa: E402
from probe import error_km  # noqa: E402
from timing_fit import JointClockObjective, fit  # noqa: E402

from leo.analysis.hard60_score import Hard60Objective  # noqa: E402
from leo.application.hard60_runner import HARD60_SCORE  # noqa: E402

ARMS = ("fitted-c", "zero-c")


def arm_selected(document, arm):
    return next(a["selected"] for a in document["methods"][0]["arms"] if a["name"] == arm)


def accepted(row, fallback):
    return row if row["converged"] else fallback


def run_pipeline(case, original, additional):
    regional, sources = {}, {}
    for arm in ARMS:
        selected, source = select(arm_selected(original, arm), arm_selected(additional, arm))
        if selected is None:
            raise ValueError(f"No regional finalist for {arm}")
        regional[arm] = dict(
            stage="region",
            arm=arm,
            converged=selected["converged"],
            error_km=selected["horizontal_error_m"] / 1000,
            posterior_rms_hz=selected["posterior_rms_hz"],
            selected=selected,
        )
        sources[arm] = source
    document = additional if sources["fitted-c"] == "additional" else original
    selected = arm_selected(document, "fitted-c")
    start = next(
        r
        for r in document["diagnostics"]["final_starts"]
        if r["arm"] == "fitted-c"
        and r["basin"] == selected["source_basin"]
        and r["fit"]
        and r["fit"]["converged"]
        and abs(r["fit"]["objective"] - selected["objective"]) < 1e-9
    )
    lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
    bank = case.bank.select([lookup[n] for n in selected["satellites"]])
    calibration = document["diagnostics"]["calibrations"][selected["source_basin"]]
    base = Hard60Objective(
        case.prepared.observations,
        bank,
        case.prior,
        HARD60_SCORE,
        receiver_baseline_hz=np.asarray(calibration["receiver_baseline_hz"]),
    )
    correction = calibration["correction"]
    nodes, knots = correction["nodes_s"], correction["knots_hz"]
    seed = np.asarray(start["fit"]["vector"])
    stages = {}

    def run_stage(name, model, seed, clock=None, first=False, dynamic=False):
        rows = {}
        for arm in ARMS:
            if first:
                row = initial_fit(model, seed, arm=arm)
            elif dynamic:
                row = rf_fit(model, seed, arm=arm, clock_seed=clock)
            else:
                row = fit(model, seed, arm=arm, clock_seed=clock)
            row = json_value(row)
            row.update(stage=name, arm=arm, error_km=error_km(case.prior, row["vector"], document))
            rows[arm] = row
        stages[name] = rows
        return rows

    joint = run_stage("joint-100", InitialClockObjective(base, nodes, knots, 2), seed, first=True)
    if not joint["fitted-c"]["converged"]:
        return dict(
            regional_sources=sources,
            stages=stages,
            operational=regional,
            stopped="joint fitted-c nonstationary",
        )
    chosen = joint["fitted-c"]
    try:
        subset, seed, removed = reduce_bank(base, np.asarray(chosen["vector"]), 5)
    except ValueError as error:
        return dict(
            regional_sources=sources, stages=stages, operational=regional, stopped=str(error)
        )
    pruned = run_stage(
        "remove-5", JointClockObjective(subset, nodes, knots, 2), seed, chosen["clock_coefficients"]
    )
    if not pruned["fitted-c"]["converged"]:
        return dict(
            regional_sources=sources,
            stages=stages,
            operational=regional,
            stopped="pruned fitted-c nonstationary",
            removed=removed,
        )
    chosen = pruned["fitted-c"]
    post = run_stage(
        "post-200",
        JointClockObjective(subset, nodes, knots, 4),
        np.asarray(chosen["vector"]),
        chosen["clock_coefficients"],
    )
    post_operational = {
        arm: accepted(post[arm], accepted(pruned[arm], regional[arm])) for arm in ARMS
    }
    chosen = accepted(post["fitted-c"], pruned["fitted-c"])
    final = run_stage(
        "drift-50",
        DynamicRFObjective(subset, nodes, knots, 50),
        np.asarray(chosen["vector"]),
        np.r_[chosen["clock_coefficients"], 0.0, 0.0],
        dynamic=True,
    )
    return dict(
        regional_sources=sources,
        regional=regional,
        stages=stages,
        operational={arm: accepted(final[arm], post_operational[arm]) for arm in ARMS},
        removed=removed,
        satellites=subset.bank.numbers.tolist(),
        stopped=None,
    )
