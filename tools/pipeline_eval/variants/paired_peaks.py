"""Merge native simultaneous same-pilot peaks before narrow orbital path decoding."""

from collections import defaultdict
from time import perf_counter

import numpy as np

from . import peak_paths as stock

METHOD = "paired_peaks"
BOUNDARY = "Simultaneous native GLRT factors through relative receiver calibration and fused paths"
FRAME_RATE = 750.0
FRAME_TOLERANCE = 1.25
PAIR_HZ = 650.0
LIMIT = 128
RAW_RANKS = 6


def circular(value, period):
    return value - period * np.rint(value / period)


def peaks(probe):
    cells = []
    for j, c in enumerate(
        sorted(probe["candidates"], key=lambda p: p["candidate_rank"])[:RAW_RANKS]
    ):
        frame = c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"]
        y = stock.fold(c["fractional_tracking_cfo_hz"])
        margin = c["fractional_margin"]
        gate = bool(c["passed_fractional_margin_gate"])
        if not np.isfinite([frame, y, margin]).all():
            raise ValueError("invalid native candidate")
        prior = (0.95 if gate else -0.9) + np.clip(margin / 0.1, -1, 1) - 0.18 * j
        if not any(abs(frame - a) < 0.5 and abs(stock.fold(y - b)) < 120 for a, b, _, _ in cells):
            cells.append((frame, y, prior, gate))
    return np.asarray(cells, dtype=float).reshape(-1, 4)


def edges(left, right, period):
    delta_time = circular(right[None, :, 0] - left[:, None, 0], period)
    delta_hz = stock.fold(right[None, :, 1] - left[:, None, 1])
    i, j = np.nonzero(abs(delta_time) <= FRAME_TOLERANCE)
    return i, j, delta_time[i, j], delta_hz[i, j]


def synchronized(capture, misalign):
    by_visit = defaultdict(dict)
    for p in capture.probes:
        recv = p["receiver_id"]
        if recv in by_visit[p["visit_index"]] or recv not in (0, 1):
            raise ValueError("ambiguous physical receiver identity")
        by_visit[p["visit_index"]][recv] = p
    streams = defaultdict(list)
    unsupported = 0
    for visit, duo in sorted(by_visit.items()):
        same = (
            0 in duo
            and 1 in duo
            and all(
                duo[0][k] == duo[1][k]
                for k in ("valid_start_counter", "actual_rf_hz", "channel", "probe_start_ms")
            )
        )
        if not same:
            unsupported += 1
            continue
        left, right = duo[0], duo[1]
        t = (
            left["valid_start_counter"] - capture.first_counter
        ) / capture.sample_rate_hz + capture.probe_ms / 2000
        if not 0 <= t <= capture.duration_s or left["probe_start_ms"] != 0:
            raise ValueError("unsupported native acquisition timing")
        streams[left["channel"], left["actual_rf_hz"]].append((visit, t, peaks(left), peaks(right)))
    if misalign:
        for lane in streams.values():
            replacement = np.roll(np.arange(len(lane)), 127)
            shifted = [lane[j][3] for j in replacement]
            lane[:] = [(*value[:3], r) for value, r in zip(lane, shifted, strict=True)]
    return streams, dict(
        native_probe_rows=len(capture.probes),
        physical_visit_opportunities=len(by_visit),
        simultaneous_same_rf_visits=sum(map(len, streams.values())),
        unsupported_visits=unsupported,
    )


def nearest(points, center, drift, mid, limit=PAIR_HZ):
    result = []
    for t, visit, delta_s, delta_hz in points:
        offset = center + drift * (t - mid)
        raw = stock.fold(delta_hz - offset)
        i = int(np.argmin(abs(raw)))
        if abs(raw[i]) <= limit:
            result.append((t, visit, delta_s[i], raw[i]))
    return np.asarray(result, dtype=float).reshape(-1, 4)


