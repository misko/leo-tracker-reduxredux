"""Measure supported anonymous CFO turning points without choosing orbit identities."""

from collections import Counter

import numpy as np

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from ..reference import grid, tracker
from .folded_doppler import _offset
from .peak_paths import read_peaks

METHOD = "doppler_turns"
BOUNDARY = "Anonymous native GLRT and causal orbit turning-point feasibility"
MIN_RATE = 100.0
SCALE = 350.0
CAP = 96


def descriptor(track):
    if not track.confirmed or track.last[0] - track.samples[0][0] < 10:
        return None
    support = track.samples if track.samples[-1] is track.last else [*track.samples, track.last]
    if len(support) < 12:
        return None
    t, f = np.asarray(support).T
    return dict(t=t, f=f, lane=track.lane)


class AnonymousTracks(tracker.Tracker):
    """Reuse signed-symmetric linking without filtering by arc curvature."""

    def retire(self, track):
        if (doc := descriptor(track)) is not None:
            self.retired.append((track.hits, track.ordinal, doc))
            self.retired.sort(key=lambda item: (-item[0], item[1]))
            del self.retired[CAP:]

    def arcs(self):
        for lane in self.lanes.values():
            for track in lane:
                self.retire(track)
        return [d for _, _, d in self.retired]


def fit(x, y):
    dx = x - x.mean()
    m = (dx @ y) / (dx @ dx)
    b = y.mean() - m * x.mean()
    rms = np.sqrt(np.mean((b + m * x - y) ** 2))
    return float(m), float(b), float(rms)


def bracket(x, y):
    left, right = (x >= -10) & (x <= -2), (x >= 2) & (x <= 10)
    center = np.abs(x) < 2
    if left.sum() < 3 or right.sum() < 3 or center.sum() < 2:
        return None
    m, b, er1 = fit(x[left], y[left])
    n, c, er2 = fit(x[right], y[right])
    if (
        m * n >= 0
        or min(abs(m), abs(n)) < MIN_RATE
        or min(abs(m) * np.ptp(x[left]), abs(n) * np.ptp(x[right])) < 500
        or max(er1, er2) > SCALE
    ):
        return None
    t = (c - b) / (m - n)
    a = x[center] - t
    if abs(t) > 2 or not ((a >= -2) & (a < 0)).any() or not ((a > 0) & (a <= 2)).any():
        return None
    pred = np.where(a <= 0, m * x[center] + b, n * x[center] + c)
    if np.sqrt(np.mean((pred - y[center]) ** 2)) > SCALE:
        return None
    return t, int(np.sign(m)), [m, n]


def scan(t, f):
    if len(t) < 12 or np.any(np.diff(t) <= 0):
        return 0, []
    head = np.arange(len(t)) % 2 == 0
    proposed, events = 0, []
    for at in t[(t >= t[0] + 7) & (t <= t[-1] - 7)]:
        x = t - at
        a = bracket(x[head], f[head])
        if a is None:
            continue
        proposed += 1
        b = bracket(x[~head], f[~head])
        if b is not None and a[1] == b[1] and abs(a[0] - b[0]) <= 2:
            events.append(
                dict(
                    time_s=float(at + a[0]),
                    checked_time_s=float(at + b[0]),
                    direction=a[1],
                    slopes_hz_s=a[2],
                    held_slopes_hz_s=b[2],
                )
            )
    return proposed, events


def unique_events(events):
    result = []
    for best in sorted(events, key=lambda x: abs(x["time_s"] - x["checked_time_s"])):
        if all(
            best["direction"] != e["direction"] or abs(best["time_s"] - e["time_s"]) > 3
            for e in result
        ):
            result.append(best)
    return result


