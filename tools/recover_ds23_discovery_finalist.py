"""Finish the original third discovery branch in an isolated bounded run.

Recompute the frozen RF proposal pool and verify the two saved finalists before
reusing them. Never treat a two-branch timeout as the completed three-branch
search. Original benchmark files and observations remain untouched.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import time

import numpy as np

from run_algo02_ds23 import (
    ROOT, DEFAULT_RUN, THREAD_ENV, read, write as write_json, digest, verify_freeze, bounded_command,
)

OUT = ROOT / 'reports/2026_10_20_ds23_discovery_completion_v2'
CASE = 'DS23-0068'


def plain(value):
    return json.loads(json.dumps(value, default=lambda a: a.tolist(), sort_keys=True))


def write(path, value):
    write_json(path, plain(value))


def reconcile(selected, checkpoint):
    """A saved prefix is reusable only if every original ranked node agrees."""
    if len(selected) != 3 or checkpoint.get('GPS_used') is not False:
        raise ValueError('original three-finalist search and GPS-free checkpoint required')
    choices = checkpoint['choices']
    if [c['hypothesis'] for c in choices] != list(range(len(choices))) or len(choices) >= 3:
        raise ValueError('a strict, ordered incomplete prefix is required')
    for choice, (score, node) in zip(choices, selected):
        if abs(choice['center_score'] - score) > 1e-6 or plain(choice['node']) != plain(node):
            raise ValueError('regenerated original discovery finalists differ')
        if set(choice['arms']) != {'c0', 'fitted_c'}:
            raise ValueError('saved finalist lacks a complete c pair')
    return list(choices)


def prepare():
    verify_freeze(DEFAULT_RUN)
    OUT.mkdir(exist_ok=True)
    path = OUT / 'protocol.json'
    if path.exists():
        p = read(path)
        if p['source_sha256'] != digest(Path(__file__)):
            raise ValueError('recovery source changed after sealing')
        return p
    source = DEFAULT_RUN / CASE
    if read(source / 'execution_receipt.json')['code'] != 124 or (source / 'fit_radio_noise.json').exists():
        raise ValueError('original incomplete discovery status changed')
    files = [source / name for name in (
        'bank.npz', 'tracks.json', 'radio_noise.json', 'observations.json',
        'nominal_elements.json', 'receipt.json', 'previous.tle', 'previous_receipt.json',
        'tracking.json', 'input_receipt.json', 'prepared.json', 'progress_radio_noise.json')]
    files += list((DEFAULT_RUN / 'causal_prior' / CASE).iterdir())
    files += [DEFAULT_RUN / 'causal_phase_history' / (CASE + s) for s in ('.json', '_forecast.json')]
    bindings = {}
    for source_path in files:
        relative = source_path.relative_to(DEFAULT_RUN)
        target = OUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        before = digest(source_path)
        if not target.exists():
            shutil.copyfile(source_path, target)
        if digest(target) != before or digest(source_path) != before:
            raise ValueError('immutable checkpoint copy changed')
        bindings[str(relative)] = before
    checkpoint = read(source / 'progress_radio_noise.json')
    if checkpoint['GPS_used'] or [c['hypothesis'] for c in checkpoint['choices']] != [0, 1]:
        raise ValueError('expected exactly the first two completed original finalists')
    p = dict(case=CASE, input_sha256=bindings, source_sha256=digest(Path(__file__)),
        per_stage_timeout_s=300, stages=['discovery', 'initial', 'algo02'],
        scientific_seed_budget=4, fully_fitted_finalists=3, phase_rounds=5,
        position_iterations=48, cold_start_km=[0, 0], region_box_width_km=25,
        all_original_scientific_budgets_unchanged=True,
        unused_zero_phase_diagnostics_omitted=True,
        no_GPS_future_TLE_raw_IQ_or_new_RF=True,
        original_benchmark_and_timeout_receipts_preserved=True)
    write(path, p)
    return p


def discover():
    import evaluate_ds23_phase_refreshed as engine
    from iterate_dsx01_position_nominations import AnchoredFamilies

    p = read(OUT / 'protocol.json')
    for relative, expected in p['input_sha256'].items():
        if digest(DEFAULT_RUN / relative) != expected or digest(OUT / relative) != expected:
            raise ValueError('checkpoint source changed')
    directory = OUT / CASE
    if (directory / 'fit_radio_noise.json').exists():
        return
    checkpoint = read(directory / 'progress_radio_noise.json')
    began = time.monotonic()
    guard = engine.PilotGuard(directory)
    guard.install()
    scan = engine.FreshScan(directory, noise_mode='radio')
    sigma = scan.radio_sigma_hz
    candidates = engine.fresh_discovery(scan, sigma, budget=4)
    best = min(candidates, key=lambda r: r['center_score'])
    nodes, seen = [], set()
    for candidate in candidates:
        key = engine.signature(candidate)
        if key not in seen:
            nodes.append(candidate)
            seen.add(key)
    for point in engine.PROPOSAL_POINTS[1:]:
        seed, detail = engine.explore(scan, best['seed']['state'], point,
                                      'receiver_smooth', compact_update=False)
        anchor = AnchoredFamilies(scan, seed, 'receiver_smooth', False, point)
        node = dict(seed=seed, aliases=anchor.alias, proposal_point=point,
                    candidate_hypotheses=detail['candidate_hypotheses'])
        key = engine.signature(node)
        if key not in seen:
            nodes.append(node)
            seen.add(key)
    scored = []
    for node in nodes:
        cold = dict(seed=dict(rows=node['seed']['rows'], state=engine.zero_state(scan)),
                    aliases=node['aliases'])
        problem = engine.DiagnosticNormal(scan, cold, sigma, False,
            reference=np.zeros(len({r['candidate_index'] for r in cold['seed']['rows']})))
        residual = problem.residual(np.zeros(2))
        scored.append((float(residual @ residual), cold))
    selected = sorted(scored, key=lambda r: r[0])[:3]
    choices = reconcile(selected, checkpoint)
    differences = []
    for choice in choices:
        for arm, result in choice['arms'].items():
            problem = engine.DiagnosticNormal(scan, choice['node'], sigma, arm == 'fitted_c',
                                               reference=np.asarray(result['reference']))
            residual = problem.residual(np.asarray(result['fit']['parameters']))
            delta = float(residual @ residual) - result['fit']['score']
            if abs(delta) > 1e-3:
                raise ValueError('saved finalist endpoint does not replay')
            differences.append(dict(hypothesis=choice['hypothesis'], arm=arm, score_difference=delta))
    write(directory / 'regenerated_finalists.json', dict(
        original_two_prefix_verified=True, endpoint_replay=differences,
        unique_RF_hypotheses=len(scored), finalist_center_scores=[s for s, _ in selected],
        input_read_paths=sorted(guard.read_paths)))
    print('Original two ranked finalists and all four endpoint scores replayed', flush=True)
    for index in range(len(choices), 3):
        score, node = selected[index]
        pair = {}
        for arm in engine.ARMS:
            problem, result, history = engine.refreshed(scan, sigma, node, arm)
            x = result['parameters']
            legacy = dict(rows=problem.rows, state=problem.state(x), aliases=problem.alias,
                          east_north_km=x, fits=[result])
            metrics = engine.actual_metrics(problem, legacy, arm, x)
            pair[arm] = dict(fit=result, phase_rounds=history, state=problem.state(x),
                reference=problem.reference, metrics=metrics,
                all_graph_associations=engine.extend_associations(problem, x, metrics),
                profile_gradient=None,
                conditional_residual_hz=problem.calculate(x)['conditional_residual_hz'])
        choices.append(dict(hypothesis=index, center_score=score, node=node, arms=pair))
        write(directory / 'resumed_progress_radio_noise.json', dict(
            case=CASE, choices=choices, GPS_used=False, status='running'))
    winner = min(choices, key=lambda c: c['arms']['c0']['fit']['score'])
    write(directory / 'fit_radio_noise.json', dict(case=CASE, status='complete',
        GPS_used=False, choices=choices, selected_hypothesis=winner['hypothesis'],
        unique_RF_hypotheses=len(scored), fully_fitted_hypotheses=3,
        zero_phase_control={}, diagnostic_zero_phase_controls_not_reconstructed=True,
        same_observations_candidates_priors_bounds_and_budgets_in_c_pair=True,
        fresh_radio_seed_budget=4, RF_proposal_points=engine.PROPOSAL_POINTS,
        region_center=engine.CENTER, box_width_km=25, noise_sigma_hz=sigma, noise_mode='radio',
        noise_features_sha256=scan.fixed_window_noise_sha256,
        physical_prior_previous_tle_path=str(scan.previous_tle_path),
        input_read_paths=sorted(guard.read_paths), seconds=time.monotonic()-began,
        source_sha256=engine.sha(Path(engine.__file__)), original_saved_branches_replayed=True))
    print('All three original discovery finalists complete', flush=True)


def run():
    protocol = prepare()
    directory = OUT / CASE
    path = directory / 'recovery_receipt.json'
    if path.exists():
        print(read(path), flush=True)
        return
    env = dict(os.environ, PYTHONPATH='/tmp/algo03-feasible-deps:src:tools',
               PYTHONHASHSEED='0', **THREAD_ENV)
    stages = []
    began = time.monotonic()
    with (directory / 'recovery.log').open('a') as stream:
        for stage in protocol['stages']:
            command = ([str(ROOT / '.venv/bin/python'), __file__, '--stage', 'discover']
                if stage == 'discovery' else [str(ROOT / '.venv/bin/python'),
                    str(ROOT / 'tools/algo02_scan.py'), '--run-dir', str(OUT),
                    '--case', CASE, '--stage', stage])
            code = bounded_command(command, stream, protocol['per_stage_timeout_s'], env)
            stages.append(dict(stage=stage, exit_code=code))
            if code:
                break
    result = directory / 'algo02_result.json'
    receipt = dict(case=CASE, stages=stages, seconds=time.monotonic()-began,
        result_sha256=digest(result) if result.exists() else None,
        status=read(result)['status'] if result.exists() else 'unavailable')
    write(path, receipt)
    print(receipt, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=('prepare', 'discover', 'run'), required=True)
    stage = parser.parse_args().stage
    {'prepare': prepare, 'discover': discover, 'run': run}[stage]()
