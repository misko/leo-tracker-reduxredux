"""Bounded early/middle/late carrier fits on46 existing simultaneous probes."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import json
import signal
import time
import numpy as np
from ds23_joint_component_refinement import JointComponentWorkspace
from ds23_probe_frequency_profile import frequency_only_fit,effective_times,curvature_contrast
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_frequency_profile'
BULK=Path('/srv/bulk/leo/research/ds23-frequency-profile-20261021')
SOURCE=ROOT/'reports/2026_10_21_ds23_joint_component_refinement'


def one(item,old):
    job=item['job'];target=BULK/(job['group']+f"_probe{job['probe']:06d}.json")
    if target.exists():return read(target)
    started=time.monotonic()
    def timeout(*_):raise TimeoutError('60-second three-part saved-IQ frequency-profile cap exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(60)
    result=dict(case=job['case'],group=job['group'],probe=job['probe'])
    try:
        panel=Path(item['source'])/'panels'/(job['case']+'.npz')
        with np.load(panel,allow_pickle=False) as z:
            metadata=json.loads(str(z['metadata_json']));point=next(p for p in metadata['points'] if p['probe']==job['probe'])
            v=z[point['window_key']][:,point['receiver_offset']]
        samples=v[:,0].astype(float)+1j*v[:,1].astype(float)
        p=JointComponentWorkspace(samples,metadata['sample_rate_hz'],job['edge'],[job['first']['epoch'],job['second']['epoch']],
            [item['fit']['first_fit'],item['fit']['second_fit']])
        initial=np.array(old['full']['parameters']);all_segments=p.segments;baseline=p.statistics(initial,derivatives=False)
        thirds=np.array_split(np.arange(len(all_segments)),3);parts=[]
        for indices in thirds:
            p.segments=[all_segments[i] for i in indices]
            fit=frequency_only_fit(p,initial);times=effective_times(p,fit['parameters'])
            parts.append(dict(fit,**times,first_sample=int(p.segments[0][0]),last_sample=int(p.segments[-1][-1])))
        contrast=curvature_contrast([r['effective_time_s'] for r in parts],[r['CFO_hz'] for r in parts],[r['covariance_hz2'] for r in parts])
        total_error=sum(r['squared_error'] for r in parts);total_samples=sum(r['samples'] for r in parts)
        if total_samples!=baseline['samples']:raise ValueError('early/middle/late partition lost original samples')
        gain=float(2*total_samples*np.log(baseline['squared_error']/total_error)-4*np.log(total_samples))
        result.update(status='complete',parts=parts,contrast=contrast,profile_gain_minus_four_parameter_BIC=gain,
            whole_probe_fixed_frequency=initial[[0,3]],timing_rate_fixed_from_original_whole_probe_RF_fit=True,
            every_raw_sample_and_same_frame_channel_dimensions_retained=True,
            all_searches_interior=not any(r['search_boundary'] for r in parts),
            no_GPS_satellite_identity_or_orbit_used=True,no_CFO_correction_applied=True)
    except Exception as exc:result.update(status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started;write(target,result);return result


def main():
    OUT.mkdir(exist_ok=True);BULK.mkdir(exist_ok=True);source=read(SOURCE/'protocol.json');evaluation=read(SOURCE/'evaluation.json')
    for name,digest in source['source_sha256'].items():
        if sha(ROOT/'tools'/name)!=digest:raise ValueError('two-component RF source changed')
    lookup={(r['case'],r['probe']):r for r in evaluation['rows']}
    protocol=dict(jobs=source['jobs'],workers=8,per_probe_seconds=60,three_parts='chronological frame intersections, all original support partitioned once',
        within_frame_phase_free_and_constant_channels_per_intersection=True,
        original_whole_probe_timing_code_rate_conditioned_not_refit=True,
        no_GPS_TLE_satellite_selection_or_new_RF_collection=True,
        no_physical_settling_or_position_improvement_claim=True,
        source_protocol_sha256=sha(SOURCE/'protocol.json'),source_evaluation_sha256=sha(SOURCE/'evaluation.json'),
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_probe_frequency_profile.py',ROOT/'tools/ds23_joint_component_refinement.py']})
    target=OUT/'protocol.json'
    if target.exists() and read(target)!=protocol:raise ValueError('within-probe frequency-profile protocol changed')
    if not target.exists():write(target,protocol)
    rows=[]
    with ProcessPoolExecutor(max_workers=8) as pool:
        for future in as_completed([pool.submit(one,item,lookup[item['job']['case'],item['job']['probe']]) for item in protocol['jobs']]):
            r=future.result();rows.append(r)
            print(r['group'],r['probe'],r['status'],r.get('contrast',{}).get('common_contrast_hz'),r.get('error'),flush=True)
    complete=[r for r in rows if r['status']=='complete']
    write(OUT/'evaluation.json',dict(rows=rows,all_terminal=True,complete=len(complete),
        median_absolute_common_non_affine_contrast_hz=float(np.median([abs(r['contrast']['common_contrast_hz']) for r in complete])),
        common_contrast_over_three_local_sigmas=sum(r['contrast']['common_contrast_in_local_sigma']>3 for r in complete),
        frequency_profiles_not_yet_independent_RF_prediction_validated=True,
        conditional_local_Gaussian_proxies_not_calibrated_confidence=True,no_satellite_or_geographic_position_used=True,
        no_measurement_or_localization_policy_changed=True,protocol_sha256=sha(target)))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,4.8),constrained_layout=True)
    for r in complete:
        for component in [0,1]:
            values=np.array([p['CFO_hz'][component] for p in r['parts']])-r['whole_probe_fixed_frequency'][component]
            times=np.array([p['effective_time_s'][component] for p in r['parts']])*1000
            axes[0].plot(times,values,'o-',alpha=.2,lw=.7,ms=2)
    axes[0].set(xlabel='Effective time within20ms probe (ms)',ylabel='Component CFO relative to whole-probe fit (Hz)',title='Independent early/middle/late within-frame fits')
    axes[1].scatter([r['contrast']['non_affine_CFO_contrast_hz'][0] for r in complete],[r['contrast']['non_affine_CFO_contrast_hz'][1] for r in complete],s=20)
    axes[1].axhline(0,color='gray',lw=.6);axes[1].axvline(0,color='gray',lw=.6)
    axes[1].set(xlabel='First component non-affine contrast (Hz)',ylabel='Second component non-affine contrast (Hz)',title='Does short-time curvature follow both signals?')
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle('Saved-IQ within-probe CFO diagnostic ·46 probes/23 scans\nTiming/code rate conditioned; independent frame phases; no settling or position correction applied')
    fig.savefig(OUT/'within_probe_frequency.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
