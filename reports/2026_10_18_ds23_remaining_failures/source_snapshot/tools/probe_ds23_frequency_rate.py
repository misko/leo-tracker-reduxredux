"""Test a missing receiver clock-rate mode: drift proportional to RF within band."""

import argparse
import copy
from pathlib import Path
import numpy as np

from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import HISTORY,refit
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha,final_scan

OUT=ROOT/'reports/2026_10_18_ds23_frequency_rate'


def frequency_rate_basis(times,rf_hz,center_hz,sigma_hz_per_s_GHz):
    # Existing receiver-basis features are multiplied by q*200 Hz. Divide
    # here so the new physical mode is sigma*(t-150)*delta_RF_GHz Hz.
    return sigma_hz_per_s_GHz*(np.asarray(times)-150)*(rf_hz-center_hz)/1e9/(200*(rf_hz/11.5e9))


def augment_scan(scan,sigma):
    changed=copy.copy(scan)
    centers={}
    for rx in (1,2):
        for band in (0,1):
            frequencies={t['rf_hz'] for t in scan.tracks if t['receiver']==rx and int(t['channel']>4)==band}
            if frequencies:centers[(rx,band)]=float(np.mean(sorted(frequencies)))
    changed.rx_basis=[]
    for track,basis in zip(scan.tracks,scan.rx_basis,strict=True):
        center=centers[(track['receiver'],int(track['channel']>4))]
        extra=frequency_rate_basis(track['times'],track['rf_hz'],center,sigma)
        changed.rx_basis.append(np.column_stack((basis,extra)))
    return changed,centers


def augment_node(node):
    changed=copy.deepcopy(node)
    old=np.asarray(changed['seed']['state']['smooth'])
    changed['seed']['state']['smooth']=np.column_stack((old,np.zeros(2)))
    return changed


def run(case):
    original_scan=final_scan(case);original=read(SOURCE/case/'result.json')
    node=original['final_node'];keep0=np.array(original['final_mask'],bool)
    base=problem(original_scan,node,'c0',keep0)
    forecast=read(HISTORY/(case+'_forecast.json'))
    assert forecast['strictly_pre_RF'] and not forecast['GPS_or_radio_used']
    v,b=forecast['distribution_validation'],forecast['original_distribution_validation']
    model=forecast['all_past_distribution'] if v['count']>=30 and v['negative_twice_log_density']<b['negative_twice_log_density'] else dict(shrinkage=0.,multiplier=1.,nu=None)
    _,receipts=phase_widths(original_scan,base.labels);means=forecast_phase_mean(receipts,model['shrinkage'])
    weights=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    results={};centers=None
    for sigma in (0.,.25,1.):
        scan,centers=augment_scan(original_scan,sigma);keep=keep0.copy();history=[]
        expanded_node=augment_node(node)
        for epoch in range(4):
            pair={arm:refit(scan,expanded_node,keep,arm,weights,means,model['multiplier'],model['nu']) for arm in ('c0','fitted_c')}
            failed={r['component'] for arm in pair for r in pair[arm]['gates']['tracks'] if not r['compatible']}
            history.append(dict(epoch=epoch,points=int(keep.sum()),failed=sorted(failed)))
            if not failed or epoch==3:break
            for row,sl in zip(base.rows,base.slices,strict=True):
                if row['component'] in failed:keep[sl]=False
        results[str(sigma)]=dict(arms=pair,mask=keep,history=history,valid=not failed,
            frequency_rate_prior_sigma_hz_per_s_GHz=sigma,
            posterior_rate_hz_per_s_GHz={arm:np.array(r['state']['smooth'])[:,-1]/200*sigma for arm,r in pair.items()})
        print(case,'sigma',sigma,int(keep.sum()),'valid',not failed,flush=True)
    OUT.mkdir(parents=True,exist_ok=True)
    write(OUT/(case+'.json'),dict(case=case,results=results,centers_hz={str(k):v for k,v in centers.items()},
        GPS_used=False,source_sha256=sha(Path(__file__)),forecast_sha256=sha(HISTORY/(case+'_forecast.json')),
        physical_hypothesis='one RF-dependent within-band linear frequency drift per receiver',
        other_priors_labels_aliases_initial_data_and_c_pair_budgets_preserved=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
