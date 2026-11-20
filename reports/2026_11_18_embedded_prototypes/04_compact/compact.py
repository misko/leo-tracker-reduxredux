"""End-of-scan compact Doppler positioning replay on anonymous DS26 tracks."""

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from bench import CASES, PANEL, latlon
import cold_replay as cold


STEP_S = 8.0
TILE_SATS = 16
TOP_TRACKS = 64
SAMPLES = 12
K = 12
HALF_BOX = PANEL["box_width_km"] / 2
FIELDS = ("frequency", "east", "north", "elevation_sine")
PACKED = np.dtype(list(zip(FIELDS, ("<i4", "<i2", "<i2", "<i2"), strict=True)))
REFERENCE = np.dtype([(name, "<f8") for name in FIELDS])
QUANTUM = (0.125, 0.0625, 0.0625, 1 / 32767)
ARMS = ("c0", "fitted_c")
MOMENT_ROW, MOMENT_COL = np.triu_indices(4)


@dataclass(frozen=True)
class Table:
    cells: np.ndarray
    sat_ids: np.ndarray
    first_s: float

    @classmethod
    def create(cls, fields, ids, first_s, packed):
        cells = np.empty(fields[0].shape, dtype=PACKED if packed else REFERENCE)
        for field, values, step in zip(FIELDS, fields, QUANTUM, strict=True):
            if packed:
                values = np.rint(values / step)
                limits = np.iinfo(PACKED[field])
                if not np.all((limits.min <= values) & (values <= limits.max)):
                    raise ValueError(f"{field} quantization overflow")
            cells[field] = values
        return cls(cells, np.asarray(ids, dtype=np.int32), float(first_s))

    @property
    def nbytes(self):
        return self.cells.nbytes + self.sat_ids.nbytes + 16  # first knot and cadence

    def index(self, seconds):
        slot = (np.asarray(seconds) - self.first_s) / STEP_S
        left = np.floor(slot).astype(int)
        if np.any(left < 1) or np.any(left + 2 >= self.cells.shape[1]):
            raise ValueError("sample outside cubic table support")
        u = slot - left
        u2, u3 = u * u, u * u * u
        value = np.stack((-.5*u + u2 - .5*u3, 1 - 2.5*u2 + 1.5*u3,
                          .5*u + 2*u2 - 1.5*u3, -.5*u2 + .5*u3), axis=-1)
        rate = np.stack((-.5 + 2*u - 1.5*u2, -5*u + 4.5*u2,
                         .5 + 4*u - 4.5*u2, -u + 1.5*u2), axis=-1) / STEP_S
        return left[:, None] + np.arange(-1, 3), value, rate

    def at(self, sats, plan):
        columns, weight, rate_weight = plan
        block = self.cells[sats[:, None, None], columns[None]]
        scales = QUANTUM if self.cells.dtype == PACKED else (1.,) * len(FIELDS)
        fields = [np.einsum("sti,ti->st", block[name], weight) * scale
                  for name, scale in zip(FIELDS, scales, strict=True)]
        rate = np.einsum("sti,ti->st", block["frequency"], rate_weight) * scales[0]
        return (*fields, rate)


def build_fields(case, meta):
    cutoff, anchor = (meta[k] for k in ("causal_cutoff_utc_ns", "anchor_utc_ns"))
    oldest = cutoff - 48 * 3600 * 10**9
    paths = sorted((cold.INPUT / case / "tle").rglob("*.tle"))
    snapshot = [p for p in paths if oldest <= int(p.name.split("-")[0]) <= cutoff][-1]
    raw = snapshot.read_bytes()
    if hashlib.sha256(raw).hexdigest() != snapshot.stem.split("-")[1]:
        raise ValueError(f"snapshot checksum mismatch for {case}")
    catalog = cold.parse_element_sets(raw.decode())
    rows = [sat for sat, name, epoch in zip(
        catalog.satellites, catalog.names, catalog.element_epoch_utc_ns(), strict=True
    ) if "STARLINK" in name.upper() and oldest <= epoch <= cutoff]
    duration = meta["duration_s"]
    err, p, v = cold.state(rows, anchor, np.arange(0, duration + 60, 60))
    regional = np.all(err == 0, axis=1) & (cold.projection(p, v, (0, 0))[-1].max(axis=1) >= -.06)
    provisional = [sat for sat, keep in zip(rows, regional, strict=True) if keep]
    knots = np.arange(-STEP_S, (np.ceil(duration / STEP_S) + 3) * STEP_S, STEP_S)
    err, p, v = cold.state(provisional, anchor, knots)
    valid = np.all(err == 0, axis=1)
    sats = [sat for sat, keep in zip(provisional, valid, strict=True) if keep]
    fields = cold.projection(p[valid], v[valid], (0, 0))
    receipt = dict(snapshot=snapshot.name, cutoff_utc_ns=cutoff, eligible_catalog=len(rows),
                   regional_satellites=len(sats), knots=len(knots), step_s=STEP_S,
                   archive_duration_s=duration)
    return fields, sats, knots, receipt


