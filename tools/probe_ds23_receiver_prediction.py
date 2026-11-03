"""Omit a family on one RX, fit other evidence, predict the omitted CFOs."""

import argparse
import copy
from pathlib import Path
import numpy as np
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED,make_problem,refit
from probe_ds23_statistical_curvature import replay
from diagnose_ds23_position_information import derivative_at
from probe_ds23_band_covariance import split_basis
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha,final_scan
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis

OUT=ROOT/'reports/2026_10_19_ds23_receiver_prediction'
METHODS=('baseline','fast_receiver','fast_band_half')


def expand(scan,node,method):
    if method not in METHODS:raise ValueError('unknown covariance hypothesis')
    if method=='baseline':return scan,node
    changed=copy.copy(scan);seed=copy.deepcopy(node);basis=[]
    amplitude=scan.radio_sigma_hz/np.sqrt(2)
    for track,slow in zip(scan.tracks,scan.rx_basis,strict=True):
        fast=projected_receiver_basis(track['times'],spacing_s=10,width_s=5)*amplitude/200
        if method=='fast_band_half':fast=split_basis(fast,int(track['channel']>4),.5)
        basis.append(np.column_stack((slow,fast)))
    changed.rx_basis=basis
    old=np.asarray(seed['seed']['state']['smooth']);seed['seed']['state']['smooth']=np.column_stack((old,np.zeros((2,basis[0].shape[1]-old.shape[1]))))
    return changed,seed


def gaussian_score(residual,covariance):
    r,c=np.asarray(residual,float),np.asarray(covariance,float)
    if r.ndim!=1 or c.shape!=(len(r),len(r)) or not np.isfinite(r).all() or not np.isfinite(c).all():
        raise ValueError('finite residual and matching covariance required')
    root=np.linalg.cholesky(c);z=np.linalg.solve(root,r)
    return dict(negative_twice_log_density=float(z@z+2*np.log(np.diag(root)).sum()+len(r)*np.log(2*np.pi)),
        quadratic=float(z@z),observations=len(r),RMS_hz=float(np.sqrt(np.mean(r*r))),
        covariance_RMS_hz=float(np.sqrt(np.mean(np.diag(c)))))


def predictive(p,x,train,test,powers,held_family):
    c=p.calculate(x);f=c['features'];precision=c['coefficient_prior_precision'].copy()
    # This family remains observed on the other RX. Its phase precision is
    # learned only from that training evidence, and must not be reset here.
    assert np.any(train&(p.flat_labels==p.labels.index(held_family)))
    w=powers[p.noise_groups[train]]*c['noise_precision'][p.noise_groups[train]]/p.point_noise[train]**2
    d=derivative_at(p,x,c['coefficient'],.01)
    full=np.column_stack((d,f));prior=np.diag(np.r_[np.zeros(2),precision])
    gram=prior+full[train].T@(full[train]*w[:,None])
    root=np.linalg.cholesky((gram+gram.T)/2)
    projected=np.linalg.solve(root,full[test].T)
    # An unobserved noise group retains Gamma(2,2): E[1/lambda]=2.
    covariance=np.diag(2*p.point_noise[test]**2)+projected.T@projected
    r=c['conditional_residual_hz'][test]
    return dict(gaussian_score(r,covariance),time_s=p.flat_times[test],residual_hz=r,
        marginal_sigma_hz=np.sqrt(np.diag(covariance)),position_covariance_included=True,
        unobserved_noise_groups_use_prior_not_their_own_residuals=True,
        Student_and_position_uncertainties_are_moment_matched_local_Gaussian_approximation=True)


def folds(p,keep):
    families=[]
    for j in p.labels:
        owners={p.scan.tracks[i]['receiver'] for row,i,sl in zip(p.rows,p.members,p.slices,strict=True) if row['candidate_index']==j and keep[sl].any()}
        counts=[int(keep[sl].sum()) for row,sl in zip(p.rows,p.slices,strict=True) if row['candidate_index']==j]
        if owners=={1,2}:families.append((sum(counts),j))
    if not families:return []
    # Largest cross-RX family, selected by active observations before new fits.
    _,j=max(families,key=lambda r:(r[0],-r[1]));result=[]
    for rx in (1,2):
        test=np.zeros(len(keep),bool)
        for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
            if row['candidate_index']==j and p.scan.tracks[i]['receiver']==rx:test[sl]=keep[sl]
        result.append(dict(family=j,receiver=rx,train=keep&~test,test=test))
    return result


