"""Replay anonymous Doppler inflection times against past-only Starlink TLEs."""

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from bench import CASES, PANEL, latlon
import cold_replay as cold
from check import pass_center_time
from winner_to_fix import track_document, winners


HALF_BOX = PANEL["box_width_km"] / 2
GRID_AXIS = np.linspace(-HALF_BOX, HALF_BOX, 21)
GRID = np.stack(np.meshgrid(GRID_AXIS, GRID_AXIS), axis=-1).reshape(-1, 2)
PROFILE_DELTA = 4.61
FAR_DISTANCE_KM = 5.
OUTLIER_COST = 2.5**2
MIN_MATCHES = 4
TIMING_FLOOR_S = 1.25
CLUSTER_WIDTH_S = .65
ROTATIONS = np.arange(1, 20) / 20.
OFFSET_STRESS_HZ_PER_GHZ = 120_000.


def extract(rows, deadline, half_probe, *, rf_offset=0.):
    """Compress a prefix of causal track updates to event time and repeatability."""
    prefix = [row for row in rows if row[4] + half_probe <= deadline + 1e-8]
    document, counts = track_document(prefix)
    marks = []
    for track in document["tracks"]:
        t, y = track["times"], track["values"]
        if len(t) < 16 or t[-1] - t[0] < 20.:
            continue
        y = y + rf_offset * (track["rf_hz"] / 1e9 - 11.5)
        y = y - y.mean()
        even, odd = (pass_center_time(t, y, parity) for parity in (0, 1))
        if even is not None and odd is not None and abs(even - odd) <= 1.:
            marks.append(((even + odd) / 2., abs(even - odd) / 2.))

    # One satellite can produce simultaneous tracks on several receiver/channel lanes.
    # Each cluster has bounded total width, so repeats cannot chain across the scan.
    clusters = []
    for mark in sorted(marks):
        if not clusters or mark[0] - clusters[-1][0][0] > CLUSTER_WIDTH_S:
            clusters.append([])
        clusters[-1].append(mark)
    events = np.asarray([
        (statistics.mean(m[0] for m in cluster),
         max(max(m[1] for m in cluster), (cluster[-1][0] - cluster[0][0]) / 2.))
        for cluster in clusters
    ]).reshape(-1, 2)
    counts.update(winners=len(prefix), stable_raw=len(marks), events=len(events))
    return events, counts


def read_catalog(case, meta):
    cutoff = meta["causal_cutoff_utc_ns"]
    oldest = cutoff - 48 * 3600 * 10**9
    paths = sorted((cold.INPUT / case / "tle").rglob("*.tle"))
    eligible = [p for p in paths if oldest <= int(p.name.split("-")[0]) <= cutoff]
    snapshot = eligible[-1]
    raw = snapshot.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == snapshot.stem.split("-")[1]
    catalog = cold.parse_element_sets(raw.decode())
    rows = [sat for sat, name, epoch in zip(
        catalog.satellites, catalog.names, catalog.element_epoch_utc_ns(), strict=True
    ) if "STARLINK" in name.upper() and oldest <= epoch <= cutoff]
    assert rows and len({sat.satnum for sat in rows}) == len(rows)
    return rows, snapshot.name


def roots(p, v, knots, xy):
    """First convex Doppler inflection with negative slope and visible LOS per orbit."""
    f, _, _, up = cold.projection(p, v, xy)
    h = knots[1] - knots[0]
    # Five-point central stencil for d²f/dt² and linear interpolation of its zero.
    a = (-f[:, 4:] + 16. * f[:, 3:-1] - 30. * f[:, 2:-2]
         + 16. * f[:, 1:-3] - f[:, :-4]) / (12. * h*h)
    left, right = a[:, :-1], a[:, 1:]
    candidates = (left < 0.) & (right >= 0.) & (f[:, 3:-2] < f[:, 2:-3])
    candidates &= (up[:, 3:-2] > -.01) | (up[:, 2:-3] > -.01)
    i, j = np.nonzero(candidates)
    first = np.r_[True, i[:-1] != i[1:]][:len(i)]
    i, j = i[first], j[first]
    offset = -left[i, j] / (right[i, j] - left[i, j])
    t = np.full(len(p), np.nan)
    t[i] = knots[j + 2] + h * offset
    return t


