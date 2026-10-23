"""Bounded family-held-out position diagnostics; evaluation GPS stays in reporting."""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import argparse
import contextlib
import signal
import sys
import time
import traceback
import numpy as np
from scipy.stats import chi2
import mechanism as m
sys.path.insert(0, '/srv/bulk/leo/research/algo04-native-mechanisms-20261023/audit')
from diagnostics import decompose

OUT = Path(__file__).resolve().parents[1]
CASES = ('DS23-0259', 'DS23-0353')


def conditional(raw, covariance, held):
    """Joint Gaussian H|R, retaining cross-family shared calibration covariance."""
    y, k, h = np.asarray(raw, float), np.asarray(covariance, float), np.asarray(held, bool)
    if k.shape != (len(y), len(y)) or h.shape != y.shape or not h.any():
        raise ValueError('nonempty held vector and matching covariance required')
    r = ~h
    mean = np.zeros(h.sum())
    cov = k[np.ix_(h, h)].copy()
    if r.any():
        cross = k[np.ix_(h, r)]
        mean = cross @ np.linalg.solve(k[np.ix_(r, r)], y[r])
        cov -= cross @ np.linalg.solve(k[np.ix_(r, r)], cross.T)
    cov = (cov + cov.T) / 2
    innovation = y[h] - mean
    root = np.linalg.cholesky(cov)
    whitened = np.linalg.solve(root, innovation)
    q = float(whitened @ whitened)
    logdet = float(2 * np.log(np.diag(root)).sum())
    return dict(raw_residual_hz=y[h], conditional_mean_correction_hz=mean,
                innovation_hz=innovation, covariance_hz2=cov,
                quadratic=q, logdet=logdet, score=q+logdet+int(h.sum())*np.log(2*np.pi),
                points=int(h.sum()), quadratic_per_point=q/h.sum(),
                diagnostic_chi2_upper_tail=float(chi2.sf(q, h.sum())))


def family_mask(p, family):
    held = np.zeros(len(p.keep), bool)
    for row, sl in zip(p.rows, p.slices, strict=True):
        if int(p.scan.norads[row['candidate_index']]) == family:
            held[sl] = p.keep[sl]
    return held


def training_data(full, kind, family, mode):
    p = m.exp.paths.build(full, kind, 'c0', np.zeros(len(full['means'])))
    held = family_mask(p, family) if mode == 'whole_family' else np.zeros(len(p.keep), bool)
    keep = np.asarray(full['keep']).copy()
    keep[held] = False
    entries = [e for e in full['entries'] if int(p.scan.norads[e['candidate_index']]) != family]
    return dict(full, keep=keep, entries=entries), held


def design_blocks(p):
    a = p.hardware.shape[1]; b = a + p.smooth.shape[1]
    c = b + len(p.labels); d = c + 3*len(p.supported)
    return [('radio_hardware', 0, a), ('receiver_smooth', a, b),
            ('satellite_phase', b, c), ('satellite_orbit', c, d),
            ('fragment_constant', d, d+len(p.members))]


def local_sensitivity(p, x, step=.001):
    """Gauss-Newton sensitivity of actual residual objective, not a confidence region."""
    jac = []; derivative = []
    for j in range(2):
        dx = np.eye(2)[j]*step
        plus, minus = p.calculate(x+dx), p.calculate(x-dx)
        jac.append((np.asarray(plus['residual'])-minus['residual'])/(2*step))
        derivative.append((np.asarray(plus['coefficient'])-minus['coefficient'])/(2*step))
    info = np.array(jac) @ np.array(jac).T
    val, vec = np.linalg.eigh(info)
    coeff_change = np.array(derivative).T @ vec[:, 0]
    blocks = {name:float(np.linalg.norm(coeff_change[a:b])) for name,a,b in design_blocks(p)}
    return dict(information=info, eigenvalues=val, weak_direction_east_north=vec[:,0],
                condition_number=float(val[-1]/val[0]) if val[0]>0 else None,
                coefficient_derivative_norm_by_block=blocks,
                note='dimensionless standardized design coefficient change per km along weak direction; block dimensions differ; not posterior correlation',
                finite_difference_km=step, fixed_phase_reference=True,
                uncertainty_warning='local profiled residual sensitivity including empirical precision changes; not calibrated position covariance')


