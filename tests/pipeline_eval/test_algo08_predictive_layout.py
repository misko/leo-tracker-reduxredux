from collections import Counter
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3.predictive_linear import geometry_features, predictive_residual
from leo.analysis.localization_v3.region import SearchRegion
from tools.pipeline_eval.variants import algo08_predictive_layout as variant


@pytest.mark.parametrize("fitted", [False, True])
def test_prepared_predictive_geometry_replays_after_position_and_phase_moves(fitted):
    rng = np.random.default_rng(308)
    knots = np.arange(-10., 50., 0.5)
    times = np.linspace(0., 30., 27)
    norads = [58, 60]
    count = len(norads)
    position = rng.normal(size=(count, len(knots), 3)) * 30. + [6888., 100., 90.]
    velocity = rng.normal(size=position.shape) * 0.1 + [0., 7., 0.]
    modes = rng.normal(size=(count * 3, len(knots), 3))
    view = SimpleNamespace(
        scan=SimpleNamespace(search_region=SearchRegion((12., 28.))),
        variant="radio_noise", labels=norads, supported=[60], supported_local=[1],
        flat_labels=np.arange(len(times)) % 2, flat_times=times, reference=np.array([1.5, 1.7]),
        phase_sigma=np.array([2., 3.5]), q=np.linspace(0.9, 1.1, len(times)),
        sky=dict(time_s=knots, position_km=position, velocity_km_s=velocity),
        mode_bank=dict(time_s=knots, position_km=modes, velocity_km_s=modes * 0.1),
        hardware=rng.normal(size=(len(times), 8 + int(fitted))),
        smooth=rng.normal(size=(len(times), 12)), constants=np.zeros((len(times), 6)),
    )
    saved = variant.GeometryRows(view)
    for reference, point in ((1.5, (0., 0.)), (-2.0, (-3., 2.)), (-2.0, (12.5, -12.5))):
        view.reference[0] = reference
        actual = saved.evaluate(point)
        expected = geometry_features(view, point, 0.0)
        for name, actual_values in zip(("features", "intercept", "elevation"), actual, strict=True):
            assert actual_values.tobytes() == expected[name].tobytes(), name


@pytest.mark.parametrize("trim", [False, True])
def test_curved_gram_reuses_whole_or_masked_rows_and_checks_invalidation(trim):
    rng = np.random.default_rng(935308)
    count, width = 94, 26
    keep = np.ones(count, dtype=bool)
    if trim:
        keep[::4] = False
    problem = SimpleNamespace(keep=keep, noise_groups=np.arange(count) % 4,
                              point_noise=rng.uniform(40., 120., count))
    powers = np.array([0.5, 1., 0.8, 0.3])
    plan = variant.CurvedRows(problem, powers, width)
    for _ in range(3):
        result = dict(features=rng.normal(size=(count, width)),
                      noise_precision=rng.uniform(0.5, 3., 4),
                      coefficient_prior_precision=rng.uniform(0.2, 4., width))
        expected = variant.stock_gram(problem, powers, result)
        assert plan.gram(problem, powers, result).tobytes() == expected.tobytes()
    problem.point_noise[0] = np.nextafter(problem.point_noise[0], np.inf)
    assert plan.gram(problem, powers, result) is None


@pytest.mark.parametrize("groups_count", [1, 4])
def test_predictive_bias_noise_and_precision_reuse_keep_exact_residuals(groups_count):
    rng = np.random.default_rng(999)
    count, width = 17, 12
    groups = np.arange(count) % groups_count
    sigma = rng.uniform(40., 120., count)
    plan = variant.PredictiveRows(sigma, groups, width)
    for _ in range(3):
        design, raw = rng.normal(size=(count, width)), rng.normal(size=count)
        gram = np.eye(width) + design.T @ design
        expected = predictive_residual(raw, design, gram, sigma * np.sqrt(2), groups)
        actual = plan.residual(raw, design, gram)
        assert actual.keys() == expected.keys()
        for key, value in expected.items():
            if isinstance(value, str):
                assert actual[key] == value
            else:
                assert np.asarray(actual[key]).tobytes() == np.asarray(value).tobytes(), key


@pytest.mark.parametrize("events,max_bytes", [(1, 1024**2), (0, 1)])
def test_event_or_oversized_layout_uses_stock_components(events, max_bytes, monkeypatch):
    monkeypatch.setattr(variant, "MAX_SCRATCH_BYTES", max_bytes)
    problem = SimpleNamespace(keep=np.ones(7, dtype=bool))
    view = SimpleNamespace(
        variant="radio_noise", hardware=np.zeros((4, 8)), smooth=np.zeros((4, 6)),
        constants=np.zeros((4, 3)), labels=[1, 2], supported=[1],
    )
    stats = Counter()
    plan = variant.make_plan(
        problem, view, np.ones(1), np.full(4, 80.), np.zeros(4, dtype=int),
        np.zeros((4, events)), stats,
    )
    assert plan is None
    assert stats == {"unsupported_layouts": 1}
