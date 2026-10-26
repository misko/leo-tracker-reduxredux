"""Frozen chronological conditional forecasts of one exposed complete owner."""
import argparse
from pathlib import Path
import signal
import sys
import time
import traceback

START = time.monotonic()
import numpy as np
from scipy.special import roots_legendre
import conditional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OLD = Path('/srv/bulk/leo/research/ds24-cached-ambiguity-r01/witness')
sys.path.insert(0, str(OLD))
import contrast as base
r, w, k, sr = base.r, base.w, base.k, base.sr
ARMS = ('c0', 'fitted_c')
MODELS = ('nominal', 'three_modes')
ORDERS = (32, 64)
CAP = 300.


def read(path):
    return base.read(path)


def sha(path):
    return base.sha(path)


def write(name, value):
    r.write_new(HERE / name, value)


def save_arrays(name, **arrays):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        np.savez_compressed(stream, **arrays)


def rules(support, order, candidate):
    pieces = np.asarray(sr.sg.panels(support['inner_visible_intervals'],
                                     np.asarray(support['interpolation_breakpoints'])))
    z, weights = roots_legendre(order)
    half, center = np.diff(pieces, axis=1)[:, 0] / 2, pieces.mean(axis=1)
    nodes = (center[:, None] + half[:, None]*z).ravel()
    logw = (np.log(half[:, None]) + np.log(weights)[None]).ravel()
    law = sr.law(candidate)
    # One alias prior belongs to the COMPLETE owner, once in train and joint.
    logw += law['distribution'].logpdf(nodes) - np.log(law['mass']) - np.log(9)
    return nodes, logw, len(pieces), law


