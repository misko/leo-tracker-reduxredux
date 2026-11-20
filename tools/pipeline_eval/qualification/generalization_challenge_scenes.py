"""Generate supported native GLRT factors at geographically independent blind sites."""

from collections import defaultdict

import numpy as np
from scipy.optimize import root

from ..__main__ import encoded, write
from . import challenge_scenes_generator as perturb
from . import clock_model_synthetic as clock_model
from . import cold_scenes as cold
from . import site_transfer_samples as samples
from .portable_v5_transfer import authentic_history, preferred_history, simulated_document

BOXES = ((48, -120), (-26, -68), (5, 38), (34, 112), (-39, 169))
AGE_HOURS = (0.4, 1.3, 3.0, 6.0, 10.0)
CONDITIONS = {"present": 5.0, "inside-edge": 1.5, "outside-edge": -2.0, "omitted": -25.0}


def local(site, center):
    frame = cold.ecef_to_enu_matrix(*center)
    delta = cold.geodetic_to_ecef_km(*site, 0.0) - cold.geodetic_to_ecef_km(*center, 0.0)
    return frame[:2] @ delta


def offer_center(site, target):
    position = root(lambda center: local(site, center) - target, site)
    if not position.success or np.max(abs(local(site, position.x) - target)) > 1e-6:
        raise ValueError("offered square could not be positioned to the declared face clearance")
    return position.x.tolist()


def clearance(site, center, width=25.0):
    exceed = abs(local(site, center)) - width / 2
    return float(-np.linalg.norm(np.maximum(exceed, 0)) if max(exceed) > 0 else -max(exceed))


def add_empirical_cfo(document, pool, rng):
    grouped = defaultdict(list)
    phases = rng.uniform(0, 2 * np.pi, (2, len(clock_model.PERIODS_S)))
    gain = rng.uniform(0.6, 1.4, 2)
    for probe in document["probes"]:
        time = (probe["valid_start_counter"] - document["first_counter"]) / cold.RATE
        time += cold.PROBE_MS / 2000
        signal = [p for p in probe["candidates"] if p["passed_fractional_margin_gate"]]
        if signal:
            grouped[int(time // 50), probe["receiver_id"], probe["channel"]].append(
                (time, probe["actual_rf_hz"], signal[0])
            )
    audit = []
    for (block, rx, ch), rows in sorted(grouped.items()):
        key, t, z = samples._window(pool, rng)
        time = np.array([r[0] for r in rows])
        host_clock = clock_model.oscillator(time, phases[rx]) * gain[rx]
        # Use the empirical frequency error shape, with no donor geometry or lanes in inference.
        texture = np.interp(time - block * 50 - 5, t, z) if len(t) >= 2 else np.zeros(len(time))
        for (_, rf, peak), smooth, noise in zip(rows, host_clock, texture, strict=True):
            y = peak["fractional_tracking_cfo_hz"] + smooth * rf / 11.5e9 + noise
            peak["fractional_tracking_cfo_hz"] = float(cold._wrap_cfo(y))
        audit.append(
            dict(
                block=block,
                receiver_id=rx,
                channel=ch,
                donor=key,
                noise_rms_hz=float(np.sqrt(np.mean(texture**2))),
                smooth_rms_hz=float(np.sqrt(np.mean(host_clock**2))),
            )
        )
    return audit


def generate(seed, work):
    received, nominal, history, _ = authentic_history()
    constellation = cold._constellation(nominal, received)
    satellites = {r.satnum: r for r in constellation}
    pool, receipts = samples.donors()
    rng = np.random.default_rng(int.from_bytes(seed, "big"))
    catalogue = work / "orbit.tle"
    write(catalogue, nominal)
    queries, labels, capture_audit = [], {}, {}

    def packet(ident, anchor, probes, counter):
        native = work / f"{ident}.json"
        document = simulated_document(ident, anchor, probes, counter)
        write(native, encoded(document))
        cutoff = document["clock_anchor"]["before"]["realtime_ns"]
        causal = preferred_history(history, cutoff)
        return dict(native=native, cutoff=cutoff, probes=len(probes), history=causal)

    for i, (middle, age) in enumerate(zip(BOXES, AGE_HOURS, strict=True), 1):
        site = (np.asarray(middle) + rng.uniform(-3, 3, 2)).tolist()
        ident = rng.bytes(10).hex()
        anchor = received + int(age * 3600 * cold.NS)
        probes, counter, truth = cold._generate_capture(constellation, anchor, site, rng)
        clock_doc = dict(
            probes=probes,
            first_counter=counter,
            anchor_utc_ns=anchor,
        )
        truth["latlon"] = site
        disturbances = perturb._perturb(clock_doc, truth, satellites, rng)
        measured = add_empirical_cfo(clock_doc, pool, rng)
        cases = packet(ident, anchor, probes, counter)
        capture_audit[ident] = dict(
            site_index=i,
            snapshot_age_h=age,
            phase_and_gaps=disturbances,
            measured=measured,
            capture_ns=anchor,
        )
        axis, sign = int(rng.integers(2)), int(rng.choice([-1, 1]))
        offset = np.full(2, rng.uniform(-7, 7))
        for condition, boundary in CONDITIONS.items():
            offset[axis] = sign * (12.5 - boundary)
            qi = rng.bytes(10).hex()
            center = offer_center(site, offset)
            offer = dict(id=qi, center=center, width_km=25.0)
            queries.append(dict(id=qi, capture=ident, offer=offer, **cases))
            labels[qi] = dict(
                site=i,
                condition=condition,
                truth=site,
                boundary_clearance_km=clearance(site, center),
            )
        if i == 1:
            null_id = rng.bytes(10).hex()
            shuffled = packet(null_id, anchor, cold._shuffled(probes, rng), counter)
            qi = rng.bytes(10).hex()
            queries.append(
                dict(id=qi, capture=null_id, offer=dict(queries[-4]["offer"], id=qi), **shuffled)
            )
            labels[qi] = dict(
                site=None, condition="shuffle", truth=None, boundary_clearance_km=None
            )
    rng.shuffle(queries)
    return (
        queries,
        labels,
        catalogue,
        received,
        dict(captures=capture_audit, donor_receipts=receipts),
    )