def prediction(full, train, held_curved, kind, arm, saved, family):
    # All native observations are represented jointly, but their held family did
    # not enter the preceding fit; none enter the curved normal equations here.
    d = dict(train, entries=full['entries'])
    p = m.exp.paths.build(d, kind, arm, saved['phase_reference'])
    x = np.asarray(saved['endpoint_east_north_km'])
    dense = decompose(p, x, d['powers'])
    c = p.curved_calculate(x)
    y = dense['raw_residual_hz']; k = dense['covariance_hz2']
    h = np.zeros(len(y), bool); metadata = []; ids = []
    for e, (start, stop) in zip(d['entries'], dense['entry_slices'], strict=True):
        t = p.scan.tracks[e['track_index']]
        is_held = int(p.scan.norads[e['candidate_index']]) == family
        h[start:stop] = is_held
        ids.extend(t['observation_ids'])
        metadata.extend([dict(key=e['component'], family=int(p.scan.norads[e['candidate_index']]),
                              receiver=int(t['receiver']), channel=int(t['channel']), band='high' if t['channel']>4 else 'low',
                              time_s=float(tm), role='native') for tm in t['times']])
    native = conditional(y, k, h)
    if held_curved.any():
        u = c['features'][held_curved]
        cov = dense['coefficient_covariance']
        noise = p.point_noise[held_curved]*np.sqrt(2/np.asarray(d['powers'])[p.noise_groups[held_curved]])
        curve_cov = u @ cov @ u.T + np.diag(noise**2)
        cross = dense['features'] @ cov @ u.T
        k = np.block([[k,cross],[cross.T,curve_cov]])
        y = np.r_[y,c['conditional_residual_hz'][held_curved]]
        h = np.r_[h,np.ones(int(held_curved.sum()),bool)]
        for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
            t=p.scan.tracks[i]
            for use,oid,tm in zip(held_curved[sl],t['observation_ids'],t['times'],strict=True):
                if use:
                    ids.append(oid)
                    metadata.append(dict(key=t['key'],family=int(p.scan.norads[row['candidate_index']]),
                                         receiver=int(t['receiver']),channel=int(t['channel']),band='high' if t['channel']>4 else 'low',
                                         time_s=float(tm),role='curved'))
    assert len(ids)==len(set(ids))==len(y)
    result=conditional(y,k,h)
    selected=[v for v,use in zip(metadata,h,strict=True) if use]
    held_ids=[v for v,use in zip(ids,h,strict=True) if use]
    training_ids={o for i,sl in zip(p.members,p.slices,strict=True) for o,use in zip(p.scan.tracks[i]['observation_ids'],p.keep[sl],strict=True) if use}
    training_ids.update(o for e in train['entries'] for o in e['observation_ids'])
    assert not training_ids.intersection(held_ids)
    result.update(metadata=selected,observation_ids=held_ids,training_ID_overlap=0,
                  native_only={key:value for key,value in native.items() if key not in ('covariance_hz2',)},
                  full_shared_covariance=True,graph_discovery_conditioned_on_original_data=True,
                  no_held_family_position_or_calibration_data=bool(held_curved.any()))
    # Compact path means with exact covariance of each arithmetic mean.
    path_rows=[]
    for key in dict.fromkeys(v['key'] for v in selected):
        use=np.array([v['key']==key for v in selected]); weights=use/use.sum()
        mean=float(weights@result['innovation_hz']);sd=float(np.sqrt(weights@result['covariance_hz2']@weights))
        vals=result['innovation_hz'][use]
        path_rows.append(dict(selected[np.flatnonzero(use)[0]],points=int(use.sum()),
                              mean_innovation_hz=mean,mean_prediction_sd_hz=sd,mean_z=mean/sd,
                              centered_RMS_hz=float(np.sqrt(np.mean((vals-mean)**2)))))
    result['path_means']=path_rows
    return result


