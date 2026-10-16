from types import SimpleNamespace

import numpy as np
import pytest

from leo.application import channel_group_refinement as module


def test_refinement_factory_keeps_declared_frequency_port_explicit(monkeypatch):
    seen = []
    port = object()
    monkeypatch.setattr(module, "Hard60Objective", lambda *_: object())

    def clock(base, nodes, knots, scale, **kwargs):
        seen.append(kwargs["likelihood_port"])
        return base

    monkeypatch.setattr(module, "JointClockObjective", clock)
    monkeypatch.setattr(module, "GroupCalibrationObjective", lambda base, *_args, **_kwargs: base)
    inputs = SimpleNamespace(observations=SimpleNamespace(channel=np.array([1, 5])))
    module.objective(inputs, None, None, np.array([0.0, 30.0]), likelihood_port=port)
    assert seen == [port]
    with pytest.raises(ValueError, match="explicit joint clock"):
        module.objective(inputs, None, None, None, common_clock=False, likelihood_port=port)


@pytest.mark.parametrize("full_pool", [False, True])
@pytest.mark.parametrize("preserve_starts", [False, True])
def test_refinement_matches_candidates_starts_budgets_and_does_not_select_on_held(
    monkeypatch, full_pool, preserve_starts
):
    rows = [
        dict(east_km=east, north_km=0.0, satellite_indices=indices)
        for east, indices in ((0.0, [0, 1]), (25.0, [1, 2]), (50.0, [0, 2]))
    ]
    prepared = {view: SimpleNamespace(view=view) for view in ("low", "high", "all")}
    held = {view: object() for view in prepared}
    banks, fits, predictions = [], [], []
    bank = SimpleNamespace(numbers=np.array([1001, 1002, 1003, 1004]))
    expected = [0, 1, 2, 3] if full_pool else [0, 1, 2]

    def select(indices):
        assert indices == expected
        return SimpleNamespace(numbers=bank.numbers[indices])

    bank.select = select

    def objective(inputs, selected_bank, prior, nodes, **kwargs):
        banks.append((inputs.view, tuple(selected_bank.numbers)))
        return SimpleNamespace(view=inputs.view)

    def seed(row, *_, **kwargs):
        assert kwargs["nearest_timings"] == full_pool
        return dict(vector=np.array([row["east_km"], 0.0]), nuisance=np.array([]))

    def fit(model, vector, nuisance, **kwargs):
        assert kwargs["seconds"] == 45 and kwargs["iterations"] == 600
        assert kwargs["local_radius_km"] == 25
        np.testing.assert_array_equal(kwargs["local_center"], vector)
        fits.append((model.view, kwargs["arm"], vector[0]))
        return dict(vector=vector, converged=True, objective=float(vector[0] ** 2))

    def predict(state, held_observations, *_):
        assert any(held_observations is value for value in held.values())
        predictions.append(state)
        # Held score would prefer the last initialization; it must not select.
        return dict(frequency_nll=-float(state[0]))

    monkeypatch.setattr(module, "objective", objective)
    monkeypatch.setattr(module, "carried_seed", seed)
    monkeypatch.setattr(module, "fit_group_calibration", fit)
    monkeypatch.setattr(module, "freeze_group_calibration", lambda *_: None)
    monkeypatch.setattr(module, "freeze_group_position", lambda bank, fit, _: fit["vector"])
    monkeypatch.setattr(module, "score_frozen_group_position", predict)
    cache = {}
    port = SimpleNamespace(get=cache.get, put=lambda key, result: cache.update({key: result}))
    result = module.refine_channel_groups(
        dict(available=True, selected=rows),
        prepared,
        held,
        bank,
        None,
        None,
        port,
        training_rows=rows + [dict(east_km=75.0, north_km=0.0, satellite_indices=[2, 3])]
        if full_pool
        else None,
        extra_starts=rows if preserve_starts else (),
    )
    assert len(fits) == (72 if preserve_starts else 36) and len(predictions) == 12
    assert result["starts"] == (6 if preserve_starts else 3)
    assert all(numbers == tuple(bank.numbers[expected]) for _, numbers in banks)
    for models in result["results"].values():
        for view in models.values():
            assert all(row["start"] == 0 for row in view["selected"].values())
    module.refine_channel_groups(
        dict(available=True, selected=rows),
        prepared,
        held,
        bank,
        None,
        None,
        port,
        training_rows=rows + [dict(east_km=75.0, north_km=0.0, satellite_indices=[2, 3])]
        if full_pool
        else None,
        extra_starts=rows if preserve_starts else (),
    )
    assert len(fits) == (72 if preserve_starts else 36)


def test_unsealed_or_incomplete_discovery_cannot_enter_refinement():
    with pytest.raises(ValueError, match="sealed"):
        module.refine_channel_groups(
            dict(available=False, selected=[]), {}, {}, None, None, None, None
        )


def test_carried_seed_transports_function_and_keeps_declared_timing_priority():
    from leo.analysis.regional_position_score import zero_sum_basis
    from leo.contracts.regional_position import PositionObservations, RegionalPrior

    channels = np.array([1, 1, 2, 2, 7, 7, 8, 8] * 4)
    inputs = SimpleNamespace(
        observations=PositionObservations(
            tuple(map(str, range(32))),
            np.linspace(0, 150, 32),
            np.zeros(32),
            10.5e9 + channels * 250e6,
            np.arange(32) % 2,
            channels,
            np.ones(32),
        )
    )
    prepared = {"all": inputs}
    bank = SimpleNamespace(numbers=np.array([1001, 1002, 1003]))
    bank.select = lambda indices: SimpleNamespace(numbers=bank.numbers[indices])
    prior = RegionalPrior()
    nodes = np.arange(0.0, 151.0, 30.0)
    rows = []
    for indices, shifts in (([0, 1], [1.0, 2.0]), ([1, 2], [9.0, 3.0])):
        vector = np.r_[
            4.0,
            5.0,
            100.0,
            2.0,
            200.0,
            3.0,
            -500.0,
            np.mean(shifts),
            zero_sum_basis(2).T @ (np.array(shifts) - np.mean(shifts)),
        ]
        rows.append(
            dict(
                east_km=4.0,
                north_km=5.0,
                satellite_indices=indices,
                fits={
                    "all": dict(
                        vector=vector, nuisance=np.array([-24000.0, 38000.0]), converged=True
                    )
                },
            )
        )
    model = module.objective(inputs, bank, prior, nodes, common_clock=False)
    seed = module.carried_seed(rows[0], rows, model, prepared, bank, prior, nodes, False)
    physical = seed["vector"][7] + model.basis @ seed["vector"][8:]
    # Candidate 1002 retains this point's timing, not the other start's 9 s.
    np.testing.assert_allclose(physical, [1.0, 2.0, 3.0], atol=1e-12)
    source_model = module.objective(inputs, bank.select([0, 1]), prior, nodes, common_clock=False)
    np.testing.assert_allclose(
        model.correction(seed["vector"], seed["nuisance"]),
        source_model.correction(
            rows[0]["fits"]["all"]["vector"], rows[0]["fits"]["all"]["nuisance"]
        ),
        atol=1e-7,
    )
