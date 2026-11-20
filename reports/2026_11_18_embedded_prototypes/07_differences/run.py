"""Scan-end localization from disjoint modulo-CFO changes."""

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
from scipy.optimize import lsq_linear


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bench
import cold_replay as cold


EARLY = np.arange(6)
LATE = np.array([6, 8, 10, 7, 9, 11])
PAIRS = len(EARLY)
DIFF_SD_HZ = np.sqrt(2.0) * cold.SHAPE_SD
DRIFT_SD_HZ_PER_S = 5.0
RF_SD_HZ_PER_GHZ = 200_000.0
GRID = np.linspace(-12.5, 12.5, 7)


def differences(values):
    return values[..., LATE] - values[..., EARLY]


def profile(target, features, xy, *, level=None, level_features=None, bias=None):
    east, north, rate = np.moveaxis(features, -1, 0)
    residual = cold.wrap(target - east * xy[0] - north * xy[1])
    scale = DIFF_SD_HZ**-2
    precision = scale * np.mean(rate**2, axis=-1) + cold.PHASE_SD_S**-2
    rhs = scale * np.mean(rate * residual, axis=-1)
    if level is not None:
        me, mn, mr = np.moveaxis(level_features, -1, 0)
        level_residual = cold.wrap(level - me * xy[0] - mn * xy[1] - bias)
        precision += (mr / cold.LEVEL_SD)**2
        rhs += mr * level_residual / cold.LEVEL_SD**2
    phase = np.clip(rhs / precision, -8.0, 8.0)
    after = cold.wrap(residual - rate * phase[..., None])
    cost = scale * np.mean(after**2, axis=-1) + (phase / cold.PHASE_SD_S)**2
    if level is not None:
        cost += (cold.wrap(level_residual - mr * phase) / cold.LEVEL_SD)**2
    return cost, phase


def prepare(doc, bank, *, levels=False, perturb=False):
    index = sorted(doc["curved_indices"], key=lambda i: -len(doc["tracks"][i]["times"]))[:64]
    rows = []
    evaluated = 0
    for track_id in index:
        track = doc["tracks"][track_id]
        time = np.asarray(track["times"], dtype=float)
        sample = np.rint(np.linspace(0, len(time) - 1, cold.SAMPLES)).astype(int)
        if len(np.unique(sample)) != cold.SAMPLES:
            continue
        time = time[sample]
        visible = np.flatnonzero(cold.interpolate(bank["up"], time, bank).min(axis=1) >= -.008)
        if len(visible) < cold.K:
            continue
        evaluated += len(visible)
        rf_ghz = track["rf_hz"] / 1e9 - 11.5
        ratio = track["rf_hz"] / cold.CARRIER
        lane = 2 * (track["receiver"] - 1) + int(track["channel"] > 4)
        model = [cold.interpolate(bank[name][visible], time, bank) * ratio
                 for name in ("f", "east", "north", "rate")]
        observed = np.asarray(track["values"], dtype=float)[sample]
        if perturb:
            # Independently perturb the arbitrary lift at each sample. Also add
            # a fixed but different offset to every track and a common RF term.
            lift = np.random.default_rng(track_id).integers(-3, 4, size=cold.SAMPLES)
            track_offset = 170_000.0 * np.cos(track_id + .3)
            lane_offset = 93_000.0 * (-1)**lane
            observed = cold.wrap(observed + track_offset + lane_offset + 59_000.0 * rf_ghz)
            observed += cold.PERIOD * lift
        unwrapped_residual = observed - model[0]
        target = cold.wrap(differences(unwrapped_residual))
        features = np.stack([differences(feature) for feature in model[1:]], axis=-1)
        cost, _ = profile(target, features, (0.0, 0.0))
        keep = np.argsort(cost, kind="stable")[:cold.K]
        row = dict(track_id=track_id, ids=bank["ids"][visible[keep]],
                   target=target[keep], features=features[keep], dt=differences(time),
                   time_mean=time.mean() - doc["metadata"]["duration_s"] / 2,
                   lane=lane, rf_ghz=rf_ghz)
        if levels:
            residual = unwrapped_residual[keep]
            first = cold.wrap(residual[:, 0])
            row["level"] = cold.wrap(first + cold.wrap(residual - first[:, None]).mean(axis=1))
            row["level_features"] = np.column_stack([feature[keep].mean(axis=1)
                                                     for feature in model[1:]])
        rows.append(row)
    counts = dict(curved_tracks_considered=len(index), track_satellite_pairs_scored=evaluated)
    if not rows:
        return None, counts
    data = {key: np.stack([row[key] for row in rows]) for key in rows[0]}
    counts.update(nominated_tracks=len(rows), nominees_per_track=cold.K,
                  descriptor_array_bytes=sum(array.nbytes for array in data.values()),
                  pair_lag_s=dict(minimum=float(data["dt"].min()), median=float(np.median(data["dt"])),
                                  maximum=float(data["dt"].max())))
    return data, counts


