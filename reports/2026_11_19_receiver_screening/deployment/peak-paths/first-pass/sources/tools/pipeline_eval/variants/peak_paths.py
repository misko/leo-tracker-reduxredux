"""Decode orbital CFO paths directly from native per-visit peak alternatives."""

import ctypes as ct
import subprocess
from collections import defaultdict
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
from scipy.optimize import lsq_linear

from ..reference import grid

METHOD = "peak_paths"
BOUNDARY = "Native GLRT peak sets and single causal TLE through orbital paths and held position"
ARMS = ("c0", "fitted_c")
PERIOD = 1 / 4.4e-6
PHASES = (-10.0, 0.0, 10.0)
PEAKS = 4
STEP = 5.0
EARTH_ROTATION = 7.29211514670698e-5


@dataclass(frozen=True)
class Lane:
    key: tuple
    visit: np.ndarray
    t: np.ndarray
    y: np.ndarray
    marks: np.ndarray

    def subset(self, use):
        return Lane(self.key, self.visit[use], self.t[use], self.y[use], self.marks[use])

    @property
    def group(self):
        return 2 * self.key[0] + int(self.key[1] > 4)


def fold(hz):
    return hz - PERIOD * np.rint(hz / PERIOD)


def read_peaks(capture, shuffle=False):
    groups = defaultdict(list)
    count, passed = 0, 0
    for probe in capture.probes:
        t = (probe["valid_start_counter"] - capture.first_counter) / capture.sample_rate_hz
        t += capture.probe_ms / 2000
        key = int(probe["receiver_id"]), int(probe["channel"]), float(probe["actual_rf_hz"])
        if key[0] not in (0, 1) or key[1] not in range(1, 9) or not 1e9 < key[2] < 100e9:
            raise ValueError("unrecognized receiver or tuned RF")
        if not 0 <= t <= capture.duration_s:
            raise ValueError("native probe time outside acquisition support")
        candidates = sorted(probe["candidates"], key=lambda r: r["candidate_rank"])[:PEAKS]
        values, evidence = np.zeros(PEAKS), np.full(PEAKS, -np.inf)
        for j, p in enumerate(candidates):
            margin, value = p["fractional_margin"], p["fractional_tracking_cfo_hz"]
            if not np.isfinite((margin, value)).all():
                raise ValueError("invalid native peak score or CFO")
            gate = bool(p["passed_fractional_margin_gate"])
            passed += gate
            values[j] = fold(value)
            evidence[j] = (0.95 if gate else -0.9) + np.clip(margin / 0.1, -1, 1) - 0.18 * j
        count += len(candidates)
        groups[key].append((t, probe["visit_index"], values, evidence))
    lanes = []
    for i, (key, points) in enumerate(sorted(groups.items())):
        t, visit, y, evidence = (np.asarray(v) for v in zip(*sorted(points), strict=True))
        if np.any(np.diff(t) <= 0) or len(set(visit)) != len(visit):
            raise ValueError("the lane must have strictly ordered unique receiver visits")
        order = np.random.default_rng(20261119 + i).permutation(len(t)) if shuffle else slice(None)
        lanes.append(Lane(key, visit, t, y[order], evidence[order]))
    return lanes, dict(
        native_visits=len(capture.probes),
        native_peaks_retained=count,
        retained_passing_peaks=passed,
        rf_lanes=len(lanes),
        shuffle=shuffle,
    )


@cache
def kernel():
    with TemporaryDirectory(prefix="leo-peak-paths-") as scratch:
        output = Path(scratch) / "kernel.so"
        subprocess.run(
            [
                "cc",
                "-O3",
                "-std=c11",
                "-shared",
                "-fPIC",
                str(Path(__file__).with_suffix(".c")),
                "-lm",
                "-o",
                str(output),
            ],
            check=True,
            capture_output=True,
        )
        library = ct.CDLL(str(output))
    decode = library.peak_paths_decode
    f64 = np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS")
    i16 = np.ctypeslib.ndpointer(dtype=np.int16, flags="C_CONTIGUOUS")
    decode.argtypes = [ct.c_int] * 4 + [f64] * 5 + [i16]
    decode.restype = ct.c_int
    return decode


def decode(lane, predictions, *, fixed=False):
    trajectories = np.ascontiguousarray(predictions, dtype=float)
    n, v = trajectories.shape
    if v != len(lane.t) or lane.y.shape != (v, PEAKS):
        raise ValueError("each potential orbit needs one prediction per visited opportunity")
    value, path = np.zeros(n), np.full((n, v), -1, np.int16)
    if (
        n
        and v
        and kernel()(
            n,
            v,
            PEAKS,
            int(fixed),
            np.ascontiguousarray(lane.t),
            np.ascontiguousarray(lane.y),
            np.ascontiguousarray(lane.marks),
            trajectories,
            value,
            path,
        )
    ):
        raise MemoryError("peak path traceback allocation failed")
    return value, path


