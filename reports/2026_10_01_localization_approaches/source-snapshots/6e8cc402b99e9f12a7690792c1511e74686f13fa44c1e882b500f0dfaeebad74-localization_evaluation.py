"""Narrow evaluation ports for single-scan localization optimizers.

The protocol keeps evidence construction outside pure numerical solvers.  Branch
scores are normalized log joints in candidate order followed by background.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from leo.analysis.gaussian_sum_location import ObservationFactor, Prediction
from leo.analysis.greedy_joint_location import _selected_log

FloatArray = NDArray[np.float64]


@runtime_checkable
class LocalizationTrackPort(Protocol):
    """One physical track and all of its catalogue association branches."""

    observation_ids: tuple[str, ...]
    observation: FloatArray
    candidate_count: int
    priors_piecewise_constant: bool

    def score_all(self, state: FloatArray) -> FloatArray:
        """Return candidate then background normalized log-joint scores."""

    def score_selected(self, state: FloatArray, index: int) -> float:
        """Return one normalized log joint, including background."""

    def predict_selected(self, state: FloatArray, index: int) -> Prediction:
        """Return the selected satellite prediction and Jacobian.

        ``index`` is always less than :attr:`candidate_count`; background has no
        prediction and is never passed to this method.
        """


@dataclass(frozen=True)
class ObservationFactorTrackPort:
    """Compatibility adapter for the existing factor and all-branch scorer."""

    factor: ObservationFactor
    branch_scorer: Callable[[FloatArray], FloatArray]
    degrees_of_freedom: float | None = None
    priors_piecewise_constant: bool = False

    @property
    def observation_ids(self) -> tuple[str, ...]:
        return self.factor.observation_ids

    @property
    def observation(self) -> FloatArray:
        return self.factor.observation

    @property
    def candidate_count(self) -> int:
        return len(self.factor.candidates)

    def score_all(self, state: FloatArray) -> FloatArray:
        return np.asarray(self.branch_scorer(state), dtype=np.float64)

    def score_selected(self, state: FloatArray, index: int) -> float:
        if not 0 <= index <= self.candidate_count:
            raise IndexError("selected branch index is out of range")
        return _selected_log(self.factor, index, state, self.degrees_of_freedom)

    def predict_selected(self, state: FloatArray, index: int) -> Prediction:
        if not 0 <= index < self.candidate_count:
            raise IndexError("selected candidate index is out of range")
        return self.factor.candidates[index].predict(state)
