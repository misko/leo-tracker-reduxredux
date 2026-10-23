"""Known-label localization with declared point noise; real GPS is never read.

This tests a conditional Gaussian-noise scenario at the causal phase mean and
zero nuisance coefficients. It is not a full hierarchical prior-predictive
simulation, an association test, or evidence of real-data accuracy improvement.
"""

import copy
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np

from probe_ds23_synthetic_closure import generate,TEMPLATES
from probe_ds23_frequency_events import parameters,refit
from run_ds23_combined_recovery_full import context,ARMS
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_synthetic_noise'
SITE=(-5.,5.)


def perturb_tracks(scan,members,seed):
    """One synthetic noise value per physical ID, reused across any views."""
    ids=sorted({oid for i in members for oid in scan.tracks[i]['observation_ids']})
    metadata=scan.fixed_window_noise;by_id=metadata['per_observation_noise_sigma_hz']
    scales={oid:(by_id[oid] if metadata['extra_parameter_BIC_gain']>0 else scan.radio_sigma_hz) for oid in ids}
    if not all(np.isfinite(v) and v>0 for v in scales.values()):raise ValueError('positive declared point uncertainties required')
    z=np.random.default_rng(seed).normal(size=len(ids))
    noise={oid:float(value*scales[oid]) for oid,value in zip(ids,z,strict=True)}
    for i in sorted(set(members)):
        track=scan.tracks[i]
        track['values']=np.asarray(track['values'])+np.asarray([noise[oid] for oid in track['observation_ids']])
    return dict(unique_observations=len(ids),noise_sigma_min_hz=min(scales.values()),noise_sigma_max_hz=max(scales.values()),
        realized_standard_normal_RMS=float(np.sqrt(np.mean(z*z))))


def gate_counts(record):
    curved=record['gates']['tracks'];linear=record['linear_gates']
    return dict(curved=len(curved),failed_curved=sum(not r['compatible'] for r in curved),
        predictive=len(linear),failed_predictive=sum(not r['compatible'] for r in linear),
        all_original_gates_pass=all(r['compatible'] for r in curved+linear))


def run(case,draw):
    path=OUT/(case+'_draw'+str(draw)+'.json')
    if path.exists():return read(path)
    begin=time.monotonic();seed=194729+draw*1009+int(case.split('-')[1])
    def timeout(*_):raise TimeoutError('120 second noisy-control budget exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(120)
    result=dict(case=case,draw=draw,seed=seed,synthetic_site_east_north_km=SITE,
        cold_start_east_north_km=[0,0],evaluation_GPS_used=False,oracle_labels_and_aliases=True,
        Gaussian_point_noise_at_original_declared_sigmas=True,full_hierarchical_prior_predictive=False)
    try:
        scan,node,mask,base,old=context(case);powers,means,hyper=parameters(scan,base,old)
        entries=old['linear_entries'] if old['linear_paired_valid'] else []
        original=[t['values'].copy() for t in scan.tracks]
        synthetic,copied,predictive,reconstruction=generate(scan,node,base,means,entries,SITE)
        noise=perturb_tracks(synthetic,set(base.members)|{e['track_index'] for e in predictive},seed)
        if any(not np.array_equal(v,t['values']) for v,t in zip(original,scan.tracks,strict=True)):
            raise ValueError('noise generation changed original source observations')
        pair={a:refit(synthetic,copied,mask,a,powers,means,hyper,[],predictive) for a in ARMS}
        for a,r in pair.items():
            r['synthetic_position_error_km']=float(np.linalg.norm(np.asarray(r['endpoint_east_north_km'])-SITE))
            r['original_gate_counts']=gate_counts(r)
        result.update(status='complete',arms=pair,noise=noise,source_observations_unchanged=True,
            same_observations_masks_priors_weights_labels_aliases_in_c_arms=True,
            maximum_forward_alias_reconstruction_error_before_noise_hz=reconstruction)
    except Exception as exc:result.update(status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-begin;write(path,result)
    print(case,draw,result['status'],{a:(r['synthetic_position_error_km'],r['original_gate_counts']) for a,r in result.get('arms',{}).items()},flush=True)
    return result


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    protocol=dict(templates=list(TEMPLATES),draws_per_template=4,synthetic_site=list(SITE),
        workers=8,per_instance_seconds=120,seed_formula='194729+draw*1009+template_number',
        full_hierarchical_prior_predictive=False,conditional_Gaussian_noise_only=True,
        not_real_DS23_accuracy_or_full_association_validation=True,
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/probe_ds23_synthetic_closure.py']})
    target=OUT/'protocol.json'
    if target.exists() and read(target)!=protocol:raise ValueError('noisy-control protocol changed')
    if not target.exists():write(target,protocol)
    rows=[]
    with ProcessPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(run,c,d) for c in TEMPLATES for d in range(4)]):rows.append(f.result())
    summaries={}
    for a in ARMS:
        arms=[r['arms'][a] for r in rows if r['status']=='complete'];err=[r['synthetic_position_error_km'] for r in arms]
        summaries[a]=dict(n=len(arms),mean_error_km=float(np.mean(err)) if err else None,median_error_km=float(np.median(err)) if err else None,
            maximum_error_km=max(err) if err else None,all_gate_qualified_instances=sum(r['original_gate_counts']['all_original_gates_pass'] for r in arms),
            curved_tracks=sum(r['original_gate_counts']['curved'] for r in arms),failed_curved_tracks=sum(r['original_gate_counts']['failed_curved'] for r in arms),
            predictive_tracks=sum(r['original_gate_counts']['predictive'] for r in arms),failed_predictive_tracks=sum(r['original_gate_counts']['failed_predictive'] for r in arms))
    write(OUT/'evaluation.json',dict(instances=len(rows),summary=summaries,
        failures=[(r['case'],r['draw'],r.get('error')) for r in rows if r['status']!='complete'],
        conditional_oracle_label_diagnostic_only=True,not_real_data_accuracy_gain=True,protocol_sha256=sha(target)))


if __name__=='__main__':main()