def orbital_bank(capture, center):
    sky = grid.prepare_sky(capture, capture.catalog)
    tile = grid.make_tile(sky, center)
    d = sky.positions_km - tile.ecef_center_km
    relevant = ((d @ tile.enu_frame[2]) >= -0.08 * np.linalg.norm(d, axis=-1)).any(axis=1)
    satellites = tuple(s for s, k in zip(sky.satellites, relevant, strict=True) if k)
    knots = np.arange(-18, capture.duration_s + 23, STEP)
    usable, position, velocity = grid._valid_states(satellites, capture.anchor_utc_ns, knots)
    bank = replace(tile, positions_km=position, velocities_km_s=velocity, knots_s=knots)
    return bank, [int(s.satnum) for s in usable], sky.stats


def rotate(p, angle):
    out = p.copy()
    c, s = np.cos(angle), np.sin(angle)
    out[..., 0], out[..., 1] = c * p[..., 0] - s * p[..., 1], s * p[..., 0] + c * p[..., 1]
    return out


def orbit_geometry(bank, times, phase, site, rf, *, horizon=False):
    p, v, _ = grid._interpolated_states(bank, times + phase)
    p, v = (rotate(x, EARTH_ROTATION * phase) for x in (p, v))
    delta = p - site
    distance = np.linalg.norm(delta, axis=-1)
    ray = delta / distance[..., None]
    radial = np.sum(ray * v, axis=-1)
    scale = rf / grid.LIGHT_SPEED_KM_S
    signal = -scale * radial
    if horizon:
        return np.where((ray @ bank.enu_frame[2]) >= -0.03, signal, np.nan)
    spatial = scale * ((v - ray * radial[..., None]) @ bank.enu_frame[:2].T) / distance[..., None]
    return signal[0], spatial[0]


def slice_orbit(bank, rows):
    return replace(
        bank, positions_km=bank.positions_km[rows], velocities_km_s=bank.velocities_km_s[rows]
    )


def blocks(t):
    epoch = np.floor(t / 15).astype(int)
    held = epoch % 4 == 2
    delta = t % 60
    train = (delta < 27) | (delta >= 48)
    return train, held


def shortlist(bank, lane, lane_index):
    results = []
    n = len(bank.positions_km)
    for phase in PHASES:
        for first in range(0, n, 96):
            sub = slice_orbit(bank, slice(first, first + 96))
            modeled = orbit_geometry(
                sub, lane.t, phase, bank.ecef_center_km, lane.key[2], horizon=True
            )
            score, paths = decode(lane, modeled)
            for i in np.argsort(-score, kind="stable")[:10]:
                use = np.flatnonzero(paths[i] >= 0)
                if len(use) < 12 or np.ptp(lane.t[use]) < 14:
                    continue
                values = lane.y[use, paths[i, use]]
                raw = fold(values - modeled[i, use])
                offset = fold(float(np.median(raw[0] + fold(raw - raw[0]))))
                residual = fold(raw - offset)
                spread = float(np.sqrt(np.mean(residual**2)))
                t = lane.t[use] - lane.t[use].mean()
                f = modeled[i, use] - modeled[i, use].mean()
                curvature = np.sqrt(np.mean((f - t * (f @ t) / (t @ t)) ** 2))
                if spread <= 2200 and curvature >= 100:
                    results.append(
                        dict(
                            lane=lane_index,
                            orbit=first + int(i),
                            phase=phase,
                            strength=float(score[i]) / (1 + (spread / 1200) ** 2),
                            offset=float(offset),
                            t=lane.t[use],
                            visit=lane.visit[use],
                            y=values,
                        )
                    )
    return sorted(results, key=lambda p: -p["strength"])[:32]