def sample_tracks(document):
    tracks = document["tracks"]
    duration = document["metadata"]["duration_s"]
    indexes = sorted(document["curved_indices"], key=lambda i: -len(tracks[i]["times"]))[:TOP_TRACKS]
    for index in indexes:
        track = tracks[index]
        times = np.asarray(track["times"])
        if len(times) < SAMPLES:
            continue
        if times[0] < 0 or times[-1] > duration or np.any(np.diff(times) <= 0):
            raise ValueError(f"track {index} has invalid sample time support")
        sample = np.rint(np.linspace(0, len(times) - 1, SAMPLES)).astype(int)
        group = 2 * (track["receiver"] - 1) + int(track["channel"] > 4)
        yield index, times[sample], np.asarray(track["values"])[sample], group, track["rf_hz"]


def tile_features(table, sats, plan, observed, rf_hz):
    f, e, n, up, rate = table.at(sats, plan)
    ratio = rf_hz / cold.CARRIER
    return np.stack((observed - ratio*f, ratio*e, ratio*n, ratio*rate), axis=-1), up


def moments(features):
    mean = features.mean(axis=-2)
    centered = features - mean[..., None, :]
    cov = np.einsum("...si,...si->...i", centered[..., MOMENT_ROW],
                    centered[..., MOMENT_COL]) / SAMPLES
    return np.concatenate((mean, cov), axis=-1)


def phase_cost(stat, east, north, bias, *, shape_only=False):
    level, e, n, rate, rr, re, rn, rt, ee, en, et, nn, nt, tt = np.moveaxis(stat, -1, 0)
    residual = cold.wrap(level - east*e - north*n - bias)
    shape = rr - 2*east*re - 2*north*rn + east*east*ee + 2*east*north*en + north*north*nn
    cross = rt - east*et - north*nt
    level_w = 0. if shape_only else 1 / cold.LEVEL_SD**2
    shape_w = 1 / cold.SHAPE_SD**2
    phase_w = 1 / cold.PHASE_SD_S**2
    shift = np.clip((shape_w*cross + level_w*residual*rate) /
                    (shape_w*tt + level_w*rate**2 + phase_w), -8., 8.)
    return np.maximum((shape - 2*shift*cross + shift*shift*tt)*shape_w
                      + (residual - shift*rate)**2*level_w + shift*shift*phase_w, 0.)


