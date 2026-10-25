"""Paired-c recovery of unused opposite-RX native curved evidence."""

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time

import numpy as np

from algo02_scan import bind_run_directory, load_scan, pair_passes
from audit_ds23_algo01_coverage import retained_metrics
from ds23_frame_peak_recovery import select_recoveries
from ds23_predictive_linear import attach_predictive_linear
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from investigate_dsx01_localization_failures import fit
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_predictive_linear import select_entries
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, read, write, sha
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import profile, projected_receiver_basis, whitening

SOURCE=ROOT/'reports/2026_10_19_algo02_ds23_full'
REGISTRATION=ROOT/'reports/2026_10_19_algo03_frame_registration_v2'
OUT=ROOT/'reports/2026_10_19_algo03_frame_peak_recovery'
METHODS=('unassociated_winners','additional_native_peaks')
ARMS=('c0','fitted_c')


def context(case):
    bind_run_directory(SOURCE)
    scan=load_scan(SOURCE,case)
    original=read(SOURCE/case/'result.json');old=read(SOURCE/case/'algo02_result.json')
    node=original['final_node'];mask=np.asarray(old['mask'],bool)
    p=problem(scan,node,'c0',mask)
    return scan,node,mask,p,old


def prepare(case):
    path=OUT/(case+'_selection.json')
    if path.exists():
        raise FileExistsError('preserve independent RF selection')
    scan,node,mask,p,old=context(case)
    anchors={}
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        active=mask[sl];track=scan.tracks[i]
        if active.any():
            anchors[row['component']]=dict(receiver=track['receiver'],
                times=track['times'][active],values=track['values'][active],
                observation_ids=np.asarray(track['observation_ids'])[active].tolist())
    occupied={oid for track in anchors.values() for oid in track['observation_ids']}
    if old['linear_paired_valid']:
        occupied.update(oid for e in old['linear_entries'] for oid in e['observation_ids'])
    registration=read(REGISTRATION/(case+'.json'))
    observations=read(SOURCE/case/'observations.json')
    methods={}
    for method in METHODS:
        fragments,receipt=select_recoveries(case,anchors,observations,registration['pairs'],
            occupied,scan.fixed_window_noise,include_secondary=method=='additional_native_peaks')
        methods[method]=dict(fragments=fragments,receipt=receipt)
    write(path,dict(case=case,methods=methods,no_GPS_position_or_TLE_used_for_peak_selection=True,
        occupied_original_measurements=sorted(occupied),registration_sha256=sha(REGISTRATION/(case+'.json')),
        baseline_sha256=sha(SOURCE/case/'algo02_result.json'),source_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/'tools/ds23_frame_peak_recovery.py')))
    return dict(case=case,methods={key:dict(fragments=len(value['fragments']),
        **value['receipt']) for key,value in methods.items()})


def augment(scan,node,mask,base,weights,fragments):
    changed=copy.copy(scan);changed.tracks=list(scan.tracks);changed.curved=list(scan.curved)
    changed.groups=list(scan.groups);changed.index=list(scan.index);changed.white=list(scan.white)
    changed.rx_basis=list(scan.rx_basis);changed.causal_uncertainty_modes={}
    changed.fixed_window_noise=copy.deepcopy(scan.fixed_window_noise)
    metadata=changed.fixed_window_noise;by_id=metadata['per_observation_noise_sigma_hz']
    if metadata['extra_parameter_BIC_gain']<=0:
        by_id.update({oid:scan.radio_sigma_hz for t in scan.tracks for oid in t['observation_ids']})
        # Explicit research per-ID overrides for new peaks, preserving every
        # original noise value. This does not refit the radio noise law.
        metadata['extra_parameter_BIC_gain']=1.
    copied=copy.deepcopy(node);keep=mask.copy();powers=list(weights)
    row_lookup={r['component']:(k,r) for k,r in enumerate(base.rows)}
    for fragment in fragments:
        parent_k,parent=row_lookup[fragment['parent_component']]
        t=dict(fragment,times=np.asarray(fragment['times']),values=np.asarray(fragment['values']))
        i=len(changed.tracks);changed.tracks.append(t);changed.curved.append(i)
        changed.groups.append((t['key'],[t]));changed.index.append(np.searchsorted(scan.times,t['times']))
        if not np.allclose(scan.times[changed.index[-1]],t['times'],atol=1e-8,rtol=0):
            raise ValueError('recovered samples must have simultaneous original time support')
        changed.white.append(whitening(t['times']))
        changed.rx_basis.append(projected_receiver_basis(t['times']))
        by_id.update(zip(t['observation_ids'],t['sigma_hz'],strict=True))
        copied['seed']['rows'].append(dict(parent,component=t['key'],points=len(t['times']),
            active_curvature=True,association_source='RF_frame_epoch_recovery'))
        copied['aliases'].append(base.alias[parent_k])
        keep=np.r_[keep,np.ones(len(t['times']),bool)]
        powers.append(float(weights[parent_k]))
    return changed,copied,keep,np.asarray(powers)


