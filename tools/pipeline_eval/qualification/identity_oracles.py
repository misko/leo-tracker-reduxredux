"""Measure identity at a known site and localization with known emitter IDs."""

import argparse
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy.optimize import least_squares
from sgp4.api import SatrecArray

from leo.sky.frames import (
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)

from ..__main__ import encoded, save_json
from ..scoring import ARMS, distance_km
from ..variants import rate_triplets as rate
from . import cold_scenes

DEV = cold_scenes.PROTOCOL.parent
TRAIN = slice(0, 8)
HELD = slice(8, 12)
POINTS = 12
SHORTLIST = 16
UP_LIMIT = np.sin(np.deg2rad(5.0))
LIGHT_KM_S = cold_scenes.LIGHT_KM_S
PERIOD_HZ = cold_scenes.CFO_ALIAS_HZ
METHODS = {
    "shape": (False, False),
    "absolute_cfo": (True, False),
    "frame_drift": (False, True),
    "joint": (True, True),
}


@dataclass(frozen=True)
class Track:
    receiver: int
    channel: int
    rf_hz: float
    times: np.ndarray
    cfo: np.ndarray
    epoch: np.ndarray
    samples: int


@dataclass(frozen=True)
class Candidates:
    ids: np.ndarray
    cfo: np.ndarray
    epoch: np.ndarray
    shape_cost: np.ndarray
    eligible_ids: np.ndarray | None = None


def wrap(values, period):
    return (values + period / 2) % period - period / 2


def _rms(values, axis=None):
    return np.sqrt(np.mean(values**2, axis=axis))


def _center(values, period):
    return np.angle(np.mean(np.exp(2j * np.pi / period * values), axis=-1)) * period / (2 * np.pi)


