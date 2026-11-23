"""Use confirmed native margin only for the Graph discovery node reward."""

from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
import ctypes as ct
from hashlib import sha256
from math import isfinite
from pathlib import Path
import subprocess
from unittest.mock import patch

import numpy as np

from aperture_trial import PAYLOAD, write
from dense_full_short_raw import checked
from dense_geographic_trial import host
from eight_ms_crossover import strata


THRESHOLD = .025
NATIVE_DIR = PAYLOAD / "tools/pipeline_eval/variants/experimental"
NATIVE_PIN = "cbbee06c6305f82a096561ae6498ef163786e7c82af95e11af0dbf8b7da030eb"
EDIT = (
    ("leo_graph_path_abi", "leo_weighted_graph_path_abi"),
    ("leo_graph_path_v1", "leo_weighted_graph_path_v1"),
    ("double reward, double penalty,", "const double *reward, double penalty,"),
    ("    double base = 2.0 * reward - penalty;\n", ""),
    ("            double best = base - gap;", "            double next_reward = reward[target[next]];\n"
     "            double best = (reward[node] + next_reward - penalty) - gap;"),
    ("(state[prev].score + reward)", "(state[prev].score + next_reward)"),
)


def weighted_source():
    base = checked(NATIVE_DIR / "graph_path.c", NATIVE_PIN).read_text()
    for old, new in EDIT:
        if base.count(old) != 1:
            raise ValueError("Installed path recurrence differs from the frozen edit")
        base = base.replace(old, new, 1)
    return base


def build(output):
    system = host()
    output.mkdir()
    source, library = output / "weighted-graph.c", output / "weighted-graph.so"
    source.write_text(weighted_source())
    command = ["cc", "-std=c11", "-O3", "-fPIC", "-shared", "-fno-fast-math", "-ffp-contract=off",
               "-frounding-math", str(source), "-o", str(library)]
    subprocess.run(command, check=True, timeout=30)
    write(output / "build.json", dict(machine=system, command=command, reference_sha256=NATIVE_PIN,
                                      source_sha256=sha256(source.read_bytes()).hexdigest(),
                                      binary_sha256=sha256(library.read_bytes()).hexdigest()))


class WeightedPath:
    def __init__(self, library):
        self.library = ct.CDLL(str(library))
        abi = self.library.leo_weighted_graph_path_abi
        abi.argtypes, abi.restype = [], ct.c_uint32
        if abi() != 1:
            raise ValueError("Expected the reviewed weighted Graph ABI")
        self.operation = self.library.leo_weighted_graph_path_v1
        self.operation.argtypes = [ct.c_int64, ct.c_int64] + [ct.c_void_p] * 12 + [
            ct.c_double, ct.c_double, ct.c_int64, ct.c_double, ct.c_void_p, ct.POINTER(ct.c_double)]
        self.operation.restype = ct.c_int64

    def solve(self, packed, y, available, enabled, cfg, rewards):
        t, source, target, duration, velocity, *_ = packed
        path = np.empty(len(t), dtype=np.int64)
        value = ct.c_double()
        count = self.operation(
            len(t), len(source), *(a.ctypes.data for a in (*packed, available, enabled, rewards)),
            cfg.track_penalty, 2 * cfg.noise_sigma_hz**2, cfg.min_points, cfg.min_span_s, path.ctypes.data, ct.byref(value),
        )
        if not 0 <= count < len(t):
            raise ValueError("Weighted Graph returned an invalid path extent")
        edges = path[:count][::-1].copy()
        if not count:
            return np.array([], int), np.array([]), edges, 0.0
        path = np.r_[source[edges], target[edges[-1]]]
        lifted = y[path[0]] + np.r_[0., np.cumsum(velocity[edges] * duration[edges])]
        return path, lifted, edges, value.value


