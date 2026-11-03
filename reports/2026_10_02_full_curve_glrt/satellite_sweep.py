import json
import time
from pathlib import Path

import numpy as np
from position_search import Experiment, ecef
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent


def main():
    started = time.monotonic()
    selection = json.loads((ROOT / "satellite-sweep-selection.json").read_text())
    results = {
        "protocol": (
            "RX corrections fixed to track-stage solution; all 3192 groups; no holdout; "
            "same capped robust nearest-curve loss, altitude, timing, grid "
            "and multistart optimizer for each nested subset"
        ),
        "selection": selection["policy"],
        "models": {},
    }
    original_losses = []
    for count in (8, 16, 32, 64):
        experiment = Experiment(
            all_training=True,
            states_path=ROOT / "satellite-sweep-states.npz",
            candidate_limit=count,
        )
        np.testing.assert_array_equal(
            experiment.candidate_numbers, selection["subsets"][str(count)]
        )
        solution = experiment.metadata["solution"]
        origin = [solution["east_km"], solution["north_km"]]
        original_loss = experiment.evaluate(origin, False)
        original_losses.append(original_loss)
        if count == 16:
            previous = json.loads((ROOT / "position-results-all-training.json").read_text())
            np.testing.assert_allclose(
                original_loss, previous["models"]["original"]["training_loss"], rtol=1e-12
            )
        grid = []
        for east in np.arange(-200, 201, 50):
            for north in np.arange(-200, 201, 50):
                point = [float(east), float(north)]
                grid.append({"point": point, "loss": experiment.evaluate(point, False)})
        seeds = [origin, *[row["point"] for row in sorted(grid, key=lambda row: row["loss"])[:2]]]
        candidates = [(experiment.evaluate(point, False), point) for point in seeds]
        refinements = []
        for seed in seeds:
            simplex = np.tile(seed, (3, 1))
            simplex[1, 0] += 2 if seed[0] < 198 else -2
            simplex[2, 1] += 2 if seed[1] < 198 else -2
            fit = minimize(
                lambda point, current=experiment: current.evaluate(point, False),
                seed,
                method="Nelder-Mead",
                bounds=[(-200, 200), (-200, 200)],
                options={"maxfev": 180, "xatol": 0.03, "fatol": 1.0, "initial_simplex": simplex},
            )
            candidates.append((float(fit.fun), fit.x.tolist()))
            refinements.append(
                {
                    "point": fit.x.tolist(),
                    "loss": float(fit.fun),
                    "success": bool(fit.success),
                    "evaluations": int(fit.nfev),
                }
            )
        winner = min(candidates, key=lambda row: row[0])[1]
        result = experiment.evaluate(winner, False, details=True)
        reference = experiment.metadata["source"]["reference_site"]
        result["reference_error_km"] = float(
            np.linalg.norm(
                ecef(result["latitude"], result["longitude"])
                - ecef(reference["latitude_deg"], reference["longitude_deg"])
            )
        )
        result.update(
            original_loss=original_loss,
            grid=grid,
            refinements=refinements,
            satellite_ids=experiment.candidate_numbers.tolist(),
            objective_evaluations=experiment.evaluations,
        )
        results["models"][str(count)] = result
        results["elapsed_s"] = time.monotonic() - started
        (ROOT / "satellite-sweep-results.json").write_text(
            json.dumps(results, indent=2, allow_nan=False) + "\n"
        )
        print(
            json.dumps(
                {
                    "satellites": count,
                    **{
                        key: value
                        for key, value in result.items()
                        if key not in ("grid", "refinements", "satellite_ids")
                    },
                }
            ),
            flush=True,
        )
    assert np.all(np.diff(original_losses) <= 1e-8)


if __name__ == "__main__":
    main()
