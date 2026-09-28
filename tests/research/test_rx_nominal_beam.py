import copy
from types import SimpleNamespace

import numpy as np
import pytest

import tools.rx_nominal_beam as module
from tools.rx_nominal_beam import beam_features, fit_beam_arms, fit_shared_beam_scale


def _lane(up=(0.0, 2.0, 4.0), east=(-1.0, 1.0, 3.0), nominees=2):
    windows = []
    roles = np.asarray(["reception", "reception", "held_frequency"])
    for window_index in range(3):
        predictions = []
        for nominee in range(nominees):
            predictions.append(
                {
                    "track_id": f"t{nominee}",
                    "catalog_number": nominee,
                    "los_enu_unit": {
                        "east": east[window_index] + nominee,
                        "north": 0.0,
                        "up": up[window_index] + nominee,
                    },
                }
            )
        windows.append(
            {
                "source_window_id": f"w{window_index}",
                "role": str(roles[window_index]),
                "predictions": predictions,
                "observed": {"rx0": [], "rx1": []},
            }
        )
    x = np.zeros((3, nominees, 2, 8))
    x[..., 0] = 1.0
    x[..., 1] = [-1.0, 1.0]
    x[..., 2] = 0.25
    return {
        "source": {"windows": windows},
        "indices": [0, 1, 2],
        "x": x,
        "roles": roles,
        "signal": np.ones((3, nominees, 2)),
        "reference": np.arange(3.0),
        "visible": np.ones((3, nominees), dtype=bool),
        "prior": np.full(nominees, -np.log(nominees)),
    }


def test_zero_tilt_is_receiver_identical_and_twenty_degree_sign_is_physical():
    lane = _lane(up=(0.0, 0.0, 0.0))
    zero = beam_features([lane], 1.0, tilt_deg=0.0)[0]["x"][..., 3]
    np.testing.assert_array_equal(zero[..., 0], zero[..., 1])
    tilted = beam_features([lane], 1.0, tilt_deg=20.0)[0]["x"][..., 3]
    assert tilted[1, 0, 1] - tilted[1, 0, 0] > 0


def test_shared_scale_uses_reception_centered_raw_up_and_floor():
    lane = _lane(up=(0.0, 2.0, 4.0), nominees=1)
    expected = np.sqrt(np.mean(np.asarray([-1.0, 1.0]) ** 2))
    assert fit_shared_beam_scale([lane]) == pytest.approx(expected)
    changed = copy.deepcopy(lane)
    changed["source"]["windows"][2]["predictions"][0]["los_enu_unit"]["up"] = 1_000.0
    assert fit_shared_beam_scale([changed]) == pytest.approx(expected)
    assert fit_shared_beam_scale([_lane(up=(2.0, 2.0, 2.0), nominees=1)]) == 1.0


def test_reception_mean_does_not_read_held_geometry_or_outcomes():
    original = _lane()
    changed = copy.deepcopy(original)
    changed["source"]["windows"][2]["predictions"][0]["los_enu_unit"]["up"] = 100.0
    changed["source"]["windows"][2]["observed"]["rx0"] = [{"anything": "outcome"}]
    first = beam_features([original], 2.0)[0]
    second = beam_features([changed], 2.0)[0]
    np.testing.assert_array_equal(first["x"][:2, ..., 3], second["x"][:2, ..., 3])
    assert first["x"][2, 0, 0, 3] != second["x"][2, 0, 0, 3]


def test_controls_change_only_beam_geometry_and_preserve_other_lane_arrays():
    lane = _lane()
    base = beam_features([lane], 2.0)[0]
    swap = beam_features([lane], 2.0, control="swap")[0]
    reverse = beam_features([lane], 2.0, control="geometryreverse")[0]
    permute = beam_features([lane], 2.0, control="geometrypermute")[0]
    np.testing.assert_array_equal(swap["x"][..., :3], lane["x"][..., :3])
    np.testing.assert_array_equal(base["x"][..., 4:8], 0.0)
    np.testing.assert_array_equal(swap["signal"], lane["signal"])
    np.testing.assert_array_equal(reverse["reference"], lane["reference"])
    np.testing.assert_array_equal(permute["visible"], lane["visible"])
    np.testing.assert_array_equal(swap["x"][..., 3,], base["x"][..., 3][..., ::-1])
    reception = np.flatnonzero(lane["roles"] == "reception")
    np.testing.assert_array_equal(
        reverse["x"][reception, ..., 3], base["x"][reception[::-1], ..., 3]
    )
    np.testing.assert_array_equal(permute["x"][..., 3], np.roll(base["x"][..., 3], 1, axis=1))


def test_fitter_uses_monotone_slope_bounds_and_independent_d_nesting(monkeypatch):
    calls = []

    def fake_score(lanes, beta, occupancy, tau):
        return 2.0

    def fake_minimize(objective, start, args, method, bounds, options):
        calls.append({"start": np.asarray(start).copy(), "bounds": bounds, "args": args})
        return SimpleNamespace(
            x=np.asarray(start).copy(),
            success=True,
            message="ok",
            nit=1,
            nfev=1,
            fun=-1.0,
        )

    monkeypatch.setattr(module, "calibration_score", fake_score)
    monkeypatch.setattr(module, "minimize", fake_minimize)
    result = fit_beam_arms([{"family": "E"}], [{"family": "B"}])
    assert len(calls) == 6
    assert calls[2]["bounds"][3] == (0.0, 12.0)
    assert calls[4]["bounds"][3] == (0.0, 12.0)
    np.testing.assert_array_equal(calls[3]["start"], calls[5]["start"])
    assert calls[2]["args"][0] == [{"family": "E"}]
    assert calls[4]["args"][0] == [{"family": "B"}]
    assert set(result["fits"]) == {"D", "E", "B"}


def test_nonpositive_map_gain_selects_exact_nested_null(monkeypatch):
    monkeypatch.setattr(module, "calibration_score", lambda *args: 0.0)

    def fake_minimize(*args, **kwargs):
        start = np.asarray(args[1])
        return SimpleNamespace(x=start, success=True, message="ok", nit=1, nfev=1, fun=1.0)

    monkeypatch.setattr(module, "minimize", fake_minimize)
    result = fit_beam_arms([{}], [{}])
    for arm, dimension in module.ARMS.items():
        selected = result["fits"][arm]["selected"]
        assert selected["null_selected"] is True
        assert selected["beta"] == [0.0] * dimension
        assert selected["occupancy"] == 0.0