def weight(margin, anchor):
    if not isfinite(margin) or margin < THRESHOLD:
        raise ValueError("Expected a valid selected exact-minus-roll verifier margin")
    return 1. if anchor else min(1., max(0., 1. - THRESHOLD / margin))


def factor_weights(native, unit):
    result, counts = {}, Counter()
    for oid, kind, _, _, factor in strata(native, native):
        if factor is None:
            continue
        margin = factor["fractional_exact_score"] - factor["fractional_control_score"]
        if margin != factor["fractional_margin"]:
            raise ValueError("Saved margin differs from the original fractional exact-minus-roll score")
        value = weight(margin, kind == "anchor")
        result[oid] = (1. if unit else value, factor["fractional_tracking_cfo_hz"])
        counts["anchors" if kind == "anchor" else "nonanchors"] += 1
    return result, dict(counts)


@contextmanager
def discovery_weights(native, library, *, mode, counts, verify=False):
    from leo.analysis import graph_tracklets
    from leo.analysis.localization_v3 import tracks
    from tools.pipeline_eval.variants.experimental.graph_path import NativePath

    if mode not in ("unit", "weighted") or (verify and mode != "unit"):
        raise ValueError("Expected the frozen unit or measured-margin mode")
    values, census = factor_weights(native, unit=mode == "unit")
    kernel = WeightedPath(library)
    stage = ContextVar("ordered_graph_node_rewards", default=None)
    original_group = tracks._single_rf_tracks
    original_solve = NativePath.solve
    counts.update(census)
    counts["min_weight"] = min((row[0] for row in values.values()), default=None)
    counts["max_weight"] = max((row[0] for row in values.values()), default=None)
    used = set()

    def group(rows, source_id, cfg):
        groups = {}
        for row in rows:
            key = row["receiver"], row["channel"]
            groups.setdefault(key, []).append(row)
        cells = iter(groups[key] for key in sorted(groups))
        original_lane = tracks.fit_lane

        def lane(t, y, config):
            lane_rows = next(cells)
            ids = [item["observation_id"] for item in lane_rows]
            if (len(ids) != len(set(ids))
                    or not np.array_equal(t, [row["time_s"] for row in lane_rows])
                    or not np.array_equal(y, [values[oid][1] for oid in ids])):
                raise ValueError("Installed Graph inputs differ from the confirmed ordered detector rows")
            used.update(ids)
            ts, ys, order, _ = graph_tracklets.prepare_lane(t, y)
            rewards = np.array([values[ids[index]][0] for index in order], dtype=np.float64) * config.association_sigma**2
            token = stage.set((ts, ys, rewards))
            counts["lanes"] = counts.get("lanes", 0) + 1
            try:
                return original_lane(t, y, config)
            finally:
                stage.reset(token)

        with patch.object(tracks, "fit_lane", lane):
            return original_group(rows, source_id, cfg)

    def native_solve(self, packed, y, available, enabled, cfg):
        active = stage.get()
        if active is None:
            return original_solve(self, packed, y, available, enabled, cfg)
        ts, ys, rewards = active
        if ts.tobytes() != packed[0].tobytes() or ys.tobytes() != y.tobytes():
            raise ValueError("Ordered native path rows do not match their discovery rewards")
        result = kernel.solve(packed, y, available, enabled, cfg, rewards)
        counts["path_calls"] = counts.get("path_calls", 0) + 1
        if verify:
            original = original_solve(self, packed, y, available, enabled, cfg)
            if (original is None or result[3].hex() != original[3].hex()
                    or any(a.tobytes() != b.tobytes() for a, b in zip(result[:3], original[:3], strict=True))):
                raise ValueError("Unit weights changed the installed ordered native path")
            counts["verified_calls"] = counts.get("verified_calls", 0) + 1
        return result

    with patch.object(tracks, "_single_rf_tracks", group), patch.object(NativePath, "solve", native_solve):
        yield
    if used != values.keys():
        raise ValueError("The discovery reward did not cover the original Graph preparation")
