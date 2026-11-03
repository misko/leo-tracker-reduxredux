"""Nearest original-gate-feasible position for RF-qualified subset proposals.

This policy is declared before any geographic evaluation of the proposal cohort.
All original observations remain; cross-family scores must still improve after
projection. The target is an RF-derived position, never a supplied coordinate.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time

import numpy as np

from algo02_scan import pair_passes
from ds23_feasible_position import feasible_fit
from ds23_frequency_events import make_event_problem, attach_event_predictive
from ds23_multifamily_proposals import score_position
from probe_algo03_feasible_recovery import gate_slacks
from probe_ds23_fft_grid_position import setup
from probe_ds23_frequency_events import cached, summary
from probe_ds23_multifamily_proposals import OUT as SOURCE, prepare as source_protocol
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT / 'reports/2026_10_20_ds23_multifamily_projection'
ARMS = ('c0', 'fitted_c')


def prepare():
    OUT.mkdir(exist_ok=True)
    path = OUT / 'protocol.json'
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in (Path(__file__),
        ROOT / 'tools/ds23_feasible_position.py', ROOT / 'tools/probe_algo03_feasible_recovery.py')}
    if path.exists():
        p = read(path)
        if p['source_sha256'] != hashes or p['base_protocol_sha256'] != sha(SOURCE / 'protocol.json'):
            raise ValueError('frozen projection policy changed')
        return p
    base = source_protocol()
    if (SOURCE / 'evaluation.json').exists():
        raise ValueError('declare this policy before geographic evaluation')
    p = dict(development_cases=base['development_cases'], confirmation_cases=base['confirmation_cases'],
        source_sha256=hashes, base_protocol_sha256=sha(SOURCE / 'protocol.json'),
        hypothesis='project an RF-predictively qualified multiple-family candidate onto the original acceptance region instead of rejecting it outright',
        target='same selected RF proposal index in both c arms; minimize squared Euclidean displacement in regional km coordinates',
        gate_slack_margin=.01, constrained_phase_rounds=5, constrained_steps_per_round=40,
        final_selection='original paired gates and phase convergence; full cross-family score remains >2log7 better in both arms than original null',
        fallback='entire existing unprojected proposal policy, including its exact signed-prior fallback',
        original_observations_labels_aliases_noise_weights_priors_and_c_arm_matching=True,
        no_original_point_removal_or_gate_relaxation=True,
        no_GPS_future_TLE_new_RF_or_cross_scan_position_prior=True,
        declared_before_this_cohorts_geographic_evaluation=True, workers=24,
        primary='fitted-c mean AND median improve in both cohorts relative to signed incumbent; disclose all c0 outcomes')
    write(path, p)
    return p


def project(scan, node, keep, arm, original, powers, means, model, entries):
    target = np.asarray(original['endpoint_east_north_km'])
    position = target.copy()
    reference = np.asarray(original['phase_reference'])
    history = []
    for epoch in range(5):
        p = make_event_problem(scan, node, keep, arm, reference, powers, means, model, [])
        attach_event_predictive(p, entries, powers)
        cached(p)
        result = feasible_fit(lambda x: float(np.sum((np.asarray(x)-target)**2)),
            lambda x: np.array(list(gate_slacks(p, x, entries).values())) - .01,
            position, p.lower, p.upper, iterations=40)
        position = np.asarray(result['parameters'])
        phase = np.clip(p.state(position)['phases'][p.labels], -15, 15)
        change = float(np.max(abs(phase - p.reference)))
        history.append(dict(epoch=epoch, result=result, phase_change_s=change))
        reference = phase
    return dict(summary(p, position, entries), history=history, final_phase_change_s=change,
        minimum_gate_slack=min(gate_slacks(p, position, entries).values()),
        displacement_from_RF_candidate_km=float(np.linalg.norm(position-target)))


def run(case):
    prepare()
    path = OUT / (case + '.json')
    if path.exists():
        return dict(case=case, cached=True)
    began = time.monotonic()
    base_path = SOURCE / (case + '.json')
    base = read(base_path)
    proposed, scores, gains = {}, {}, {}
    attempted = bool(base['selected_full_arms'] and not base['accepted'])
    accepted = False
    if attempted:
        scan, node, keep, _, _, signed, _, model, powers, means, entries = setup(case)
        if signed['policy_arms'] != base['incumbent_arms']:
            raise ValueError('original incumbent changed')
        proposed = {a: project(scan, node, keep, a, base['selected_full_arms'][a],
            powers, means, model, entries) for a in ARMS}
        valid = pair_passes(proposed, include_linear=True)
        if valid:
            scores = {a: score_position(scan, node, keep, a, powers, means, model,
                np.asarray(proposed[a]['endpoint_east_north_km'])) for a in ARMS}
            gains = {a: base['null_scores'][a]['score'] - scores[a]['score'] for a in ARMS}
            accepted = bool(all(s['qualified'] for s in scores.values()) and
                all(g > 2*np.log(7) for g in gains.values()))
    record = dict(case=case, attempted=attempted, accepted=accepted,
        projected_arms=proposed, projected_scores=scores, score_gains=gains,
        policy_arms=proposed if accepted else base['policy_arms'],
        unprojected_policy_arms=base['policy_arms'], incumbent_arms=base['incumbent_arms'],
        base_fit_sha256=sha(base_path), seconds=time.monotonic()-began,
        GPS_used=False, future_TLE_used=False, no_original_points_removed=True,
        source_sha256=sha(Path(__file__)))
    write(path, record)
    row = dict(case=case, attempted=attempted, accepted=accepted, seconds=record['seconds'])
    print(row, flush=True)
    return row


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=('prepare', 'run'), required=True)
    args = parser.parse_args()
    protocol = prepare()
    if args.stage == 'run':
        execution = read(SOURCE / 'cohort_execution.json')
        if not execution['all_terminal'] or execution['errors']:
            raise ValueError('base cohort must finish without errors first')
        cases = protocol['development_cases'] + protocol['confirmation_cases']
        receipts = []
        with ProcessPoolExecutor(max_workers=24) as pool:
            futures = {pool.submit(run, c): c for c in cases}
            for f in as_completed(futures):
                try:
                    receipts.append(f.result())
                except Exception as exc:
                    receipts.append(dict(case=futures[f], error=repr(exc)))
                write(OUT / 'progress.json', dict(completed=len(receipts), total=len(cases)))
        write(OUT / 'execution.json', dict(all_terminal=True, receipts=receipts,
            errors=[r for r in receipts if 'error' in r]))
        print('Terminal', len(receipts), 'errors', sum('error' in r for r in receipts), flush=True)
