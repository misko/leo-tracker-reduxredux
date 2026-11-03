"""Describe remaining raw CFO trajectories in a frozen development endpoint."""

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
DATA = REPORTS / '2026_10_16_dsx01_fast_association_losses'
RESULTS = REPORTS / '2026_10_17_dsx01_iteration4/frequency_bias/results'
BUILDER = REPORTS / '2026_10_16_dsx01_models/model_b.py'
ALIAS_HZ = 1 / 4.4e-6


def sha(path):
    return 'sha256:' + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local_unwrap(values):
    y = np.asarray(values, float)
    if y.ndim != 1 or not len(y) or not np.isfinite(y).all():
        raise ValueError('Nonempty finite one-dimensional track required')
    increment = (np.diff(y) + ALIAS_HZ / 2) % ALIAS_HZ - ALIAS_HZ / 2
    return np.r_[y[0], y[0] + np.cumsum(increment)]


def curve_summary(times, values):
    t, y = np.asarray(times, float), np.asarray(values, float)
    if t.shape != y.shape or t.ndim != 1 or not np.isfinite(t).all() or not np.isfinite(y).all():
        raise ValueError('Aligned finite track times/values required')
    if len(t) < 3 or len(np.unique(t)) != len(t):
        return dict(degree=None, rms_hz=None, maximum_absolute_residual_hz=None,
                    leave_one_out_rms_hz=None, slope_at_center_hz_s=None,
                    curvature_hz_s2=None)
    degree = 2 if len(t) >= 5 else 1
    center = t.mean()
    scale = float(np.ptp(t))
    x = (t-center)/scale
    design = np.vander(x, degree+1, increasing=True)
    coefficients = np.linalg.lstsq(design, y-y.mean(), rcond=None)[0]
    residual = y-y.mean()-design@coefficients
    q, _ = np.linalg.qr(design, mode='reduced')
    denominator = 1-(q*q).sum(axis=1)
    loo = residual/denominator
    return dict(degree=degree, rms_hz=float(np.sqrt(np.mean(residual**2))),
                maximum_absolute_residual_hz=float(np.max(abs(residual))),
                leave_one_out_rms_hz=float(np.sqrt(np.mean(loo**2))),
                slope_at_center_hz_s=float(coefficients[1]/scale),
                curvature_hz_s2=float(2*coefficients[2]/scale**2) if degree == 2 else None)


def describe(rows, associated):
    rows = sorted(rows, key=lambda r: (r['time_s'], r['observation_id']))
    t = np.array([r['time_s'] for r in rows])
    y = np.array([r['measured_cfo_hz'] for r in rows])
    a = np.array([associated[r['observation_id']] for r in rows], bool)
    unwrapped = local_unwrap(y)
    result = dict(points=len(rows), unassociated=int((~a).sum()),
                  start_s=float(t[0]), end_s=float(t[-1]), duration_s=float(t[-1]-t[0]),
                  native_cfo_min_hz=float(y.min()), native_cfo_max_hz=float(y.max()),
                  local_unwrapped_span_hz=float(np.ptp(unwrapped)),
                  maximum_principal_increment_hz=float(np.max(abs(np.diff(unwrapped)), initial=0)),
                  raw_alias_jumps=int(np.sum(abs(np.diff(y)) > ALIAS_HZ/2)),
                  all_members_curve=curve_summary(t, unwrapped),
                  unassociated_members_curve=curve_summary(t[~a], unwrapped[~a]),
                  observations=[dict(observation_id=r['observation_id'], time_s=float(tt),
                       raw_cfo_hz=float(yy), local_unwrapped_cfo_hz=float(uu), associated=bool(aa))
                       for r,tt,yy,uu,aa in zip(rows,t,y,unwrapped,a,strict=True)])
    if (~a).any():
        result.update(unassociated_start_s=float(t[~a].min()), unassociated_end_s=float(t[~a].max()),
                      unassociated_native_cfo_min_hz=float(y[~a].min()),
                      unassociated_native_cfo_max_hz=float(y[~a].max()))
    return result


