"""At most12 direct TRAIN objective checks; no optimization or held scoring."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import time
import unittest
import numpy as np
from numpy.testing import assert_allclose,assert_array_equal
from timing_profiles import from_context,timing_vector

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parents[1]
JOINT=REPORTS/'2026_10_17_dsx01_iteration5/joint_band_contrast'
BLOCKED=REPORTS/'2026_10_17_dsx01_iteration5/blocked_cold'
sys.path.insert(0,str(JOINT));sys.path.append(str(BLOCKED))
from model import free_context
from training_context import load_training_context
from leo.application.shared_fast_position import plain


def digest(path):return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def save(path,value):
    with Path(path).open('x') as stream:json.dump(plain(value),stream,indent=2,allow_nan=False);stream.write('\n')


def qualify():
    begun=time.monotonic();deadline=begun+120
    if (HERE/'protocol.json').exists():raise FileExistsError('Qualification already declared; no silent retry')
    files=[HERE/'timing_profiles.py',HERE/'test_timing_profiles.py',HERE/'qualify.py',
        JOINT/'model.py',JOINT/'fit.py',JOINT/'code-handoff.json',JOINT/'manifest.json',
        JOINT/'fit-free-fitted-c.json',JOINT/'fit-free-zero-c.json',BLOCKED/'training_context.py',
        BLOCKED/'S03-block20-parity0/training-input.json',BLOCKED/'S03-block20-parity0/derivation.json']
    save(HERE/'protocol.json',dict(purpose='Qualification of exact complete-residual timing adapter; no optimization/search/proposals',
        source='Existing TRAIN-only blocked public-pipeline context and already frozen joint-band endpoints',
        arms=['fitted-c','zero-c'],maximum_direct_objective_checks=12,maximum_seconds=120,
        checks_per_arm='1 current objective construction+5 direct single-coordinate trials;2 distinct trial vectors each profile scores every bank column',
        index_policy='Deterministic bank-order indices0,K//2,K-1,K//3,2K//3; no candidate/window identity selection',
        timing_policy='Trial vectors clip(tau+.375,-19.5,19.5) and clip(tau-.625,-19.5,19.5); allother model coordinates fixed',
        prior='Unchanged common3s/zero-sum relative2s; absolute band/clock/q/other priors carried once from complete current objective',
        exclusions='No held scoring, station/reference position read, refit, q update, discovery or model/old-report mutation',
        profile_cost='Each paired orbital prediction/elevation projection and every vectorized coordinate comparison reported separately; no optimization budget implied',
        source_sha256={str(p):digest(p) for p in files}))
    import test_timing_profiles
    tests=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(test_timing_profiles))
    if not tests.wasSuccessful():raise AssertionError('Component tests failed')
    for item in read(JOINT/'manifest.json')['files']:assert digest(JOINT/item['path'])==item['sha256']
    context=load_training_context();assert context.train_mask.all()
    original_v=context.vector.copy();original_n=context.nuisance.copy();checks=[];profiles=[];calls=0
    def remaining():
        if time.monotonic()>=deadline:raise TimeoutError('Qualification120s deadline')
    for arm in ['fitted-c','zero-c']:
        remaining();frozen=read(JOINT/f'fit-free-{arm}.json')
        v=np.array(frozen['vector']);n=np.array(frozen['nuisance']);ctx=free_context(replace(context,fixed_c=arm=='zero-c'))
        if arm=='zero-c':assert v[6]==0.
        profile=from_context(ctx,v,n);calls+=profile.construction_objective_calls
        assert_allclose(profile.initial_objective,frozen['diagnostics']['objective'],atol=1e-9,rtol=0)
        # Nesting at the current full timing state is an array/projection check,
        # not another model objective evaluation.
        nested=profile.score(profile.tau)
        assert_allclose(nested,profile.initial_objective,atol=1e-7,rtol=0)
        candidates=[np.clip(profile.tau+.375,-19.5,19.5),np.clip(profile.tau-.625,-19.5,19.5)]
        scores=[profile.score(t) for t in candidates];k=len(profile.tau)
        for trial,column in [(0,0),(0,k//2),(0,k-1),(1,k//3),(1,2*k//3)]:
            remaining();single=profile.tau.copy();single[column]=candidates[trial][column]
            vv=timing_vector(v,ctx.model.basis,single)
            direct=ctx.model.evaluate_joint(vv,n);calls+=1
            error=float(scores[trial][column]-direct[0])
            assert_allclose(scores[trial][column],direct[0],atol=1e-7,rtol=0)
            checks.append(dict(arm=arm,trial=trial,column=column,old_timing_s=profile.tau[column],
                proposed_timing_s=single[column],profile_objective=scores[trial][column],direct_objective=direct[0],error=error))
        profiles.append(dict(arm=arm,training_observations=len(profile.residual_hz),candidates=k,
            unchanged_prior=[ctx.model.score.common_sigma_s,ctx.model.score.relative_sigma_s],
            absolute_band_offsets_hz=n[-ctx.model.band_count:],complete_nuisance_dimension=len(n),
            construction_objective_calls=profile.construction_objective_calls,
            construction_projection_calls=profile.construction_projection_calls,projection_calls=profile.projection_calls,
            coordinate_comparisons=profile.coordinate_comparisons,
            current_timing_nesting_error=float(np.max(abs(nested-profile.initial_objective)))))
    remaining();assert calls==12
    assert_array_equal(context.vector,original_v);assert_array_equal(context.nuisance,original_n)
    save(HERE/'qualification.json',dict(passed=True,component_tests=tests.testsRun,direct_objective_checks=calls,
        max_direct_objective_checks=12,paired_orbit_projection_calls=sum(p['construction_projection_calls']+p['projection_calls'] for p in profiles),
        vectorized_coordinate_comparisons=sum(p['coordinate_comparisons'] for p in profiles),
        max_objective_error=max(abs(c['error']) for c in checks),checks=checks,profiles=profiles,
        train_seed_unmodified=True,optimization_or_refit_calls=0,held_cfo_scored=False,reference_position_read=False,
        elapsed_seconds=time.monotonic()-begun,protocol_sha256=digest(HERE/'protocol.json')))
    print(json.dumps(dict(passed=True,direct_objective_checks=calls,max_objective_error=max(abs(c['error']) for c in checks),
        elapsed_seconds=time.monotonic()-begun,optimization_or_refit_calls=0)),flush=True)


if __name__=='__main__':qualify()
