"""NO-REFIT export of declared native held predictions from sealed endpoints."""
import argparse
import csv
import hashlib
import importlib.util
import json
import multiprocessing
from pathlib import Path
import signal
import time
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parent
REPORT = ROOT.parent
REPO = REPORT.parents[1]
CASES = ('DS26-0070', 'DS26-0309', 'DS26-0040', 'DS26-0044', 'FRSH-0004')
WINDOW_SECONDS = 120


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def serial(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: serial(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(item) for item in value]
    return value


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(serial(value), indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def id_hash(ids):
    return hashlib.sha256('\n'.join(ids).encode()).hexdigest()


def column_blocks(p, width):
    nb, ns, nl, no = p.hardware.shape[1], p.smooth.shape[1], len(p.labels), 3 * len(p.supported)
    edges = np.cumsum([0, nb, ns, nl, no, len(p.members)])
    if edges[-1] != width:
        raise ValueError('Unexpected coefficient layout; no guessed covariance decomposition')
    names = ('hardware', 'receiver_smooth', 'phase', 'physical_orbit', 'fragment_constant')
    return {name: slice(int(a), int(b)) for name, a, b in zip(names, edges[:-1], edges[1:], strict=True)}


def conditional_components(features, prior_precision, noise_precision, sigma, train, blocks):
    """Frozen train-only Gaussian covariance, including between-block terms."""
    u = np.asarray(features, float)
    weights = np.asarray(noise_precision, float)[train] / np.asarray(sigma, float)[train] ** 2
    gram = np.diag(prior_precision) + u[train].T @ (u[train] * weights[:, None])
    root = np.linalg.cholesky(gram)
    inverse_root = np.linalg.solve(root, np.eye(len(prior_precision)))
    covariance = inverse_root.T @ inverse_root
    factor = np.linalg.solve(root, u.T).T
    variances = {}
    for name, columns in blocks.items():
        local = u[:, columns]
        variances[name] = np.einsum('ij,jk,ik->i', local, covariance[columns, columns], local)
    total = np.sum(factor ** 2, axis=1)
    cross = total - sum(variances.values())
    return covariance, factor, variances, cross


def disconnected_segments(times, fragment, max_gap=5.0):
    """Never draw a model line across a fragment boundary or a long gap."""
    times, fragment = np.asarray(times), np.asarray(fragment)
    if not len(times):
        return []
    cuts = np.flatnonzero((fragment[1:] != fragment[:-1]) | (np.diff(times) > max_gap)
                          | (np.diff(times) < 0)) + 1
    return np.split(np.arange(len(times)), cuts)


def extract(d, z, plan, split, row, numerical):
    """Rebuild one saved endpoint; no optimizer or posterior update sees held y."""
    from algo07_science.diagnose import objective
    from algo07_science import engine as e
    from leo.analysis.research.retained_track_likelihood import PERIOD
    base = d['problems']['fitted_c'][0]
    native = numerical.native(base)
    train = np.isin(native['ids'], split['train_ids'])
    held = np.isin(native['ids'], split['held_ids'])
    if set(native['ids'][train]) != set(split['train_ids']) or set(native['ids'][held]) != set(split['held_ids']):
        raise ValueError('Saved train/held IDs do not match reconstructed native inventory')
    if np.any(train & held):
        raise ValueError('Training and held native IDs overlap')
    if id_hash(native['ids'][train]) != row['train_ids_sha256'] or id_hash(native['ids'][held]) != row['held_ids_sha256']:
        raise ValueError('Saved endpoint train/held hashes disagree')
    dd = numerical.family.candidate_context(d, z, row['SD_scale'], family=int(plan['family']))
    dd, zz, receipt = numerical.adapter.prepare_context(dd, z, train)
    if receipt != row['preprocessing']:
        raise ValueError('Saved preprocessing receipt did not replay')
    p, built = e.build(dd, zz, row['arm'], np.asarray(row['reference']))
    if list(p.supported) != list(base.supported):
        raise ValueError('Frozen physical-mode support changed')
    x = np.asarray(row['x_km'])
    c = p.calculate(x)
    actual_objective = float(objective(p, built, x))
    saved_objective = float(row['history'][-1]['objective'])
    if abs(actual_objective - saved_objective) > 1e-5:
        raise ValueError(f'Saved training objective failed replay: {actual_objective - saved_objective}')
    u, a = c['features'], c['coefficient']
    blocks = column_blocks(p, u.shape[1])
    covariance, nuisance, block_variance, cross = conditional_components(
        u, c['coefficient_prior_precision'], c['noise_precision'][p.noise_groups], p.point_noise, train, blocks)
    mean = p.q * c['intercept'] + u @ a
    components = {name: u[:, columns] @ a[columns] for name, columns in blocks.items()}
    orbit = p.q * c['intercept'] + components['phase'] + components['physical_orbit']
    derivative = []
    for axis in range(2):
        delta = np.eye(2)[axis] * .02
        plus, minus = p.calculate(x + delta), p.calculate(x - delta)
        derivative.append(((p.q * plus['intercept'] + plus['features'] @ plus['coefficient'])
                           - (p.q * minus['intercept'] + minus['features'] @ minus['coefficient'])) / .04)
    position = np.column_stack(derivative) @ np.linalg.cholesky(np.asarray(row['position_covariance_km2']))
    sigma, noise_receipt = numerical.predictive_noise(c['noise_precision'], p.noise_groups, train)
    replay_score = numerical.gaussian((p.values - mean)[held], sigma[held],
                                      np.column_stack((nuisance[held], position[held])))
    saved_score = row['scores']['all']['unbounded']['negative_twice_log_density']
    if abs(replay_score['negative_twice_log_density'] - saved_score) > 1e-5:
        raise ValueError('Reconstructed conditional covariance does not replay saved held score')
    observed = np.concatenate([p.scan.tracks[i]['values'] for i in p.members])
    aliases = np.concatenate([np.full(sl.stop - sl.start, alias) for sl, alias in zip(p.slices, p.alias, strict=True)])
    fragments = np.concatenate([np.full(sl.stop - sl.start, str(r['component'])) for sl, r in zip(p.slices, p.rows, strict=True)])
    if not np.allclose(p.values, observed + aliases * PERIOD, rtol=0, atol=1e-9):
        raise ValueError('Native/lifted alias identity failed')
    arrays = dict(
        observation_id=native['ids'][held], time_s=native['times'][held], receiver=native['receiver'][held],
        channel=native['channel'][held], family=native['family'][held], fragment=fragments[held],
        alias_integer=aliases[held], observed_native_hz=observed[held], observed_lifted_hz=p.values[held],
        orbital_at_reference_hz=(p.q * c['frequency'])[held], orbital_conditional_hz=orbit[held],
        prediction_lifted_hz=mean[held], prediction_native_branch_hz=(mean - aliases * PERIOD)[held],
        residual_hz=(p.values - mean)[held], noise_variance_hz2=sigma[held] ** 2,
        nuisance_variance_hz2=np.sum(nuisance[held] ** 2, axis=1),
        position_variance_hz2=np.sum(position[held] ** 2, axis=1),
        nuisance_between_block_variance_hz2=cross[held],
        nuisance_covariance_factor_hz=nuisance[held], position_covariance_factor_hz=position[held],
        coefficient_covariance=covariance,
        coefficient_prior_precision=c['coefficient_prior_precision'], coefficient_mean=a)
    for name in blocks:
        arrays[name + '_mean_hz'] = components[name][held]
        arrays[name + '_variance_hz2'] = block_variance[name][held]
    arrays['predictive_variance_hz2'] = arrays['noise_variance_hz2'] + arrays['nuisance_variance_hz2'] + arrays['position_variance_hz2']
    metadata = dict(
        status='exported', case=plan['case'], split=split['name'], arm=row['arm'], SD_scale=row['SD_scale'],
        target_family=int(plan['family']), saved_numerical_fit_qualified=row['numerical_fit_qualified'],
        saved_unqualified_reasons=row.get('unqualified_reasons', []),
        saved_training_objective=saved_objective, replay_training_objective=actual_objective,
        objective_delta=actual_objective - saved_objective, objective_tolerance=1e-5,
        held_unbounded_score_delta=replay_score['negative_twice_log_density'] - saved_score,
        x_km=x, reference=p.reference, train_ids_sha256=row['train_ids_sha256'],
        held_ids_sha256=row['held_ids_sha256'], held_points=int(held.sum()),
        preprocessing=receipt, noise=noise_receipt,
        fragment_graph=[dict(component=str(r['component']), receiver=int(p.scan.tracks[i]['receiver']),
                             channel=int(p.scan.tracks[i]['channel']), norad=int(r['candidate_norad']),
                             times_s=np.asarray(p.scan.tracks[i]['times']), pieces=p.scan.tracks[i].get('pieces', []))
                        for r, i in zip(p.rows, p.members, strict=True) if r['candidate_norad'] == int(plan['family'])],
        covariance='diag(noise_variance_hz2) + nuisance_factor@nuisance_factor.T + position_factor@position_factor.T',
        covariance_scope='Unbounded local Gaussian approximation conditional on training endpoint; figure bands are pointwise standard deviations, not calibrated intervals. Between-block covariance is included; block variances alone do not add.',
        no_refit=True, optimizer_calls=0, held_nuisance_updates=0, GPS_used=False)
    return arrays, metadata


def save_endpoint(label, arrays, metadata):
    folder = ROOT / 'arrays'
    folder.mkdir(exist_ok=True)
    np.savez_compressed(folder / (label + '.npz'), **arrays)
    columns = [name for name, values in arrays.items() if values.ndim == 1 and len(values) == len(arrays['observation_id'])
               and name not in ('coefficient_mean', 'coefficient_prior_precision')]
    with (folder / (label + '.csv')).open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(zip(*(arrays[name] for name in columns), strict=True))
    metadata['npz_sha256'] = sha(folder / (label + '.npz'))
    metadata['csv_sha256'] = sha(folder / (label + '.csv'))
    write(folder / (label + '.json'), metadata)


def deadline(*_):
    raise TimeoutError('NO-REFIT export deadline')


def case_worker(spec):
    began = time.monotonic()
    remaining = max(1, int(spec['deadline'] - began))
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(remaining)
    case, output = spec['plan']['case'], []
    try:
        numerical = module('native_replay_engine', REPORT / 'predictive/engine.py')
        from algo07_science import engine as e
        path = Path(spec['plan']['input_path'])
        if sha(path) != spec['plan']['input_sha256']:
            raise ValueError('Frozen source input hash changed')
        e.configure(path.parent.parent, ROOT / 'replay_engine')
        e.ROOTS[case[:4]] = path.parent.parent
        d, z, _ = e.load_case(case)
        for split_name in spec['splits']:
            split = next(part for part in spec['plan']['partitions'] if part['name'] == split_name)
            rendered = []
            for scale in (1., 4.):
                label = f'{case}_{split_name}_fitted_c_SD{scale:g}'
                source = REPORT / 'predictive/cells' / (label + '.json')
                row = read(source) if source.exists() else dict(status='missing_saved_endpoint')
                sealed_row = next((saved for saved in spec['sealed_rows'] if saved.get('split') == split_name
                                   and saved.get('arm') == 'fitted_c' and saved.get('SD_scale') == scale), None)
                if source.exists() and row != sealed_row:
                    raise ValueError('Cell receipt differs from the sealed result row')
                if not split['eligible'] or row.get('status') != 'complete':
                    record = dict(case=case, split=split_name, SD_scale=scale, status='not_exportable',
                                  saved_status=row.get('status'), support_eligible=split['eligible'], no_refit=True)
                else:
                    try:
                        arrays, record = extract(d, z, spec['plan'], split, row, numerical)
                        record['saved_cell_sha256'] = sha(source)
                        record['result_seal_sha256'] = spec['result_sha256']
                        save_endpoint(label, arrays, record)
                        rendered.append((scale, arrays, record))
                    except Exception as exc:
                        record = dict(case=case, split=split_name, SD_scale=scale, status='export_failed',
                                      error=repr(exc), traceback=traceback.format_exc(), no_refit=True)
                output.append(record)
            renderer = module('native_renderer', ROOT / 'render.py')
            renderer.render(case, split_name, int(spec['plan']['family']), rendered, ROOT / 'figures')
    except Exception as exc:
        output.append(dict(case=case, status='case_export_failed', error=repr(exc), traceback=traceback.format_exc(), no_refit=True))
    finally:
        signal.alarm(0)
    write(ROOT / 'receipts' / (case + '.json'), dict(case=case, seconds=time.monotonic() - began, rows=output))
    return output


def run():
    began = time.monotonic()
    results_path, plan_path = REPORT / 'predictive/results.json', REPORT / 'predictive/plan.json'
    results = read(results_path)
    if not results.get('all_workers_joined'):
        raise ValueError('Predictive workers must be joined before no-refit export')
    result_sha = sha(results_path)
    plan = read(plan_path)
    if sha(plan_path) != results['plan_sha256'] or sha(REPORT / 'protocol.json') != results['protocol_sha256']:
        raise ValueError('Result protocol/plan bindings changed')
    for path, digest in read(REPORT / 'protocol.json')['source_sha256'].items():
        if sha(path) != digest:
            raise ValueError('Frozen inference source changed: ' + path)
    pool = multiprocessing.get_context('fork').Pool(4)
    specs = [dict(plan=next(row for row in plan['cases'] if row['case'] == case),
                  splits=['time_f0'] + (['family_to_rx1', 'family_to_rx2'] if case == 'DS26-0309' else []),
                  sealed_rows=[row for row in results['rows'] if row['case'] == case],
                  result_sha256=result_sha, deadline=began + WINDOW_SECONDS) for case in CASES]
    futures = [pool.apply_async(case_worker, (spec,)) for spec in specs]
    capped = False
    try:
        pool.close()
        for future in futures:
            remaining = began + WINDOW_SECONDS - time.monotonic()
            if remaining <= 0:
                capped = True
                break
            try:
                future.get(timeout=remaining)
            except multiprocessing.TimeoutError:
                capped = True
                break
    finally:
        if capped:
            pool.terminate()
        pool.join()
    if sha(results_path) != result_sha:
        raise ValueError('Sealed predictive results changed during export')
    receipts = []
    for case in CASES:
        path = ROOT / 'receipts' / (case + '.json')
        receipts.append(read(path) if path.exists() else dict(case=case, status='export_total_deadline'))
    write(ROOT / 'manifest.json', dict(
        protocol_sha256=sha(ROOT / 'export_protocol.json'), predictive_results_sha256=result_sha,
        predictive_plan_sha256=sha(plan_path), seconds=time.monotonic() - began,
        window_seconds=WINDOW_SECONDS, workers=4, workers_terminated_at_deadline=capped,
        all_workers_joined=True, no_refit=True, GPS_used=False, cases=receipts,
        source_sha256={name: sha(ROOT / name) for name in ['export.py', 'render.py', 'test_export.py']}))


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()