def refit(scan,node,mask,powers,means,model,arm,entries=()):
    reference=np.zeros(len(means));x=np.zeros(2);history=[]
    for _ in range(5):
        p=make_problem(scan,node,mask,arm,reference,powers,means,model['multiplier'],model['nu'])
        attach_predictive_linear(p,entries,powers)
        result=fit(p,x,iterations=48);x=np.asarray(result['parameters'])
        phase=np.clip(p.state(x)['phases'][p.labels],-15,15)
        history.append(dict(fit=result,phase_change_s=float(max(abs(phase-reference)))))
        reference=phase
    c=p.calculate(x);curved=p.curved_calculate(x) if entries else c;linear_gates=[]
    for e,sl in zip(entries,getattr(p,'linear_slices',[]),strict=True):
        t=scan.tracks[e['track_index']];raw=c['linear_raw_prediction_residual_hz'][sl]
        terms=profile(raw,np.zeros(len(raw)),*scan.white[e['track_index']],bias_sigma=300.)
        noise=batch_noise_screen(terms['innovations'],t['times'])
        valid=bool(terms['rms'][0]<=450 and abs(terms['bias'][0])<=3000 and int(terms['alias'][0])==0
            and noise['noise_screen_pass'][0] and min(c['linear_elevation'][sl])>=0)
        linear_gates.append(dict(component=e['component'],compatible=valid,points=e['points'],
            observation_ids=e['observation_ids'],rms_hz=float(terms['rms'][0]),bias_hz=float(terms['bias'][0])))
    return dict(endpoint_east_north_km=x,endpoint_latlon=latlon(x),history=history,
        state=p.state(x),phase_reference=p.reference,gates=retained_metrics(p,x),linear_gates=linear_gates,
        final_phase_change_s=history[-1]['phase_change_s'],active_points=int(mask.sum()),
        additional_predictive_points=sum(e['points'] for e in entries),
        RMS_hz=float(np.sqrt(np.mean(c['conditional_residual_hz'][mask]**2))),
        negative_twice_elbo=c['negative_twice_elbo'],curved_negative_twice_elbo=curved['negative_twice_elbo'],
        linear_calibration_max_difference=float(max(abs(c['coefficient']-curved['coefficient']))))


