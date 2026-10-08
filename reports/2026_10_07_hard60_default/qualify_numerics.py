"""Check the production port against saved Hard60 searches and original mathematics."""

import json
import sys
from pathlib import Path

import numpy as np

from leo.analysis.hard60_score import Hard60Objective
from leo.analysis.regional_position_fit import fit_position
from leo.analysis.regional_position_score import PositionObjective
from leo.analysis.regional_position_search import hierarchical_search
from leo.application.hard60_runner import HARD60_SCORE
from leo.contracts.regional_position import PositionObservations, PositionOrbitBank, RegionalPrior


def inputs(root, label):
    folder = root / "2026_10_07_n64_before_after" / "inputs" / label
    metadata = json.loads((folder / "inputs.json").read_text())
    with np.load(folder / "arrays.npz", allow_pickle=False) as arrays:
        obs = PositionObservations(
            tuple(arrays["obs_window_ids"].tolist()),
            **{
                name: arrays["obs_" + name]
                for name in ("times_s", "measured_hz", "rf_hz", "receiver", "channel", "margin")
            },
        )
        bank = PositionOrbitBank(
            **{
                name: arrays["bank_" + name]
                for name in ("numbers", "nodes_s", "position_km", "velocity_km_s")
            }
        )
    return obs, bank, RegionalPrior(**metadata["prior"])


def main(root, destination):
    root = Path(root)
    study = root / "2026_10_07_n64_sigma_slope_variants" / "results"
    receipt = {"searches": [], "fixed_states": [], "coarse_replays": []}
    for i in range(1, 65):
        label = f"N{i:02d}"
        saved = json.loads((study / label / "sigma2_60/search.json").read_text())["search"]
        lookup = {(p["east_km"], p["north_km"]): p["score"] for p in saved["evaluations"]}
        replay = hierarchical_search(
            lambda e, n, lookup=lookup: lookup[(e, n)],
            levels_km=(40, 20, 10, 5),
            budget_points=400,
            edge_priority="nearest",
        )
        assert [(p.east_km, p.north_km) for p in replay.evaluations] == list(lookup)
        assert replay.deferred_cells == saved["deferred_cells"]
        receipt["searches"].append({"label": label, "points": len(lookup), "exact_order": True})
    for label in ("N29", "N49", "N64"):
        obs, bank, prior = inputs(root, label)
        folder = study / label / "sigma2_60"
        for path in sorted((folder / "regions").glob("*.json")):
            region = json.loads(path.read_text())
            if region["status"] != "complete":
                continue
            selected = bank.select(region["association"]["selected_indices"])
            baseline = np.asarray(region["calibration"]["receiver_baseline_hz"])
            native = Hard60Objective(
                obs, selected, prior, HARD60_SCORE, receiver_baseline_hz=baseline
            )
            oracle = PositionObjective(
                obs, selected, prior, HARD60_SCORE, receiver_baseline_hz=baseline
            )
            for row in region["runs"]:
                vector = np.asarray(row["vector"])
                actual, expected = native.evaluate(vector), oracle.evaluate(vector)
                np.testing.assert_allclose(actual[0], expected[0], atol=1e-6, rtol=0)
                np.testing.assert_allclose(actual[1], expected[1], atol=1e-6, rtol=1e-7)
                receipt["fixed_states"].append(
                    {
                        "label": label,
                        "region": path.name,
                        "arm": row["arm"],
                        "objective_difference": actual[0] - expected[0],
                        "maximum_gradient_difference": float(np.max(abs(actual[1] - expected[1]))),
                    }
                )
        # The same two independently defined grid coordinates, without reference information.
        for point in ((-80, -80), (0, 0)):
            path = folder / "points" / f"{point[0]}_{point[1]}.json"
            if not path.exists():
                continue
            saved = json.loads(path.read_text())
            if saved["status"] != "complete":
                continue
            objective = Hard60Objective(
                obs, bank.select(saved["bootstrap"]["satellite_indices"]), prior, HARD60_SCORE
            )
            fitted = fit_position(
                objective,
                np.asarray(saved["bootstrap"]["vector"]),
                fixed_position=True,
                maximum_seconds=5,
                maximum_iterations=200,
                slope_half_width_hz_s=60,
            )
            delta = fitted.objective - saved["fit"]["objective"]
            receipt["coarse_replays"].append(
                {
                    "label": label,
                    "point": point,
                    "objective_difference": delta,
                    "stop_reason": fitted.stop_reason,
                    "matches_1e_6": abs(delta) <= 1e-6,
                }
            )
    Path(destination).write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({key: len(value) for key, value in receipt.items()}))


if __name__ == "__main__":
    main(*sys.argv[1:])