def predict(case, meta):
    rows, snapshot = read_catalog(case, meta)
    anchor, duration = meta["anchor_utc_ns"], meta["duration_s"]
    coarse = np.arange(0., duration + 60., 60.)
    err, p, v = cold.state(rows, anchor, coarse)
    up = cold.projection(p, v, (0., 0.))[-1]
    visible = (err == 0).all(axis=1) & (up.max(axis=1) >= -.06)
    regional = [sat for sat, keep in zip(rows, visible, strict=True) if keep]
    knots = np.arange(-10., duration + 11., 2.)
    err, p, v = cold.state(regional, anchor, knots)
    dense_state_bytes = p.nbytes + v.nbytes
    valid = (err == 0).all(axis=1)
    ids = np.array([sat.satnum for sat in regional])[valid]
    p, v = p[valid], v[valid]
    center = roots(p, v, knots, (0., 0.))
    # Keep passes straddling either scan edge under the regional position prior.
    keep = np.isfinite(center) & (center >= -4.) & (center <= duration + 4.)
    p, v, center, ids = p[keep], v[keep], center[keep], ids[keep]
    gradients = np.stack([
        (roots(p, v, knots, delta) - roots(p, v, knots, -delta)) / 2.
        for delta in np.eye(2)
    ], axis=1)
    keep = np.isfinite(gradients).all(axis=1)
    center, ids, gradients = center[keep], ids[keep], gradients[keep]
    bank = (center, gradients, ids)
    sizes = dict(snapshot=snapshot, causal_elements=len(rows), regional_elements=len(regional),
                 predicted_events=len(center), array_bytes=sum(a.nbytes for a in bank),
                 dense_state_bytes=dense_state_bytes)
    return bank, sizes


def check_projection(case, meta, bank):
    """Compare the linear timing model to independent, finer SGP4 trajectories."""
    center, gradients, ids = bank
    if not len(ids):
        return {}
    by_id = {sat.satnum: sat for sat in read_catalog(case, meta)[0]}
    knots = np.arange(-10., meta["duration_s"] + 11., .5)
    err, p, v = cold.state([by_id[i] for i in ids], meta["anchor_utc_ns"], knots)
    assert (err == 0).all()
    centered = center - roots(p, v, knots, (0., 0.))
    errors = np.concatenate([
        center + gradients @ xy - roots(p, v, knots, xy)
        for xy in GRID[[0, 20, -21, -1]]
    ])
    valid = np.isfinite(errors)
    return dict(
        centered_max_abs_s=float(np.max(np.abs(centered))),
        corner_p95_abs_s=float(np.percentile(np.abs(errors[valid]), 95.)),
        corner_max_abs_s=float(np.max(np.abs(errors[valid]))),
        corner_missing=int(np.count_nonzero(~valid))
    )


def pair_cost(target, predicted, sigma):
    res2 = ((target[:, None] - predicted[None, :]) / sigma[:, None])**2
    return np.concatenate([res2, np.full((len(target), len(target)), OUTLIER_COST)], axis=1)


def match(target, predicted, sigma):
    cost = pair_cost(target, predicted, sigma)
    i, j = linear_sum_assignment(cost)
    return float(cost[i, j].sum()), j


def profile(times, sigma, table):
    """Exact injective assignment with independent outlier slots at each grid cell."""
    loss = np.array([match(times, predicted, sigma)[0] for predicted in table])
    k = loss.argmin()
    _, owners = match(times, table[k], sigma)
    return loss, k, owners


