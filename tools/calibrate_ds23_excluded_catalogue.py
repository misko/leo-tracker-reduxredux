"""RF-only two-family exclusion contexts for a fresh causal catalogue search."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time
import numpy as np

from ds23_excluded_catalogue import choose_families
from ds23_frequency_events import make_event_problem, attach_event_predictive
from probe_ds23_fft_grid_position import setup
from probe_ds23_frequency_events import cached, refit
from probe_ds23_symmetric_family_selection import SIGNED
from probe_algo03_frame_peak_recovery import SOURCE
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT / 'reports/2026_10_20_ds23_excluded_catalogue'
ARMS = ('c0', 'fitted_c')


def hashes():
    return {str(p.relative_to(ROOT)): sha(p) for p in (Path(__file__),
        ROOT / 'tools/ds23_excluded_catalogue.py', ROOT / 'tools/ds23_frequency_events.py')}


def prepare():
    OUT.mkdir(exist_ok=True)
    path = OUT / 'calibration_protocol.json'
    if path.exists():
        p = read(path)
        if p['source_sha256'] != hashes():
            raise ValueError('frozen excluded-family calibration changed')
        return p
    evidence = read(SIGNED / 'evaluation_audit.json')['evidence']
    choices = np.random.default_rng(2026102072).choice(sorted(evidence), 40, replace=False).tolist()
    development, confirmation = sorted(choices[:20]), sorted(choices[20:])
    sizes = sorted((sum(read(SOURCE / c / 'algo02_result.json')['mask']), c) for c in development)
    p = dict(development_cases=development, confirmation_cases=confirmation,
        pilot_cases=[sizes[k][1] for k in (0, len(sizes)//2, len(sizes)-1)],
        random_seed=2026102072, workers=24, source_sha256=hashes(),
        incumbent_bindings={c:evidence[c] for c in choices},
        targets='two active curved families with largest standardized phase plus physical orbit posterior pull; >=24 points and >=2 receiver/channel lanes',
        exclusion='all curved and predictive factors of BOTH families removed together before any catalogue score',
        cold_start_km=[0, 0], box_width_km=25, phase_rounds=5, position_steps_per_round=48,
        priors_noise_weights_and_retained_observations_unchanged=True,
        matching_c0_fitted_c_masks_labels_priors_and_budgets=True,
        context_qualification='finite interior point and phase change <=0.01 in both arms; failed contexts keep incumbent',
        no_GPS_future_TLE_new_RF_or_cross_scan_position_prior=True,
        disjoint_recordings_not_untouched_geographic_locations=True,
        primary='fitted-c mean AND median improve in both cohorts; disclose all c0 results',
        success_report_requires_frozen_broader_evaluation=True)
    write(path, p)
    return p


def context(case):
    scan, node, keep, base, old, signed, binding, model, powers, means, entries = setup(case)
    path = OUT / (case + '_calibration.json')
    saved = read(path)
    if saved['incumbent_binding'] != binding:
        raise ValueError('published prior binding changed')
    return scan, node, keep, base, old, signed, model, powers, means, entries, saved


def run(case):
    protocol = prepare()
    path = OUT / (case + '_calibration.json')
    if path.exists():
        return dict(case=case, cached=True)
    began = time.monotonic()
    scan, node, keep, base, old, signed, binding, model, powers, means, entries = setup(case)
    if binding != protocol['incumbent_bindings'][case]:
        raise ValueError('published incumbent changed')
    for element in scan.elements.values():
        provenance = element['provenance']
        if max(provenance['element_epoch_utc_ns'], provenance['collected_utc_ns']) > scan.receipt['cutoff_utc_ns']:
            raise ValueError('noncausal catalogue element')
    incumbent = signed['policy_arms']
    replays, initial = [], None
    for arm in ARMS:
        r = incumbent[arm]
        p = make_event_problem(scan, node, keep, arm, np.asarray(r['phase_reference']), powers, means, model, [])
        attach_event_predictive(p, entries, powers)
        cached(p)
        x = np.asarray(r['endpoint_east_north_km'])
        difference = p.calculate(x)['negative_twice_elbo']-r['negative_twice_elbo']
        if abs(difference) > 1e-3:
            raise ValueError('disabled-hypothesis endpoint does not replay')
        replays.append(dict(arm=arm, RF_difference=difference))
        if arm == 'c0':
            initial = p, x
    targets = choose_families(*initial)
    held = [t['candidate_index'] for t in targets]
    labels = np.asarray(base.labels)[base.flat_labels]
    train = keep & ~np.isin(labels, held)
    predictive = [e for e in entries if e['candidate_index'] not in held]
    if np.any(train & np.isin(labels, held)) or any(e['candidate_index'] in held for e in predictive):
        raise ValueError('held-family observation leaked into calibration')
    arms = {a:refit(scan, node, train, a, powers, means, model, [], predictive) for a in ARMS} if len(held)==2 and train.any() else {}
    qualified = bool(arms and all(r['final_phase_change_s'] <= .01 and
        np.isfinite(r['endpoint_east_north_km']).all() and np.max(abs(np.asarray(r['endpoint_east_north_km']))) < 12.49 for r in arms.values()))
    write(path, dict(case=case, targets=targets, mask=train, original_mask=keep,
        predictive_entries=predictive, arms=arms, qualified=qualified,
        incumbent_arms=incumbent, incumbent_binding=binding,
        excluded_curved_points=int(keep.sum()-train.sum()),
        excluded_predictive_points=sum(e['points'] for e in entries)-sum(e['points'] for e in predictive),
        no_held_family_in_curved_or_predictive_calibration=True,
        original_endpoint_replays=replays, seconds=time.monotonic()-began,
        source_sha256=hashes(), no_GPS_or_future_TLE_used=True))
    row = dict(case=case, qualified=qualified, held_norads=[t['norad'] for t in targets], seconds=time.monotonic()-began)
    print(row, flush=True)
    return row


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=('prepare', 'pilot', 'cohort'), required=True)
    args = parser.parse_args()
    protocol = prepare()
    if args.stage != 'prepare':
        cases = protocol['pilot_cases'] if args.stage=='pilot' else protocol['development_cases']+protocol['confirmation_cases']
        receipts = []
        with ProcessPoolExecutor(max_workers=min(24, len(cases))) as pool:
            futures = {pool.submit(run, c):c for c in cases}
            for f in as_completed(futures):
                try:
                    receipts.append(f.result())
                except Exception as exc:
                    receipts.append(dict(case=futures[f], error=repr(exc)))
                write(OUT / (args.stage+'_calibration_progress.json'), dict(completed=len(receipts), total=len(cases)))
        write(OUT / (args.stage+'_calibration_execution.json'), dict(all_terminal=True,
            receipts=receipts, errors=[r for r in receipts if 'error' in r]))
        print('Terminal', len(receipts), 'errors', sum('error' in r for r in receipts), flush=True)
