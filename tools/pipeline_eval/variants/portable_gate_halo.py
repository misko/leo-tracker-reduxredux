"""Pair the supplied tile with an independently trained outside-region hypothesis."""

from collections import defaultdict
from itertools import product
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.variants import orbit_projector, portable_gate, portable_v5

METHOD = "portable_gate_halo"
BOUNDARY = "Portable compact v5 with an out-of-tile held Doppler comparison"


def validation_score(units, sky, region, projector, sigma):
    _, point, selected = units
    good = defaultdict(float)
    gain = portable_v5.TRACK_CONFIG["alias_spacing_hz"] / (np.sqrt(2 * np.pi) * sigma)
    site = region.latlon(point)
    for arc, orbit, offset, phase in selected:
        bank = {k: sky[k][[orbit]] for k in ("position_km", "velocity_km_s")}
        bank["time_s"] = sky["time_s"]
        grid = orbit_projector.prepare(bank, arc.held_time, phase)
        prediction, elevation, _ = projector.evaluate(grid, *site)
        if elevation.min() < 0:
            continue
        residual = portable_gate.wrap(arc.held_y - prediction[0] * arc.scale - offset)
        mixture = 0.2 + 0.8 * gain * np.exp(-0.5 * (residual / sigma) ** 2)
        score = float(np.mean(np.log(mixture)))
        # Use the same no-signal mixture for unselected arcs and count each orbit once.
        good[orbit] = max(score, good[orbit])
    return sum(good.values())


def evidence(document, prepared, region, projector):
    arcs, metrics = portable_gate.make_arcs(document)
    metrics["validation_arcs"] = len(arcs)
    if len(arcs) < portable_gate.MIN_FAMILIES:
        return False, metrics
    sky = prepared["sky"]["bank"]
    sigma = portable_v5.TRACK_CONFIG["noise_sigma_hz"]
    prior = np.clip(sky["phase_sigma_s"], 0.05, 2)
    times = np.unique(np.concatenate([arc.train_time for arc in arcs]))
    grid = orbit_projector.prepare(sky, times)
    index = [np.searchsorted(times, arc.train_time) for arc in arcs]
    width = region.width_km
    radius = region.half_width_km

    def in_tile(point):
        return max(map(abs, point)) <= radius

    def train(point):
        lat, lon = region.latlon(point)
        if not (-90 < lat < 90 and -180 <= lon <= 180):
            return -1.0, point, []
        return portable_gate.training_match(
            arcs, grid, index, projector, prior, sigma, point, (lat, lon)
        )

    inside = max(map(train, region.grid), key=lambda r: r[0])
    lattice = product(np.arange(-4, 5) * width, repeat=2)
    midpoints = product((np.arange(-4, 4) + 0.5) * width, repeat=2)
    coarse_outside = [train(p) for p in (*lattice, *midpoints) if not in_tile(p)]
    ranked = sorted((r for r in coarse_outside if r[0] >= 0), key=lambda r: -r[0])
    if not ranked:
        return False, dict(metrics, challengers_available=0)

    # Coarse localization can exchange near-degenerate orbits. Keep two outside starts.
    def refine(best, increments, accept):
        for increment in increments:
            points = [
                (best[1][0] + dx, best[1][1] + dy)
                for dx, dy in product((-increment, 0.0, increment), repeat=2)
            ]
            best = max((train(p) for p in points if accept(p)), key=lambda r: r[0])
        return best

    inside = refine(inside, (width / 8, width / 16), in_tile)
    outside = max(
        (
            refine(r, (radius, width / 4, width / 8, width / 16), lambda p: not in_tile(p))
            for r in ranked[:2]
        ),
        key=lambda r: r[0],
    )
    held = portable_gate.held_match(inside, sky, region, projector, sigma)
    in_score, out_score = (
        validation_score(r, sky, region, projector, sigma) for r in (inside, outside)
    )
    # Gate on a training-selected challenger using a held log-score margin.
    admitted = portable_gate.admit(held) and in_score - out_score >= float(np.log(20))
    return admitted, dict(
        metrics,
        **held,
        inside_held_log_score=in_score,
        outside_held_log_score=out_score,
        outside_local_km=list(outside[1]),
        outside_training_score=outside[0],
        gate_projection_calls=projector.calls,
    )


def run(document, *, tile, archive, bound, library):
    with patch.object(portable_gate, "evidence", evidence):
        result = portable_gate.run(
            document, tile=tile, archive=archive, bound=bound, library=library
        )
    result["boundary"] = BOUNDARY
    return result
