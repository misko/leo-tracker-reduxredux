"""Withhold when excluding a nominated family would remove every calibration row."""

from unittest.mock import patch

import numpy as np


class NoIndependentFamilyCalibration(Exception):
    """Raised before a family-excluded fit with no independent observations."""


def exclusion_witness(context):
    base = context["base"]
    keep = context["keep"]
    if keep.dtype != np.bool_ or keep.ndim != 1 or keep.shape != base.values.shape:
        return None
    target = None
    target_slices = []
    for row, sl in zip(base.rows, base.slices, strict=True):
        if keep[sl].any():
            family = row["candidate_index"]
            if target is not None and family != target:
                return None
            target = family
            target_slices.append(sl)
    if target is None:
        return None
    remaining = keep.copy()
    for sl in target_slices:
        remaining[sl] = False
    if remaining.any():
        return None
    return dict(candidate_index=int(target), retained_rows=int(keep.sum()),
                contributing_tracks=len(target_slices), independent_rows=0)


def guarded_inference(infer, prepared, *args, **options):
    from leo.analysis.localization_v3 import family_cavity

    original = family_cavity.nominate_families

    def nominate(context):
        proof = exclusion_witness(context)
        if proof is not None:
            raise NoIndependentFamilyCalibration(proof)
        return original(context)

    with patch.object(family_cavity, "nominate_families", nominate):
        try:
            return infer(prepared, *args, **options)
        except NoIndependentFamilyCalibration as exc:
            return dict(status="withheld", reason="no_independent_family_calibration",
                        arms={arm: {"latlon": None} for arm in ("c0", "fitted_c")},
                        metrics=dict(family_exclusion=exc.args[0]))
