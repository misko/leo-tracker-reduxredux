import importlib.util
from dataclasses import replace
from pathlib import Path

import numpy as np
from leo.analysis.shared_scan_model import SharedScanObjective

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('age_timing_model', HERE/'model.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
spec = importlib.util.spec_from_file_location('age_original_fixture',
    HERE.parents[1]/'2026_10_16_dsx01_iteration2/test_bank_expansion.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
case = fixture.case


def test_scalar2_exact_nesting_every_output_and_common_prior(case):
    ctx, _ = case
    model = module.RelativeTimingModel(ctx.model, 2.)
    original, details = ctx.model.evaluate_details(ctx.vector, ctx.nuisance)
    nested, same_details = model.evaluate_details(ctx.vector, ctx.nuisance)
    for a, b in zip(original[:3], nested[:3], strict=True):
        np.testing.assert_array_equal(a, b)
    assert nested[3] is not None and same_details.keys() == details.keys()
    np.testing.assert_array_equal(original[3].responsibilities, nested[3].responsibilities)
    assert model.score.common_sigma_s == 3.


def test_nonuniform_relative_gradient_and_unmodified_likelihood(case):
    ctx, _ = case
    model = module.RelativeTimingModel(ctx.model, [.5, 1., 1.5])
    result = model.evaluate_joint(ctx.vector, ctx.nuisance)
    base = ctx.model.evaluate_joint(ctx.vector, ctx.nuisance)
    assert result[3].nll == base[3].nll
    np.testing.assert_array_equal(result[3].responsibilities, base[3].responsibilities)
    np.testing.assert_array_equal(result[1][:8], base[1][:8])
    np.testing.assert_array_equal(result[2], base[2])
    for index in range(8, len(ctx.vector)):
        step = np.zeros_like(ctx.vector)
        step[index] = 1e-5
        fd = (model.evaluate_joint(ctx.vector+step, ctx.nuisance)[0]
              -model.evaluate_joint(ctx.vector-step, ctx.nuisance)[0])/2e-5
        np.testing.assert_allclose(fd, result[1][index], atol=2e-5, rtol=2e-5)
    # The added penalty is independent of the recording's common time shift.
    moved = ctx.vector.copy()
    moved[7] += .25
    difference = model.evaluate_joint(moved, ctx.nuisance)[0]-ctx.model.evaluate_joint(
        moved, ctx.nuisance)[0]
    np.testing.assert_allclose(difference, result[0]-base[0], atol=1e-12)


def test_weighted_profile_prior_recomputes_all_relative_offsets():
    tau = np.array([-12., 2., 5., 11.])
    proposed = np.array([.5, -3., 7., -1.])
    sigma = np.array([.5, 1., 1.5, 2.])
    def penalty(values):
        return .5*(values.mean()/3)**2+.5*np.sum(((values-values.mean())/sigma)**2)
    expected = []
    for index in range(4):
        changed = tau.copy()
        changed[index] = proposed[index]
        expected.append(penalty(changed)-penalty(tau))
    np.testing.assert_allclose(module.timing_penalty_delta(tau, proposed, sigma), expected,
                               atol=1e-12)
    np.testing.assert_array_equal(module.timing_penalty_delta(tau, proposed, np.full(4, 2.)),
        module.profile.timing_penalty_delta(tau, proposed, 3., 2.))


def test_exact_profile_columns_and_held_cfo_invariance(case):
    ctx, _ = case
    model = module.RelativeTimingModel(ctx.model, [.5, 1., 1.5])
    profile = module.Profiles(replace(ctx, model=model), ctx.vector, ctx.nuisance)
    proposed = profile.tau+np.array([.1, -.2, .3])
    scores = profile.score(proposed)
    for index in range(3):
        tau = profile.tau.copy()
        tau[index] = proposed[index]
        v = module.profile.timing_vector(model, ctx.vector, tau)
        np.testing.assert_allclose(scores[index], model.evaluate_joint(v, ctx.nuisance)[0],
                                   atol=1e-10, rtol=0)
    raw = object.__new__(type(ctx.model.original))
    raw.__dict__.update(ctx.model.original.__dict__)
    obs = ctx.model.original.observations
    raw.observations = replace(obs, measured_hz=obs.measured_hz+
                              np.where(ctx.train_mask, 0., 9876543.))
    changed = module.RelativeTimingModel(SharedScanObjective(raw,
        fixture.SequentialShift((0, 1), np.array([150., -250.])), ctx.train_mask), [.5, 1., 1.5])
    result = changed.evaluate_joint(ctx.vector, ctx.nuisance)
    original = model.evaluate_joint(ctx.vector, ctx.nuisance)
    for a, b in zip(original[:3], result[:3], strict=True):
        np.testing.assert_array_equal(a, b)
    changed_profile = module.Profiles(replace(ctx, model=changed), ctx.vector, ctx.nuisance)
    np.testing.assert_array_equal(changed_profile.score(proposed), scores)


def test_policy_minimum_unique_objects_and_unsupported_fallback():
    data = dict(age_bins=[dict(provider='space-track', lower_age_days=.5, upper_age_days=1,
        distinct_objects=100, count=200, mad_sigma_s=.775),
        dict(provider='space-track', lower_age_days=1, upper_age_days=2,
        distinct_objects=100, count=200, mad_sigma_s=8.),
        dict(provider='huggingface', lower_age_days=1, upper_age_days=2,
        distinct_objects=1, count=1, mad_sigma_s=0.)])
    sigma, status = module.widths('space-track', [-.1, .2, .75, 1.5, 3.], data)
    np.testing.assert_array_equal(sigma, [2, 2, .775, 2, 2])
    assert 'unsupported' in status[1]
    np.testing.assert_array_equal(module.widths('huggingface', [.75, 1.5], data)[0], [2, 2])