def choose(lanes, paths):
    """Use a common receiver/band harmonic level and one phase per selected satellite."""
    mode = np.zeros(4)
    consonant = []
    for group in range(4):
        options = [p for p in paths if lanes[p["lane"]].group == group]
        if not options:
            continue
        offsets = np.array([p["offset"] for p in options])
        nearby = abs(fold(offsets[:, None] - offsets)) <= 3500
        weights = np.array([min(35, p["strength"]) for p in options])
        number = np.array([p["orbit"] for p in options])
        tally = np.zeros(len(options))
        for orbit in np.unique(number):
            k = number == orbit
            tally += (nearby[:, k] * weights[k]).max(axis=1)
        winning = np.argmax(tally)
        use = nearby[winning]
        mode[group] = fold(
            offsets[winning] + float(np.median(fold(offsets[use] - offsets[winning])))
        )
        consonant.extend(p for p in options if abs(fold(p["offset"] - mode[group])) <= 3500)
    shared = defaultdict(float)
    for p in consonant:
        shared[p["orbit"], p["phase"]] += p["strength"]
    phase = {o: max(PHASES, key=lambda p: shared[o, p]) for o in {p["orbit"] for p in consonant}}
    selected, visited = [], set()
    for p in sorted(consonant, key=lambda p: -p["strength"]):
        points = {(lanes[p["lane"]].key[0], int(v)) for v in p["visit"]}
        if p["phase"] == phase[p["orbit"]] and not points & visited:
            selected.append(p)
            visited |= points
    return selected, mode


def site(bank, xy):
    xyz, _, position = grid._sites(bank, np.asarray(xy)[None, :])
    return xyz[0], position[0].tolist()


def fit(bank, lanes, paths, mode, half, enable_c):
    orbit = {n: i for i, n in enumerate(sorted({p["orbit"] for p in paths}))}
    n = 11 + len(orbit)
    lower, upper = (
        -np.r_[half, half, [6000.0] * 4, [125.0] * 4, 8000.0, [7.5] * len(orbit)],
        np.r_[half, half, [6000.0] * 4, [125.0] * 4, 8000.0, [7.5] * len(orbit)],
    )
    if not enable_c:
        lower[10], upper[10] = -1e-12, 1e-12
    prior = 1 / np.r_[1000.0, 1000.0, [3000.0] * 4, [35.0] * 4, 2000.0, [3.0] * len(orbit)]
    state = np.zeros(n)
    records = []
    for p in paths:
        lane = lanes[p["lane"]]
        index = 11 + orbit[p["orbit"]]
        sub = slice_orbit(bank, slice(p["orbit"], p["orbit"] + 1))
        pred = orbit_geometry(sub, p["t"], p["phase"], bank.ecef_center_km, lane.key[2])[0]
        y = pred + mode[lane.group] + fold(p["y"] - pred - mode[lane.group])
        records.append((p, lane, sub, index, y))

    def calculate(x, differentiate):
        xyz = site(bank, x[:2])[0]
        result, designs = [], []
        for p, lane, sub, j, y in records:
            delta = p["phase"] + x[j]
            rf, group = lane.key[2], lane.group
            f, g = orbit_geometry(sub, p["t"], delta, xyz, rf)
            time = p["t"] - bank.duration_s / 2
            term = rf / 1e9 - 11.5
            r = y - f - mode[group] - x[2 + group] - x[6 + group] * time - x[10] * term
            result.append(r)
            if differentiate:
                d = np.zeros((len(y), n))
                d[:, :2], d[:, 2 + group], d[:, 6 + group], d[:, 10] = g, 1, time, term
                d[:, j] = (
                    orbit_geometry(sub, p["t"], delta + 0.03, xyz, rf)[0]
                    - orbit_geometry(sub, p["t"], delta - 0.03, xyz, rf)[0]
                ) / 0.06
                designs.append(d)
        return np.concatenate(result), np.vstack(designs) if differentiate else None

    def objective(x, r):
        return np.sum(np.log1p((r / 420) ** 2)) + np.sum((x * prior) ** 2)

    for _ in range(5):
        r, J = calculate(state, True)
        w = 1 / np.sqrt(420**2 + r * r)
        cost = objective(state, r)
        delta = lsq_linear(
            np.vstack((J * w[:, None], np.diag(prior))),
            np.r_[r * w, -state * prior],
            bounds=(lower - state - 1e-10, upper - state + 1e-10),
            max_iter=36,
        ).x
        for a in (1.0, 0.5, 0.25, 0.125):
            new = np.clip(state + a * delta, lower, upper)
            if objective(new, calculate(new, False)[0]) < cost:
                state = new
                break
        else:
            break
    residual, J = calculate(state, True)
    q = J / np.sqrt(420**2 + residual**2)[:, None]
    information = q.T @ q + np.diag(prior**2)
    radius = float(2.45 * np.sqrt(np.linalg.eigvalsh(np.linalg.inv(information)[:2, :2])[-1]))
    return state, orbit, float(np.sqrt(np.mean(residual**2))), radius


