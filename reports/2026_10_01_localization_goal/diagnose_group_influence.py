"""Reference-blind group deletion influence and optional bounded nonlinear check."""
import argparse
import json
import time
from pathlib import Path

import numpy as np
from acquisition_dot import prepare
from regression_batch import digest, verify_sources

from leo.analysis.localization_fast import fit_localization_fast
from leo.analysis.localization_influence import group_deletion_steps

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--refit-largest', action='store_true')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    start = time.monotonic()
    freeze_path = HERE/'regression-v1-freeze.json'
    assert digest(freeze_path) == freeze_path.with_suffix('.sha256').read_text().strip()
    verify_sources(json.loads(freeze_path.read_text())['source_sha256'])
    paths = list((HERE/'regression-v1').glob('batch-*/'+args.unit+'.json'))
    assert len(paths) == 1
    path = paths[0]
    assert digest(path) == json.loads(path.with_suffix('.seal.json').read_text())[
        'prediction_sha256']
    parent = json.loads(path.read_text())
    assert parent['best']['converged']
    scan, height, ports = prepare(args.unit)
    assert scan.inputs == parent['inputs'] and height.input_bindings == parent['height']
    assert [list(p.observation_ids) for p in ports] == parent['observations']
    state = np.asarray(parent['best']['mean'])
    assigned = [int(np.argmax(p.score_all(state))) for p in ports]
    labels = sorted({i for p, i in zip(ports, assigned, strict=True) if i < p.candidate_count})
    columns = np.array(sorted({0, 1, 2, 3, 4, *(5+i for i in labels),
                               *map(int, np.flatnonzero(state))}))
    precision = np.r_[0., 0., 1., np.full(len(state)-3, 4.)]
    information = np.diag(precision[columns])
    rhs = -precision[columns]*state[columns]
    parts = np.zeros((len(labels), len(columns), len(columns)))
    scores = np.zeros((len(labels), len(columns)))
    members = [[] for _ in labels]
    for j, (port, index) in enumerate(zip(ports, assigned, strict=True)):
        if index == port.candidate_count:
            continue
        group = labels.index(index)
        p = port.predict_selected(state, index)
        assert p.eligible
        residual, jacobian = port.observation-p.mean, p.jacobian[:, columns]
        solved = np.linalg.solve(p.covariance, residual)
        weight = (4+len(residual))/(4+float(residual@solved))
        parts[group] += weight*jacobian.T@np.linalg.solve(p.covariance, jacobian)
        scores[group] += weight*jacobian.T@solved
        members[group].append(j)
    information += parts.sum(axis=0)
    rhs += scores.sum(axis=0)
    deletions = group_deletion_steps(information, rhs, parts, scores)
    rows = []
    for index, tracks, deletion in zip(labels, members, deletions, strict=True):
        step = deletion.step
        rows.append(dict(candidate_index=index, norad_id=str(scan.bank.norad_ids[index]),
                         track_indices=tracks, track_count=len(tracks), reason=deletion.reason,
                         position_step_km=step[:2].tolist() if step is not None else None,
                         position_step_m=float(1000*np.linalg.norm(step[:2]))
                         if step is not None else None))
    valid = [r for r in rows if r['position_step_m'] is not None]
    largest = max(valid, key=lambda r: r['position_step_m']) if valid else None
    result = dict(unit=args.unit, parent_sha256=digest(path), source_sha256=digest(__file__),
                  kernel_sha256=digest(HERE.parents[1]/'src/leo/analysis/localization_influence.py'),
                  group_count=len(rows), invalid_deletions=len(rows)-len(valid), groups=rows,
                  largest_candidate_index=largest['candidate_index'] if largest else None,
                  maximum_predicted_shift_m=largest['position_step_m'] if largest else None,
                  quadratic_seconds=time.monotonic()-start,
                  qualification='Fixed-state IRLS deletion approximation; no GPS read. '
                  'Groups are inferred assignments, not verified satellite identities. '
                  'Optional warm refit is diagnostic only, not independent scan performance.')
    if args.refit_largest and largest:
        drop = set(largest['track_indices'])
        keep = [j for j in range(len(ports)) if j not in drop]
        fit = fit_localization_fast(
            state, [ports[j] for j in keep], precision,
            lambda s: np.linalg.norm(s[:2]) <= 250., max_iterations=64,
            deadline=start+25., degrees_of_freedom=4.)
        delta = fit.mean[:2]-state[:2]
        result['refit'] = dict(
            selection='largest predicted position shift, without reference',
            dropped_candidate_index=largest['candidate_index'], dropped_tracks=sorted(drop),
            retained_track_count=len(keep), converged=fit.converged, reason=fit.reason,
            iterations=fit.iterations, mean=fit.mean.tolist(), objectives=list(fit.objectives),
            observed_shift_m=float(1000*np.linalg.norm(delta)),
            observed_step_km=delta.tolist(), prediction_difference_m=float(1000*np.linalg.norm(
                delta-np.asarray(largest['position_step_km']))),
            remaining_assignment_changes=sum(fit.associations[k] != assigned[j]
                                             for k, j in enumerate(keep)))
    result['seconds'] = time.monotonic()-start
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    args.output.with_suffix('.sha256').write_text(digest(args.output)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('groups', 'refit')}))
    if 'refit' in result:
        print(json.dumps({k: v for k, v in result['refit'].items()
                          if k not in ('mean', 'objectives')}))


if __name__ == '__main__':
    main()