def prepare():
    base.threads(); sr.alarm(180.)
    oldrf = read(OLD / 'RF_seal.json')
    paths = [OLD / (arm + '_full_parent.npz') for arm in ARMS]
    paths += [OLD / (arm + '_full_parent_parent.json') for arm in ARMS]
    for path in paths:
        if sha(path) != oldrf['files'][str(path)]:
            raise ValueError('Original full-parent snapshot changed')
    d, x, family, target, entry = base.input_context()
    candidate = k.candidate(w.owner_context(d, entry), base.NORAD)
    if not np.array_equal(candidate['target_sky']['time_s'], candidate['target_mode_bank']['time_s']):
        raise ValueError('Original causal bank grids differ')
    arrays = {arm: dict(np.load(OLD / (arm + '_full_parent.npz'))) for arm in ARMS}
    first = arrays['c0']
    for arm, values in arrays.items():
        if list(values['native_ids']) != entry['observation_ids'] or not np.array_equal(values['x'], x):
            raise ValueError('Complete native ID/common RF point changed')
        if not np.array_equal(values['q'], first['q']) or not np.array_equal(values['times'], first['times']):
            raise ValueError('Paired observation/RF normalization changed')
        if np.linalg.eigvalsh(values['covariance'] - 300.**2*np.ones((29, 29))).min() <= 0:
            raise ValueError('One shared owner constant not present with positive remaining covariance')
        save_arrays(arm + '_input.npz', **values)
    folds = conditional.split_indices(first['times'], first['native_ids'])
    write('split.json', dict(rule='Sort(time_s,native_ID), first14 vs last15, then reverse',
        folds=[dict(name=name, train_indices=train, held_indices=held,
                    train_IDs=first['native_ids'][train], held_IDs=first['native_ids'][held]) for name, train, held in folds],
        complete_owner_IDs=entry['observation_ids'], identity_selected_on_all_D=True))
    observer = sr.geodetic_to_ecef_km(*k.latlon(x), 0.)
    up = sr.ecef_to_enu_matrix(*k.latlon(x))[2]
    support = sr.sg.support(candidate['target_sky'], first['times'], up, observer)
    write('support.json', support)
    if (not support['certified'] or support['root_brackets']
        or len(support['inner_visible_intervals']) != 1
        or not np.allclose(support['inner_visible_intervals'][0], [-15, 15], atol=1e-12, rtol=0)):
        raise ValueError('Full-owner full-domain nominal visibility prerequisite failed')
    geometry_records = []
    for order in ORDERS:
        nodes, logweights, panels, law = rules(support, order, candidate)
        frequency = np.empty((len(nodes), 29)); modes = np.empty((len(nodes), 29, 3))
        minimum = np.inf
        for start in range(0, len(nodes), 512):
            geometry = k.m.q.phase_geometry(candidate, x, nodes[start:start+512])
            stop = start + len(geometry['frequency_hz'])
            frequency[start:stop] = geometry['frequency_hz'] * first['q'][None]
            modes[start:stop] = geometry['shape_columns_hz'] * first['q'][None, :, None]
            minimum = min(minimum, float(np.min(geometry['elevation_deg'])))
        if minimum < 0:
            raise ValueError('Certified full visibility/node replay disagrees')
        save_arrays('geometry_GL' + str(order) + '.npz', nodes=nodes,
            log_prior_weights=logweights, frequency=frequency, modes=modes)
        phase_alias_mass = float(np.exp(logweights).sum() * 9)
        if abs(phase_alias_mass - 1.) > 1e-8:
            raise ValueError('Original normalized phase/one-alias prior mass failed')
        geometry_records.append(dict(order=order, panels=panels, nodes=len(nodes), minimum_elevation_deg=minimum,
                                     quadrature_phase_times_alias_prior_mass=phase_alias_mass))
    # Actual serialized-port smoke: three fixed prior-design nodes, not a
    # reported quadrature forecast. No rule or split is selected from scores.
    phases = np.asarray([law['location'] - .1, law['location'], law['location'] + .1])
    g = k.m.q.phase_geometry(candidate, x, phases)
    smoke = dict(nodes=phases, log_prior_weights=law['distribution'].logpdf(phases)-np.log(law['mass'])-np.log(9),
        frequency=g['frequency_hz']*first['q'][None], modes=g['shape_columns_hz']*first['q'][None,:,None])
    checks = []
    for arm in ARMS:
        for fold, train, held in folds:
            for model in MODELS:
                original = conditional.evaluate(arrays[arm]['raw'], arrays[arm]['covariance'], smoke, train, held,
                                                model == 'three_modes', k.PERIOD)
                changed = arrays[arm]['raw'].copy(); changed[held] += 1000.
                redacted = conditional.evaluate(changed, arrays[arm]['covariance'], smoke, train, held,
                                                model == 'three_modes', k.PERIOD)
                errors = {key: float(np.max(abs(original[key]-redacted[key]))) for key in
                          ('prediction_mean','prediction_covariance','posterior_node_alias_mass','alias_probabilities')}
                if max(errors.values()) != 0:
                    raise ValueError('Held response leaked into forecast/train posterior')
                checks.append(dict(arm=arm, fold=fold, model=model, errors=errors,
                    original_joint_conditional_error=original['joint_conditional_identity_error']))
    signal.setitimer(signal.ITIMER_REAL, 0)
    write('preparation.json', dict(seconds=time.monotonic()-START, geometry=geometry_records,
        redaction_smoke=checks, no_primary_forecast_outcome_read=True,
        phase_prior=dict(location=law['location'], marginal_SD=law['sd'], scale=law['sd']/np.sqrt(3), interval_mass=law['mass'])))
    bindings = dict(read(OLD / 'protocol.json')['bindings'])
    for path in paths + [OLD / 'RF_seal.json', ROOT / 'COORDINATOR_PLAN.md']:
        bindings[str(path)] = sha(path)
    for path in HERE.iterdir():
        if path.is_file() and path.name != 'protocol.json':
            bindings[str(path)] = sha(path)
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and path.endswith('.py') and path.startswith((str(r.REPO), '/srv/bulk/leo/research/')):
            bindings[path] = sha(path)
    for path, expected in bindings.items():
        if sha(path) != expected:
            raise ValueError('Frozen dependency changed: ' + path)
    write('protocol.json', dict(schema='same-owner-chronological-prediction/v1', bindings=bindings,
        arms=ARMS, models=MODELS, folds=[name for name, _, _ in folds], slots=8,
        orders=ORDERS, primary_order=64, preparation_seconds=read(HERE/'preparation.json')['seconds'],
        test_seconds=read(HERE/'test_receipt.json')['seconds'], cap_worker_seconds=CAP,
        numerical_workers=1, BLAS_threads=1, tolerances=dict(score=1e-3, phase=1e-4, alias=1e-6,
            prediction_Hz=.1, shape=1e-4, constant_Hz=.01, conditional_identity=1e-6),
        identity_validation=False, position_fits=0, no_new_identity_admission=True))
    print('PREPARED', sha(HERE/'protocol.json'), flush=True)


