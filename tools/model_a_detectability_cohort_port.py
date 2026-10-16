"""The existing A q families on exact full-derived observation masks."""

import model_a_path_detectability as original
import numpy as np

VIEWS = ("all", "low", "high")


def mask_for(model, view):
    channels = np.asarray(model.observations.channel)
    if view not in VIEWS:
        raise ValueError("Declared all/CH1-4/CH5-8 view required")
    mask = (
        np.ones(len(channels), bool)
        if view == "all"
        else (channels <= 4 if view == "low" else channels >= 5)
    )
    if not mask.any():
        raise ValueError("Empty view is unavailable, not an inherited estimate")
    return mask


class ViewModel(original.PathModel):
    """Retain full frame, fraction, bounds and priors while masking measured rows.

    These are conditional views. This constructor does not claim independent
    half-only discovery, preprocessing or calibration initialization.
    """

    def __init__(self, raw, shift, family, view, *, width=1e-5):
        if raw.group_count or family not in ("shared", "contrast"):
            raise ValueError("Exact frozen-contrast A q family required")
        mask = mask_for(raw, view)
        self.model = (
            original.band.smooth.SmoothVisibilityModel(raw, mask, width=width)
            if family == "shared"
            else original.band.BandDetectabilityModel(raw, mask, width=width)
        )
        self.observation_family, self.conditional_view = family, view
        delta = np.asarray(shift.offsets_hz, float)
        self.fixed_contrast_prior_penalty = 0.5 * float(delta @ delta) / 50000.0**2


fit = original.fit
