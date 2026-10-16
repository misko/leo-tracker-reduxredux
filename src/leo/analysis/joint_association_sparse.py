"""Equivalent joint objective predicting only available native branch windows."""

import numpy as np

from leo.analysis import joint_association_score as dense_score
from leo.analysis.joint_association_score import JointAssociationObjective
from leo.contracts.regional_position import PositionObservations


class SparseNativeJointObjective(JointAssociationObjective):
    """One orbit call over the native inventory, rather than all padded slots."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        rows, slots = np.nonzero(self.branches.available)
        self.native_rows, self.native_slots = rows, slots
        obs = self.observations
        times = np.column_stack([o.times_s for o in self.branch_observations])[rows, slots]
        self.native_observations = PositionObservations(
            tuple(self.branches.candidate_ids[i][j] for i, j in zip(rows, slots, strict=True)),
            times,
            self.branches.cfo_hz[rows, slots],
            obs.rf_hz[rows],
            obs.receiver[rows],
            obs.channel[rows],
            obs.margin[rows],
        )
        self.native_design = self.branch_design.transpose(0, 2, 1)[rows, slots]

    def evaluate(self, vector):
        vector = np.asarray(vector, float)
        if vector.shape != (self.size,) or not np.isfinite(vector).all():
            raise ValueError("invalid sparse joint position vector")
        relative = self.basis @ vector[8:]
        values = dense_score.predict_orbits(
            self.bank, self.native_observations, self.prior, vector[:2], vector[7] + relative
        )
        native_prediction, native_visible, spatial, timing = values
        native_prediction += (self.native_design @ vector[2:7] + self.baseline[self.native_rows])[
            :, None
        ]
        shape = (
            len(self.observations.times_s),
            len(self.bank.numbers),
            self.branches.cfo_hz.shape[1],
        )
        prediction, visible = np.zeros(shape), np.zeros(shape, bool)
        prediction[self.native_rows, :, self.native_slots] = native_prediction
        visible[self.native_rows, :, self.native_slots] = native_visible
        terms, dense_weight = self.likelihood(prediction, visible)
        weight = dense_weight[self.native_rows, :, self.native_slots]
        shift_gradient = np.sum(weight * timing, axis=0)
        gradient = np.zeros(self.size)
        gradient[:2] = np.einsum("mk,mki->i", weight, spatial)
        gradient[2:7] = self.native_design.T @ weight.sum(axis=1)
        gradient[7] = shift_gradient.sum() + vector[7] / self.score.common_sigma_s**2
        gradient[8:] = self.basis.T @ (shift_gradient + relative / self.score.relative_sigma_s**2)
        penalty = 0.5 * (vector[7] / self.score.common_sigma_s) ** 2
        penalty += 0.5 * np.sum((relative / self.score.relative_sigma_s) ** 2)
        return terms.nll + float(penalty), gradient, terms
