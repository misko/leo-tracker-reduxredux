"""All passed native peaks, exclusive peak paths, shared-probe covariance."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from itertools import combinations
from pathlib import Path
import signal
import time
import numpy as np

from ds23_same_probe_covariance import disjoint_peak_paths,compare_paths
from probe_ds23_secondary_curves import probe_authority
from probe_algo01_0217_improvements import polynomial_proposals
from leo.analysis.polynomial_tracklets import TrackConfig
from leo.analysis.research.visible_arc_variants import deduplicate
from probe_algo03_frame_peak_recovery import SOURCE
from evaluate_ds22_merged_tracks import CONFIG
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_same_probe_curves'
CASES=('DS23-0202','DS23-0274')


def lanes(case):
    document=read(SOURCE/case/'tracking.json');source,authority=probe_authority(document)
    receivers=sorted({p['receiver_id'] for p in source['probes']});result={}
    for pi,probe in enumerate(source['probes']):
        observed=authority.get(pi)
        if observed is None:continue
        lane=(receivers.index(probe['receiver_id'])+1,probe['channel'],probe['actual_rf_hz'])
        for candidate in probe['candidates']:
            if not candidate['passed_fractional_margin_gate']:continue
            epoch=candidate['integer_epoch_sample']+candidate['fractional_epoch_offset_samples']
            result.setdefault(lane,[]).append(dict(time_s=observed['time_s'],probe=pi,
                cfo_hz=candidate['fractional_tracking_cfo_hz'],epoch=float(epoch),
                margin=candidate['fractional_margin'],rank=candidate['candidate_rank'],
                probe_observation_id=observed['observation_id']))
    output=[]
    for lane,candidates in sorted(result.items()):
        representatives,_=deduplicate([c['cfo_hz'] for c in candidates],[c['margin'] for c in candidates],[c['probe'] for c in candidates])
        candidates=sorted([candidates[i] for i in representatives],key=lambda c:(c['time_s'],c['cfo_hz']))
        output.append(dict(case=case,lane=list(lane),sample_rate_hz=source['sample_rate_hz'],candidates=candidates))
    return output


def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    jobs=[j for case in CASES for j in lanes(case)]
    protocol=dict(cases=list(CASES),jobs=jobs,workers=4,per_lane_seconds=120,
        original_graph_config_sha256=sha(CONFIG),RANSAC_trials_per_lane=1200,
        no_occupied_probe_exclusion=True,exclusive_peak_ownership_not_exclusive_probe_ownership=True,
        maximum_disjoint_paths_per_lane=32,minimum_paired_probes=16,minimum_paired_span_s=20,
        active_relative_curvature_RMS_hz=250,minimum_relative_curvature_BIC_gain=10,
        minimum_affine_frequency_relation_residual_RMS_hz=250,minimum_median_epoch_separation_us=2,
        common_noise_rule='positive matched residual correlation >=.6, both interleaved correlations>=.4, diagnostic permutation rank<=.01, both original residual noise screens pass',
        no_GPS_TLE_or_satellite_selection=True,no_new_RF_collection=True,no_IQ_read=True,
        source_tracking_sha256={c:sha(SOURCE/c/'tracking.json') for c in CASES},
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_same_probe_covariance.py',ROOT/'tools/probe_algo01_0217_improvements.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('multi-peak curve protocol changed')
    if not path.exists():write(path,protocol)
    return protocol


def run(job):
    case=job['case'];rx,ch,rf=job['lane'];path=OUT/(case+f'_RX{rx}_CH{ch}.json')
    if path.exists():return read(path)
    started=time.monotonic()
    def timeout(*_):raise TimeoutError('120 second radio-only multi-peak lane budget exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(120)
    result=dict(case=case,lane=job['lane'],native_peak_candidates=len(job['candidates']))
    try:
        candidates=job['candidates'];cfg=TrackConfig(**read(CONFIG)['config'])
        models=polynomial_proposals(candidates,cfg,trials=1200,seed=20261021+int(case.split('-')[1])*32+rx*8+ch)
        selected=disjoint_peak_paths(models);paths=[]
        for k,m in enumerate(selected):
            ix=np.asarray(m['indices'],int);rows=[candidates[i] for i in ix]
            paths.append(dict(key=case+f'-MULTI-RX{rx}-CH{ch}-P{k:02}',lane=job['lane'],
                times=[r['time_s'] for r in rows],probes=[r['probe'] for r in rows],
                values=m['values'],epochs=[r['epoch'] for r in rows],
                peak_indices=ix,degree=m['piece']['degree'],gain=m['gain'],diagnostics=m['diagnostics']))
        pairs=[]
        for first,second in combinations(paths,2):
            comparison=compare_paths(first,second,job['sample_rate_hz'],seed=20261021+len(pairs))
            if comparison is not None:pairs.append(comparison)
        result.update(status='complete',proposals=len(models),paths=paths,pairs=pairs,
            distinct_geometry_pairs=sum(all(r['geometry_checks'].values()) for r in pairs),
            common_noise_candidates=sum(r['common_noise_candidate'] for r in pairs))
    except Exception as exc:result.update(status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-started;write(path,result)
    print(case,rx,ch,result['status'],result.get('error'),'paths',len(result.get('paths',[])),
        'pairs',len(result.get('pairs',[])),'geometry',result.get('distinct_geometry_pairs'),'common',result.get('common_noise_candidates'),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--pilot',action='store_true');args=parser.parse_args()
    protocol=prepare();jobs=protocol['jobs']
    if args.pilot:
        jobs=sorted(jobs,key=lambda j:-len(j['candidates']))[:2]
    with ProcessPoolExecutor(max_workers=min(4,len(jobs))) as pool:
        for f in as_completed([pool.submit(run,j) for j in jobs]):f.result()
    rows=[];pending=[]
    for job in protocol['jobs']:
        rx,ch,_=job['lane'];path=OUT/(job['case']+f'_RX{rx}_CH{ch}.json')
        if path.exists():rows.append(read(path))
        else:pending.append(dict(case=job['case'],lane=job['lane']))
    write(OUT/'evaluation.json',dict(rows=rows,pending=pending,protocol_sha256=sha(OUT/'protocol.json'),
        no_satellite_or_position_inference=True,real_DS23_accuracy_gain=False))


if __name__=='__main__':main()
