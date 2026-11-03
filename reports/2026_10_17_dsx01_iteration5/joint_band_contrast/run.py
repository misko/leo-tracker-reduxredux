"""Bounded blocked-cold pilot; persist all TRAIN endpoints before held scoring."""
from dataclasses import replace
import csv
import hashlib
import json
from pathlib import Path
import sys
import time
import unittest
import numpy as np
from numpy.testing import assert_allclose,assert_array_equal
from fit import fit_free
from model import free_context,predict_joint

HERE=Path(__file__).resolve().parent
ITER=HERE.parent
REPORTS=ITER.parent
BLOCKED=ITER/'blocked_cold'
ATTEMPT=BLOCKED/'S03-block20-parity0'
PROFILE=ITER/'band_contrast_audit'
CONTROL=ITER/'age_timing'
DATA=REPORTS/'2026_10_16_dsx01_fast_association_losses'
sys.path.append(str(BLOCKED))
from training_context import load_training_context,predict_original
from common import endpoint_status
from leo.application.shared_fast_position import plain
from leo.analysis.shared_scan_model import density
from leo.contracts.regional_position import PositionObservations


def digest(path):return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def save(path,value):
    with Path(path).open('x') as stream:json.dump(plain(value),stream,indent=2,allow_nan=False);stream.write('\n')


def verify_manifest(root):
    manifest=read(root/'manifest.json')
    for item in manifest['files']:
        assert digest(root/item['path'])==item['sha256'],item['path']
    return len(manifest['files'])


def qualify_controls(context):
    """No fit: bind exact unchanged all-2s wrapper and independently replay endpoints."""
    plan=read(CONTROL/'blocked_plan.json');qualification=read(CONTROL/'blocked_qualification.json')
    assert plan['maximum_evaluations']==1000 and plan['maximum_seconds']==120
    for path,sha in plan['source_sha256'].items():assert digest(path)==sha,path
    assert qualification['passed'] and not qualification['held_CFO_read']
    assert_array_equal(qualification['metadata']['numbers'],context.bank.numbers)
    assert qualification['metadata']['train_observations']==len(context.observations.times_s)
    for name,path in [('terminal_sha256',ATTEMPT/'output/terminal.json'),('training_input_sha256',ATTEMPT/'training-input.json')]:
        assert qualification['metadata'][name]==digest(path)
    seal=read(CONTROL/'blocked_seal_scalar2.json');sealed={Path(r['path']).name:r['sha256'] for r in seal['outcomes']}
    outcomes={};audits={}
    for arm in ['fitted-c','zero-c']:
        path=CONTROL/f'blocked_fit_scalar2_{arm}.json';r=read(path)
        assert digest(path)==sealed[path.name]
        assert r['family']=='scalar2' and r['arm']==arm
        assert_array_equal(r['effective_sigmas_s'],np.full(len(context.bank.numbers),2.))
        assert r['diagnostics']['fixed_c']==(arm=='zero-c')
        ctx=replace(context,fixed_c=arm=='zero-c')
        audit=endpoint_status(ctx,np.asarray(r['vector']),np.asarray(r['nuisance']))
        for name in ['training_objective','training_nll','stationarity']:
            assert_allclose(audit[name],r['audit'][name],atol=1e-9,rtol=0)
        assert audit['accepted'] and audit['feasible']
        r.update(method='frozen',reused_from=str(path),reused_sha256=digest(path),
            domain='common.refit broad regional disk; original production extra25km disk not imposed',
            separate_reuse_audit_objective_calls=1)
        save(HERE/f'fit-frozen-{arm}.json',r);outcomes[arm]=r;audits[arm]=audit
    save(HERE/'control-reuse-qualification.json',dict(passed=True,source_files_verified=len(plan['source_sha256']),
        scalar2_source_semantics='RelativeTimingModel.evaluate_details returns super result unchanged when all sigmas equal2; pinned source and original qualification verify objective and every gradient',
        exact_source_seed='Unmodified complete TRAIN terminal vector/nuisance; c0 only vector[6]=0',
        optimizer='Same common.refit1000/120 broad regional prior disk, same source/prior/mask/bank/q/calibration, no profile/alternate starts',
        plan_sha256=digest(CONTROL/'blocked_plan.json'),seal_sha256=digest(CONTROL/'blocked_seal_scalar2.json'),
        audits=audits,separate_endpoint_replay_objective_calls=2,held_cfo_read=False))
    return outcomes


