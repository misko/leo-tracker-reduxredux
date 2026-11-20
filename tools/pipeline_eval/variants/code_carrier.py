"""Test whether native pilot epoch increments add geometry beyond signed Doppler."""

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from ..reference import grid, tracker
from . import clock_transfer_grouped, doppler_turns, joint_pass, multi_session, peak_paths
from .track_epoch import counter_phase

FRAME_HZ = 750
MAX_GAP_S = 2.5
EPOCH_SIGMA = 3.0
CARRIER_SIGMA = 1.0
CAP = 25.0
BOUNDARY = "Native anonymous GLRT intervals and causal TLE range change"
MODES = ("carrier", "joint", "joint_free", "code_shuffle", "carrier_shuffle", "center")


@dataclass(frozen=True)
class Arc:
    lane: tuple
    generation: str
    time: np.ndarray
    counters: np.ndarray
    cfo: np.ndarray
    epoch: np.ndarray
    stop: int
    norad: int
    orbital_phase: float
    position: np.ndarray


def wrapped(x, period):
    return x - period * np.rint(x / period)


def arrival_samples(counters, origin, epochs, rate):
    """Form the positive pilot arrival coordinate modulo the original frame clock."""
    samples = np.asarray(counters, dtype=np.int64) - origin
    return (counter_phase(samples, rate) + epochs) % (rate / FRAME_HZ)


def carrier_samples(cfo, dt, rf, rate):
    """Convert signed carrier Hz integrated on adjacent visits into delay samples."""
    return -rate / rf * (cfo[:-1] + cfo[1:]) * dt / 2


