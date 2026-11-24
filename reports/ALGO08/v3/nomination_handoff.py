"""Hand the installed c=0 nomination its exact, request-local cold prefix."""

from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
from inspect import getsource
import json
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np


SCREEN_SOURCE = "f276b8ee2f4c059d571da874b2fbef6f6b13d08078e30fd93950428f8c10fb70"
RACE_SOURCE = "eeb7d1041f34fb7dbb805cb12eb93f66eba87e729e9cf695ff77811b51842fe7"
CUT = "    screens = []\n"
AFTER = "    scores = [score if np.isfinite(score) else None for score, _, _ in screens]\n"


def same(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, np.ndarray):
        return (left.shape, left.dtype, left.strides, left.tobytes()) == (
            right.shape, right.dtype, right.strides, right.tobytes())
    if isinstance(left, dict):
        return tuple(left) == tuple(right) and all(same(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right))
    if isinstance(left, (float, np.generic)):
        return np.asarray(left).tobytes() == np.asarray(right).tobytes()
    return left == right


def screen_port(stock, consume):
    filename = Path(stock.__code__.co_filename)
    if sha256(filename.read_bytes()).hexdigest() != SCREEN_SOURCE:
        raise ValueError("Unsupported installed screen source")
    source = getsource(stock)
    if source.count(CUT) != 1 or source.count(AFTER) != 1:
        raise ValueError("Unexpected original screen checkpoint")
    bridge = """    screens = _checkpoint(scan, nodes)
    if screens is None:
        return _ordinary_screen(scan, nodes, metrics)
"""
    changed = source[:source.index(CUT)] + bridge + source[source.index(AFTER):]
    namespace = dict(stock.__globals__, _checkpoint=consume, _ordinary_screen=stock)
    exec(compile(changed, str(filename), "exec"), namespace)
    return namespace[stock.__name__]


def numerical_inputs(prepared):
    sky = prepared["sky"]
    digest = sha256()
    document = (prepared["tracks"]["tracks"], sky["metadata"], sky["nominal_elements"],
                sky["previous_receipt"], sky["previous_tle"])
    digest.update(json.dumps(document, separators=(",", ":")).encode())
    for name, value in sky["bank"].items():
        array = np.asarray(value)
        if array.dtype.hasobject:
            raise ValueError("Unsupported geometry input type")
        digest.update(json.dumps((name, array.shape, array.dtype.str, array.strides)).encode())
        digest.update(memoryview(np.ascontiguousarray(array)).cast("B"))
    return digest.digest()