def track_candidates(table, plan, measured, rf_hz):
    retained = np.empty((0, 14))
    satellite_rows = np.empty(0, dtype=np.int32)
    visible_count = 0
    for first in range(0, len(table.sat_ids), TILE_SATS):
        tile = np.arange(first, min(first + TILE_SATS, len(table.sat_ids)), dtype=np.int32)
        feat, elevation_sine = tile_features(table, tile, plan, measured, rf_hz)
        visible = elevation_sine.min(axis=-1) >= -.008
        visible_count += int(visible.sum())
        retained = np.concatenate((retained, moments(feat[visible])))
        satellite_rows = np.concatenate((satellite_rows, tile[visible]))
        shape = phase_cost(retained, 0, 0, 0, shape_only=True)
        abs_level = np.abs(cold.wrap(retained[:, 0]))
        combined = shape + np.maximum(1., abs_level / 12000.)**2
        shape_order = np.lexsort((satellite_rows, shape))[:K//2]
        combined_order = np.lexsort((satellite_rows, combined))[:K]
        # Top six by shape and top twelve by combined score are sufficient
        # to merge the exact final twelve, irrespective of tile boundaries.
        keep = np.r_[shape_order, combined_order[~np.isin(combined_order, shape_order)]]
        retained, satellite_rows = retained[keep], satellite_rows[keep]
    return satellite_rows[:K], retained[:K], visible_count


def describe(table, tracks):
    results = []
    visible_pairs = 0
    for track in tracks:
        _, seconds, measured, _, rf_hz = track
        rows, stats, visible = track_candidates(table, table.index(seconds), measured, rf_hz)
        visible_pairs += visible
        if visible >= K:
            results.append((track, rows, stats))
    return results, visible_pairs


def acquire(descriptors):
    if not descriptors:
        return np.zeros(4), (0., 0.), (), 0., 0
    group = np.array([track[3] for track, _, _ in descriptors])
    stats = np.stack([stat for _, _, stat in descriptors])
    bias = np.zeros(4)
    evaluations = 0
    for lane in np.unique(group):
        lane_stats = stats[group == lane]

        def score(b):
            losses = phase_cost(lane_stats, 0., 0., b).min(axis=1)
            return np.sum(1 / (1 + losses / 4))

        grid = np.linspace(-cold.PERIOD/2, cold.PERIOD/2, 73, endpoint=False)
        center = max(grid, key=score)
        bias[lane] = cold.wrap(max(center + np.linspace(-1700, 1700, 9), key=score))
        evaluations += 82 * lane_stats.shape[0] * K
    best = None
    for east in np.linspace(-HALF_BOX, HALF_BOX, 7):
        for north in np.linspace(-HALF_BOX, HALF_BOX, 7):
            cost = phase_cost(stats, east, north, bias[group, None])
            winners = np.argmin(cost, axis=1)
            loss = cost[np.arange(len(winners)), winners]
            score = np.sum(1 / (1 + loss / 4))
            if best is None or score > best[0]:
                best = (score, (east, north), winners, loss)
    score, start, winners, loss = best
    selected = tuple((descriptors[i][0], descriptors[i][1][winners[i]])
                     for i in np.flatnonzero(loss < 12))
    return bias, start, selected, float(score), evaluations + 49 * len(group) * K


def bounded_profile(normal, rhs):
    nuisance = np.linalg.solve(normal[2:, 2:], np.column_stack((normal[2:, :2], rhs[2:])))
    curvature = normal[:2, :2] - normal[:2, 2:] @ nuisance[:, :2]
    linear = rhs[:2] - normal[:2, 2:] @ nuisance[:, 2]
    free = np.linalg.solve(curvature, linear)
    if np.max(np.abs(free)) <= 1.:
        location = free
    else:
        candidates = []
        for i in range(2):
            j = 1 - i
            for edge in (-1., 1.):
                candidate = np.zeros(2)
                candidate[i] = edge
                candidate[j] = np.clip((linear[j] - curvature[j, i]*edge) / curvature[j, j], -1., 1.)
                candidates.append(candidate)
        location = min(candidates, key=lambda z: z @ curvature @ z - 2*linear @ z)
    return np.r_[location, nuisance[:, 2] - nuisance[:, :2] @ location]


def fit(table, selected, bias, start, fitted):
    sat_rows = [row for _, row in selected]
    owners, inverse = np.unique(sat_rows, return_inverse=True)
    if len(owners) < 3 or len(selected) < 4:
        return dict(status="abstain", reason="under four inlier tracks or three satellite families",
                    rms_hz=None)
    clocks = 11 if fitted else 10
    prior_sd = np.r_[[1000.] * 2, [32000.] * 4, [750.] * 4,
                     [200000.] if fitted else [], [cold.PHASE_SD_S] * len(owners)]
    scale = prior_sd.copy()
    scale[:2] = HALF_BOX
    prior = (scale / prior_sd)**2
    equations = []
    for ((_, seconds, measured, group, rf_hz), sat), owner in zip(selected, inverse, strict=True):
        features, _ = tile_features(table, np.array([sat]), table.index(seconds), measured, rf_hz)
        residual, e, n, rate = features[0].T
        lift = cold.PERIOD * np.rint(np.mean(residual - start[0]*e - start[1]*n - bias[group]) / cold.PERIOD)
        target = residual - lift - bias[group]
        columns = [0, 1, 2+group, 6+group]
        local = [e, n, np.ones_like(e), (seconds-150.) / 150.]
        if fitted:
            columns.append(10)
            local.append(np.full_like(e, rf_hz/1e9 - 11.5))
        columns.append(clocks + owner)
        local.append(rate)
        raw = np.column_stack(local) * scale[columns]
        a = raw.mean(axis=0)
        b = target.mean()
        shaped = (raw - a) / (cold.SHAPE_SD * np.sqrt(SAMPLES))
        centered = (target - b) / (cold.SHAPE_SD * np.sqrt(SAMPLES))
        block = shaped.T @ shaped + np.outer(a, a) / cold.LEVEL_SD**2
        linear = shaped.T @ centered + a*b / cold.LEVEL_SD**2
        constant = centered @ centered + (b / cold.LEVEL_SD)**2
        equations.append((columns, np.ix_(columns, columns), block, linear, constant, raw, target))
    weights = np.ones(len(selected))
    for _ in range(4):
        normal = np.diag(prior)
        rhs = np.zeros_like(prior)
        for weight, (columns, scatter, block, linear, _, _, _) in zip(weights, equations, strict=True):
            normal[scatter] += weight*block
            rhs[columns] += weight*linear
        position = bounded_profile(normal, rhs)
        losses = []
        for columns, _, block, linear, constant, _, _ in equations:
            partial = position[columns]
            losses.append(max(0., partial @ block @ partial - 2*linear @ partial + constant))
        norms = np.sqrt(losses)
        weights = np.minimum(1., 2.5 / np.maximum(.01, norms))
    squared_hz = sum(np.sum((raw @ position[columns] - target)**2)
                     for columns, _, _, _, _, raw, target in equations)
    robust_loss = np.where(norms <= 2.5, .5*norms**2, 2.5*(norms-1.25)).sum()
    xy = position[:2] * HALF_BOX
    equation_bytes = sum(block.nbytes + linear.nbytes + raw.nbytes + target.nbytes + 8
                         for _, _, block, linear, _, raw, target in equations)
    return dict(status="estimate", xy_km=xy.tolist(), latlon=latlon(xy), tracks=len(selected),
                satellites=len(owners), rms_hz=float(np.sqrt(squared_hz / (SAMPLES * len(selected)))),
                profile_objective=float(robust_loss + .5*np.sum(prior*position**2)),
                c_hz_per_ghz=float(position[10] * scale[10]) if fitted else 0.,
                on_boundary=bool(np.max(np.abs(position[:2])) > .9992),
                profiled_parameters=len(prior), normal_matrix_bytes=normal.nbytes,
                track_equation_numeric_bytes=equation_bytes)


def run_table(table, tracks):
    start = time.perf_counter()
    descriptors, visible = describe(table, tracks)
    described = time.perf_counter()
    bias, xy, selected, score, grid_evaluations = acquire(descriptors)
    acquired = time.perf_counter()
    arms = {arm: fit(table, selected, bias, xy, arm == "fitted_c") for arm in ARMS}
    done = time.perf_counter()
    result = dict(table_bytes=table.nbytes, bytes_per_knot=table.cells.dtype.itemsize,
                  candidate_seconds=described-start, grid_seconds=acquired-described,
                  both_solve_seconds=done-acquired, wall_s=done-start,
                  tracks_screened=len(tracks), tracks_with_shortlist=len(descriptors),
                  visibility_pass_track_sat_pairs=visible,
                  interpolated_track_sat_sample_pairs=len(tracks)*len(table.sat_ids)*SAMPLES,
                  hypothesis_score_evaluations=grid_evaluations, initial_xy_km=list(xy), grid_score=score,
                  shortlist_array_bytes=sum(rows.nbytes + stats.nbytes for _, rows, stats in descriptors),
                  sampled_track_array_bytes=sum(t.nbytes + y.nbytes for _, t, y, _, _ in tracks),
                  acquisition_selected=[(track[0], int(table.sat_ids[sat])) for track, sat in selected])
    return arms, result


def abs_error(estimate, truth):
    error = np.abs(estimate - truth)
    return dict(n=int(error.size), p95=float(np.percentile(error, 95)), maximum=float(error.max()))


def validate_geometry(packed, control, sats, knots, meta):
    times = knots[1:-3:2] + .5*STEP_S
    anchor = meta["anchor_utc_ns"]
    err, p, v = cold.state(sats, anchor, times)
    err_b, p_b, v_b = cold.state(sats, anchor, times - .125)
    err_a, p_a, v_a = cold.state(sats, anchor, times + .125)
    valid = (err == 0) & (err_b == 0) & (err_a == 0)
    indexes = np.arange(len(sats))
    compact = packed.at(indexes, packed.index(times))
    double = control.at(indexes, control.index(times))
    geometry = {}
    for xy in ((0., 0.), (-HALF_BOX, -HALF_BOX), (-HALF_BOX, HALF_BOX),
               (HALF_BOX, -HALF_BOX), (HALF_BOX, HALF_BOX)):
        exact, _, _, up = cold.projection(p, v, xy)
        above = valid & (up >= 0.)
        approximations = [(f + xy[0]*east + xy[1]*north)[above]
                          for f, east, north, _, _ in (compact, double)]
        row = dict(xy_km=list(xy), packed_vs_geometry_hz=abs_error(approximations[0], exact[above]),
                   float64_vs_geometry_hz=abs_error(approximations[1], exact[above]),
                   packed_vs_float64_hz=abs_error(*approximations))
        if xy == (0., 0.):
            exact_rate = (cold.projection(p_a, v_a, xy)[0] - cold.projection(p_b, v_b, xy)[0]) / .25
            row.update(packed_vs_geometry_rate_hz_per_s=abs_error(compact[4][above], exact_rate[above]),
                       packed_vs_float64_rate_hz_per_s=abs_error(compact[4][above], double[4][above]))
        geometry[str(xy)] = row
    return geometry


def run_case(case):
    total_at = time.perf_counter()
    graph = cold.read(cold.GRAPHS / f"{case}.json")
    tracks = tuple(sample_tracks(graph))
    input_end = time.perf_counter()
    meta = graph["metadata"]
    fields, sats, knots, receipt = build_fields(case, meta)
    orbit_end = time.perf_counter()
    ids = [sat.satnum for sat in sats]
    packed = Table.create(fields, ids, knots[0], packed=True)
    pack_end = time.perf_counter()
    arms, search = run_table(packed, tracks)
    wall = time.perf_counter() - total_at
    control = Table.create(fields, ids, knots[0], packed=False)
    reference, reference_search = run_table(control, tracks)
    delta = {}
    for arm in ARMS:
        if arms[arm]["status"] == reference[arm]["status"] == "estimate":
            delta[arm] = dict(endpoint_separation_km=float(np.linalg.norm(
                np.subtract(arms[arm]["xy_km"], reference[arm]["xy_km"]))),
                delta_rms_hz=arms[arm]["rms_hz"] - reference[arm]["rms_hz"])
    return dict(case=case, wall_s=wall, arms=arms, bank=receipt, compact=search,
                input_read_and_track_sample_s=input_end-total_at, orbit_build_s=orbit_end-input_end,
                packing_s=pack_end-orbit_end, float64_control=dict(arms=reference, **reference_search),
                comparison=dict(arms=delta, matched_acquisition=search["acquisition_selected"] ==
                                reference_search["acquisition_selected"]),
                geometry_controls=validate_geometry(packed, control, sats, knots, meta))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", default=HERE / "result.json", type=Path)
    options = cli.parse_args()
    from test_compact import run_checks

    checks = run_checks()
    rows = []
    for case in CASES:
        row = run_case(case)
        rows.append(row)
        print(case, f"{row['wall_s']:.3f} s", {k: v["status"] for k, v in row["arms"].items()}, flush=True)
    result = dict(method="int32/int16 cubic Doppler table with tiled hypothesis search and profiled continuous fix",
                  timing_scope="Host elapsed wall time from archived graph JSON read and track sampling through "
                               "causal TLE selection, SGP4, compact table construction, shared acquisition and both "
                               "continuous c arms. Independent float64 and geometry checks excluded.",
                  cases=rows, checks=checks)
    options.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
