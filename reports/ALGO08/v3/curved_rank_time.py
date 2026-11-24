"""Limit the original compact catalogue rank to the times that it consumes."""

from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import numpy as np


SOURCE_PINS = {
    "scan.py": "49f1f2e9d73b967f694e48033b6d02ea2e1d66285f7941c4f282f5b238e79f89",
    "discovery.py": "7ca045c3809c8da7b57268b9d9bcc4b8a49366e88376250d0b11227ce6d7e26a",
    "v5_core.py": "30e6f22ab4b49d03cf8536645cbdebb8fec2afa513f3cfa4a9f3163590a84407",
    "orbit_projector.py": "873b856dd081269234f9af8415e7c1abaa00afb27c991dad43ab24e0764dd668",
    "algo08_sparse_rank_projection.py": "e381e0807e47a10091ffd9c9d1d8c0d43aa531a5e4c81acda53ddbfa922ef021",
    "catalogue_block_rank.py": "961bce0676c4cf55da4e72a417f0120aba398d48c4389b905aa3655f0d0f3311",
    "catalogue_block_bound.py": "757ddbd34b1c933d062d7e1613c5f039c6bb18bf13914b6d09ab51d2578fbe33",
    "exact_named_route.py": "8799f632207d4a1b65954e454766605dcad109a799b9b81a08158c3a2ebc26ff",
}


class AllTrackRequest(Exception):
    """The scoped caller consumed a noncurved track's projection index."""


class CurvedIndexes(list):
    def __init__(self, indexes, curved):
        super().__init__(indexes)
        self.curved = frozenset(curved)

    def __getitem__(self, track):
        if track not in self.curved:
            raise AllTrackRequest
        return super().__getitem__(track)


def time_union(times, indexes, curved):
    """Keep extrema for the original shifted interpolation range checks."""
    used = np.zeros(len(times), dtype=bool)
    if len(times) and len(curved):
        used[[0, -1]] = True
        for row in curved:
            used[indexes[row]] = True
    return np.flatnonzero(used)


def above_observer(positions):
    """Prove discarded native interpolations cannot produce a bad ECEF range."""
    # A segment cannot move farther than its chord from its first knot.
    # The 6,500 km bound covers all surface observers with generous rounding
    # margin after the kernel's binary64 interpolation and Earth rotation.
    if positions.ndim != 3 or positions.shape[1] < 2 or positions.shape[2] != 3:
        return False
    norms = np.einsum("...d,...d->...", positions, positions)
    chord = np.diff(positions, axis=1)
    steps = np.einsum("...d,...d->...", chord, chord)
    low, high, step = norms.min(), norms.max(), steps.max()
    return bool(0 < low <= high < 1e12 and np.sqrt(low) - np.sqrt(step) > 6500)


def compact_view(scan, kernel, stencil_class, audit):
    if (type(scan) is not kernel.ScanLikelihood or type(scan.geometry) is not stencil_class
            or any(name in vars(scan) for name in ("association", "predictions", "curve"))):
        audit["unsupported_scan"] += 1
        return None
    shifted = vars(scan).get("shifted")
    if shifted is not None and (getattr(shifted, "__qualname__", None) != "sparse_rank_projection.<locals>.shifted"
                                or sha256(Path(shifted.__code__.co_filename).read_bytes()).hexdigest()
                                != SOURCE_PINS["algo08_sparse_rank_projection.py"]):
        audit["unsupported_scan"] += 1
        return None
    stencil = scan.geometry
    times = scan.times
    if (not len(scan.curved) or not len(stencil.positions)
            or stencil.index.shape != (1, 3, len(times))
            or stencil.fraction.shape != stencil.index.shape):
        audit["unsupported_geometry"] += 1
        return None
    columns = time_union(times, scan.index, scan.curved)
    audit["admitted_epoch_counts"].append([len(times), len(columns)])
    if len(columns) == len(times):
        audit["full_union"] += 1
        return None
    # The exact block scorer tests the entire original nominal Doppler plane
    # for finite values within 1 MHz. Convex interpolation of velocity knots
    # with norms below 25 km/s implies less than 960 kHz at 11.5 GHz.
    speeds2 = np.einsum("...d,...d->...", stencil.velocities, stencil.velocities)
    if (not np.array_equal(stencil.positions, scan.sky["position_km"])
            or not np.array_equal(stencil.velocities, scan.sky["velocity_km_s"])
            or not np.max(speeds2) < 25.**2 or not above_observer(stencil.positions)):
        audit["unproved_projection_domain"] += 1
        return None
    mapped = np.full(len(times), -1, dtype=np.intp)
    mapped[columns] = np.arange(len(columns))
    indexes = list(scan.index)
    for i in scan.curved:
        indexes[i] = mapped[indexes[i]]
    geometry = replace(stencil, index=np.ascontiguousarray(stencil.index[..., columns]),
                       fraction=np.ascontiguousarray(stencil.fraction[..., columns]))
    geometry.index.setflags(write=False)
    geometry.fraction.setflags(write=False)
    audit["compact_ranks"] += 1
    return dict(times=times[columns], index=CurvedIndexes(indexes, scan.curved), geometry=geometry,
                reference=scan.reference.copy(), element_derivatives=scan.element_derivatives.copy())


def narrow_rank(original, kernel, stencil_class, audit):
    def rank(scan):
        view = compact_view(scan, kernel, stencil_class, audit)
        if view is not None:
            try:
                with patch.multiple(scan, **view):
                    return original(scan)
            except AllTrackRequest:
                audit["all_track_fallbacks"] += 1
        return original(scan)

    return rank


@contextmanager
def projected_ranking(audit):
    """Opt in around original exact ports; leave final scan and named fallback intact."""
    import exact_named_route as entry
    import catalogue_block_bound, catalogue_block_rank
    from leo.analysis.localization_v3 import discovery, scan
    from tools.pipeline_eval.variants import algo08_sparse_rank_projection, orbit_projector, v5_core

    modules = (scan, discovery, orbit_projector, v5_core, algo08_sparse_rank_projection,
               catalogue_block_bound, catalogue_block_rank, entry)
    if any(sha256(Path(m.__file__).read_bytes()).hexdigest()
           != SOURCE_PINS[Path(m.__file__).name] for m in modules):
        audit["unsupported_sources"] += 1
        yield
        return
    original = entry.rank_with_exact_inputs

    def bind(*args, **kwargs):
        return narrow_rank(original(*args, **kwargs), scan, orbit_projector.Stencil, audit)

    with patch.object(entry, "rank_with_exact_inputs", bind):
        yield
