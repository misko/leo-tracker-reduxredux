import copy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from tools import ds7_baseline_adapter as baseline
from tools.ds7_association_adapter import (
    frozen_starts,
    permute_candidate_rows,
    reverse_trajectory_time,
    winning_run_index,
)


def synthetic_document() -> tuple[dict, dict]:
    center = [37.85625, -122.484375]
    config = {
        "geographic_prior_center_deg": center,
        "timing_grid_s": [-0.25, 0.0, 0.25],
    }
    receiver, up = baseline.site(*center)
    count = 9
    desired = np.linspace(-1200.0, 1200.0, count)
    position = receiver + up * 1000.0
    positions = np.broadcast_to(position, (1, 3, count, 3)).copy()
    velocities = np.empty_like(positions)
    for tau in range(3):
        velocities[0, tau] = -desired[:, None] * baseline.LIGHT_KM_S / baseline.REFERENCE_RF_HZ * up
    track = {
        "candidate_position_km": positions,
        "candidate_velocity_km_s": velocities,
        "y": desired.copy(),
        "mask": np.array([True, True, False, True, False, True, False, True, False]),
        "catalogue_size": 1,
    }
    return {"tracks": [track]}, config


def test_frozen_searches_have_identical_total_cap_allocation():
    assert len(frozen_starts("local", 1)) * 60 == 180
    assert len(frozen_starts("multibasin", 1)) * 20 == 180


def test_ready_configs_bind_exact_starts_and_canonical_rf():
    root = Path(__file__).parents[2]
    for policy in ("local", "multibasin"):
        config = json.loads((root / f"config/ds7/association-{policy}-ready-v1.json").read_text())[
            "config"
        ]
        assert config["frozen_starts"] == [row.tolist() for row in frozen_starts(policy, 1)]
        assert config["canonical_rf_hz"] == baseline.REFERENCE_RF_HZ
        assert config["timing_grid_s"] == np.arange(-5.0, 5.001, 0.25).tolist()
        assert len(config["frozen_starts"]) * config["per_start_nfev_cap"] == 180


def test_array_bearing_fake_optimizer_selects_second_winner():
    runs = [
        SimpleNamespace(fun=2.0, x=np.array([1.0, 2.0])),
        SimpleNamespace(fun=1.0, x=np.array([3.0, 4.0])),
    ]
    assert winning_run_index(runs) == 1


def test_candidate_label_permutation_is_likelihood_invariant():
    document, config = synthetic_document()
    duplicate = copy.deepcopy(document)
    duplicate["tracks"][0]["candidate_position_km"] = np.concatenate(
        [document["tracks"][0]["candidate_position_km"]] * 2
    )
    duplicate["tracks"][0]["candidate_velocity_km_s"] = np.concatenate(
        [document["tracks"][0]["candidate_velocity_km_s"]] * 2
    )
    duplicate["tracks"][0]["catalogue_size"] = 2
    point = np.zeros(3)
    original = baseline.Stationary(duplicate, config).evaluate(point)[0]
    permuted = baseline.Stationary(permute_candidate_rows([duplicate])[0], config).evaluate(point)[
        0
    ]
    assert permuted == original


def test_wrong_trajectory_control_loses_injected_identity_support():
    document, config = synthetic_document()
    point = np.zeros(3)
    correct = baseline.Stationary(document, config).evaluate(point)[0]
    wrong = baseline.Stationary(reverse_trajectory_time([document])[0], config).evaluate(point)[0]
    assert correct > wrong + 10.0
