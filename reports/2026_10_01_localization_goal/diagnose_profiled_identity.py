"""Profile alternative group identities over epoch offsets, then restore free association."""
import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
from acquisition_dot import prepare
from epoch_prior_adapter import FixedOriginalPort
from regression_batch import digest, verify_sources

from leo.analysis.localization_fast import fit_localization_fast
from leo.analysis.localization_group_proposals import rank_group_proposals

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    freeze = HERE/'profiled-identity-v1/sources.json'
    verify_sources(json.loads(freeze.read_text())['source_sha256'])
    original = HERE/'regression-v1-freeze.json'
    assert digest(original) == original.with_suffix('.sha256').read_text().strip()
    verify_sources(json.loads(original.read_text())['source_sha256'])
    parent_path = next((HERE/'regression-v1').glob('batch-*/'+args.unit+'.json'))
    assert digest(parent_path) == json.loads(parent_path.with_suffix('.seal.json').read_text())[
        'prediction_sha256']
    parent = json.loads(parent_path.read_text())
    scan, height, ports = prepare(args.unit)
    assert parent['inputs'] == scan.inputs and parent['height'] == height.input_bindings
    assert parent['observations'] == [list(p.observation_ids) for p in ports]
    state = np.asarray(parent['best']['mean'])
    assigned = [int(np.argmax(p.score_all(state))) for p in ports]
    logs = [p.score_selected(state, i) for p, i in zip(ports, assigned, strict=True)]
    precision = np.r_[0., 0., 1., np.full(len(state)-3, 4.)]
    baseline_objective = .5*(precision*state)@state-sum(logs)
    assert abs(baseline_objective-parent['best']['objectives'][-1]) < 1e-6
    grid = np.array([-4., -2., -1., -.5, 0., .5, 1., 2., 4.])
    cube = []
    for epoch in grid:
        probe = state.copy()
        probe[5:] = epoch
        cube.append(np.stack([p.score_all(probe)[:-1] for p in ports]))
    proposals = rank_group_proposals(np.stack(cube), grid, assigned, logs, state[5:], limit=3)
    proposal_seconds = time.monotonic()-start
    rows = []
    best_state, best_objective, selected = state, float(baseline_objective), None
    for rank, proposal in enumerate(proposals):
        if time.monotonic() >= start+50.:
            rows.append(dict(rank=rank, proposal=asdict(proposal), status='not_started_budget'))
            continue
        seed = state.copy()
        seed[5+proposal.source] = 0.
        seed[5+proposal.target] = grid[proposal.epoch_index]
        trial_assignments = assigned.copy()
        for track in proposal.track_indices:
            trial_assignments[track] = proposal.target
        fixed = [FixedOriginalPort(p, i) for p, i in zip(ports, trial_assignments, strict=True)]
        conditional = fit_localization_fast(
            seed, fixed, precision, lambda x: np.linalg.norm(x[:2]) <= 250., max_iterations=8,
            deadline=min(start+50., time.monotonic()+8.), degrees_of_freedom=4.)
        # Conditional stage only generates a seed. It is never accepted as an
        # original-model solution; restore every original branch for the test.
        fit = fit_localization_fast(
            conditional.mean, ports, precision, lambda x: np.linalg.norm(x[:2]) <= 250.,
            max_iterations=64, deadline=min(start+50., time.monotonic()+10.),
            degrees_of_freedom=4.)
        objective = fit.objectives[-1] if fit.objectives else None
        status = 'converged' if fit.converged else 'unresolved'
        if fit.converged and objective < best_objective-1e-6:
            best_state, best_objective, selected = fit.mean, float(objective), rank
        rows.append(dict(
            rank=rank, proposal=asdict(proposal), status=status,
            proposed_epoch_s=float(grid[proposal.epoch_index]),
            source_norad=int(scan.bank.norad_ids[proposal.source]),
            target_norad=int(scan.bank.norad_ids[proposal.target]),
            conditional_reason=conditional.reason, conditional_iterations=conditional.iterations,
            conditional_mean=conditional.mean.tolist(),
            conditional_objectives=list(conditional.objectives),
            converged=fit.converged, reason=fit.reason, iterations=fit.iterations,
            mean=fit.mean.tolist(), objectives=list(fit.objectives),
            original_objective_gain=float(baseline_objective-objective) if objective else None,
            final_assignment_changes=sum(a != b for a, b in
                                         zip(assigned, fit.associations, strict=True)),
            position_change_m=float(1000*np.linalg.norm(fit.mean[:2]-state[:2]))))
    result = dict(
        unit=args.unit, parent_sha256=digest(parent_path), source_freeze_sha256=digest(freeze),
        inputs=scan.inputs, height=height.input_bindings, observations=parent['observations'],
        assignments=assigned, epoch_grid_s=grid.tolist(), proposal_seconds=proposal_seconds,
        proposals=rows, baseline_objective=float(baseline_objective),
        selected_proposal=selected, selected_objective=best_objective,
        selected_mean=best_state.tolist(), seconds=time.monotonic()-start,
        cpu_seconds=time.process_time()-cpu,
        qualification='Warm profiled-identity search diagnostic, not cold scan performance. '
        'Whole assigned groups propose unused satellites at9 fixed epoch offsets, paying one '
        'epoch prior per satellite. Top3 proposals get8 fixed-identity iterations then64 '
        'free-association iterations; baseline retained unless a converged original-objective '
        'gain exceeds1e-6. No GPS. Grid search is not exhaustive over identities or offsets.')
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    args.output.with_suffix('.sha256').write_text(digest(args.output)+'\n')
    keys = ['unit', 'proposal_seconds', 'selected_proposal', 'baseline_objective',
            'selected_objective', 'seconds']
    print(json.dumps({k: result[k] for k in keys}))


if __name__ == '__main__':
    main()
