"""Restore all evidence after a group-deletion excursion; original objective only."""
import argparse
import json
import time
from pathlib import Path

import numpy as np
from acquisition_dot import prepare
from regression_batch import digest, verify_sources

from leo.analysis.localization_fast import fit_localization_fast

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    freeze_path = HERE/'deletion-bridge-v1/sources.json'
    frozen = json.loads(freeze_path.read_text())
    verify_sources(frozen['source_sha256'])
    original = HERE/'regression-v1-freeze.json'
    assert digest(original) == original.with_suffix('.sha256').read_text().strip()
    verify_sources(json.loads(original.read_text())['source_sha256'])
    deletion_path = Path(frozen['parents'][args.unit])
    deletion = json.loads(deletion_path.read_text())
    assert digest(deletion_path) == deletion_path.with_suffix('.sha256').read_text().strip()
    assert deletion['refit']['converged']
    path = next((HERE/'regression-v1').glob('batch-*/'+args.unit+'.json'))
    assert digest(path) == deletion['parent_sha256']
    parent = json.loads(path.read_text())
    assert parent['best']['converged']
    scan, height, ports = prepare(args.unit)
    assert scan.inputs == parent['inputs'] and height.input_bindings == parent['height']
    assert [list(p.observation_ids) for p in ports] == parent['observations']
    original_state = np.asarray(parent['best']['mean'])
    state = np.asarray(deletion['refit']['mean'])
    precision = np.r_[0., 0., 1., np.full(len(state)-3, 4.)]
    original_assignments = [int(np.argmax(p.score_all(original_state))) for p in ports]
    original_objective = .5*float((precision*original_state)@original_state)-sum(
        float(p.score_selected(original_state, i))
        for p, i in zip(ports, original_assignments, strict=True))
    assert abs(original_objective-parent['best']['objectives'][-1]) < 1e-6
    fit = fit_localization_fast(
        state, ports, precision, lambda s: np.linalg.norm(s[:2]) <= 250.,
        max_iterations=64, deadline=start+25., degrees_of_freedom=4.)
    result = dict(
        unit=args.unit, parent_sha256=digest(path), deletion_sha256=digest(deletion_path),
        source_freeze_sha256=digest(freeze_path), seconds=time.monotonic()-start,
        cpu_seconds=time.process_time()-cpu, converged=fit.converged, reason=fit.reason,
        iterations=fit.iterations, mean=fit.mean.tolist(), objectives=list(fit.objectives),
        original_objective=original_objective,
        objective_gain=original_objective-fit.objectives[-1],
        displacement_from_original_m=float(1000*np.linalg.norm(fit.mean[:2]-original_state[:2])),
        initial_excursion_m=float(1000*np.linalg.norm(state[:2]-original_state[:2])),
        assignment_changes=sum(a != b for a, b in zip(
            original_assignments, fit.associations, strict=True)),
        track_count=len(ports), observations=parent['observations'],
        qualification='Warm search diagnostic, not independent cold inference. All original '
        'tracks restored; original normalized robust objective and free association. No GPS read. '
        'Inputs chosen from existing three pilot controls and two largest predicted influence '
        'checks, not geographic errors. No candidate selection using geographic reference.')
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    args.output.with_suffix('.sha256').write_text(digest(args.output)+'\n')
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ['mean', 'objectives', 'observations']}))


if __name__ == '__main__':
    main()