def estimate_lane_offsets(data):
    bias = np.zeros(4)
    for lane in np.unique(data["lane"]):
        tracks = data["lane"] == lane
        level, level_features = data["level"][tracks], data["level_features"][tracks]
        target, features = data["target"][tracks], data["features"][tracks]

        def agreement(offset):
            cost, _ = profile(target, features, (0.0, 0.0), level=level,
                              level_features=level_features, bias=offset)
            return np.sum(1.0 / (1.0 + cost.min(axis=1) / 4.0))

        coarse = np.linspace(-cold.PERIOD / 2, cold.PERIOD / 2, 73, endpoint=False)
        center = max(coarse, key=agreement)
        bias[lane] = cold.wrap(max(center + np.linspace(-1700.0, 1700.0, 9), key=agreement))
    return bias


def grid_vote(data, *, bias=None):
    level_args = {} if bias is None else dict(level=data["level"],
                                              level_features=data["level_features"],
                                              bias=bias[data["lane"], None])
    rows = np.arange(len(data["track_id"]))
    best = None
    for east in GRID:
        for north in GRID:
            xy = (east, north)
            cost, phase = profile(data["target"], data["features"], xy, **level_args)
            winners = np.argmin(cost, axis=1)
            loss = cost[rows, winners]
            score = np.sum(1.0 / (1.0 + loss / 4.0))
            if best is None or score > best["score"]:
                best = dict(xy=xy, score=float(score), winners=winners, loss=loss,
                            phase=phase[rows, winners])
    return best