def empirical(capture):
    lanes, counts = read_peaks(capture)
    chronological = sorted(
        (float(t), i, j) for i, lane in enumerate(lanes) for j, t in enumerate(lane.t)
    )
    linked = AnonymousTracks()
    for t, i, j in chronological:
        lane = lanes[i]
        keep = lane.y[j, lane.marks[j] > 0.05]
        distinct = []
        for hz in keep:
            if all(abs(tracker.wrap(float(hz) - last)) >= 160 for last in distinct):
                distinct.append(float(hz))
        linked.ingest(t, lane.key, distinct)
    counts.update(
        arc_count=0,
        total_arc_seconds=0.0,
        candidate_windows=0,
        held_windows=0,
        held_arcs=0,
        descending_arcs=0,
    )
    events, ledger = [], []
    for track in linked.arcs():
        t, f, lane = track["t"], track["f"], track["lane"]
        windows, observed = scan(t, f)
        slope = fit(t - t.mean(), f - f.mean())[0]
        counts["arc_count"] += 1
        counts["total_arc_seconds"] += float(t[-1] - t[0])
        counts["candidate_windows"] += windows
        counts["held_windows"] += len(observed)
        counts["held_arcs"] += bool(observed)
        counts["descending_arcs"] += slope < 0
        ledger.append(
            dict(
                lane=lane,
                first_s=float(t[0]),
                last_s=float(t[-1]),
                points=len(t),
                slope_hz_s=slope,
                proposed=windows,
                held=len(observed),
            )
        )
        events.extend(dict(x, lane=lane) for x in observed)
    return counts | dict(events=unique_events(events), arc_inventory=ledger)


def modeled(capture, center):
    sky = grid.prepare_sky(capture, capture.catalog)
    centre = geodetic_to_ecef_km(*center, 0.0)
    frame = ecef_to_enu_matrix(*center)
    d = sky.positions_km - centre
    nearby = ((d @ frame[2]) >= -0.10 * np.linalg.norm(d, axis=-1)).any(axis=1)
    sample = np.arange(0.0, capture.duration_s + 1e-9, 2.0)
    sats, p, v = grid._valid_states(
        [s for s, possible in zip(sky.satellites, nearby, strict=True) if possible],
        capture.anchor_utc_ns,
        sample,
    )
    counts = Counter()
    for east, north in ((0, 0), (10, 0), (-10, 0), (0, 10), (0, -10)):
        site = _offset(center, east, north)
        delta = p - geodetic_to_ecef_km(*site, 0)
        ranges = np.linalg.norm(delta, axis=-1)
        above = delta @ ecef_to_enu_matrix(*site)[2] > 0
        hz = (-11.8e9 / grid.LIGHT_SPEED_KM_S) * np.sum(delta * v, axis=-1) / ranges
        rate = np.diff(hz, axis=1) / 2
        visible_turn = above[:, :-2] & above[:, 1:-1] & above[:, 2:]
        counts["visible_orbit_sites"] += int(np.count_nonzero(np.any(above, axis=1)))
        counts["raw_visible_zero_crossings"] += int(
            np.count_nonzero(visible_turn & (rate[:, :-1] * rate[:, 1:] < 0))
        )
        # Two 8 s secants starting 2 s from the candidate midpoint.
        a, b = (hz[:, 4:-6] - hz[:, :-10]) / 8, (hz[:, 10:] - hz[:, 6:-4]) / 8
        up = np.lib.stride_tricks.sliding_window_view(above, 11, axis=1).all(axis=-1)
        counts["visible_two_sided_turn_windows"] += int(
            np.count_nonzero(up & (a * b < 0) & (np.minimum(abs(a), abs(b)) >= MIN_RATE))
        )
    return dict(**counts, orbit_sites=5, fine_orbits=len(sats), epoch_samples=len(sample))


def measure(capture, tile):
    if tile.get("width_km", 25) != 25:
        raise ValueError("one 25 km offered square is required")
    support = empirical(capture)
    synthetic_geometry = modeled(capture, tile["center"])
    return dict(
        status="withheld",
        reason="turning_point_feasibility_only",
        boundary=BOUNDARY,
        metrics=support | dict(modeled=synthetic_geometry, position_attempted=False),
        arms={arm: dict(latlon=None, forced_latlon=None) for arm in ("c0", "fitted_c")},
    )
