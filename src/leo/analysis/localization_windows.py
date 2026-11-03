"""Shared-position windows over independent scan nuisance blocks.

Local ports own time origins and satellite catalogues. This adapter changes only
coordinate indexing; no observation times, physical IDs or scores are rewritten.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from leo.analysis.gaussian_sum_location import Prediction
from leo.analysis.localization_evaluation import LocalizationTrackPort


def independent_scan_columns(candidate_counts: Sequence[int]) -> tuple[np.ndarray, ...]:
    """Local [E,N,clock,drift0,drift1,epochs...] to shared-position state."""
    if not candidate_counts or any(not isinstance(n, (int, np.integer)) or n < 1 for n in candidate_counts):
        raise ValueError('each scan needs a nonempty satellite catalogue')
    result = []
    offset = 2
    for count in candidate_counts:
        result.append(np.r_[0, 1, np.arange(offset, offset+3+count)])
        offset += 3+count
    return tuple(result)


def independent_scan_precision(candidate_counts: Sequence[int]) -> np.ndarray:
    """One flat position prior; each scan has 1 s clock and 0.5 nuisance sigma."""
    columns = independent_scan_columns(candidate_counts)
    precision = np.zeros(2+sum(3+n for n in candidate_counts))
    for indices in columns:
        precision[indices[2]] = 1.
        precision[indices[3:]] = 4.
    return precision


@dataclass(frozen=True)
class WindowTrackPort:
    """Lift a scan port to a larger state without altering its likelihood."""

    local: LocalizationTrackPort
    columns: np.ndarray
    dimension: int

    def __post_init__(self):
        columns = np.array(self.columns, copy=True)
        if (columns.ndim != 1 or columns.dtype.kind not in 'iu'
                or len(columns) != 5+self.local.candidate_count
                or not np.array_equal(columns[:2], [0, 1])
                or len(set(columns.tolist())) != len(columns)
                or np.any(columns < 0) or np.any(columns >= self.dimension)):
            raise ValueError('invalid local-to-window columns')
        columns.setflags(write=False)
        object.__setattr__(self, 'columns', columns)

    @property
    def observation_ids(self):
        return self.local.observation_ids

    @property
    def observation(self):
        return self.local.observation

    @property
    def candidate_count(self):
        return self.local.candidate_count

    @property
    def priors_piecewise_constant(self):
        return self.local.priors_piecewise_constant

    def _state(self, state):
        state = np.asarray(state, dtype=float)
        if state.shape != (self.dimension,) or not np.all(np.isfinite(state)):
            raise ValueError('invalid window state')
        return state[self.columns]

    def score_all(self, state):
        return self.local.score_all(self._state(state))

    def score_selected(self, state, index):
        return self.local.score_selected(self._state(state), index)

    def predict_selected(self, state, index):
        prediction = self.local.predict_selected(self._state(state), index)
        jacobian = np.zeros((len(self.observation), self.dimension))
        jacobian[:, self.columns] = prediction.jacobian
        return Prediction(prediction.mean, jacobian, prediction.covariance, prediction.eligible)
