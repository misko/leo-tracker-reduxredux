from types import SimpleNamespace

import models
import numpy as np
import pytest
from selection import MODEL_NAMES


class TinyData:
    def __init__(self):
        self.times = np.array([100.0, 101.0, 102.0, 103.0])
        self.measured = np.array([10.0, 12.0, 30.0, 31.0])
        self.rf = np.full(4, 11.2e9)
        self.receiver = np.array([0, 0, 1, 1])
        self.channel = np.array([0, 0, 1, 1])
        self.group = np.array([0, 0, 1, 2])
        self.margin = np.ones(4)
        self.numbers = np.arange(64) + 60000
        self.initial = np.zeros(70)
        self.tracks = [
            {
                "track_id": "left",
                "rows": np.array([0, 1]),
                "candidate_indices": np.arange(64),
            },
            {
                "track_id": "right",
                "rows": np.array([2, 3]),
                "candidate_indices": np.arange(64),
            },
        ]

    def predict(self, parameters, rows=None, satellites=None):
        parameters = np.asarray(parameters)
        full = np.tile(np.arange(64, dtype=float), (len(self.times), 1))
        full += parameters[0] * 0.1 + parameters[1] * 0.2
        full += parameters[2 + 2 * self.receiver, None]
        full += parameters[3 + 2 * self.receiver, None] * (self.times[:, None] - 150)
        full += parameters[6:][None, :] * 0.5
        visible = np.ones(full.shape, dtype=bool)
        if rows is None and satellites is None:
            return full, visible
        if (rows is None) != (satellites is None):
            raise ValueError("paired rows and satellites required")
        rows = np.asarray(rows, dtype=int)
        satellites = np.asarray(satellites, dtype=int)
        return full[rows, satellites], visible[rows, satellites]


def test_model_order_is_exactly_the_frozen_selection():
    assert models.MODEL_NAMES == MODEL_NAMES
    assert len(models.MODEL_NAMES) == 13


def test_group_assignment_uses_one_nearest_row_and_satellite_per_group():
    residual = np.array(
        [
            [20.0, 8.0],
            [3.0, 40.0],
            [np.inf, 5.0],
            [7.0, 2.0],
        ]
    )
    visible = np.isfinite(residual)
    rows, satellites, errors = models._best_group_assignments(
        residual, visible, np.array([4, 4, 9, 10])
    )
    np.testing.assert_array_equal(rows, [1, 2, 3])
    np.testing.assert_array_equal(satellites, [0, 1, 1])
    np.testing.assert_allclose(errors, [3.0, 5.0, 2.0])


def test_unmatched_loss_is_capped_at_2000_hz():
    assert models.rho(np.inf) == pytest.approx(models.rho(2000.0))
    assert models.rho(100000.0) == pytest.approx(models.rho(2000.0))


def test_data_contract_rejects_old_per_track_top_five_scope():
    data = TinyData()
    data.tracks[0]["candidate_indices"] = np.arange(5)
    with pytest.raises(ValueError, match="common 64-candidate pool"):
        models._validate_data(data)


def test_run_models_checkpoints_failures_and_continues(monkeypatch):
    data = TinyData()
    calls = []

    def dispatch(context, model_name, deadline):
        if model_name == "track_constant":
            raise RuntimeError("deliberate component failure")
        parameters = context.initial.copy()
        parameters[0] = len(calls)
        return {
            "parameters": parameters,
            "success": True,
            "status": "converged",
            "objective": 1.0,
            "free_parameters": ["east_km"],
            "assigned_groups": 1,
        }

    monkeypatch.setattr(models, "_dispatch", dispatch)

    def checkpoint(results):
        calls.append(tuple(results))

    results = models.run_models(data, checkpoint=checkpoint)
    assert tuple(results) == MODEL_NAMES
    assert len(calls) == len(MODEL_NAMES)
    assert results["track_constant"]["status"] == "error"
    assert results["track_constant"]["error"].endswith("deliberate component failure")
    assert results["track_linear"]["success"]
    assert all(len(receipt["parameters"]) == 70 for receipt in results.values())
    assert all(isinstance(receipt["free_parameters"], int) for receipt in results.values())


def test_independent_track_receipt_has_separate_nuisance_and_null_common_metric(monkeypatch):
    data = TinyData()
    arrays, numbers, initial, tracks = models._validate_data(data)
    context = models._Context(data, arrays, numbers, initial, tracks, float("inf"))
    selected = []
    for track_index, track in enumerate(tracks):
        rows = np.asarray(track["rows"])
        selected.append(
            {
                "track_id": track["track_id"],
                "track_index": track_index,
                "rows": rows,
                "satellite": track_index,
                "offset_hz": 100.0 + track_index,
                "alias_branch": None,
                "cost": 2.0,
                "errors": np.ones(len(rows)),
                "accepted": True,
            }
        )
    search = {
        "success": True,
        "status": "converged",
        "message": "synthetic",
        "objective": 2.0,
        "point": np.array([1.0, 2.0]),
        "details": (2.0, selected, {}),
        "grid_best": {"point": [0.0, 0.0], "objective": 3.0},
        "local_runs": [],
    }
    monkeypatch.setattr(models, "_search_position", lambda *args, **kwargs: search)
    receipt = models._track_receipt(context, "track_independent", float("inf"))
    assert len(receipt["parameters"]) == 70
    assert receipt["common_full_group_diagnostic"] is None
    assert [row["offset_hz"] for row in receipt["nuisance_parameters"]] == [100.0, 101.0]
    assert "older per-track top-five" in receipt["candidate_scope"]


