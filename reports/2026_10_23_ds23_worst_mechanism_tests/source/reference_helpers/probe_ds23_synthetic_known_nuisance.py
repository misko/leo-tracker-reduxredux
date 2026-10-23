"""Bounded value-of-information controls, not an operational estimator.

Each test uses the same noisy all-component simulation. Only declared nuisance
prior means/uncertainties change. All fits start at regional zero, not truth.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import signal
import time
import numpy as np

from ds23_synthetic_known_nuisance import known_problem, attach_known_predictive, COMPONENTS
from ds23_synthetic_phase_law import bounded_phase_draw
from ds23_frequency_events import make_event_problem, attach_event_predictive
from investigate_dsx01_localization_failures import fit
from probe_ds23_frequency_events import parameters, summary, cached
from probe_ds23_synthetic_noise import perturb_tracks, gate_counts
import probe_ds23_synthetic_nuisance_components as component
from run_ds23_combined_recovery_full import context, prepare, ARMS, valid
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT / 'reports/2026_10_20_ds23_synthetic_known_nuisance'
SOURCE = ROOT / 'reports/2026_10_20_ds23_synthetic_nuisance_v2'
VARIANTS = {name: (name,) for name in COMPONENTS}
VARIANTS.update(phase_smooth=('phase', 'smooth'), all=COMPONENTS)


def prepare_protocol():
    prepare()
    source = read(SOURCE / 'protocol.json')
    for name, expected in source['source_sha256'].items():
        if sha(ROOT / 'tools' / name) != expected:
            raise ValueError('generating simulator changed')
    cases = sorted({r['case'] for r in source['jobs'] if r['stratum'] == 'random_validation'})
    protocol = dict(cases=cases, site_by_case={c: source['site_by_case'][c] for c in cases},
        variants=VARIANTS, source_protocol_sha256=sha(SOURCE / 'protocol.json'),
        source_evaluation_sha256=sha(SOURCE / 'evaluation.json'),
        known_coordinate_prior_SD_fraction=1e-5, linear_known_bias_SD_hz=.003,
        workers=8, per_variant_seconds=120, cold_start_km=[0., 0.],
        phase_rounds=5, position_iterations=48, same_noise_observations_masks_weights=True,
        synthetic_truth_used_only_for_diagnostic_oracle_priors=True,
        real_evaluation_GPS_used=False, real_DS23_accuracy_gain=False,
        original_gates_unchanged_no_observations_removed=True,
        source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT / 'tools/ds23_synthetic_known_nuisance.py']})
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'protocol.json'
    # JSON canonicalization also converts variant tuples to lists.
    import json
    protocol = json.loads(json.dumps(protocol))
    if target.exists() and read(target) != protocol:
        raise ValueError('oracle diagnostic protocol changed')
    if not target.exists(): write(target, protocol)
    return protocol


def setup(case, site):
    scan, node, mask, base, old = context(case)
    powers, means, hyper = parameters(scan, base, old)
    entries = old['linear_entries'] if old['linear_paired_valid'] else []
    component.SITE = tuple(site); component.bounded_phase_draw = bounded_phase_draw
    synthetic, copied, predictive, truth = component.synthesize(scan, node, mask, base,
        powers, means, hyper, entries, 'all', 0)
    noise = perturb_tracks(synthetic, set(base.members) | {e['track_index'] for e in predictive},
        194729 + int(case.split('-')[1]))
    saved = read(SOURCE / (case + '_draw0_all.json'))
    if noise != saved['noise']:
        raise ValueError('matched synthetic noise changed')
    for key in ('selected_coefficients', 'true_phases_s', 'phase_prior_sigma_s'):
        np.testing.assert_array_equal(truth[key], saved['generation_truth'][key])
    return synthetic, copied, mask, powers, means, hyper, predictive, truth, saved


def fit_known(scan, node, mask, arm, powers, means, hyper, entries, truth, known):
    reference = np.zeros(len(means)); x = np.zeros(2); history = []
    for _ in range(5):
        p = known_problem(scan, node, mask, arm, reference, powers, means, hyper, truth, known)
        attach_known_predictive(p, entries, powers, truth, known); cached(p)
        fitted = fit(p, x, iterations=48); x = np.asarray(fitted['parameters'])
        phase = np.clip(p.state(x)['phases'][p.labels], -15, 15)
        history.append(dict(fit=fitted, phase_change_s=float(np.max(abs(phase - reference)))))
        reference = phase
    record = summary(p, x, entries)
    record.update(history=history, final_phase_change_s=history[-1]['phase_change_s'])
    return record


def run_case(case, site):
    data = setup(case, site)
    scan, node, mask, powers, means, hyper, entries, truth, baseline = data
    # No-knowledge builder must recover the actual frozen likelihood at both
    # saved endpoints, including predictive covariance and gate booleans.
    differences = {}
    for arm in ARMS:
        saved = baseline['arms'][arm]; x = np.asarray(saved['endpoint_east_north_km'])
        ref = np.asarray(saved['phase_reference'])
        p = known_problem(scan, node, mask, arm, ref, powers, means, hyper, truth, [])
        attach_known_predictive(p, entries, powers, truth, []); cached(p)
        direct = make_event_problem(scan, node, mask, arm, ref, powers, means, hyper, [])
        attach_event_predictive(direct, entries, powers); cached(direct)
        a, b = p.calculate(x), direct.calculate(x)
        np.testing.assert_array_equal(a['coefficient'], b['coefficient'])
        np.testing.assert_array_equal(a['residual'], b['residual'])
        differences[arm] = float(a['negative_twice_elbo'] - saved['negative_twice_elbo'])
        if abs(differences[arm]) > 1e-6:
            raise ValueError('no-oracle likelihood does not match frozen baseline')
    write(OUT / (case + '_identity_control.json'), dict(case=case,
        objective_replay_differences=differences, coefficients_and_residuals_bitwise_identical=True,
        baseline_sha256=sha(SOURCE / (case + '_draw0_all.json'))))
    results = []
    for variant, known in VARIANTS.items():
        path = OUT / (case + '_' + variant + '.json')
        if path.exists():
            results.append(read(path)); continue
        started = time.monotonic()
        def timeout(*_): raise TimeoutError('120 second truth-conditioned control budget exhausted')
        signal.signal(signal.SIGALRM, timeout); signal.alarm(120)
        record = dict(case=case, variant=variant, known_components=list(known),
            synthetic_site_east_north_km=site, real_GPS_used=False,
            diagnostic_truth_priors_not_a_real_data_algorithm=True)
        try:
            pair = {arm: fit_known(scan, node, mask, arm, powers, means, hyper, entries, truth, known) for arm in ARMS}
            for arm, r in pair.items():
                r['synthetic_position_error_km'] = float(np.linalg.norm(np.asarray(r['endpoint_east_north_km']) - site))
                r['original_gate_counts'] = gate_counts(r)
            if any(r['linear_calibration_max_difference'] != 0 for r in pair.values()):
                raise ValueError('predictive linear tracks updated calibration')
            record.update(status='complete', arms=pair, paired_qualified=valid(pair))
        except Exception as exc:
            record.update(status='failed', error=repr(exc))
        finally:
            signal.alarm(0)
        record['seconds'] = time.monotonic() - started; write(path, record)
        print(case, variant, record['status'], {a: r['synthetic_position_error_km'] for a, r in record.get('arms', {}).items()}, flush=True)
        results.append(record)
    return results


def evaluate(protocol):
    summaries = {}; pending = []; failures = []
    for variant in ['baseline', *VARIANTS]:
        rows = []
        for case in protocol['cases']:
            path = SOURCE / (case + '_draw0_all.json') if variant == 'baseline' else OUT / (case + '_' + variant + '.json')
            if not path.exists(): pending.append(dict(case=case, variant=variant)); continue
            r = read(path)
            if r['status'] != 'complete': failures.append(dict(case=case, variant=variant, error=r.get('error'))); continue
            rows.append(r)
        summaries[variant] = {}
        for arm in ARMS:
            err = [r['arms'][arm]['synthetic_position_error_km'] for r in rows]
            summaries[variant][arm] = dict(n=len(err), mean_km=float(np.mean(err)) if err else None,
                median_km=float(np.median(err)) if err else None, maximum_km=max(err) if err else None,
                all_original_gates_pass=sum(gate_counts(r['arms'][arm])['all_original_gates_pass'] for r in rows))
    write(OUT / 'evaluation.json', dict(summary=summaries, pending=pending, failures=failures,
        complete=not pending and not failures, protocol_sha256=sha(OUT / 'protocol.json'),
        real_DS23_accuracy_gain=False))
    print('ORACLE_DIAGNOSTIC', summaries, 'pending', len(pending), 'failures', len(failures), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--case')
    args = parser.parse_args(); protocol = prepare_protocol()
    cases = [args.case] if args.case else protocol['cases']
    if not set(cases).issubset(protocol['cases']): raise ValueError('case outside predeclared random templates')
    with ProcessPoolExecutor(max_workers=min(8, len(cases))) as pool:
        jobs = [pool.submit(run_case, c, protocol['site_by_case'][c]) for c in cases]
        for f in as_completed(jobs):
            f.result()
    evaluate(protocol)


if __name__ == '__main__': main()
