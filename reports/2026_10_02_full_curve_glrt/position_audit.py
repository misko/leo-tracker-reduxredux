import json
from pathlib import Path

import numpy as np
from matching import ALIAS_HZ
from position_search import PRIOR_LATITUDE, PRIOR_LONGITUDE, Experiment, coordinates

ROOT = Path(__file__).resolve().parent


def reference_point(latitude, longitude):
    latitude, longitude, origin_latitude, origin_longitude = np.deg2rad(
        [latitude, longitude, PRIOR_LATITUDE, PRIOR_LONGITUDE]
    )
    delta = longitude - origin_longitude
    bearing = np.arctan2(
        np.sin(delta) * np.cos(latitude),
        np.cos(origin_latitude) * np.sin(latitude)
        - np.sin(origin_latitude) * np.cos(latitude) * np.cos(delta),
    )
    distance = 6371.0088 * np.arccos(
        np.clip(
            np.sin(origin_latitude) * np.sin(latitude)
            + np.cos(origin_latitude) * np.cos(latitude) * np.cos(delta),
            -1,
            1,
        )
    )
    return [float(distance * np.sin(bearing)), float(distance * np.cos(bearing))]


def main():
    experiment = Experiment()
    results = json.loads((ROOT / "position-results.json").read_text())
    reference = experiment.metadata["source"]["reference_site"]
    truth = reference_point(reference["latitude_deg"], reference["longitude_deg"])
    np.testing.assert_allclose(
        coordinates(*truth), [reference["latitude_deg"], reference["longitude_deg"]], atol=1e-8
    )
    original = results["models"]["original"]["point"]
    best = results["models"]["profiled_rx"]["point"]
    audit = {
        "scope": "post-search diagnostics only; reference not used to select a solution",
        "reference_point": truth,
        "reference_profiled": experiment.evaluate(truth, True, details=True),
        "original_profiled": experiment.evaluate(original, True, details=True),
    }
    generator = np.random.default_rng(20261002)
    controls = []
    for _trial in range(20):
        shifts = generator.uniform(10000, ALIAS_HZ - 10000, 16)
        controls.append(experiment.evaluate(best, True, details=True, phase_shift_hz=shifts))
    audit["controls"] = controls
    surface = []
    for east in np.linspace(best[0] - 5, best[0] + 5, 11):
        for north in np.linspace(best[1] - 5, best[1] + 5, 11):
            surface.append(
                {
                    "point": [float(east), float(north)],
                    "training_loss": experiment.evaluate([east, north], True),
                }
            )
    audit["local_surface"] = surface
    (ROOT / "position-audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(
        json.dumps(
            {
                "reference_profiled_loss": audit["reference_profiled"]["training_loss"],
                "original_profiled_loss": audit["original_profiled"]["training_loss"],
                "control_training_loss_range": [
                    min(row["training_loss"] for row in controls),
                    max(row["training_loss"] for row in controls),
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
