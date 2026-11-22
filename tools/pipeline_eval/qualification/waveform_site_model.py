"""Draw physically delayed, Doppler-rotated Qin pilot IQ for scheduled dual-RX visits."""

import numpy as np

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from . import cold_scenes as orbit
from .compact_blind_generator import EDGE_HZ, SCHEDULE, regional_offer

SITE_BOX = (9.5, 76.5)
LOW_HEIGHT_RANGE_M = (25.0, 110.0)
SWEEPS = 150
DWELL = 20
STRIDE_MS = 44
SWEEP_S = 2
RATE = orbit.RATE
SAMPLES = RATE // 50
OVER = 4
INDEX = np.arange(SAMPLES, dtype=np.float64)


def schedule():
    rows = []
    for sweep in range(SWEEPS):
        for channel in range(8):
            edge = "lower" if channel % 2 == 0 else "upper"
            rf = orbit.CHANNELS[channel] + (-EDGE_HZ if edge == "lower" else EDGE_HZ)
            counter = (sweep * SWEEP_S * 1000 + channel * STRIDE_MS) * RATE // 1000
            rows.append(
                dict(
                    visit=len(rows),
                    channel=channel + 1,
                    edge=edge,
                    rf_hz=int(rf),
                    relative_counter=counter,
                )
            )
    return rows


def pulse_bank():
    return {
        edge: qin_edge_pilot_frame(RATE * OVER, edge).astype(np.complex64)
        for edge in ("lower", "upper")
    }


def pulse(frame, epoch, period):
    phase = np.remainder(INDEX - epoch, period) * (RATE * OVER / (orbit.FRAME_HZ * period))
    lo = phase.astype(np.int32)
    w = (phase - lo).astype(np.float32)
    return frame[lo % len(frame)] * (1 - w) + frame[(lo + 1) % len(frame)] * w


def iq(record, profile, frame):
    """Quantize exact per-lane emissions and independent receiver nuisances to CI16."""
    rng = np.random.default_rng(record["sample_seed"])
    time = (INDEX - (SAMPLES - 1) / 2) / profile["sample_rate_truth_hz"]
    out = np.empty((SAMPLES, 2, 2), dtype="<i2")
    for lane, plant in enumerate(record["planted"]):
        reuse = time * record["tone_hz"] + rng.uniform(-0.5, 0.5)
        wave = (record["tone_amplitude"] * np.exp(2j * np.pi * reuse)).astype(np.complex64)
        if plant is not None:
            epoch, period = plant["epoch"], plant["period"]
            pilot = pulse(frame, epoch, period)
            echoed = pulse(frame, epoch + 1.2 + 0.3 * lane, period)
            pilot += (0.11 + 0.065j) * echoed
            carrier = (
                time * plant["actual_cfo_hz"]
                + 0.5 * plant["slope_hz_s"] * time**2
                + rng.uniform(-0.5, 0.5)
            )
            wave += (plant["amplitude"] * pilot * np.exp(2j * np.pi * carrier)).astype(np.complex64)
        out[:, lane, :] = np.clip(
            np.rint(
                np.column_stack((wave.real, wave.imag)) + rng.normal(0, 530, size=(SAMPLES, 2))
            ),
            -32768,
            32767,
        ).astype("<i2")
    return out


