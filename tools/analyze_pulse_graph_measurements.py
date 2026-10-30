"""Frozen graph partition and template-only CFO bias diagnostics; no location fit."""
import argparse,hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from probe_native_fft_bias import response_curve,debias
from leo.analysis.research.grouped_prediction import geometry_partition_schedule,replay_split,polynomial_reference


def canonical_correction(values,response):
    """Apply only to original GLRT CFO, before any track alias lift."""
    values=np.asarray(values,float)
    if not np.isfinite(values).all():raise ValueError('finite original CFO required')
    eligible=(abs(values)>1000)&(abs(values)<399000)
    correction=np.zeros_like(values);correction[eligible]=debias(values[eligible],response)-values[eligible]
    return correction,eligible


def centered_metrics(times,residual,split_s=182.5):
    t,r=np.asarray(times,float),np.asarray(residual,float);r=r-r.mean()
    return dict(centered_RMS_hz=float(np.sqrt(np.mean(r*r))),
        slope_hz_s=float(np.polyfit(t-t.mean(),r,1)[0]),
        late_minus_early_hz=float(r[t>=split_s].mean()-r[t<split_s].mean()) if (t>=split_s).any() and (t<split_s).any() else None)


def run(args):
    r=read(args.diagnostic);hashes={}
    def load(p):
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();return read(p)
    load(args.diagnostic)
    fragments=[f for f in r['arms'][0]['fragments'] if f['shared_family'] or not f['calibration_points']]
    components=[f['component'] for f in fragments]
    rows=r['observations'];values=np.array([o['measured_cfo_hz'] for o in rows]);times=np.array([o['time_s'] for o in rows])
    member=np.array([o['component'] in components for o in rows]);labels=np.array([o['component'] for o in rows])
    curve=response_curve(r['job']['sample_rate_hz'],'upper');delta,eligible=canonical_correction(values,curve)
    metrics=[]
    for arm in r['arms']:
        residual=np.array(arm['residual_without_fragment_constants_hz'])
        for component in components+['union']:
            use=member if component=='union' else labels==component
            for method,d in [('original',np.zeros(len(times))),('template_only',delta)]:
                metrics.append(dict(arm=arm['arm'],component=component,method=method,points=int(use.sum()),
                    **centered_metrics(times[use],(residual+d)[use])))
    # Recover archived acquisition estimates; this tests measurement semantics,
    # not the identity of the exact shared object originally executed.
    visits={o['visit_index']:o for o in rows};native=[]
    manifest=load(args.analysis_root/'manifest.json')
    for path in sorted(args.analysis_root.glob('scientific/fast-scan/*/*.json')):
        document=read(path);selected=[w for w in document['windows'] if w['visit'] in visits]
        if not selected:continue
        load(path)
        for w in selected:
            o=visits[w['visit']];rx=next(x for x in w['receivers'] if x['receiver_id']==o['native_receiver_id'])
            c=next(x for x in rx['candidates'] if x['candidate_rank']==o['winner']['candidate_rank'])
            if abs(c['fractional_tracking_cfo_hz']-o['measured_cfo_hz'])>1e-8:raise ValueError('archived measurement mismatch')
            native.append(dict(observation_id=o['observation_id'],visit=w['visit'],iq_sha256=w['iq_sha256'],edge=w['edge'],candidate=c,source=str(path)))
    if len(native)!=len(rows) or len({o['observation_id'] for o in native})!=len(rows):raise ValueError('incomplete native provenance')
    if {o['edge'] for o in native}!={'upper'}:raise ValueError('response edge mismatch')
    all_obs=load(Path(r['job']['root'])/r['job']['case']/'observations.json')
    schedule=geometry_partition_schedule(np.array([o['time_s'] for o in all_obs]),times[member],seeds=[20261029,94721,4081,434541565,834719],required=3)
    if not schedule['ready']:raise ValueError('three distinct partitions required')
    graph_values={oid:value for f in fragments for oid,value in zip(f['original_graph']['observation_ids'],f['original_graph']['values'],strict=True)}
    use_rows=[o for o in rows if o['observation_id'] in graph_values];tt=np.array([o['time_s'] for o in use_rows]);yy=np.array([graph_values[o['observation_id']] for o in use_rows]);ll=np.array([o['component'] for o in use_rows])
    folds=[]
    for split in schedule['selected']:
        train,held=replay_split(tt,split)
        for grouping in ('union','original_partition'):
            groups=[np.ones(len(tt),bool)] if grouping=='union' else [ll==c for c in components]
            fits=[]
            for use in groups:
                fits.append(polynomial_reference(tt[use],yy[use],train[use],held[use]))
            n=sum(f['held']['points'] for f in fits)
            folds.append(dict(seed=split['seed'],grouping=grouping,held_points=n,
                negative_twice_log_density=sum(f['held']['negative_twice_log_density'] for f in fits),
                held_RMS_hz=float(np.sqrt(sum(f['held']['rms_hz']**2*f['held']['points'] for f in fits)/n)),
                orders=[f['order'] for f in fits],fits=fits))
    write(args.output,dict(metrics=metrics,response=curve,correction_hz=delta,correction_eligible=eligible,
        native_measurements=native,analysis_release_id=manifest['pipeline_release_id'],
        native_acquired_equals_fractional=all(abs(n['candidate']['acquired_cfo_hz']-n['candidate']['fractional_tracking_cfo_hz'])<1e-8 for n in native),
        source_hashes=hashes,partition_schedule=schedule,polynomial_folds=folds,
        correction_not_fitted_to_observations=True,capture_binary_identity_not_established=True,
        fixed_position_receiver_orbit_and_pulse=True,GPS_used=False,future_TLE=False,
        frozen_graph_conditioned=True,polynomial_fits_are_not_satellite_predictions=True,
        new_association_or_position_fit=False))
    for m in metrics:print(m,flush=True)
    for f in folds:print({k:v for k,v in f.items() if k!='fits'},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('diagnostic','analysis-root','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
