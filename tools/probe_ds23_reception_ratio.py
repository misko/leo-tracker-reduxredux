"""Test nominal sky-direction information in simultaneous curved RX winners.

Only pairs with the same current curved-family label and a native frame-epoch
match enter this diagnostic. Reference GPS and station location fields are
never read. The nominal70deg east/west mounting geometry remains unmeasured.
"""

from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np
from ds23_frame_registration import wrap
from ds23_frequency_events import make_event_problem
from ds23_reception_ratio import beam_contrast,logit_ratio,cross_validate
from probe_ds23_sign_carrier_position import context_signed
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.continuous_curve_fit import paired_phase_states
from leo.sky.frames import look_angles,geodetic_to_ecef_km,ecef_to_enu_matrix

OUT=ROOT/'reports/2026_10_21_ds23_reception_ratio'
BULK=Path('/srv/bulk/leo/research/ds23-reception-ratio-20261021')
SOURCE=ROOT/'reports/2026_10_19_algo02_ds23_full'


def one(case):
    target=BULK/(case+'.json')
    if target.exists():return read(target)
    started=time.monotonic()
    def timeout(*_):raise TimeoutError('90-second saved-contract reception-ratio cap exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(90);record=dict(case=case)
    try:
        context=context_signed(case);scan,node,mask,powers,means,hyper,_,signed,signed_path=context
        old=signed['policy_arms']['c0'];x=np.array(old['endpoint_east_north_km']);p=make_event_problem(scan,node,mask,'c0',np.array(old['phase_reference']),powers,means,hyper,[])
        state=p.state(x);owners={oid:row['candidate_index'] for row,index,sl in zip(p.rows,p.members,p.slices,strict=True)
            for oid,keep in zip(scan.tracks[index]['observation_ids'],mask[sl],strict=True) if keep}
        document=read(SOURCE/case/'tracking.json');source=document.get('source',document);fs=source['sample_rate_hz']
        anchor=document['clock_anchor']['sample_counter'] if 'clock_anchor' in document else source['timing']['session_start_device_sample_counter']
        probes={}
        for probe in source['probes']:
            timestamp=(probe['valid_start_counter']-anchor)/fs+probe['probe_start_ms']/1000+source['probe_ms']/2000
            key=(probe['receiver_id']+1,round(timestamp,6),probe['channel'],probe['actual_rf_hz'])
            if key in probes:raise ValueError('duplicate native probe/timestamp identity')
            probes[key]=probe
        observations=read(SOURCE/case/'observations.json');slots=defaultdict(dict)
        for row in observations:
            if row['observation_id'] in owners:
                slots[round(row['time_s'],6),row['channel'],row['actual_rf_hz']][row['receiver']]=row
        rows=[];diagnostics=defaultdict(int)
        for (timestamp,channel,frequency),pair in slots.items():
            if len(pair)!=2:continue
            if owners[pair[1]['observation_id']]!=owners[pair[2]['observation_id']]:
                diagnostics['different_curved_labels']+=1;continue
            diagnostics['same_curved_label_pairs']+=1;peaks=[]
            for rx in [1,2]:
                probe=probes.get((rx,timestamp,channel,frequency));observation=pair[rx]
                if probe is None:break
                eligible=[r for r in probe['candidates'] if r['passed_fractional_margin_gate']]
                if not eligible:break
                best=min(eligible,key=lambda r:abs(float(wrap(r['fractional_tracking_cfo_hz']-observation['measured_cfo_hz']))))
                if abs(float(wrap(best['fractional_tracking_cfo_hz']-observation['measured_cfo_hz'])))>1.:break
                peaks.append(best)
            if len(peaks)!=2:diagnostics['missing_exact_native_winner']+=1;continue
            epoch=[r['integer_epoch_sample']+r['fractional_epoch_offset_samples'] for r in peaks]
            difference=float(wrap(epoch[1]-epoch[0],fs/750))/fs
            if abs(difference)>80e-9:diagnostics['native_epoch_mismatch']+=1;continue
            margin=[r['fractional_margin'] for r in peaks]
            if not all(0<m<1 for m in margin):diagnostics['unsupported_margin_range']+=1;continue
            candidate=owners[pair[1]['observation_id']];position,velocity=paired_phase_states(scan.sky,np.array([timestamp]),np.array([candidate]),state['phases'])
            az,el,_,_=look_angles(position,velocity,geodetic_to_ecef_km(*latlon(x),0.),ecef_to_enu_matrix(*latlon(x)))
            rows.append(dict(norad=int(scan.norads[candidate]),candidate_index=candidate,time_s=timestamp,band=int(channel>4),channel=channel,
                feature=float(beam_contrast(az[0],el[0])),log_ratio=float(logit_ratio(*margin)),margins=margin,
                native_epoch_difference_ns=difference*1e9,azimuth_deg=float(az[0]),elevation_deg=float(el[0])))
        grouped=defaultdict(list)
        for row in rows:grouped[row['norad'],row['band']].append(row)
        medians=[]
        for (family,band),group in sorted(grouped.items()):
            if len(group)<6 or np.ptp([r['time_s'] for r in group])<8.:continue
            medians.append(dict(norad=family,band=band,feature=float(np.median([r['feature'] for r in group])),
                log_ratio=float(np.median([r['log_ratio'] for r in group])),points=len(group),span_s=float(np.ptp([r['time_s'] for r in group]))))
        result=cross_validate(medians)
        record.update(status='complete',paired_points=rows,family_band_medians=medians,validation=result,
            diagnostics=dict(diagnostics),RF_position_east_north_km=x,incumbent_sha256=sha(signed_path),
            tracking_sha256=sha(SOURCE/case/'tracking.json'),observations_sha256=sha(SOURCE/case/'observations.json'),
            no_GPS_or_station_position_fields_read=True,independent_curved_family_validation_not_position_estimation=True,
            nominal_mount_and_margin_to_SNR_law_are_unverified_hypotheses=True,
            original_associations_and_CFO_position_outputs_unchanged=True)
    except Exception as exc:record.update(status='failed',error=repr(exc))
    finally:signal.alarm(0)
    record['seconds']=time.monotonic()-started;write(target,record);return record


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True)
    prior=ROOT/'reports/2026_10_21_ds23_joint_component_refinement/protocol.json';cases=sorted({r['job']['case'] for r in read(prior)['jobs']})
    protocol=dict(cases=cases,workers=8,per_case_seconds=90,
        selection='all23 original phase-blind RF cohort scans; paired canonical winners on same currently active curved family',
        native_epoch_tolerance_ns=80.,minimum_pairs_per_family_band=6,minimum_span_s=8.,minimum_held_families=4,
        geometry='nominal receiver axes270/90deg azimuth,70deg elevation; unmeasured installed beam and provisional RX mapping',
        model='logit margin ratio=band intercept+signed squared angular-distance contrast',
        all_rows_of_held_satellite_excluded_from_training=True,one_family_band_median_vote_not_one_point_vote=True,
        qualifier='>20percent held-family SSE improvement and consistent slope sign across folds',
        no_position_refit_or_GPS_station_location_read_or_association_prior_adopted=True,
        input_cohort_sha256=sha(prior),source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_reception_ratio.py']})
    target=OUT/'protocol.json'
    if target.exists() and read(target)!=protocol:raise ValueError('reception ratio protocol changed')
    if not target.exists():write(target,protocol)
    rows=[]
    with ProcessPoolExecutor(max_workers=8) as pool:
        for future in as_completed([pool.submit(one,c) for c in cases]):
            r=future.result();rows.append(r);print(r['case'],r['status'],len(r.get('paired_points',[])),r.get('validation',{}).get('qualified'),r.get('error'),flush=True)
    complete=[r for r in rows if r['status']=='complete'];supported=[r for r in complete if 'held_family_SSE_fractional_improvement' in r['validation']]
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,failures=[r for r in rows if r['status']!='complete'],
        supported_cases=len(supported),qualified_cases=sum(r['validation']['qualified'] for r in supported),
        per_case_held_family_improvements={r['case']:r['validation']['held_family_SSE_fractional_improvement'] for r in supported},
        no_new_localization_or_antenna_prior_adoption=True,protocol_sha256=sha(target)))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(13,4.8),constrained_layout=True)
    axes[0].bar(np.arange(len(supported)),[r['validation']['held_family_SSE_fractional_improvement']*100 for r in supported])
    axes[0].set(xticks=np.arange(len(supported)),xticklabels=[r['case'][-4:] for r in supported],xlabel='DS23 scan',ylabel='Held-family SSE improvement (%)')
    axes[0].axhline(20.,color='gray',ls=':');axes[0].grid(axis='y',alpha=.2)
    for case in supported:
        for fold in case['validation']['folds']:
            axes[1].scatter([r['observed'] for r in fold['predictions']],[r['direction_prediction'] for r in fold['predictions']],s=15,alpha=.5)
    axes[1].set(xlabel='Observed family-median logit RX margin ratio',ylabel='Predicted from other families and nominal sky direction');axes[1].grid(alpha=.2)
    fig.suptitle('Can paired-RX reception strengths independently constrain sky associations?\nOnly native frame-matched curved winners; nominal unmeasured mount; no GPS or position change')
    fig.savefig(OUT/'reception_ratio_validation.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