def _independent_peaks(capture):
    indexed = {}
    for p in capture.probes:
        key = (p["receiver_id"], p["channel"], p["actual_rf_hz"])
        counter = p["valid_start_counter"] - capture.first_counter
        time = counter / capture.sample_rate_hz + capture.probe_ms / 2000
        indexed[key, time] = [
            (
                rate.wrap(c["fractional_tracking_cfo_hz"]),
                (counter + c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"])
                % (capture.sample_rate_hz / cold_scenes.FRAME_HZ),
            )
            for c in p["candidates"]
            if c["passed_fractional_margin_gate"]
        ]
    return indexed


def _make_track(key, times, frequency, t, f, path, indexed):
    keep = np.linspace(0, len(t) - 1, POINTS).round().astype(int)
    epoch = []
    for selected in keep:
        visit, peak, _ = path[selected]
        nominees = indexed[key, times[visit]]
        epoch.append(min(nominees, key=lambda r: abs(rate.wrap(r[0] - frequency[visit][peak])))[1])
    return Track(*key, t[keep], f[keep], np.asarray(epoch), len(t))


def tracklets(capture):
    """Reuse the locked rate tracker gates and retain its selected raw epochs."""
    indexed = _independent_peaks(capture)
    result = []
    for key, rows in sorted(rate.peaks(capture).items()):
        rows.sort(key=lambda r: r[0])
        times = np.asarray([r[0] for r in rows])
        frequency = [r[1] for r in rows]
        used = [np.zeros(len(r), dtype=bool) for r in frequency]
        for i in range(max(0, len(rows) - 17)):
            for j in np.flatnonzero(~used[i]):
                eligible = []
                for seed in rate.successive_seeds(times, frequency, used, i, j):
                    path, t, f = rate.extend(times, frequency, used, seed)
                    if segment := rate.shape(key, t, f):
                        eligible.append((segment, t, f, path))
                if not eligible:
                    continue
                segment, t, f, path = max(
                    eligible, key=lambda row: (row[0].points, -row[0].noise_hz)
                )
                for visit, peak, _ in path:
                    used[visit][peak] = True
                track = _make_track(key, times, frequency, t, f, path, indexed)
                result.append((segment.curvature_hz / max(75, segment.noise_hz), track))
    return [r[1] for r in sorted(result, key=lambda r: -r[0])[:28]]


def _states(anchor, satellites, seconds):
    jd, fraction = julian_day_from_utc_ns(anchor + np.rint(seconds * 1e9).astype(np.int64))
    errors, p, v = SatrecArray(satellites).sgp4(jd, fraction)
    p, v = teme_to_ecef(p, v, greenwich_mean_sidereal_time_rad(jd, fraction))
    return errors, p, v


def _model(position, velocity, site, rf, sample_rate):
    delta = position - site
    distance = np.linalg.norm(delta, axis=-1)
    radial = np.sum(delta * velocity, axis=-1) / distance
    return -rf / LIGHT_KM_S * radial, sample_rate / LIGHT_KM_S * distance


def _candidates(capture, satellites, tracks, latlon, *, midpoint_states=None):
    up = ecef_to_enu_matrix(*latlon)[2]
    site = geodetic_to_ecef_km(*latlon, 0.0)
    if midpoint_states is None:
        middle = np.array([tr.times.mean() for tr in tracks])
        midpoint_states = _states(capture.anchor_utc_ns, satellites, middle)
    errs, position, _ = midpoint_states
    delta = position - site
    visible = (errs == 0) & ((delta @ up) >= UP_LIMIT * np.linalg.norm(delta, axis=-1))
    rows = []
    for i, track in enumerate(tracks):
        objects = [satellites[j] for j in np.flatnonzero(visible[:, i])]
        odds, pos, vel = _states(capture.anchor_utc_ns, objects, track.times)
        delta = pos - site
        valid = ((odds == 0) & ((delta @ up) >= UP_LIMIT * np.linalg.norm(delta, axis=-1))).all(1)
        if not valid.any():
            raise ValueError("known-site tracklet has no causal sky candidates")
        cfo, epoch = _model(pos[valid], vel[valid], site, track.rf_hz, capture.sample_rate_hz)
        difference = track.cfo - cfo
        center = _center(difference[:, TRAIN], PERIOD_HZ)
        shape = _rms(wrap(difference[:, TRAIN] - center[:, None], PERIOD_HZ), axis=1)
        keep = np.argsort(shape, kind="stable")[:SHORTLIST]
        ids = np.array([sat.satnum for sat, ok in zip(objects, valid, strict=True) if ok])
        rows.append(
            Candidates(ids[keep], difference[keep], track.epoch - epoch[keep], shape[keep], ids)
        )
    return rows


def _design(tracks, times, fit_c):
    receivers = np.asarray([t.receiver for t in tracks])
    lane = (receivers[:, None] == np.arange(2)).astype(float)
    values = [lane, lane * (times[:, None] - 150)]
    if fit_c:
        values.append(np.asarray([(t.rf_hz / 1e9 - 11.5,) for t in tracks]))
    return np.column_stack(values)


def _fit_lo(design, receiver, y):
    # Circular branch around the per-receiver location, then robust regression.
    location = np.asarray([_center(y[receiver == rx], PERIOD_HZ) for rx in range(2)])
    target = location[receiver] + wrap(y - location[receiver], PERIOD_HZ)
    start = np.linalg.lstsq(design, target, rcond=None)[0]
    return least_squares(
        lambda params: (target - design @ params) / 250,
        start,
        loss="soft_l1",
        max_nfev=35,
    ).x


def _frame_clock(values, times, period):
    t = times - times.mean(axis=1, keepdims=True)
    y = wrap(values - _center(values, period)[:, None], period)
    return float(np.sum(t * y) / np.sum(t**2))


def identify(tracks, candidates, period, kind, fit_c):
    absolute, frame = METHODS[kind]
    times = np.stack([t.times for t in tracks])
    t0 = times[:, TRAIN].mean(1)
    dt = times - t0[:, None]
    receivers = np.asarray([t.receiver for t in tracks])
    design = _design(tracks, t0, fit_c)
    center = [_center(c.cfo[:, TRAIN], PERIOD_HZ) for c in candidates]
    choice = np.zeros(len(tracks), int)
    controls = np.zeros(design.shape[-1])
    clock = 0.0
    for _ in range(4):
        if absolute:
            offsets = np.array([x[j] for x, j in zip(center, choice, strict=True)])
            controls = _fit_lo(design, receivers, offsets)
        if frame:
            selected = np.stack(
                [a.epoch[j, TRAIN] for a, j in zip(candidates, choice, strict=True)]
            )
            clock = _frame_clock(selected, times[:, TRAIN], period)
        rank = []
        for i, cand in enumerate(candidates):
            cost = (cand.shape_cost / 120) ** 2
            if absolute:
                offset = wrap(center[i] - design[i] @ controls, PERIOD_HZ)
                cost = cost + (offset / 450) ** 2
            if frame:
                epoch = cand.epoch[:, TRAIN] - clock * dt[i, TRAIN]
                residual = wrap(epoch - _center(epoch, period)[:, None], period)
                cost = cost + (_rms(residual, axis=1) / 2) ** 2
            rank.append(cost)
        choice = np.array([int(np.argmin(cost)) for cost in rank])
    rows = []
    for i, (cand, j) in enumerate(zip(candidates, choice, strict=True)):
        epoch = cand.epoch[j] - clock * dt[i]
        phase = _center(epoch[None, TRAIN], period)[0]
        track_cfo = wrap(cand.cfo[j, HELD] - center[i][j], PERIOD_HZ)
        absolute_cfo = wrap(
            cand.cfo[j, HELD] - design[i] @ controls - controls[2 + receivers[i]] * dt[i, HELD],
            PERIOD_HZ,
        )
        rows.append(
            dict(
                selected_norad=int(cand.ids[j]),
                shortlisted_norad=cand.ids.tolist(),
                score=float(rank[i][j]),
                held_centered_cfo_rms_hz=float(_rms(track_cfo)),
                held_absolute_cfo_rms_hz=float(_rms(absolute_cfo)) if absolute else None,
                held_epoch_rms_samples=float(_rms(wrap(epoch[HELD] - phase, period))),
            )
        )
    return dict(
        rows=rows,
        clock_samples_per_s=clock,
        c_hz_per_ghz=float(controls[-1]) if absolute and fit_c else 0.0,
    )


def _gather_known(capture, tracks, satellites, assigned):
    lookup = {int(x.satnum): x for x in satellites}
    position, velocity = [], []
    for t, norad in zip(tracks, assigned, strict=True):
        code, p, v = _states(capture.anchor_utc_ns, [lookup[norad]], t.times)
        if code.any():
            raise ValueError("planted orbit failed propagation")
        position.append(p[0])
        velocity.append(v[0])
    return np.stack(position), np.stack(velocity)


def _center_train(values):
    return values - values[..., TRAIN].mean(axis=-1, keepdims=True)


def _known_residual(sites, ephemeris, rf, sample_rate, observed, dt):
    p, v = ephemeris
    receiver = geodetic_to_ecef_km(sites[:, 0], sites[:, 1], 0).T
    f, delay = _model(p[None], v[None], receiver[:, None, None], rf, sample_rate)
    carrier = _center_train(observed[0] - f)
    epoch = _center_train(observed[1] - delay)
    slope = (epoch[..., TRAIN] * dt[:, TRAIN]).sum(axis=(1, 2)) / (dt[:, TRAIN] ** 2).sum()
    return carrier, epoch - slope[:, None, None] * dt, f, slope


def fit_known_ids(capture, tracks, satellites, assigned):
    ephemeris = _gather_known(capture, tracks, satellites, assigned)
    rf = np.array([t.rf_hz for t in tracks])[:, None]
    times = np.stack([t.times for t in tracks])
    t0 = times[:, TRAIN].mean(1)
    dt = times - t0[:, None]
    observed = (
        np.stack([t.cfo for t in tracks]),
        np.unwrap(
            np.stack([t.epoch for t in tracks]),
            period=capture.sample_rate_hz / cold_scenes.FRAME_HZ,
        ),
    )
    receivers = np.array([t.receiver for t in tracks])
    mesh = rate.spherical_grid(1536)
    costs = []
    for chunk in np.array_split(mesh, 24):
        carrier, phase, _, _ = _known_residual(
            chunk, ephemeris, rf, capture.sample_rate_hz, observed, dt
        )
        costs.extend(
            np.mean((carrier[..., TRAIN] / 120) ** 2 + (phase[..., TRAIN] / 2) ** 2, axis=(1, 2))
        )
    starts = []
    for index in np.argsort(costs):
        site = mesh[index]
        if all(distance_km(site.tolist(), saved.tolist()) > 500 for saved in starts):
            starts.append(site)
        if len(starts) == 4:
            break
    results = {}
    for arm in ARMS:
        design = _design(tracks, t0, arm == "fitted_c")
        fits = []
        for seed in starts:

            def details(x, center=seed, matrix=design):
                site = rate.offset_site(center, *x[:2])[None, :]
                centered, frame, model, slope = _known_residual(
                    site, ephemeris, rf, capture.sample_rate_hz, observed, dt
                )
                intercept = matrix @ x[2:]
                group_drift = x[2:][receivers + 2]
                absolute = wrap(
                    observed[0] - model[0] - intercept[:, None] - group_drift[:, None] * dt,
                    PERIOD_HZ,
                )
                return site[0], centered[0], absolute, frame[0], slope[0]

            def residual(x, describe=details):
                _, centered, absolute, frame, _ = describe(x)
                return np.concatenate(
                    [
                        centered[:, TRAIN].ravel() / 120,
                        absolute[:, TRAIN].ravel() / 450,
                        frame[:, TRAIN].ravel() / 2,
                    ]
                )

            _, _, f, _ = _known_residual(
                seed[None, :], ephemeris, rf, capture.sample_rate_hz, observed, dt
            )
            center = _center(observed[0][:, TRAIN] - f[0, :, TRAIN], PERIOD_HZ)
            initial = np.r_[0, 0, _fit_lo(design, receivers, center)]
            limit = np.r_[
                1000, 1000, PERIOD_HZ, PERIOD_HZ, 1200, 1200, np.repeat(50000, design.shape[1] - 4)
            ]
            fit = least_squares(
                residual,
                np.clip(initial, -0.99 * limit, 0.99 * limit),
                bounds=(-limit, limit),
                loss="soft_l1",
                max_nfev=40,
                x_scale="jac",
            )
            fits.append((fit.cost, fit.x, details(fit.x)))
        cost, params, (site, shape, absolute, frame, slope) = min(fits, key=lambda f: f[0])
        results[arm] = dict(
            latlon=site.tolist(),
            training_cost=float(cost),
            held_shape_rms_hz=float(_rms(shape[:, HELD])),
            held_absolute_cfo_rms_hz=float(_rms(absolute[:, HELD])),
            held_epoch_rms_samples=float(_rms(frame[:, HELD])),
            clock_samples_per_s=float(slope),
            c_hz_per_ghz=float(params[-1]) if arm == "fitted_c" else 0.0,
        )
    return dict(arms=results, evaluated_mesh_points=len(mesh), local_starts=len(starts))


def _labels(folder):
    path = folder / "scores.json"
    labels = cold_scenes._read(path)["generated_truth"]
    if (
        cold_scenes._sha(encoded(labels) + b"\n")
        != cold_scenes._read(folder / "input-lock.json")["truth_sha256"]
    ):
        raise ValueError("development label commitment differs")
    return labels


def run_development(public, output, *, dev=DEV):
    labels = _labels(dev)
    roster = cold_scenes._read(dev / "prediction-lock.json")["cases"]
    manifest = cold_scenes._read(public / "manifest.json")
    if manifest != cold_scenes._read(dev / "manifest.json"):
        raise ValueError("expected the corrected development input packet")
    cases = []
    for case in roster:
        started = perf_counter()
        capture = cold_scenes._capture(public, case)
        tracks = tracklets(capture)
        truth = labels[case]
        if truth["latlon"] is None:
            cases.append(dict(id=case, control=True, qualifying_tracklets=len(tracks)))
            continue
        roster_ids = {(r["block"], r["channel"]): r["norad"] for r in truth["emitters"]}
        assigned = [roster_ids[int(np.median(t.times) // 50), t.channel] for t in tracks]
        satellites = cold_scenes._constellation(capture.catalog, capture.cutoff_utc_ns)
        candidates = _candidates(capture, satellites, tracks, truth["latlon"])
        identity = {}
        for method in METHODS:
            identity[method] = {}
            for arm in ARMS:
                details = identify(
                    tracks,
                    candidates,
                    capture.sample_rate_hz / cold_scenes.FRAME_HZ,
                    method,
                    arm == "fitted_c",
                )
                good = set()
                for row, expected in zip(details["rows"], assigned, strict=True):
                    row["true_norad"] = expected
                    if row["selected_norad"] == expected:
                        good.add(expected)
                details.update(
                    correct_tracklets=sum(
                        r["selected_norad"] == r["true_norad"] for r in details["rows"]
                    ),
                    correctly_recovered_norads=len(good),
                )
                identity[method][arm] = details
        fitted = fit_known_ids(capture, tracks, satellites, assigned)
        for arm in fitted["arms"].values():
            arm["error_km"] = distance_km(arm["latlon"], truth["latlon"])
        cases.append(
            dict(
                id=case,
                control=False,
                qualitative_site_index=truth["case_index"],
                qualifying_tracklets=len(tracks),
                planted_norads=len(roster_ids),
                true_tracks_on_shortlist=sum(
                    label in row.ids for label, row in zip(assigned, candidates, strict=True)
                ),
                identity=identity,
                known_id_position=fitted,
                worker_wall_s=perf_counter() - started,
            )
        )
        print(
            case,
            "shape",
            identity["shape"]["c0"]["correct_tracklets"],
            "joint",
            identity["joint"]["fitted_c"]["correct_tracklets"],
            "known-ID km",
            fitted["arms"]["fitted_c"]["error_km"],
            flush=True,
        )
    save_json(
        output,
        dict(
            cases=cases,
            development_input_lock_sha256=cold_scenes._sha((dev / "input-lock.json").read_bytes()),
            implementation_sha256=cold_scenes._sha(Path(__file__).read_bytes()),
        ),
    )


def figure(results, output):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import NullLocator, ScalarFormatter

    cases = [r for r in cold_scenes._read(results)["cases"] if not r["control"]]
    fig, (identity, geography) = plt.subplots(1, 2, figsize=(10.5, 4.7))
    names = ("CFO shape", "Shape + absolute CFO", "Shape + frame drift", "Joint")
    amount = [sum(r["qualifying_tracklets"] for r in cases)] * len(names)
    identity.barh(names, amount, color="#edf1f2", height=0.55)
    for j, arm in enumerate(ARMS):
        color = "#127581" if arm == "c0" else "#a76033"
        label = "Zero calibration" if arm == "c0" else "Fitted calibration"
        correct = [
            sum(r["identity"][method][arm]["correct_tracklets"] for r in cases)
            for method in METHODS
        ]
        shift = -0.12 if j == 0 else 0.12
        identity.barh(np.arange(4) + shift, correct, height=0.17, color=color, label=label)
        for y, count in enumerate(correct):
            identity.text(count + 0.5, y + shift, f"{count}", va="center", fontsize=8, color=color)
        errors = [1000 * c["known_id_position"]["arms"][arm]["error_km"] for c in cases]
        geography.scatter(np.arange(len(cases)) + shift, errors, color=color, s=28)
    identity.invert_yaxis()
    identity.set_title("Known site · tracklet identity")
    identity.set(xlim=(0, 108), xlabel="Correct associations out of 96")
    geography.set_title("Planted IDs supplied · global search")
    geography.set(yscale="log", ylabel="Position error (m)")
    geography.set_yticks([30, 50, 100, 200, 500, 800])
    geography.yaxis.set_major_formatter(ScalarFormatter())
    geography.yaxis.set_minor_locator(NullLocator())
    geography.set_xticks(range(len(cases)), ("Europe", "Australia", "Mexico", "S. Africa"))
    geography.grid(axis="y", linewidth=0.7, alpha=0.35)
    for axis in (identity, geography):
        axis.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Development oracles on four synthetic receiver sites", fontsize=14)
    handles, labels = identity.get_legend_handles_labels()
    fig.legend(handles, labels, ncol=2, loc="lower center", frameon=False)
    fig.tight_layout(rect=(0, 0.09, 1, 0.92))
    fig.savefig(output, dpi=170)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("public", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--figure", type=Path)
    args = parser.parse_args()
    run_development(args.public, args.output)
    if args.figure:
        figure(args.output, args.figure)


if __name__ == "__main__":
    main()
