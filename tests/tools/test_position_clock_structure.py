import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np


def _module():
    path = Path(__file__).parents[2] / "tools/research/position_clock_structure.py"
    spec = importlib.util.spec_from_file_location("position_clock_structure", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _prediction(values, measured, mask):
    return SimpleNamespace(
        taus_s=np.asarray([-1.0, 0.0, 1.0]),
        predictions_hz=np.asarray(values, float),
        measured_hz=np.asarray(measured, float),
        training_mask=np.asarray(mask, bool),
        visible=np.asarray([True]),
        candidate_ids=np.asarray(["1"]),
        times_s=np.arange(len(measured), dtype=float),
    )


def test_selection_is_invariant_to_evaluation_frequency_mutation():
    module = _module()
    mask = [True, True, True, False, False, False]
    values = np.array([[[0, 1, 2, 3, 4, 5], [5, 6, 7, 8, 9, 10], [9, 10, 11, 12, 13, 14]]])
    original = _prediction(values, [0, 1, 2, 3, 4, 5], mask)
    changed = _prediction(values, [0, 1, 2, 1e8, -1e8, 1e8], mask)
    a = module.score_scan([original], "per_track_tau")
    b = module.score_scan([changed], "per_track_tau")
    assert a["choices"][0]["candidate_id"] == b["choices"][0]["candidate_id"]
    assert a["choices"][0]["tau_s"] == b["choices"][0]["tau_s"]
    assert a["training_capped_weighted_rms_hz"] == b["training_capped_weighted_rms_hz"]


def test_single_scan_clock_forces_one_tau_for_every_track():
    module = _module()
    mask = [True, True, True, False, False, False]
    first = _prediction(
        np.array([[[0, 1, 2, 3, 4, 5], [5, 6, 7, 8, 9, 10], [9, 10, 11, 12, 13, 14]]]),
        [0, 1, 2, 3, 4, 5],
        mask,
    )
    second = _prediction(
        np.array([[[9, 10, 11, 12, 13, 14], [5, 6, 7, 8, 9, 10], [0, 1, 2, 3, 4, 5]]]),
        [0, 1, 2, 3, 4, 5],
        mask,
    )
    result = module.score_scan([first, second], "single_tau_per_scan")
    assert len({row["tau_s"] for row in result["choices"]}) == 1


def test_location_selection_is_invariant_to_evaluation_mutation():
    module = _module()
    mask = [True, True, True, False, False, False]
    good = np.array([[[0, 1, 2, 3, 4, 5], [4, 5, 6, 7, 8, 9], [8, 9, 10, 11, 12, 13]]])
    worse = np.array([[[2, 3, 5, 7, 11, 13], [3, 5, 7, 11, 13, 17], [5, 7, 11, 13, 17, 19]]])
    original = [
        _prediction(good, [0, 1, 2, 3, 4, 5], mask),
        _prediction(worse, [0, 1, 2, 3, 4, 5], mask),
    ]
    changed = [
        _prediction(good, [0, 1, 2, 1e8, -1e8, 1e8], mask),
        _prediction(worse, [0, 1, 2, -1e8, 1e8, -1e8], mask),
    ]
    rows = []
    for location_id, prediction in zip(("a", "b"), original, strict=True):
        rows.append(
            {
                "location_id": location_id,
                "structure": "per_track_tau",
                **module.score_location([("s", [prediction])], "per_track_tau"),
            }
        )
    changed_rows = []
    for location_id, prediction in zip(("a", "b"), changed, strict=True):
        changed_rows.append(
            {
                "location_id": location_id,
                "structure": "per_track_tau",
                **module.score_location([("s", [prediction])], "per_track_tau"),
            }
        )
    assert (
        module.select_location(rows, "per_track_tau")["location_id"]
        == module.select_location(changed_rows, "per_track_tau")["location_id"]
    )