class NominationHandoff:
    """Own a single serial previous-scan/rank result and its two-round prefix."""

    def __init__(self, core, screens, exact_rank, audit):
        self.core, self.screens, self.exact_rank = core, screens, exact_rank
        self.scan_context = core.scan_context
        self.counts = Counter()
        audit["nomination_handoff"] = self.counts
        self.source = None
        self.scan = None
        self.nodes = None
        self.checkpoint = None
        self.used = False
        try:
            self.screen = screen_port(screens.screen_nodes, self.consume)
        except (OSError, TypeError, ValueError):
            self.screen = None
            self.counts["unsupported_binding"] += 1

    def prepare(self, prepared, region, digest, bound, previous):
        scan = self.scan_context(prepared, region, digest, bound, previous)
        if previous == "previous" and self.scan is None:
            try:
                self.source = (prepared, region, digest, bound, self.geometry(prepared))
                self.scan = scan
            except (KeyError, TypeError, ValueError):
                self.counts["unsupported_geometry"] += 1
        return scan

    def geometry(self, prepared):
        start = process_time_ns()
        try:
            return numerical_inputs(prepared)
        finally:
            self.counts["geometry_guard_cpu_ns"] += process_time_ns()-start

    def resume(self, prepared, region, digest, bound, previous):
        if self.source is not None:
            source, offered, noise, native, geometry = self.source
            if previous == "previous" and prepared is source and region is offered and bound is native and digest == noise:
                try:
                    if self.geometry(prepared) == geometry:
                        self.counts["scan_reuses"] += 1
                        return self.scan
                except (KeyError, TypeError, ValueError):
                    self.counts["unsupported_geometry"] += 1
        return self.scan_context(prepared, region, digest, bound, previous)

    def rank(self, scan):
        nodes = self.exact_rank(scan)
        if scan is self.scan and self.nodes is None:
            start = process_time_ns()
            self.nodes = deepcopy(nodes)
            self.counts["ranked_nodes"] = len(nodes)
            self.counts["checkpoint_cpu_ns"] += process_time_ns()-start
        return nodes

    def replay_rank(self, scan):
        if scan is self.scan and self.nodes is not None and self.checkpoint is not None and not self.used:
            self.counts["rank_reuses"] += 1
            return deepcopy(self.nodes)
        return self.exact_rank(scan)

    def capture(self, scan, nodes, outcomes):
        start = process_time_ns()
        if (scan is not self.scan or self.nodes is None or not nodes or not same(nodes, self.nodes[:3])
                or set(outcomes) != set(range(len(nodes)))):
            self.counts["incomplete_prefix"] += 1
            return
        answers = []
        for k, node in enumerate(nodes):
            got, xy, phases, score = outcomes[k]
            labels = sorted({row["candidate_index"] for row in node["seed"]["rows"]})
            if (not same(got, node) or score is None or not np.isfinite(score) or tuple(phases) != tuple(labels)
                    or xy.shape != (2,) or not np.isfinite(xy).all()):
                self.counts["invalid_prefix"] += 1
                return
            reference = np.array(list(phases.values()))
            if reference.shape != (len(labels),) or not np.isfinite(reference).all() or np.any(np.abs(reference) > 15):
                self.counts["invalid_prefix"] += 1
                return
            answers.append((score, xy.copy(), reference))
        self.checkpoint = answers
        self.counts["prefixes_captured"] = len(answers)
        self.counts["checkpoint_cpu_ns"] += process_time_ns()-start

    def consume(self, scan, nodes):
        if not self.used and scan is self.scan and self.checkpoint is not None and same(nodes, self.nodes[:3]):
            self.used = True
            self.counts["prefixes_reused"] += len(nodes)
            return deepcopy(self.checkpoint)
        self.counts["ordinary_screens"] += 1
        return None

    @contextmanager
    def producer(self):
        with (patch.object(self.core, "scan_context", self.prepare),
              patch.object(self.core, "ranked_initial_nodes", self.rank)):
            yield

    @contextmanager
    def fallback(self):
        with patch.object(self.core, "ranked_initial_nodes", self.exact_rank):
            if self.nodes is None or self.checkpoint is None or self.used or self.screen is None:
                self.counts["ordinary_fallbacks"] += 1
                yield
                return
            with (patch.object(self.core, "scan_context", self.resume),
                  patch.object(self.core, "ranked_initial_nodes", self.replay_rank),
                  patch.object(self.screens, "screen_nodes", self.screen)):
                yield


def capture_race(race, handoff):
    original, partial = race.refine, race.partial_fits

    def capture(scan, nodes, half_width, details):
        outcomes, completed = partial(scan, nodes, half_width, details)
        handoff.capture(scan, nodes, outcomes)
        return outcomes, completed

    def refine(mode, prepared, region, bound):
        if mode != "race":
            return original(mode, prepared, region, bound)
        # The opt-in uses the exact rank already installed for the named path.
        with handoff.producer(), patch.object(race, "partial_fits", capture):
            return original(mode, prepared, region, bound)

    return refine


@contextmanager
def routed_binding(reader, cutoff, audit, original_rank):
    """Research-only opt-in for the existing history-risk route."""
    import cold_finalist_race as race
    from history_risk_route import binding
    from tools.pipeline_eval.variants import v5_core, v5_screen_winner

    handoff = NominationHandoff(v5_core, v5_screen_winner, v5_core.ranked_initial_nodes, audit)
    if sha256(Path(race.__file__).read_bytes()).hexdigest() != RACE_SOURCE or handoff.screen is None:
        handoff.counts["independent_route"] += 1
        with binding(reader, cutoff, audit, original_rank):
            yield
        return
    original = v5_core.infer

    def named(*args, **kwargs):
        with handoff.fallback():
            return original(*args, **kwargs)

    with (patch.object(v5_core, "infer", named), patch.object(race, "refine", capture_race(race, handoff)),
          binding(reader, cutoff, audit, original_rank)):
        yield