def test_track_rows_are_globally_group_exclusive_before_fit():
    data = TinyData()
    data.group = np.array([0, 0, 0, 1])
    arrays, numbers, initial, tracks = models._validate_data(data)
    context = models._Context(data, arrays, numbers, initial, tracks, float("inf"))
    accounting = models._exclusive_track_rows(context)
    retained = np.concatenate(list(accounting["rows"].values()))
    assert len(retained) == len(np.unique(data.group[retained]))
    assert accounting["input_track_observations"] == 4
    assert accounting["modeled_track_observations"] == 2
    assert accounting["duplicate_track_group_rows"] == 2


@pytest.mark.parametrize("mode", ["independent", "constant", "linear"])
def test_track_models_are_invariant_to_per_observation_integer_alias_lifts(mode):
    original = TinyData()
    lifted = TinyData()
    lifted.measured = lifted.measured + np.array([3, -4, 2, 7]) * models.ALIAS_HZ

    def context(data):
        arrays, numbers, initial, tracks = models._validate_data(data)
        return models._Context(data, arrays, numbers, initial, tracks, float("inf"))

    original_fit = models._track_evaluate(context(original), np.array([0.0, 0.0]), mode)
    lifted_fit = models._track_evaluate(context(lifted), np.array([0.0, 0.0]), mode)
    assert lifted_fit[0] == pytest.approx(original_fit[0], rel=1e-9, abs=1e-5)
    assert [row["accepted"] for row in lifted_fit[1]] == [
        row["accepted"] for row in original_fit[1]
    ]
    assert [row["cost"] for row in lifted_fit[1]] == pytest.approx(
        [row["cost"] for row in original_fit[1]], rel=1e-9, abs=1e-5
    )


def test_checkpoint_exception_propagates(monkeypatch):
    data = TinyData()

    def dispatch(context, model_name, deadline):
        return {
            "parameters": context.initial,
            "success": True,
            "status": "converged",
            "objective": 0.0,
            "free_parameters": [],
            "assigned_groups": 0,
        }

    monkeypatch.setattr(models, "_dispatch", dispatch)

    def checkpoint(_results):
        raise OSError("cannot persist")

    with pytest.raises(OSError, match="cannot persist"):
        models.run_models(data, checkpoint=checkpoint)


def test_failure_receipt_keeps_none_objective_and_attempted_flag():
    data = TinyData()
    arrays, numbers, initial, tracks = models._validate_data(data)
    context = models._Context(data, arrays, numbers, initial, tracks, float("inf"))
    receipt = models._failure_receipt(
        context, "glrt_fixed_8", "error", RuntimeError("synthetic failure")
    )
    receipt["attempted"] = True
    normalized = models._normalize_receipt("glrt_fixed_8", receipt, 0.25)
    assert normalized["objective"] is None
    assert normalized["attempted"] is True
    assert normalized["success"] is False


def test_budget_skip_can_be_marked_unattempted():
    data = TinyData()
    arrays, numbers, initial, tracks = models._validate_data(data)
    context = models._Context(data, arrays, numbers, initial, tracks, float("inf"))
    receipt = models._failure_receipt(
        context, "anchors", "limit_reached", models._LimitReached("not started")
    )
    receipt["attempted"] = False
    normalized = models._normalize_receipt("anchors", receipt, 0.0)
    assert normalized["attempted"] is False
    assert normalized["status"] == "limit_reached"


def test_deadline_data_interrupts_numerical_predict(monkeypatch):
    data = TinyData()
    monkeypatch.setattr(models.time, "monotonic", lambda: 2.0)
    bounded = models._DeadlineData(data, 1.0)
    with pytest.raises(models._LimitReached, match="budget"):
        bounded.predict(data.initial)


def test_existing_coherent_components_load_without_scipy_import():
    anchors, association, refinement = models._coherent_modules()
    assert callable(anchors.select_anchors)
    assert callable(association.associate)
    assert callable(refinement.fit_fixed)


def test_position_search_converges_from_ranked_grid_not_distant_prior():
    visited = []

    def evaluate(point):
        visited.append(np.asarray(point).copy())
        return float(np.sum((np.asarray(point) - [-83.2, -79.7]) ** 2)), {"point": point}

    result = models._search_position(evaluate, [0, 0], float("inf"))
    assert result["success"]
    np.testing.assert_allclose(result["point"], [-83.2, -79.7], atol=0.02)
    assert result["local_runs"][0]["seed"] == [-100.0, -100.0]


