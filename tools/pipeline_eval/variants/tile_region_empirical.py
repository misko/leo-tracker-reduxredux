"""Estimate the local Doppler displacement information from development innovations."""

from collections import defaultdict
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.variants import tile_region_support as support

METHOD = "tile_region_empirical"
BOUNDARY = "Portable compact v5 after held region support with development-calibrated noise"
# The frozen compact-v5 likelihood rejects sub-40 Hz observation uncertainty.
MIN_DEVELOPMENT_SIGMA_HZ = 40.0


def orbit_scale(squares):
    count = len(squares)
    return max(
        MIN_DEVELOPMENT_SIGMA_HZ, float(np.median(np.sqrt(squares))) * np.sqrt(count / (count - 2))
    )


class CalibratedOrbitModel(support.FixedOrbitModel):
    def first_fit_scale(self, point):
        _, offset, phase = self.estimate(point, None)
        f, _, h = self.projector.evaluate(self.training_grid, *self.region.latlon(point))
        scaled = defaultdict(list)
        for (j, arc, weight), ix, bias in zip(self.arcs, self.train_index, offset, strict=True):
            residual = arc.train_y - (f[j, ix] + phase[j] * h[j, ix]) * arc.scale - bias
            scaled[j].append((weight, float(np.mean(residual**2))))
        squares = [
            np.average([z for _, z in rows], weights=[w for w, _ in rows])
            for rows in scaled.values()
        ]
        return orbit_scale(squares)

    def fit(self, start, lo, hi, omitted=None):
        result = super().fit(start, lo, hi, omitted)
        if not hasattr(self, "development_scale"):
            self.development_scale = self.first_fit_scale(result.x)
            # The phase prior rows retain their original precision.
            result.jac[: -len(self.orbits)] *= support.SIGMA / self.development_scale
        return result


def run(document, *, tile, archive, bound, library):
    fitted = []

    def model(*args):
        result = CalibratedOrbitModel(*args)
        fitted.append(result)
        return result

    with patch.object(support, "FixedOrbitModel", model):
        result = support.run(document, tile=tile, archive=archive, bound=bound, library=library)
    result["boundary"] = BOUNDARY
    if fitted:
        result["metrics"]["geographic_gate"]["development_uncertainty_sigma_hz"] = fitted[
            0
        ].development_scale
    return result
