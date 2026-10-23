"""RF-only audit of curvature on the original numerical calibration masks."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import signal
import numpy as np

import run_ds23_dbg01_iteration_016 as runner
from ds23_supported_curvature import curvature_evidence
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_23_ds23_original_calibration_curvature'
AUTHORITY=ROOT/'reports/2026_10_22_ds23_family_cavity_full_assessment/evidence/publication_receipt.json'
SOURCE=ROOT/'reports/2026_10_22_ds23_family_cavity/phase_refreshed/full_DS23/position'


def active_evidence(track,use):
    use=np.asarray(use,bool);times=np.asarray(track['times']);values=np.asarray(track['values'])
    if use.shape!=times.shape or values.shape!=times.shape or not use.any():raise ValueError('nonempty original numerical mask must match source')
    return curvature_evidence(dict(track,times=times[use],values=values[use]))


def protocol():
    OUT.mkdir(parents=True,exist_ok=True);path=OUT/'protocol.json'
    if path.exists():return read(path)
    available=sorted(r['case'] for r in read(AUTHORITY)['case_result_sha256']);engineering=read(runner.RAW/'protocol.json')['cases'];closed=set(runner.CLOSED)|set(engineering)|{'DS23-0405'}
    pool=[c for c in available if c not in closed];random20=sorted(np.random.default_rng(2026102316).choice(pool,20,replace=False).tolist())
    record=dict(cases=engineering+random20,engineering=engineering,random20=random20,random_pool=pool,seed=2026102316,
        case_selection_uses_only_IDs_no_position_errors=True,random20_scan_disjoint_from_closed_DBG01_and_current_two=True,
        same_site_previously_studied_not_new_location_or_untouched_validation=True,
        original_actual_calibration_mask_not_full_graph_source_controls_eligibility=True,
        existing_every_single_point_deletion_rule=dict(minimum_points=12,minimum_span_s=10,minimum_linear_RMS_hz=250,quadratic_BIC_gain_strictly_above=10),
        original_points_labels_aliases_noise_powers_and_all_priors_unchanged_inventory_only=True,
        prior_statistical_curvature_tool='tools/probe_ds23_statistical_curvature.py',prior_tool_sha256=sha(ROOT/'tools/probe_ds23_statistical_curvature.py'),
        distinction='prior study promoted new unused sources; this inventory inspects original calibration, with no demotion or fitting yet',
        source_sha256=sha(Path(__file__)),criterion_sha256=sha(Path(curvature_evidence.__code__.co_filename)),authority_sha256=sha(AUTHORITY),
        workers=4,per_case_seconds=90,no_GPS_future_TLE_new_RF_IQ_or_position_fit=True)
    write(path,record);return record


def one(case):
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('90s original curvature inventory cap')));signal.alarm(90)
    runner.configure();d=runner.engine.current_setup(case);rows=[];all_ids=[];retained=[];demoted=[]
    for k,(r,i,sl) in enumerate(zip(d['base'].rows,d['base'].members,d['base'].slices,strict=True)):
        use=d['keep'][sl]
        if not use.any():continue
        track=d['scan'].tracks[i];e=active_evidence(track,use);ids=np.asarray(track['observation_ids'])[use].tolist();all_ids.extend(ids)
        (retained if e['qualified'] else demoted).extend(ids)
        rows.append(dict(component=r['component'],row=k,track_index=i,norad=r['candidate_norad'],candidate_index=r['candidate_index'],
            receiver=track['receiver'],channel=track['channel'],active_points=int(use.sum()),source_points=len(use),active_span_s=float(np.ptp(np.asarray(track['times'])[use])),
            original_power=float(d['powers'][k]),observation_ids=ids,evidence=e,would_retain_calibration=e['qualified']))
    if len(all_ids)!=len(set(all_ids)) or set(retained)&set(demoted):raise ValueError('original source masks overlap')
    result=dict(case=case,rows=rows,original_calibration_points=len(all_ids),robust_calibration_points=len(retained),would_demote_points=len(demoted),
        original_curved_sources=len(rows),would_demote_sources=sum(not r['would_retain_calibration'] for r in rows),
        original_calibration_IDs=sorted(all_ids),demoted_IDs=sorted(demoted),source_position_sha256=sha(SOURCE/(case+'.json')),
        observations_sha256=sha(d['observations_path']),no_classification_fit_or_contract_change_applied=True)
    write(OUT/(case+'.json'),result);signal.alarm(0);print(case,'original calibration',len(all_ids),'would retain',len(retained),'weak sources',result['would_demote_sources'],flush=True)
    return {k:result[k] for k in ['case','original_calibration_points','robust_calibration_points','would_demote_points','original_curved_sources','would_demote_sources']}


def main():
    p=protocol()
    if (OUT/'execution.json').exists():raise FileExistsError('preserve RF inventory')
    with ProcessPoolExecutor(max_workers=4) as pool:rows=list(pool.map(one,p['cases']))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,all_passed=True,inventory_only_no_accuracy_computation=True))


if __name__=='__main__':main()
