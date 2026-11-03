import json
import time
from pathlib import Path

import numpy as np
from position_search import coordinates, ecef
from scipy.optimize import minimize
from time_shift_search import build

ROOT = Path(__file__).resolve().parent


def main():
    objective, metadata, states = build("satellite-time-states-10s.npz", sigma=10 / 3)
    narrow = json.loads((ROOT / "time-shift-refined.json").read_text())
    baseline = json.loads((ROOT / "satellite-sweep-results.json").read_text())["models"]["64"]
    cold = np.r_[baseline["point"], np.zeros(64)]
    np.testing.assert_allclose(
        objective.evaluate(cold, details=True)["mean_frequency_loss"],
        baseline["training_loss"],
        atol=1,
        rtol=0,
    )
    reference = metadata["source"]["reference_site"]
    runs = []
    for label, initial in [
        ("warm_from_3s", np.r_[narrow["point"], narrow["shifts_s"]]),
        ("zero_shifts", cold),
    ]:
        started = time.monotonic()
        fitted = minimize(
            objective.evaluate,
            initial,
            jac=True,
            method="L-BFGS-B",
            bounds=[(-200, 200)] * 2 + [(-10, 10)] * 64,
            options={"maxiter": 700, "maxfun": 1000, "ftol": 1e-9, "gtol": 1e-4, "maxls": 25},
        )
        assert fitted.fun <= objective.evaluate(initial)[0] + 1e-6
        latitude, longitude = coordinates(*fitted.x[:2])
        result = objective.evaluate(fitted.x, details=True)
        result.update(
            start=label,
            point=fitted.x[:2].tolist(),
            latitude=float(latitude),
            longitude=float(longitude),
            shifts_s=fitted.x[2:].tolist(),
            satellite_numbers=states["numbers"].tolist(),
            reference_error_km=float(
                np.linalg.norm(
                    ecef(latitude, longitude)
                    - ecef(reference["latitude_deg"], reference["longitude_deg"])
                )
            ),
            shifts_at_bound=int(np.sum(np.abs(fitted.x[2:]) >= 9.9999)),
            success=bool(fitted.success),
            message=str(fitted.message),
            iterations=int(fitted.nit),
            elapsed_s=time.monotonic() - started,
            protocol=(
                "64 frozen candidates; fixed RX corrections at receive time; "
                "position plus satellite time shifts bounded +/-10s; Gaussian sigma=10/3s; "
                "all 3192 groups, no holdout; same robust loss and position bounds; "
                "conditional shortlist, not blind validation or calibrated posterior"
            ),
        )
        runs.append(result)
        best = min(runs, key=lambda row: row["penalized_objective"])
        for name, value in [("time-shift-10s-runs.json", runs), ("time-shift-10s.json", best)]:
            (ROOT / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
        print(
            json.dumps(
                {
                    key: value
                    for key, value in result.items()
                    if key not in ("gradient", "shifts_s", "satellite_numbers", "assignment_counts")
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
