import json
import time
from pathlib import Path

import numpy as np
from position_search import coordinates, ecef
from scipy.optimize import minimize
from time_shift_search import build

ROOT = Path(__file__).resolve().parent


def main():
    started = time.monotonic()
    previous = json.loads((ROOT / "time-shift-results.json").read_text())
    objective, metadata, states = build()
    best = previous["best"]
    initial = np.r_[best["point"], best["shifts_s"]]
    fitted = minimize(
        objective.evaluate,
        initial,
        jac=True,
        method="L-BFGS-B",
        bounds=[(-200, 200), (-200, 200)] + [(-3, 3)] * 64,
        options={"maxiter": 600, "maxfun": 800, "ftol": 1e-9, "gtol": 1e-4, "maxls": 25},
    )
    assert fitted.fun <= objective.evaluate(initial)[0] + 1e-6
    latitude, longitude = coordinates(*fitted.x[:2])
    reference = metadata["source"]["reference_site"]
    result = objective.evaluate(fitted.x, details=True)
    result.update(
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
        shifts_at_bound=int(np.sum(np.abs(fitted.x[2:]) >= 2.9999)),
        success=bool(fitted.success),
        message=str(fitted.message),
        iterations=int(fitted.nit),
        evaluations=int(fitted.nfev),
        elapsed_s=time.monotonic() - started,
        protocol=previous["protocol"],
    )
    (ROOT / "time-shift-refined.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )
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
