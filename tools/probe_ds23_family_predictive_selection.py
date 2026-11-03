"""Select receiver covariance through two completely withheld curved families.

Identities, aliases and radio noise are frozen, so this is conditional RF
validation, not an independent satellite-identity test. GPS is not imported.
"""

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import time

import numpy as np

from algo02_scan import pair_passes
from ds23_family_predictive_selection import family_folds,gaussian_predictive,qualified_gain
from ds23_receiver_family_search import fine_receiver_basis
from ds23_frequency_events import make_event_problem
from investigate_dsx01_localization_failures import fit
from probe_algo03_frame_peak_recovery import context
from probe_ds23_frequency_events import cached
from probe_ds23_symmetric_family_selection import OUT as BANK,bound_incumbent
from run_algo01_ds23_sample import ROOT,read,write,sha
from run_dsx01_clean_region import zero_state

OUT=ROOT/'reports/2026_10_20_ds23_family_predictive_selection'
ARMS=('c0','fitted_c')


def hashes():
    return {str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),ROOT/'tools/ds23_family_predictive_selection.py')}


def prepare():
    OUT.mkdir(exist_ok=True);path=OUT/'protocol.json'
    if path.exists():
        p=read(path)
        if p['source_sha256']!=hashes():raise ValueError('frozen family-prediction rule changed')
        return p
    cases=read(BANK/'protocol.json')['cases'];bindings={}
    for case in cases:
        sources=[BANK/case/'result.json',BANK/case/'fine_null.json']
        if (BANK/case/'fine_null_constrained.json').exists():sources.append(BANK/case/'fine_null_constrained.json')
        bindings[case]={str(p.relative_to(ROOT)):sha(p) for p in sources}
    p=dict(cases=cases,workers=20,source_sha256=hashes(),input_bindings=bindings,
        hypothesis='shared radio flexibility must predict entirely withheld satellite families',
        folds='two largest active curved families with >=24 points; at least four total families',
        training='exclude each held family on ALL receivers/channels and every predictive linear observation',
        train_phase_rounds=3,train_position_steps=24,cold_start_km=[0,0],
        qualification='all four c-arm training comparisons interior/converged; both families improve in each arm; sum gain >2log2',
        local_position_covariance_and_full_shared_coefficient_covariance_in_prediction=True,
        held_noise_inverse_precision_mean=2.,held_phase_uses_prior_marginal_variance=True,
        uncertainty_is_local_moment_matched_Gaussian_not_calibrated=True,
        full_fits_reused_from_hash_pinned_matched_5x48_cold_covariance_nulls=True,
        all_original_curved_and_predictive_points_restored_in_final_fits=True,
        masks_aliases_labels_powers_other_priors_and_gates_unchanged=True,
        identities_and_radio_noise_are_conditioned_on_frozen_full_scan_preprocessing=True,
        no_GPS_future_TLE_new_RF_or_linear_calibration_feedback=True,
        cohort_is_reused_development_requires_disjoint_confirmation=True)
    write(path,p);return p


def make(scan,node,train,arm,reference,powers,means,model):
    p=make_event_problem(scan,node,train,arm,reference,powers,means,model,[])
    cached(p);return p


def train_and_predict(scan,node,fold,arm,powers,means,model):
    x=np.zeros(2);reference=np.zeros(len(means));history=[]
    for epoch in range(3):
        p=make(scan,node,fold['train'],arm,reference,powers,means,model)
        fitted=fit(p,x,iterations=24);x=np.asarray(fitted['parameters'])
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        change=float(np.max(abs(phase-reference)));reference=phase
        history.append(dict(epoch=epoch,phase_change_s=change,endpoint_east_north_km=x))
    c=p.calculate(x);coefficient=c['coefficient'];derivatives=[]
    for k in (0,1):
        delta=np.zeros(2);delta[k]=.01
        predictions=[]
        for point in (x+delta,x-delta):
            geometry=p.calculate(point)
            predictions.append(p.q*geometry['intercept']+geometry['features']@coefficient)
        derivatives.append((predictions[0]-predictions[1])/.02)
    full=np.column_stack((*derivatives,c['features']))
    precision=c['coefficient_prior_precision'].copy()
    phase_start=p.hardware.shape[1]+p.smooth.shape[1]
    local=p.labels.index(fold['family'])
    # The held family has NO RF training evidence. Its Student prior's
    # marginal standardized variance is one, unlike a factorized VB prior.
    precision[phase_start+local]=1.
    train,test=fold['train'],fold['test']
    if np.any(train&(np.asarray(p.labels)[p.flat_labels]==fold['family'])):
        raise ValueError('held satellite leaked into training calibration')
    w=powers[p.noise_groups[train]]*c['noise_precision'][p.noise_groups[train]]/p.point_noise[train]**2
    prediction=gaussian_predictive(c['conditional_residual_hz'][test],full[test],full[train],w,
        np.r_[np.zeros(2),precision],p.point_noise[test]*np.sqrt(2/powers[p.noise_groups[test]]))
    return dict(prediction=prediction,history=history,endpoint_east_north_km=x,
        qualified_training=bool(change<=.01 and np.max(abs(x))<12.49),
        train_points=int(train.sum()),test_points=int(test.sum()),phase_change_s=change)