def anonymous(capture):
    observed, batches = {}, {}
    ordered = []
    if not isinstance(capture.generation, str) or not capture.generation:
        raise ValueError("an authenticated continuous sample generation is required")
    for probe in capture.probes:
        if probe["probe_start_ms"] != 0:
            raise ValueError("epoch origin requires a zero-offset native probe")
        counter = probe["valid_start_counter"]
        t = (counter - capture.first_counter) / capture.sample_rate_hz + capture.probe_ms / 2000
        if not 0 <= t <= capture.duration_s:
            raise ValueError("native probe outside hardware sample generation")
        lane = (probe["receiver_id"], probe["channel"], probe["actual_rf_hz"], probe["edge"])
        valid = []
        for c in sorted(
            probe["candidates"], key=lambda p: (-p["fractional_margin"], p["candidate_rank"])
        ):
            if (
                not c["passed_fractional_margin_gate"]
                or c["fractional_epoch_offset_samples"] is None
            ):
                continue
            f = tracker.wrap(c["fractional_tracking_cfo_hz"])
            if all(abs(tracker.wrap(f - item[0])) >= tracker.DUPLICATE_HZ for item in valid):
                valid.append((f, c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"]))
            if len(valid) == tracker.MAX_CANDIDATES:
                break
        if (t, lane) in observed:
            raise ValueError("duplicate native clock/RF coordinate")
        observed[t, lane] = counter, valid
        ordered.append((t, lane))
    for t, lane in sorted(ordered):
        block = int(t // 45)
        if block not in batches:
            batches[block] = doppler_turns.AnonymousTracks()
        batches[block].ingest(t, lane, [value[0] for value in observed[t, lane][1]])

    arcs, available = [], 0
    for block, tracks in batches.items():
        paths = set()
        for found in sorted(tracks.arcs(), key=lambda x: -len(x["t"]) * np.ptp(x["t"])):
            lane = found["lane"]
            group = 2 * lane[0] + int(lane[1] > 4)
            t, frequency = found["t"], found["f"]
            if np.ptp(t) < 15:
                continue
            stop = int(np.searchsorted(t, t[0] + (t[-1] - t[0]) * 2 / 3))
            good = np.diff(t) <= MAX_GAP_S
            if good[: stop - 1].sum() < 8 or good[stop:].sum() < 4:
                continue
            available += 1
            if group in paths:
                continue
            counters, epochs = [], []
            for time, lifted in zip(t, frequency, strict=True):
                counter, alternatives = observed[time, lane]
                matches = [
                    epoch for f, epoch in alternatives if abs(tracker.wrap(lifted - f)) < 1e-5
                ]
                if len(matches) != 1:
                    raise ValueError("linked carrier failed its exact native epoch join")
                counters.append(counter)
                epochs.append(matches[0])
            paths.add(group)
            arcs.append(
                (block, group, lane, t, frequency, np.asarray(counters), np.asarray(epochs), stop)
            )
    return arcs, dict(
        native_probes=len(ordered),
        available_tracks=available,
        selected_tracks=len(arcs),
        generation=capture.generation,
    )


def assign(tracks, capture, center):
    bank, ids, _ = peak_paths.orbital_bank(capture, center)
    receiver = geodetic_to_ecef_km(*center, 0.0)
    enu = ecef_to_enu_matrix(*center)
    related = []
    for _block, group, lane, t, frequency, counters, epochs, stop in tracks:
        rf = lane[2]
        options = joint_pass.shortlist(
            (0, group, t[:stop], frequency[:stop], rf), bank, ids, receiver, enu
        )
        if options is None:
            continue
        expected = clock_transfer_grouped.exact_project(options.p, options.v, receiver, rf)
        y = clock_transfer_grouped.unwrap(peak_paths.fold(frequency[:stop] - expected))
        residual, phase, _ = joint_pass.profile(y, options.phase, t[:stop], stop, independent=True)
        cost = np.mean(np.minimum(CAP, (residual / 450.0) ** 2), axis=1) + (phase / 6) ** 2 / stop
        j = int(np.argmin(cost))
        if cost[j] > 9:
            continue
        norad = int(options.norad[j])
        p, _ = clock_transfer_grouped.states(bank, [ids.index(norad)], t, [phase[j]])
        related.append(
            Arc(
                lane,
                capture.generation,
                t,
                counters,
                frequency,
                epochs,
                stop,
                norad,
                float(phase[j]),
                p[0],
            )
        )
    return related, len(ids)


def shuffled(values, stop, rng):
    return np.r_[rng.permutation(values[:stop]), rng.permutation(values[stop:])]


def packet(arcs, capture):
    rng = np.random.default_rng(750440)
    samples = defaultdict(list)
    used = []
    for i, arc in enumerate(arcs):
        dt = np.diff(arc.time)
        idx = np.arange(len(dt))
        take = (dt <= MAX_GAP_S) & (idx != arc.stop - 1)
        split = idx < arc.stop - 1
        epoch = arrival_samples(
            arc.counters, capture.first_counter, arc.epoch, capture.sample_rate_hz
        )
        prior = dict(
            dt=dt,
            orbit=np.full(len(dt), arc.norad),
            track=np.full(len(dt), i),
            rf=np.full(len(dt), arc.lane[2]),
            receiver=np.full(len(dt), arc.lane[0]),
            path=np.full(len(dt), 2 * arc.lane[0] + int(arc.lane[1] > 4)),
            time=(arc.time[1:] + arc.time[:-1]) / 2,
            train=split,
            code=wrapped(np.diff(epoch), capture.sample_rate_hz / FRAME_HZ),
            code_shuffle=wrapped(
                np.diff(shuffled(epoch, arc.stop, rng)), capture.sample_rate_hz / FRAME_HZ
            ),
            carrier=carrier_samples(arc.cfo, dt, arc.lane[2], capture.sample_rate_hz),
            carrier_shuffle=carrier_samples(
                shuffled(arc.cfo, arc.stop, rng), dt, arc.lane[2], capture.sample_rate_hz
            ),
        )
        for key, value in prior.items():
            samples[key].append(value[take])
        used.append(take)
    return {name: np.concatenate(values) for name, values in samples.items()}, used


def indicator(labels):
    return np.equal.outer(labels, np.unique(labels)).astype(float)


def design(data, *, free):
    dt = data["dt"][:, None]
    level = indicator(data["track"]) * dt
    path = indicator(data["track"] if free else data["path"])
    drift = path * dt * (data["time"][:, None] - 150) / 150
    code = indicator(data["track"] if free else data["receiver"]) * dt
    return code, np.hstack((level, drift))


def predict(observed, expected, x, train, sigma, period=None):
    residual = observed - expected
    coef = np.zeros(x.shape[1])
    for _ in range(3):
        e = residual - x @ coef
        if period is not None:
            e = wrapped(e, period)
        weight = 1 / np.sqrt(np.hypot(1, e[train] / sigma))
        coef += np.linalg.lstsq(x[train] * weight[:, None], e[train] * weight, rcond=None)[0]
    e = residual - x @ coef
    return wrapped(e, period) if period is not None else e


def geometry(arcs, used, site, scale):
    receiver, basis = geodetic_to_ecef_km(*site, 0.0), ecef_to_enu_matrix(*site)[:2]
    delays, derivatives = [], []
    for arc, take in zip(arcs, used, strict=True):
        delta = arc.position - receiver
        rho = np.linalg.norm(delta, axis=1)
        ray = delta / rho[:, None]
        delays.append(scale * np.diff(rho)[take])
        derivatives.append(-scale * np.diff(ray @ basis.T, axis=0)[take])
    return np.concatenate(delays), np.vstack(derivatives)


def loss(value, take, sigma):
    return float(np.mean(np.minimum(CAP, (value[take] / sigma) ** 2)))


def rms(value, take):
    return float(np.sqrt(np.mean(value[take] ** 2)))


def fisher(j, design, train, sigma):
    q, x = j[train] / sigma, design[train]
    residual = q - x @ np.linalg.lstsq(x, q, rcond=None)[0]
    return residual.T @ residual


def calibration_audit(data, x, rate):
    col = -rate / data["rf"] * (data["rf"] / 1e9 - 11.5) * data["dt"]
    fitted = x @ np.linalg.lstsq(x, col, rcond=None)[0]
    return dict(
        norm=float(np.linalg.norm(col)),
        residual_norm=float(np.linalg.norm(col - fitted)),
        rank=clock_transfer_grouped.data_rank(x),
        rank_with_c=clock_transfer_grouped.data_rank(np.column_stack((x, col))),
    )


def profile(data, predicted, j, sample_rate):
    train = data["train"]
    keep = ~train
    period = sample_rate / FRAME_HZ
    code, carrier = design(data, free=False)
    free_code, free_carrier = design(data, free=True)
    observed = data["code"], data["carrier"]
    nuisance = (code, carrier)
    e, f = [
        predict(y, predicted, x, train, sigma, circ)
        for y, x, sigma, circ in (
            (observed[0], nuisance[0], EPOCH_SIGMA, period),
            (observed[1], nuisance[1], CARRIER_SIGMA, None),
        )
    ]
    free_e = predict(observed[0], predicted, free_code, train, EPOCH_SIGMA, period)
    free_f = predict(observed[1], predicted, free_carrier, train, CARRIER_SIGMA)
    null_e = predict(data["code_shuffle"], predicted, code, train, EPOCH_SIGMA, period)
    null_f = predict(data["carrier_shuffle"], predicted, carrier, train, CARRIER_SIGMA)
    reversed_e = predict(observed[0], -predicted, code, train, EPOCH_SIGMA, period)
    zero_e = predict(observed[0], np.zeros_like(predicted), code, train, EPOCH_SIGMA, period)
    free_null_e = predict(data["code_shuffle"], predicted, free_code, train, EPOCH_SIGMA, period)
    free_null_f = predict(data["carrier_shuffle"], predicted, free_carrier, train, CARRIER_SIGMA)
    free_reverse = predict(observed[0], -predicted, free_code, train, EPOCH_SIGMA, period)
    free_zero = predict(
        observed[0], np.zeros_like(predicted), free_code, train, EPOCH_SIGMA, period
    )
    base_info = fisher(j, carrier, train, CARRIER_SIGMA)
    joint_info = base_info + fisher(j, code, train, EPOCH_SIGMA)
    free_info = fisher(j, free_carrier, train, CARRIER_SIGMA) + fisher(
        j, free_code, train, EPOCH_SIGMA
    )
    output = {}
    for mode, ce, cf, info in (
        ("carrier", e, f, base_info),
        ("joint", e, f, joint_info),
        ("joint_free", free_e, free_f, free_info),
        ("code_shuffle", null_e, f, joint_info),
        ("carrier_shuffle", e, null_f, joint_info),
    ):
        score = {
            k: loss(cf, mask, CARRIER_SIGMA)
            + (0.0 if mode == "carrier" else loss(ce, mask, EPOCH_SIGMA))
            for k, mask in (("train", train), ("held", keep))
        }
        singular = np.sqrt(np.maximum(np.linalg.eigvalsh(info), 0))
        tracks = np.unique(data["track"][keep])
        supported = {
            int(data["orbit"][m][0])
            for t in tracks
            if ((m := (data["track"] == t) & keep).any() and rms(ce, m) <= 3 and rms(cf, m) <= 2)
        }
        output[mode] = dict(
            loss=score,
            code_rms=rms(ce, keep),
            carrier_rms=rms(cf, keep),
            closure_rms=rms(wrapped(ce - cf, period), keep),
            code_clock_only_rms=rms(free_zero if mode == "joint_free" else zero_e, keep),
            code_reflected_rms=rms(free_reverse if mode == "joint_free" else reversed_e, keep),
            code_shuffled_rms=rms(free_null_e if mode == "joint_free" else null_e, keep),
            carrier_shuffled_rms=rms(free_null_f if mode == "joint_free" else null_f, keep),
            fisher_singular_km_inv=singular.tolist(),
            fisher_rank=int(np.sum(singular > 1e-5)),
            qualified_held_orbits=len(supported),
        )
    return output


def evaluate(capture, center):
    tracks, stats = anonymous(capture)
    arcs, causal = assign(tracks, capture, center)
    if len(arcs) < 3:
        return dict(
            status="unavailable", reason="insufficient_anonymous_causal_tracks", stats=stats
        )
    data, mask = packet(arcs, capture)
    points, offers = multi_session.design(center)
    _, carrier = design(data, free=False)
    audit = calibration_audit(data, carrier, capture.sample_rate_hz)
    if audit["rank"] != audit["rank_with_c"] or audit["residual_norm"] > 1e-10:
        raise ValueError("the RF linear offset failed its exact per-track gauge audit")
    profiles = {
        xy: profile(
            data,
            *geometry(arcs, mask, site, capture.sample_rate_hz / grid.LIGHT_SPEED_KM_S),
            capture.sample_rate_hz,
        )
        for xy, site in points.items()
    }
    outcomes = []
    for offer, region in offers.items():
        for method in MODES:
            mode = "joint" if method == "center" else method
            cell = (
                multi_session.OFFERS[offer]
                if method == "center"
                else min(region["points"], key=lambda xy: profiles[xy][mode]["loss"]["train"])
            )
            state = profiles[cell][mode]
            rival = min(
                p[mode]["loss"]["held"]
                for xy, p in profiles.items()
                if np.linalg.norm(np.subtract(xy, cell)) >= 10
            )
            lead = rival - state["loss"]["held"]
            held_gate = (
                state["code_rms"] <= 3
                and state["code_rms"]
                <= 0.8
                * min(
                    state[k]
                    for k in ("code_clock_only_rms", "code_reflected_rms", "code_shuffled_rms")
                )
                and state["carrier_rms"] <= 2
                and state["carrier_rms"] <= 0.8 * state["carrier_shuffled_rms"]
                and state["qualified_held_orbits"] >= 2
                and state["fisher_rank"] == 2
                and lead >= 0.25
            )
            ok = method in ("joint", "joint_free") and held_gate
            result = dict(
                status="ok" if ok else "withheld",
                reason=None
                if ok
                else (
                    "insufficient_physical_held_range_evidence"
                    if method in ("joint", "joint_free")
                    else "experimental_comparison"
                ),
                boundary=BOUNDARY,
                arms=dict(
                    c0=dict(
                        latlon=points[cell] if ok else None,
                        forced_latlon=points[cell] if not ok else None,
                    ),
                    fitted_c=dict(
                        status="unavailable",
                        latlon=None,
                        reason="fixed_rf_term_is_absorbed_by_local_carrier_offset",
                    ),
                ),
                metrics=dict(
                    position_attempted=True,
                    selected_cell_km=cell,
                    held_site_lead=lead,
                    matched_carrier_only=profiles[cell]["carrier"],
                    **state,
                ),
            )
            outcomes.append(
                dict(
                    offer=offer,
                    method=method,
                    result=result,
                    tile=dict(center=region["center"], width_km=25),
                )
            )
    return dict(
        status="ok",
        outcomes=outcomes,
        stats=stats,
        calibration=audit,
        causal_orbits=causal,
        arcs=[
            dict(
                lane=a.lane,
                norad=a.norad,
                orbital_phase_s=a.orbital_phase,
                start_counter=int(a.counters[0]),
                end_counter=int(a.counters[-1]),
                train_stop_counter=int(a.counters[a.stop - 1]),
            )
            for a in arcs
        ],
        train_intervals=int(data["train"].sum()),
        held_intervals=int((~data["train"]).sum()),
        donor_orbits=len(np.unique(data["orbit"])),
    )