def analyze(events, bank, duration):
    predicted, gradients, ids = bank
    if len(events) < MIN_MATCHES:
        return dict(status="abstain", reason="fewer than four event clusters"), {}
    if not len(predicted):
        return dict(status="abstain", reason="no causal TLE event candidates"), {}

    times, repeatability = events.T
    sigma = np.hypot(repeatability, TIMING_FLOOR_S)
    table = predicted + GRID @ gradients.T
    table_bytes = table.nbytes
    loss, k, owners = profile(times, sigma, table)
    xy = GRID[k]
    found = owners < len(predicted)
    used = owners[found]
    residual = times[found] - table[k, used]
    distance = np.linalg.norm(GRID - xy, axis=1)
    plausible = loss - loss[k] <= PROFILE_DELTA
    chi = loss[k]
    far_delta = (loss[distance >= FAR_DISTANCE_KM] - chi).min()
    # If identities were fixed to the chosen assignment, the timing design alone
    # predicts these coordinate sensitivities; all competition stays in the grid profile.
    singular = np.linalg.svd(gradients[used] / sigma[found, None], compute_uv=False)
    weak_std = 1. / singular[-1] if len(singular) == 2 and singular[-1] > 1e-10 else None
    conditional_std = [float(1. / s) if s > 1e-10 else None for s in singular]
    ties = np.sum(np.abs(times[:, None] - table[k]) <= 2.5 * sigma[:, None], axis=1)
    null_loss = [
        float(profile((times + rotate * duration) % duration, sigma, table)[0].min())
        for rotate in ROTATIONS
    ]
    null_rank = float((1 + np.count_nonzero(np.asarray(null_loss) <= chi)) / (1 + len(null_loss)))
    changed = []
    for kk in np.flatnonzero(plausible & (distance >= FAR_DISTANCE_KM)):
        _, competing = match(times, table[kk], sigma)
        changed.append(np.count_nonzero(competing[found] != owners[found]))

    details = dict(
        forced_grid_xy_km=xy.tolist(), shadow_grid_latlon=latlon(xy), best_cost=float(chi),
        matched_events=len(used), conditional_timing_rms_s=float(np.sqrt(np.mean(residual**2)))
        if len(residual) else None, assignments=ids[used].tolist(),
        median_eligible_competitors_at_best=float(np.median(ties)),
        max_eligible_competitors_at_best=int(ties.max()),
        conditional_axis_std_km=conditional_std,
        grid_candidates=len(table), grid_table_bytes=table_bytes, plausible_cells=int(plausible.sum()),
        max_plausible_displacement_km=float(distance[plausible].max()),
        min_far_cost_delta=float(far_delta), most_changed_far_assignments=int(max(changed, default=0)),
        circular_time_shift_empirical_rank=null_rank, circular_time_shift_costs=null_loss,
        event_time_gradient_median_s_per_km=float(np.median(np.linalg.norm(gradients, axis=1))),
        event_time_gradient_max_s_per_km=float(np.max(np.linalg.norm(gradients, axis=1))),
    )
    failed = []
    if len(used) < MIN_MATCHES:
        failed.append("fewer than four assigned events")
    if weak_std is None or weak_std > FAR_DISTANCE_KM:
        failed.append("weak conditional geometry")
    if far_delta <= PROFILE_DELTA:
        failed.append("competing positions at least five kilometres away")
    if null_rank > 1. / (1 + len(null_loss)):
        failed.append("time-shift control matches or beats event cost")
    if np.any(np.abs(xy) == HALF_BOX):
        failed.append("search-box boundary")
    details["failed_gates"] = failed
    if failed:
        return dict(status="abstain", reason=failed[0]), details
    return dict(status="estimate", latlon=latlon(xy), rms_hz=None), details


def correctness():
    t = np.linspace(0, 50, 101)
    y = 73_000. - 2_500. * (t - 22.75) + .8 * (t - 22.75)**3
    for parity in (0, 1):
        root = pass_center_time(t, y, parity)
        shifted = pass_center_time(t, y + 230_000. + 7. * t, parity)
        assert abs(root - 22.75) < 1e-8 and abs(root - shifted) < 1e-8

    cost, owners = match(np.array([7., 7.02, 100.]), np.array([7., 90.]), np.ones(3))
    assert (owners < 2).sum() == 1 and owners[0] == 0 and cost == 2. * OUTLIER_COST

    grid_target = np.array([3.75, -5.])
    base = np.linspace(10., 225., 12)
    angle = np.linspace(0., 2 * np.pi, len(base), endpoint=False)
    gradients = .22 * np.column_stack([np.cos(angle), np.sin(angle)])
    marks = np.column_stack([base + gradients @ grid_target, np.zeros(len(base))])
    result, receipt = analyze(marks, (base, gradients, np.arange(len(base))), 300.)
    assert result["status"] == "estimate", receipt
    assert receipt["forced_grid_xy_km"] == grid_target.tolist()
    return dict(synthetic_affine_track_root_error_s=abs(root - 22.75),
                synthetic_assignment_unique=True, synthetic_grid_target_km=grid_target.tolist())


