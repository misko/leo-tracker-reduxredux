"""Sign-aware RF development and point-disjoint confirmation on saved panels."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import hashlib
import json
import random
import signal
import time
import numpy as np

from benchmark_ds23_fast_pilots import PANELS,OUT as BENCHMARK
from fast_local_pilot_refinement import FastPilotWorkspace
from local_pilot_refinement import PilotWorkspace
from sign_aware_pilot import sign_aware_fit,sign_spectrum
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_sign_aware_pilot'


def prepare():
    benchmark=read(BENCHMARK/'benchmark.json')
    if benchmark['continuous_source_sha256']!=sha(ROOT/'tools/fast_local_pilot_refinement.py'):
        raise ValueError('reference continuous RF fitter changed')
    development=[dict(row['entry'],stratum='development',base_fit=row['results']['continuous']['result']) for row in benchmark['rows']]
    excluded={r['point']['observation_id'] for r in development}
    prior=read(ROOT/'reports/2026_10_20_ds23_frequency_selective_pilot/corrected_evaluation.json')
    excluded.update(r['observation_id'] for r in prior['rows'])
    pool={};panels={}
    for path in PANELS:
        with np.load(path,allow_pickle=False) as z:metadata=json.loads(str(z['metadata_json']))
        panels[str(path.relative_to(ROOT))]=sha(path)
        ownership={o:(t['receiver'],int(t['channel']>4)) for t in metadata['tracks'] for o in t['observation_ids']}
        for p in metadata['points']:
            oid=p['observation_id'];rx,band=ownership[oid]
            if oid not in pool and oid not in excluded:
                pool[oid]=dict(case=metadata['case'],receiver=rx,band=band,panel=str(path.relative_to(ROOT)),point=p,stratum='point_disjoint_confirmation')
    rng=random.Random(2026102101);confirmation=[];counts=[]
    for case in ('DS23-0202','DS23-0274'):
        for rx in (1,2):
            for band in (0,1):
                group=sorted([r for r in pool.values() if (r['case'],r['receiver'],r['band'])==(case,rx,band)],key=lambda r:r['point']['observation_id'])
                chosen=rng.sample(group,min(8,len(group)));confirmation.extend(chosen)
                counts.append(dict(case=case,receiver=rx,band=band,available=len(group),selected=len(chosen)))
    jobs=development+confirmation
    if len({r['point']['observation_id'] for r in jobs})!=len(jobs):raise ValueError('development and confirmation overlap')
    protocol=dict(jobs=jobs,panels=panels,confirmation_counts=counts,
        benchmark_sha256=sha(BENCHMARK/'benchmark.json'),workers=4,per_probe_seconds=120,
        RF_only=True,new_RF_collection=False,IQ='saved local exported panels only',
        phase_model='one common complex phase and real signed per-frame gains, independent complex DC per frame',
        exact_within_frame_likelihood_resolves_extra_frequency_aliases=True,
        frequency_radius_hz=400,frame_frequency_alias_hz=375,half_frame_fold_alias_hz=187.5,
        timing_and_rate_conditioned_on_all_frame_RF_fit=True,
        fixed_acceptance=dict(full_coherence_squared=.8,minimum_effective_frames=8,
            both_frame_prediction_fraction=.9,maximum_fold_CFO_difference_hz=10,
            maximum_full_vs_fold_average_difference_hz=5,minimum_other_mode_objective_gap=10,
            maximum_phase_surrogate_rank=.01,controls=199,base_RF_parameters_interior=True,positive_exact_control_margin=True),
        same_cases_point_disjoint_not_new_scan_or_location_validation=True,
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/sign_aware_pilot.py',ROOT/'tools/local_pilot_refinement.py',ROOT/'tools/fast_local_pilot_refinement.py']})
    OUT.mkdir(parents=True,exist_ok=True);target=OUT/'protocol.json'
    if target.exists() and read(target)!=protocol:raise ValueError('sign-aware RF protocol changed')
    if not target.exists():write(target,protocol)
    return protocol


def run(job):
    point=job['point'];oid=point['observation_id'];path=OUT/(oid.split(':')[-1]+'.json')
    if path.exists():return read(path)
    started=time.monotonic()
    def timeout(*_):raise TimeoutError('120 second sign-aware saved-IQ budget exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(120)
    record={k:job[k] for k in ('case','receiver','band','stratum')};record['observation_id']=oid
    try:
        with np.load(ROOT/job['panel'],allow_pickle=False) as z:
            metadata=json.loads(str(z['metadata_json']));fs=metadata['sample_rate_hz']
            raw=z[point['window_key']][:,point['receiver_offset']]
        samples=raw[:,0].astype(float)+1j*raw[:,1].astype(float)
        peak=point['peak'];epoch=peak['integer_epoch_sample']+peak['fractional_epoch_offset_samples']
        base=job.get('base_fit')
        if base is None:base=FastPilotWorkspace(samples,fs,point['edge'],epoch).fast_joint_fit(peak['fractional_tracking_cfo_hz'])
        p=PilotWorkspace(samples,fs,point['edge'],epoch)
        seed=int(hashlib.sha256(oid.encode()).hexdigest()[:8],16)
        result=sign_aware_fit(p,base,seed)
        f=result['fits']['all']
        control=float(sign_spectrum(p,[f['CFO_hz']],f['offset_samples'],f['modulation_ppm'],control=True)['score'][0])
        result['checks']['positive_control_margin']=f['score']>control
        result['checks']['base_RF_interior']=not any(base.get(k,False) for k in ('frequency_search_boundary','epoch_search_boundary','code_rate_search_boundary'))
        result['accepted']=all(result['checks'].values())
        proxy=f['frequency_sigma_proxy_hz']
        sigma=max(5.,result['fold_CFO_difference_hz'],2*proxy) if proxy is not None else None
        record.update(status='complete',base_fit=base,result=result,
            archived_CFO_hz=peak['fractional_tracking_cfo_hz'],proposed_CFO_hz=f['CFO_hz'],
            proposed_noise_sigma_hz=sigma,CFO_change_from_continuous_hz=f['CFO_hz']-base['CFO_hz'],
            rolled_control_score=control,RF_only_no_GPS_satellite_or_orbit_input=True)
    except Exception as exc:record.update(status='failed',error=repr(exc))
    finally:signal.alarm(0)
    record['seconds']=time.monotonic()-started;write(path,record)
    print(job['case'],job['stratum'],record['status'],record.get('error'),'accepted',record.get('result',{}).get('accepted'),
        'failed',[k for k,v in record.get('result',{}).get('checks',{}).items() if not v],flush=True)
    return record


def main():
    protocol=prepare();rows=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(run,j) for j in protocol['jobs']]):
            rows.append(f.result());write(OUT/'progress.json',dict(completed=len(rows),total=len(protocol['jobs'])))
    summary={}
    for stratum in ('development','point_disjoint_confirmation'):
        selected=[r for r in rows if r['stratum']==stratum and r['status']=='complete']
        failures={}
        for r in selected:
            for k,v in r['result']['checks'].items():
                if not v:failures[k]=failures.get(k,0)+1
        accepted=[r for r in selected if r['result']['accepted']]
        summary[stratum]=dict(completed=len(selected),accepted=len(accepted),failed_checks=failures,
            median_absolute_accepted_CFO_change_hz=float(np.median([abs(r['CFO_change_from_continuous_hz']) for r in accepted])) if accepted else None,
            accepted_case_counts={c:sum(r['case']==c for r in accepted) for c in ('DS23-0202','DS23-0274')})
    write(OUT/'evaluation.json',dict(rows=rows,summary=summary,protocol_sha256=sha(OUT/'protocol.json'),
        failures=[r for r in rows if r['status']!='complete'],real_DS23_accuracy_gain=False))
    print('SIGN_AWARE_RF',summary,flush=True)


if __name__=='__main__':main()
