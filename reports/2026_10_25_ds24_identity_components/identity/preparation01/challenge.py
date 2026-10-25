"""Bounded causal identity challenge; no position fit or geographic input."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import itertools
import json
from pathlib import Path
import signal
import sys
import time
import traceback

import numpy as np
from scipy.integrate import quad
from scipy.linalg import solve_triangular
from scipy.special import logsumexp

HERE = Path(__file__).resolve().parent
OLD = Path('/srv/bulk/leo/research/ds24-next-directions-review-r01/identity')
sys.path.insert(0, str(OLD))
import review as m
import owner02 as owners
from ds23_family_cavity import coarse_phase_scores
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.retained_track_likelihood import PERIOD
from prototype_dsx01_continuous_position import latlon

ARMS = ('c0', 'fitted_c')
ALIASES = np.arange(-4, 5)
CAP = 600.


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(name, value):
    m.r.write_new(HERE / name, value)


def alarm(seconds):
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('600s cumulative scientific cap')))
    signal.setitimer(signal.ITIMER_REAL, max(.001, seconds))


def records(item, d):
    target = item['target']
    raw = [dict(component=target['component'], observation_ids=target['observation_ids'])]
    if item['case'] == 'DS24-0013':
        raw += item['other_same_family_raw_sources']
    ids = [oid for owner in raw for oid in owner['observation_ids']]
    if len(ids) != len(set(ids)):
        raise ValueError('native owner overlap: no trimming authorized')
    for arm in ARMS:
        if set(ids) & set(d['parent_membership'][arm]['accepted_observation_ids']):
            raise ValueError('native owner overlaps complete original parent accepted IDs')
    result = []
    for owner in raw:
        i = next(i for i, track in enumerate(d['scan'].tracks) if track['key'] == owner['component'])
        if d['scan'].tracks[i]['observation_ids'] != owner['observation_ids']:
            raise ValueError('complete original source IDs/order differ')
        result.append(dict(component=owner['component'], track_index=i,
                           candidate_index=target['candidate_index'], alias=0,
                           observation_ids=owner['observation_ids'], points=len(owner['observation_ids'])))
    return result


def cavity(d, pool, arm):
    keep = d['keep'].copy()
    for row, sl in zip(d['base'].rows, d['base'].slices, strict=True):
        if row['candidate_index'] in pool:
            keep[sl] = False
    entries = [e for e in d['entries'] if e['candidate_index'] not in pool]
    changed = dict(d, keep=keep, entries=entries,
                   original_protected=set(d['original_protected']) - set(pool))
    reference = np.asarray(d['arms'][arm]['phase_reference']).copy()
    history = []
    for _ in range(5):
        p = m.r.build(changed, arm, reference)
        phase = p.state(np.asarray(d['arms'][arm]['endpoint_east_north_km']))['phases'][p.labels]
        history.append(float(np.max(abs(phase - reference))))
        reference = np.clip(phase, -15, 15)
    initial_phase_qualified = bool(history[-1] <= .01 and np.max(abs(phase)) <= 15.000001)
    changed['arms'] = dict(d['arms'])
    changed['arms'][arm] = dict(d['arms'][arm], phase_reference=reference)
    p = m.r.build(changed, arm, reference)
    x = np.asarray(d['arms'][arm]['endpoint_east_north_km'])
    state = p.state(x)
    calids = [oid for i, sl in zip(p.members, p.slices, strict=True)
              for oid, use in zip(d['scan'].tracks[i]['observation_ids'], keep[sl], strict=True) if use]
    predids = [oid for e in entries for oid in e['observation_ids']]
    removed = [oid for i, sl in zip(p.members, p.slices, strict=True)
               for oid, before, after in zip(d['scan'].tracks[i]['observation_ids'], d['keep'][sl], keep[sl], strict=True)
               if before and not after]
    if any(keep[sl].any() for row, sl in zip(p.rows, p.slices, strict=True) if row['candidate_index'] in pool):
        raise ValueError('shortlisted family remains in calibration')
    if any(e['candidate_index'] in pool for e in entries):
        raise ValueError('shortlisted family remains in predictive conditioning')
    summary = m.r.summary(p, x, entries)
    final_change = float(np.max(abs(state['phases'][p.labels] - reference)))
    parent_gates_pass = all(row['compatible'] for row in summary['gates']['tracks']) and all(
        row['compatible'] for row in summary['linear_gates'])
    phase_qualified = bool(initial_phase_qualified and final_change <= .01 and
                           np.max(abs(state['phases'][p.labels])) <= 15.000001)
    return changed, dict(phase_reference=reference, phase_changes_s=history, final_phase_change_s=final_change,
                         phase_qualified=phase_qualified,
                         maximum_unclipped_parent_phase_s=float(np.max(abs(state['phases'][p.labels]))),
                         calibration_ids=calids, predictive_ids=predids, removed_curved_ids=removed,
                         removed_predictive_ids=[oid for e in d['entries'] if e['candidate_index'] in pool
                                                 for oid in e['observation_ids']],
                         calibration_ids_sha256=hashlib.sha256(json.dumps(calids).encode()).hexdigest(),
                         predictive_ids_sha256=hashlib.sha256(json.dumps(predids).encode()).hexdigest(),
                         diagnostic_gates=summary['gates'], diagnostic_predictive_gates=summary['linear_gates'],
                         original_remaining_gates_pass=parent_gates_pass,
                         fixed_score_status='parent_gates_passed' if parent_gates_pass else 'parent_gate_failed_diagnostic_only')


def candidate(d, norad):
    return m.candidate_context(d, norad)


def alias_vectors(groups, support):
    count = int(np.max(groups)) + 1
    hypotheses = np.asarray(list(itertools.product(support, repeat=count)), int)
    return hypotheses, PERIOD * hypotheses[:, groups]


def conditional_costs(raw, covariance, shape, shifts):
    """All phase/alias costs via rank3 Woodbury; no density constants omitted."""
    root = np.linalg.cholesky(covariance)
    w = solve_triangular(root, np.asarray(raw).T, lower=True).T
    s = solve_triangular(root, shifts.T, lower=True).T
    b = np.asarray(shape)
    wb = solve_triangular(root, b.transpose(1, 0, 2).reshape(b.shape[1], -1), lower=True)
    wb = wb.reshape(b.shape[1], len(b), b.shape[2]).transpose(1, 0, 2)
    gram = np.eye(b.shape[2])[None] + np.einsum('nki,nkj->nij', wb, wb)
    base = np.sum(w * w, axis=1)
    quadratic = base[:, None] + 2 * w @ s.T + np.sum(s * s, axis=1)[None]
    rhs0 = np.einsum('nki,nk->ni', wb, w)
    for k in range(len(shifts)):
        rhs = rhs0 + np.einsum('nki,k->ni', wb, s[k])
        solution = np.linalg.solve(gram, rhs[..., None])[..., 0]
        quadratic[:, k] -= np.sum(rhs * solution, axis=1)
    logdet = np.linalg.slogdet(gram)[1] + 2 * np.log(np.diag(root)).sum()
    return quadratic + logdet[:, None] + covariance.shape[0] * np.log(2 * np.pi)


def node_terms(d, comp, phases, indices, support=ALIASES):
    geom = m.q.phase_geometry(d, comp['x'], np.asarray(phases))
    ix = np.asarray(indices, int)
    scale = comp['q'][ix]
    frequency = geom['frequency_hz'][:, ix] * scale
    shape = geom['shape_columns_hz'][:, ix] * scale[None, :, None]
    groups = comp['groups'][ix]
    _, remap = np.unique(groups, return_inverse=True)
    hypotheses, shifts = alias_vectors(remap, support)
    costs = conditional_costs(comp['raw'][ix][None] - frequency,
                              comp['covariance'][np.ix_(ix, ix)], shape, shifts)
    return -.5 * costs, hypotheses, float(geom['elevation_deg'][:, ix].min())


def score(d, comp, indices, count, support=ALIASES):
    nodes, weights = m.q.phase_nodes(d, count)
    terms, hypotheses, elevation = node_terms(d, comp, nodes, indices, support)
    endpoint = m.q.phase_geometry(d, comp['x'], np.asarray(m.q.DOMAIN))['elevation_deg'][:, indices].min()
    if min(elevation, endpoint) < 0:
        raise ValueError('candidate phase-domain visibility failure')
    per_alias = logsumexp(weights[:, None] + terms, axis=0)
    mixture = logsumexp(per_alias) - np.log(len(hypotheses))
    posterior = np.exp(per_alias - logsumexp(per_alias))
    return dict(objective=float(-2 * mixture), aliases=hypotheses, alias_log_density=per_alias,
                alias_posterior=posterior, alias_image_sum_objective=float(-2 * logsumexp(per_alias)),
                minimum_elevation_deg=float(min(elevation, endpoint)),
                quadrature_prior_mass=float(np.exp(logsumexp(weights))),
                phase_prior={k: v for k, v in m.q.prior(d).items() if k != 'distribution'})


def adaptive(d, comp, indices):
    # Same R2 physical phase integrand; fixed9/81 alias sum inside each node.
    phases = np.linspace(-15, 15, 641)
    terms, aliases, _ = node_terms(d, comp, phases, indices)
    law = m.q.prior(d)
    logprior = law['distribution'].logpdf(phases) - np.log(law['interval_probability'])
    grid = logsumexp(terms, axis=1) - np.log(len(aliases)) + logprior
    peaks = np.flatnonzero((grid[1:-1] >= grid[:-2]) & (grid[1:-1] >= grid[2:])) + 1
    points = sorted(set(float(phases[k]) for peak in peaks for k in
                        range(max(1, peak - 2), min(len(phases) - 1, peak + 3))))
    shift = float(grid.max())
    def density(phi):
        term = node_terms(d, comp, np.asarray([phi]), indices)[0][0]
        loglike = logsumexp(term) - np.log(len(aliases))
        return float(np.exp(loglike + law['distribution'].logpdf(phi)
                            - np.log(law['interval_probability']) - shift))
    value, error = quad(density, -15, 15, points=points, epsabs=1e-10, epsrel=1e-10, limit=1000)[:2]
    if value <= 0 or error / value > 1e-6:
        raise ValueError('independent adaptive phase integration failed')
    return dict(objective=float(-2 * (shift + np.log(value))), relative_integral_error=float(error / value))


def null_score(comp, indices, support=ALIASES):
    ix = np.asarray(indices, int)
    groups = comp['groups'][ix]
    unique, group = np.unique(groups, return_inverse=True)
    columns = np.zeros((len(ix), 5 * len(unique)))
    times = np.asarray(comp['d']['target_track']['times'])[ix]
    for g in range(len(unique)):
        use = group == g
        t = times[use]
        z = 2 * (t - t.min()) / np.ptp(t) - 1
        columns[use, 5*g:5*g+5] = np.polynomial.legendre.legvander(z, 4) * PERIOD / np.sqrt(6)
    covariance = comp['covariance'][np.ix_(ix, ix)] + columns @ columns.T
    root = np.linalg.cholesky(covariance)
    hypotheses, shifts = alias_vectors(group, support)
    white = solve_triangular(root, (comp['raw'][ix][None] + shifts).T, lower=True).T
    cost = np.sum(white * white, axis=1) + 2 * np.log(np.diag(root)).sum() + len(ix) * np.log(2*np.pi)
    loglike = logsumexp(-cost / 2)
    return dict(objective=float(-2 * (loglike - np.log(len(hypotheses)))),
                alias_image_sum_objective=float(-2*loglike), aliases=hypotheses, alias_log_density=-cost/2)


def alias_diagnostics(wide):
    """No new propagation: extract common9 support and shifted supports from11."""
    hypotheses = np.asarray(wide['aliases'])
    logdensity = np.asarray(wide['alias_log_density'])
    main = np.all(abs(hypotheses) <= 4, axis=1)
    logmain = float(logsumexp(logdensity[main]))
    count = int(main.sum())
    score0 = -2 * (logmain - np.log(count))
    shifted = []
    for owner in range(hypotheses.shape[1]):
        for change in (-1, 1):
            translated = hypotheses.copy(); translated[:, owner] -= change
            use = np.all(abs(translated) <= 4, axis=1)
            shifted.append(float(-2 * (logsumexp(logdensity[use]) - np.log(count)) - score0))
    tail = abs(-2 * logsumexp(logdensity) + 2 * logmain)
    return dict(objective=float(score0), image_sum_range_error=float(tail),
                unchanged_support_period_shift_changes=shifted,
                alias_stable=bool(max([tail]+list(map(abs, shifted))) <= 1e-3),
                allowed_aliases=hypotheses[main],
                allowed_alias_posterior=np.exp(logdensity[main] - logmain))


def freeze():
    inv = read(OLD / 'inventory.json')
    paths = [Path(__file__), HERE/'PROTOCOL.md', HERE/'test_challenge.py', OLD/'review.py', OLD/'owner02.py',
             OLD/'inventory.json', OLD/'seal.json', OLD/'owner02_seal.json',
             m.t.R2/'scientific/quadrature02.py', m.t.R2/'scientific/adapter.py',
             m.r.REPO/'tools/ds23_family_cavity.py',
             m.r.REPO/'tools/ds23_conditioned_relative_nomination.py',
             m.r.REPO/'tools/ds23_new_family_prediction.py']
    inputs = dict(inv['input_source_sha256'])
    inputs.update({str(path):sha(path) for path in paths})
    protocol = dict(cases=[row['case'] for row in inv['rows']], source_hashes=inputs,
                    aliases=ALIASES, alias_prior='uniform per complete source; proper finite real-vector mixture',
                    maximum_candidates=8, reserve={'DS24-0012':66259},
                    discovery='target owner only at saved c0 baseline; no held owner enters shortlist',
                    phase_nodes=1281, reference_nodes=2561, score_tolerance=1e-3,
                    maximum_candidate_contexts=112, maximum_scientific_seconds=CAP,
                    workers=2, BLAS_threads=1, position_fits=0, GPS_used=False,
                    operational_acceptance_rule=None, identity_qualified=False)
    write('protocol.json', protocol)
    print(sha(HERE/'protocol.json'), flush=True)


def verify():
    protocol = read(HERE/'protocol.json')
    for path, expected in protocol['source_hashes'].items():
        if sha(path) != expected:
            raise ValueError('frozen input/source changed: ' + path)
    return protocol


def screen():
    verify()
    start = time.monotonic(); alarm(CAP)
    rows = []
    try:
        for item in read(OLD/'inventory.json')['rows']:
            began = time.monotonic()
            try:
                d = m.t.load_target(item['target']); entries = records(item, d)
                x = np.asarray(d['arms']['c0']['endpoint_east_north_km'])
                comp = owners.components(d, 'c0', x, entries[:1])
                times = np.asarray(d['target_track']['times'])
                f, elevation = phase_frequency_grid(d['scan'].sky, times, *latlon(x), phase_seconds=d['all_means'])
                plus = phase_frequency_grid(d['scan'].sky, times, *latlon(x), phase_seconds=d['all_means']+.01)[0]
                minus = phase_frequency_grid(d['scan'].sky, times, *latlon(x), phase_seconds=d['all_means']-.01)[0]
                scale = comp['q'][None]
                coarse = coarse_phase_scores(comp['raw'], np.zeros(len(times)), f*scale,
                                             (plus-minus)/.02*scale, d['widths'], comp['covariance'], np.zeros(len(times), int))
                scores = np.where(elevation.min(axis=1) >= 0, coarse['score'], np.inf)
                nominee = item['target']['candidate_norad']
                ranked = sorted((int(d['scan'].norads[j]), j, float(scores[j]))
                                for j in range(len(scores)) if np.isfinite(scores[j]))
                ranked.sort(key=lambda row:(row[2], row[0]))
                pool = [nominee]
                if item['case'] == 'DS24-0012':
                    pool.append(66259)
                for norad, _, _ in ranked:
                    if norad not in pool and len(pool) < 8:
                        pool.append(norad)
                row = dict(case=item['case'], status='complete', nominee=nominee, candidate_norads=pool,
                           candidate_indices=[int(np.flatnonzero(d['scan'].norads == n)[0]) for n in pool],
                           catalogue_count=len(scores), catalogue_norads=d['scan'].norads,
                           coarse_scores=[float(v) if np.isfinite(v) else None for v in scores], coarse_aliases=coarse['aliases'],
                           ranked_visible_norads=[r[0] for r in ranked], entries=entries,
                           discovery_observation_ids=entries[0]['observation_ids'],
                           held_owner_IDs_exposed_to_nomination=False, position_fits=0, GPS_used=False,
                           cutoff_utc_ns=d['scan'].receipt['cutoff_utc_ns'],
                           causal_elements_verified=len(d['scan'].elements))
            except Exception as exc:
                row = dict(case=item['case'], status='failed', error=repr(exc), traceback=traceback.format_exc())
            row['seconds'] = time.monotonic() - began
            rows.append(row); write(item['case']+'_screen.json', row)
            print(item['case'], 'screen', row['status'], row.get('candidate_norads'), row['seconds'], flush=True)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        write('screen_receipt.json', dict(rows=[dict(case=r['case'],status=r['status']) for r in rows],
                                         seconds=time.monotonic()-start, protocol_sha256=sha(HERE/'protocol.json'),
                                         position_fits=0, GPS_used=False))


def exact_job(case, arm, deadline):
    began = time.monotonic()
    checkpoint = []
    try:
        if deadline <= began:
            raise TimeoutError('global scientific budget already exhausted')
        alarm(deadline-began)
        item = next(row for row in read(OLD/'inventory.json')['rows'] if row['case'] == case)
        screen = read(HERE/(case+'_screen.json'))
        if screen['status'] != 'complete':
            raise ValueError('screen not complete; no backfill')
        d = m.t.load_target(item['target']); entries = records(item, d)
        dd, cavity_info = cavity(d, screen['candidate_indices'], arm)
        write(case+'_'+arm+'_cavity.json', cavity_info)
        if not cavity_info['phase_qualified']:
            raise ValueError('cavity phase convergence or absolute phase qualification failed; no scores')
        x = np.asarray(dd['arms'][arm]['endpoint_east_north_km'])
        panels = [('single', entries[:1])]
        if case == 'DS24-0013':
            panels += [('held_'+str(k), [entries[0], e]) for k,e in enumerate(entries[1:], 1)]
        results = []
        for label, panel in panels:
            comp = owners.components(dd, arm, x, panel)
            indices = np.arange(len(comp['raw']))
            discovery = np.arange(panel[0]['points'])
            nullwide = null_score(comp, indices, np.arange(-5,6))
            null = alias_diagnostics(nullwide)
            null['conditional_objective'] = (null['objective'] - null_score(comp, discovery)['objective']
                                               if len(panel) == 2 else None)
            candidates = []
            for norad in screen['candidate_norads']:
                row = dict(norad=norad, status='failed', identity_qualified=False)
                try:
                    cd = candidate(comp['d'], norad)
                    wide = score(cd, comp, indices, 1281, np.arange(-5,6))
                    fixed = alias_diagnostics(wide)
                    dense = score(cd, comp, indices, 2561)
                    error = abs(fixed['objective'] - dense['objective'])
                    row.update(status='complete', **fixed, reference_objective=dense['objective'],
                               score_error=error, numerically_qualified=bool(error <= 1e-3),
                               phase_prior=wide['phase_prior'], minimum_elevation_deg=wide['minimum_elevation_deg'],
                               quadrature_prior_mass=wide['quadrature_prior_mass'])
                    if len(panel) == 2:
                        disc = score(cd, comp, discovery, 1281)
                        discdense = score(cd, comp, discovery, 2561)
                        row['discovery_objective'] = disc['objective']
                        row['conditional_objective'] = row['objective'] - disc['objective']
                        row['reference_conditional_objective'] = dense['objective'] - discdense['objective']
                        row['conditional_score_error'] = abs(row['conditional_objective'] - row['reference_conditional_objective'])
                        row['numerically_qualified'] &= row['conditional_score_error'] <= 1e-3
                    row['gain_vs_unresolved_curve'] = null['objective'] - row['objective']
                    if len(panel) == 2:
                        row['held_gain_vs_unresolved_curve'] = null['conditional_objective'] - row['conditional_objective']
                except Exception as exc:
                    row.update(status='blocked', reason=repr(exc), traceback=traceback.format_exc())
                candidates.append(row)
                checkpoint.append(dict(panel=label, candidate=row))
                write(f'{case}_{arm}_{label}_{norad}_checkpoint.json', row)
                print(case, arm, label, norad, row['status'], row.get('objective'), row.get('score_error'), flush=True)
            usable = [row for row in candidates if row['status']=='complete' and row['numerically_qualified']]
            sortkey = 'conditional_objective' if len(panel)==2 else 'objective'
            usable.sort(key=lambda row:(row[sortkey], row['norad']))
            # Fixed reference budget: top2 single scores, top1 held challenge.
            for row in usable[:(2 if len(panel)==1 else 1)]:
                try:
                    cd = candidate(comp['d'], row['norad'])
                    reference = adaptive(cd, comp, indices)
                    row['adaptive_reference'] = reference
                    error = abs(row['objective']-reference['objective'])
                    if len(panel)==2:
                        discref = adaptive(cd, comp, discovery)
                        row['adaptive_discovery_reference'] = discref
                        conditional_ref = reference['objective']-discref['objective']
                        error = max(error, abs(row['conditional_objective']-conditional_ref))
                    row['adaptive_score_error'] = error
                    row['numerically_qualified'] &= error <= 1e-3
                except Exception as exc:
                    row['adaptive_failure'] = repr(exc); row['numerically_qualified'] = False
            results.append(dict(panel=label, entries=panel, null=null, candidates=candidates,
                                shared_parent_fingerprint=hashlib.sha256(
                                    comp['parent_coefficients'].tobytes()+comp['parent_noise'].tobytes()).hexdigest(),
                                candidate_calibration_reused=False,
                                source_exposed=len(panel)==1, held_owner_used_for_nomination=False))
        result = dict(case=case, arm=arm, status='complete', cavity=cavity_info, panels=results,
                      position_east_north_km=x, position_fits=0, GPS_used=False, identity_qualified=False)
    except Exception as exc:
        result = dict(case=case, arm=arm, status='failed', error=repr(exc), traceback=traceback.format_exc(),
                      partial_candidate_checkpoints=len(checkpoint), position_fits=0, GPS_used=False)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    result['seconds'] = time.monotonic()-began
    write(case+'_'+arm+'_result.json', result)
    return dict(case=case, arm=arm, status=result['status'], seconds=result['seconds'])


def exact():
    protocol = verify()
    receipt = read(HERE/'screen_receipt.json')
    if receipt['protocol_sha256'] != sha(HERE/'protocol.json'):
        raise ValueError('screen protocol binding changed')
    review = read(HERE/'independent_preflight.json')
    if not review['all_passed'] or review['protocol_sha256'] != sha(HERE/'protocol.json'):
        raise ValueError('independent review missing or does not bind frozen protocol')
    began = time.monotonic(); remaining = CAP-receipt['seconds']; deadline = began+remaining
    rows = []
    with ProcessPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(exact_job, case, arm, deadline) for case in protocol['cases'] for arm in ARMS]
        for job in as_completed(jobs):
            rows.append(job.result())
    output = dict(rows=rows, seconds=time.monotonic()-began,
                  cumulative_scientific_seconds=receipt['seconds']+time.monotonic()-began,
                  prior_screen_seconds=receipt['seconds'], workers=2, BLAS_threads=1,
                  position_fits=0, GPS_used=False, identity_qualified=False)
    write('execution.json', output)
    names = sorted(path.name for path in HERE.glob('*.json') if path.name != 'RF_seal.json')
    write('RF_seal.json', dict(protocol_sha256=sha(HERE/'protocol.json'),
                              files={name:sha(HERE/name) for name in names},
                              cumulative_scientific_seconds=output['cumulative_scientific_seconds'],
                              position_fits=0, GPS_used=False, identity_qualified=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=('freeze','screen','exact'), required=True)
    stage = parser.parse_args().stage
    globals()[stage]()
