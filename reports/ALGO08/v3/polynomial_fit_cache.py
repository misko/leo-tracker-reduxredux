"""Research cache for byte-identical Graph polynomial inputs within one lane."""

from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
import marshal
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np


SOURCE_PINS = {
    "polynomial_tracklets": "933b83ce5e414a8441c62d17f8e5eb75e07b79cada283bf681193f7316346922",
    "graph_tracklets": "74575f44c4e9716707faaac56e3e7c35bb423ba0f75332656d7c6576cd8f2c27",
    "tracklet_fitting": "8e3917e1bb94bf59e37d97a7a3782254612e459d36075f67acfdfe15b3a19414",
    "tracks": "db44a947666c2dd7946534f69bf6af72ced63c8af553bb1b089c0fba3d5b7b6f",
}
MAX_ENTRIES = 256
MAX_ARRAY_ITEMS = 4096
MISSING = object()


def supported(*arrays):
    return all(type(a) is np.ndarray and a.ndim == 1 and a.dtype.kind in "iuf"
               and len(a) <= MAX_ARRAY_ITEMS for a in arrays)


def array_keys(*arrays):
    if not supported(*arrays):
        return None
    return tuple((a.dtype.str, a.shape, a.strides, a.tobytes()) for a in arrays)


def clone(piece):
    if piece is None:
        return None
    return {key: value.copy() if isinstance(value, np.ndarray) else value for key, value in piece.items()}


class LaneCache:
    def __init__(self, config, counts, census):
        self.config = config
        self.counts = counts
        self.census = census
        self.duplicate_best = False
        self.finishing = False
        self.prefix = {"best": None, "piece": None}
        self.entries = {"best": {}, "piece": {}}

    def config_key(self, config):
        if config is not self.config:
            return None
        try:
            return marshal.dumps(vars(config), 2)
        except ValueError:
            return None

    def evaluate(self, name, operation, args, context, inputs, config_key):
        self.counts[f"{name}_calls"] += 1
        if context is None or inputs is None or config_key is None:
            self.counts[f"{name}_fallback"] += 1
            return operation(*args)
        prefix = (*context, config_key)
        entries = self.entries[name]
        if prefix != self.prefix[name]:
            self.prefix[name] = prefix
            entries.clear()
        saved = entries.get(inputs, MISSING)
        hit = saved is not MISSING
        self.counts[f"{name}_hits"] += hit
        if self.census:
            earlier = self.duplicate_best
            if name == "best":
                self.duplicate_best = hit
            started = process_time_ns()
            try:
                result = operation(*args)
            finally:
                cpu = process_time_ns()-started
                self.duplicate_best = earlier
            self.counts[f"{name}_original_cpu_ns"] += cpu
            if hit:
                self.counts[f"{name}_original_duplicate_cpu_ns"] += cpu
                if self.finishing and not saved:
                    self.counts[f"{name}_finalization_hits_from_refinement"] += 1
                if name == "piece" and not earlier:
                    self.counts["piece_duplicate_cpu_ns_outside_duplicate_best"] += cpu
        elif hit:
            return clone(saved)
        else:
            result = operation(*args)

        if not hit:
            if len(entries) >= MAX_ENTRIES:
                entries.pop(next(iter(entries)))
                self.counts[f"{name}_evictions"] += 1
            entries[inputs] = self.finishing if self.census else clone(result)
            peak = f"{name}_peak_entries_per_lane"
            self.counts[peak] = max(self.counts[peak], len(entries))
        return result


def installed_sources():
    from leo.analysis import graph_tracklets, polynomial_tracklets, tracklet_fitting
    from leo.analysis.localization_v3 import tracks

    found = {name: sha256(Path(module.__file__).read_bytes()).hexdigest()
             for name, module in (("polynomial_tracklets", polynomial_tracklets), ("graph_tracklets", graph_tracklets),
                                  ("tracklet_fitting", tracklet_fitting), ("tracks", tracks))}
    if found != SOURCE_PINS:
        raise ValueError("Expected the pinned installed Graph arithmetic and consumers")
    return polynomial_tracklets, tracks


@contextmanager
def reuse(mode, counts):
    from contextlib import ExitStack

    if mode == "stock":
        yield
        return
    if mode not in ("best", "piece", "both", "census"):
        raise ValueError("Unknown polynomial reuse mode")
    poly, tracks = installed_sources()
    original_lane, original_best, original_piece = tracks.fit_lane, poly._best_piece, poly._piece
    active = ContextVar("graph_polynomial_lane_cache", default=None)

    def lane(t, y, cfg=None):
        if type(cfg) is not poly.TrackConfig:
            return original_lane(t, y, cfg)
        counts["lanes"] += 1
        token = active.set(LaneCache(cfg, counts, census=mode == "census"))
        try:
            return original_lane(t, y, cfg)
        finally:
            active.reset(token)

    def best(t, y, indices, prediction, cfg):
        state = active.get()
        args = (t, y, indices, prediction, cfg)
        if state is None:
            return original_best(*args)
        config_key = state.config_key(cfg)
        context = array_keys(t, y)
        inputs = None
        if (context is not None and config_key is not None and supported(indices, prediction)
                and indices.dtype.kind in "iu" and len(indices) == len(prediction)):
            lifted = prediction + poly._wrap(y[indices] - prediction, cfg.alias_spacing_hz)
            inputs = array_keys(indices, lifted)
        return state.evaluate("best", original_best, args, context, inputs, config_key)

    def piece(t, lifted, indices, degree):
        state = active.get()
        args = (t, lifted, indices, degree)
        if state is None:
            return original_piece(*args)
        config_key = state.config_key(state.config)
        context, arrays = array_keys(t), array_keys(lifted, indices)
        inputs = (*arrays, type(degree), int(degree)) if arrays is not None and type(degree) is int else None
        return state.evaluate("piece", original_piece, args, context, inputs, config_key)

    with ExitStack() as stack:
        stack.enter_context(patch.object(tracks, "fit_lane", lane))
        if mode in ("best", "both", "census"):
            stack.enter_context(patch.object(poly, "_best_piece", best))
        if mode in ("piece", "both", "census"):
            stack.enter_context(patch.object(poly, "_piece", piece))
        if mode == "census":
            from leo.analysis import graph_tracklets

            original_finish = graph_tracklets.finish_lane

            def finish(*args, **kwargs):
                state = active.get()
                if state is None:
                    return original_finish(*args, **kwargs)
                state.finishing = True
                try:
                    return original_finish(*args, **kwargs)
                finally:
                    state.finishing = False

            stack.enter_context(patch.object(graph_tracklets, "finish_lane", finish))
        yield
