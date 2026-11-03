"""Frame-matched native peaks as predictive-only position evidence.

New short/linear fragments never enter receiver or orbital calibration normal
equations. Every inference arm retains the frozen curved data and its full
shared nuisance covariance; no original point is removed or counted twice.
"""

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time

import numpy as np

from algo02_scan import pair_passes
from ds23_frame_peak_recovery import select_recoveries
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo03_frame_peak_recovery import context, SOURCE, REGISTRATION, METHODS
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_predictive_linear import refit
from run_algo01_ds23_sample import ROOT, read, write, sha
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis, whitening

OUT=ROOT/'reports/2026_10_19_algo03_frame_predictive'


def prepare(case):
    output=OUT/(case+'_selection.json')
    if output.exists():
        raise FileExistsError('preserve RF-only predictive selection')
    scan,node,mask,p,old=context(case)
    anchors={}
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        active=mask[sl];t=scan.tracks[i]
        if active.any():
            anchors[row['component']]=dict(receiver=t['receiver'],times=t['times'][active],
                values=t['values'][active],observation_ids=np.asarray(t['observation_ids'])[active].tolist())
    occupied={oid for t in anchors.values() for oid in t['observation_ids']}
    if old['linear_paired_valid']:
        occupied.update(oid for e in old['linear_entries'] for oid in e['observation_ids'])
    observations=read(SOURCE/case/'observations.json')
    registration=read(REGISTRATION/(case+'.json'))
    methods={}
    for method in METHODS:
        fragments,receipt=select_recoveries(case,anchors,observations,registration['pairs'],
            occupied,scan.fixed_window_noise,include_secondary=method=='additional_native_peaks',
            require_curvature=False)
        methods[method]=dict(fragments=fragments,receipt=receipt)
    write(output,dict(case=case,methods=methods,no_GPS_TLE_or_position_used_for_selection=True,
        all_new_peaks_predictive_only_even_if_curved=True,occupied_original_measurements=sorted(occupied),
        baseline_sha256=sha(SOURCE/case/'algo02_result.json'),
        registration_sha256=sha(REGISTRATION/(case+'.json')),
        helper_sha256=sha(ROOT/'tools/ds23_frame_peak_recovery.py')))
    return dict(case=case,methods={m:dict(fragments=len(r['fragments']),
        added_original=r['receipt']['added_original_winners'],
        added_native=r['receipt']['added_native_secondary_peaks']) for m,r in methods.items()})


def append_predictions(scan,base,old,fragments):
    modified=copy.copy(scan)
    modified.tracks=list(scan.tracks);modified.index=list(scan.index)
    modified.white=list(scan.white);modified.rx_basis=list(scan.rx_basis)
    modified.fixed_window_noise=copy.deepcopy(scan.fixed_window_noise)
    metadata=modified.fixed_window_noise
    if metadata['extra_parameter_BIC_gain']<=0:
        metadata['per_observation_noise_sigma_hz'].update({oid:scan.radio_sigma_hz
            for t in scan.tracks for oid in t['observation_ids']})
        metadata['extra_parameter_BIC_gain']=1.
    entries=copy.deepcopy(old['linear_entries']) if old['linear_paired_valid'] else []
    lookup={r['component']:(k,r) for k,r in enumerate(base.rows)}
    owner_sets={j:{scan.tracks[i]['receiver'] for r,i,sl in zip(base.rows,base.members,base.slices,strict=True)
        if r['candidate_index']==j and base.keep[sl].any()} for j in base.labels}
    for fragment in fragments:
        k,parent=lookup[fragment['parent_component']]
        t=dict(fragment,times=np.asarray(fragment['times']),values=np.asarray(fragment['values']))
        i=len(modified.tracks);modified.tracks.append(t)
        modified.index.append(np.searchsorted(scan.times,t['times']))
        modified.white.append(whitening(t['times']));modified.rx_basis.append(projected_receiver_basis(t['times']))
        metadata['per_observation_noise_sigma_hz'].update(zip(t['observation_ids'],t['sigma_hz'],strict=True))
        entries.append(dict(track_index=i,component=t['key'],candidate_index=parent['candidate_index'],
            norad=parent['candidate_norad'],alias=base.alias[k],points=len(t['times']),
            cross_receiver_curved_support=len(owner_sets[parent['candidate_index']])==2,
            observation_ids=t['observation_ids'],association_source='native_frame_epoch'))
    ids=[oid for e in entries for oid in e['observation_ids']]
    original_ids={oid for row,i,sl in zip(base.rows,base.members,base.slices,strict=True)
                  for oid in np.asarray(scan.tracks[i]['observation_ids'])[base.keep[sl]]}
    if len(ids)!=len(set(ids)) or set(ids)&original_ids:
        raise ValueError('predictive evidence has duplicate original ownership')
    # Preserve the exact original curved graph, nuisance design and support.
    if modified.curved!=scan.curved:
        raise ValueError('new predictive points cannot calibrate receiver or orbit modes')
    return modified,entries


