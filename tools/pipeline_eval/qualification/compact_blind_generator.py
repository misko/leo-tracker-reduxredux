"""Generate new-location native factors from retarded wideband orbital Doppler."""

from dataclasses import dataclass

import numpy as np

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from . import cold_scenes as orbit

BOXES = ((30.0, -7.0), (-31.0, -54.0), (44.0, 93.0), (-13.0, 164.0))
ANCHOR_OFFSETS_S = (3240, 8640, 15480, 33120)
SLOT_MS = 44
EDGE_HZ = 115_312_500
SCHEDULE = ((0, 5), (2, 7), (1, 4), (3, 6), (0, 6), (2, 5))


@dataclass(frozen=True)
class Emitter:
    nominal: object
    phase_s: float

    def sgp4_array(self, jd, fraction):
        return self.nominal.sgp4_array(jd, fraction + self.phase_s / 86400)


def regional_offer(site, axis, sign, distance):
    """Use the same exact local axes as the installed rectangular 25 km offer."""
    lat, lon = site
    if axis == 0:
        return [lat, lon + sign * distance / (111.32 * np.cos(np.deg2rad(lat)))]
    return [lat + sign * distance / 111.0, lon]


def local_offset(site, center):
    return (
        (site[1] - center[1]) * 111.32 * np.cos(np.deg2rad(center[0])),
        (site[0] - center[0]) * 111.0,
    )


def make_case(catalogue, collected, index, rng):
    site = (np.asarray(BOXES[index]) + rng.uniform(-2, 2, 2)).tolist()
    elevation_m = float(rng.uniform(15, 110))
    anchor = collected + ANCHOR_OFFSETS_S[index] * orbit.NS
    xyz = geodetic_to_ecef_km(*site, elevation_m)
    satellites = orbit._constellation(catalogue, collected)
    opportunities = orbit._emitters(satellites, anchor, xyz, ecef_to_enu_matrix(*site), rng)
    counter = int(rng.integers(10_000, 30_000_000))
    elapsed_ms = np.arange(0, 300_000 - orbit.PROBE_MS + 1, SLOT_MS, dtype=np.int64)
    starts = elapsed_ms * orbit.RATE // 1000
    channel = np.arange(len(starts)) % 8
    clock_s = float(rng.uniform(-0.002, 0.002))
    clock_rate = orbit.RATE * (1 + float(rng.uniform(-0.5e-6, 0.5e-6)))
    sample_t = (starts + orbit.RATE * 0.010) / clock_rate + clock_s
    lo = rng.uniform(-2500.0, 2500.0, 2)
    lo_drift = rng.normal(0.0, 0.55, 2)
    c = float(rng.choice([-1, 1]) * rng.uniform(450, 1450))
    emitted = {}
    truth = []
    for j, (block, _, sat) in enumerate(opportunities):
        ch = SCHEDULE[block][j % 2]
        use = np.flatnonzero(
            (channel == ch) & (sample_t > block * 50 + 3) & (sample_t < block * 50 + 47)
        )
        phase = float(rng.normal(0.0, 0.16))
        delay, rate = orbit._signal(Emitter(sat, phase), anchor, sample_t[use], xyz)
        frame_s = float(rng.uniform(0, 1 / orbit.FRAME_HZ))
        signal_bias = float(rng.normal(0.0, 70.0))
        epochs = orbit._relative_epoch(
            delay, frame_s, clock_s, clock_rate, starts[use], sample_t[use]
        )
        innovations = rng.normal(0.0, 16.0, len(use))
        for k in range(1, len(use)):
            innovations[k] += 0.78 * innovations[k - 1]
        for k, at in enumerate(use):
            emitted[int(at)] = (epochs[k], rate[k], signal_bias + innovations[k])
        truth.append(
            dict(
                block=block,
                channel=ch + 1,
                norad=int(sat.satnum),
                orbit_phase_s=phase,
                transmitter_frequency_offset_hz=signal_bias,
                frame_phase_s=frame_s,
            )
        )
    probes = []
    for i, (ch, start) in enumerate(zip(channel, starts, strict=True)):
        for rx, sign in enumerate((-1, 1)):
            rf = orbit.CHANNELS[ch] + sign * EDGE_HZ
            candidates = []
            if i in emitted and rng.random() > 0.075:
                epoch, radial_rate, bias = emitted[i]
                frequency = (
                    -rf / orbit.LIGHT_KM_S * radial_rate
                    + bias
                    + lo[rx]
                    + lo_drift[rx] * (sample_t[i] - 150)
                    + c * (rf / 1e9 - 11.5)
                    + rng.normal(0.0, 32.0)
                )
                epoch = (epoch + 0.35 * rx + rng.normal(0.0, 0.16)) % (orbit.RATE / orbit.FRAME_HZ)
                candidates.append(orbit._peak(0, frequency, epoch, rng.uniform(0.08, 0.38)))
            if rng.random() < 0.045:
                candidates.append(
                    orbit._peak(
                        len(candidates),
                        rng.uniform(-orbit.CFO_ALIAS_HZ / 2, orbit.CFO_ALIAS_HZ / 2),
                        rng.uniform(0.0, orbit.RATE / orbit.FRAME_HZ),
                        rng.uniform(0.007, 0.042),
                    )
                )
            row = orbit._probe_row(i, rx, ch, int(start + counter), candidates)
            row["actual_rf_hz"] = int(rf)
            probes.append(row)
    orbit._check_probe_times(probes, counter, orbit.RATE, orbit.PROBE_MS, 300)
    axis, sign = int(rng.integers(0, 2)), int(rng.choice([-1, 1]))
    offers = dict(
        containing=regional_offer(site, axis, sign, float(rng.uniform(7, 10))),
        omitted=regional_offer(site, axis, sign, 14.0),
    )
    for mode, center in offers.items():
        inside = max(map(abs, local_offset(site, center))) <= 12.5
        if inside != (mode == "containing"):
            raise AssertionError("offered square does not preserve the frozen geographic condition")
    return (
        anchor,
        probes,
        counter,
        offers,
        dict(
            site=site,
            elevation_m=elevation_m,
            clock_offset_s=clock_s,
            sample_clock_rate_hz=clock_rate,
            receiver_lo_hz=lo.tolist(),
            receiver_drift_hz_s=lo_drift.tolist(),
            rf_coefficient_hz_per_ghz=c,
            emitters=truth,
        ),
    )
