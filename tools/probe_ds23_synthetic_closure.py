"""Ideal-label, noiseless localization closure; not an association benchmark.

Synthetic positions are fixed regional offsets, unrelated to the evaluation
GPS. The forward generator knows them; the fitter always starts at town zero.
The original causal priors, masks, weights, noise law and two c arms are kept.
"""

import copy
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time

import numpy as np

from ds23_predictive_linear import linear_geometry
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.retained_track_likelihood import PERIOD
from probe_ds23_frequency_events import parameters,refit
from prototype_dsx01_continuous_position import latlon
from run_ds23_combined_recovery_full import context,ARMS
from run_dsx01_clean_region import zero_state
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_synthetic_closure'
TEMPLATES=('DS23-0001','DS23-0002')
SITES=((0.,0.),(-5.,5.),(5.,5.))


def alias_encode(frequency):
    f=np.asarray(frequency,float)
    if f.ndim!=1 or not len(f) or not np.isfinite(f).all():
        raise ValueError('finite nonempty one-dimensional synthetic frequency required')
    alias=int(np.rint(f.mean()/PERIOD))
    return f-alias*PERIOD,alias


def generate(scan,node,base,means,entries,site):
    changed=copy.copy(scan)
    changed.tracks=[dict(t,values=np.asarray(t['values']).copy()) for t in scan.tracks]
    copied=copy.deepcopy(node);copied['seed']['state']=zero_state(scan)
    predictive=copy.deepcopy(entries)
    f,_=paired_phase_frequency(base.sky,base.flat_times,base.flat_labels,means,*latlon(site))
    forward_error=[]
    for k,(i,sl) in enumerate(zip(base.members,base.slices,strict=True)):
        raw=base.q[sl]*f[sl];values,alias=alias_encode(raw)
        changed.tracks[i]['values']=values;copied['aliases'][k]=alias
        forward_error.extend(abs(values+alias*PERIOD-raw))
    if entries:
        view,_,_,_,slices=linear_geometry(base,entries)
        f,_=paired_phase_frequency(view.sky,view.flat_times,view.flat_labels,means,*latlon(site))
        for entry,sl in zip(predictive,slices,strict=True):
            if entry['track_index'] in base.members:
                raise ValueError('closure requires disjoint curved and predictive track templates')
            raw=view.q[sl]*f[sl];values,alias=alias_encode(raw)
            changed.tracks[entry['track_index']]['values']=values;entry['alias']=alias
            forward_error.extend(abs(values+alias*PERIOD-raw))
    return changed,copied,predictive,float(max(forward_error,default=0.))


def run_case(case,site_index):
    path=OUT/(case+'_site'+str(site_index)+'.json')
    if path.exists():return read(path)
    begin=time.monotonic()
    def timeout(*_):raise TimeoutError('120 second closure-control budget exhausted')
    signal.signal(signal.SIGALRM,timeout);signal.alarm(120)
    record=dict(case=case,site_index=site_index,synthetic_site_east_north_km=SITES[site_index],
        cold_start_east_north_km=[0,0],evaluation_GPS_used=False,
        labels_known_by_construction=True,association_pipeline_not_tested=True,
        zero_noise_zero_radio_orbit_and_fragment_nuisance=True)
    try:
        scan,node,mask,base,old=context(case);powers,means,model=parameters(scan,base,old)
        entries=old['linear_entries'] if old['linear_paired_valid'] else []
        original=[t['values'].copy() for t in scan.tracks]
        synthetic,copied,predictive,reconstruction=generate(scan,node,base,means,entries,SITES[site_index])
        if any(not np.array_equal(before,t['values']) for before,t in zip(original,scan.tracks,strict=True)):
            raise ValueError('synthetic generation mutated original observations')
        pair={a:refit(synthetic,copied,mask,a,powers,means,model,[],predictive) for a in ARMS}
        for a,r in pair.items():
            r['synthetic_position_error_km']=float(np.linalg.norm(np.asarray(r['endpoint_east_north_km'])-SITES[site_index]))
        record.update(status='complete',arms=pair,maximum_forward_alias_reconstruction_error_hz=reconstruction,
            original_observations_unchanged=True,same_mask_weights_priors_aliases_and_observations_in_c_arms=True,
            original_input_sha256=sha(ROOT/'reports/2026_10_19_algo02_ds23_full'/case/'algo02_result.json'))
    except Exception as exc:record.update(status='failed',error=repr(exc))
    finally:signal.alarm(0)
    record['seconds']=time.monotonic()-begin;write(path,record)
    print(case,site_index,record['status'],{a:r['synthetic_position_error_km'] for a,r in record.get('arms',{}).items()},flush=True)
    return record


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    protocol=dict(templates=TEMPLATES,synthetic_sites_east_north_km=SITES,workers=6,per_instance_seconds=120,
        labels_and_aliases_known_by_construction=True,not_end_to_end_association_validation=True,
        zero_random_noise=True,zero_radio_orbit_and_fragment_coefficients=True,
        true_phase_equals_strictly_causal_forecast_mean=True,real_evaluation_position_not_read=True,
        full_prior_and_noise_law_still_integrated_by_fitter=True,
        source_sha256=sha(Path(__file__)))
    target=OUT/'protocol.json'
    if target.exists() and read(target)!=readable(protocol):raise ValueError('closure protocol changed')
    if not target.exists():write(target,protocol)
    rows=[]
    with ProcessPoolExecutor(max_workers=6) as pool:
        futures=[pool.submit(run_case,c,k) for c in TEMPLATES for k in range(len(SITES))]
        for f in as_completed(futures):rows.append(f.result())
    errors={a:[r['arms'][a]['synthetic_position_error_km'] for r in rows if r['status']=='complete'] for a in ARMS}
    write(OUT/'evaluation.json',dict(instances=len(rows),failures=[(r['case'],r['site_index'],r.get('error')) for r in rows if r['status']!='complete'],
        errors_km=errors,summary={a:dict(maximum_km=max(v) if v else None,mean_km=float(np.mean(v)) if v else None) for a,v in errors.items()},
        synthetic_localizer_closure_only=True,not_a_DS23_accuracy_gain=True,protocol_sha256=sha(target)))


def readable(value):
    import json
    return json.loads(json.dumps(value))


if __name__=='__main__':main()