def calibrate(points, duration):
    train = [r for r in points if r[0] % 60 < 27]
    check = [r for r in points if r[0] % 60 >= 48]
    final = [r for r in points if 30 <= r[0] % 60 < 45]
    info = dict(
        near_epoch_training_visits=len(train),
        near_epoch_calibration_check_visits=len(check),
        near_epoch_final_visits=len(final),
        supported=False,
    )
    if len(train) < 16:
        return info
    tally = defaultdict(int)
    for _, _, _, d in train:
        for key in set(np.rint(d / 500).astype(int)):
            tally[int(key)] += 1
    mid = duration / 2
    offset = 500 * max(tally, key=tally.get)
    drift = 0.0
    for _ in range(3):
        use = nearest(train, offset, drift, mid, limit=1000.0)
        if len(use) < 16:
            return info
        bin_id = np.floor(use[:, 0] / 15).astype(int)
        block = np.array(
            [
                np.median(use[bin_id == key], axis=0)
                for key in np.unique(bin_id)
                if np.count_nonzero(bin_id == key) >= 3
            ]
        )
        if len(block) >= 3 and np.ptp(block[:, 0]) >= 60:
            A = np.column_stack((np.ones(len(block)), block[:, 0] - mid))
            change, gradient = np.linalg.lstsq(A, block[:, 3], rcond=None)[0]
            drift = float(np.clip(drift + gradient, -15, 15))
        else:
            change = np.median(use[:, 3])
        offset = float(stock.fold(offset + change))
    trained = nearest(train, offset, drift, mid)
    validation = nearest(check, offset, drift, mid)
    later = nearest(final, offset, drift, mid)
    bins = len(np.unique(np.floor(validation[:, 0] / 15)))
    info.update(
        supported=bool(len(trained) >= 16 and len(validation) >= 8 and bins >= 2),
        offset_hz=offset,
        drift_hz_per_s=drift,
        aligned_training=len(trained),
        aligned_calibration_check=len(validation),
        calibration_check_blocks=bins,
        aligned_final_hold=len(later),
        final_relative_cfo_rms_hz=float(np.sqrt(np.mean(later[:, 3] ** 2))) if len(later) else None,
        final_epoch_rms_samples=float(np.sqrt(np.mean(later[:, 2] ** 2))) if len(later) else None,
    )
    return info


def fused_visit(left, right, index, shift):
    i, j, _, delta = index
    err = stock.fold(delta - shift)
    compatible = [
        k
        for k in np.argsort(abs(err))
        if abs(err[k]) <= PAIR_HZ and (left[i[k], 3] or right[j[k], 3])
    ]
    a, b, offer = set(), set(), []
    for k in compatible:
        p, q = int(i[k]), int(j[k])
        if p in a or q in b:
            continue
        a.add(p)
        b.add(q)
        quality = max(left[p, 2], right[q, 2]) + 0.46
        offer.append((quality, float(stock.fold(left[p, 1] + err[k] / 2)), True))
    for lane, used, translation in ((left, a, 0.0), (right, b, shift)):
        for j, row in enumerate(lane):
            if j not in used:
                offer.append((row[2] - 0.48, float(stock.fold(row[1] - translation)), False))
    selected = []
    for mark, y, pair in sorted(offer, key=lambda r: (not r[2], -r[0])):
        if all(abs(stock.fold(y - r[1])) > 110 for r in selected):
            selected.append((mark, y, pair))
        if len(selected) >= stock.PEAKS:
            break
    while len(selected) < stock.PEAKS:
        selected.append((-np.inf, 0.0, False))
    return np.asarray(selected)


