import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.hard60_score import Hard60Objective, likelihood
from leo.application.hard60_runner import HARD60_SCORE, Hard60Configuration
from leo.contracts.regional_position import PositionObservations, PositionOrbitBank, RegionalPrior

SPEC = importlib.util.spec_from_file_location("adapter116", Path(__file__).with_name("adapter.py"))
A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(A)


def fixture():
    obs = PositionObservations(
        tuple(str(i) for i in range(8)),
        np.arange(8.0),
        np.arange(8.0) * 20,
        np.full(8, 11e9),
        np.arange(8) % 2,
        np.zeros(8, int),
        np.ones(8),
    )
    bank = PositionOrbitBank(
        np.array([30, 10, 40, 20]),
        np.array([-30.0, 30.0]),
        np.ones((4, 2, 3)) * 7000,
        np.ones((4, 2, 3)),
    )
    model = Hard60Objective(obs, bank.select([1, 3]), RegionalPrior(radius_km=50), HARD60_SCORE)
    vector = np.zeros(model.size)
    vector[2:8] = [3, 1, -4, -2, 0, 2]
    vector[8:] = 0.3
    return obs, bank, model, vector


def predictor(bank, obs, prior, point, shifts, **kwargs):
    prediction = np.broadcast_to(
        bank.numbers[None, :] * 3 + shifts[None, :] * 10, (len(obs.times_s), len(bank.numbers))
    ).copy()
    visible = (np.arange(len(obs.times_s))[:, None] + bank.numbers[None, :]) % 3 != 0
    return prediction, visible, None, None


def expected(model, vector, bank, shifts):
    p, v, _, _ = predictor(bank, model.observations, model.prior, vector[:2], shifts)
    p += (model.design @ vector[2:7] + model.baseline)[:, None]
    relative = model.basis @ vector[8:]
    penalty = 0.5 * (vector[7] / HARD60_SCORE.common_sigma_s) ** 2 + 0.5 * np.sum(
        (relative / HARD60_SCORE.relative_sigma_s) ** 2
    )
    return likelihood(model.observations.measured_hz, p, v, HARD60_SCORE).nll + penalty


@pytest.mark.parametrize("batch_size", [1, 3, 64])
def test_actual_model_composition_and_dense_parity(batch_size):
    _, bank, model, vector = fixture()
    original = expected(model, vector, model.bank, vector[7] + model.basis @ vector[8:])
    row = A.rescore(model, vector, bank, original, predictor=predictor, batch_size=batch_size)
    oracle = expected(model, vector, bank, row["transport"]["physical_shifts_s"])
    assert row["fixed"]["objective"] == pytest.approx(oracle, rel=0, abs=1e-10)
    assert row["native"]["objective"] == pytest.approx(original, rel=0, abs=1e-10)
    assert row["native"]["penalty"] == row["fixed"]["penalty"]


def test_binding_and_state_mismatch_fail_before_common_scoring():
    _, bank, model, vector = fixture()
    with pytest.raises(ValueError, match="did not reproduce"):
        A.rescore(model, vector, bank, 0, predictor=predictor)
    changed = PositionOrbitBank(
        bank.numbers, bank.nodes_s, bank.position_km + 1, bank.velocity_km_s
    )
    with pytest.raises(ValueError, match="states changed"):
        A.rescore(model, vector, changed, 0, predictor=predictor)


def test_point_adapter_shared_seeds_budget_and_locks():
    obs, bank, model, vector = fixture()
    vector[6] = 17.0
    calls, starts = [], []

    def bootstrap(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(satellite_indices=[1, 3], vector=vector.copy())

    def fitter(objective, start, **kwargs):
        starts.append((start.copy(), kwargs))
        if kwargs["rf_arm"] == "zero-c":
            start[6] = 0
        return SimpleNamespace(vector=start, objective=7.0, converged=False)

    def scorer(*args):
        return {mode: {"objective": 7.0} for mode in ("native", "fixed")}

    evaluate = A.PointEvaluator(
        obs, bank, model.prior, [], bootstrap=bootstrap, fitter=fitter, scorer=scorer
    )
    for arm in ("fitted-c", "zero-c"):
        first = evaluate(0, 0, arm)
        assert evaluate(0, 0, arm) is first
        assert first["fit"].vector[6] == (0 if arm == "zero-c" else 17)
    assert len(calls) == 1 and len(starts) == 2
    np.testing.assert_array_equal(starts[0][0], starts[1][0])
    for _, options in starts:
        assert options["maximum_seconds"] == 5 and options["maximum_iterations"] == 200
        assert options["fixed_position"] and options["slope_half_width_hz_s"] == 60


def test_zero_c_bad_fitter_rejected():
    obs, bank, model, vector = fixture()
    vector[6] = 17.0
    evaluate = A.PointEvaluator(
        obs,
        bank,
        model.prior,
        [],
        bootstrap=lambda *a, **k: SimpleNamespace(satellite_indices=[1, 3], vector=vector),
        fitter=lambda model, start, **k: SimpleNamespace(vector=start, objective=0),
    )
    with pytest.raises(ValueError, match="lock violated"):
        evaluate(0, 0, "zero-c")


def test_queue_intervention_uses_ordinary_centers_and_same_budget():
    calls = []

    def evaluate(e, n, arm):
        calls.append((e, n, arm))
        return {
            "scores": {
                "native": {"objective": (e - 30) ** 2 + n * n},
                "fixed": {"objective": (e + 30) ** 2 + n * n},
            }
        }

    result = A.search_pair(
        evaluate,
        RegionalPrior(radius_km=50),
        "zero-c",
        configuration=Hard60Configuration(point_budget=20),
    )
    a, b = [result[mode]["search"].evaluations for mode in ("native", "fixed")]
    assert len(a) == len(b) == 20
    assert [(p.east_km, p.north_km) for p in a if p.spacing_km == 40] == [
        (p.east_km, p.north_km) for p in b if p.spacing_km == 40
    ]
    assert {(p.east_km, p.north_km) for p in a} != {(p.east_km, p.north_km) for p in b}
    assert {row[2] for row in calls} == {"zero-c"}