def make_scene(bank, causal, anchor, rng, *, height_range_m=LOW_HEIGHT_RANGE_M):
    site = (np.asarray(SITE_BOX) + rng.uniform(-2.0, 2.0, 2)).tolist()
    height = float(rng.uniform(*height_range_m))
    xyz = geodetic_to_ecef_km(*site, height)
    emitters = orbit._emitters(bank, anchor, xyz, ecef_to_enu_matrix(*site), rng)
    scan = schedule()
    counter = int(rng.integers(10_000_000, 40_000_000))
    physical_rate = RATE * (1.0 + float(rng.uniform(-0.35e-6, 0.35e-6)))
    clock = float(rng.uniform(-0.0015, 0.0015))
    times = np.array([r["relative_counter"] for r in scan]) / physical_rate + clock
    times += (SAMPLES - 1) / (2 * physical_rate)
    lo = rng.uniform(-1800.0, 1800.0, 2)
    drift = rng.normal(0.0, 0.55, 2)
    rf_gain = float(rng.choice([-1, 1]) * rng.uniform(500, 1350))
    tx = []
    for row in scan:
        row["planted"] = [None, None]
        row["sample_seed"] = int(rng.integers(0, 2**63))
        row["tone_hz"] = float(rng.uniform(-4e5, 4e5))
        row["tone_amplitude"] = float(rng.uniform(90, 270))
    nominal = {s.satnum: s for s in causal}
    for j, (block, _, truth) in enumerate(emitters):
        channel = SCHEDULE[block][j % 2] + 1
        used = [
            r["visit"]
            for r in scan
            if r["channel"] == channel and 50 * block + 3 < times[r["visit"]] < 50 * block + 47
        ]
        t = times[used]
        delay, velocity = orbit._signal(truth, anchor, t, xyz)
        _, before = orbit._signal(truth, anchor, t - 0.01, xyz)
        _, after = orbit._signal(truth, anchor, t + 0.01, xyz)
        _, model_rate = orbit._signal(nominal[truth.satnum], anchor, t, xyz)
        phase = float(rng.uniform(0, 1 / orbit.FRAME_HZ))
        tx_offset = float(rng.normal(0.0, 65.0))
        adc = float(rng.uniform(820, 1550))
        tx.append(
            dict(
                norad=int(truth.satnum),
                block=block,
                channel=channel,
                frame_phase_s=phase,
                carrier_offset_hz=tx_offset,
                scheduled_visits=len(used),
            )
        )
        for k, visit in enumerate(used):
            row = scan[visit]
            f = row["rf_hz"]
            rad = velocity[k]
            # Nearby frame arrival is recovered in physical ADC samples before wrapping.
            tick = np.rint((t[k] - delay[k] - phase) * orbit.FRAME_HZ)
            arrival = tick / orbit.FRAME_HZ + phase + delay[k]
            period = physical_rate / orbit.FRAME_HZ * (1.0 + rad / orbit.LIGHT_KM_S)
            local = (arrival - clock) * physical_rate - row["relative_counter"]
            for lane in (0, 1):
                cfo = (
                    -f / orbit.LIGHT_KM_S * rad
                    + tx_offset
                    + lo[lane]
                    + drift[lane] * (t[k] - 150)
                    + rf_gain * (f / 1e9 - 11.5)
                )
                epoch = (local + 0.42 * lane) % period
                row["planted"][lane] = dict(
                    norad=int(truth.satnum),
                    epoch=float(epoch),
                    period=float(period),
                    amplitude=float(
                        adc * np.clip(0.0029 / delay[k], 0.55, 1.35) * rng.uniform(0.70, 1.22)
                    ),
                    actual_cfo_hz=float(cfo),
                    cfo_model_hz=float(cfo * RATE / physical_rate),
                    slope_hz_s=float(-f / orbit.LIGHT_KM_S * (after[k] - before[k]) / 0.02),
                    catalogue_mismatch_hz=float(-f / orbit.LIGHT_KM_S * (rad - model_rate[k])),
                )
    axis, sign = int(rng.integers(0, 2)), int(rng.choice([-1, 1]))
    offers = {
        "containing": regional_offer(site, axis, sign, float(rng.uniform(6, 9))),
        "omitted": regional_offer(site, axis, sign, 14.0),
    }
    return scan, dict(
        coordinate=site,
        height_m=height,
        counter=counter,
        clock_s=clock,
        sample_rate_truth_hz=physical_rate,
        receiver_lo_hz=lo.tolist(),
        lo_drift_hz_s=drift.tolist(),
        rf_constant_hz_per_ghz=rf_gain,
        emitters=tx,
        offers=offers,
    )
