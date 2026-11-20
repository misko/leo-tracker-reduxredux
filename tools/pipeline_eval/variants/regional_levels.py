"""Evaluate the absolute-Doppler receiver on equal offered and exterior cells."""

from itertools import product
from time import perf_counter

import numpy as np

from leo.sky.frames import geodetic_to_ecef_km

from . import absolute_doppler as world

METHOD = "regional_levels"
CONTROL = "regional_free_offset"
BOUNDARY = "Anonymous native GLRT, causal TLE and offered tile through fixed regional CFO grids"
REGIONS = dict(inside=(0, 0), east=(50, 0), west=(-50, 0), north=(0, 50), south=(0, -50))


def cells(tile):
    center = tile["center"]
    if (
        float(tile.get("width_km", 25.0)) != 25
        or len(center) != 2
        or not np.isfinite(center).all()
        or abs(center[0]) > 90
        or abs(center[1]) > 180
    ):
        raise ValueError("regional search needs one valid 25 km square")
    steps = range(-10, 11, 5)
    return {
        name: [world.geodesy._offset(center, e + x, n + y) for x, y in product(steps, repeat=2)]
        for name, (e, n) in REGIONS.items()
    }


def geographic_gap(winner, rivals):
    xyz = geodetic_to_ecef_km(*winner["point"], 0)
    costs = [
        r["held_score"]
        for r in rivals
        if np.linalg.norm(geodetic_to_ecef_km(*r["point"], 0) - xyz) >= 30
    ]
    return min(costs) - winner["held_score"] if costs else None


def supported(value):
    return (
        value["held_good_orbits"] >= 4
        and value["held_good_carriers"] >= 3
        and value["held_good_groups"] >= 2
    )


def profile(states, numbers, arcs, row, mode, points):
    valid = [i for i, r in enumerate(row.assignments[mode]) if r is not None]
    if len(valid) < 3:
        return None
    measured = [arcs[i] for i in valid]
    chosen = [row.assignments[mode][i] for i in valid]
    f, y, use, group, rf = world.exact(states, measured, row.point, chosen)
    length = np.array([len(a.time) for a in measured])
    end = np.cumsum(length)[:-1]
    owners = [int(numbers[r[0]]) for r in chosen]
    offset = world.physical.fold(
        np.array(
            [
                r[2] if mode else row.levels[0][a.group]
                for a, r in zip(measured, chosen, strict=True)
            ]
        )
    )
    early = [
        float(res[: a.train].mean()) for a, res in zip(measured, np.split(y - f, end), strict=True)
    ]
    alias = np.rint((np.asarray(early) - offset) / world.physical.PERIOD_HZ).astype(int)
    base = np.repeat(offset + alias * world.physical.PERIOD_HZ, length)
    design = np.repeat(np.eye(len(valid)), length, axis=0) if mode else np.eye(4)[group]
    rf_contrast = not mode and any(len(set(rf[group == g])) >= 2 for g in np.unique(group))
    models = [design, np.column_stack((design, rf / 1e9 - 11.5)) if rf_contrast else design]
    states_at_sites = {}
    for point in points:
        pred, *_ = world.exact(states, measured, point, chosen)
        result = {}
        for i, arm in enumerate(world.physical.ARMS):
            fitted = bool(i and rf_contrast)
            x, residual = world.clock_fit(y - pred - base, models[i], use, fitted)
            held = [r[a.train :] for r, a in zip(np.split(residual, end), measured, strict=True)]
            good = np.asarray([world.physical.rmshz(r) <= 1200 for r in held])
            costs = [np.minimum(np.log1p((h / 500) ** 2).mean(), world.CEILING) for h in held]
            result[arm] = dict(
                point=list(point),
                train_score=float(np.log1p((residual[use] / 500) ** 2).mean()),
                held_score=float(
                    (sum(costs) + (len(arcs) - len(valid)) * world.CEILING) / len(arcs)
                ),
                rf_rms_hz=world.physical.rmshz(residual[use]),
                held_rms_hz=world.physical.rmshz(residual[~use]),
                held_points=int((~use).sum()),
                held_good_orbits=len(set(np.asarray(owners)[good])),
                held_good_groups=len({a.group for a, ok in zip(measured, good, strict=True) if ok}),
                held_good_carriers=len({a.rf for a, ok in zip(measured, good, strict=True) if ok}),
                c_hz_per_ghz=float(x[-1]) if fitted else (None if i else 0.0),
                c_identifiable=rf_contrast,
            )
        states_at_sites[tuple(point)] = result
    factors = [
        dict(
            receiver=a.group // 2,
            channel=a.channel,
            rf_hz=a.rf,
            norad=n,
            phase_s=r[1],
            held_start=a.train,
            time_s=a.time.tolist(),
            cfo_hz=a.frequency.tolist(),
        )
        for a, n, r in zip(measured, owners, chosen, strict=True)
    ]
    best = {
        arm: min((d[arm] for d in states_at_sites.values()), key=lambda d: d["train_score"])
        for arm in world.physical.ARMS
    }
    return dict(
        best=best, points=states_at_sites, owners=owners, aliases=alias.tolist(), factors=factors
    )


