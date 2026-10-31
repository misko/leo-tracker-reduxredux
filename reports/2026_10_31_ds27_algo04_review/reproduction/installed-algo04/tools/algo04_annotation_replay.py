"""ALGO04 frozen-competition reference30 replay, preserving annotation contracts.

Baseline15 receipts are reused, never refitted here. Only the
numerical reference changes; physical phase priors and target support do not.
"""
import argparse
import copy
import hashlib
import json
import signal
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for directory in (REPOSITORY_ROOT / "src", REPOSITORY_ROOT / "tools"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import numpy as np

from annotate_predictive_only import context, prediction_models, check_predictive_role
from annotate_track_predictively import fit_training
from annotation_partition_plan import require_distinct_annotation
from debug_fast_graph_unassociated import read, write
from leo.analysis.research.grouped_prediction import replay_split, identity_consensus
from leo.analysis.research.predictive_track import mixture_prediction
from leo.analysis.research.retained_track_likelihood import PERIOD
from phase_reference_checks import reference_domain

ARMS=('c0','fitted_c')


def has_phase_overflow(value):
    """Any saved round may clip even when the final round no longer clips."""
    if isinstance(value,dict):
        if value.get('phase_outside_reference_window') is True:return True
        overflow=value.get('maximum_phase_overflow_s')
        if isinstance(overflow,(int,float)) and np.isfinite(overflow) and overflow>0:return True
        return any(has_phase_overflow(v) for v in value.values())
    if isinstance(value,(list,tuple)):return any(has_phase_overflow(v) for v in value)
    return False


def fingerprint(mask):
    return hashlib.sha256(np.asarray(mask,np.uint8).tobytes()).hexdigest()


def competition_signature(result):
    return [(f['seed'],copy.deepcopy(f['split']),[(q['candidate_index'],q['norad'],q['alias']) for q in f['proposals']])
        for f in result['folds']]


def target_context(d,inventory,frozen,protocol,source):
    """Use source-validated public reconstruction routes for appended views."""
    if frozen.get('graph_bundle'):
        from predictive_graph_bundle import validated_bundle_context
        changed,target=validated_bundle_context(d,inventory,source)
    elif frozen.get('inactive_graph_fragment'):
        from inactive_graph_fragment import validated_inactive_context
        changed,target=validated_inactive_context(d,inventory,source)
    elif protocol['target'].get('native_branch_source'):
        from native_predictive_branch import native_context,validated_native_source
        changed,target=native_context(d,inventory,validated_native_source(source),frozen['track_id'])
    else:
        target=next(t for t in inventory['tracks'] if t['track_id']==frozen['track_id'])
        changed=d
    expected=protocol['target'];track=changed['scan'].tracks[target['track_index']]
    for key in ('track_id','track_index','component','observation_ids'):
        if key in expected and target.get(key)!=expected[key]:raise ValueError(f'frozen target {key} changed')
    appended=bool(frozen.get('inactive_graph_fragment') or frozen.get('graph_bundle') or expected.get('native_branch_source'))
    expected_ids=expected['observation_ids'] if appended else expected.get('all_track_observation_ids',expected['observation_ids'])
    if track['key']!=frozen['component'] or set(track['observation_ids'])!=set(expected_ids):
        raise ValueError('frozen annotation observations or component changed')
    if not appended and 'all_track_observation_ids' in expected and list(track['observation_ids'])!=list(expected_ids):
        raise ValueError('frozen chronological graph observations changed')
    focus=(protocol.get('partition_plan') or {}).get('target_times_s')
    if focus is not None and not np.array_equal(np.asarray(track['times']),np.asarray(focus)):
        raise ValueError('frozen annotation target timestamps changed')
    if protocol.get('measurement_refinement'):
        from native_iq_refined_context import replay_refinement
        changed=replay_refinement(changed,target,protocol['measurement_refinement'])
    return changed,target


def check_bank(p,x):
    phase=np.asarray(p.state(x)['phases'])[p.labels]
    check=reference_domain(p.sky['time_s'],p.flat_times,p.flat_labels,phase)
    if not check['in_domain']:raise ValueError('final training phases leave frozen causal orbit bank')
    return check


def replay_annotation(inventory,source,output):
    """Replay all saved proposals at reference30 into a normal annotation folder."""
    began=time.monotonic();inventory,source,output=map(Path,(inventory,source,output))
    inv,frozen,protocol=read(inventory),read(source/'result.json'),read(source/'protocol.json')
    require_distinct_annotation(frozen,protocol)
    if not has_phase_overflow(frozen):raise ValueError('reference30 replay requires saved phase overflow metadata')
    if protocol['job']['job_id']!=inv['job']['job_id']:raise ValueError('annotation and inventory jobs differ')
    if protocol.get('phase_rounds',5)!=5 or protocol.get('position_steps',48)!=48:
        raise ValueError('frozen training budget differs from unchanged five-by-48 implementation')
    if protocol.get('fixed_noise_hz',150)!=150 or protocol.get('phase_box_s',[-15,15])!=[-15,15]:
        raise ValueError('frozen physical noise or target phase policy differs')
    original_competition=competition_signature(frozen)
    d=context(inv);base,_=d['problems']['c0']
    d,target=target_context(d,inv,frozen,protocol,source)
    i=target['track_index'];track=d['scan'].tracks[i]
    check_predictive_role(base,i,protocol.get('inactive_curved_member_as_predictive',False))
    n=len(base.flat_times);full_times=np.r_[base.flat_times,track['times']]
    output.mkdir(parents=True,exist_ok=False)
    sources=[inventory,source/'result.json',source/'protocol.json',Path(__file__)]
    receipt=dict(reference_limit_s=30.,baseline15_receipts_reused=True,frozen_competition=True,
        source=str(source),source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        observations_candidates_aliases_splits_priors_starts_and_budgets_unchanged=True,
        physical_phase_prior_and_target_support_unchanged=True,GPS_used=False,new_RF=False,new_TLE=False)
    updated_protocol=copy.deepcopy(protocol);updated_protocol.update(reference_limit_s=30.,frozen_competition=True,numerical_replay=receipt)
    write(output/'protocol.json',updated_protocol)
    # Capture optimizer termination without changing fit_training's algorithm.
    import investigate_dsx01_localization_failures as fitter
    original_fit=fitter.fit;attempts=[]
    def recording_fit(*args,**kwargs):
        result=original_fit(*args,**kwargs);attempts.append(copy.deepcopy(result));return result
    fitter.fit=recording_fit
    folds=[]
    try:
        for fold in frozen['folds']:
            train,held=replay_split(full_times,fold['split']);keep=d['keep']&train[:n];tt,th=train[n:],held[n:]
            if tt.sum()<8 or th.sum()<4:raise ValueError('frozen target grouping lacks original minimum support')
            updated=copy.deepcopy(fold);fits={}
            masks=dict(graph_training=fingerprint(keep),target_training=fingerprint(tt),target_held=fingerprint(th))
            for arm in ARMS:
                start=len(attempts);p,x,meta=fit_training(d,d['node'],keep,arm,reference_limit_s=30.)
                for h,opt in zip(meta['history'],attempts[start:],strict=True):h['optimizer']=opt
                np.testing.assert_array_equal(p.keep,keep)
                meta['final_training_reference_domain']=check_bank(p,x);fits[arm]=(p,x,meta)
            for proposal in updated['proposals']:
                j=proposal['candidate_index']
                if int(d['scan'].norads[j])!=proposal['norad']:raise ValueError('frozen candidate catalogue identity changed')
                for arm,(p,x,meta) in fits.items():
                    mu,cov,lp,phases,elev,prior=prediction_models(d,p,x,i,j,
                        phase_step=protocol['phase_step_s'],uncalibrated_phase_mixture=protocol['uncalibrated_phase_mixture'])
                    domains=[]
                    for boundary in (float(phases.min()),float(phases.max())):
                        domain=reference_domain(p.sky['time_s'],track['times'],np.zeros(len(track['times']),int),np.array([boundary]))
                        if not domain['in_domain']:raise ValueError('target prediction leaves frozen causal orbit bank')
                        domains.append(domain)
                    observed=track['values']+proposal['alias']*PERIOD
                    if np.isfinite(lp).any():
                        score=mixture_prediction(observed,mu,cov,lp,tt,th);weights=score['training_mixture_weights']
                        visible=float(elev[weights>1e-6].min());mean=float(weights@phases)
                        sd=float(np.sqrt(weights@((phases-mean)**2)))
                        boundary=float(weights[abs(phases)>=14.9].sum()) if len(phases)>1 else float(abs(phases[0])>=14.9)
                    else:
                        score=dict(negative_twice_log_density=1e30,rms_hz=1e15,unobservable=True)
                        visible=float(elev.max());mean=sd=boundary=None
                    old=proposal['arms'][arm];value=copy.deepcopy(old)
                    value.update(copy.deepcopy(meta),scores=dict(conditional_target=score,target=score),prior=prior,
                        minimum_target_elevation_deg=visible,target_phase_training_mean_s=mean,target_phase_training_sigma_s=sd,
                        target_phase_boundary_mass=boundary,target_enters_calibration_equations=False,
                        mask_sha256=masks,target_reference_domain=domains,
                        baseline15_score_difference=score['negative_twice_log_density']-old['scores']['conditional_target']['negative_twice_log_density'])
                    if target.get('graph_bundle'):
                        checks={};members=np.asarray(target['member_indices'])
                        for k,member in enumerate(target['members']):
                            held_member=th&(members==k)
                            if held_member.sum()<4:continue
                            z=mixture_prediction(observed,mu,cov,lp,tt,held_member) if np.isfinite(lp).any() else dict(negative_twice_log_density=1e30,rms_hz=1e15)
                            checks[member['track_id']]=dict(z,held_points=int(held_member.sum()))
                        value['bundle_member_scores']=checks
                    proposal['arms'][arm]=value
                write(output/f"{fold['seed']}-{proposal['norad']}.json",proposal)
            folds.append(updated);write(output/f"seed-{fold['seed']}.json",updated)
            print('reference30',frozen['track_id'],fold['seed'],[(a,fits[a][2]['final_phase_change_s']) for a in ARMS],flush=True)
    finally:
        fitter.fit=original_fit
    result=copy.deepcopy(frozen);result.update(folds=folds,annotation=identity_consensus(folds,score_name='conditional_target'),
        reference_limit_s=30.,numerical_replay=receipt,seconds=time.monotonic()-began,no_production_change=True)
    if target.get('graph_bundle'):
        from predictive_graph_bundle import member_evidence
        result['bundle_member_checks']=member_evidence(folds,target,result['annotation']['norad'])
        if result['annotation']['status']=='conditionally_supported_identity' and not result['bundle_member_checks']['passed']:
            result['annotation']['status']='bundle_member_support_failed'
    if competition_signature(result)!=original_competition:raise ValueError('frozen competition changed during replay')
    require_distinct_annotation(result,updated_protocol)
    write(output/'result.json',result)
    return result


run=replay_annotation


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('inventory','source','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('590s annotation replay cap')));signal.alarm(590)
    replay_annotation(args.inventory,args.source,args.output)
