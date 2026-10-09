"""Research-only frozen RX-by-satellite prediction correction around B7."""

import numpy as np

from leo.analysis.hard60_dynamic_rf import fit  # unchanged existing B7 fitter
from leo.analysis.hard60_score import likelihood, predict_orbits


class FixedReceiverContrast:
    """Reuse every B7 parameter, constraint and prior; add no fitted dimensions.

    Contrasts must be frozen from one globally specified fitted-derived smooth-
    projected diagnostic and shared across both c arms. This wrapper does not
    select or estimate them, and contains no reference-position inputs.
    """

    def __init__(self, base, satellite_ids, contrasts_hz):
        ids = np.asarray(satellite_ids)
        values = np.asarray(contrasts_hz, dtype=float)
        if (
            ids.ndim != 1
            or values.shape != ids.shape
            or not np.isfinite(ids).all()
            or not np.isfinite(values).all()
            or np.any(ids != np.floor(ids))
            or np.any(ids <= 0)
            or len(set(ids.tolist())) != len(ids)
        ):
            raise ValueError("Unique positive satellite IDs and finite aligned contrasts required")
        lookup = {int(number): i for i, number in enumerate(base.bank.numbers)}
        if any(int(number) not in lookup for number in ids):
            raise ValueError("Contrast satellite outside the frozen B7 candidate bank")
        if not np.isclose(values.sum(), 0, atol=1e-9, rtol=0):
            raise ValueError("Frozen satellite contrasts must have zero sum")
        self.base = base
        self.contrasts_hz = np.zeros(len(base.bank.numbers))
        for number, value in zip(ids, values, strict=True):
            self.contrasts_hz[lookup[int(number)]] = value
        self.contrasts_hz.setflags(write=False)
        receiver = np.asarray(base.observations.receiver, dtype=float)
        if (
            receiver.shape != (len(base.observations.times_s),)
            or not np.isin(receiver, [0, 1]).all()
        ):
            raise ValueError("Receiver observations must be RX0 or RX1")
        self.receiver_sign = 2 * receiver - 1
        self.receiver_sign.setflags(write=False)

    def __getattr__(self, name):
        return getattr(self.base, name)

    def evaluate_joint(self, vector, clock):
        # Keep exact zero control on the production evaluation path.
        if not np.any(self.contrasts_hz):
            return self.base.evaluate_joint(vector, clock)
        relative = self.basis @ vector[8:]
        prediction, visible, spatial, timing = predict_orbits(
            self.bank, self.observations, self.prior, vector[:2], vector[7] + relative
        )
        prediction += (self.design @ vector[2:7] + self.baseline + self.clock_design @ clock)[
            :, None
        ]
        offsets, slopes = self.physical_corrections(clock)
        prediction += offsets[None, :] + self.delta_time * (100 * slopes)[None, :]
        prediction += self.receiver_sign[:, None] * self.contrasts_hz[None, :] / 2
        terms = likelihood(self.observations.measured_hz, prediction, visible, self.score)
        weight = terms.prediction_gradient
        shift = np.sum(weight * timing, axis=0)
        gradient = np.zeros(self.size)
        gradient[:2] = np.einsum("nk,nki->i", weight, spatial)
        gradient[2:7] = self.design.T @ weight.sum(axis=1)
        gradient[7] = shift.sum() + vector[7] / self.score.common_sigma_s**2
        gradient[8:] = self.basis.T @ (shift + relative / self.score.relative_sigma_s**2)
        nuisance = self.clock_design.T @ weight.sum(axis=1) + self.precision @ clock
        if self.offset_slice.stop > self.offset_slice.start:
            nuisance[self.offset_slice] += self.satellite_basis.T @ weight.sum(axis=0)
        if self.slope_slice.stop > self.slope_slice.start:
            nuisance[self.slope_slice] += self.satellite_basis.T @ (weight * self.delta_time).sum(
                axis=0
            )
        penalty = 0.5 * (vector[7] / self.score.common_sigma_s) ** 2
        penalty += 0.5 * np.sum((relative / self.score.relative_sigma_s) ** 2)
        penalty += 0.5 * clock @ self.precision @ clock
        return terms.nll + penalty, gradient, nuisance, terms


__all__ = ["FixedReceiverContrast", "fit"]