def replay(case):
    native = json.loads((cold.INPUT / case / "native.json").read_bytes())
    half_width = (native["clock_anchor"]["after"]["realtime_ns"]
                  - native["clock_anchor"]["before"]["realtime_ns"]) / 2e9
    wall = time.perf_counter()
    rows, meta, half_probe = winners(native)
    duration = meta["duration_s"]
    events, counts = extract(rows, duration, half_probe)
    after_events = time.perf_counter()
    bank, catalog = predict(case, meta)
    after_bank = time.perf_counter()
    arm, checks = analyze(events, bank, duration)
    finish = time.perf_counter()
    # c changes constant per-track CFO only, hence there is no coefficient to fit.
    marks_shift, _ = extract(rows, duration, half_probe, rf_offset=OFFSET_STRESS_HZ_PER_GHZ)
    max_offset_diff = float(np.max(np.abs(events - marks_shift), initial=0.))
    assert events.shape == marks_shift.shape and max_offset_diff < 1e-8
    shifted_arm, shifted_checks = analyze(marks_shift, bank, duration)
    assert shifted_arm == arm
    assert shifted_checks.keys() == checks.keys()
    if checks:
        assert shifted_checks["assignments"] == checks["assignments"]
        assert abs(shifted_checks["best_cost"] - checks["best_cost"]) < 1e-8

    prefixes = []
    for deadline in (90., 180., 240.):
        prior_events, prior_counts = extract(rows, deadline, half_probe)
        pt, pg, pi = bank
        prior = pt <= deadline + 4.
        prefix_arm, prefix_checks = analyze(prior_events, (pt[prior], pg[prior], pi[prior]), deadline)
        prefixes.append(dict(deadline_air_s=deadline, counts=prior_counts,
                             primary_arm=prefix_arm, diagnostics=prefix_checks))
    checks.update(counts=counts, catalog=catalog, utc_anchor_half_width_s=half_width,
                  decision_air_s=duration, event_times_s=events[:, 0].tolist(),
                  split_or_repeat_scatter_s=events[:, 1].tolist(), prefixes=prefixes,
                  projection=check_projection(case, meta, bank),
                  c_offset_stress_max_event_difference_s=max_offset_diff,
                  winner_and_event_extraction_wall_s=after_events - wall,
                  causal_catalog_and_projection_wall_s=after_bank - after_events,
                  matching_and_shift_controls_wall_s=finish - after_bank)
    return dict(case=case, wall_s=finish - wall, arms=dict(c0=arm, fitted_c=shifted_arm)), checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="run the local synthetic checks only")
    parser.add_argument("--output", type=Path, default=HERE / "result.json")
    args = parser.parse_args()
    check = correctness()
    if args.check:
        print(json.dumps(check))
        return
    cases, details = [], {}
    for case in CASES:
        row, receipt = replay(case)
        cases.append(row)
        details[case] = receipt
        print(case, row["arms"]["c0"], receipt["counts"]["events"], flush=True)
    result = dict(
        method="anonymous Doppler inflection time with injective past-TLE matching",
        timing_scope="Full scan detector export to position decision, inclusive of winner selection, "
        "linking, time extraction, causal TLE I/O, propagation, matching and 19 rotated-time controls. "
        "Excludes RF acquisition, detector, JSON hydration, prefix diagnostics and duplicate invariance run.",
        cases=cases,
        checks=dict(synthetic=check, c_parameter_identifiable=False,
                    c_offset_stress_hz_per_ghz=OFFSET_STRESS_HZ_PER_GHZ, case_diagnostics=details),
    )
    args.output.write_text(json.dumps(result, allow_nan=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