def held_scores(bank, lanes, chosen, mode, fit_value):
    x, index, _, _ = fit_value
    xyz = site(bank, x[:2])[0]
    trials = []
    for item in chosen:
        lane = lanes[item["lane"]]
        query = lane.subset(blocks(lane.t)[1])
        rf, group, no = lane.key[2], lane.group, item["orbit"]
        sub = slice_orbit(bank, slice(no, no + 1))
        f = orbit_geometry(sub, query.t, item["phase"] + x[11 + index[no]], xyz, rf, horizon=True)[
            0
        ]
        pred = (
            f
            + mode[group]
            + x[2 + group]
            + x[6 + group] * (query.t - bank.duration_s / 2)
            + x[10] * (rf / 1e9 - 11.5)
        )
        score, path = decode(query, pred[None], fixed=True)
        use = np.flatnonzero(path[0] >= 0)
        if len(use) >= 5:
            trials.append(
                (
                    score[0],
                    no,
                    query,
                    query.visit[use],
                    query.t[use],
                    fold(query.y[use, path[0, use]] - pred[use]),
                )
            )
    visits, families, pieces, residuals = set(), set(), set(), []
    for _, no, lane, ids, t, r in sorted(trials, key=lambda r: -r[0]):
        ref = {(lane.key[0], int(x)) for x in ids}
        if not visits & ref:
            visits |= ref
            families.add(no)
            pieces.update(np.floor(t / 15).astype(int))
            residuals.extend(r)
    return dict(
        held_points=len(residuals),
        held_orbits=len(families),
        held_blocks=len(pieces),
        held_rms_hz=float(np.sqrt(np.mean(np.square(residuals)))) if residuals else None,
    )


def solve(capture, *, tile, shuffle=False):
    start = perf_counter()
    lanes, counts = read_peaks(capture, shuffle)
    packed = perf_counter()
    half = float(tile.get("width_km", 25)) / 2
    bank, norads, sky = orbital_bank(capture, tile["center"])
    propagated = perf_counter()
    paths = [
        p
        for i, lane in enumerate(lanes)
        for p in shortlist(bank, lane.subset(blocks(lane.t)[0]), i)
    ]
    selected, mode = choose(lanes, paths)
    decoded = perf_counter()
    count = len({p["orbit"] for p in selected})
    groups = len({lanes[p["lane"]].group for p in selected})
    c_separated = len(
        {
            lanes[p["lane"]].group
            for p in selected
            if len(
                {
                    lanes[q["lane"]].key[2]
                    for q in selected
                    if lanes[q["lane"]].group == lanes[p["lane"]].group
                }
            )
            >= 2
        }
    )
    arms = {arm: dict(latlon=None, forced_latlon=None) for arm in ARMS}
    reason = "insufficient_disjoint_orbital_paths"
    if count >= 4 and groups >= 2:
        reason = None
        for arm in ARMS:
            current = fit(bank, lanes, selected, mode, half, arm == "fitted_c")
            x, _, rf, radius = current
            checked = held_scores(bank, lanes, selected, mode, current)
            coords = site(bank, x[:2])[1]
            arms[arm].update(
                forced_latlon=coords,
                rf_rms_hz=rf,
                radius_km=radius,
                c_hz_per_ghz=0.0 if arm == "c0" else float(x[10]),
                **checked,
            )
            if (
                checked["held_points"] < 25
                or checked["held_orbits"] < 3
                or checked["held_blocks"] < 2
            ):
                reason = "insufficient_contiguous_held_path_support"
            elif np.max(abs(x[:2])) > half - 0.75 or radius > 6:
                reason = reason or "weak_position_geometry"
        if reason is None:
            for arm in arms.values():
                arm["latlon"] = arm["forced_latlon"]
    counts.update(
        sky,
        regional_orbits=len(norads),
        path_candidates=len(paths),
        selected_paths=len(selected),
        selected_orbits=count,
        clock_groups=groups,
        independent_rf_clock_groups=c_separated,
        selected_points=sum(len(p["t"]) for p in selected),
        phase_seeds=list(PHASES),
        read_s=packed - start,
        orbit_s=propagated - packed,
        decode_s=decoded - propagated,
        fit_and_hold_s=perf_counter() - decoded,
    )
    trace = [
        dict(
            norad=norads[p["orbit"]],
            lane=list(lanes[p["lane"]].key),
            phase_s=p["phase"],
            points=len(p["t"]),
            visit_ids=p["visit"].tolist(),
            start_s=float(p["t"][0]),
            end_s=float(p["t"][-1]),
            strength=p["strength"],
        )
        for p in selected
    ]
    return dict(
        status="ok" if reason is None else "withheld",
        reason=reason,
        boundary=BOUNDARY,
        metrics=counts,
        arms=arms,
    ), trace
