"""Fixed geometry-overlap prior layered onto the existing research slope model."""

import sys
from pathlib import Path

import numpy as np
from position_overlap import coupling, precision

REPORTS = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPORTS / f"2026_10_08_position_error_iter{n}")
                for n in ("27", "24", "19", "04", "10")]
from slope_prior import SlopePrior  # noqa: E402

from leo.analysis.hard60_score import predict_orbits  # noqa: E402


class PositionProtectedSlope(SlopePrior):
    def __init__(self, base, nodes, knots, centers_s, shared_seed, shared_clock, *,
                 wide_sigma=0.5, protected_sigma=0.25):
        super().__init__(base, nodes, knots, centers_s, wide_sigma)
        vector = np.asarray(shared_seed, dtype=float)
        clock = np.asarray(shared_clock, dtype=float)
        if vector.shape != (self.size,) or clock.shape != self.initial_clock.shape:
            raise ValueError("One shared complete seed in this slope model's coordinates required")
        _, _, _, terms = self.evaluate_joint(vector, clock)
        _, _, spatial, _ = predict_orbits(
            self.bank, self.observations, self.prior, vector[:2],
            vector[7] + self.basis @ vector[8:],
        )
        cross = coupling(terms.responsibilities, spatial, self.observations.times_s,
                         self.centers_s, self.satellite_basis)
        geometry = precision(cross, wide_sigma=wide_sigma, protected_sigma=protected_sigma)
        self.precision[self.slope_slice, self.slope_slice] = geometry["precision"]
        self.geometry_diagnostics = dict(
            rank=geometry["rank"], singular_values=geometry["singular_values"].tolist(),
            projector=geometry["projector"].tolist(), cross_information=cross.tolist(),
            wide_sigma_hz_s=wide_sigma, protected_sigma_hz_s=protected_sigma,
            scope="Fixed at shared hypothesis seed; no reference-position input",
        )
