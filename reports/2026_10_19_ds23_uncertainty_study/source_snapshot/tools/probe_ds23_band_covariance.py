"""Variance-matched common versus per-band receiver smooth corrections."""

import argparse
import copy
from pathlib import Path
import numpy as np

from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED,refit
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha,final_scan

OUT=ROOT/'reports/2026_10_19_ds23_band_covariance'


def split_basis(basis,band,rho):
    basis=np.asarray(basis,float)
    if basis.ndim!=2 or not np.isfinite(basis).all() or band not in (0,1) or not np.isfinite(rho) or not 0<=rho<=1:
        raise ValueError('finite matrix, band 0/1 and correlation in [0,1] required')
    if rho==1:return basis.copy()
    zero=np.zeros_like(basis)
    low=basis if band==0 else zero;high=basis if band==1 else zero
    if rho==0:return np.column_stack((low,high))
    return np.column_stack((np.sqrt(rho)*basis,np.sqrt(1-rho)*low,np.sqrt(1-rho)*high))


def split_seed(values,rho):
    values=np.asarray(values,float)
    if rho==1:return values.copy()
    if rho==0:return np.column_stack((values,values))
    return np.column_stack((np.sqrt(rho)*values,np.sqrt(1-rho)*values,np.sqrt(1-rho)*values))


def augment(scan,node,rho):
    changed=copy.copy(scan);changed_node=copy.deepcopy(node)
    changed.rx_basis=[split_basis(b,int(t['channel']>4),rho) for b,t in zip(scan.rx_basis,scan.tracks,strict=True)]
    changed_node['seed']['state']['smooth']=split_seed(node['seed']['state']['smooth'],rho)
    return changed,changed_node


def run(case):
    scan0=final_scan(case);original=read(SOURCE/case/'result.json');node=original['final_node']
    keep0=np.array(original['final_mask'],bool);base=problem(scan0,node,'c0',keep0)
    learned=read(LEARNED/(case+'.json'));assert not learned['GPS_used']
    model=learned['hyperparameters_from_pre_RF_TLE_only']
    _,receipts=phase_widths(scan0,base.labels);means=forecast_phase_mean(receipts,model['shrinkage'])
    weights=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    results={}
    for rho in (1.,.5,0.):
        scan,expanded_node=augment(scan0,node,rho);keep=keep0.copy();history=[]
        for epoch in range(4):
            pair={arm:refit(scan,expanded_node,keep,arm,weights,means,model['multiplier'],model['nu']) for arm in ('c0','fitted_c')}
            failed={r['component'] for arm in pair for r in pair[arm]['gates']['tracks'] if not r['compatible']}
            history.append(dict(epoch=epoch,points=int(keep.sum()),failed=sorted(failed)))
            if not failed or epoch==3:break
            for row,sl in zip(base.rows,base.slices,strict=True):
                if row['component'] in failed:keep[sl]=False
        results[str(rho)]=dict(arms=pair,mask=keep,history=history,valid=not failed,cross_band_prior_correlation=rho)
        print(case,'rho',rho,int(keep.sum()),'valid',not failed,flush=True)
    OUT.mkdir(parents=True,exist_ok=True)
    write(OUT/(case+'.json'),dict(case=case,results=results,GPS_used=False,
        source_sha256=sha(Path(__file__)),learned_input_sha256=sha(LEARNED/(case+'.json')),
        each_band_marginal_smooth_variance_unchanged=True,linear_drift_priors_unchanged=True,
        within_band_covariance_unchanged=True,aliases_labels_initial_data_and_c_pair_budgets_matched=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
