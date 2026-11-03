import importlib.util
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from leo.analysis.regional_position_score import observer
from leo.analysis.sequential_group_calibration import SequentialShift, fixed_shift_objective
from leo.analysis.shared_scan_model import SharedScanObjective
from leo.application.channel_group_refinement import objective
from leo.contracts.regional_position import PositionObservations, PositionOrbitBank, RegionalPrior

spec = importlib.util.spec_from_file_location('bank_expansion', Path(__file__).with_name(
    'bank_expansion.py'))
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


@dataclass
class Context:
    model: object
    full_model: object
    vector: np.ndarray
    nuisance: np.ndarray
    observations: object
    bank: object
    prior: object
    nodes: np.ndarray
    train_mask: np.ndarray
    fixed_c: bool = False


@pytest.fixture
def case():
    obs = PositionObservations(tuple(f'w{i}' for i in range(16)), np.arange(16.),
        np.linspace(-100, 100, 16), np.tile([11.5e9, 11.7e9], 8),
        np.tile([0, 0, 1, 1], 4), np.tile([1, 5, 2, 6], 4), np.ones(16))
    prior = RegionalPrior()
    site, up = observer(prior, [0, 0])
    times = np.arange(-21., 37.)
    positions = np.array([[site+(650+10*k)*up+np.array([.02*t, .1*k, 0.])
                           for t in times] for k in range(6)])
    velocities = np.tile([.02, 0., 0.], (6, len(times), 1))
    regional = PositionOrbitBank(np.arange(10, 16), times, positions, velocities)
    bank = regional.select([0, 1, 2])
    nodes = np.linspace(0, 15, 5)
    joint = objective(SimpleNamespace(observations=obs), bank, prior, nodes)
    shift = SequentialShift((0, 1), np.array([150., -250.]))
    raw = fixed_shift_objective(joint.base, shift)
    mask = np.arange(16) % 2 == 0
    model = SharedScanObjective(raw, shift, mask)
    v = np.r_[[1., 2., 10., .1, -20., -.2, 30.], .3, [.5, -.7]]
    n = model.initial_nuisance.copy()
    n[:model.clock_count] = np.linspace(-2, 2, model.clock_count)
    n[model.base_nuisance_count:] = [2., -2.]
    context = Context(model, SharedScanObjective(raw, shift), v, n, obs, bank, prior, nodes, mask)
    return context, regional


def test_exact_no_addition_and_complete_expansion_transport(case):
    ctx, regional = case
    unchanged, receipt = core.expandable_context(ctx, [], regional=regional)
    assert unchanged is ctx and receipt['objective_calls'] == 0
    expanded, receipt = core.expandable_context(ctx, [14, 13], regional=regional)
    np.testing.assert_array_equal(expanded.bank.numbers, [10, 11, 12, 13, 14])
    np.testing.assert_array_equal(expanded.vector[:7], ctx.vector[:7])
    np.testing.assert_array_equal(expanded.train_mask, ctx.train_mask)
    np.testing.assert_array_equal(expanded.nuisance[:ctx.model.base_nuisance_count],
                                  ctx.nuisance[:ctx.model.base_nuisance_count])
    old_tau = ctx.vector[7]+ctx.model.basis@ctx.vector[8:]
    np.testing.assert_allclose(expanded.vector[7]+expanded.model.basis@expanded.vector[8:],
                               np.r_[old_tau, [0, 0]], atol=1e-14)
    assert receipt['calibration_maximum_error_hz'] == 0
    assert receipt['original_satellite_timing_maximum_error_s'] < 1e-14
    assert expanded.model.fixed_contrast_prior_penalty == ctx.model.fixed_contrast_prior_penalty
    target = np.array(receipt['q_projection']['target_probabilities'])
    actual = expanded.model.hyperparameters(
        expanded.nuisance[expanded.model.base_nuisance_count:])[2]
    old = ctx.model.hyperparameters(ctx.nuisance[ctx.model.base_nuisance_count:])[2]
    np.testing.assert_allclose(target, np.r_[old*3/5, [1.6/5]*2])
    assert abs(actual.sum()-1.6) < 1e-12
    assert np.max(abs(expanded.nuisance[expanded.model.base_nuisance_count:])) <= 2+1e-12
    assert receipt['q_projection']['probability_maximum_error'] == pytest.approx(
        np.max(abs(actual-target)))
    # Genuine original equations execute on the preserved fold, not a fake fitter.
    result = expanded.model.evaluate_joint(expanded.vector, expanded.nuisance)
    assert np.isfinite(result[0]) and np.isfinite(result[1]).all()


def test_excluded_measurements_do_not_change_projection_or_training_objective(case):
    ctx, regional = case
    original, _ = core.expandable_context(ctx, [13], regional=regional)
    changed_obs = replace(ctx.observations, measured_hz=ctx.observations.measured_hz+
                          np.where(ctx.train_mask, 0., 9876543.))
    changed, _ = core.expandable_context(replace(ctx, observations=changed_obs),
                                        [13], regional=regional)
    np.testing.assert_array_equal(original.vector, changed.vector)
    np.testing.assert_array_equal(original.nuisance, changed.nuisance)
    a = original.model.evaluate_joint(original.vector, original.nuisance)
    b = changed.model.evaluate_joint(changed.vector, changed.nuisance)
    for x, y in zip(a[:3], b[:3], strict=True):
        np.testing.assert_array_equal(x, y)


@pytest.mark.parametrize('numbers', [[10], [13, 13], [999], [13.5], [True], list(range(20, 29))])
def test_invalid_or_ineligible_additions_fail(case, numbers):
    ctx, regional = case
    with pytest.raises(ValueError):
        core.expandable_context(ctx, numbers, regional=regional)


def test_changed_common_orbit_and_nonconstant_baseline_rejected(case):
    ctx, regional = case
    positions = regional.position_km.copy()
    positions[0, 0, 0] += 1e-6
    changed = PositionOrbitBank(regional.numbers, regional.nodes_s, positions,
                                regional.velocity_km_s)
    with pytest.raises(AssertionError):
        core.expandable_context(ctx, [13], regional=changed)
    ctx.model.original.baseline = ctx.model.original.baseline.copy()
    ctx.model.original.baseline[0] += 1
    with pytest.raises(AssertionError):
        core.expandable_context(ctx, [13], regional=regional)


def test_fixed_c_arm_and_projection_bounds(case):
    ctx, regional = case
    v = ctx.vector.copy()
    v[6] = 0
    expanded, receipt = core.expandable_context(replace(ctx, vector=v, fixed_c=True),
                                               [13, 14, 15], regional=regional)
    assert expanded.fixed_c and expanded.vector[6] == 0 and receipt['fixed_c']
    assert expanded.full_model.mask.all() and not expanded.model.mask.all()


def test_bounded_projection_branch_reports_loss_instead_of_clipping(case):
    ctx, regional = case
    expanded, _ = core.expandable_context(ctx, [13], regional=regional)
    # Explicit narrow synthetic projection bounds exercise the otherwise
    # inactive bounded-LS branch; no production model or fixture is changed.
    expanded.model.group_limits = np.full_like(expanded.model.group_limits, .1)
    tail, receipt = core.project_q(ctx.model, expanded.model,
        ctx.nuisance[ctx.model.base_nuisance_count:], 1)
    assert np.max(abs(tail)) <= .1+1e-12
    assert receipt['numerical_linear_projections'] == 1
    assert receipt['projection_active_coordinates']
    assert receipt['probability_maximum_error'] > 0
    assert abs(receipt['expanded_probability_mass']-1.6) < 1e-12
