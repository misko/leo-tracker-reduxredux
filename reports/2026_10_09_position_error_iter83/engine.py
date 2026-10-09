"""Generic ordinary regional inputs and shared-clock transport for research."""

import functools
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter51"))
from cohort_inputs import load, read  # noqa: E402, F401

sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter82"))
from protocol_loader import verified_protocol  # noqa: E402

sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter41"))
from region_inventory import inventory, regional  # noqa: E402, F401

sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter68"))
from audit import make_model, residuals  # noqa: E402, F401

sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter52"))
from common_sigma1 import (  # noqa: E402
    HARD60_SCORE,
    Hard60Objective,
    InitialClockObjective,
    fit,
    json_value,
    predict_orbits,
    transport,
)

sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter67"))
from clock_starts import clock_starts  # noqa: E402, F401
from probe import error_km  # noqa: E402, F401

# Scope the historical metadata lookup without modifying its executed source.
baseline_module = sys.modules["baseline"]
assert Path(baseline_module.__file__).resolve() == (
    REPORTS / "2026_10_08_position_error_iter01/baseline.py"
)
baseline_module.protocol = functools.partial(verified_protocol, baseline_module.HERE)


def common_inventory(case, baseline, regions):
    """Use final-fit banks, never the smaller calibration bootstrap bank."""
    numbers = sorted({
        n for region in regions for arm in region["document"]["methods"][0]["arms"]
        for n in arm["selected"]["satellites"]
    })
    if not numbers:
        raise ValueError("No successful regional final bank")
    common = make_model(case, baseline, 1, numbers)
    lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
    rows = []
    for region in regions:
        document = region["document"]
        for start in document["diagnostics"]["final_starts"]:
            row = dict(region=region["region"]["index"], source_arm=start["arm"],
                       start=start["start"], basin=start["basin"])
            if not start["fit"]:
                rows.append(dict(row, status="missing_fit"))
                continue
            selected = next(a["selected"] for a in document["methods"][0]["arms"]
                            if a["name"] == start["arm"])
            assert selected["source_basin"] == start["basin"]
            bank = case.bank.select([lookup[n] for n in selected["satellites"]])
            cal = document["diagnostics"]["calibrations"][start["basin"]]
            base = Hard60Objective(
                case.prepared.observations, bank, case.prior,
                replace(HARD60_SCORE, relative_sigma_s=2),
                receiver_baseline_hz=np.asarray(cal["receiver_baseline_hz"]),
            )
            correction = cal["correction"]
            old = InitialClockObjective(base, correction["nodes_s"], correction["knots_hz"], 2)
            vector = np.asarray(start["fit"]["vector"])
            clock = old.initial_clock.copy()
            np.testing.assert_allclose(base.evaluate(vector)[0], start["fit"]["objective"],
                                       atol=1e-6, rtol=0)
            indices = [numbers.index(int(n)) for n in bank.numbers]
            seed, delta = transport(old, common, vector, clock, indices)
            old_p, old_v, _, _ = predict_orbits(
                bank, case.prepared.observations, case.prior,
                vector[:2], vector[7] + old.basis @ vector[8:],
            )
            new_p, new_v, _, _ = predict_orbits(
                common.bank, case.prepared.observations, case.prior,
                seed[:2], seed[7] + common.basis @ seed[8:],
            )
            np.testing.assert_allclose(new_p[:, indices], old_p, atol=1e-6, rtol=0)
            np.testing.assert_array_equal(new_v[:, indices], old_v)
            limits = dict(slope_hz_s=float(max(abs(seed[[3, 5]]))), c=float(abs(seed[6])),
                          common_s=float(abs(seed[7])), clock_hz=float(max(abs(clock))),
                          total_timing_s=float(max(abs(seed[7] + common.basis @ seed[8:]))))
            violations = [k for k, bound in dict(slope_hz_s=60, c=5000, common_s=10,
                                                total_timing_s=20, clock_hz=2000).items()
                          if limits[k] > bound + 1e-8]
            row.update(status="infeasible" if violations else "feasible", limits=limits,
                       violations=violations, source_converged=start["fit"]["converged"],
                       seed=seed.tolist(), clock=clock.tolist(), affine_delta=delta.tolist(),
                       common_score=float(common.evaluate_joint(seed, clock)[0]))
            rows.append(row)
    return common, dict(candidate_union=numbers, rows=rows)


def attempt(model, seed, clock, arm):
    model.initial_clock = np.asarray(clock).copy()
    result = json_value(fit(model, np.asarray(seed).copy(), arm=arm,
                            maximum_seconds=90, maximum_iterations=600))
    if arm == "zero-c":
        assert result["vector"][6] == 0
    return result
