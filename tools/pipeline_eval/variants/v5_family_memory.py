"""Use the three causal alignment samples directly in full-family confidence."""

import hashlib
from contextlib import contextmanager
from types import FunctionType
from unittest.mock import patch

import numpy as np

METHOD = "v5_family_memory"
BOUNDARY = "Composed compact v5 with sampled causal priors for family confidence"


def alignment_only(scan, labels):
    """Return the alignment inventory consumed by the frozen phase-width function."""
    from leo.analysis.localization_v3 import orbit_modes as original

    if scan.previous_tle is None or scan.previous_tle_sha256 is None:
        raise ValueError("Explicit previous causal TLE text and hash required")
    if hashlib.sha256(scan.previous_tle.encode()).hexdigest() != scan.previous_tle_sha256:
        raise ValueError("previous causal TLE bytes differ from the original prior receipt")
    key = tuple(labels)
    if key in getattr(scan, "previous_shape_cache", {}):
        return scan.previous_shape_cache[key]
    old = original.parse_element_sets(scan.previous_tle)
    lookup = dict(zip(old.satellite_numbers, old.satellites, strict=True))
    available = [k for k, j in enumerate(labels) if int(scan.norads[j]) in lookup]
    if not available:
        return None, set(), {}
    numbers = [int(scan.norads[labels[k]]) for k in available]
    catalogue = original.ElementSetCatalogue(
        tuple(map(str, numbers)), tuple(numbers), tuple(lookup[n] for n in numbers)
    )
    current = (
        scan.sky
        if key == tuple(range(len(scan.norads)))
        else dict(
            time_s=scan.sky["time_s"],
            position_km=scan.sky["position_km"][labels],
            velocity_km_s=scan.sky["velocity_km_s"][labels],
        )
    )
    sample = np.array([0.0, 150.0, 300.0])
    po, _, good = original.ecef_states(catalogue, scan.origin_utc_ns, sample)
    assert good.all()
    pn, vn = original.phase_shifted_states(current, sample, 0)
    pn, vn = pn[available], vn[available]
    vi = vn.copy()
    vi[..., 0] -= original.EARTH_ROTATION_RAD_S * pn[..., 1]
    vi[..., 1] += original.EARTH_ROTATION_RAD_S * pn[..., 0]
    phase = np.median(np.sum((po - pn) * vi, axis=2) / np.sum(vi**2, axis=2), axis=1)
    return None, set(available), dict(zip(numbers, map(float, phase), strict=True))


def width_reader(function):
    """Give only the reviewed phase-width function the sample-only implementation."""
    return FunctionType(function.__code__, dict(function.__globals__, previous_bank=alignment_only))


@contextmanager
def family_widths_context():
    """Replace only the all-catalogue width lookup inside family confidence."""
    from leo.analysis.localization_v3 import family_weighting, history_policy

    stock = history_policy.confidence_for

    def confidence(*args, **kwargs):
        with patch.object(
            family_weighting, "phase_widths", width_reader(family_weighting.phase_widths)
        ):
            return stock(*args, **kwargs)

    with patch.object(history_policy, "confidence_for", confidence):
        yield
