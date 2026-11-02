"""Bounded matched-arm full-data sensitivity; no production mutations."""
import argparse
import copy
import hashlib
import json
import signal
import time
from pathlib import Path
import numpy as np
from prototype import ROOT, INPUT, SCALES, configure, select_family, candidate_context, e
from algo06_science.common import read, write
from algo07_science import previous
from algo07_science.diagnose import objective
from algo06_science.position import family_score
from prototype_dsx01_continuous_position import latlon


def evaluation_error(x):
    # Called only after fit and original qualification have completed.
    site = np.deg2rad((37.849061591561885,-122.48574968092912))
    at = np.deg2rad(latlon(x))
    h = np.sin((at[0]-site[0])/2)**2+np.cos(at[0])*np.cos(site[0])*np.sin((at[1]-site[1])/2)**2
    return float(6371008.8*2*np.arcsin(np.sqrt(h)))


def native_ids(d):
    p = d['problems']['fitted_c'][0]
    return sorted(o for i,sl in zip(p.members,p.slices)
                  for o,use in zip(d['scan'].tracks[i]['observation_ids'],p.keep[sl]) if use)


def run(case):
    began=time.monotonic()
    signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('900s first experiment cap')))
    signal.alarm(900)
    out=ROOT/case;out.mkdir(parents=True,exist_ok=True)
    configure()
    d,z,replay=e.load_case(case)
    family,ranking=select_family(d,z)
    expected=native_ids(d)
    start=np.asarray(d['problems']['fitted_c'][1]).copy()
    reference=d['problems']['fitted_c'][0].reference.copy()
    shared=dict(d,problems=dict(d['problems']))
    for arm,(p,_) in d['problems'].items():
        q=copy.copy(p);q.reference=reference.copy();shared['problems'][arm]=(q,start.copy())
    write(out/'plan.json',dict(case=case,selected_family=family,ranking=ranking,
        shared_start=start,shared_phase_reference=reference,replay=replay,
        input_sha256=hashlib.sha256((INPUT/'inputs'/(case+'.json')).read_bytes()).hexdigest(),
        native_ids_sha256=hashlib.sha256('\n'.join(expected).encode()).hexdigest(),
        native_ids=expected,active_points=len(expected),protocol_sha256=hashlib.sha256((ROOT/'protocol.json').read_bytes()).hexdigest()))
    for scale in SCALES:
        dd=candidate_context(shared,z,scale,family)
        for arm in ('c0','fitted_c'):
            path=out/(f'scale{scale:g}-{arm}.json')
            if path.exists():continue
            row=previous.fit(dd,z,arm,start,True,rounds=15)
            p,ctx=e.build(dd,z,arm,np.asarray(row['reference']))
            x=np.asarray(row['x']);c=p.calculate(x)
            _,details=family_score(ctx['families'],ctx,p,x,details=True)
            row['mixture_phase_boundary_masses']=[f['phase_boundary_mass'] for f in details]
            row['mixture_phase_interior']=all(f['phase_boundary_mass']<.01 for f in details)
            ids=sorted(o for t in row['tracks'] for o in t['observation_ids'])
            row['native_ids_preserved']=ids==expected and len(ids)==len(set(ids))
            row['fully_qualified']=bool(row['qualified'] and row['mixture_phase_interior'] and
                row['native_ids_preserved'] and not row['lost_ids'] and not row['reassigned_ids'])
            row.update(arm=arm,SD_scale=scale,covariance_scale=scale**2,selected_family=family,
                model='family_physical_covariance_scale',start_policy='shared published fitted-c RF endpoint/reference',
                native_ids_sha256=hashlib.sha256('\n'.join(ids).encode()).hexdigest(),
                decomposition={k:c[k] for k in ('quadratic','logvolume','gamma_cost','normalization_constant','negative_twice_elbo','precision_iterations','final_log_precision_change') if k in c},
                family_discrepancy=p.family_discrepancy,
                score_scope='existing normalized hierarchical generalized ELBO plus unchanged predictive-family terms',
                evaluation_error_m=evaluation_error(x),status='complete')
            np.savez_compressed(out/(f'scale{scale:g}-{arm}-native.npz'),times_s=p.flat_times,
                values_hz=p.values,keep=p.keep,residual_hz=c['conditional_residual_hz'],
                adjusted_hz=p.values-c['conditional_residual_hz'],orbit_hz=p.q*c['frequency'],
                features=c['features'],coefficient=c['coefficient'],phase=p.state(x)['phases'])
            write(path,row)
            print(case,scale,arm,'score',round(row['objective'],2),'GPS_m',round(row['evaluation_error_m'],1),
                  'qualified',row['fully_qualified'],'closure',row['phase_closed'],'sec',round(time.monotonic()-began),flush=True)
    write(out/'completion.json',dict(status='complete',seconds=time.monotonic()-began))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('case');run(ap.parse_args().case)