def fit(data, vote, *, bias=None, fitted_c=False):
    selected = np.flatnonzero(vote["loss"] < 12.0)
    winners = vote["winners"][selected]
    owners, sat_rows = np.unique(data["ids"][selected, winners], return_inverse=True)
    n, sat_count = len(selected), len(owners)
    if n < 4 or sat_count < 3:
        return dict(status="abstain", reason="Fewer than four inlier tracks or three unique satellites")

    include_levels = bias is not None
    lane = data["lane"][selected]
    offset_start = 6
    c_col = offset_start + 4
    phase_start = c_col + int(fitted_c) if include_levels else offset_start
    columns = phase_start + sat_count
    design = np.zeros((n, PAIRS + int(include_levels), columns))
    rows = np.arange(n)
    features = data["features"][selected, winners]
    design[:, :PAIRS, :2] = features[:, :, :2]
    design[rows, :PAIRS, 2 + lane] = data["dt"][selected]
    design[rows, :PAIRS, phase_start + sat_rows] = features[:, :, 2]

    # These candidates scored inside the inlier gate. Lift each residual to the
    # branch nearest its grid location and profiled time shift before local fit.
    target = data["target"][selected, winners]
    predicted = features[:, :, :2] @ vote["xy"] + features[:, :, 2] * vote["phase"][selected, None]
    target = predicted + cold.wrap(target - predicted)
    noise = np.full(PAIRS, DIFF_SD_HZ * np.sqrt(PAIRS))
    center = np.zeros(columns)
    prior_sd = [1000.0] * 2 + [DRIFT_SD_HZ_PER_S] * 4
    if include_levels:
        means = data["level_features"][selected, winners]
        design[:, PAIRS, :2] = means[:, :2]
        design[rows, PAIRS, 2 + lane] = data["time_mean"][selected]
        design[rows, PAIRS, offset_start + lane] = 1.0
        design[rows, PAIRS, phase_start + sat_rows] = means[:, 2]
        if fitted_c:
            design[:, PAIRS, c_col] = data["rf_ghz"][selected]
        level = data["level"][selected, winners]
        prediction = means[:, :2] @ vote["xy"] + means[:, 2] * vote["phase"][selected] + bias[lane]
        target = np.column_stack([target, prediction + cold.wrap(level - prediction)])
        noise = np.append(noise, cold.LEVEL_SD)
        prior_sd.extend([32_000.0] * 4)
        if fitted_c:
            prior_sd.append(RF_SD_HZ_PER_GHZ)
        center[offset_start:c_col] = bias
    prior_sd = np.array(prior_sd + [cold.PHASE_SD_S] * sat_count)

    scaled_a = design / noise[None, :, None]
    scaled_b = target / noise[None, :]
    upper = np.r_[[12.5, 12.5], np.full(columns - 2, np.inf)]
    weights = np.ones(n)
    for _ in range(4):
        weight = np.sqrt(weights)[:, None]
        a = (scaled_a * weight[:, :, None]).reshape(-1, columns)
        b = (scaled_b * weight).ravel()
        matrix = np.vstack([a * prior_sd, np.eye(columns)])
        rhs = np.r_[b - a @ center, np.zeros(columns)]
        solution = lsq_linear(matrix, rhs, bounds=((-upper - center) / prior_sd,
                                                   (upper - center) / prior_sd),
                              method="bvls", tol=1e-8, max_iter=40)
        if not solution.success:
            return dict(status="abstain", reason="Bounded least squares hit its iteration limit")
        x = solution.x * prior_sd + center
        residual = scaled_a @ x - scaled_b
        weights = np.minimum(1.0, 2.5 / np.maximum(.01, np.linalg.norm(residual, axis=1)))

    error = cold.wrap(design @ x - target)
    result = dict(status="estimate", latlon=bench.latlon(x[:2]),
                  rms_hz=float(np.sqrt(np.mean(error[:, :PAIRS]**2))),
                  tracks=n, satellites=sat_count,
                  on_boundary=bool(np.max(np.abs(x[:2])) > 12.49))
    if include_levels:
        result["absolute_mean_rms_hz"] = float(np.sqrt(np.mean(error[:, PAIRS]**2)))
        result["c_hz_per_ghz"] = float(x[c_col]) if fitted_c else 0.0
    return result


def invariance_check(doc, bank, data, vote, result):
    shifted, _ = prepare(doc, bank, perturb=True)
    assert shifted is not None
    np.testing.assert_array_equal(shifted["track_id"], data["track_id"])
    np.testing.assert_array_equal(shifted["ids"], data["ids"])
    np.testing.assert_allclose(shifted["target"], data["target"], rtol=0, atol=3e-9)
    repeated_vote = grid_vote(shifted)
    np.testing.assert_array_equal(repeated_vote["xy"], vote["xy"])
    np.testing.assert_array_equal(repeated_vote["winners"], vote["winners"])
    np.testing.assert_allclose(repeated_vote["loss"], vote["loss"], rtol=0, atol=1e-7)
    np.testing.assert_array_equal(repeated_vote["loss"] < 12., vote["loss"] < 12.)
    repeated_result = fit(shifted, repeated_vote)
    assert repeated_result["status"] == result["status"]
    if result["status"] == "estimate":
        np.testing.assert_allclose(repeated_result["latlon"], result["latlon"], rtol=0, atol=1e-10)
        np.testing.assert_allclose(repeated_result["rms_hz"], result["rms_hz"], rtol=0, atol=1e-7)
    return dict(passed=True, track_offset_hz=170_000.0, lane_offset_hz=93_000.0,
                injected_c_hz_per_ghz=59_000.0, per_sample_period_shift_max=3,
                largest_change_disagreement_hz=float(np.max(np.abs(shifted["target"] - data["target"]))))


