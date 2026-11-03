"""Generic TRAIN-profile plus joint-band policy, charging every proposal call."""
from dataclasses import replace
from pathlib import Path
import sys
import time
import numpy as np
from numpy.testing import assert_allclose,assert_array_equal
from model import free_context,predict_joint
from leo.analysis.regional_position_score import circular

REPORTS=Path(__file__).resolve().parents[2]
sys.path.append(str(REPORTS/'2026_10_16_dsx01_models'))
sys.path.append(str(REPORTS/'2026_10_17_dsx01_iteration5'/'band_contrast_audit'))
from common import refit
from band_profile import BandProfiles,Grid


def fit_free(context,*,max_evaluations=1000,max_seconds=120,reused_profile=None,qualification_callback=None):
    begun=time.monotonic()
    if reused_profile is None:
        profile=BandProfiles(context,context.vector,context.nuisance,Grid(max_evaluations=min(200,max_evaluations-3),max_seconds=max_seconds)).fit()
        reused=False
    else:
        profile=reused_profile;reused=True
        assert_array_equal(profile['vector'],context.vector);assert_array_equal(profile['nuisance'],context.nuisance)
        assert_array_equal(profile['q'],context.model.hyperparameters(context.nuisance[context.model.base_nuisance_count:])[2])
        assert_array_equal(profile['total_timing_s'],context.vector[7]+context.model.basis@context.vector[8:])
    proposal_calls=int(profile['diagnostics']['evaluations'])
    charged_proposal_seconds=float(profile['diagnostics']['elapsed_seconds'])
    if proposal_calls+2>=max_evaluations:raise ValueError('Total allowance must include profile and two real qualification calls')
    changed=free_context(context,profile['absolute_offsets_hz'])
    original_n=changed.model.pack(context.nuisance)
    qualification_begun=time.monotonic()
    incumbent=changed.model.evaluate_joint(context.vector,original_n)
    seed,details=changed.model.evaluate_details(context.vector,changed.nuisance)
    assert_allclose(incumbent[0],profile['training_objective_before'],atol=1e-8,rtol=0)
    assert_allclose(seed[0],profile['training_objective'],atol=1e-8,rtol=0)
    assert_allclose(seed[3].nll,profile['training_nll'],atol=1e-8,rtol=0)
    training=context.model.scored_observations
    transport=predict_joint(changed,context.vector,changed.nuisance,training)
    predicted_residual=circular(training.measured_hz[:,None]-transport['prediction_hz'])
    assert_allclose(predicted_residual,seed[3].residual_hz,atol=1e-9,rtol=0)
    assert_array_equal(transport['detection_probability'],details['detection_probability'])
    qualifier_seconds=time.monotonic()-qualification_begun
    if qualification_callback is not None:
        qualification_callback(dict(passed=True,qualification_objective_calls=2,
            original_free_objective=float(incumbent[0]),original_frozen_objective=float(profile['training_objective_before']),
            profile_free_objective=float(seed[0]),profile_saved_objective=float(profile['training_objective']),
            prediction_transport_error_hz=float(np.max(abs(predicted_residual-seed[3].residual_hz))),
            original_nuisance_count=changed.model.original_nuisance_count,
            new_nuisance_count=len(changed.nuisance),band_scales=changed.model.group_scales[-changed.model.band_count:],
            band_limits=changed.model.group_limits[-changed.model.band_count:],held_cfo_read=False))
        qualifier_seconds=time.monotonic()-qualification_begun
    # Original incumbent remains an eligible point of the same free objective.
    if seed[0]>incumbent[0]+1e-9:
        changed=replace(changed,nuisance=original_n)
    remaining=max_evaluations-proposal_calls-2
    remaining_seconds=max_seconds-charged_proposal_seconds-qualifier_seconds
    if remaining_seconds<=0:raise TimeoutError('Profile/qualification exhausted whole policy allowance')
    changed=replace(changed,deadline=min(context.deadline,time.monotonic()+remaining_seconds))
    result=refit(changed,changed.vector,changed.nuisance,max_evaluations=remaining,
        max_seconds=remaining_seconds,fixed_c=context.fixed_c)
    if result['diagnostics']['objective']>incumbent[0]+1e-8:
        raise AssertionError('Original feasible free-model incumbent was lost')
    original_diagnostics=result['diagnostics'].copy()
    result['diagnostics'].update(refit_evaluations=original_diagnostics['evaluations'],
        profile_evaluations=proposal_calls,qualification_evaluations=2,
        evaluations=proposal_calls+2+original_diagnostics['evaluations'],
        refit_allocation=remaining,profile_reused=reused,
        profile_seconds_charged=charged_proposal_seconds,qualification_seconds=qualifier_seconds,
        elapsed_seconds=charged_proposal_seconds+qualifier_seconds+original_diagnostics['elapsed_seconds'],
        wall_seconds_this_call=time.monotonic()-begun,
        original_incumbent_objective=float(incumbent[0]),profile_seed_objective=float(seed[0]),
        real_profile_objective_qualification=True,train_prediction_transport_error_hz=float(np.max(abs(predicted_residual-seed[3].residual_hz))),
        profile_optimization_orbit_queries=profile['diagnostics'].get('optimization_orbit_queries',2),
        qualification_prediction_orbit_queries=1,
        domain='common.refit broad regional disk; original production extra25km disk not imposed',
        policy='TRAIN-only contrast profile plus joint continuation versus frozen-band continuation; not pure parameter-count causality')
    assert result['diagnostics']['evaluations']<=max_evaluations
    return result,changed,profile