def run(case):
    protocol=prepare();directory=OUT/case;directory.mkdir(exist_ok=True)
    if (directory/'result.json').exists():return dict(case=case,cached=True)
    for path,digest in protocol['input_bindings'][case].items():
        if sha(ROOT/path)!=digest:raise ValueError('frozen covariance fit changed')
    previous=read(BANK/case/'result.json');scan,node,keep,base,old=context(case)
    incumbent=previous['incumbent_arms'];signed,_=bound_incumbent(case)
    if incumbent!=signed['policy_arms']:raise ValueError('signed incumbent changed')
    labels=np.asarray(base.labels)[base.flat_labels]
    folds=family_folds(labels,keep);powers=np.asarray(previous['powers'])
    means=np.asarray(previous['means_s'])[base.labels]
    model=old['hyperparameters_from_pre_RF_TLE_only'];started=time.monotonic();records=[]
    for covariance in ('original','fine'):
        changed=copy.copy(scan);candidate=copy.deepcopy(node)
        if covariance=='fine':changed.rx_basis=[fine_receiver_basis(t['times']) for t in scan.tracks]
        candidate['seed']['state']=zero_state(changed)
        for fold in folds:
            for arm in ARMS:
                row=train_and_predict(changed,candidate,fold,arm,powers,means,model)
                records.append(dict(row,covariance=covariance,arm=arm,family=fold['family']))
                write(directory/'progress.json',dict(records=records))
                print(case,covariance,arm,'withhold',fold['family'],'loss',row['prediction']['negative_twice_log_density'],flush=True)
    gains={}
    for arm in ARMS:
        pairs=[]
        for fold in folds:
            a=next(r for r in records if r['arm']==arm and r['family']==fold['family'] and r['covariance']=='original')
            b=next(r for r in records if r['arm']==arm and r['family']==fold['family'] and r['covariance']=='fine')
            pairs.append(dict(family=fold['family'],gain=a['prediction']['negative_twice_log_density']-b['prediction']['negative_twice_log_density'],
                qualified_training=a['qualified_training'] and b['qualified_training']))
        gains[arm]=pairs
    qualified=all(qualified_gain(gains[a]) for a in ARMS)
    candidates=[]
    for name in ('fine_null.json','fine_null_constrained.json'):
        path=BANK/case/name
        if path.exists():
            record=read(path)
            if pair_passes(record['arms'],include_linear=True):candidates.append((path,record))
    candidate=min(candidates,key=lambda r:r[1]['arms']['c0']['negative_twice_elbo']) if candidates else None
    accepted=bool(qualified and candidate)
    chosen=candidate[1]['arms'] if accepted else incumbent
    result=dict(case=case,accepted=accepted,predictively_qualified=qualified,gains=gains,records=records,
        selected_covariance='fine' if accepted else 'original',
        full_fine_result_binding=dict(path=str(candidate[0].relative_to(ROOT)),sha256=sha(candidate[0])) if candidate else None,
        full_fine_pair=candidate[1]['arms'] if candidate else None,
        policy_arms=chosen,incumbent_arms=incumbent,baseline_arms=old['policy_arms'],
        GPS_used=False,future_TLE_used=False,no_original_points_removed=True,
        seconds=time.monotonic()-started)
    write(directory/'result.json',result)
    print(case,'predictive selected fine',accepted,'seconds',result['seconds'],flush=True)
    return dict(case=case,accepted=accepted,seconds=result['seconds'])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case');args=parser.parse_args();protocol=prepare()
    if args.case:run(args.case)
    else:
        receipts=[]
        with ProcessPoolExecutor(max_workers=protocol['workers']) as pool:
            futures={pool.submit(run,c):c for c in protocol['cases']}
            for f in as_completed(futures):
                try:receipts.append(f.result())
                except Exception as exc:receipts.append(dict(case=futures[f],error=repr(exc)))
                write(OUT/'progress.json',dict(receipts=receipts,completed=len(receipts),total=len(futures)))
        write(OUT/'execution.json',dict(receipts=receipts,all_terminal=True))