def run(case):
    output=OUT/(case+'_position.json')
    if output.exists():
        raise FileExistsError('preserve paired predictive experiment')
    selected=read(OUT/(case+'_selection.json'))
    if selected['helper_sha256']!=sha(ROOT/'tools/ds23_frame_peak_recovery.py'):
        raise ValueError('RF selection helper changed')
    scan,node,mask,p,old=context(case);model=old['hyperparameters_from_pre_RF_TLE_only']
    powers=np.asarray(old['weights']);_,receipts=phase_widths(scan,p.labels)
    means=forecast_phase_mean(receipts,model['shrinkage']);results={};started=time.monotonic()
    for method in METHODS:
        fragments=selected['methods'][method]['fragments']
        if not fragments:
            results[method]=dict(no_change=True,policy_arms=old['policy_arms'])
            continue
        changed,entries=append_predictions(scan,p,old,fragments)
        pair={arm:refit(changed,node,mask,powers,means,model,arm,entries) for arm in ('c0','fitted_c')}
        valid=pair_passes(pair,include_linear=True)
        results[method]=dict(paired_valid=valid,trial_arms=pair,entries=entries,
            offered_fragments=len(fragments),offered_points=sum(len(f['times']) for f in fragments),
            policy_arms=pair if valid else old['policy_arms'])
        write(OUT/(case+'_partial.json'),dict(case=case,results=results))
        print(case,method,'fragments',len(fragments),'valid',valid,flush=True)
    write(output,dict(case=case,results=results,baseline_arms=old['policy_arms'],
        selection_sha256=sha(OUT/(case+'_selection.json')),seconds=time.monotonic()-started,
        no_GPS_postscan_TLE_previous_scan_position_or_manually_selected_satellite_used=True,
        no_new_point_enters_calibration_normal_equations=True,
        original_curved_data_aliases_identities_noise_powers_and_priors_unchanged=True,
        original_valid_linear_entries_retained=True,
        paired_c_data_hypotheses_and_search_budgets_matched=True))
    return dict(case=case,seconds=time.monotonic()-started,
        accepted={m:r.get('paired_valid',False) for m,r in results.items()})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['prepare','fit'],required=True)
    parser.add_argument('--cases',nargs='+');parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    cases=args.cases or ['DS23-0202','DS23-0274']
    if args.stage=='prepare':
        OUT.mkdir(exist_ok=True)
        if (OUT/'protocol.json').exists():
            raise FileExistsError('preserve predictive recovery protocol')
        write(OUT/'protocol.json',dict(cases=cases,methods=METHODS,workers=args.workers,
            source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/'tools/ds23_frame_peak_recovery.py'),
            require_curvature_for_new_calibration=True,new_peaks_are_predictive_only=True,
            max_degree=4,minimum_points=8,minimum_span_s=6.,maximum_gap_s=10.,
            noise_floor_hz=150.,new_curve_bias_prior_sigma_hz=300.,
            no_new_peak_ownership_overlaps=True,no_GPS_hyperparameter_selection=True,
            paired_c0_fitted_c_same_data_labels_priors_noise_and_cold_start_budgets=True))
    results=[]
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        for future in as_completed([executor.submit(prepare if args.stage=='prepare' else run,c) for c in cases]):
            result=future.result();results.append(result);print(result,flush=True)
    write(OUT/(args.stage+'_execution.json'),dict(results=results))


if __name__=='__main__':
    main()
