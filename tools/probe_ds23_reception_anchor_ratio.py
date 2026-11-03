"""Curved-anchor reception ratios from unique epoch/CFO matched native peaks.

Only the anchor label comes from the current curved graph. An opposite-RX
partner can be a weaker native peak. No linear track updates frequency offset,
drift, antenna calibration eligibility or satellite family labels.
"""

from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np
from ds23_frame_registration import unique_peaks,wrap
from ds23_reception_anchor_pairs import counterpart
from ds23_reception_ratio import beam_contrast,logit_ratio,cross_validate
from ds23_frequency_events import make_event_problem
from probe_ds23_sign_carrier_position import context_signed
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.continuous_curve_fit import paired_phase_states
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis
from leo.sky.frames import look_angles,geodetic_to_ecef_km,ecef_to_enu_matrix

OUT=ROOT/'reports/2026_10_21_ds23_reception_anchor_ratio'
BULK=Path('/srv/bulk/leo/research/ds23-reception-anchor-ratio-20261021')
SOURCE=ROOT/'reports/2026_10_19_algo02_ds23_full'


def one(case):
    target=BULK/(case+'.json')
    if target.exists():return read(target)
    started=time.monotonic()
    def timeout(*_):raise TimeoutError('90-second curved-anchor ratio diagnostic cap exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(90);result=dict(case=case)
    try:
        scan,node,mask,powers,means,hyper,_,signed,signed_path=context_signed(case);old=signed['policy_arms']['c0']
        x=np.array(old['endpoint_east_north_km']);p=make_event_problem(scan,node,mask,'c0',np.array(old['phase_reference']),powers,means,hyper,[]);state=p.state(x)
        owners={oid:row['candidate_index'] for row,index,sl in zip(p.rows,p.members,p.slices,strict=True)
            for oid,keep in zip(scan.tracks[index]['observation_ids'],mask[sl],strict=True) if keep}
        document=read(SOURCE/case/'tracking.json');source=document.get('source',document);fs=source['sample_rate_hz']
        anchor_counter=document['clock_anchor']['sample_counter'] if 'clock_anchor' in document else source['timing']['session_start_device_sample_counter']
        probes={}
        for probe in source['probes']:
            timestamp=(probe['valid_start_counter']-anchor_counter)/fs+probe['probe_start_ms']/1000+source['probe_ms']/2000
            key=(probe['receiver_id']+1,round(timestamp,6),probe['channel'],probe['actual_rf_hz'])
            if key in probes:raise ValueError('duplicate native RF probe identity')
            probes[key]=probe
        candidates=defaultdict(list);diagnostics=defaultdict(int)
        for observation in read(SOURCE/case/'observations.json'):
            if observation['observation_id'] not in owners:continue
            rx=observation['receiver'];t=round(observation['time_s'],6);ch=observation['channel'];rf=observation['actual_rf_hz']
            first=probes.get((rx,t,ch,rf));other=probes.get((3-rx,t,ch,rf))
            if first is None or other is None:continue
            peaks=unique_peaks(first['candidates'],fs)
            if not peaks:continue
            seed=min(peaks,key=lambda r:abs(float(wrap(r['cfo']-observation['measured_cfo_hz']))))
            if abs(float(wrap(seed['cfo']-observation['measured_cfo_hz'])))>1.:continue
            basis=projected_receiver_basis(np.array([t]));radio=[]
            for receiver in [1,2]:
                track=dict(receiver=receiver,channel=ch,rf_hz=rf,times=np.array([t]))
                radio.append(float(scan.hardware(track,state['beta'])[0]+rf/11.5e9*(basis@state['smooth'][receiver-1])[0]))
            expected=radio[1]-radio[0];partner=counterpart(seed,unique_peaks(other['candidates'],fs),expected if rx==1 else -expected,fs)
            if partner is None:diagnostics['no_unique_epoch_CFO_partner']+=1;continue
            pair=[seed,partner] if rx==1 else [partner,seed]
            if not all(0<r['margin']<1 for r in pair):continue
            key=(t,ch,rf,pair[0]['rank'],pair[1]['rank'])
            candidates[key].append(dict(candidate_index=owners[observation['observation_id']],first=pair[0],second=pair[1],time_s=t,channel=ch,rf_hz=rf,
                native_CFO_calibration_residual_hz=float(wrap(pair[1]['cfo']-pair[0]['cfo']-expected))))
        rows=[]
        for group in candidates.values():
            if len({r['candidate_index'] for r in group})!=1:diagnostics['conflicting_curved_family_anchors']+=1;continue
            row=group[0];candidate=row['candidate_index'];t=row['time_s']
            position,velocity=paired_phase_states(scan.sky,np.array([t]),np.array([candidate]),state['phases'])
            az,el,_,_=look_angles(position,velocity,geodetic_to_ecef_km(*latlon(x),0.),ecef_to_enu_matrix(*latlon(x)))
            margins=[row['first']['margin'],row['second']['margin']]
            rows.append(dict(norad=int(scan.norads[candidate]),candidate_index=candidate,time_s=t,band=int(row['channel']>4),channel=row['channel'],
                feature=float(beam_contrast(az[0],el[0])),log_ratio=float(logit_ratio(*margins)),margins=margins,
                native_peaks=[row['first'],row['second']],curved_anchor_votes=len(group),
                native_CFO_calibration_residual_hz=row['native_CFO_calibration_residual_hz']))
        by_family=defaultdict(list)
        for row in rows:by_family[row['norad'],row['band']].append(row)
        medians=[]
        for (family,band),group in sorted(by_family.items()):
            if len(group)<6 or np.ptp([r['time_s'] for r in group])<8.:continue
            medians.append(dict(norad=family,band=band,feature=float(np.median([r['feature'] for r in group])),
                log_ratio=float(np.median([r['log_ratio'] for r in group])),points=len(group),span_s=float(np.ptp([r['time_s'] for r in group]))))
        result.update(status='complete',paired_points=rows,family_band_medians=medians,validation=cross_validate(medians),
            diagnostics=dict(diagnostics),RF_position_east_north_km=x,incumbent_sha256=sha(signed_path),
            tracking_sha256=sha(SOURCE/case/'tracking.json'),
            same_original_curved_calibration_no_linear_offset_or_drift_updates=True,
            no_GPS_new_RF_or_satellite_label_or_position_change=True,
            matched_native_peaks_are_proposals_not_independent_satellite_identity_proof=True)
    except Exception as exc:result.update(status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started;write(target,result);return result


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True);old=ROOT/'reports/2026_10_21_ds23_reception_ratio/protocol.json';cases=read(old)['cases']
    protocol=dict(cases=cases,workers=8,per_case_seconds=90,all23_previous_RF_cohort_scans=True,
        only_current_active_curved_anchors=True,opposite_RX_native_peak_unique_by_epoch_and_frozen_curved_radio_calibration=True,
        epoch_tolerance_ns=80.,CFO_tolerance_hz=750.,minimum_family_band_pairs=6,minimum_span_s=8.,
        native_pairs_with_conflicting_curved_labels_excluded_and_counted=True,
        one_vote_per_family_band_and_leave_whole_family_out=True,nominal_unmeasured_mount_and_margin_SNR_law=True,
        no_GPS_location_read_new_RF_or_localization_or_label_change=True,
        original_two_curved_winner_control_sha256=sha(ROOT/'reports/2026_10_21_ds23_reception_ratio/evaluation.json'),
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_reception_ratio.py',ROOT/'tools/ds23_reception_anchor_pairs.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('curved-anchor ratio protocol changed')
    if not path.exists():write(path,protocol)
    rows=[]
    with ProcessPoolExecutor(max_workers=8) as pool:
        for future in as_completed([pool.submit(one,c) for c in cases]):
            r=future.result();rows.append(r);print(r['case'],r['status'],len(r.get('paired_points',[])),r.get('validation',{}).get('qualified'),r.get('error'),flush=True)
    supported=[r for r in rows if r['status']=='complete' and 'held_family_SSE_fractional_improvement' in r['validation']]
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,failures=[r for r in rows if r['status']!='complete'],
        supported_cases=len(supported),qualified_cases=sum(r['validation']['qualified'] for r in supported),
        per_case_held_family_improvements={r['case']:r['validation']['held_family_SSE_fractional_improvement'] for r in supported},
        no_new_association_prior_or_position_estimate_adopted=True,protocol_sha256=sha(path)))


if __name__=='__main__':main()
