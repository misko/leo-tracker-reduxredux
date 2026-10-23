"""Integrate causal orbit uncertainty even for a single observed RX/channel.

The prior comes from causal orbital evidence, independently of how many radio
owners detected a candidate. Existing ownership gates still govern acceptance.
"""

from build_dsx01_orbit_modes import build_modes
from dsx01_robust_joint import RobustJoint
from dsx01_structured_joint import StructuredJoint, eccentricity_bank
from dsx01_window_noise import WindowNoise

VARIANTS = ("all_3", "all_5", "all_3_window")


def expand_uncertainty(problem, *, eccentric=False):
    p = problem
    previous = tuple(p.supported)
    p.supported = list(p.labels)
    p.supported_local = list(range(len(p.labels)))
    p.mode_bank, p.mode_metadata = build_modes(p.scan, p.labels, p.supported, "physical")
    if eccentric:
        p.ecc_bank, p.ecc_metadata = eccentricity_bank(p.scan, p.labels, p.supported)
    p.single_owner_uncertainty_labels = tuple(j for j in p.labels if j not in previous)
    return p


def all_candidate_problem(scan, seed, fitted_c, *, variant, **kwargs):
    if variant not in VARIANTS:
        raise ValueError("unknown all-candidate uncertainty hypothesis")
    cls, configuration = (
        (WindowNoise, "window_noise")
        if variant == "all_3_window"
        else (StructuredJoint, "eccentric")
        if variant == "all_5"
        else (RobustJoint, "robust")
    )
    p = cls(scan, seed, fitted_c, variant=configuration, **kwargs)
    return expand_uncertainty(p, eccentric=variant == "all_5")
