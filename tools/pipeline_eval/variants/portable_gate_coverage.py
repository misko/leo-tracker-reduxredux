"""Require held Doppler across most independent native time–frequency arcs."""

from collections import defaultdict
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.variants import orbit_projector, portable_gate

METHOD = "portable_gate_coverage"
BOUNDARY = "Portable compact v5 with broad independently held Doppler support"


def units(arcs):
    """Collapse duplicate receiver tracks occupying the same RF and time support."""
    lanes = defaultdict(list)
    for arc in arcs:
        lanes[arc.channel, arc.scale].append(arc)
    for rows in lanes.values():
        chronological = sorted(rows, key=lambda a: a.train_time[0])
        clusters = []
        for arc in chronological:
            a, b = arc.train_time[[0, -1]]
            for cluster in clusters:
                c, d = cluster[0].train_time[[0, -1]]
                if min(b, d) - max(a, c) >= min(b - a, d - c) / 2:
                    cluster.append(arc)
                    break
            else:
                clusters.append([arc])
        yield from clusters


def support(selected, arcs, bank, region, projector, sigma):
    _, point, rows = selected
    station = region.latlon(point)
    valid = set()
    for arc, j, offset, phase in rows:
        sky = {k: bank[k][[j]] for k in ("position_km", "velocity_km_s")}
        sky["time_s"] = bank["time_s"]
        grid = orbit_projector.prepare(sky, arc.held_time, phase)
        modeled, elevation, _ = projector.evaluate(grid, *station)
        residual = portable_gate.wrap(arc.held_y - modeled[0] * arc.scale - offset)
        inliers = np.mean(abs(residual) <= portable_gate.MAX_HELD_RMS_SIGMAS * sigma)
        if inliers >= portable_gate.MIN_HELD_INLIER_FRACTION and elevation.min() >= 0:
            valid.add(id(arc))
    groups = list(units(arcs))
    passed = sum(any(id(a) in valid for a in group) for group in groups)
    return dict(held_arc_units=len(groups), supported_held_arc_units=passed)


def evidence(document, prepared, region, projector):
    original_arcs = portable_gate.make_arcs
    original_held = portable_gate.held_match
    arcs = []

    def remember(doc):
        tracks, metrics = original_arcs(doc)
        arcs.extend(tracks)
        return tracks, metrics

    def validate(selected, bank, region, projector, sigma):
        stats = original_held(selected, bank, region, projector, sigma)
        return dict(stats, **support(selected, arcs, bank, region, projector, sigma))

    with (
        patch.object(portable_gate, "make_arcs", remember),
        patch.object(portable_gate, "held_match", validate),
    ):
        admitted, metrics = ORIGINAL_EVIDENCE(document, prepared, region, projector)
    total = metrics.get("held_arc_units", 0)
    coherent = metrics.get("supported_held_arc_units", 0)
    # Two supported arcs per unexplained arc, in addition to orbit/channel/time diversity.
    return admitted and coherent * 3 >= total * 2, metrics


ORIGINAL_EVIDENCE = portable_gate.evidence


def run(document, *, tile, archive, bound, library):
    with patch.object(portable_gate, "evidence", evidence):
        result = portable_gate.run(
            document, tile=tile, archive=archive, bound=bound, library=library
        )
    result["boundary"] = BOUNDARY
    return result
