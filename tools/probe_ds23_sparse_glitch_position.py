"""Sparse measurement glitches with curved-only calibration selection."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import signal
import time
import numpy as np

from ds23_sparse_glitch_noise import make_glitch_problem
from investigate_dsx01_localization_failures import fit
from probe_ds23_frequency_events import cached, summary
from probe_ds23_sign_carrier_position import context_signed, SIGNED_AUDIT
from run_ds23_combined_recovery_full import ARMS, valid
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_21_ds23_sparse_glitches'
BULK = Path('/srv/bulk/leo/research/ds23-sparse-glitches-20261021')
MODELS = dict(fragment=(0., 0.), curved_tail=(.01, 0.), predictive_tail=(0., .01), both=(.01, .01))
CASES = ['DS23-0202', 'DS23-0274', 'DS23-0293', 'DS23-0240', 'DS23-0112', 'DS23-0114', 'DS23-0289']


def refit(data, model, arm, linear):
    scan, node, mask, powers, means, hyper, entries, *_ = data
    x, reference, history = np.zeros(2), np.zeros(len(means)), []
    for _ in range(5):
        p = make_glitch_problem(scan, node, mask, arm, reference, powers, means, hyper,
                               entries if linear else [], *MODELS[model]); cached(p)
        fitted = fit(p, x, iterations=48); x = np.asarray(fitted['parameters'])
        phase = np.clip(p.state(x)['phases'][p.labels], -15, 15)
        change = float(np.max(abs(phase-reference))); history.append(dict(fit=fitted, phase_change_s=change)); reference = phase
    c = p.calculate(x); record = summary(p, x, entries if linear else [])
    record.update(history=history, final_phase_change_s=change,
        final_log_precision_change=c['final_log_precision_change'],
        linear_mixture_convergence=c.get('linear_mixture_convergence', 0.),
        noise_precision=c['noise_precision'], group_noise_precision=c['group_noise_precision'],
        glitch_probability=c['glitch_probability'], linear_glitch_probability=c.get('linear_glitch_probability', []))
    return record


def converged(record):
    return record['final_log_precision_change'] <= 1e-4 and record['linear_mixture_convergence'] <= 1e-4


def select(curved, results):
    n = max(2, curved['fragment']['active_points'])
    gain = curved['fragment']['negative_twice_elbo']-curved['curved_tail']['negative_twice_elbo']
    curved_choice = 'curved_tail' if (gain > np.log(n) and curved['curved_tail']['final_phase_change_s'] <= .01
                                    and converged(curved['curved_tail'])) else 'fragment'
    alternative = 'both' if curved_choice == 'curved_tail' else 'predictive_tail'
    nlinear = max(2, results[curved_choice]['arms']['c0']['predictive_points'])
    predictive_gain = results[curved_choice]['arms']['c0']['negative_twice_elbo']-results[alternative]['arms']['c0']['negative_twice_elbo']
    choice = alternative if predictive_gain > np.log(nlinear) and results[alternative]['paired_valid'] else curved_choice
    return dict(model=choice, curved_choice=curved_choice, curved_gain=gain, curved_penalty=float(np.log(n)),
                predictive_gain=predictive_gain, predictive_penalty=float(np.log(nlinear)))


def run(case):
    path = BULK/(case+'.json')
    if path.exists():
        return read(path)
    started = time.monotonic()
    def timeout(*_):
        raise TimeoutError('600second sparse-glitch case budget exhausted')
    signal.signal(signal.SIGALRM, timeout); signal.alarm(600)
    try:
        data = context_signed(case); scan, node, mask, powers, means, hyper, entries, signed, source = data
        replays = {}
        for arm, old in signed['policy_arms'].items():
            p = make_glitch_problem(scan, node, mask, arm, np.array(old['phase_reference']), powers, means, hyper, entries, 0., 0.)
            r = summary(p, np.array(old['endpoint_east_north_km']), entries)
            replays[arm] = r['negative_twice_elbo']-old['negative_twice_elbo']
            if abs(replays[arm]) > 1e-6:
                raise ValueError('no-glitch control fails original objective replay')
        curved = {m: refit(data, m, 'c0', False) for m in ['fragment', 'curved_tail']}
        results = {}
        for model in MODELS:
            pair = {a: refit(data, model, a, True) for a in ARMS}
            accepted = valid(pair) and all(converged(r) for r in pair.values())
            results[model] = dict(arms=pair, paired_valid=accepted, policy_arms=pair if accepted else signed['policy_arms'])
            print(case, model, 'paired_valid', accepted, flush=True)
        selection = select(curved, results); choice = selection['model']
        policy = signed['policy_arms'] if choice == 'fragment' else results[choice]['policy_arms']
        record = dict(case=case, status='complete', results=results, curved_selection=curved, selection=selection,
            policy_arms=policy, incumbent_arms=signed['policy_arms'], control_replay=replays,
            original_mask=mask, powers=powers, means_s=means, hyper=hyper, entries=entries,
            incumbent_path=str(source.relative_to(ROOT)), incumbent_sha256=sha(source),
            all_original_points_retained=True, original_labels_aliases_and_gates_unchanged=True,
            noise_marginal_variance_unchanged=True, no_GPS_or_future_TLE=True)
    except Exception as exc:
        record = dict(case=case, status='failed', error=repr(exc))
    finally:
        signal.alarm(0)
    record['seconds'] = time.monotonic()-started; write(path, record)
    print(case, record['status'], record.get('selection'), record.get('error'), flush=True)
    return record


def freeze():
    OUT.mkdir(parents=True, exist_ok=True); BULK.mkdir(parents=True, exist_ok=True)
    import json
    protocol = dict(cases=CASES, development_only=True, models=MODELS,
        glitch_prior_probability=.01, glitch_SD_ratio=10, mixture_variance_normalized_to_one=True,
        original_fragment_Gamma_noise_preserved=True, marginal_noise_variance_unchanged=True,
        linear_calibration_means_never_update=True, all_original_observations_gates_and_physical_priors_preserved=True,
        selection='curved-tail choice from curved-only c0 bound gain>logN; then predictive-tail choice with same curved calibration class, paired gates, full c0 gain>logNlinear',
        linear_data_do_not_choose_curved_calibration_noise_class=True,
        fixed_latent_probability_and_variance_ratio_not_fitted_hyperparameters=True,
        cold_start=[0, 0], regional_center=[37.906, -122.545], regional_width_km=25,
        phase_rounds=5, position_iterations=48, workers=7, per_case_seconds=600, matched_c0_fitted_c=True,
        no_GPS_or_future_TLE_or_satellite_whitelist=True,
        source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/ds23_sparse_glitch_noise.py']},
        signed_audit_sha256=sha(SIGNED_AUDIT))
    protocol = json.loads(json.dumps(protocol)); path = OUT/'protocol.json'
    if path.exists() and read(path) != protocol:
        raise ValueError('sparse-glitch position protocol changed')
    if not path.exists():
        write(path, protocol)
    return protocol


def main():
    protocol = freeze()
    with ProcessPoolExecutor(max_workers=7) as pool:
        rows = [f.result() for f in as_completed([pool.submit(run, c) for c in protocol['cases']])]
    write(OUT/'execution.json', dict(rows=rows, all_terminal=True, failures=[r for r in rows if r['status'] != 'complete']))


if __name__ == '__main__':
    main()
