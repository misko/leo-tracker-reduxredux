"""Canonicalize duplicate polynomial proposals before Graph ownership."""

from collections import Counter, defaultdict
from contextlib import contextmanager
from unittest.mock import patch

import numpy as np

from leo.analysis import graph_tracklets as graph
from leo.analysis import polynomial_tracklets as poly


LIFT_EVIDENCE = "_graph_alias_lift_evidence"


def relative_winding(raw, lifted, period):
    """Recover the unique integer lift only when binary64 can distinguish it."""
    # The stock lift is p + wrap(y - p, period). Its short sequence of
    # additions, remainder and reconstruction stays within a few multiples of
    # this scale. Allow 32 eps for those roundoffs and require disjoint lifts.
    scale = np.maximum(np.maximum(np.abs(raw), np.abs(lifted)), period)
    error = (32 * np.finfo(float).eps) * scale
    if not np.all(error < period / 4):
        return None
    with np.errstate(over="ignore", invalid="ignore"):
        integers = np.rint((lifted - raw) / period)
        recovered = raw + integers * period
    if not np.all(np.abs(lifted - recovered) <= error):
        return None
    integer_lifts = integers.astype(np.int64)
    return integer_lifts - integer_lifts[0]


def canonical_proposals(t, y, models, cfg, metrics):
    """Use one fit for each certified support, degree and relative winding."""
    same_support = defaultdict(list)
    cleaned = []
    for index, original in enumerate(models):
        model = original.copy()
        evidence = model.pop(LIFT_EVIDENCE, None)
        cleaned.append(model)
        ix = model["indices"]
        if evidence is None or not len(ix) or not np.array_equal(ix, evidence[0]):
            continue
        same_support[(ix.tobytes(), model["degree"], model["reference_time_s"],
                      model["time_scale_s"])].append((index, evidence[1]))
    for group in same_support.values():
        if len(group) < 2:
            continue
        ix = cleaned[group[0][0]]["indices"]
        raw = y[ix]
        winding_groups = defaultdict(list)
        for index, lifted in group:
            winding = relative_winding(raw, lifted, cfg.alias_spacing_hz)
            if winding is None:
                metrics["uncertain_proposals"] += 1
            else:
                winding_groups[winding.tobytes()].append((index, winding))
        for equivalent in winding_groups.values():
            if len(equivalent) < 2:
                continue
            first, winding = equivalent[0]
            # The first supported raw measurement fixes the carrier gauge.
            # Aligning all other samples by relative integer shifts makes the
            # regression independent of the original fit's additive gauge.
            with np.errstate(over="ignore", invalid="ignore"):
                canonical = raw + winding * cfg.alias_spacing_hz
            if not np.all(np.isfinite(canonical)):
                metrics["uncertain_proposals"] += len(equivalent)
                continue
            cleaned[first] = poly._piece(t, canonical, ix, cleaned[first]["degree"])
            for index, _ in equivalent[1:]:
                cleaned[index] = None
            metrics["canonical_groups"] += 1
            metrics["duplicate_proposals"] += len(equivalent) - 1
    return [model for model in cleaned if model is not None]


@contextmanager
def canonical_alias_proposals():
    """Record the actual lifted response in discovery, then run stock finalization."""
    metrics = Counter()
    fit_piece, finish_lane = poly._piece, graph.finish_lane

    def observe_piece(t, lifted, indices, degree):
        piece = fit_piece(t, lifted, indices, degree)
        piece[LIFT_EVIDENCE] = (indices, lifted)
        return piece

    def finish(t, y, order, original_size, models, cfg, **kwargs):
        with patch.object(poly, "_piece", fit_piece):
            canonical = canonical_proposals(t, y, models, cfg, metrics)
            return finish_lane(t, y, order, original_size, canonical, cfg, **kwargs)

    with patch.object(poly, "_piece", observe_piece), patch.object(graph, "finish_lane", finish):
        yield metrics
