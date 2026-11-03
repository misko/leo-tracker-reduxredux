"""RF-only replay of exclusions, real-data Gaussian proposals and joint fits."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np

from algo02_scan import pair_passes
from build_dsx01_orbit_modes import build_modes
from calibrate_ds23_excluded_catalogue import OUT, ARMS, context
from ds23_excluded_catalogue import apply_changes, orbit_frequency_modes
from ds23_frequency_events import make_event_problem, attach_event_predictive
from ds23_symmetric_family_code import observed_labels, family_code, symmetric_gain
from fit_ds23_excluded_catalogue import prepare
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_frequency_events import summary
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, read, write, sha
from screen_ds23_excluded_catalogue import block_data, evaluate_candidates, subbank
from leo.analysis.research.phase_linear_geometry import prepare_phase_geometry, phase_linear_frequency
from leo.analysis.research.retained_track_likelihood import PERIOD


def proposal_replay(scan, p, x, original, screen, model, block):
    data = block_data(p, x, original, block['family'], block['receiver'])
    candidate = next(r for r in block['candidates'] if r['candidate_index']==block['family'])
    j = candidate['candidate_index']
    means = np.array([screen['means_s'][j]])
    sigma = phase_widths(scan, [j])[0]*model['multiplier']
    sky, modes = subbank(scan.sky, [j]), build_modes(scan, [j], [j], 'physical')[0]
    best, reference = np.inf, means.copy()
    for anchor in (-1., 0., 1.):
        r = evaluate_candidates(data, sky, modes, np.clip(means+anchor*np.minimum(sigma, 10.), -15, 15), means, sigma, latlon(x))
        if r['visible'][0] and abs(r['phase_s'][0])<=15 and r['cost'][0]<best:
            best, reference = float(r['cost'][0]), r['phase_s'].copy()
    for _ in range(6):
        used_reference = reference.copy()
        r = evaluate_candidates(data, sky, modes, reference, means, sigma, latlon(x))
        reference = np.clip(r['phase_s'], -15, 15)
    if abs(r['cost'][0]-candidate['score'])>1e-4 or abs(r['phase_s'][0]-candidate['phase_s'])>1e-5:
        raise ValueError('original-candidate proposal score does not replay from its own causal mode bank')
    # Independent dense covariance identity, including the real held data and
    # full radio uncertainty. This does not call the batch marginal integrator.
    g = prepare_phase_geometry(sky, data['times'], used_reference, derivative_step_s=.01)
    f, _, derivative = phase_linear_frequency(g, *latlon(x))
    expected = data['q']*(f[0]+derivative[0]*(means[0]-used_reference[0]))
    aliases = []
    w = 1/np.diag(data['covariance'])
    for group in range(int(data['groups'].max())+1):
        use = data['groups']==group
        aliases.append(int(np.rint(np.sum(w[use]*(expected[use]-data['observed'][use]))/w[use].sum()/PERIOD)))
    raw = data['observed']+PERIOD*np.asarray(aliases)[data['groups']]-expected
    phase = data['q']*derivative[0]*sigma[0]
    orbit = orbit_frequency_modes(sky, modes, data['times'], used_reference, latlon(x))[0]*data['q'][:, None]
    u = np.column_stack((phase, orbit))
    covariance = data['covariance']+u@u.T
    root = np.linalg.cholesky((covariance+covariance.T)/2)
    white = np.linalg.solve(root, raw)
    dense = float(white@white+2*np.log(np.diag(root)).sum()+len(raw)*np.log(2*np.pi))
    if abs(dense-candidate['score'])>1e-4:
        raise ValueError('real-data proposal differs from direct dense Gaussian density')
    return dict(family=block['original_norad'], receiver=block['receiver'],
        points=len(raw), batch_replay_difference=float(r['cost'][0]-candidate['score']),
        dense_replay_difference=dense-candidate['score'])


def run(case):
    cache = OUT/'verification_cases'/(case+'.json')
    paths = [OUT/(case+'_calibration.json'), OUT/(case+'_screen.json'), OUT/case/'result.json']
    bindings = {str(p.relative_to(ROOT)):sha(p) for p in paths}
    if cache.exists():
        saved = read(cache)
        if saved['input_sha256']!=bindings or saved['verification_source_sha256']!=sha(Path(__file__)):
            raise ValueError('cached verification binding changed')
        return saved
    scan, node, original, base, old, signed, model, powers, means, entries, calibration = context(case)
    result, screen = read(paths[2]), read(paths[1])
    held = [t['candidate_index'] for t in calibration['targets']]
    labels = np.asarray(base.labels)[base.flat_labels]
    train = np.asarray(calibration['mask'], bool)
    np.testing.assert_array_equal(train, original & ~np.isin(labels, held))
    if any(e['candidate_index'] in held for e in calibration['predictive_entries']):
        raise ValueError('held family leaked into predictive training')
    if not calibration['qualified']:
        if result['accepted'] or result['policy_arms']!=signed['policy_arms']:
            raise ValueError('unqualified calibration did not keep exact incumbent')
        receipt = dict(case=case, accepted=False, no_attempt=True)
    else:
        replays, proposals = [], []
        for arm in ARMS:
            r = calibration['arms'][arm]
            p = make_event_problem(scan, node, train, arm, np.asarray(r['phase_reference']), powers, means, model, [])
            attach_event_predictive(p, calibration['predictive_entries'], powers)
            p.powers = powers
            x = np.asarray(r['endpoint_east_north_km'])
            d = p.calculate(x)
            if abs(d['negative_twice_elbo']-r['negative_twice_elbo'])>1e-3:
                raise ValueError('calibration RF endpoint no longer reproduces')
            curved = p.curved_calculate(x) if calibration['predictive_entries'] else d
            difference = float(np.max(abs(curved['coefficient']-d['coefficient'])))
            if difference>1e-10:
                raise ValueError('linear points changed calibration coefficients')
            replays.append(dict(arm=arm, RF_difference=d['negative_twice_elbo']-r['negative_twice_elbo'],
                linear_calibration_difference=difference))
            if arm=='c0':
                for block in screen['blocks']:
                    proposals.append(proposal_replay(scan, p, x, original, screen, model, block))
        incumbent_code = family_code(len(scan.norads), observed_labels(node, entries, original, base.slices))
        valid, trial_replays = [], []
        for path in sorted((OUT/case).glob('trial_*.json')):
            trial = read(path)
            changed, predictive = apply_changes(node, entries, trial['choices'])
            if changed['seed']['rows']!=trial['node']['seed']['rows'] or changed['aliases']!=trial['node']['aliases'] or predictive!=trial['predictive_entries']:
                raise ValueError('joint changes were not simultaneous and complete')
            if [e['observation_ids'] for e in predictive]!=[e['observation_ids'] for e in entries]:
                raise ValueError('predictive observations changed during nomination')
            active_labels = sorted({r['candidate_index'] for r in changed['seed']['rows']})
            code = family_code(len(scan.norads), observed_labels(changed, predictive, original, base.slices))
            if abs(code-trial['code'])>1e-10:
                raise ValueError('symmetric family code changed')
            fresh = {}
            for arm in ARMS:
                r = trial['arms'][arm]
                p = make_event_problem(scan, changed, original, arm, np.asarray(r['phase_reference']),
                    powers, np.asarray(screen['means_s'])[active_labels], model, [])
                attach_event_predictive(p, predictive, powers)
                x = np.asarray(r['endpoint_east_north_km'])
                d = summary(p, x, predictive)
                difference = d['negative_twice_elbo']-r['negative_twice_elbo']
                if abs(difference)>1e-3:
                    raise ValueError('full original-data trial does not replay')
                if [g['compatible'] for g in d['gates']['tracks']+d['linear_gates']] != [g['compatible'] for g in r['gates']['tracks']+r['linear_gates']]:
                    raise ValueError('original trial gates changed')
                gain = symmetric_gain(signed['policy_arms'][arm]['negative_twice_elbo'], incumbent_code, d['negative_twice_elbo'], code)
                if abs(gain-trial['coded_gains'][arm])>1e-3:
                    raise ValueError('coded RF score changed')
                fresh[arm] = dict(d, final_phase_change_s=r['final_phase_change_s'])
            if pair_passes(fresh, include_linear=True)!=trial['paired_valid']:
                raise ValueError('paired trial qualification changed')
            if trial['paired_valid'] and all(g>2*np.log(7) for g in trial['coded_gains'].values()):
                valid.append(trial)
            trial_replays.append(dict(path=str(path.relative_to(ROOT)), sha256=sha(path), paired_valid=trial['paired_valid']))
        chosen = min(valid, key=lambda t:t['arms']['c0']['negative_twice_elbo']+t['code']) if valid else None
        if bool(chosen)!=result['accepted'] or result['policy_arms']!=(chosen['arms'] if chosen else signed['policy_arms']):
            raise ValueError('selection or exact incumbent fallback changed')
        if chosen:
            selected_labels = sorted({r['candidate_index'] for r in chosen['node']['seed']['rows']})
            for arm in ARMS:
                r = chosen['arms'][arm]
                actual = np.asarray(r['state']['phases'])[selected_labels]
                reference = np.asarray(r['phase_reference'])
                if np.max(abs(actual-reference))>.01 or np.max(abs(actual))>15:
                    raise ValueError('accepted trial phase is not actually converged inside interpolation bounds')
        receipt = dict(case=case, accepted=result['accepted'], calibration_replays=replays,
            real_data_proposal_replays=proposals, trial_replays=trial_replays,
            no_held_family_in_calibration=True, every_original_point_restored=True)
    receipt.update(input_sha256=bindings, verification_source_sha256=sha(Path(__file__)), no_GPS_used=True)
    cache.parent.mkdir(exist_ok=True)
    write(cache, receipt)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=('pilot', 'cohort'), required=True)
    args = parser.parse_args()
    protocol = prepare()
    cases = protocol['pilot_cases'] if args.stage=='pilot' else protocol['development_cases']+protocol['confirmation_cases']
    receipts, errors = [], []
    with ProcessPoolExecutor(max_workers=min(16, len(cases))) as pool:
        futures = {pool.submit(run, c):c for c in cases}
        for f in as_completed(futures):
            try:
                receipts.append(f.result())
            except Exception as exc:
                errors.append(dict(case=futures[f], error=repr(exc)))
            write(OUT/(args.stage+'_verification_progress.json'), dict(completed=len(receipts)+len(errors), total=len(cases)))
    write(OUT/(args.stage+'_verification.json'), dict(all_terminal=True, receipts=receipts, errors=errors,
        qualified=not errors and len(receipts)==len(cases), no_GPS_used=True))
    print('Verified', len(receipts), 'errors', errors, flush=True)