def observations(capture, misalign=False):
    streams, info = synchronized(capture, misalign)
    epoch_period = capture.sample_rate_hz / FRAME_RATE
    normalized, model = {}, {}
    for band in (0, 1):
        group = {key: lane for key, lane in streams.items() if int(key[0] > 4) == band}
        samples = []
        for key, lane in group.items():
            intermediate = []
            both = 0
            for visit, t, left, right in lane:
                e = edges(left, right, epoch_period)
                i, j, de, df = e
                joint = (left[i, 3] > 0) & (right[j, 3] > 0)
                both += bool((left[:, 3] > 0).any() and (right[:, 3] > 0).any())
                if joint.any():
                    samples.append((t, visit, de[joint], df[joint]))
                intermediate.append((visit, t, left, right, e))
            normalized[key] = intermediate
            info.setdefault("both_gated_by_channel", {})[str(key[0])] = both
        model[band] = calibrate(samples, capture.duration_s)
        model[band]["near_epoch_both_gated_visits"] = len(samples)
    result, paired = [], []
    for key, rows in sorted(normalized.items()):
        estimate = model[int(key[0] > 4)]
        if not estimate["supported"]:
            continue
        data = np.array(
            [
                fused_visit(
                    left,
                    right,
                    pairs,
                    estimate["offset_hz"]
                    + estimate["drift_hz_per_s"] * (t - capture.duration_s / 2),
                )
                for _, t, left, right, pairs in rows
            ]
        )
        result.append(
            stock.Lane(
                (0, *key),
                np.array([r[0] for r in rows]),
                np.array([r[1] for r in rows]),
                np.ascontiguousarray(data[:, :, 1]),
                np.ascontiguousarray(data[:, :, 0]),
            )
        )
        paired.append(data[:, :, 2].astype(bool))
    info.update(
        calibration=model,
        fused_lanes=len(result),
        paired_factors=sum(int(x.sum()) for x in paired),
        fused_peak_factors=sum(int(np.isfinite(r.marks).sum()) for r in result),
        misalign=misalign,
    )
    return result, paired, info


