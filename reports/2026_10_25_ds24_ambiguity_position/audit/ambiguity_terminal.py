"""Independent saved-array/evidence audit; no orbit propagation or fitting."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import logsumexp
from leo.analysis.research.retained_track_likelihood import PERIOD

ROOT = Path(__file__).resolve().parent.parent
SCI = ROOT / 'ambiguity'
read = lambda path: json.loads(Path(path).read_bytes())
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()


def arrays(path):
    with np.load(path, allow_pickle=False) as data:
        return {name: data[name] for name in data.files}


def bound(row):
    if row.get('empty_support_certified') and row.get('certified_visibility'):
        return -np.inf, -np.inf
    lo, hi = row.get('full_support_lower_log_integral'), row.get('full_support_upper_log_integral')
    if row.get('certified_visibility') and lo is not None and hi is not None and np.isfinite([lo, hi]).all() and lo <= hi:
        return lo, hi
    return None


def mixture(physical, unknown, weight):
    priors = np.r_[np.full(8, weight/8), 1-weight]
    values = np.array([-.5*q['objective'] if q.get('objective') is not None else -np.inf for q in physical] + [-.5*unknown['objective']])
    logz = logsumexp(values + np.log(priors))
    ranges = [bound(q) for q in physical] + [(unknown['lower_logZ'], unknown['upper_logZ']) if unknown['reference_passed'] else None]
    valid = all(q is not None for q in ranges)
    result = dict(objective=float(-2*logz), weights=np.exp(values+np.log(priors)-logz), bounds_available=valid)
    if valid:
        result['lower'] = float(-2*logsumexp([q[1] for q in ranges]+np.log(priors)))
        result['upper'] = float(-2*logsumexp([q[0] for q in ranges]+np.log(priors)))
    return result


def independent_unknown(raw, covariance, times):
    # Least-squares projection of the augmented whitened model, independently
    # reproducing its proper Gaussian determinant and finite-alias normalization.
    root = np.linalg.cholesky(covariance)
    polynomial = np.polynomial.legendre.legvander(2*(times-times.min())/np.ptp(times)-1, 4)*PERIOD/np.sqrt(6)
    design = np.vstack((solve_triangular(root, polynomial, lower=True), np.eye(5)))
    whitened = solve_triangular(root, (raw[None]+np.arange(-4, 5)[:, None]*PERIOD).T, lower=True)
    augmented = np.vstack((whitened, np.zeros((5, 9))))
    coefficients = np.linalg.lstsq(design, augmented, rcond=None)[0]
    residual = augmented - design @ coefficients
    rr = np.linalg.qr(design, mode='reduced')[1]
    normalization = 2*np.log(np.diag(root)).sum()+2*np.log(abs(np.diag(rr))).sum()+len(raw)*np.log(2*np.pi)
    return float(-2*(logsumexp(-.5*(np.sum(residual**2, axis=0)+normalization))-np.log(9)))


def main():
    start = time.monotonic(); checks = []; physical_rows = []; unknown_errors = []; contrasts = []
    def check(name, passed, **detail):
        checks.append(dict(name=name, passed=bool(passed), **detail))
    protocol = read(SCI / 'protocol02.json'); seal = read(SCI / 'RF_seal.json'); execution = read(SCI / 'execution.json')
    check('exact protocol, all original/revised input bytes and RF output hashes',
        sha(SCI / 'protocol02.json') == seal['protocol_sha256'] ==
        'c50f0dee25838b41c42a42beba40c390a752337270098f27aac62ef0c878f05e' and
        all(sha(path) == value for path, value in protocol['source_input_hashes'].items()) and
        all(sha(path) == value for path, value in seal['files'].items()))
    expected_slots = []
    case_rows = {q['case']: q for q in execution['cases']}
    for case in protocol['cases']:
        meta = read(SCI / 'prepared' / case / 'metadata.json'); pool = meta['pool']; points = meta['entry']['points']
        check(case + ': fixed full-owner pool and common archived weak axis',
            len(pool) == len(set(pool)) == 8 and meta['all8_families_absent_from_parent_likelihood'] and
            len(meta['entry']['observation_ids']) == len(set(meta['entry']['observation_ids'])) == points and
            np.allclose(np.array(meta['probes']['plus'])-meta['probes']['minus'], .2*np.array(meta['weak']), rtol=0, atol=1e-14))
        summaries = {}
        for probe in protocol['probes']:
            for arm in protocol['arms']:
                folder = SCI / case / probe
                for identity in pool+['unknown']:
                    path = folder / (arm+'_'+str(identity)+'.json')
                    expected_slots.append(dict(case=case, probe=probe, arm=arm, identity=identity,
                        status='complete' if path.exists() else 'failed_or_missing'))
                background_path = folder / (arm+'_background.npz')
                if not background_path.exists():
                    continue
                background = arrays(background_path); parent = read(folder / (arm+'_parent.json'))
                check(case+'/'+probe+'/'+arm+': common-coordinate proper radio background, exact parent IDs/hard prerequisites',
                    np.array_equal(background['common_x'], meta['probes'][probe]) and len(background['raw']) == points and
                    np.linalg.eigvalsh(background['covariance']).min() > 0 and
                    not parent['removed_curved_ids'] and not parent['removed_predictive_ids'] and
                    parent['phase_qualified'] and parent['precision_qualified'] and parent['support_qualified'] and
                    parent['retained_calibration_nonempty'] and bool(parent['retained_supported_families']) and
                    parent['maximum_unclipped_parent_phase_s'] <= 15.000001 and parent['final_phase_change_s'] <= .01 and
                    np.isfinite(parent['final_log_precision_change']) and parent['final_log_precision_change'] <= 1e-5)
                if probe == 'center':
                    saved = arrays(SCI / 'prepared' / case / (arm+'.npz'))
                    check(case+'/'+arm+': serialized center is unchanged actual prepared background',
                        all(np.array_equal(background[k], saved[k]) for k in ['raw', 'covariance', 'q']))
                path = folder / (arm+'_unknown.json')
                if path.exists():
                    unknown = read(path)
                    error = abs(independent_unknown(background['raw'], background['covariance'], np.array(meta['target_times_s']))-unknown['objective'])
                    unknown_errors.append(error)
                    check(case+'/'+probe+'/'+arm+': proper degree4 unknown, shared radio covariance and normalized nine aliases',
                        error <= 1e-7 and unknown['reference_passed'] == (unknown['reference_error'] <= 1e-7), objective_difference=error)
                for norad in pool:
                    path = folder / (arm+'_'+str(norad)+'.json')
                    if not path.exists():
                        continue
                    row = read(path); primary = read(folder / (arm+'_'+str(norad)+'_primary.json'))
                    physical_rows.append(row)
                    changed = {'independent_GL32_64', 'primary_reference_objective_difference', 'point_quadrature_stable'}
                    check(case+'/'+probe+'/'+arm+'/'+str(norad)+': primary checkpoint unchanged and prior/support law retained',
                        all(row[k] == v for k, v in primary.items() if k not in changed) and
                        row['norad'] == norad and row['case'] == case and row['arm'] == arm and row['probe'] == probe and
                        row.get('visible_mass_renormalized') is False and
                        row.get('original_phase_sd_s', 0) > 0)
                path = folder / (arm+'_summary.json')
                if not path.exists():
                    continue
                summary = read(path); summaries[probe, arm] = summary
                rows = [read(folder / (arm+'_'+str(norad)+'.json')) for norad in pool]
                check(case+'/'+probe+'/'+arm+': all eight components, exact original hard label, no score-selected replacement',
                    [q['norad'] for q in summary['models']] == pool and summary['models'] == rows and
                    summary['hard']['objective'] == next(q['objective'] for q in rows if q['norad'] == meta['hard_norad']) and
                    summary['all_point_quadratures_stable'] == all(q['point_quadrature_stable'] for q in rows))
                for weight in [.25, .5, .75]:
                    saved = summary['mixture'][str(weight)]; expected = mixture(rows, unknown, weight)
                    check(case+'/'+probe+'/'+arm+': normalized full-source mixture '+str(weight),
                        saved['available'] and abs(saved['objective']-expected['objective']) < 1e-10 and
                        np.allclose(saved['conditional_model_weights'], expected['weights'], rtol=1e-12, atol=1e-12) and
                        saved['bounds_available'] == expected['bounds_available'] and
                        not saved['weights_are_calibrated_identity_probabilities'] and
                        (not expected['bounds_available'] or max(abs(saved['lower_objective']-expected['lower']), abs(saved['upper_objective']-expected['upper'])) < 1e-10))
        record = case_rows[case]
        if record['status'] == 'complete':
            check(case+': all twelve plus/minus mixture contrasts retained', len(record['contrasts']) == 6 and len(summaries) == 6)
            for contrast in record['contrasts']:
                arm, weight = contrast['arm'], contrast['weight']; minus, plus = summaries['minus', arm], summaries['plus', arm]
                m, p = minus['mixture'][str(weight)], plus['mixture'][str(weight)]; hm, hp = minus['hard'], plus['hard']
                expected = (p['objective']-hp['objective']-m['objective']+hm['objective'])/.2
                proxy = -.5*expected/meta['weak_information']
                bounded = all(q.get('bounds_available') for q in [m, p, hm, hp])
                passed = (abs(contrast['delta_finite_difference_per_km']-expected) < 1e-10 and
                    abs(contrast['archived_c0_curvature_scaled_secant_proxy_km']-proxy) < 1e-10 and
                    contrast['bounds_available'] == bounded and not contrast['true_derivative_claimed'] and
                    not contrast['achieved_displacement_claimed'])
                if bounded:
                    low = (p['lower_objective']-hp['upper_objective']-m['upper_objective']+hm['lower_objective'])/.2
                    high = (p['upper_objective']-hp['lower_objective']-m['lower_objective']+hm['upper_objective'])/.2
                    interval = np.array([-.5*high, -.5*low])/meta['weak_information']
                    passed &= np.allclose(contrast['delta_finite_difference_interval'], [low, high], rtol=0, atol=1e-10)
                    passed &= np.allclose(contrast['proxy_interval_km'], interval, rtol=0, atol=1e-10)
                    passed &= contrast['interval_supports_material_25m'] == bool(interval[0] >= .025 or interval[1] <= -.025)
                check(case+'/'+arm+': finite-secants and conservative proxy interval '+str(weight), passed)
                contrasts.append(dict(case=case, **contrast))
    check('all108 preregistered outcome slots, no failed/missing substitution',
        len(expected_slots) == 108 and execution['all108_slots'] == expected_slots and set(case_rows) == {'DS24-0011', 'DS24-0012'})
    check('original600second cumulative cap, all terminal and no position/GPS/operational changes',
        abs(execution['cumulative_scientific_seconds']-protocol['preparation_seconds']-sum(q['scientific_seconds'] for q in execution['cases'])) < 1e-8 and
        execution['cumulative_scientific_seconds'] <= 600.1 and execution['all_cases_terminal'] and
        execution['position_fits'] == 0 and not execution['GPS_used'] and not execution['operational_adoption'])
    seconds = time.monotonic()-start
    receipt = dict(all_passed=all(q['passed'] for q in checks), checks=checks, seconds=seconds,
        source_sha256=sha(__file__), protocol_sha256=sha(SCI/'protocol02.json'), RF_seal_sha256=sha(SCI/'RF_seal.json'),
        slot_counts=dict(Counter(q['status'] for q in expected_slots)), physical_completed=len(physical_rows),
        quadrature_stable=sum(q['point_quadrature_stable'] for q in physical_rows),
        absolute_precision_qualified=sum(q['numerically_qualified'] for q in physical_rows),
        maximum_independent_unknown_objective_error=max(unknown_errors, default=0), contrasts=contrasts,
        orbit_propagation_calls=0, position_fits=0, geographic_truth_read=False,
        scope='Bounded central finite differences under declared whole-source priors, not calibrated posterior identity or optimized position results.')
    with (ROOT/'audit/ambiguity_terminal.json').open('x') as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps(dict(all_passed=receipt['all_passed'], checks=len(checks), seconds=seconds,
        failed=[q for q in checks if not q['passed']], physical_completed=len(physical_rows),
        maximum_unknown_error=receipt['maximum_independent_unknown_objective_error'])))


if __name__ == '__main__':
    main()
