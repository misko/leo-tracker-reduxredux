"""Build an exact regional likelihood layout once its aliases are explicit."""

from contextlib import contextmanager
from hashlib import sha256
from inspect import getsource
from time import process_time_ns
from types import FunctionType, SimpleNamespace
from unittest.mock import patch

import numpy as np

from leo.analysis.localization_v3 import marginal
from leo.analysis.localization_v3.families import AnchoredFamilies, FixedFamilies
from leo.analysis.localization_v3.scan import ScanLikelihood


MARGINAL_SHA256 = "f31930912a32318dfe38741033c4ecc3e5d38ac0ecd8f000bb821728edafdebd"
LAYOUT_SHA256 = "6845b4c2b5874b4a8c2ccec84f1289da4fe50dce393c215750790c79cffc2d1c"
ANCHORED_SHA256 = "b341832e154363e8dae05e151c061a9c999a525319879abed21a61033cf978b1"


def fixed_layout(scan, seed):
    """Preserve the layout prefix of FixedFamilies in its original row order."""
    rows = [row for row in seed["rows"] if row["active_curvature"]]
    track_indices = {track["key"]: i for i, track in enumerate(scan.tracks)}
    members = [track_indices[row["component"]] for row in rows]
    assert set(members) == set(scan.curved)
    labels = sorted({row["candidate_index"] for row in rows})
    local_j = {label: k for k, label in enumerate(labels)}
    counts = np.array([len(scan.tracks[i]["times"]) for i in members])
    boundaries = np.r_[0, np.cumsum(counts)]
    slices = [slice(a, b) for a, b in zip(boundaries[:-1], boundaries[1:], strict=True)]
    flat_times = np.concatenate([scan.tracks[i]["times"] for i in members])
    flat_labels = np.repeat([local_j[row["candidate_index"]] for row in rows], counts)
    sky = dict(time_s=scan.sky["time_s"], position_km=scan.sky["position_km"][labels].copy(),
               velocity_km_s=scan.sky["velocity_km_s"][labels].copy())
    return SimpleNamespace(rows=rows, members=members, labels=labels, local_j=local_j, slices=slices,
                           flat_times=flat_times, flat_labels=flat_labels, sky=sky)


def valid_seed(scan, seed, layout):
    """Keep the original constructor for unusual seeds or unsupported phase times."""
    state = seed["state"]
    beta, smooth, phase = (np.asarray(state[k]) for k in ("beta", "smooth", "phases"))
    if (scan.search_region is None or beta.shape not in ((8,), (9,))
            or smooth.shape != (2, scan.rx_basis[0].shape[1]) or phase.shape != (len(scan.norads),)
            or state["extra"] or any(a.dtype.kind not in "fiu" or not np.isfinite(a).all()
                                     for a in (beta, smooth, phase))):
        return False
    times = layout.flat_times
    knots = layout.sky["time_s"]
    queries = times + np.clip(phase[layout.labels], -15, 15)[layout.flat_labels]
    return bool(np.isfinite(times).all() and np.all((knots[0] <= queries) & (queries <= knots[-1])))


def fast_init(stock, counts):
    if (sha256(getsource(stock).encode()).hexdigest() != MARGINAL_SHA256
            or sha256(getsource(FixedFamilies.__init__).encode()).hexdigest() != LAYOUT_SHA256
            or sha256(getsource(AnchoredFamilies.__init__).encode()).hexdigest() != ANCHORED_SHA256
            or stock.__globals__["AnchoredFamilies"] is not AnchoredFamilies):
        raise ValueError("The fixed-alias overlay requires the reviewed layout and marginal constructor")
    original_layout = stock.__globals__["AnchoredFamilies"]

    def explicit_layout(scan, seed, method, fitted_c, anchor):
        try:
            layout = fixed_layout(scan, seed)
            if valid_seed(scan, seed, layout):
                counts["direct_layouts"] += 1
                return layout
        except (KeyError, IndexError, TypeError, ValueError):
            pass
        counts["layout_fallbacks"] += 1
        return original_layout(scan, seed, method, fitted_c, anchor)

    # Only the private layout constructor changes; keep the original joint
    # design, retained aliases, priors, mode bank and nuisance calculation.
    namespace = dict(stock.__globals__, AnchoredFamilies=explicit_layout)
    operation = FunctionType(stock.__code__, namespace, argdefs=stock.__defaults__)
    operation.__kwdefaults__ = stock.__kwdefaults__
    return operation


@contextmanager
def measured_fixed_alias_layout(*, enabled):
    stock = marginal.JointMarginal.__init__
    counts = dict(calls=0, explicit_aliases=0, direct_layouts=0, layout_fallbacks=0,
                  constructor_cpu_ns=0, eligible_cpu_ns=0)
    direct = fast_init(stock, counts) if enabled else stock

    def construct(self, scan, seed, fitted_c, *, variant, sigma=150., reference=None, aliases=None):
        start = process_time_ns()
        eligible = aliases is not None and variant == "radio_noise" and type(scan) is ScanLikelihood
        counts["calls"] += 1
        counts["explicit_aliases"] += int(eligible)
        try:
            operation = direct if eligible else stock
            return operation(self, scan, seed, fitted_c, variant=variant, sigma=sigma,
                             reference=reference, aliases=aliases)
        finally:
            delta = process_time_ns() - start
            counts["constructor_cpu_ns"] += delta
            if eligible:
                counts["eligible_cpu_ns"] += delta

    with patch.object(marginal.JointMarginal, "__init__", construct):
        yield counts
