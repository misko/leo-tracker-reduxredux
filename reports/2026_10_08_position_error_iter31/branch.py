"""Matched single-basin diagnostic through public numerical functions."""

import sys
from pathlib import Path

import numpy as np

REPORTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter28"))
# isort: off
from extension import extend_pipeline  # noqa: E402
from inputs import json_value  # noqa: E402
from pipeline import run_pipeline  # noqa: E402
from probe import error_km  # noqa: E402
from leo.analysis.hard60_score import Hard60Objective, predict_orbits  # noqa: E402
from leo.analysis.regional_position_association import associate_calibration  # noqa: E402
from leo.analysis.regional_position_calibration import RegionalCalibration, receiver_correction  # noqa: E402
from leo.analysis.regional_position_fit import PositionFit, fit_position  # noqa: E402
from leo.application.hard60_runner import HARD60_SCORE  # noqa: E402
# isort: on


def fitted(model, seed, **kwargs):
    return fit_position(
        model, seed, maximum_seconds=20, maximum_iterations=600, slope_half_width_hz_s=60, **kwargs
    )


def regional(case, point):
    key = f"point:{point[0]:g}:{point[1]:g}"
    receipt = case.checkpoint(key)
    initial = receipt["result"]
    if initial is None:
        raise ValueError("Existing coarse point unavailable")
    indices = tuple(initial["bootstrap"]["satellite_indices"])
    subset = case.bank.select(list(indices))
    model = Hard60Objective(case.prepared.observations, subset, case.prior, HARD60_SCORE)
    saved = initial["fits"]["V16"]["fit"]
    prefit = PositionFit(**{**saved, "vector": np.asarray(saved["vector"])})
    if not prefit.converged:
        prefit = fitted(model, prefit.vector, fixed_position=True)
    if not prefit.converged:
        raise ValueError("Calibration prefit did not converge")
    correction = receiver_correction(case.prepared.observations, model.evaluate(prefit.vector)[2])
    corrected = Hard60Objective(
        case.prepared.observations,
        subset,
        case.prior,
        HARD60_SCORE,
        receiver_baseline_hz=correction.values_hz,
    )
    postfit = fitted(corrected, prefit.vector, fixed_position=True)
    if not postfit.converged:
        raise ValueError("Calibration postfit did not converge")
    baseline = correction.values_hz + corrected.design[:, :4] @ postfit.vector[2:6]
    calibration = RegionalCalibration(indices, prefit, postfit, correction, baseline)
    association = associate_calibration(
        case.prepared.observations,
        case.bank,
        case.prior,
        calibration,
        maximum_seconds=60,
        orbit_predictor=predict_orbits,
    )
    final_bank = case.bank.select(list(association.selected_indices))
    objective = Hard60Objective(
        case.prepared.observations,
        final_bank,
        case.prior,
        HARD60_SCORE,
        receiver_baseline_hz=baseline,
    )
    knots = correction.knots_hz
    penalty = float(
        0.5 * (np.sum(knots**2) / 50**2 + np.sum(np.diff(knots, n=2, axis=1) ** 2) / 25**2)
    )
    center = np.asarray(point, dtype=float)
    finals, arms = [], []
    for arm in ("zero-c", "fitted-c"):
        completed = []
        for name in ("association", "zero-timing", "own-continuation"):
            seed = np.array(association.initial_vector)
            if name == "zero-timing":
                seed[7:] = 0
            elif name == "own-continuation" and completed:
                seed = np.array(min(completed, key=lambda r: r["objective"])["vector"])
            for origin, bound in ((np.zeros(2), case.prior.radius_km), (center, 25)):
                delta = seed[:2] - origin
                length = np.linalg.norm(delta)
                if bound < length <= bound + 1e-6:
                    seed[:2] = origin + delta * ((bound - 1e-8) / length)
            fit = json_value(
                fitted(objective, seed, rf_arm=arm, local_center=center, local_radius_km=25)
            )
            if arm == "zero-c":
                assert fit["vector"][6] == 0
            completed.append(fit)
            finals.append(
                dict(arm=arm, basin=key, start=name, fit=fit, calibration_penalty=penalty)
            )
        eligible = [r for r in completed if r["converged"]]
        if not eligible:
            raise ValueError(f"No converged regional candidate for {arm}")
        chosen = min(eligible, key=lambda r: r["objective"])
        arms.append(
            dict(
                name=arm,
                selected=dict(
                    **chosen,
                    source_basin=key,
                    satellites=final_bank.numbers.tolist(),
                    selection_score=chosen["objective"] + penalty,
                    horizontal_error_m=1000 * error_km(case.prior, chosen["vector"], case.document),
                    calibration_penalty=penalty,
                ),
            )
        )
    # This is a minimal private experiment input, not a persisted public V2 document.
    document = dict(
        scope="Oracle branch diagnostic intermediate; not a public position document",
        reference_latitude_deg=case.document["reference_latitude_deg"],
        reference_longitude_deg=case.document["reference_longitude_deg"],
        methods=[dict(arms=arms)],
        diagnostics=dict(final_starts=finals, calibrations={key: json_value(calibration)}),
    )
    return document, dict(
        coarse=receipt,
        calibration=json_value(calibration),
        association=json_value(association),
        regional_fits=finals,
    )


def downstream(case, document):
    upstream = run_pipeline(case, document, document)
    extended = extend_pipeline(case, document, document, upstream)
    for rows in [*upstream["stages"].values(), *extended["stages"].values()]:
        zero = rows["zero-c"]
        assert zero["vector"][6] == 0
        assert all(x == 0 for x in zero.get("rf_drift_coefficients", []))
    return dict(upstream=upstream, extended=extended)
