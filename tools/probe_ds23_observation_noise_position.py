"""Controlled regional comparison of fragment, block and point noise models."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import signal
import time
import numpy as np

from ds23_observation_noise import make_observation_noise_problem
from investigate_dsx01_localization_failures import fit
from probe_ds23_frequency_events import cached, summary
from probe_ds23_sign_carrier_position import context_signed, SIGNED_AUDIT
from run_ds23_combined_recovery_full import ARMS, valid
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_21_ds23_observation_noise'
BULK = Path('/srv/bulk/leo/research/ds23-observation-noise-20261021')
MODELS = dict(fragment=None, point=1, block4=4)
CASES = ['DS23-0202', 'DS23-0274', 'DS23-0293', 'DS23-0240', 'DS23-0112', 'DS23-0114', 'DS23-0289']
PENALTY = float(2*np.log(2))


def refit(data, model, arm, linear):
    scan, node, mask, powers, means, hyper, entries, *_ = data
    x, reference, history = np.zeros(2), np.zeros(len(means)), []
    for _ in range(5):
        p = make_observation_noise_problem(scan, node, mask, arm, reference, powers, means, hyper,
                                            entries if linear else [], MODELS[model]); cached(p)
        result = fit(p, x, iterations=48); x = np.asarray(result['parameters'])
        phase = np.clip(p.state(x)['phases'][p.labels], -15, 15)
        change = float(np.max(abs(phase-reference)))
        history.append(dict(fit=result, phase_change_s=change)); reference = phase
    c = p.calculate(x)
    record = summary(p, x, entries if linear else [])
    record.update(history=history, final_phase_change_s=change, precision_iterations=c['precision_iterations'],
        final_log_precision_change=c['final_log_precision_change'],
        noise_precision=c['noise_precision'], noise_groups=p.noise_groups,
        original_noise_groups=p.original_noise_groups)
    return record


def choose(curved):
    eligible = [m for m in MODELS if m != 'fragment'
                and curved['fragment']['negative_twice_elbo']-curved[m]['negative_twice_elbo'] > PENALTY
                and curved[m]['final_phase_change_s'] <= .01 and curved[m]['final_log_precision_change'] <= 1e-4]
    return min(eligible, key=lambda m: curved[m]['negative_twice_elbo']) if eligible else 'fragment'


def run(case):
    path = BULK/(case+'.json')
    if path.exists():
        return read(path)
    started = time.monotonic()
    def timeout(*_):
        raise TimeoutError('600second observation-noise case budget exhausted')
    signal.signal(signal.SIGALRM, timeout); signal.alarm(600)
    try:
        data = context_signed(case); scan, node, mask, powers, means, hyper, entries, signed, source = data
        replay = {}
        for arm, old in signed['policy_arms'].items():
            p = make_observation_noise_problem(scan, node, mask, arm, np.array(old['phase_reference']),
                                                powers, means, hyper, entries, None)
            r = summary(p, np.array(old['endpoint_east_north_km']), entries)
            replay[arm] = r['negative_twice_elbo']-old['negative_twice_elbo']
            if abs(replay[arm]) > 1e-6:
                raise ValueError('fragment-noise control fails exact incumbent replay')
        curved = {m: refit(data, m, 'c0', False) for m in MODELS}
        selected = choose(curved)
        print(case, 'curved RF choice', selected,
            {m: curved['fragment']['negative_twice_elbo']-r['negative_twice_elbo'] for m, r in curved.items()}, flush=True)
        results = {}
        for model in MODELS:
            pair = {arm: refit(data, model, arm, True) for arm in ARMS}
            accepted = valid(pair) and all(r['final_log_precision_change'] <= 1e-4 for r in pair.values())
            results[model] = dict(arms=pair, paired_valid=accepted,
                                  policy_arms=pair if accepted else signed['policy_arms'])
            print(case, model, 'paired gates', accepted, flush=True)
        policy = signed['policy_arms'] if selected == 'fragment' else results[selected]['policy_arms']
        record = dict(case=case, status='complete', results=results, curved_selection=curved, selected_model=selected,
            policy_arms=policy, incumbent_arms=signed['policy_arms'], exact_fragment_control_replay=replay,
            original_mask=mask, powers=powers, means_s=means, hyper=hyper, entries=entries,
            signed_incumbent_path=str(source.relative_to(ROOT)), signed_incumbent_sha256=sha(source),
            all_original_observations_retained=True, no_original_alias_or_label_or_gate_changes=True,
            marginal_noise_Gamma_prior_unchanged=True, no_GPS_or_future_TLE_used=True)
    except Exception as exc:
        record = dict(case=case, status='failed', error=repr(exc))
    finally:
        signal.alarm(0)
    record['seconds'] = time.monotonic()-started; write(path, record)
    return record


def freeze():
    OUT.mkdir(parents=True, exist_ok=True); BULK.mkdir(parents=True, exist_ok=True)
    protocol = dict(cases=CASES, development_cases=True, models=MODELS,
        hypothesis='a few bad points currently deflate reliability of every point in the same curved fragment',
        unchanged_marginal_noise_prior='Gamma(2,2); E[1/tau]=2 for fragment, point and block4',
        changed_only='partition of curved measurement noise precision',
        linear_measurements_remain_one_predictive_block_with_full_curved_covariance=True,
        all_original_observations_labels_aliases_masks_and_gates_preserved=True,
        selection='lowest normalized curved-only c0 bound, gain over fragment >2log2; phase and noise convergence',
        no_GPS_selection=True, generalized_evidence_not_exact_probability=True,
        paired_c0_fitted_c=True, workers=7, per_case_seconds=600, phase_rounds=5, position_iterations=48,
        cold_start=[0, 0], regional_center=[37.906, -122.545], regional_width_km=25,
        exact_incumbent_fallback_on_any_original_gate_or_numerical_failure=True,
        source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/ds23_observation_noise.py']},
        signed_audit_sha256=sha(SIGNED_AUDIT))
    import json
    protocol = json.loads(json.dumps(protocol))
    path = OUT/'protocol.json'
    if path.exists() and read(path) != protocol:
        raise ValueError('observation-noise experiment changed')
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
