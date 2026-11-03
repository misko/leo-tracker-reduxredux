"""Profile a shared UTC correction strictly inside the recorded host bracket."""

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

OUT=ROOT/'reports/2026_10_19_ds23_utc_bracket'
FRACTIONS=(-1.,-.5,0.,.5,1.)


def shift_geometry(p,delta):
    # These times query the ECEF orbit banks. Hardware and smooth designs
    # were already built from elapsed device time and remain unchanged.
    if not np.isfinite(delta):raise ValueError('finite UTC shift required')
    p.flat_times=np.asarray(p.flat_times)+delta
    return p


def refit_clock(scan,node,keep,arm,powers,means,multiplier,nu,delta):
    reference=np.zeros(len(means));anchor=np.zeros(2);history=[]
    for epoch in range(5):
        p=shift_geometry(make_problem(scan,node,keep,arm,reference,powers,means,multiplier,nu),delta)
        result=fit(p,anchor,iterations=48);anchor=np.array(result['parameters'])
        phase=p.state(anchor)['phases'][p.labels]
        history.append(dict(epoch=epoch,fit=result,phase_change_s=float(max(abs(phase-reference)))))
        reference=np.clip(phase,-15,15)
    c=p.calculate(anchor);residual=p.residual(anchor)
    return dict(endpoint_east_north_km=anchor,endpoint_latlon=latlon(anchor),score=float(residual@residual),
        negative_twice_elbo=c['negative_twice_elbo'],RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][keep]**2))),
        active_points=int(keep.sum()),gates=retained_metrics(p,anchor),history=history,state=p.state(anchor),
        phase_reference=reference,UTC_shift_s=delta)


def run(case):
    scan=final_scan(case);original=read(SOURCE/case/'result.json');node=original['final_node']
    source=read(LEARNED/(case+'.json'));assert not source['GPS_used']
    primary=source['results']['mean_and_distribution'];keep=np.array(primary['mask'],bool)
    metadata=read(SOURCE/case/'prepared.json')['metadata'];half=float(metadata['utc_half_width_s'])
    assert half>=0 and np.isfinite(half)
    assert metadata['anchor_utc_ns']==scan.receipt['origin_utc_ns']
    assert metadata['causal_cutoff_utc_ns']==scan.receipt['cutoff_utc_ns']
    assert abs((metadata['anchor_utc_ns']-metadata['causal_cutoff_utc_ns'])/1e9-half)<1e-8
    base=problem(scan,node,'c0',keep);_,receipts=phase_widths(scan,base.labels)
    model=source['hyperparameters_from_pre_RF_TLE_only'];means=forecast_phase_mean(receipts,model['shrinkage'])
    powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    records=[];OUT.mkdir(parents=True,exist_ok=True)
    for fraction in FRACTIONS:
        delta=fraction*half
        pair={arm:refit_clock(scan,node,keep,arm,powers,means,model['multiplier'],model['nu'],delta) for arm in ('c0','fitted_c')}
        valid=all(t['compatible'] for arm in pair for t in pair[arm]['gates']['tracks'])
        records.append(dict(fraction=fraction,delta_s=delta,arms=pair,paired_gates_pass=valid))
        candidates=[k for k,r in enumerate(records) if r['paired_gates_pass']]
        chosen=min(candidates,key=lambda k:(records[k]['arms']['c0']['negative_twice_elbo'],abs(records[k]['delta_s']),k)) if candidates else None
        write(OUT/(case+'.json'),dict(case=case,records=records,chosen=chosen,UTC_half_width_s=half,
            fractions=FRACTIONS,source_sha256=sha(Path(__file__)),GPS_used=False,
            metadata_sha256=sha(SOURCE/case/'prepared.json'),learned_input_sha256=sha(LEARNED/(case+'.json')),
            fixed_mask=keep,causal_cutoff_and_catalogue_unchanged=True,
            clock_is_shared_across_all_receivers_and_satellites=True,
            elapsed_hardware_times_and_independent_satellite_phase_priors_unchanged=True,
            selection='minimum c0 normalized generalized RF loss among paired-gate passing clock nodes',
            no_observation_trimming_inside_clock_search=True,partial=len(records)<len(FRACTIONS)))
        print(case,'UTC fraction',fraction,'delta',round(delta,5),'ELBO',round(pair['c0']['negative_twice_elbo'],3),'valid',valid,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
