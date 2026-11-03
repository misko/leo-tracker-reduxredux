import json
import time
from pathlib import Path

import numpy as np
from position_search import coordinates, ecef
from scipy.optimize import minimize
from time_shift_model import TimeShiftObjective

ROOT = Path(__file__).resolve().parent


def site(point):
    latitude, longitude = coordinates(*point)
    latitude_rad, longitude_rad = np.deg2rad([latitude, longitude])
    up = np.array(
        [
            np.cos(latitude_rad) * np.cos(longitude_rad),
            np.cos(latitude_rad) * np.sin(longitude_rad),
            np.sin(latitude_rad),
        ]
    )
    return ecef(latitude, longitude), up


def build(states_path="satellite-time-states.npz", sigma=1):
    data = np.load(ROOT / "inputs.npz")
    states = np.load(ROOT / states_path)
    metadata = json.loads((ROOT / "inputs.json").read_text())
    correction = np.zeros(len(data["times"]))
    for receiver in (0, 1):
        parameters = metadata["solution"]["parameters"][str(receiver)]
        mask = data["receiver"] == receiver
        correction[mask] = parameters["intercept_hz_at_150s"] + parameters["slope_hz_s"] * (
            data["times"][mask] - 150
        )
    return TimeShiftObjective(data, states, correction, site, sigma=sigma), metadata, states


def main():
    started = time.monotonic()
    objective, metadata, states = build()
    previous = json.loads((ROOT / "satellite-sweep-results.json").read_text())["models"]["64"]
    baseline = np.r_[previous["point"], np.zeros(64)]
    baseline_details = objective.evaluate(baseline, details=True)
    np.testing.assert_allclose(
        baseline_details["mean_frequency_loss"], previous["training_loss"], rtol=0, atol=1
    )
    check = baseline.copy()
    check[2:] = 0.037
    _, analytic = objective.evaluate(check)
    checked = [0, 1, *list(2 + np.argsort(-np.abs(analytic[2:]))[:6])]
    finite_difference = []
    for index in checked:
        plus, minus = check.copy(), check.copy()
        plus[index] += 1e-5
        minus[index] -= 1e-5
        difference = (objective.evaluate(plus)[0] - objective.evaluate(minus)[0]) / 2e-5
        finite_difference.append(
            {"index": int(index), "analytic": float(analytic[index]), "numeric": float(difference)}
        )
        np.testing.assert_allclose(analytic[index], difference, rtol=2e-3, atol=0.03)
    seeds = [
        previous["point"],
        *[row["point"] for row in sorted(previous["grid"], key=lambda row: row["loss"])[:2]],
    ]
    result = {
        "protocol": (
            "64 fixed candidates; position plus 64 satellite orbit-time shifts; "
            "shifts shared across RX/channels; tau in [-3,3]s; N(0,1s^2) prior; "
            "RX line uses unshifted receive time and stays fixed; all 3192 groups; no holdout; "
            "sum(rho/(2*200Hz^2)) + sum(tau^2/2); penalized surrogate, not calibrated posterior"
        ),
        "baseline": baseline_details,
        "gradient_checks": finite_difference,
        "runs": [],
    }
    best_value, best = objective.evaluate(baseline)[0], baseline
    for seed in seeds:
        initial = np.r_[seed, np.zeros(64)]
        fitted = minimize(
            objective.evaluate,
            initial,
            jac=True,
            method="L-BFGS-B",
            bounds=[(-200, 200), (-200, 200)] + [(-3, 3)] * 64,
            options={"maxiter": 180, "maxfun": 450, "ftol": 1e-9, "gtol": 1e-4, "maxls": 25},
        )
        details = objective.evaluate(fitted.x, details=True)
        details.update(
            point=fitted.x[:2].tolist(),
            shifts_s=fitted.x[2:].tolist(),
            success=bool(fitted.success),
            message=str(fitted.message),
            iterations=int(fitted.nit),
            evaluations=int(fitted.nfev),
        )
        result["runs"].append(details)
        if fitted.fun < best_value:
            best_value, best = float(fitted.fun), fitted.x.copy()
        result["elapsed_s"] = time.monotonic() - started
        (ROOT / "time-shift-results.json").write_text(json.dumps(result, indent=2) + "\n")
        print(
            json.dumps(
                {
                    key: value
                    for key, value in details.items()
                    if key not in ("gradient", "shifts_s", "assignment_counts")
                }
            ),
            flush=True,
        )
    latitude, longitude = coordinates(*best[:2])
    reference = metadata["source"]["reference_site"]
    final = objective.evaluate(best, details=True)
    final.update(
        point=best[:2].tolist(),
        latitude=float(latitude),
        longitude=float(longitude),
        shifts_s=best[2:].tolist(),
        satellite_numbers=states["numbers"].tolist(),
        reference_error_km=float(
            np.linalg.norm(
                ecef(latitude, longitude)
                - ecef(reference["latitude_deg"], reference["longitude_deg"])
            )
        ),
        shifts_at_bound=int(np.sum(np.abs(best[2:]) >= 2.9999)),
    )
    result["best"] = final
    result["elapsed_s"] = time.monotonic() - started
    (ROOT / "time-shift-results.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )


if __name__ == "__main__":
    main()