def nominations(bank, lane, paired, phase):
    """Compare short packed CFO increments first, then trace at most LIMIT orbits."""
    t_idx = np.flatnonzero(paired.any(axis=1))
    if len(t_idx) < 3:
        return np.array([], dtype=int)
    peak = np.argmax(paired[t_idx], axis=1)
    t, y = lane.t[t_idx], lane.y[t_idx, peak]
    right = np.searchsorted(t, t + 0.64)
    left = np.flatnonzero(right < len(t))
    left = left[t[right[left]] - t[left] < 2.6]
    if len(left) < 2:
        return np.array([], dtype=int)
    right = right[left]
    target = stock.fold(y[right] - y[left])
    times, index = np.unique(np.r_[t[left], t[right]], return_inverse=True)
    i, j = np.split(index, 2)
    n = len(bank.positions_km)
    scores = np.zeros(n)
    for a in range(0, n, 128):
        orbit = stock.slice_orbit(bank, slice(a, a + 128))
        f = stock.orbit_geometry(
            orbit, times, phase, bank.ecef_center_km, lane.key[2], horizon=True
        )
        error = abs(stock.fold(target - (f[:, j] - f[:, i])))
        score = np.where(np.isfinite(error), np.maximum(0.0, 1.0 - error / 650), 0.0)
        # An orbit needs local support rather than accidental matches across a five-minute dwell.
        block = (t[left] // 30).astype(int)
        sums = np.column_stack([score[:, block == k].sum(axis=1) for k in np.unique(block)])
        scores[a : a + len(f)] = sums.max(axis=1)
    order = np.argsort(-scores, kind="stable")[:LIMIT]
    return order[scores[order] >= 1.35]


def shortlist(bank, lane, paired, lane_index):
    candidates, searched = [], 0
    for phase in stock.PHASES:
        proposed = nominations(bank, lane, paired, phase)
        searched += len(proposed)
        for offset in range(0, len(proposed), 64):
            numbers = proposed[offset : offset + 64]
            small = stock.slice_orbit(bank, numbers)
            f = stock.orbit_geometry(
                small, lane.t, phase, bank.ecef_center_km, lane.key[2], horizon=True
            )
            score, paths = stock.decode(lane, f)
            for i in np.argsort(-score, kind="stable")[:18]:
                use = np.flatnonzero(paths[i] >= 0)
                if len(use) < 12 or np.ptp(lane.t[use]) < 14:
                    continue
                joint = paired[use, paths[i, use]]
                if joint.sum() < 3:
                    continue
                y = lane.y[use, paths[i, use]]
                raw = stock.fold(y - f[i, use])
                level = stock.fold(np.median(raw[0] + stock.fold(raw - raw[0])))
                deviation = stock.fold(raw - level)
                spread = np.sqrt(np.mean(deviation**2))
                t = lane.t[use] - lane.t[use].mean()
                signal = f[i, use] - f[i, use].mean()
                curvature = np.sqrt(np.mean((signal - t * (t @ signal) / (t @ t)) ** 2))
                if spread <= 2200 and curvature >= 100:
                    candidates.append(
                        dict(
                            lane=lane_index,
                            orbit=int(numbers[i]),
                            phase=phase,
                            strength=float(score[i]) / (1 + (spread / 1200) ** 2),
                            offset=float(level),
                            t=lane.t[use],
                            visit=lane.visit[use],
                            y=y,
                            pair_count=int(joint.sum()),
                        )
                    )
    return sorted(candidates, key=lambda p: -p["strength"])[:32], searched


def solve(capture, *, tile, misalign=False):
    begin = perf_counter()
    lanes, paired, metrics = observations(capture, misalign)
    metrics["fusion_s"] = perf_counter() - begin
    arms = {arm: dict(latlon=None, forced_latlon=None) for arm in stock.ARMS}
    reason = "unsupported_paired_receiver_calibration"
    trace = []
    if lanes:
        stage = perf_counter()
        bank, numbers, sky = stock.orbital_bank(capture, tile["center"])
        hour = perf_counter()
        paths, total = [], 0
        for i, lane in enumerate(lanes):
            train, _ = stock.blocks(lane.t)
            selected, n = shortlist(bank, lane.subset(train), paired[i][train], i)
            paths.extend(selected)
            total += n
        chosen, level = stock.choose(lanes, paths)
        kept = perf_counter()
        orbits = len({p["orbit"] for p in chosen})
        channels = len({lanes[p["lane"]].key[1] for p in chosen})
        rf_groups = len(
            {
                g
                for g in (0, 1)
                if len({lanes[p["lane"]].key[2] for p in chosen if lanes[p["lane"]].group == g})
                >= 2
            }
        )
        metrics.update(
            sky,
            orbit_s=hour - stage,
            proposal_decode_s=kept - hour,
            full_orbit_lane_phases=len(numbers) * len(lanes) * len(stock.PHASES),
            decoded_orbit_lane_phases=total,
            path_candidates=len(paths),
            selected_paths=len(chosen),
            selected_orbits=orbits,
            selected_channels=channels,
            independent_rf_clock_groups=rf_groups,
            selected_points=sum(len(p["t"]) for p in chosen),
            selected_paired_points=sum(p["pair_count"] for p in chosen),
        )
        reason = "insufficient_fused_orbital_paths"
        half = float(tile.get("width_km", 25)) / 2
        if orbits >= 4 and channels >= 3 and rf_groups >= 1:
            reason = None
            for arm in stock.ARMS:
                fit = stock.fit(bank, lanes, chosen, level, half, arm == "fitted_c")
                x, _, rms, radius = fit
                validation = stock.held_scores(bank, lanes, chosen, level, fit)
                arms[arm].update(
                    forced_latlon=stock.site(bank, x[:2])[1],
                    rf_rms_hz=rms,
                    radius_km=radius,
                    c_hz_per_ghz=0.0 if arm == "c0" else float(x[10]),
                    **validation,
                )
                if (
                    validation["held_points"] < 25
                    or validation["held_orbits"] < 3
                    or validation["held_blocks"] < 2
                ):
                    reason = "insufficient_contiguous_held_path_support"
                elif np.max(abs(x[:2])) > half - 0.75 or radius > 6:
                    reason = reason or "weak_position_geometry"
            if reason is None:
                for row in arms.values():
                    row["latlon"] = row["forced_latlon"]
        metrics["fit_and_hold_s"] = perf_counter() - kept
        trace = [
            dict(
                norad=numbers[p["orbit"]],
                channel=lanes[p["lane"]].key[1],
                phase_s=p["phase"],
                paired_peaks=p["pair_count"],
                visit_ids=p["visit"].tolist(),
            )
            for p in chosen
        ]
    return dict(
        status="ok" if reason is None else "withheld",
        reason=reason,
        boundary=BOUNDARY,
        metrics=metrics,
        arms=arms,
    ), trace
