"""Cold multiple-family deletion proposals, selected on full cross-family RF prediction.

Unlike leave-one-family-out position averaging, half-family fits can escape
several mutually supporting bad families. Full original-data gates still apply.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time

import numpy as np

from algo02_scan import pair_passes
from ds23_multifamily_proposals import subsets, family_masks, score_position
from ds23_frequency_events import make_event_problem, attach_event_predictive
from probe_ds23_fft_grid_position import setup
from probe_ds23_frequency_events import refit, summary, cached
from probe_ds23_symmetric_family_selection import SIGNED
from probe_algo03_frame_peak_recovery import SOURCE
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT / 'reports/2026_10_20_ds23_multifamily_proposals'
ARMS = ('c0', 'fitted_c')


def hashes():
    return {str(p.relative_to(ROOT)): sha(p) for p in (Path(__file__),
        ROOT / 'tools/ds23_multifamily_proposals.py', ROOT / 'tools/ds23_frequency_events.py',
        ROOT / 'tools/ds23_family_predictive_selection.py')}


def prepare():
    OUT.mkdir(exist_ok=True)
    path = OUT / 'protocol.json'
    if path.exists():
        p = read(path)
        if p['source_sha256'] != hashes():
            raise ValueError('frozen multi-family experiment changed')
        return p
    evidence = read(SIGNED / 'evaluation_audit.json')['evidence']
    chosen = np.random.default_rng(2026102071).choice(sorted(evidence), 40, replace=False).tolist()
    development, confirmation = sorted(chosen[:20]), sorted(chosen[20:])
    sizes = sorted((sum(read(SOURCE / c / 'algo02_result.json')['mask']), c) for c in development)
    p = dict(development_cases=development, confirmation_cases=confirmation,
        seed=2026102071, source_sha256=hashes(),
        pilot_cases=[sizes[k][1] for k in (0, len(sizes)//2, len(sizes)-1)],
        pilot_selection='curved point count minimum/median/maximum, without GPS errors',
        incumbent_bindings={c: evidence[c] for c in chosen}, workers=24,
        proposals='six deterministic case-hashed random subsets of half the active curved families, at least four retained and at least six total',
        null_candidate='published signed-prior incumbent, same full cross-family score as proposals',
        subset_training='all curved and predictive factors of omitted families excluded; five cold phase rounds of 48 position steps',
        scoring='sum of leave-one-family-out Gaussian predictive log densities at fixed candidate position, with full nuisance covariance, unseen Gamma noise and held phase prior marginal variance',
        scoring_counts='each original curved observation exactly once; predictive linear data never set calibration',
        scoring_approximation='moment-matched composite predictive score, not joint evidence or a calibrated identity probability',
        scoring_phase_rounds=5, position_covariance_in_score=False,
        c_pair_matching='same six subsets, original masks, labels, aliases, powers, priors and budgets; one common proposal index selected by c0 score',
        selection='lowest qualified c0 score; require gains greater than 2log7 in both c arms relative to null',
        final_acceptance='restore every original curved and predictive observation, refresh phases five times at the candidate position, require original paired gates and phase change <=0.01',
        failed_pair_fallback='exact published signed-prior incumbent; no scan removed',
        primary='fitted-c mean AND median improve in both cohorts; disclose all c0 outcomes',
        cold_start_km=[0, 0], box_width_km=25, goal_population=413,
        no_GPS_future_TLE_new_RF_or_cross_scan_position_prior=True,
        single_scan_fits=True, cohort_recordings_disjoint_not_untouched_locations=True)
    write(path, p)
    return p


def fixed_full(scan, node, keep, arm, position, powers, means, model, entries):
    reference = np.zeros(len(means))
    for _ in range(5):
        p = cached(make_event_problem(scan, node, keep, arm, reference, powers, means, model, []))
        attach_event_predictive(p, entries, powers)
        phase = np.clip(p.state(position)['phases'][p.labels], -15, 15)
        change = float(np.max(abs(phase - p.reference)))
        reference = phase
    return dict(summary(p, position, entries), final_phase_change_s=change)


def run(case):
    protocol = prepare()
    path = OUT / (case + '.json')
    if path.exists():
        return dict(case=case, cached=True)
    began = time.monotonic()
    scan, node, keep, base, old, signed, binding, model, powers, means, entries = setup(case)
    if binding != protocol['incumbent_bindings'][case]:
        raise ValueError('published incumbent source binding changed')
    incumbent = signed['policy_arms']
    labels = np.asarray(base.labels)[base.flat_labels]
    families = np.unique(labels[keep])
    offered = subsets(case, families)
    trials, null_replays = [], []
    null_positions = {a: np.asarray(incumbent[a]['endpoint_east_north_km']) for a in ARMS}
    for arm in ARMS:
        r = incumbent[arm]
        p = make_event_problem(scan, node, keep, arm, np.asarray(r['phase_reference']), powers, means, model, [])
        attach_event_predictive(p, entries, powers)
        delta = p.calculate(null_positions[arm])['negative_twice_elbo'] - r['negative_twice_elbo']
        if abs(delta) > 1e-3:
            raise ValueError('published RF incumbent does not replay')
        null_replays.append(dict(arm=arm, RF_difference=delta))
    if offered:
        null_scores = {a: score_position(scan, node, keep, a, powers, means, model, null_positions[a]) for a in ARMS}
        for k, chosen in enumerate(offered):
            train = family_masks(labels, keep, chosen)
            predictive = [e for e in entries if e['candidate_index'] in chosen]
            pair = {a: refit(scan, node, train, a, powers, means, model, [], predictive) for a in ARMS}
            qualified = all(r['final_phase_change_s'] <= .01 and
                np.isfinite(r['endpoint_east_north_km']).all() and
                np.max(abs(np.asarray(r['endpoint_east_north_km']))) < 12.49 for r in pair.values())
            scores = {a: score_position(scan, node, keep, a, powers, means, model,
                np.asarray(pair[a]['endpoint_east_north_km'])) for a in ARMS} if qualified else {}
            trials.append(dict(index=k, families=chosen, train_points=int(train.sum()),
                train_predictive_points=sum(e['points'] for e in predictive), arms=pair,
                training_qualified=qualified, scores=scores,
                qualified=bool(qualified and all(s['qualified'] for s in scores.values()))))
            write(OUT / (case + '_progress.json'), dict(completed=len(trials), total=len(offered)))
        eligible = [t for t in trials if t['qualified']]
        candidate = min(eligible, key=lambda t: t['scores']['c0']['score']) if eligible else None
        gains = {a: null_scores[a]['score'] - candidate['scores'][a]['score'] for a in ARMS} if candidate else {}
        positive = bool(candidate and all(s['qualified'] for s in null_scores.values()) and
            all(g > 2*np.log(7) for g in gains.values()))
        pair = {a: fixed_full(scan, node, keep, a, np.asarray(candidate['arms'][a]['endpoint_east_north_km']),
            powers, means, model, entries) for a in ARMS} if positive else {}
        accepted = bool(pair and pair_passes(pair, include_linear=True))
    else:
        null_scores, gains, pair, candidate, accepted = {}, {}, {}, None, False
    record = dict(case=case, accepted=accepted, selected_index=candidate['index'] if candidate else None,
        selected_full_arms=pair, policy_arms=pair if accepted else incumbent,
        incumbent_arms=incumbent, baseline_arms=old['policy_arms'], trials=trials,
        null_scores=null_scores, score_gains=gains, null_endpoint_replay=null_replays,
        original_mask=keep, incumbent_binding=binding, original_family_count=len(families),
        seconds=time.monotonic()-began, source_sha256=hashes(),
        GPS_used=False, future_TLE_used=False, no_original_points_removed=True,
        all_candidates_scored_on_identical_original_curved_observations=True)
    write(path, record)
    row = dict(case=case, accepted=accepted, families=len(families), proposals=len(trials), seconds=record['seconds'])
    print(row, flush=True)
    return row


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=('prepare', 'pilot', 'development', 'confirmation'), required=True)
    args = parser.parse_args()
    protocol = prepare()
    if args.stage != 'prepare':
        cases = protocol[args.stage + '_cases']
        receipts = []
        with ProcessPoolExecutor(max_workers=min(protocol['workers'], len(cases))) as pool:
            futures = {pool.submit(run, c): c for c in cases}
            for future in as_completed(futures):
                try:
                    receipts.append(future.result())
                except Exception as exc:
                    receipts.append(dict(case=futures[future], error=repr(exc)))
                write(OUT / (args.stage + '_progress.json'), dict(receipts=receipts, completed=len(receipts), total=len(cases)))
        write(OUT / (args.stage + '_execution.json'), dict(all_terminal=True, receipts=receipts))
        print('Terminal', len(receipts), 'errors', sum('error' in r for r in receipts), flush=True)