def run(case, *, output_dir=None):
    destination=OUT if output_dir is None else Path(output_dir)
    output=destination/(case+'_position.json')
    if output.exists():
        raise FileExistsError('preserve bounded recovery hypothesis results')
    selection=read(destination/(case+'_selection.json'))
    if selection['helper_sha256']!=sha(ROOT/'tools/ds23_frame_peak_recovery.py'):
        raise ValueError('peak selection helper changed')
    scan,node,mask,base,old=context(case);model=old['hyperparameters_from_pre_RF_TLE_only']
    weights=np.asarray(old['weights']);_,receipts=phase_widths(scan,base.labels)
    means=forecast_phase_mean(receipts,model['shrinkage']);results={};started=time.monotonic()
    for method in METHODS:
        offered=selection['methods'][method]['fragments'];remaining=list(offered);steps=[];curved=None
        if not remaining:
            results[method]=dict(no_change=True,policy_arms=old['policy_arms'],offered_fragments=0)
            continue
        for gate_round in range(3):
            modified,copied,keep,powers=augment(scan,node,mask,base,weights,remaining)
            pair={arm:refit(modified,copied,keep,powers,means,model,arm) for arm in ARMS}
            failed={r['component'] for arm in ARMS for r in pair[arm]['gates']['tracks'] if not r['compatible']}
            steps.append(dict(round=gate_round,fragments=[f['key'] for f in remaining],
                failed=sorted(failed),arms=pair))
            print(case,method,'curved round',gate_round,'offered',len(remaining),'failed',len(failed),flush=True)
            if pair_passes(pair) and all(v['final_phase_change_s']<=.01 for v in pair.values()):
                curved=pair;break
            removable=failed&{f['key'] for f in remaining}
            if not removable:
                break
            remaining=[f for f in remaining if f['key'] not in removable]
            if not remaining:
                break
        result=dict(offered_fragments=len(offered),curved_gate_steps=steps,curved_paired_valid=curved is not None,
            recovered_fragments=remaining if curved is not None else [],policy_arms=old['policy_arms'])
        if curved is not None:
            p=make_problem(modified,copied,keep,'c0',np.asarray(curved['c0']['phase_reference']),
                powers,means,model['multiplier'],model['nu'])
            x=np.asarray(curved['c0']['endpoint_east_north_km']);entries=select_entries(p,x,retained_metrics(p,x))
            linear={arm:refit(modified,copied,keep,powers,means,model,arm,entries) for arm in ARMS}
            valid=pair_passes(linear,include_linear=True)
            result.update(curved_arms=curved,linear_arms=linear,linear_entries=entries,
                linear_paired_valid=valid,policy_arms=linear if valid else curved,
                fallback=None if valid else 'new_curved_pair')
        results[method]=result
        write(destination/(case+'_partial.json'),dict(case=case,results=results))
    write(output,dict(case=case,results=results,baseline_policy_arms=old['policy_arms'],
        selection_sha256=sha(destination/(case+'_selection.json')),seconds=time.monotonic()-started,
        no_GPS_postscan_TLE_or_previous_scan_position_used=True,
        original_curved_mask_labels_aliases_noise_powers_and_prior_scales_preserved=True,
        native_recovered_curves_use_same_300Hz_bias_prior=True,
        new_physical_cross_RX_support_can_enable_existing_three_orbit_modes=True,
        no_original_measurement_trimmed=True,linear_measurements_never_calibrate_nuisance=True,
        matched_c0_fitted_c_data_and_search_budgets=True))
    return dict(case=case,seconds=time.monotonic()-started,
        accepted={m:r.get('curved_paired_valid',False) for m,r in results.items()})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['prepare','fit'],required=True)
    parser.add_argument('--cases',nargs='+');parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args()
    cases=args.cases or ['DS23-0202','DS23-0274']
    if args.stage=='prepare':
        OUT.mkdir(exist_ok=True)
        protocol=OUT/'protocol.json'
        if protocol.exists():
            raise FileExistsError('preserve paired recovery protocol')
        write(protocol,dict(cases=cases,source_sha256=sha(Path(__file__)),
            helper_sha256=sha(ROOT/'tools/ds23_frame_peak_recovery.py'),
            comparison_methods=METHODS,workers=args.workers,
            minimum_curved_span_s=20.,max_interpoint_gap_s=10.,max_degree=4,
            curvature_BIC_gain=10.,extra_peak_noise_floor_hz=150.,
            retained_original_peaks_excluded=True,ambiguous_peak_owners_rejected=True,
            RF_selection_sealed_before_new_position_fits=True,no_GPS_hyperparameter_choice=True,
            paired_c0_fitted_c_same_data_labels_noise_and_cold_start_budgets=True))
    receipts=[]
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        for future in as_completed([executor.submit(prepare if args.stage=='prepare' else run,c) for c in cases]):
            result=future.result();receipts.append(result);print(result,flush=True)
    write(OUT/(args.stage+'_execution.json'),dict(receipts=receipts))


if __name__=='__main__':
    main()