def run():
    begun=time.monotonic()
    if (HERE/'protocol.json').exists():raise FileExistsError('Pilot already declared; no silent overwrite/retry')
    source_paths=[HERE/name for name in ['model.py','fit.py','test_model.py','run.py']]
    source_paths += [PROFILE/'manifest.json',PROFILE/'selection-fitted-c.json',PROFILE/'selection-zero-c.json',
        BLOCKED/'manifest.json',BLOCKED/'training_context.py',ATTEMPT/'training-input.json',ATTEMPT/'output/terminal.json',
        CONTROL/'blocked_plan.json',CONTROL/'blocked_qualification.json',CONTROL/'blocked_seal_scalar2.json',
        CONTROL/'blocked_fit_scalar2_fitted-c.json',CONTROL/'blocked_fit_scalar2_zero-c.json',
        REPORTS/'2026_10_16_dsx01_models/common.py',Path(sys.modules['leo.analysis.shared_scan_model'].__file__)]
    save(HERE/'protocol.json',dict(policy='TRAIN-only contrast profile plus joint continuation compared with frozen-band continuation',
        experiment='Single previously selected blocked-interpolation source; no additional discovery or fit campaign',
        arms=['frozen-fitted-c','free-fitted-c','frozen-zero-c','free-zero-c'],
        maximum_evaluations=1000,maximum_seconds=120,free_profile_calls=159,free_qualification_calls=2,free_refit_cap=839,
        free_profile_grid='Reuse sealed TRAIN-only +/-10000Hz coarse500/fine25 profile, exact absolute50k prior, original incumbent retained',
        controls='Reuse exactly qualified scalar2 endpoints from identical complete terminal seeds and original Shared objective; no duplicate controls',
        domain='Both policies use common.refit broad regional disk; extra original production25km disk is not imposed',
        likelihood='Original fixed bank, winner observations,125Hz shared-q conditional likelihood; physical/clock/q priors and budget unchanged; band absolute50000Hz prior exactly once',
        selection='TRAIN objective only. Persist all four endpoints and metadata-only predictions before held CFO scoring',
        c0='Conditional downstream sensitivity: vector[6]=0 only at seed and constrained in refit; original discovery/pipeline was fittedc',
        interpretation='Policy comparison includes TRAIN band-profile initialization; not pure parameter-count causality. Prior conditional gain was concentrated in one held block, not broad evidence.',
        source_sha256={str(p):digest(p) for p in source_paths}))
    import test_model
    tests=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(test_model))
    if not tests.wasSuccessful():raise AssertionError('Component tests failed')
    counts={name:verify_manifest(root) for name,root in [('blocked',BLOCKED),('band_profile',PROFILE)]}
    context=load_training_context();source_id=read(ATTEMPT/'derivation.json')['source_id']
    seedv=context.vector.copy();seedn=context.nuisance.copy()
    frozen=qualify_controls(context)
    print(json.dumps(dict(stage='controls_exactly_reused',calls={a:r['diagnostics']['evaluations'] for a,r in frozen.items()})),flush=True)
    states={('frozen',arm):(context,np.asarray(r['vector']),np.asarray(r['nuisance']),r) for arm,r in frozen.items()}
    for arm in ['fitted-c','zero-c']:
        v=seedv.copy()
        if arm=='zero-c':v[6]=0.
        ctx=replace(context,vector=v,nuisance=seedn.copy(),fixed_c=arm=='zero-c')
        def qualified(value):
            save(HERE/f'qualification-{arm}.json',value)
            print(json.dumps(dict(stage='real_qualification_passed',arm=arm,objective=value['profile_free_objective'],refit_cap=839)),flush=True)
        r,changed,profile=fit_free(ctx,reused_profile=read(PROFILE/f'selection-{arm}.json'),qualification_callback=qualified)
        r.update(method='free',arm=arm,absolute_band_offsets_hz=r['nuisance'][-changed.model.band_count:],
            original_offsets_hz=changed.model.original_offsets_hz,
            band_updates_hz=r['nuisance'][-changed.model.band_count:]-changed.model.original_offsets_hz,
            reused_profile_sha256=digest(PROFILE/f'selection-{arm}.json'),selection_uses_held_cfo=False)
        save(HERE/f'fit-free-{arm}.json',r)
        states['free',arm]=(changed,r['vector'],r['nuisance'],r)
        assert_array_equal(context.vector,seedv);assert_array_equal(context.nuisance,seedn)
        print(json.dumps(plain(dict(stage='free_fit_complete',arm=arm,diagnostics=r['diagnostics'],band_updates_hz=r['band_updates_hz']))),flush=True)
    save(HERE/'endpoint-freeze.json',dict(endpoints={f'{method}-{arm}':digest(HERE/f'fit-{method}-{arm}.json') for method,arm in states},
        all_selections_train_only=True,held_cfo_scored=False))
    # Only metadata columns are forwarded to prediction; CFO/gate/score are ignored.
    metadata=[]
    for line in (DATA/'context-observations.jsonl').read_text().splitlines():
        row=json.loads(line)
        if row['source_id']==source_id:metadata.append({k:row[k] for k in ['observation_id','time_s','actual_rf_hz','receiver','channel']})
    obs=PositionObservations(tuple(r['observation_id'] for r in metadata),np.array([r['time_s'] for r in metadata]),
        np.zeros(len(metadata)),np.array([r['actual_rf_hz'] for r in metadata]),np.array([r['receiver']-1 for r in metadata]),
        np.array([r['channel'] for r in metadata]),np.ones(len(metadata)))
    with np.load(ATTEMPT/'predictions.npz') as prior:masks={role:prior[role+'_mask'].copy() for role in ['train','held','boundary']}
    predictions={}
    for (method,arm),(ctx,v,n,r) in states.items():
        prediction=(predict_joint if method=='free' else predict_original)(ctx,v,n,obs)
        predictions[method,arm]=prediction
        np.savez_compressed(HERE/f'predictions-{method}-{arm}.npz',**prediction,times_s=obs.times_s,
            **{role+'_mask':mask for role,mask in masks.items()})
    save(HERE/'prediction-freeze.json',dict(endpoints_sha256=digest(HERE/'endpoint-freeze.json'),
        predictions={f'{m}-{a}':digest(HERE/f'predictions-{m}-{a}.npz') for m,a in states},held_cfo_scored=False))
    # Evaluation only: held measurements and requested membership first enter scoring.
    rows=[json.loads(line) for line in (DATA/'context-observations.jsonl').read_text().splitlines()]
    rows=[r for r in rows if r['source_id']==source_id];assert [r['observation_id'] for r in rows]==list(obs.window_ids)
    measured=np.array([r['measured_cfo_hz'] for r in rows])
    with (DATA/'membership.csv').open() as stream:members=[r for r in csv.DictReader(stream) if r['source_id']==source_id]
    windows={rid:np.array([key in {r['observation_id'] for r in members if r['region_id']==rid} for key in obs.window_ids]) for rid in sorted({r['region_id'] for r in members})}
    classified={}
    for key,prediction in predictions.items():
        terms,details=density(measured,prediction['prediction_hz'],prediction['visibility_weight'],np.full(len(rows),125.),prediction['detection_probability'],context.model.score)
        best=terms.responsibilities.argmax(1);associated=terms.responsibilities[np.arange(len(best)),best]>terms.clutter_probability
        residual=terms.residual_hz[np.arange(len(best)),best]
        classified[key]=(terms,details,associated,residual,best)
    results=[]
    def metric(use,key):
        terms,details,associated,residual,best=classified[key];base=classified['frozen',key[1]]
        shared=use&associated&base[2];rms=lambda x:float(np.sqrt(np.mean(x*x))) if len(x) else None
        return dict(observations=int(use.sum()),associated=int((use&associated).sum()),frequency_nll=float(details['row_nll'][use].sum()),
            associated_rms_hz=rms(residual[use&associated]),new_vs_frozen=int((use&associated&~base[2]).sum()),
            lost_vs_frozen=int((use&~associated&base[2]).sum()),retained_vs_frozen=int(shared.sum()),
            intersection_frozen_rms_hz=rms(base[3][shared]),intersection_current_rms_hz=rms(residual[shared]))
    for key,(ctx,v,n,r) in states.items():
        method,arm=key
        result=dict(method=method,arm=arm,full=metric(np.ones(len(rows),bool),key),
            **{role:metric(mask,key) for role,mask in masks.items()},
            windows=[dict(region_id=rid,full=metric(use,key),**{role:metric(use&mask,key) for role,mask in masks.items()}) for rid,use in windows.items()],
            diagnostics=r['diagnostics'],position_vector_deg=np.asarray(v)[:2],
            absolute_band_offsets_hz=np.asarray(n)[-ctx.model.band_count:] if method=='free' else free_context(context).model.original_offsets_hz,
            common_timing_s=float(v[7]),relative_timing_rms_s=float(np.sqrt(np.mean((ctx.model.basis@np.asarray(v)[8:])**2))))
        assert_allclose(result['train']['frequency_nll'],r['diagnostics']['likelihood_nll'],atol=1e-8,rtol=0)
        results.append(result)
        terms,details,associated,residual,best=classified[key]
        np.savez_compressed(HERE/f'evaluation-{method}-{arm}.npz',associated=associated,residual_hz=residual,
            best_number=context.bank.numbers[best],row_nll=details['row_nll'],times_s=obs.times_s,
            **{role+'_mask':mask for role,mask in masks.items()})
    save(HERE/'results.json',dict(results=results,evaluation_denominators=read(ATTEMPT/'derivation.json')['evaluation_denominators'],
        prelaunch_tests=tests.testsRun,verified_sealed_files=counts,optimizer_calls_new=2,optimizer_calls_reused=2,
        policy_evaluations={f'{m}-{a}':r['diagnostics']['evaluations'] for (m,a),(_,_,_,r) in states.items()},
        separate_control_endpoint_replay_objective_calls=2,evaluation_density_calls=4,prediction_orbit_queries=4,
        elapsed_seconds=time.monotonic()-begun,protocol_sha256=digest(HERE/'protocol.json'),prediction_freeze_sha256=digest(HERE/'prediction-freeze.json'),
        qualification='Single blocked-interpolation pilot, conditional on fittedc TRAIN production discovery. Same broad research domain for frozen/free; not fullproductionbounds. No identitytruth/newposition/fullpipelinec0 claim.'))
    print(json.dumps(dict(stage='evaluated',results=[dict(method=r['method'],arm=r['arm'],train=r['train']['associated'],held=r['held']['associated'],held_nll=r['held']['frequency_nll'],requested_held=sum(w['held']['associated'] for w in r['windows'])) for r in results])),flush=True)


if __name__=='__main__':run()
