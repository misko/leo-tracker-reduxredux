"""Assemble the qualified slope-0.25 stage without changing frozen upstream fits."""

import sys
from pathlib import Path

import numpy as np

REPORTS = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPORTS / f"2026_10_08_position_error_iter{n}") for n in ("25", "27")]
# isort: off
from inputs25 import load  # noqa: E402, F401
from dynamic_rf import DynamicRFObjective, fit  # noqa: E402
from slope_prior import SlopePrior  # noqa: E402
from inputs import json_value  # noqa: E402
from probe import error_km  # noqa: E402
from pipeline import ARMS, arm_selected  # noqa: E402
from leo.analysis.hard60_score import Hard60Objective  # noqa: E402
from leo.application.hard60_runner import HARD60_SCORE  # noqa: E402
# isort: on


def extend_basis(case, document, base, correction, seed, clock, previous):
    control = DynamicRFObjective(base, correction["nodes_s"], correction["knots_hz"], 50)
    _, _, _, terms = control.evaluate_joint(seed, clock)
    mass = terms.responsibilities.sum(axis=0)
    centers = np.divide(
        terms.responsibilities.T @ base.observations.times_s,
        mass,
        out=np.full(len(mass), base.observations.time_center_s),
        where=mass > 1e-12,
    )
    slope = SlopePrior(base, correction["nodes_s"], correction["knots_hz"], centers, 0.25)
    stages = {}
    for name, model, initial in (
        ("control-refit", control, clock),
        ("slope-0.25", slope, slope.expand_clock(clock)),
    ):
        rows = {}
        for arm in ARMS:
            row = json_value(fit(model, seed, arm=arm, clock_seed=initial))
            row.update(stage=name, arm=arm, error_km=error_km(case.prior, row["vector"], document))
            if name == "slope-0.25":
                row["satellite_slopes_hz_s"] = slope.physical_corrections(
                    np.asarray(row["clock_coefficients"])
                )[1].tolist()
            if arm == "zero-c":
                assert row["vector"][6] == 0 and row["rf_drift_coefficients"] == [0, 0]
            rows[arm] = row
        stages[name] = rows
    control_operational = {
        arm: stages["control-refit"][arm]
        if stages["control-refit"][arm]["converged"]
        else previous[arm]
        for arm in ARMS
    }
    return dict(
        stages=stages,
        control_operational=control_operational,
        operational={
            arm: stages["slope-0.25"][arm]
            if stages["slope-0.25"][arm]["converged"]
            else control_operational[arm]
            for arm in ARMS
        },
        centers_s=centers.tolist(),
        satellites=base.bank.numbers.tolist(),
    )


def extend_pipeline(case, original, additional, result):
    if result["stopped"] is not None:
        return dict(
            stages={},
            control_operational=result["operational"],
            operational=result["operational"],
            stopped=result["stopped"],
        )
    document = additional if result["regional_sources"]["fitted-c"] == "additional" else original
    selected = arm_selected(document, "fitted-c")
    calibration = document["diagnostics"]["calibrations"][selected["source_basin"]]
    lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
    bank = case.bank.select([lookup[n] for n in result["satellites"]])
    base = Hard60Objective(
        case.prepared.observations,
        bank,
        case.prior,
        HARD60_SCORE,
        receiver_baseline_hz=np.asarray(calibration["receiver_baseline_hz"]),
    )
    for source in ("drift-50", "post-200", "remove-5"):
        chosen = result["stages"][source]["fitted-c"]
        if chosen["converged"]:
            break
    else:
        raise ValueError("No accepted fitted seed after successful upstream pipeline")
    clock = np.asarray(chosen["clock_coefficients"])
    if source != "drift-50":
        clock = np.r_[clock, 0.0, 0.0]
    result = extend_basis(
        case,
        document,
        base,
        calibration["correction"],
        np.asarray(chosen["vector"]),
        clock,
        result["operational"],
    )
    result.update(source_stage=source, stopped=None)
    return result