def train_fit(scan,node,keep,powers,means,model):
    reference=np.zeros(len(means));x=np.zeros(2);history=[]
    for _ in range(3):
        p=make_problem(scan,node,keep,'c0',reference,powers,means,model['multiplier'],model['nu'])
        result=fit(p,x,iterations=24);x=np.asarray(result['parameters']);history.append(result)
        reference=np.clip(p.state(x)['phases'][p.labels],-15,15)
    return p,x,history


def run(case):
    scan0=final_scan(case);node0=read(SOURCE/case/'result.json')['final_node']
    learned=read(LEARNED/(case+'.json'));primary=learned['results']['mean_and_distribution']
    keep=np.array(primary['mask'],bool);model=learned['hyperparameters_from_pre_RF_TLE_only']
    base=problem(scan0,node0,'c0',keep);_,receipt=phase_widths(scan0,base.labels)
    means=forecast_phase_mean(receipt,model['shrinkage']);powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    selections=folds(base,keep);records=[];OUT.mkdir(parents=True,exist_ok=True)
    for method in METHODS:
        scan,node=expand(scan0,node0,method)
        for fold in selections:
            p,x,history=train_fit(scan,node,fold['train'],powers,means,model)
            try:
                prediction=predictive(p,x,fold['train'],fold['test'],powers,fold['family']);failure=None
            except np.linalg.LinAlgError as error:prediction=None;failure=str(error)
            records.append(dict(method=method,receiver=fold['receiver'],family_index=fold['family'],
                norad=int(scan.norads[fold['family']]),train_points=int(fold['train'].sum()),test_points=int(fold['test'].sum()),
                prediction=prediction,failure=failure,training_endpoint_east_north_km=x,training_history=history))
            print(case,method,'omit RX',fold['receiver'],'score',None if prediction is None else round(prediction['negative_twice_log_density'],3),flush=True)
            write(OUT/(case+'_partial.json'),dict(case=case,records=records,source_sha256=sha(Path(__file__))))
    selected='baseline';gains={}
    if selections:
        for method in METHODS[1:]:
            a=[r for r in records if r['method']=='baseline'];b=[r for r in records if r['method']==method]
            if all(r['prediction'] is not None for r in a+b):
                gain=[left['prediction']['negative_twice_log_density']-right['prediction']['negative_twice_log_density'] for left,right in zip(a,b,strict=True)]
                gains[method]=dict(per_receiver=gain,total=sum(gain),qualified=min(gain)>0 and sum(gain)>2*np.log(2))
        qualified=[m for m in gains if gains[m]['qualified']]
        if qualified:selected=max(qualified,key=lambda m:gains[m]['total'])
    full={};selected_pair=primary['arms'];fallback=False
    for method in METHODS[1:]:
        scan,node=expand(scan0,node0,method)
        pair={arm:refit(scan,node,keep,arm,powers,means,model['multiplier'],model['nu']) for arm in ('c0','fitted_c')}
        valid=all(t['compatible'] for r in pair.values() for t in r['gates']['tracks'])
        full[method]=dict(arms=pair,paired_valid=valid,policy_arms=pair if valid else primary['arms'])
        if method==selected:
            fallback=not valid;selected_pair=pair if valid else primary['arms']
    write(OUT/(case+'.json'),dict(case=case,records=records,gains=gains,selected=selected,
        selected_arms=selected_pair,selected_fallback=fallback,full_results=full,baseline=primary['arms'],
        fixed_mask=keep,powers=powers,GPS_used=False,source_sha256=sha(Path(__file__)),
        learned_input_sha256=sha(LEARNED/(case+'.json')),
        train_budget=dict(phase_rounds=3,position_steps=24,cold_start=[0,0]),
        full_pair_budget=dict(phase_rounds=5,position_steps=48,cold_start=[0,0]),
        validation_is_conditional_on_frozen_identities_aliases_and_radio_noise=True,
        withheld_RX_family_data_do_not_fit_position_or_nuisances_in_the_fold=True,
        folds_do_not_impose_production_two_owner_gate_on_withheld_families=True,
        every_original_point_restored_for_full_position_comparison=True))
    print(case,'selected',selected,'fallback',fallback,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