def finish(arcs, states, numbers, lattice, coarse, mode, metrics):
    start = perf_counter()
    metrics = dict(metrics)
    arms = {a: dict(latlon=None, forced_latlon=None) for a in world.physical.ARMS}
    profiles = {
        name: profile(
            states, numbers, arcs, min(fits, key=lambda s: s.losses[mode]), mode, lattice[name]
        )
        for name, fits in coarse.items()
    }
    primary = profiles.get("inside")
    reason = "insufficient_supported_orbits" if coarse else "insufficient_anonymous_arcs"
    if primary is not None:
        reason = None
        for arm in world.physical.ARMS:
            row = primary["best"][arm]
            center = primary["points"][lattice["inside"][12]][arm]
            rivals = [d["best"][arm] for n, d in profiles.items() if n != "inside" and d]
            gap = geographic_gap(row, rivals)
            local = [p[arm]["held_score"] for p in primary["points"].values()]
            arms[arm] = dict(
                row,
                latlon=None,
                forced_latlon=row["point"],
                selected_norads=primary["owners"],
                train_aliases=primary["aliases"],
                held_geographic_lead=gap,
                center_rf_rms_hz=center["rf_rms_hz"],
                center_held_rms_hz=center["held_rms_hz"],
                center_held_score=center["held_score"],
                inside_held_cost_span=max(local) - min(local),
                exterior=[
                    {k: r[k] for k in ("point", "held_score", "held_rms_hz")} for r in rivals
                ],
            )
            if not supported(row):
                reason = reason or "insufficient_held_absolute_frequency_support"
            if row["held_rms_hz"] > 750 or gap is None or gap < 0.65:
                reason = reason or "ambiguous_regional_position"
        if reason is None:
            for a in arms.values():
                a["latlon"] = a["forced_latlon"]
        metrics["selected_factors"] = primary["factors"]
        metrics["exact_sites"] = sum(len(row["points"]) for row in profiles.values() if row)
        metrics["inside_profile"] = {
            arm: [
                {k: row[arm][k] for k in ("point", "train_score", "held_score", "held_rms_hz")}
                for row in primary["points"].values()
            ]
            for arm in world.physical.ARMS
        }
    metrics["final_fit_s"] = perf_counter() - start
    return dict(
        status="withheld" if reason else "ok",
        reason=reason,
        boundary=BOUNDARY,
        arms=arms,
        metrics=metrics,
    )


def paired(capture, tile):
    start = perf_counter()
    lattice = cells(tile)
    _, tracks, counts = world.raw.observations(capture, False)
    states, numbers, sky = world.bank(capture)
    arcs = world.arc_data(tracks, states)
    coarse = (
        {name: [world.evaluate(arcs, p) for p in points] for name, points in lattice.items()}
        if len(arcs) >= 4
        else {}
    )
    metrics = dict(
        counts,
        **sky,
        selected_arcs=len(arcs),
        anonymous_arcs=len(tracks),
        accounted_orbits=len(numbers),
        supplied_location=True,
        coarse_sites=sum(map(len, coarse.values())),
        evaluated_cells=lattice if coarse else {},
        shared_search_s=perf_counter() - start,
    )
    return [finish(arcs, states, numbers, lattice, coarse, mode, metrics) for mode in range(2)]
