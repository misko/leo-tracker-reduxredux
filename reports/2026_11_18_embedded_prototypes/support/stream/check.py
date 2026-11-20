"""Bounded streaming and event-only feasibility on anonymous DS26 CFO measurements."""
import argparse
import json
import math
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment


TRACK_ROOT = Path("/srv/bulk/leo/research/algo07v3-20261104/tracks001/candidate")
MEMBERSHIP = Path("/srv/bulk/leo/research/ds26-20261030/fast-only-evaluation-membership.json")
OUTPUT = Path(__file__).resolve().parent
PERIOD = 1 / 4.4e-6


def wrap(frequency):
    return frequency - PERIOD * round(frequency / PERIOD)


@dataclass(slots=True)
class Track:
    ordinal: int
    start: float
    time: float
    frequency: float
    rate: float = 0.
    hits: int = 1
    pending: list = field(default_factory=list)


def stream(rows):
    tracks = defaultdict(list)
    membership = {}
    confirmations = []
    next_id = 0
    evaluations = 0
    peak = 0
    for obs, receiver, channel, rf, now, measured in rows:
        lane = tracks[receiver, channel, rf]
        lane[:] = [track for track in lane if now - track.time <= (6 if track.hits >= 3 else 2.5)]
        best_cost, best = math.inf, None
        for track in lane:
            dt = now - track.time
            if dt <= 0:
                continue
            evaluations += 1
            innovation = wrap(measured - track.frequency - track.rate * dt)
            if track.hits == 1:
                gate = 450 + 8000 * dt
            elif track.hits == 2:
                gate = 600 + 500 * dt + 35 * dt * dt
            else:
                gate = 450 + 100 * dt + 35 * dt * dt
            if abs(innovation) > gate:
                continue
            cost = abs(innovation) / gate + (0.5 if track.hits == 1 else 0)
            if cost < best_cost:
                best_cost, best = cost, (dt, innovation, track)
        if best is None:
            if len(lane) == 8:
                lane.remove(min(lane, key=lambda track: (min(6, track.hits), track.time)))
            lane.append(Track(next_id, now, now, measured, pending=[obs]))
            next_id += 1
            peak = max(peak, len(lane))
            continue
        dt, innovation, track = best
        gain = 1. if track.hits == 1 else 0.35
        track.frequency += track.rate * dt + (1. if track.hits == 1 else 0.8) * innovation
        track.rate = max(-8000., min(8000., track.rate + gain * innovation / dt))
        track.time, track.hits = now, track.hits + 1
        if track.hits < 6:
            track.pending.append(obs)
        else:
            membership[obs] = track.ordinal
            if track.hits == 6:
                membership.update((previous, track.ordinal) for previous in track.pending)
                track.pending.clear()
                confirmations.append((track.start, now))
    return membership, confirmations, evaluations, peak


def overlap_metrics(tracks, membership):
    truth = {obs: index for index, track in enumerate(tracks) for obs in track["observation_ids"]}
    groups = sorted(set(membership.values()))
    index = {value: i for i, value in enumerate(groups)}
    counts = np.zeros((len(groups), len(tracks)), dtype=np.int64)
    for obs, owner in membership.items():
        if obs in truth:
            counts[index[owner], truth[obs]] += 1
    matched_rows, matched_cols = linear_sum_assignment(counts, maximize=True)
    one_to_one = counts[matched_rows, matched_cols].sum()
    majority = counts.max(axis=1).sum() if counts.size else 0
    return dict(graph=len(truth), emitted=len(membership), both=int(counts.sum()),
                majority=int(majority), one_to_one=int(one_to_one), fragments=len(groups),
                graph_tracks=len(tracks))


def pass_center_time(t, y, parity):
    start, end = t[0], t[-1]
    midpoint, half = (start + end) / 2, (end - start) / 2
    select = slice(parity, None, 2)
    x = (t[select] - midpoint) / half
    design = np.column_stack((np.ones_like(x), x, x*x, x*x*x))
    coef, residual, rank, _ = np.linalg.lstsq(design, y[select], rcond=None)
    if rank < 4:
        return None
    deviation = max(1., math.sqrt(residual[0] / (len(x)-4)))
    sigma_cubic = deviation * math.sqrt(np.linalg.inv(design.T @ design)[3, 3])
    if coef[3] <= 3 * sigma_cubic:
        return None
    event = -coef[2] / (3*coef[3])
    slope = coef[1] + 2*coef[2]*event + 3*coef[3]*event*event
    if not (-.6 <= event <= .6 and slope < 0 and (x < event).sum() >= 3 and (x > event).sum() >= 3):
        return None
    return midpoint + half * event


def events(tracks):
    eligible, split_pair = 0, 0
    stable = []
    for i, track in enumerate(tracks):
        t = np.asarray(track["times"])
        if len(t) < 16 or t[-1] - t[0] < 20:
            continue
        eligible += 1
        y = np.asarray(track["values"])
        even, odd = [pass_center_time(t, y, parity) for parity in (0, 1)]
        if even is not None and odd is not None:
            split_pair += 1
            if abs(even-odd) <= 1:
                stable.append(i)
    return dict(eligible=eligible, same_pass=split_pair, stable=len(stable), stable_track_indexes=stable)


def synthetic():
    t = np.arange(50.)
    event = 25.
    clean = 7000. - 2500.*(t-event) + 0.03*(t-event)**3
    for parity in (0, 1):
        assert abs(pass_center_time(t, clean, parity) - event) < 1e-6
        assert abs(pass_center_time(t, clean+1000, parity) - event) < 1e-6
    a = [(i, 1, 1, 10.8e9, i*0.4, wrap(1e5 + i*1200)) for i in range(60)]
    stream_ids, confirmed, _, _ = stream(a)
    assert len(stream_ids) == 60 and len(set(stream_ids.values())) == 1 and confirmed == [(0., 2.)]
    b = [(100+i, 2, 1, 10.8e9, i*0.4, wrap(1e5 - i*1500)) for i in range(60)]
    together, *_ = stream(sorted(a+b, key=lambda row: row[4]))
    assert len(together) == 120 and len(set(together.values())) == 2
    assert set(stream(a[:5])[0]) == set() and len(stream(a[:6])[0]) == 6