def test_failed_search_preserves_better_local_attempt():
    def evaluate(point):
        return float(np.sum((np.asarray(point) - [-83.2, -79.7]) ** 2)), {}

    result = models._search_position(evaluate, [0, 0], float("inf"), maxfev=12)
    assert not result["success"]
    assert result["objective"] < result["grid_best"]["objective"]


def test_timing_receipt_uses_returned_optimum_not_last_trial(monkeypatch):
    import scipy.optimize

    data = TinyData()
    arrays, numbers, initial, tracks = models._validate_data(data)
    context = models._Context(data, arrays, numbers, initial, tracks, float("inf"))

    def minimize(function, vector, **kwargs):
        rejected = vector.copy()
        rejected[0] = 40.0
        function(rejected)
        return SimpleNamespace(
            x=vector, fun=0.0, success=True, status=0, message="test", nit=1, nfev=2
        )

    monkeypatch.setattr(scipy.optimize, "minimize", minimize)
    receipt = models._timing_receipt(context, "glrt_timing_3s", float("inf"))
    np.testing.assert_array_equal(receipt["parameters"][:2], [0, 0])


def test_batched_timing_derivative_matches_objective_finite_differences():
    data = TinyData()
    data.measured += np.array([0.17, 0.31, -0.21, 0.42])
    arrays, numbers, initial, tracks = models._validate_data(data)
    context = models._Context(data, arrays, numbers, initial, tracks, float("inf"))
    objective = models._TimingObjective(context, initial, 1.0, 3.0, float("inf"))
    vector = np.r_[0.37, -0.11, np.linspace(-0.01, 0.01, 64)]
    _, gradient = objective.evaluate(vector)
    for index in (0, 1, 12, 32, 33, 65):
        plus, minus = vector.copy(), vector.copy()
        plus[index] += 1e-4
        minus[index] -= 1e-4
        numeric = (objective.evaluate(plus)[0] - objective.evaluate(minus)[0]) / 2e-4
        assert gradient[index] == pytest.approx(numeric, rel=1e-3, abs=1e-7)


def test_free_glrt_profiles_from_downstream_rx_seed(monkeypatch):
    data = TinyData()
    arrays, numbers, initial, tracks = models._validate_data(data)
    context = models._Context(data, arrays, numbers, initial, tracks, float("inf"))
    downstream = initial.copy()
    downstream[2:6] = [123, 2, -321, -3]
    monkeypatch.setattr(context, "downstream_initial", lambda: (downstream, "test seed"))
    seeds = []

    def profile(context, base, visible, count, receiver, seed):
        seeds.append(seed.copy())
        return seed

    monkeypatch.setattr(models, "_profile_receiver_glrt", profile)
    models._glrt_receipt(context, "glrt_free_16", float("inf"))
    np.testing.assert_array_equal(seeds[0], downstream[2:4])
    np.testing.assert_array_equal(seeds[1], downstream[4:6])


def test_glrt_seed_histogram_excludes_invisible_candidates(monkeypatch):
    data = TinyData()
    arrays, numbers, initial, tracks = models._validate_data(data)
    context = models._Context(data, arrays, numbers, initial, tracks, float("inf"))
    base = np.zeros((4, 64))
    visible = np.zeros((4, 64), dtype=bool)
    visible[0, 0] = True
    values = []
    histogram = np.histogram

    def record(values_in, **kwargs):
        values.extend(values_in.tolist())
        return histogram(values_in, **kwargs)

    monkeypatch.setattr(np, "histogram", record)
    models._profile_receiver_glrt(context, base, visible, 16, 0, np.zeros(2))
    assert values == [10.0]


def test_timing_10s_includes_successful_3s_warm_start(monkeypatch):
    import scipy.optimize

    data = TinyData()
    arrays, numbers, initial, tracks = models._validate_data(data)
    context = models._Context(data, arrays, numbers, initial, tracks, float("inf"))
    warm = initial.copy()
    warm[:2] = [2, 3]
    warm[6:] = 0.4
    context.results["glrt_timing_3s"] = {"success": True, "parameters": warm}
    seeds = []

    def minimize(function, vector, **kwargs):
        seeds.append(vector.copy())
        return SimpleNamespace(
            x=vector,
            fun=function(vector)[0],
            success=True,
            status=0,
            message="test",
            nit=1,
            nfev=1,
        )

    monkeypatch.setattr(scipy.optimize, "minimize", minimize)
    receipt = models._timing_receipt(context, "glrt_timing_10s", float("inf"))
    np.testing.assert_array_equal(seeds[0], np.r_[warm[:2], warm[6:]])
    np.testing.assert_array_equal(seeds[1][2:], np.zeros(64))
    assert receipt["optimizer_runs"][0]["seed_kind"] == "successful glrt_timing_3s"
