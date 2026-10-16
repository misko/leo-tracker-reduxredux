"""Existing shared/band q models with a source path's frozen contrast prior."""

import model_a_band_detectability as band
import numpy as np


class PathModel:
    """Forward the original q metadata; add the frozen-shift prior once.

    ``original`` deliberately forwards to the q model's original GroupCalibration
    source. The band's fitter uses that identity to partition its non-diagonal q
    prior correctly; a wrapper must not replace it with the q model itself.
    """

    def __init__(self, original, shift, family, *, width=1e-5):
        if original.group_count or family not in ("shared", "contrast"):
            raise ValueError("Frozen-contrast A and declared shared/contrast family required")
        mask = np.ones(len(original.observations.times_s), bool)
        self.model = (
            band.smooth.SmoothVisibilityModel(original, mask, width=width)
            if family == "shared"
            else band.BandDetectabilityModel(original, mask, width=width)
        )
        self.observation_family = family
        self.fixed_contrast_prior_penalty = (
            0.5 * float(np.asarray(shift.offsets_hz) @ np.asarray(shift.offsets_hz)) / 50000.0**2
        )

    def __getattr__(self, name):
        return getattr(self.model, name)

    def evaluate_details(self, vector, nuisance):
        e, details = self.model.evaluate_details(vector, nuisance)
        details = dict(
            details,
            fixed_contrast_prior=self.fixed_contrast_prior_penalty,
            prior_penalty=details["prior_penalty"] + self.fixed_contrast_prior_penalty,
        )
        return (e[0] + self.fixed_contrast_prior_penalty, *e[1:]), details

    def evaluate_joint(self, vector, nuisance):
        return self.evaluate_details(vector, nuisance)[0]


def fit(model, vector, nuisance, **options):
    """Explicit scientific dispatch, including wrappers/counters; no rebuilding."""
    api = band.fit if model.observation_family == "contrast" else band.smooth.port.fit
    result = api(model, vector, nuisance, **options)
    result["fixed_contrast_prior_penalty"] = model.fixed_contrast_prior_penalty
    return result
