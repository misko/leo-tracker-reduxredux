"""Share prior prepared catalogue terms through the original v3 regional rank."""

from collections import Counter
from contextlib import contextmanager
from hashlib import sha256
from inspect import getsource, unwrap
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np


DISCOVERY_SHA256 = "7ca045c3809c8da7b57268b9d9bcc4b8a49366e88376250d0b11227ce6d7e26a"
PHASE_STATISTICS_SHA256 = "a93ff2401ddc18a3dbe450ba65e599baf83ee0f20da0533958f16f5cd534bf40"


class AnchorTables:
    """Retain one regional centre and a bounded set of fixed per-track terms."""

    def __init__(self, scan, project, counters, max_track_bytes):
        self.scan, self.project, self.counters = scan, project, counters
        self.center = np.asarray(scan.search_region.center, dtype=np.float64).tobytes()
        self.max_track_bytes = max_track_bytes
        self.nominal = None
        self.current = None
        self.tracks = {}
        self.retained = 0

    def projection(self, states, latitude, longitude, **kwargs):
        if states is not self.scan.geometry or kwargs:
            return self.project(states, latitude, longitude, **kwargs)
        point = np.asarray((latitude, longitude), dtype=np.float64).tobytes()
        at_center = point == self.center
        if at_center and self.nominal is not None:
            self.counters["centre_projections_reused"] += 1
            self.current = self.nominal
            return self.nominal
        if not at_center:
            self.nominal = None
            self.tracks.clear()
            self.retained = 0
        self.current = self.project(states, latitude, longitude)
        self.counters["nominal_projections"] += 1
        self.counters["nominal_projection_cells"] += self.current[0].size
        if at_center:
            self.nominal = self.current
            self.counters["centre_projection_bytes"] = sum(a.nbytes for a in self.nominal)
        else:
            self.counters["other_projections"] += 1
        return self.current

    def shared_inputs(self, bank, corrections, height):
        if self.current is None or type(bank) is not dict or height != 0:
            return False
        frequency, elevation, _ = self.current
        return (bank.get("time_s") is self.scan.times and bank.get("doppler_0") is frequency
                and bank.get("elevation_deg") is elevation
                and all(value == 0 and not np.signbit(value) for value in corrections.values()))

    def track_inputs(self, track, indexes, q):
        t = track["times"]
        key = track["key"]
        cached = self.tracks.get(key)
        if cached is not None and t is cached[0] and q == cached[1]:
            self.counters["centre_track_terms_reused"] += 1
            self.counters["centre_track_cells_reused"] += cached[2][0].size
            return cached[2]

        frequency, elevation, derivative = self.current
        scaled = q * frequency[:, indexes]
        visible = np.min(elevation[:, indexes], axis=1) >= 0.0
        h = q * derivative[:, indexes]
        hm = h.mean(axis=1)
        hc = h - hm[:, None]
        x = (t - t.mean()) / 150
        hh = np.sum(hc * hc, axis=1)
        xh = hc @ x
        prepared = scaled, visible, hc, hm, hh, xh
        size = sum(a.nbytes for a in prepared)
        self.counters["geometry_track_terms_built"] += 1
        if self.current is self.nominal and self.retained + size <= self.max_track_bytes:
            self.tracks[key] = t, q, prepared
            self.retained += size
            self.counters["peak_centre_track_bytes"] = max(
                self.counters["peak_centre_track_bytes"], self.retained,
            )
        return prepared


def fused_statistics(stock, tables):
    """Reuse the reviewed reducer and give it the current anchor's track terms."""
    released = unwrap(stock)
    source = getsource(released)
    replacements = (
        (
            "    # npz members decompress on every access.",
            "    if not _tables.shared_inputs(bank, corrections, height):\n"
            "        return _stock(groups, bank, corrections, height)\n"
            "    phase = dict(hm=[], hh=[], xh=[], zh=[])\n"
            "    # npz members decompress on every access.",
        ),
        (
            '            z = track["values"][None, :] - q * bank[f"doppler_{height}"][:, indexes]\n',
            '            scaled, in_view, hc, hm, hh, xh = _tables.track_inputs(track, indexes, q)\n'
            '            z = track["values"][None, :] - scaled\n',
        ),
        (
            '            visible.append(np.min(bank["elevation_deg"][:, indexes], axis=1) >= 0.0)\n',
            '            visible.append(in_view)\n'
            '            phase["hm"].append(hm)\n'
            '            phase["hh"].append(hh)\n'
            '            phase["xh"].append(xh)\n'
            '            phase["zh"].append(np.sum(hc * centered, axis=1))\n',
        ),
        (
            '    return result\n',
            '    result.update({key: np.asarray(rows) for key, rows in phase.items()})\n'
            '    return result\n',
        ),
    )
    for old, new in replacements:
        if source.count(old) != 1:
            raise ValueError("Unexpected ALGO08v3 discovery statistics")
        source = source.replace(old, new, 1)
    globals_ = dict(released.__globals__, _stock=stock, _tables=tables)
    exec(compile(source, released.__code__.co_filename, "exec"), globals_)
    return globals_["statistics"]


@contextmanager
def shared_rank_preparation(scan, *, max_track_bytes=128 * 1024**2):
    """Keep the centre seeds, every corner, and the released rank/refinement rules."""
    from leo.analysis.localization_v3 import discovery
    from leo.analysis.research import shared_orbit_phase_fit

    for module, expected in ((discovery, DISCOVERY_SHA256),
                             (shared_orbit_phase_fit, PHASE_STATISTICS_SHA256)):
        if sha256(Path(module.__file__).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Unreviewed regional discovery module: {module.__file__}")
    counts = Counter()
    tables = AnchorTables(scan, discovery.phase_linear_frequency, counts, max_track_bytes)
    statistics = fused_statistics(discovery.statistics, tables)
    augment_phase = discovery.augment_phase_statistics

    def statistics_timed(*args, **kwargs):
        start = process_time_ns()
        result = statistics(*args, **kwargs)
        counts["statistics_cpu_ns"] += process_time_ns() - start
        return result

    def augment(stats, times, frequency, derivative):
        if tables.current is not None and times is scan.times and frequency is tables.current[0] and (
            derivative is tables.current[2] and "zh" in stats
        ):
            counts["fused_passes"] += 1
            return stats
        return augment_phase(stats, times, frequency, derivative)

    with (patch.object(discovery, "phase_linear_frequency", tables.projection),
          patch.object(discovery, "statistics", statistics_timed),
          patch.object(discovery, "augment_phase_statistics", augment)):
        yield counts
