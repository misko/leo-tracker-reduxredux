"""Transfer held-tested cross-receiver clock evidence to an anonymous orbital fit."""

from collections import Counter, defaultdict

import numpy as np

from . import clock_geometry as measured
from . import joint_pass as base
from .folded_doppler import _offset

METHOD = "clock_geometry"
BOUNDARY = measured.BOUNDARY
ARMS = measured.ARMS


def band_fit(lanes, middle):
    train, check, offset = {}, {}, {}
    for channel, points in lanes.items():
        learn = points[points[:, 0] % 30 < 18]
        validate = points[points[:, 0] % 30 >= 18]
        if len(learn) < 8 or len(validate) < 4:
            continue
        k, counts = np.unique(np.rint(learn[:, 1] / 100), return_counts=True)
        train[channel], check[channel] = learn, validate
        offset[channel] = float(100 * k[counts.argmax()])
    result = dict(
        eligible=False, input_channels=sorted(train), check_points=sum(map(len, check.values()))
    )
    drift, information = 0.0, 0.0
    for _ in range(3):
        groups = {}
        for lane, data in train.items():
            error = measured.pairs.fold(data[:, 1] - offset[lane] - drift * (data[:, 0] - middle))
            block = data[:, 0] // 15
            spans = []
            for k in np.unique(block):
                use = (block == k) & (abs(error) <= measured.GATE_HZ)
                if use.sum() >= 3:
                    spans.append(
                        (float(np.median(data[use, 0]) - middle), float(np.median(error[use])))
                    )
            if len(spans) >= 2:
                groups[lane] = np.array(spans)
        all_times = [t for arr in groups.values() for t in arr[:, 0]]
        if (
            len(groups) < 2
            or len({int((t + middle) // 15) for t in all_times}) < 5
            or np.ptp(all_times) < 100
        ):
            return result
        signal = sum(
            (q[:, 0] - q[:, 0].mean()) @ (q[:, 1] - q[:, 1].mean()) for q in groups.values()
        )
        information = sum(np.sum((q[:, 0] - q[:, 0].mean()) ** 2) for q in groups.values())
        slope = signal / information
        for lane, q in groups.items():
            offset[lane] = float(
                measured.pairs.fold(offset[lane] + np.mean(q[:, 1] - slope * q[:, 0]))
            )
        drift += slope
    count, bins, residual = {}, set(), []
    for lane in groups:
        v = check[lane]
        e = measured.pairs.fold(v[:, 1] - offset[lane] - drift * (v[:, 0] - middle))
        valid = abs(e) <= measured.GATE_HZ
        bins.update(v[valid, 0] // 15)
        count[lane] = int(valid.sum())
        residual.extend(e)
    n, agreement = len(residual), sum(count.values())
    rms = float(np.sqrt(np.mean(np.square(residual))))
    sigma = max(1.5, rms / np.sqrt(information))
    admitted = (
        agreement >= 15
        and agreement / n >= 0.65
        and len(bins) >= 3
        and sum(x >= 4 for x in count.values()) >= 2
        and abs(drift) <= 30
        and rms <= 300
        and sigma <= 10
    )
    return result | dict(
        eligible=admitted,
        relative_hz_s=float(drift),
        sigma_hz_s=float(sigma),
        check_rms_hz=rms,
        check_agreement=agreement,
        used_check_points=n,
        train_channels=sorted(groups),
        agreeing_check_by_lane=count,
        held_check_groups=len(bins),
    )


def calibrate(capture):
    streams, _ = measured.hardware.synchronized(capture, False)
    raw = defaultdict(dict)
    for (channel, _), rows in streams.items():
        raw[int(channel > 4)][channel] = measured.unique_clock_samples(
            rows, capture.sample_rate_hz / 750
        )
    return {b: band_fit(raw[b], capture.duration_s / 2) for b in (0, 1)}


def relative_normal(H, g, x, relation, blocks):
    extra_loss = 0.0
    for band, row in relation.items():
        v = np.zeros(len(x))
        v[2 + band], v[4 + band] = -1, 1
        error = row["relative_hz_s"] - v @ x
        width = row["sigma_hz_s"]
        extra_loss += (error / width) ** 2 / blocks
        strength = (base.SIGMA / width) ** 2 / blocks
        H += strength * np.outer(v, v)
        g += strength * error * v
    return extra_loss


def normal(arcs, center, x, relation, collect=False):
    score, H, g, owners, rf = base.normal(arcs, x, center, True, collect=collect)
    score += relative_normal(H, g, x, relation, len({a.block for a in arcs}))
    return score, H, g, owners, rf


def fit(arcs, center, seed, relation, fixed=False):
    x = np.zeros(6)
    x[:2] = seed
    span = slice(2, None) if fixed else slice(None)
    current = normal(arcs, center, x, relation)
    for _ in range(6):
        _, H, g, *_ = current
        normal_block = H[span, span] + np.eye(len(g[span])) * 3
        step = np.linalg.solve(normal_block, g[span])
        if np.max(np.abs(step)) < 0.015:
            break
        for fraction in (1.0, 0.5):
            trial = x.copy()
            trial[span] += fraction * step
            trial[2:] = np.clip(trial[2:], -base.MAX_DRIFT, base.MAX_DRIFT)
            if not fixed:
                trial[:2] = np.clip(trial[:2], -12.5, 12.5)
            proposed = normal(arcs, center, trial, relation)
            if proposed[0] < current[0]:
                x, current = trial, proposed
                break
        else:
            break
    return x, normal(arcs, center, x, relation, collect=True)


def solve(train, test, center, relation):
    options = [fit(train, center, seed, relation) for seed in base.STARTS]
    x, (_, H, _, owners, rms) = min(options, key=lambda p: p[1][0])
    blocks = Counter(a.block for a in train)
    retained, radius = base.condition(H, len(blocks))
    _, data, _, _, _ = base.normal(train, x, center, True)
    for a in train:
        data[2 + a.group, 2 + a.group] -= (base.SIGMA / base.DRIFT_SD) ** 2 / (
            len(blocks) * blocks[a.block]
        )
    data_retained, data_radius = base.condition(data, len(blocks))
    h, held_rms, families = base.held(test, center, x, owners, True)
    rivals = [q for q, _ in options if np.linalg.norm(q[:2] - x[:2]) >= 8]
    rivals.extend(
        fit(train, center, p, relation, fixed=True)[0]
        for p in ((0, 0), (45, 0), (-45, 0), (0, 45), (0, -45))
        if np.linalg.norm(p - x[:2]) >= 8
    )
    lead = min(base.held(test, center, q, owners, True)[0] for q in rivals) - h
    relative_z = [
        abs(x[4 + b] - x[2 + b] - v["relative_hz_s"]) / v["sigma_hz_s"] for b, v in relation.items()
    ]
    accepted = (
        families >= 3
        and held_rms is not None
        and held_rms <= 700
        and lead >= 0.15
        and retained >= 0.2
        and radius is not None
        and radius <= 12.5
        and max(relative_z, default=0) <= 3
    )
    return (
        list(_offset(center, *x[:2])),
        accepted,
        dict(
            profiled_radius_km=radius,
            retained_clock_direction=retained,
            data_only_receiver_profile_radius_km=data_radius,
            data_only_receiver_direction_fraction=data_retained,
            train_rms_hz=rms,
            held_rms_hz=held_rms,
            held_families=families,
            held_site_lead=lead,
            estimated_path_drifts_hz_s=x[2:].tolist(),
            relative_compatibility_sigma=relative_z,
        ),
    )


def evaluate(capture, tile, clock):
    center = tile["center"]
    rows, stats = base.extract(capture)
    bank, ids, _ = base.orbit.orbital_bank(capture, center)
    xyz, enu = base.geodetic_to_ecef_km(*center, 0), base.ecef_to_enu_matrix(*center)
    arcs = [a for r in rows if (a := base.shortlist(r, bank, ids, xyz, enu)) is not None]
    train = [a for a in arcs if a.block % 3 != 1]
    support = {i for i in range(4) if len({a.block for a in train if a.group == i}) >= 2}
    test = [a for a in arcs if a.block % 3 == 1 and a.group in support]
    relation = {
        int(k): v
        for k, v in clock.items()
        if v["eligible"] and int(k) in support and int(k) + 2 in support
    }
    ready = len({a.block for a in train}) >= 3
    m = dict(
        stats,
        position_attempted=ready,
        candidate_shapes=sum(len(a.norad) for a in arcs),
        c_identifiable=False,
        c_projected_column_norm=0.0,
        applied_relative_bands=sorted(relation),
    )
    forced, published = None, None
    reason = "insufficient_training_passes"
    if ready:
        forced, accepted, diagnostics = solve(train, test, center, relation)
        m.update(diagnostics)
        published = forced if accepted else None
        reason = None if accepted else "insufficient_held_clock_catalogue_geometry"
    return dict(
        status="withheld" if reason else "ok",
        reason=reason,
        boundary=BOUNDARY,
        metrics=m,
        arms=dict(
            c0=dict(latlon=published, forced_latlon=forced),
            fitted_c=dict(
                latlon=None,
                forced_latlon=None,
                status="unavailable",
                reason="constant_rf_projects_out_with_free_arc_intercepts",
            )
            if ready
            else dict(latlon=None, forced_latlon=None),
        ),
    )
