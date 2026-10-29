"""Partial RF-only effective-time control after archived pilot refinement."""

import argparse
import copy
from pathlib import Path
import numpy as np
from ds23_refined_noise import learn_noise
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED
from probe_ds23_raw_pilot_refinement import OUT as RAW
from probe_ds23_refined_curve_position import update_values,proposed_delta
from probe_ds23_refined_restoration import restoration_mask
from probe_ds23_refined_precision import OUT,refit
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,final_scan,read,write,sha
from leo.analysis.research.phase_linear_geometry import prepare_phase_geometry
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis,whitening


def apply_effective_times(scan,rows):
    offsets={}
    for r in rows:
        if proposed_delta(r,'joint_CFO_epoch_rate')[1]!='refined':continue
        time=r['joint_CFO_epoch_rate']['effective_time_from_probe_start_s']
        if time is None or not np.isfinite(time) or not 0<=time<=.020:
            raise ValueError('effective CFO instant must lie in the original 20 ms support')
        offsets[r['point']['observation_id']]=time-.010
    for t in scan.tracks:
        t['times']=t['times']+np.array([offsets.get(oid,0.) for oid in t['observation_ids']])
        if np.any(np.diff(t['times'])<=0):raise ValueError('effective instants changed curve order')
    scan.times=np.unique(np.concatenate([t['times'] for t in scan.tracks]))
    scan.index=[np.searchsorted(scan.times,t['times']) for t in scan.tracks]
    scan.geometry=prepare_phase_geometry(scan.sky,scan.times)
    scan.white=[whitening(t['times']) for t in scan.tracks]
    scan.ou=[whitening(t['times'],correlated_sigma_hz=150.,correlation_seconds=10.) for t in scan.tracks]
    scan.rx_basis=[projected_receiver_basis(t['times']) for t in scan.tracks]
    return offsets


def run(case):
    raw=read(RAW/(case+'_tracks.json'));scan=final_scan(case)
    learned=read(LEARNED/(case+'.json'));primary=learned['results']['mean_and_distribution']
    original=np.array(primary['mask'],bool);node=read(SOURCE/case/'result.json')['final_node']
    model=learned['hyperparameters_from_pre_RF_TLE_only']
    powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
    p=problem(scan,node,'c0',original);_,receipts=phase_widths(scan,p.labels)
    means=forecast_phase_mean(receipts,model['shrinkage'])
    keep,restored=restoration_mask(scan,p,original,{r['point']['observation_id'] for r in raw['rows']})
    by_id,radio=learn_noise(raw);modified=copy.deepcopy(scan)
    updates=update_values(modified,raw['rows'],'joint_CFO_epoch_rate')
    offsets=apply_effective_times(modified,raw['rows'])
    pair={arm:refit(modified,node,keep,arm,powers,means,model,by_id) for arm in ('c0','fitted_c')}
    failed={r['component'] for a in pair.values() for r in a['gates']['tracks'] if not r['compatible']}
    write(OUT/(case+'_times.json'),dict(case=case,trial_arms=pair,paired_valid=not failed,failed_tracks=sorted(failed),
        reported_arms=pair if not failed else primary['arms'],restored=restored,mask=keep,offsets_s=offsets,
        radio_noise_receipts=radio,GPS_used=False,paired_c=True,no_original_point_removed=True,
        original_aliases_and_physical_priors_preserved=True,instant_inside_original_measurement_support=True,
        source_sha256=sha(Path(__file__)),raw_sha256=sha(RAW/(case+'_tracks.json'))))
    print(case,'timing paired valid',not failed,'failed',len(failed),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
