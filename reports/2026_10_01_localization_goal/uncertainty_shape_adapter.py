"""Combine the frozen local-curvature and deletion-shape calculations."""
import numpy as np

from leo.analysis.localization_deletion_spread import deletion_spread
from leo.analysis.localization_influence import group_deletion_steps
from leo.analysis.localization_uncertainty import profiled_position_covariance


def build_shapes(ports, state):
    state = np.asarray(state, dtype=float)
    assigned = [int(np.argmax(p.score_all(state))) for p in ports]
    labels = sorted({i for p, i in zip(ports, assigned, strict=True) if i < p.candidate_count})
    columns = np.array(sorted({0, 1, 2, 3, 4, *(5+i for i in labels),
                               *map(int, np.flatnonzero(state))}))
    precision = np.r_[0., 0., 1., np.full(len(state)-3, 4.)]
    information = np.diag(precision[columns])
    rhs = -precision[columns]*state[columns]
    parts = np.zeros((len(labels), len(columns), len(columns)))
    scores = np.zeros((len(labels), len(columns)))
    for port, index in zip(ports, assigned, strict=True):
        if index == port.candidate_count:
            continue
        group = labels.index(index)
        p = port.predict_selected(state, index)
        if not p.eligible:
            raise ValueError('ineligible fixed assignment')
        residual, jacobian = port.observation-p.mean, p.jacobian[:, columns]
        solved = np.linalg.solve(p.covariance, residual)
        weight = (4+len(residual))/(4+float(residual@solved))
        parts[group] += weight*jacobian.T@np.linalg.solve(p.covariance, jacobian)
        scores[group] += weight*jacobian.T@solved
    information += parts.sum(axis=0)
    rhs += scores.sum(axis=0)
    curvature = profiled_position_covariance(information)
    deletions = group_deletion_steps(information, rhs, parts, scores)
    if any(d.step is None for d in deletions):
        raise ValueError('unidentified group deletion; no covariance fallback')
    shifts = np.array([d.step[:2] for d in deletions])
    spread = deletion_spread(shifts)
    matrices = dict(curvature=curvature, deletion=spread, sum=curvature+spread)
    for matrix in matrices.values():
        np.linalg.cholesky(matrix)
    return matrices, labels, shifts
