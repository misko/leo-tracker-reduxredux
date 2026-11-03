"""Fixed-data regional restarts for the non-Gaussian causal-prior objective."""

import argparse
from pathlib import Path
import numpy as np

from audit_ds23_algo01_coverage import retained_metrics
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED,make_problem
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha,final_scan

OUT=ROOT/'reports/2026_10_18_ds23_learned_prior_restarts'
STARTS=[(0.,0.),(-5.,0.),(5.,0.),(0.,-5.),(0.,5.),(-10.,0.),(10.,0.),(0.,-10.),(0.,10.),(-5.,-5.),(-5.,5.),(5.,-5.),(5.,5.)]


def refit_start(scan,node,keep,arm,weights,means,multiplier,nu,start):
    reference=np.zeros(len(means));anchor=np.array(start);history=[]
    for epoch in range(5):
        p=make_problem(scan,node,keep,arm,reference,weights,means,multiplier,nu)
        result=fit(p,anchor,iterations=48);anchor=np.array(result['parameters'])
        phase=p.state(anchor)['phases'][p.labels]
        history.append(dict(epoch=epoch,fit=result,phase_change_s=float(max(abs(phase-reference)))))
        reference=np.clip(phase,-15,15)
    c=p.calculate(anchor);r=p.residual(anchor)
    return dict(endpoint_east_north_km=anchor,endpoint_latlon=latlon(anchor),score=float(r@r),
        negative_twice_elbo=c['negative_twice_elbo'],RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))),
        active_points=int(keep.sum()),gates=retained_metrics(p,anchor),history=history,state=p.state(anchor),phase_reference=reference)


def run(case):
    scan=final_scan(case);original=read(SOURCE/case/'result.json');node=original['final_node']
    learned=read(LEARNED/(case+'.json'));keep=np.array(learned['results']['mean_and_distribution']['mask'],bool)
    model=learned['hyperparameters_from_pre_RF_TLE_only']
    p=problem(scan,node,'c0',keep);_,receipts=phase_widths(scan,p.labels)
    means=forecast_phase_mean(receipts,model['shrinkage'])
    weights=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    records=[];OUT.mkdir(parents=True,exist_ok=True)
    for start in STARTS:
        pair={arm:refit_start(scan,node,keep,arm,weights,means,model['multiplier'],model['nu'],start) for arm in ('c0','fitted_c')}
        valid=all(r['compatible'] for arm in pair for r in pair[arm]['gates']['tracks'])
        records.append(dict(start=start,arms=pair,paired_gates_pass=valid))
        valid_indices=[k for k,r in enumerate(records) if r['paired_gates_pass']]
        chosen=min(valid_indices,key=lambda k:(records[k]['arms']['c0']['score'],k)) if valid_indices else None
        write(OUT/(case+'.json'),dict(case=case,records=records,chosen=chosen,fixed_mask=keep,GPS_used=False,
            no_identity_changes_or_mask_trimming_inside_this_control=True,
            paired_c_selection_uses_only_c0_loss_on_identical_data=True,source_sha256=sha(Path(__file__)),
            prior_input_sha256=sha(LEARNED/(case+'.json')),planned_starts=STARTS))
        print(case,start,'score',round(pair['c0']['score'],4),'valid',valid,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
