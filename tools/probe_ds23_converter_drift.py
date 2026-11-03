"""Matched causal position fits under fixed recorded-converter drift loadings."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import time
import numpy as np

from algo02_scan import pair_passes
from ds23_converter_drift import change_scan
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_fft_grid_position import setup
from probe_ds23_frequency_events import refit
from probe_algo03_frame_peak_recovery import SOURCE
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_converter_drift'
ARMS=('c0','fitted_c')
LAWS=('LNB','tuner')


def hashes():
    return {str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),ROOT/'tools/ds23_converter_drift.py',
        ROOT/'tools/ds23_frequency_events.py',ROOT/'tools/probe_ds23_frequency_events.py')}


def prepare():
    OUT.mkdir(exist_ok=True);path=OUT/'protocol.json'
    if path.exists():
        p=read(path)
        if p['source_sha256']!=hashes():raise ValueError('frozen converter experiment changed')
        return p
    metadata=read(OUT/'metadata_export.json')
    if not metadata['all_terminal'] or metadata['count']!=40:raise ValueError('all converter metadata must be sealed first')
    previous=read(ROOT/'reports/2026_10_20_ds23_excluded_catalogue/calibration_protocol.json')
    p=dict(development_cases=previous['development_cases'],confirmation_cases=previous['confirmation_cases'],
        pilot_cases=previous['pilot_cases'],source_sha256=hashes(),workers=24,
        hypothesis='receiver nonlinear drift can follow LNB reference or tuner frequency instead of total RF',
        laws=list(LAWS),original_law='RF/11.5GHz',
        prior_normalization='match mean squared loading across every immutable configured channel/edge target, independent of point counts and position',
        no_added_nuisance_coordinates=True,all_Doppler_RF_scales_unchanged=True,
        all_masks_points_noise_powers_aliases_satellite_labels_and_other_priors_fixed=True,
        conditional_on_recorded_RF_mapping_hypotheses_not_independent_LO_measurement=True,
        numerical_controls=['saved signed-incumbent endpoint replay','exact RF-law basis null','matched cold RF-law refit'],
        c_pair_matching='same physical law, metadata, observations, calibration rules and budgets',
        cold_start_km=[0,0],box_width_km=25,phase_rounds=5,position_iterations=48,
        fixed_policy='adopt the specified law only if original curved/predictive gates and true phase/reference <=.01 within +/-15s pass in BOTH c arms; otherwise exact signed-incumbent fallback',
        RF_selection='lowest c0 full bound among qualified LNB/tuner proposals, requiring both gains >2log3 versus best valid saved/cold RF null; exact incumbent otherwise',
        primary='fixed LNB law improves fitted-c mean AND median in BOTH cohorts; disclose fixed tuner and RF-selected policies plus c0',
        same_cohort_previously_exposed_not_untouched_locations=True,
        earlier_additive_law_negative_on_original20_not_new_claim=True,
        no_GPS_future_TLE_new_RF_cross_scan_position_prior_or_satellite_preselection=True,
        metadata_bindings={case:sha(OUT/(case+'_converter.json')) for case in previous['development_cases']+previous['confirmation_cases']},
        goal_population=413)
    write(path,p);return p


def valid(pair,labels):
    return bool(pair_passes(pair,include_linear=True) and all(
        np.max(abs(np.asarray(r['state']['phases'])[labels]))<=15 and
        np.max(abs(np.asarray(r['state']['phases'])[labels]-np.asarray(r['phase_reference'])))<=.01
        for r in pair.values()))


def run(case):
    protocol=prepare();path=OUT/(case+'_result.json')
    if path.exists():return dict(case=case,cached=True)
    began=time.monotonic();metadata_path=OUT/(case+'_converter.json')
    if sha(metadata_path)!=protocol['metadata_bindings'][case]:raise ValueError('converter metadata changed')
    metadata=read(metadata_path);geometry=metadata['geometry']
    scan,node,keep,base,old,signed,binding,model,powers,means,entries=setup(case)
    incumbent=signed['policy_arms'];null_scan,null_receipt=change_scan(scan,geometry,'RF')
    for a,b in zip(scan.rx_basis,null_scan.rx_basis,strict=True):np.testing.assert_array_equal(a,b)
    old_replays=[]
    for arm in ARMS:
        r=incumbent[arm]
        p=make_event_problem(null_scan,node,keep,arm,np.asarray(r['phase_reference']),powers,means,model,[])
        attach_event_predictive(p,entries,powers)
        delta=p.calculate(np.asarray(r['endpoint_east_north_km']))['negative_twice_elbo']-r['negative_twice_elbo']
        if abs(delta)>1e-3:raise ValueError('unchanged RF law failed incumbent replay')
        old_replays.append(dict(arm=arm,RF_difference=delta))
    null={a:refit(null_scan,node,keep,a,powers,means,model,[],entries) for a in ARMS}
    null_valid=valid(null,base.labels)
    reference={a:min(incumbent[a]['negative_twice_elbo'],null[a]['negative_twice_elbo']) if null_valid else
               incumbent[a]['negative_twice_elbo'] for a in ARMS}
    methods={}
    for law in LAWS:
        changed,receipt=change_scan(scan,geometry,law)
        if abs(receipt['configured_target_loading_RMS']-receipt['configured_target_RF_loading_RMS'])>1e-12:
            raise ValueError('fixed-grid pointwise prior variance changed')
        pair={a:refit(changed,node,keep,a,powers,means,model,[],entries) for a in ARMS}
        accepted=valid(pair,base.labels)
        if any(r['linear_calibration_max_difference']>1e-10 for r in pair.values()):
            raise ValueError('predictive evidence changed calibration')
        gains={a:reference[a]-pair[a]['negative_twice_elbo'] for a in ARMS}
        methods[law]=dict(arms=pair,accepted=accepted,policy_arms=pair if accepted else incumbent,
            receiver_loading_receipt=receipt,RF_gains=gains)
    choices=[law for law,r in methods.items() if r['accepted'] and min(r['RF_gains'].values())>2*np.log(3)]
    selected=min(choices,key=lambda law:methods[law]['arms']['c0']['negative_twice_elbo']) if choices else None
    write(path,dict(case=case,methods=methods,incumbent_arms=incumbent,cold_RF_null_arms=null,
        cold_RF_null_paired_valid=null_valid,reference_costs=reference,RF_selected_law=selected,
        RF_selected_policy_arms=methods[selected]['arms'] if selected else incumbent,
        original_mask=keep,source_sha256=hashes(),metadata_sha256=sha(metadata_path),incumbent_binding=binding,
        null_endpoint_replays=old_replays,null_loading_receipt=null_receipt,
        no_GPS_future_TLE_or_original_measurement_removed=True,seconds=time.monotonic()-began))
    row=dict(case=case,accepted={law:r['accepted'] for law,r in methods.items()},RF_selected=selected,
        seconds=time.monotonic()-began)
    print(row,flush=True);return row


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('prepare','pilot','cohort'),required=True)
    stage=parser.parse_args().stage;p=prepare()
    if stage!='prepare':
        if stage=='cohort' and not read(OUT/'pilot_verification.json')['qualified']:
            raise ValueError('independent pilot replay required before cohort positions')
        cases=p['pilot_cases'] if stage=='pilot' else p['development_cases']+p['confirmation_cases'];receipts=[]
        with ProcessPoolExecutor(max_workers=min(24,len(cases))) as pool:
            futures={pool.submit(run,c):c for c in cases}
            for f in as_completed(futures):
                try:receipts.append(f.result())
                except Exception as exc:receipts.append(dict(case=futures[f],error=repr(exc)))
                write(OUT/(stage+'_progress.json'),dict(completed=len(receipts),total=len(cases)))
        errors=[r for r in receipts if 'error' in r]
        write(OUT/(stage+'_execution.json'),dict(all_terminal=True,receipts=receipts,errors=errors))
        print('Terminal',len(receipts),'errors',errors,flush=True)
