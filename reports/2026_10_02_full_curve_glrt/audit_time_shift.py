import argparse
import json
from pathlib import Path

import numpy as np
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from matching import circular_residual
from position_loss import SCALE_HZ, best_group_rows, rho
from time_shift_model import gaussian_prior
from time_shift_search import build, site

from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", default="time-shift-refined.json")
    parser.add_argument("--states", default="satellite-time-states.npz")
    parser.add_argument("--sigma", type=float, default=1)
    parser.add_argument("--output", default="time-shift-exact-audit.json")
    args = parser.parse_args()
    result = json.loads((ROOT / args.result).read_text())
    objective, metadata, states = build(args.states, args.sigma)
    data = objective.data
    origin = metadata["source"]["start_utc_ns"]
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshot = archive.select_latest_before(origin - 505_000_000_000)
    assert snapshot.digest == metadata["source"]["snapshot_digest"]
    payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = parse_element_sets(payload)
    lookup = {int(number): index for index, number in enumerate(catalogue.satellite_numbers)}
    receiver, up = site(result["point"])
    predictions, elevations = [], []
    for number, shift in zip(result["satellite_numbers"], result["shifts_s"], strict=True):
        position, velocity, valid = propagate_candidate_states(
            catalogue, [lookup[number]], origin, data["times"], np.array([shift])
        )
        assert list(valid) == [lookup[number]]
        delta = position[0, 0] - receiver
        direction = delta / np.linalg.norm(delta, axis=1)[:, None]
        predictions.append(
            -data["rf"] * np.sum(direction * velocity[0, 0], axis=1) / 299792.458
            + objective.correction
        )
        elevations.append(np.sum(direction * up, axis=1))
    residual = circular_residual(data["measured"][:, None], np.array(predictions).T)
    residual[np.array(elevations).T < 0] = np.inf
    _, satellites, errors = best_group_rows(residual, data["group"])
    exact_loss = float(np.mean(rho(errors)))
    exact_objective = float(
        np.sum(rho(errors)) / (2 * SCALE_HZ**2)
        + gaussian_prior(np.array(result["shifts_s"]), args.sigma)[0]
    )
    audit = {
        "exact_mean_frequency_loss": exact_loss,
        "interpolated_mean_frequency_loss": result["mean_frequency_loss"],
        "difference_hz2": exact_loss - result["mean_frequency_loss"],
        "exact_penalized_objective": exact_objective,
        "groups_within_1000hz": int(np.sum(np.abs(errors) < 1000)),
        "satellite_matches": [
            {
                "catalog_number": int(number),
                "shift_s": float(shift),
                "matched_groups": int(np.sum((satellites == index) & (np.abs(errors) < 1000))),
            }
            for index, (number, shift) in enumerate(
                zip(result["satellite_numbers"], result["shifts_s"], strict=True)
            )
        ],
    }
    assert abs(exact_loss - result["mean_frequency_loss"]) < 1
    (ROOT / args.output).write_text(json.dumps(audit, indent=2) + "\n")
    print(
        json.dumps({key: value for key, value in audit.items() if key != "satellite_matches"}),
        flush=True,
    )


if __name__ == "__main__":
    main()