def run(job):
    dest=OUT/'raw'/job['name'];dest.mkdir(parents=True,exist_ok=True)
    path=dest/'result.json'
    if path.exists():return dict(name=job['name'],status=m.read(path)['status'],reused=True)
    start=time.monotonic();result=dict(job=job,status='failed')
    with (dest/'run.log').open('w') as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
        try:
            signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180s job cap')));signal.alarm(180)
            parent,kind,fragments,record=m.load(job['case']);full=m.append(parent,fragments)
            train,held=training_data(full,kind,job['family'],job['mode'])
            pair={arm:m.refit(parent,train,kind,arm,1.) for arm in m.ARMS}
            predictions={arm:prediction(full,train,held,kind,arm,s,job['family']) for arm,s in pair.items()}
            assert predictions['c0']['observation_ids']==predictions['fitted_c']['observation_ids']
            sensitivity={}
            for arm,saved in pair.items():
                p=m.exp.paths.build(train,kind,arm,saved['phase_reference'])
                sensitivity[arm]=local_sensitivity(p,np.asarray(saved['endpoint_east_north_km']))
            result.update(status='complete',arms=pair,predictions=predictions,sensitivity=sensitivity,
                          paired_training_gates_pass=m.exp.qualifies(pair),
                          removed_curved_points=int(held.sum()),
                          held_native_points=predictions['c0']['native_only']['points'])
        except Exception as exc:result.update(error=repr(exc),traceback=traceback.format_exc())
        finally:signal.alarm(0)
        result['seconds']=time.monotonic()-start;m.write(path,result)
    return dict(name=job['name'],status=result['status'],seconds=result['seconds'],error=result.get('error'))


def freeze():
    jobs=[];inputs={};selection={}
    for case in CASES:
        path=m.FROZEN/'raw'/case/'native'/(case+'_persistent5s_selection.json')
        fragments=m.read(path)['selected']
        sizes={j:sum(len(f['times']) for f in fragments if f['norad']==j) for j in {f['norad'] for f in fragments}}
        families=sorted(sizes,key=lambda j:(-sizes[j],j))[:4]
        selection[case]=dict(all_native_family_point_counts=sizes,selected=families)
        for family in families:
            for mode in ('native_only','whole_family'):
                jobs.append(dict(name=f'{case}_{family}_{mode}',case=case,family=family,mode=mode))
        for f in [path,m.FROZEN/'raw'/case/'result.json',m.FROZEN/'raw'/case/'native'/(case+'.json')]:inputs[str(f)]=m.sha(f)
    protocol=dict(jobs=jobs,selection=selection,source_sha256=m.sha(Path(__file__)),input_hashes=inputs,
                  selection_rule='top4 new families by native point count, NORAD tie break; identical bothc arms',
                  c_arms=m.ARMS,fit='cold region center, zero phase reference,5rounds x48ordinaryiterations',
                  held_modes='native_only:leave all native entries of family out; whole_family:also leave original retained curved family out',
                  score='Schur-complement Gaussian family prediction conditional on other predictive entries, full shared curved-calibration covariance',
                  covariance='empirical Bayes Gaussian, fixed identities/aliases/discovery; curve measurement variance2sigma²/power; native2sigma²+300Hzpathbias',
                  tests='chi2 tails diagnostic only; preregistered flag p<.01/(4families*2arms) in BOTH arms, not adoption criterion',
                  local_information='GN actual residual sensitivity fixed phase; not calibrated posterior uncertainty',
                  no_GPS_inference=True,no_future_TLE=True,no_new_RF=True,no_production_adoption=True,
                  region_center=[37.906,-122.545],region_width_km=25,job_cap_seconds=180)
    dest=OUT/'protocol.json'
    if dest.exists():assert m.read(dest)==__import__('json').loads(__import__('json').dumps(protocol))
    else:m.write(dest,protocol)
    return jobs


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=4);parser.add_argument('--freeze-only',action='store_true');args=parser.parse_args()
    jobs=freeze()
    if not args.freeze_only:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for result in as_completed([pool.submit(run,j) for j in jobs]):print(result.result(),flush=True)
