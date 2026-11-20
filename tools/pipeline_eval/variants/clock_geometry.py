"""Measure two independent simultaneous GLRT clock invariants."""

from collections import defaultdict

import numpy as np
from scipy.integrate import cumulative_trapezoid

from . import paired_doppler as pairs
from . import paired_peaks as hardware

METHOD = "clock_geometry"
BOUNDARY = "Exact GLRT clock observables through anonymous causal regional position"
ARMS = ("c0", "fitted_c")
SEPARATION_SAMPLES = 0.25
GATE_HZ = 220


def closure(t, epoch, difference, rf, fs):
    """Fit only the prefix nuisance and check held frame delay with known sign."""
    n = 2 * len(t) // 3
    A = np.column_stack((np.ones(len(t)), t - t[0]))
    inverse = np.linalg.pinv(A[:n])
    continuous = np.unwrap(epoch, period=fs / 750)
    model = -fs / rf * cumulative_trapezoid(difference, t, initial=0)
    values = {}
    for label, direction in (("physical", 1), ("reversed", -1), ("clock_only", 0)):
        error = continuous - direction * model
        predicted = error - A @ (inverse @ error[:n])
        values[label] = float(np.sqrt(np.mean(predicted[n:] ** 2)))
    values["qualified"] = values["physical"] <= 3 and values["physical"] <= 0.8 * min(
        values["reversed"], values["clock_only"]
    )
    return values


def timing(capture, witnessed):
    raw = {
        (r["receiver_id"], r["channel"], r["actual_rf_hz"], r["valid_start_counter"]): r
        for r in capture.probes
        if r["probe_start_ms"] == 0
    }
    rows = []
    for p in witnessed:
        lane, block = tuple(p["lane"]), p["block"]
        times, CFO, epoch = [], [], []
        for t, counter, left, right, ra, rb in p["witnesses"]:
            options = {v["candidate_rank"]: v for v in raw[(*lane, counter)]["candidates"]}
            a, b = (options[j] for j in (ra, rb))
            if not all(s["passed_fractional_margin_gate"] for s in (a, b)):
                raise ValueError("pair epoch does not reproduce a verified native gate")
            if (
                max(
                    abs(pairs.fold(c - v["fractional_tracking_cfo_hz"]))
                    for c, v in ((left, a), (right, b))
                )
                > 1e-6
            ):
                raise ValueError("pair timing uses a different measured CFO candidate")

            def phase(s):
                return s["integer_epoch_sample"] + s["fractional_epoch_offset_samples"]

            epoch.append(float(pairs.fold(phase(a) - phase(b), capture.sample_rate_hz / 750)))
            times.append(t)
            CFO.append(left - right)
        t = np.asarray(times)
        blocks = np.split(np.arange(len(t)), np.flatnonzero(np.diff(t) > 3) + 1)
        for keep in blocks:
            span = np.ptp(t[keep])
            if len(keep) >= 10 and span >= 6:
                score = closure(
                    t[keep],
                    np.asarray(epoch)[keep],
                    np.asarray(CFO)[keep],
                    lane[2],
                    capture.sample_rate_hz,
                )
                rows.append(
                    dict(
                        block=block, channel=lane[1], points=len(keep), span_s=float(span), **score
                    )
                )
    groups = {row["block"] for row in rows if row["qualified"]}
    a, b = len({x for x in groups if x % 3 != 1}), len({x for x in groups if x % 3 == 1})
    return dict(
        pieces=rows,
        qualified_train_blocks=a,
        qualified_held_blocks=b,
        geometry_eligible=min(a, b) >= 2,
    )


def unique_clock_samples(stream, period):
    result = []
    for _, t, left, right in stream:
        if int(t // 30) % 3 == 1:
            continue
        i, j, de, df = hardware.edges(left, right, period)
        both = left[i, 3].astype(bool) & right[j, 3].astype(bool)
        errors, offsets = np.abs(de[both]), df[both]
        order = np.argsort(errors)
        if len(order) and (
            len(order) == 1 or errors[order[1]] - errors[order[0]] >= SEPARATION_SAMPLES
        ):
            result.append((t, float(offsets[order[0]])))
    return np.asarray(result).reshape(-1, 2)


def channel_fit(points, middle):
    train = points[points[:, 0] % 30 < 18]
    check = points[points[:, 0] % 30 >= 18]
    metrics = dict(train_points=len(train), check_points=len(check), eligible=False)
    if len(train) < 15 or len(check) < 15:
        return metrics
    bins, count = np.unique(np.rint(train[:, 1] / 100), return_counts=True)
    offset = 100 * bins[count.argmax()]
    drift, head = 0.0, None
    for _ in range(3):
        delta = pairs.fold(train[:, 1] - offset - drift * (train[:, 0] - middle))
        group = np.floor(train[:, 0] / 15)
        head = np.array(
            [
                (np.median(train[m, 0]), np.median(delta[m]))
                for k in np.unique(group)
                if np.count_nonzero(m := (group == k) & (abs(delta) <= GATE_HZ)) >= 3
            ]
        ).reshape(-1, 2)
        if len(head) < 5 or np.ptp(head[:, 0]) < 100:
            return metrics
        t, y = head.T
        X = np.column_stack((np.ones(len(t)), t - middle))
        add = np.linalg.lstsq(X, y, rcond=None)[0]
        offset, drift = float(pairs.fold(offset + add[0])), drift + add[1]
    check_residual = pairs.fold(check[:, 1] - offset - drift * (check[:, 0] - middle))
    agree = abs(check_residual) <= GATE_HZ
    if agree.sum() < 15 or agree.mean() < 0.65 or len(set(check[agree, 0] // 15)) < 3:
        return metrics
    rms = float(np.sqrt(np.mean(check_residual**2)))
    sigma = max(1.5, rms / np.sqrt(np.sum((head[:, 0] - head[:, 0].mean()) ** 2)))
    return metrics | dict(
        eligible=rms <= 300 and sigma <= 10 and abs(drift) <= 30,
        relative_hz_s=float(drift),
        slope_sigma_hz_s=float(sigma),
        check_rms_hz=rms,
        check_inliers=int(agree.sum()),
        offset_hz=offset,
    )


def rates(capture):
    stream, raw = hardware.synchronized(capture, False)
    by_path = defaultdict(list)
    for (channel, rf), window in sorted(stream.items()):
        data = unique_clock_samples(window, capture.sample_rate_hz / 750)
        fitted = channel_fit(data, capture.duration_s / 2)
        by_path[int(channel > 4)].append(dict(channel=channel, rf_hz=rf, **fitted))
    bands = {}
    for band, lane in by_path.items():
        use = [r for r in lane if r["eligible"]]
        estimate = None
        if len(use) >= 2:
            y = np.array([r["relative_hz_s"] for r in use])
            s = np.array([r["slope_sigma_hz_s"] for r in use])
            if np.ptp(y) <= max(4, 2.5 * np.hypot(s.min(), s.max())):
                estimate = dict(
                    relative_hz_s=float(np.average(y, weights=1 / s**2)),
                    sigma_hz_s=float(max(1.5, np.std(y), np.sqrt(1 / np.sum(1 / s**2)))),
                    channels=[r["channel"] for r in use],
                )
        bands[band] = dict(channels=lane, relative_prior=estimate)
    return dict(same_receiver_time_rf=raw["simultaneous_same_rf_visits"], bands=bands)
