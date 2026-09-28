import copy

import numpy as np
import pytest

from tools.rx_orbit_increment import _target_density, attach_orbit_increment

PERIOD = 10_000.0


def _lane(observations, mus, times=None):
    if times is None:
        times = list(range(len(observations)))
    windows = []
    for index, (values, mu) in enumerate(zip(observations, mus, strict=True)):
        windows.append(
            {
                "source_window_id": f"w{index}",
                "role": "reception" if index < len(observations) - 1 else "held_frequency",
                "predictions": [
                    {
                        "track_id": "track",
                        "catalog_number": 1,
                        "mu_canonical_rx0_hz": mu,
                        "visible": True,
                    }
                ],
                "observed": {
                    "rx0": [{"canonical_rx0_hz": value} for value in values],
                    "rx1": [],
                },
            }
        )
    count = len(windows)
    source = {
        "lane": {"session_id": "s", "channel": 1, "edge": "lower"},
        "alias_period_hz": PERIOD,
        "components": [
            {
                "kind": "track_candidate",
                "track_id": "track",
                "catalog_number": 1,
                "log_prior": 0.0,
            },
            {"kind": "other", "log_prior": None},
        ],
        "windows": windows,
    }
    return {
        "source": source,
        "indices": list(range(count)),
        "x": np.zeros((count, 1, 8)),
        "visible": np.ones((count, 1), dtype=bool),
        "counts": np.asarray([[len(values), 0] for values in observations]),
        "signal": np.zeros((count, 1, 2)),
        "log_count_probabilities": np.zeros((count, 2, 2)),
        "reference": np.zeros(count),
        "prior": np.asarray([0.0]),
        "times": np.asarray(times, dtype=float),
        "roles": np.asarray([window["role"] for window in windows]),
    }


def test_target_phase_density_is_normalized():
    grid = np.linspace(0.0, PERIOD, 200_001)
    density = _target_density(grid, [100.0, 9_000.0], 700.0, PERIOD)
    assert np.trapezoid(density, grid / PERIOD) == pytest.approx(1.0, abs=2e-9)
    assert np.all(density > 0)


def test_known_orbit_increment_and_duplicate_history_deduplication():
    output, diagnostics = attach_orbit_increment([_lane([[100.0, 100.0], [200.0]], [100.0, 200.0])])
    row = diagnostics[0]["receivers"][0]["windows"][1]["nominees"][0]
    assert row["mode"] == "orbit_increment"
    assert row["history_source_window_id"] == "w0"
    assert row["motion_delta_hz"] == pytest.approx(100.0)
    assert row["target_means_hz"] == pytest.approx([200.0])
    assert output[0]["signal"][1, 0, 0] > 0


def test_empty_advances_clock_without_overwrite_and_stale_history_expires():
    lane = _lane([[100.0], [], [400.0]], [100.0, 200.0, 400.0], times=[0.0, 2.0, 11.0])
    output, diagnostics = attach_orbit_increment([lane])
    rows = diagnostics[0]["receivers"][0]["windows"]
    assert rows[1]["nominees"][0]["history_source_window_id"] == "w0"
    assert rows[1]["nominees"][0]["forecast_horizon_s"] == 2.0
    assert output[0]["signal"][1, 0, 0] == 0.0
    assert rows[2]["nominees"][0]["mode"] == "frozen_mu"
    assert rows[2]["nominees"][0]["history_source_window_id"] is None


def test_motion_controls_and_shift_apply_to_current_target_only():
    lane = _lane([[100.0], [200.0]], [100.0, 200.0])
    lane["x"][:] = np.arange(8)
    regular_output, regular = attach_orbit_increment([copy.deepcopy(lane)])
    zero_output, zero = attach_orbit_increment([copy.deepcopy(lane)], motion_control="zero")
    reverse_output, reverse = attach_orbit_increment(
        [copy.deepcopy(lane)], motion_control="reverse"
    )
    _, shifted = attach_orbit_increment(
        [copy.deepcopy(lane)], frequency_shift_fraction=0.25
    )
    def get(rows):
        return rows[0]["receivers"][0]["windows"][1]["nominees"][0]

    assert get(regular)["target_means_hz"] == pytest.approx([200.0])
    assert get(zero)["target_means_hz"] == pytest.approx([100.0])
    assert get(reverse)["target_means_hz"] == pytest.approx([0.0])
    assert get(shifted)["motion_delta_hz"] == pytest.approx(100.0)
    assert get(shifted)["target_means_hz"] == pytest.approx([2_700.0])
    shifted_window = shifted[0]["receivers"][0]["windows"][1]
    assert shifted_window["delta_mu_hz"] == pytest.approx([100.0])
    assert shifted_window["nominee_keys"] == [{"track_id": "track", "catalog_number": 1}]
    for rows in (regular, zero, reverse):
        assert rows[0]["receivers"][0]["windows"][0]["nominees"][0][
            "target_means_hz"
        ] == pytest.approx([100.0])
    np.testing.assert_array_equal(regular_output[0]["x"], lane["x"])
    np.testing.assert_array_equal(zero_output[0]["x"], lane["x"])
    np.testing.assert_array_equal(reverse_output[0]["x"], lane["x"])


def test_scoring_is_prefix_invariant_and_reference_is_identical():
    first = _lane([[100.0], [200.0], [300.0]], [100.0, 200.0, 300.0])
    second = copy.deepcopy(first)
    second["source"]["windows"][2]["observed"]["rx0"] = [
        {"canonical_rx0_hz": 8_000.0}
    ]
    first_output, first_diagnostics = attach_orbit_increment([first])
    second_output, second_diagnostics = attach_orbit_increment([second])
    np.testing.assert_allclose(first_output[0]["signal"][:2], second_output[0]["signal"][:2])
    np.testing.assert_allclose(first_output[0]["reference"][:2], second_output[0]["reference"][:2])
    for index in (0, 1):
        assert (
            first_diagnostics[0]["receivers"][0]["windows"][index]["nominees"]
            == second_diagnostics[0]["receivers"][0]["windows"][index]["nominees"]
        )
    assert first_output[0]["signal"][2, 0, 0] != pytest.approx(
        second_output[0]["signal"][2, 0, 0]
    )