def alias_check():
    np.testing.assert_array_equal(np.sort(np.r_[EARLY, LATE]), np.arange(cold.SAMPLES))
    assert np.all(LATE > EARLY)
    np.testing.assert_array_equal(differences(np.full(cold.SAMPLES, .73)), np.zeros(PAIRS))
    orbit = 8700.0 * np.arange(cold.SAMPLES)**1.4
    observed = cold.wrap(orbit + 175_000.0 + 59_000.0 * .73)
    observed += cold.PERIOD * (np.arange(cold.SAMPLES) % 4)
    np.testing.assert_allclose(cold.wrap(differences(observed - orbit)), 0, rtol=0, atol=1e-8)


def run_case(case, *, control=True):
    started = perf_counter()
    source = cold.read(cold.GRAPHS / f"{case}.json")
    meta = {key: source["metadata"][key] for key in ("causal_cutoff_utc_ns", "anchor_utc_ns", "duration_s")}
    doc = dict(metadata=meta, tracks=source["tracks"], curved_indices=source["curved_indices"])
    bank, bank_info = cold.build_bank(case, meta, check_approximation=False)
    bank_done = perf_counter()
    data, counts = prepare(doc, bank)
    names = ("c0", "fitted_c")
    if data is None:
        arms = {name: dict(status="abstain", reason="No curved tracks with twelve visible satellites")
                for name in names}
        return (dict(case=case, wall_s=perf_counter() - started, arms=arms),
                dict(bank=bank_info, prep=counts,
                     offset_and_alias_invariance=dict(passed=False, reason="No candidates to check")))
    vote = grid_vote(data)
    primary = fit(data, vote)
    primary_done = perf_counter()
    arms = {name: dict(primary) for name in names}
    arms["c0"]["c_hz_per_ghz"] = 0.0
    arms["fitted_c"].update(c_hz_per_ghz=None, c_identifiability="zero data column after differencing")
    selected = np.flatnonzero(vote["loss"] < 12.0)
    case_checks = dict(bank=bank_info, prep=counts, read_and_bank_s=bank_done - started,
                       shortlist_and_fit_s=primary_done - bank_done, grid_votes=len(GRID)**2,
                       grid_xy=list(vote["xy"]), grid_score=vote["score"],
                       selected_track_ids=data["track_id"][selected].tolist(),
                       selected_satellite_ids=data["ids"][selected, vote["winners"][selected]].tolist())
    if control:
        start_control = perf_counter()
        absolute, _ = prepare(doc, bank, levels=True)
        bias = estimate_lane_offsets(absolute)
        absolute_vote = grid_vote(absolute, bias=bias)
        control_arms = {name: fit(absolute, absolute_vote, bias=bias, fitted_c=(name == "fitted_c"))
                        for name in names}
        case_checks["paired_changes_plus_wrapped_means_control"] = dict(
            additional_wall_s=perf_counter() - start_control, arms=control_arms,
            grid_score=absolute_vote["score"], grid_xy=list(absolute_vote["xy"]))
        np.testing.assert_array_equal(absolute["ids"], data["ids"])
    case_checks["offset_and_alias_invariance"] = invariance_check(doc, bank, data, vote, primary)
    return dict(case=case, wall_s=primary_done - started, arms=arms), case_checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Run synthetic and first-case invariance checks")
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("result.json"))
    args = parser.parse_args()
    alias_check()
    if args.check:
        case, checks = run_case(bench.CASES[0], control=False)
        assert checks["offset_and_alias_invariance"]["passed"]
        assert case["arms"]["c0"]["status"] == "estimate"
        print(case["case"], checks["offset_and_alias_invariance"])
        return

    records = []
    checks = {}
    for case in bench.CASES:
        record, checks[case] = run_case(case)
        records.append(record)
    result = dict(method="Within-track modulo-CFO changes on six disjoint pairs",
                  timing_scope="Scan-end graph JSON read, causal TLE bank, pair descriptor nomination, "
                               "49-point position vote, and one identifiable bounded robust fit",
                  rms_kind="Raw observed-minus-fitted CFO changes modulo the detector period in Hz, "
                           "unweighted over six disjoint pairs per selected track",
                  cases=records, checks=checks)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