def verify():
    protocol = read(HERE/'protocol.json')
    for path, expected in protocol['bindings'].items():
        if sha(path) != expected:
            raise ValueError('Frozen input/source changed: ' + path)
    receipt = read(ROOT/'audit/prediction_preflight.json')
    if not receipt['all_passed'] or receipt['protocol_sha256'] != sha(HERE/'protocol.json'):
        raise ValueError('Exact independent preflight required')
    return protocol


def check(a, b, tolerance):
    return dict(held_score=abs(a['held_negative_twice_log_density']-b['held_negative_twice_log_density'])<=tolerance['score'],
        train_score=abs(a['train_log_evidence']-b['train_log_evidence'])<=tolerance['score'],
        phase=abs(a['phase_mean_s']-b['phase_mean_s'])<=tolerance['phase'] and abs(a['phase_SD_s']-b['phase_SD_s'])<=tolerance['phase'],
        alias=np.max(abs(a['alias_probabilities']-b['alias_probabilities']))<=tolerance['alias'],
        prediction=np.max(abs(a['prediction_mean']-b['prediction_mean']))<=tolerance['prediction_Hz'] and np.max(abs(a['prediction_SD']-b['prediction_SD']))<=tolerance['prediction_Hz'],
        shape=not len(a['shape_mean']) or np.max(abs(a['shape_mean']-b['shape_mean']))<=tolerance['shape'],
        constant=abs(a['source_constant_mean_Hz']-b['source_constant_mean_Hz'])<=tolerance['constant_Hz'],
        conditional_identity=max(a['joint_conditional_identity_error'],b['joint_conditional_identity_error'])<=tolerance['conditional_identity'])


def run():
    base.threads(); protocol=verify()
    prefix=protocol['preparation_seconds']+protocol['test_seconds']
    began=time.monotonic(); sr.alarm(CAP-prefix)
    write('execution_started.json', dict(protocol_sha256=sha(HERE/'protocol.json'), prefix_worker_seconds=prefix))
    slots=[]
    try:
        for arm in ARMS:
            raw=dict(np.load(HERE/(arm+'_input.npz')))
            folds=conditional.split_indices(raw['times'],raw['native_ids'])
            for fold,train,held in folds:
                for model in MODELS:
                    start=time.monotonic(); values={}
                    name=arm+'_'+fold+'_'+model
                    for order in ORDERS:
                        geometry=dict(np.load(HERE/('geometry_GL'+str(order)+'.npz')))
                        value=conditional.evaluate(raw['raw'],raw['covariance'],geometry,train,held,model=='three_modes',k.PERIOD)
                        arrays={key:value.pop(key) for key in ('prediction_mean','prediction_covariance','prediction_SD','posterior_node_alias_mass','held_raw_residual')}
                        save_arrays(name+'_GL'+str(order)+'.npz',**arrays)
                        write(name+'_GL'+str(order)+'.json',value)
                        values[order]=dict(value,**arrays)
                    checks=check(values[32],values[64],protocol['tolerances'])
                    result=dict(arm=arm,fold=fold,model=model,status='complete',train_indices=train,held_indices=held,
                        orders={str(order):{key:val for key,val in v.items() if key not in ('prediction_mean','prediction_covariance','prediction_SD','posterior_node_alias_mass','held_raw_residual')} for order,v in values.items()},
                        checks=checks,numerically_qualified=all(checks.values()),seconds=time.monotonic()-start,
                        independent_identity_validation=False,position_fit=False,held_values_used_for_training=False)
                    write(name+'_result.json',result); slots.append(dict(arm=arm,fold=fold,model=model,status='complete',qualified=result['numerically_qualified'],seconds=result['seconds']))
                    print(arm,fold,model,result['numerically_qualified'],flush=True)
    except Exception as exc:
        write('failure.json',dict(error=repr(exc),traceback=traceback.format_exc()))
    finally:signal.setitimer(signal.ITIMER_REAL,0)
    complete={(q['arm'],q['fold'],q['model']) for q in slots}
    slots += [dict(arm=a,fold=f,model=m,status='unavailable') for a in ARMS for f in protocol['folds'] for m in MODELS if (a,f,m) not in complete]
    write('execution.json',dict(slots=slots,cumulative_worker_seconds=prefix+time.monotonic()-began,
        run_wall_seconds=time.monotonic()-began,position_fits=0,GPS_used=False,identity_admissions=0))
    verify()
    write('RF_seal.json',dict(protocol_sha256=sha(HERE/'protocol.json'),files={str(p):sha(p) for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts}))
    print('TERMINAL',read(HERE/'execution.json')['cumulative_worker_seconds'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','run'])
    globals()[parser.parse_args().action]()