def run():
    paths = [HERE/'PROTOCOL.md',Path(__file__),HERE/'test_audit.py',BUILDER,
             DATA/'membership.csv',DATA/'context-observations.jsonl']
    paths += [RESULTS/f'S{i:02d}-fitted-c-b1000-profile.npz' for i in range(1,6)]
    bindings = {str(p):sha(p) for p in paths}
    with (HERE/'source_freeze.json').open('x') as stream:
        json.dump(dict(files=bindings, orbit_calls=0, localization_fits=0,
                       source_preparations=0, scope='Frozen raw-array track description'),stream,indent=2)
    spec = importlib.util.spec_from_file_location('highcoverage_original_tracklets',BUILDER)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    with (DATA/'membership.csv').open() as stream:
        membership = list(csv.DictReader(stream))
    requested = {r['observation_id'] for r in membership}
    fields = ('source_id','observation_id','time_s','receiver','channel','actual_rf_hz','measured_cfo_hz')
    raw = {}
    for line in (DATA/'context-observations.jsonl').read_text().splitlines():
        row = json.loads(line)
        if row['observation_id'] in requested:
            raw[row['observation_id']] = {k:row[k] for k in fields}
    if len(raw) != 693 or len(membership) != 693:
        raise ValueError('All693 unique frozen winner memberships required')
    associated = {}
    for source in sorted({r['source_id'] for r in membership}):
        with np.load(RESULTS/f'{source}-fitted-c-b1000-profile.npz') as data:
            for key,time,flag in zip(data['observation_id'],data['times_s'],data['associated'],strict=True):
                if str(key) in requested:
                    if float(time) != raw[str(key)]['time_s']:
                        raise ValueError('Frozen raw/endpoint time mismatch')
                    associated[str(key)] = bool(flag)
    if len(associated) != 693 or sum(associated.values()) != 462:
        raise ValueError('Exact frozen462/693 endpoint required')
    fragments,windows = [],[]
    for region in sorted({r['region_id'] for r in membership}):
        rows = [raw[r['observation_id']] for r in membership if r['region_id']==region]
        windows.append(dict(region_id=region,source_id=rows[0]['source_id'],points=len(rows),
                            assigned=sum(associated[r['observation_id']] for r in rows)))
        lanes = sorted({(r['receiver'],r['channel'],r['actual_rf_hz']) for r in rows})
        for rx,ch,rf in lanes:
            lane = sorted([r for r in rows if (r['receiver'],r['channel'],r['actual_rf_hz'])==(rx,ch,rf)],
                          key=lambda r:(r['time_s'],r['observation_id']))
            obs = SimpleNamespace(times_s=np.array([r['time_s'] for r in lane]),
                                  measured_hz=np.array([r['measured_cfo_hz'] for r in lane]),
                                  receiver=np.full(len(lane),rx),channel=np.full(len(lane),ch))
            labels = builder.build_tracklets(obs)
            for label in np.unique(labels):
                segment = [r for i,r in enumerate(lane) if labels[i]==label]
                result = describe(segment,associated)
                result.update(region_id=region,source_id=rows[0]['source_id'],receiver=rx,
                              channel=ch,actual_rf_hz=rf,fragment=int(label))
                fragments.append(result)
    fragments.sort(key=lambda r:(-r['unassociated'],
        r['unassociated_members_curve']['leave_one_out_rms_hz'] if
        r['unassociated_members_curve']['leave_one_out_rms_hz'] is not None else float('inf'),
        r['region_id'],r['start_s']))
    for path,hashed in bindings.items():
        if sha(path)!=hashed:
            raise ValueError('Frozen evidence changed')
    with (HERE/'fragments.json').open('x') as stream:
        json.dump(dict(windows=windows,fragments=fragments,total_points=693,assigned=462,
                       unassociated=231,alias_hz=ALIAS_HZ,identity_truth=False,
                       orbit_calls=0,localization_fits=0),stream,indent=2,allow_nan=False)
    columns=['region_id','source_id','receiver','channel','fragment','points','unassociated',
             'start_s','end_s','duration_s','native_cfo_min_hz','native_cfo_max_hz',
             'local_unwrapped_span_hz','raw_alias_jumps','all_quadratic_rms_hz',
             'all_leave_one_out_rms_hz','unassociated_leave_one_out_rms_hz']
    with (HERE/'fragments.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader()
        for r in fragments:
            row={k:r.get(k) for k in columns}
            row.update(all_quadratic_rms_hz=r['all_members_curve']['rms_hz'],
                all_leave_one_out_rms_hz=r['all_members_curve']['leave_one_out_rms_hz'],
                unassociated_leave_one_out_rms_hz=r['unassociated_members_curve']['leave_one_out_rms_hz'])
            writer.writerow(row)
    print(json.dumps(dict(windows=windows,top_fragments=[{k:r[k] for k in
        ['region_id','receiver','channel','points','unassociated','start_s','end_s',
         'native_cfo_min_hz','native_cfo_max_hz','local_unwrapped_span_hz',
         'all_members_curve','unassociated_members_curve']} for r in fragments[:14]]),indent=2))


if __name__=='__main__':
    run()
