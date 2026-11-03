"""One bounded mode-support control after single-curve reentry diagnoses."""

import copy
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import signal
import time

import numpy as np

from ds23_active_mode_support import make_problem
from ds23_frequency_events import attach_event_predictive
from ds23_feasible_position import feasible_fit
from investigate_dsx01_localization_failures import fit
from probe_algo03_feasible_recovery import gate_slacks
from probe_ds23_frequency_events import cached, summary
from probe_ds23_reentry_family_cavity import audit_baseline
from probe_ds23_single_curved_reentry import OUT as NOMINATIONS
from probe_ds23_worst_association_bottleneck import OUT as DEBUG, setup
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = DEBUG/'support_aware_reentry'


def protected(d):
    return {r['candidate_index'] for r, sl in zip(d['base'].rows, d['base'].slices, strict=True)
            if d['keep'][sl].any()} | {e['candidate_index'] for e in d['entries']}


def build(d, node, keep, arm, reference, means):
    p = make_problem(d['scan'], node, keep, arm, np.asarray(reference), d['powers'], means, d['model'], protected(d))
    attach_event_predictive(p, d['entries'], d['powers'])
    return cached(p)


def refit(d, node, keep, arm, means):
    x, reference, history = np.zeros(2), np.zeros(len(means)), []
    for _ in range(5):
        p = build(d, node, keep, arm, reference, means)
        result = fit(p, x, iterations=48)
        x = np.asarray(result['parameters'])
        phase = np.clip(p.state(x)['phases'][p.labels], -15, 15)
        history.append(dict(fit=result, phase_change_s=float(np.max(abs(phase-reference)))))
        reference = phase
    record = summary(p, x, d['entries'])
    record.update(history=history, final_phase_change_s=history[-1]['phase_change_s'],
                  disabled_shape_families=p.disabled_new_one_owner_orbit_families)
    return record


def one(case):
    start = time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('240 s final support control cap')))
    signal.alarm(240)
    try:
        d = setup(case)
        old = read(NOMINATIONS/(case+'_positions.json'))
        candidates = []
        for trial in old['trials']:
            if trial['paired_valid']:
                continue
            node, keep, means = trial['node'], np.asarray(trial['mask'], bool), np.asarray(trial['means'])
            p = build(d, node, keep, 'c0', trial['arms']['c0']['phase_reference'], means)
            if not p.disabled_new_one_owner_orbit_families:
                continue
            # Only standalone otherwise-good curves, or their combination with
            # the previously selected valid addition; no repeated broad sweep.
            if len(trial['additions']) <= 2:
                candidates.append(trial)
        candidates.sort(key=lambda r: (len(r['additions']), tuple(a['component'] for a in r['additions'])))
        trials = []
        for proposal in candidates[:2]:
            pair = {arm: refit(d, proposal['node'], np.asarray(proposal['mask'], bool), arm,
                               np.asarray(proposal['means'])) for arm in ['c0', 'fitted_c']}
            result = copy.deepcopy(proposal)
            result.update(arms=pair, paired_valid=bool(valid(pair) and all(r['final_phase_change_s'] <= .01 for r in pair.values())),
                          original_all_nominee_support_pair_passed=proposal['paired_valid'])
            trials.append(result)
            print(case, 'mode-support control', [a['norad'] for a in proposal['additions']], result['paired_valid'], flush=True)
        record = dict(case=case, status='complete', trials=trials, no_GPS_or_future_TLE_used=True,
                      frozen_incumbent_modes_and_all_points_and_gates_unchanged=True,
                      no_new_ALGO_version=True, seconds=time.monotonic()-start,
                      source_sha256=sha(Path(__file__)), helper_sha256=sha(ROOT/'tools/ds23_active_mode_support.py'))
    except Exception as exc:
        import traceback
        record = dict(case=case, status='failed', error=repr(exc), traceback=traceback.format_exc())
    finally:
        signal.alarm(0)
    write(OUT/(case+'.json'), record)
    return record


def main():
    OUT.mkdir(exist_ok=True)
    protocol = dict(cases=read(DEBUG/'protocol.json')['cases'],
          final_bounded_prototype_in_this_iteration=True, per_case_s=240, at_most_two_previously_failed_proposals=True,
          newly_active_one_owner_families_keep_phase_but_disable_three_orbit_shape_modes=True,
          incumbent_curved_and_predictive_mode_support_preserved=True, no_gate_relaxed=True,
          same_both_c_arm_points_priors_starts_and_fit_budgets=True,
          cold_regional_start=[0, 0], phase_rounds=5, position_steps=48,
          source_sha256=sha(Path(__file__)), helper_sha256=sha(ROOT/'tools/ds23_active_mode_support.py'))
    if (OUT/'protocol.json').exists():
        raise FileExistsError('preserve frozen control')
    write(OUT/'protocol.json', protocol)
    with ProcessPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(one, protocol['cases']))
    write(OUT/'execution.json', dict(rows=[dict(case=r['case'], status=r['status']) for r in rows],
                                   all_terminal=True, all_passed=all(r['status'] == 'complete' for r in rows)))


if __name__ == '__main__':
    main()
