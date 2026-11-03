"""Freeze both TRAIN-only contrast profiles before scoring held CFO."""
from dataclasses import asdict
import csv
import hashlib
import json
from pathlib import Path
import sys
import time
import unittest
import numpy as np
from numpy.testing import assert_array_equal,assert_allclose
from band_profile import BandProfiles,Grid

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parents[1]
BLOCKED=REPORTS/'2026_10_17_dsx01_iteration5'/'blocked_cold'
DATA=REPORTS/'2026_10_16_dsx01_fast_association_losses'
sys.path.append(str(BLOCKED))
from training_context import load_training_context,predict_original
from leo.application.shared_fast_position import plain
from leo.analysis.shared_scan_model import density
from leo.contracts.regional_position import PositionObservations


def digest(path):return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
    with Path(path).open('x') as stream:json.dump(plain(value),stream,indent=2,allow_nan=False);stream.write('\n')


def run():
    begun=time.monotonic();protocol_path=HERE/'protocol.json'
    if protocol_path.exists():raise FileExistsError('Assay namespace already exists; no silent retry or overwrite')
    grid=Grid()
    save(protocol_path,dict(model='Conditional frozen-state band-contrast-only TRAIN grid assay',grid=asdict(grid),
        arms=['fitted-c','zero-c'],zero_c_policy='Only physicalvectorc setzero; allotherseed coordinates and fixedcontrasts identical',
        selection='Exact TRAIN likelihood plus absolute frozen contrast prior referencedzero; independentRXhighlanes',
        holdout_policy='Select and persist BOTH arms before loading held CFO for scoring; no held-driven grid or selection',
        local_search_box='Identical ±10000Hz update perreceiver, coarse500Hz then ±500Hz fine25Hz, clipped tosamebox and original±ALIAS_HZ/2 bounds',
        cost_policy='Each baseline sharedobjective or partial/full density call countsone toward200/120sec perarm. Cachehits and orbitqueries reported separately.',
        source_blocked_manifest_sha256=digest(BLOCKED/'manifest.json'),
        research_code_sha256={p.name:digest(p) for p in [HERE/'band_profile.py',HERE/'run_assay.py',HERE/'test_band_profile.py']},
        scope='No geography,timing,clock,q,candidate identity selection or referencecoordinates changed. Original production discovery fittedc; thisc0 sensitivity is conditional, not a newc0pipeline or newposition validation.'))
    import test_band_profile
    tests=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(test_band_profile))
    if not tests.wasSuccessful():raise AssertionError('Assay tests failed')
    context=load_training_context();seedv=context.vector.copy();seedn=context.nuisance.copy()
    selections={};states={}
    for arm in ['fitted-c','zero-c']:
        v=seedv.copy();n=seedn.copy()
        if arm=='zero-c':v[6]=0.
        profile=BandProfiles(context,v,n,grid);fit=profile.fit()
        assert fit['diagnostics']['evaluations']<=grid.max_evaluations
        assert fit['diagnostics']['elapsed_seconds']<=grid.max_seconds+.1
        assert_array_equal(context.vector,seedv);assert_array_equal(context.nuisance,seedn)
        fit.update(arm=arm,vector=v,nuisance=n,original_offsets_hz=profile.current,
            q=profile.q,total_timing_s=v[7]+context.model.basis@v[8:],
            training_observations=len(context.observations.times_s),grid=asdict(grid),
            strict_full_joint_kkt_claimed=False,selection_uses_held_cfo=False)
        save(HERE/f'selection-{arm}.json',fit);selections[arm]=fit;states[arm]=(v,n)
        print(json.dumps(dict(stage='selection_frozen',arm=arm,updates_hz=fit['updates_hz'].tolist(),
            training_objective_before=fit['training_objective_before'],training_objective=fit['training_objective'],
            evaluations=fit['diagnostics']['evaluations'])),flush=True)
    # Both selections are durable before metadata-only full prediction.
    metadata=[]
    for line in (DATA/'context-observations.jsonl').read_text().splitlines():
        row=json.loads(line)
        if row['source_id']=='S03':
            metadata.append({k:row[k] for k in ['observation_id','time_s','actual_rf_hz','receiver','channel']})
    obs=PositionObservations(tuple(r['observation_id'] for r in metadata),np.array([r['time_s'] for r in metadata]),
        np.zeros(len(metadata)),np.array([r['actual_rf_hz'] for r in metadata]),np.array([r['receiver']-1 for r in metadata]),
        np.array([r['channel'] for r in metadata]),np.ones(len(metadata)))
    with np.load(BLOCKED/'S03-block20-parity0'/'predictions.npz') as original:
        masks={role:original[role+'_mask'].copy() for role in ['train','held','boundary']}
    predictions={}
    for arm,(v,n) in states.items():
        base=predict_original(context,v,n,obs)
        delta=sum((obs.receiver==rx)*(obs.channel>=5)*update for rx,update in enumerate(selections[arm]['updates_hz']))
        changed=base['prediction_hz']+delta[:,None]
        predictions[arm]=(base,changed)
        np.savez_compressed(HERE/f'predictions-{arm}.npz',baseline_prediction_hz=base['prediction_hz'],
            profile_prediction_hz=changed,visibility_weight=base['visibility_weight'],detection_probability=base['detection_probability'],
            number=base['number'],times_s=obs.times_s,**{role+'_mask':mask for role,mask in masks.items()})
    save(HERE/'prediction-freeze.json',dict(selections={arm:digest(HERE/f'selection-{arm}.json') for arm in selections},
        predictions={arm:digest(HERE/f'predictions-{arm}.npz') for arm in selections},
        held_cfo_loaded_for_scoring=False,geography_timing_clock_q_and_bank_unmutated=True))
    # Evaluation only: held CFO and window membership first enter scoring here.
    rows=[json.loads(line) for line in (DATA/'context-observations.jsonl').read_text().splitlines()]
    rows=[r for r in rows if r['source_id']=='S03'];assert [r['observation_id'] for r in rows]==list(obs.window_ids)
    measured=np.array([r['measured_cfo_hz'] for r in rows])
    with (DATA/'membership.csv').open() as stream:members=[r for r in csv.DictReader(stream) if r['source_id']=='S03']
    windows={rid:np.array([key in {r['observation_id'] for r in members if r['region_id']==rid} for key in obs.window_ids]) for rid in sorted(set(r['region_id'] for r in members))}
    results=[]
    for arm,(base,changed) in predictions.items():
        classified={}
        for label,prediction in [('baseline',base['prediction_hz']),('profile',changed)]:
            terms,details=density(measured,prediction,base['visibility_weight'],np.full(len(rows),125.),base['detection_probability'],context.model.score)
            best=terms.responsibilities.argmax(1);associated=terms.responsibilities[np.arange(len(best)),best]>terms.clutter_probability
            residual=terms.residual_hz[np.arange(len(best)),best]
            classified[label]=(terms,details,best,associated,residual)
        def metric(use,label):
            terms,details,best,assigned,residual=classified[label];old=classified['baseline'][3]
            select=use&assigned;intersection=use&assigned&old
            rms=lambda values:float(np.sqrt(np.mean(values**2))) if len(values) else None
            return dict(observations=int(use.sum()),associated=int(select.sum()),frequency_nll=float(details['row_nll'][use].sum()),
                associated_rms_hz=rms(residual[select]),new_vs_paired_baseline=int((use&assigned&~old).sum()),
                lost_vs_paired_baseline=int((use&~assigned&old).sum()),retained_vs_paired_baseline=int(intersection.sum()),
                intersection_baseline_rms_hz=rms(classified['baseline'][4][intersection]),intersection_profile_rms_hz=rms(residual[intersection]))
        for label in ['baseline','profile']:
            r=dict(arm=arm,method=label,full=metric(np.ones(len(rows),bool),label),
                **{role:metric(mask,label) for role,mask in masks.items()},
                windows=[dict(region_id=rid,full=metric(use,label),**{role:metric(use&mask,label) for role,mask in masks.items()}) for rid,use in windows.items()],
                selected_updates_hz=selections[arm]['updates_hz'],absolute_offsets_hz=selections[arm]['absolute_offsets_hz'],
                training_objective=selections[arm]['training_objective' if label=='profile' else 'training_objective_before'])
            expected=selections[arm]['training_nll' if label=='profile' else 'training_nll_before']
            assert_allclose(r['train']['frequency_nll'],expected,atol=1e-8,rtol=0)
            if arm=='fitted-c' and label=='baseline':
                frozen=json.loads((BLOCKED/'S03-block20-parity0'/'evaluation.json').read_text())
                assert r['held']['associated']==frozen['held']['associated'] and r['train']['associated']==frozen['train']['associated']
            results.append(r)
        np.savez_compressed(HERE/f'evaluation-{arm}.npz',baseline_associated=classified['baseline'][3],profile_associated=classified['profile'][3],
            baseline_residual_hz=classified['baseline'][4],profile_residual_hz=classified['profile'][4],
            times_s=obs.times_s,**{role+'_mask':mask for role,mask in masks.items()})
    original=json.loads((BLOCKED/'S03-block20-parity0'/'derivation.json').read_text())
    save(HERE/'results.json',dict(results=results,selections=selections,evaluation_denominators=original['evaluation_denominators'],
        actual_profile_evaluations=sum(s['diagnostics']['evaluations'] for s in selections.values()),
        evaluation_density_calls=4,prediction_orbit_queries=2,prelaunch_tests=tests.testsRun,
        elapsed_including_context_and_evaluation_seconds=time.monotonic()-begun,
        protocol_sha256=digest(protocol_path),prediction_freeze_sha256=digest(HERE/'prediction-freeze.json'),
        qualification='Conditional calibration-only assay at fixedTRAIN-discovered geography/τ/clock/q/bank. Both selections precede held scoring. '
        'No continuous/fulljointKKT, wholepipelinec0, newposition or identitytruth claim.'))
    print(json.dumps(dict(stage='evaluated',results=[dict(arm=r['arm'],method=r['method'],train=r['train']['associated'],held=r['held']['associated'],held_nll=r['held']['frequency_nll'],held_new=r['held']['new_vs_paired_baseline'],held_lost=r['held']['lost_vs_paired_baseline']) for r in results])),flush=True)


if __name__=='__main__':run()
