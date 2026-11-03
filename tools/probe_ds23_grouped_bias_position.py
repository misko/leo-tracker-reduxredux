"""Frozen constant-bias covariance comparisons; geography is audit-only.

Every fragment retains its300Hz marginal prior. The curved-only normalized
bound chooses a covariance, before linear predictive data are evaluated.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import signal
import time

import numpy as np

from ds23_grouped_bias_prior import make_grouped_bias_problem
from investigate_dsx01_localization_failures import fit
from probe_ds23_frequency_events import cached, summary
from probe_ds23_sign_carrier_position import context_signed, SIGNED_AUDIT
from run_algo01_ds23_sample import ROOT, read, write, sha
from run_ds23_combined_recovery_full import ARMS, valid

OUT = ROOT/'reports/2026_10_20_ds23_grouped_bias_position'
BULK = Path('/srv/bulk/leo/research/ds23-grouped-bias-position-20261020')
MODELS = dict(null=(0., 0.), channel=(.75, 0.), family=(0., .75), crossed=(.375, .375))
PENALTY = float(2*np.log(3))
DEVELOPMENT = ['DS23-0202', 'DS23-0274', 'DS23-0293', 'DS23-0240', 'DS23-0112', 'DS23-0114']


def refit(data, model, arm, include_linear):
    scan, node, mask, powers, means, hyper, entries, *_ = data
    x, reference, history = np.zeros(2), np.zeros(len(means)), []
    for _ in range(5):
        p = make_grouped_bias_problem(scan, node, mask, arm, reference, powers, means,
            hyper, entries, *MODELS[model], include_linear=include_linear)
        cached(p)
        result = fit(p, x, iterations=48)
        x = np.asarray(result['parameters'])
        phase = np.clip(p.state(x)['phases'][p.labels], -15, 15)
        change = float(np.max(abs(phase-reference)))
        history.append(dict(fit=result, phase_change_s=change))
        reference = phase
    record = summary(p, x, entries if include_linear else [])
    record.update(history=history, final_phase_change_s=change)
    return record


def choose_model(curved_records):
    scores = {m: r['negative_twice_elbo'] for m, r in curved_records.items()}
    eligible = {m: v for m, v in scores.items()
                if m != 'null' and scores['null']-v > PENALTY
                and curved_records[m]['final_phase_change_s'] <= .01}
    return min(eligible, key=eligible.get) if eligible else 'null'


def run(case, stage):
    target = BULK/stage/(case+'.json')
    if target.exists():
        return read(target)
    began = time.monotonic()
    def timeout(*_):
        raise TimeoutError('600second grouped covariance case budget exhausted')
    signal.signal(signal.SIGALRM, timeout); signal.alarm(600)
    try:
        data = context_signed(case)
        scan, node, mask, powers, means, hyper, entries, signed, source = data
        replay = {}
        for arm, old in signed['policy_arms'].items():
            p = make_grouped_bias_problem(scan, node, mask, arm, np.array(old['phase_reference']),
                powers, means, hyper, entries, 0., 0.)
            r = summary(p, np.array(old['endpoint_east_north_km']), entries)
            delta = r['negative_twice_elbo']-old['negative_twice_elbo']
            if abs(delta) > 1e-6:
                raise ValueError('zero correlation fails exact incumbent replay')
            replay[arm] = delta
        curved = {m: refit(data, m, 'c0', False) for m in MODELS}
        selected = choose_model(curved)
        print(case, 'curved-only choice', selected, 'gains',
              {m: curved['null']['negative_twice_elbo']-r['negative_twice_elbo'] for m, r in curved.items()}, flush=True)
        models = list(MODELS) if stage == 'development' else sorted({'null', selected})
        results = {}
        for m in models:
            pair = {a: refit(data, m, a, True) for a in ARMS}
            accepted = valid(pair)
            results[m] = dict(arms=pair, paired_valid=accepted,
                              policy_arms=pair if accepted else signed['policy_arms'])
            print(case, m, 'paired_valid', accepted, flush=True)
        chosen = results[selected]
        record = dict(case=case, status='complete', stage=stage, selected_model=selected,
            curved_selection=curved, results=results, policy_arms=chosen['policy_arms'],
            selected_paired_valid=chosen['paired_valid'], incumbent_arms=signed['policy_arms'],
            original_mask=mask, powers=powers, means_s=means, hyper=hyper, entries=entries,
            incumbent_path=str(source.relative_to(ROOT)), incumbent_sha256=sha(source),
            zero_correlation_replay=replay, matched_c0_fitted_c=True,
            marginal_fragment_sigma_hz=300, linear_observations_never_update_calibration=True,
            selected_without_GPS=True, no_new_observations_or_aliases=True)
    except Exception as exc:
        record = dict(case=case, status='failed', stage=stage, error=repr(exc))
    finally:
        signal.alarm(0)
    record['seconds'] = time.monotonic()-began
    write(target, record)
    return record


def freeze(stage):
    OUT.mkdir(exist_ok=True); (BULK/stage).mkdir(parents=True, exist_ok=True)
    if stage == 'development':
        cases = DEVELOPMENT
    else:
        import random
        prior = ['2026_10_20_ds23_shared_probe_confirmation', '2026_10_20_ds23_joint_probe_confirmation',
                 '2026_10_20_ds23_multilane_confirmation']
        excluded = set(DEVELOPMENT)
        for name in prior:
            excluded.update(read(ROOT/'reports'/name/'selection.json')['cases'])
        eligible = sorted(set(read(SIGNED_AUDIT)['evidence'])-excluded)
        cases = random.Random(20261025).sample(eligible, 20)
    protocol = dict(cases=cases, stage=stage, models=MODELS, model_search_penalty=PENALTY,
        selection='lowest curved-only normalized c0 bound, gain over null >2log3; no linear likelihood selection',
        fixed_marginal_sigma_hz=300, matched_c0_fitted_c=True, phase_rounds=5, position_iterations=48,
        region_center=[37.906, -122.545], regional_box_km=25, start=[0, 0],
        linear_covariance='conditional Schur bias covariance plus full curved posterior',
        no_GPS_or_future_TLE_or_whitelist=True, original_gates_observations_priors_other_than_bias_covariance_preserved=True,
        exact_incumbent_fallback_on_either_arm_gate_failure=True,
        all_recording_formats_eligible=True, same_site_not_new_location_validation=True,
        workers=8, per_case_seconds=600, signed_audit_sha256=sha(SIGNED_AUDIT),
        source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/ds23_grouped_bias_prior.py']})
    target = OUT/(stage+'_protocol.json')
    if target.exists() and read(target) != read_jsonable(protocol):
        raise ValueError('grouped bias frozen protocol changed')
    if not target.exists():
        write(target, protocol)
    return protocol


def read_jsonable(value):
    import json
    return json.loads(json.dumps(value))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['development', 'confirmation'], required=True)
    args = parser.parse_args(); protocol = freeze(args.stage)
    with ProcessPoolExecutor(max_workers=8) as pool:
        rows = [f.result() for f in as_completed([pool.submit(run, c, args.stage) for c in protocol['cases']])]
    write(OUT/(args.stage+'_execution.json'), dict(rows=rows, all_terminal=True,
        protocol_sha256=sha(OUT/(args.stage+'_protocol.json'))))


if __name__ == '__main__':
    main()
