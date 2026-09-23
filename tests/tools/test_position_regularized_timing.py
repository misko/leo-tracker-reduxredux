import importlib.util
from pathlib import Path

import numpy as np


def _module():
    path = Path(__file__).parents[2] / "tools/research/position_regularized_timing.py"
    spec = importlib.util.spec_from_file_location("regularized_timing_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Prediction:
    def __init__(self, measured, predictions, training=(True, True, False, False)):
        self.measured_hz = np.asarray(measured, dtype=float)
        self.predictions_hz = np.asarray(predictions, dtype=float)
        self.training_mask = np.asarray(training, dtype=bool)
        self.visible = np.ones(self.predictions_hz.shape[0], dtype=bool)
        self.taus_s = np.array([-1.0, 0.0, 1.0])
        self.candidate_ids = np.array(["a", "b"])
        self.times_s = np.arange(len(measured), dtype=float)


def _predictions():
    observed = [0.0, 0.0, 50.0, 50.0]
    # Track one prefers tau -1; track two prefers tau +1 on training rows.
    return [
        Prediction(observed, [[[0, 0, 100, 100]] * 3, [[10, 10, 10, 10]] * 3]),
        Prediction(observed, [[[10, 10, 10, 10]] * 3, [[0, 0, 100, 100]] * 3]),
    ]


def test_zero_penalty_matches_independent_train_tau_argmins():
    module = _module()
    predictions = _predictions()
    answer = module.score_scan(predictions, 0.0)
    expected = [
        int(np.argmin([module.profile_track(p, j)["training_rms_hz"] for j in range(3)]))
        for p in predictions
    ]
    assert answer["choice_indices"] == expected


def test_hard_shared_forces_one_tau_per_scan():
    module = _module()
    answer = module.score_scan(_predictions(), 0.0, hard_shared=True)
    assert len(set(answer["choice_indices"])) == 1
    assert all(choice["tau_s"] == answer["clock_tau_s"] for choice in answer["choices"])


def test_train_inference_is_invariant_to_reserved_row_mutation():
    module = _module()
    first = _predictions()
    second = _predictions()
    for prediction in second:
        prediction.measured_hz[~prediction.training_mask] += 10000
    before = module.score_scan(first, 10_000.0)
    after = module.score_scan(second, 10_000.0)
    assert before["choice_indices"] == after["choice_indices"]
    assert before["clock_tau_s"] == after["clock_tau_s"]


def test_unmatched_track_does_not_pin_scan_clock_to_negative_limit():
    module = _module()
    matched = [
        {"training_rms_hz": 5.0},
        {"training_rms_hz": 4.0},
        {"training_rms_hz": 1.0},
    ]
    answer = module.scan_choices([matched, [None, None, None]], np.array([-1.0, 0.0, 1.0]), 1000.0)
    assert answer["clock_tau_s"] == 1.0


def test_validation_window_point_selection_ignores_poisoned_reserved_scores(monkeypatch):
    module = _module()

    def fake_rows(_joint, _index, _ids, _points, models):
        result = []
        for label, penalty, _ in models:
            result.extend(
                [
                    {
                        "label": label,
                        "penalty_hz2_per_s2": penalty,
                        "location_id": "train_best",
                        "latitude_deg": 1.0,
                        "longitude_deg": 1.0,
                        "training_capped_weighted_rms_hz": 1.0,
                        "reserved_capped_weighted_rms_hz": 9999.0,
                    },
                    {
                        "label": label,
                        "penalty_hz2_per_s2": penalty,
                        "location_id": "heldout_best",
                        "latitude_deg": 2.0,
                        "longitude_deg": 2.0,
                        "training_capped_weighted_rms_hz": 2.0,
                        "reserved_capped_weighted_rms_hz": 0.0,
                    },
                ]
            )
        return result

    monkeypatch.setattr(module, "_point_rows", fake_rows)

    class Joint:
        @staticmethod
        def haversine_km(a, b):
            return 0.0

    partition = {
        "duration_tiers": {
            tier: {"windows": []} for tier in ("single_300s", "about_1h", "about_3h", "about_8h")
        }
    }
    partition["duration_tiers"]["single_300s"]["windows"] = [
        {
            "window_id": "one",
            "session_ids": ["s"],
            "scan_count": 1,
            "summed_nominal_capture_seconds": 300,
            "elapsed_span_seconds": 300.0,
        }
    ]
    result = module._window_results(
        Joint(),
        {},
        partition,
        [],
        "lambda_1000",
        [("lambda_1000", 1000.0, False), ("lambda_0", 0.0, False)],
    )
    assert result["single_300s"][0]["selected_regularized"]["location_id"] == "train_best"


def test_sealed_replay_rejects_tampered_manifest_cache_or_locations():
    module = _module()
    bindings = {
        "dataset_manifest_sha256": "dataset",
        "locations_sha256": "locations",
        "cache_manifests": {"block_01": "cache"},
        "joint_source_sha256": "joint",
    }
    models = [("lambda_0", 0.0, False)]
    sealed = {"bindings": dict(bindings), "fixed_models": ["lambda_0"]}
    module._validate_sealed_inputs(sealed, bindings, models)
    for key, replacement in (
        ("dataset_manifest_sha256", "changed"),
        ("locations_sha256", "changed"),
        ("cache_manifests", {}),
    ):
        changed = dict(bindings)
        changed[key] = replacement
        try:
            module._validate_sealed_inputs(sealed, changed, models)
        except ValueError as error:
            assert key in str(error)
        else:
            raise AssertionError(f"tampered {key} was accepted")


def test_fixed_points_require_three_distinct_coordinates_and_ids():
    module = _module()
    points = [
        {"location_id": "a", "latitude_deg": 1.0, "longitude_deg": 1.0},
        {"location_id": "b", "latitude_deg": 2.0, "longitude_deg": 2.0},
        {"location_id": "c", "latitude_deg": 3.0, "longitude_deg": 3.0},
    ]
    module._validate_points(points)
    points[-1]["location_id"] = "a"
    try:
        module._validate_points(points)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate location ID was accepted")
