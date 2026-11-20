"""Measure held epoch propagation and geographic ranking on four frozen scans."""

from collections import defaultdict
from pathlib import Path
from time import perf_counter

import numpy as np

from leo.sky.frames import (
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets

from ..__main__ import ROOT, save_json
from . import owner_factor_archive
from . import range_epoch_model as m
from .fresh_scenes import _destination
from .full_held_scores import held_references
from .full_v5_check import BULK, _load_case, _sha
from .input_factor_bridge import check, read

OUT = ROOT / "reports/2026_11_19_receiver_screening/receiver-core/range-epoch"
DEVELOPMENT = ("DS26-0036", "DS29-0082")
RESERVE = ("DS26-0237", "DS29-0174")
OFFSETS = (2.0, 25.0)


def native_winners(document):
    from hashlib import sha256

    source = document["source"]
    first = document["clock_anchor"]["sample_counter"]
    rate = source["sample_rate_hz"]
    rxs = sorted({p["receiver_id"] for p in source["probes"]})
    rows = {}
    for probe in source["probes"]:
        if probe["probe_start_ms"] != 0:
            raise ValueError(
                "this recorded panel expects epochs relative to the hardware probe start"
            )
        gated = [p for p in probe["candidates"] if p["passed_fractional_margin_gate"] is True]
        if not gated:
            continue
        peak = max(gated, key=lambda p: (p["fractional_margin"], -p["candidate_rank"]))
        rx, counter = probe["receiver_id"], probe["valid_start_counter"]
        key = f"{source['session_id']}:{rx}:{counter}"
        ident = "sha256:" + sha256(key.encode()).hexdigest()
        if ident in rows:
            raise ValueError("duplicate original native observation identity")
        epoch = peak["integer_epoch_sample"] + peak["fractional_epoch_offset_samples"]
        rows[ident] = dict(
            rx=rxs.index(rx) + 1,
            channel=probe["channel"],
            rf_hz=probe["actual_rf_hz"],
            time_s=(counter - first) / rate + source["probe_ms"] * 0.0005,
            folded_hz=m.wrap(peak["fractional_tracking_cfo_hz"], m.FOLD_HZ),
            phase=m.native_phase(counter, first, epoch, rate),
        )
    return rows


def join_owned(owners, observed):
    groups = defaultdict(list)
    for row in owners:
        winner = observed.get(row["id"])
        if (
            not winner
            or any(winner[k] != row[k] for k in ("rx", "channel", "rf_hz"))
            or abs(winner["time_s"] - row["time_s"]) > 1e-9
            or abs(m.wrap(winner["folded_hz"] - row["folded_hz"], m.FOLD_HZ)) > 1e-5
        ):
            raise ValueError("published original-v5 observation differs from exact native winner")
        owner = int(row["v5_owner"])
        groups[row["component"], owner].append(
            dict(winner, component=row["component"], v5_owner=owner)
        )
    return groups


def load_case(ident):
    case = _load_case(ident)
    path = BULK / case["native"]["path"]
    native_sha = check(path, case["native"]["sha256"])
    document = read(path)
    clock = document["clock_anchor"]
    earlier, later = (clock[seat]["realtime_ns"] for seat in ("before", "after"))
    if (
        earlier != case["cutoff_utc_ns"]
        or later < earlier
        or later - earlier > 2e9
        or case["catalog_timestamp_ns"] > earlier
    ):
        raise ValueError("original clock bracket or catalogue violates the causal request")
    snapshot = BULK / case["catalog"]["path"]
    tle_sha = check(snapshot, case["catalog"]["sha256"])
    catalogue = parse_element_sets(snapshot.read_text())
    sats = {
        int(sat.satnum): sat
        for sat, epoch in zip(
            catalogue.satellites,
            catalogue.element_epoch_utc_ns(),
            strict=True,
        )
        if epoch <= earlier
    }
    owners, _, _, receipt, _ = owner_factor_archive.load_archive(ident)
    if receipt["native_sha256"] != native_sha or not receipt["catalog_in_v5_history"]:
        raise ValueError("original publication has a different native or catalogue source")
    observed = native_winners(document)
    grouped = join_owned(owners, observed)
    arcs = []
    for (_, owner), rows in sorted(grouped.items()):
        if owner in sats:
            arcs.extend(m.split(sorted(rows, key=lambda row: row["time_s"])))
    if not arcs:
        raise ValueError("no fixed 10–60 s orbital arcs on the exact native join")
    origin = (earlier + later) // 2
    rate = document["source"]["sample_rate_hz"]
    proof = dict(
        recorded_winners=len(observed),
        exact_owned_winner_matches=len(owners),
        owned_points_without_current_causal_orbit=sum(
            len(rows) for key, rows in grouped.items() if key[1] not in sats
        ),
        orbit_count=len(set(arc.owner for arc in arcs)),
        arcs=len(arcs),
        arclength_s=[float(arc.time_s[-1] - arc.time_s[0]) for arc in arcs],
        train_points=sum(int(arc.train.sum()) for arc in arcs),
        held_points=sum(int((~arc.train).sum()) for arc in arcs),
        sample_rate_hz=rate,
        native_sha256=native_sha,
        catalog_sha256=tle_sha,
        catalogue_collection_utc_ns=case["catalog_timestamp_ns"],
        anchor_midpoint_utc_ns=origin,
        bracket_ns=later - earlier,
        cutoff_utc_ns=earlier,
        original_v5_publication=receipt,
    )
    return arcs, sats, origin, rate, proof


def predict_states(arcs, sats, origin, delay_s=0.0):
    state = []
    for arc in arcs:
        stamps = origin + np.rint((arc.time_s + delay_s) * 1e9).astype(np.int64)
        jd, fract = julian_day_from_utc_ns(stamps)
        error, position, velocity = sats[arc.owner].sgp4_array(jd, fract)
        if np.any(error):
            raise ValueError("causal orbit did not propagate over a matched arc")
        state.append(teme_to_ecef(position, velocity, greenwich_mean_sidereal_time_rad(jd, fract)))
    return state


def geometry(arcs, state, site, sample_rate):
    position = geodetic_to_ecef_km(*site, 0.0)
    delay, cfo = [], []
    for arc, (p, v) in zip(arcs, state, strict=True):
        delta = p - position
        distance = np.linalg.norm(delta, axis=1)
        radial = np.sum(delta * v, axis=1) / distance
        delay.append(sample_rate * distance / m.LIGHT_KM_S)
        cfo.append(-arc.rf_hz * radial / m.LIGHT_KM_S)
    return delay, cfo


def injected_epochs(arcs, delays, rate):
    rng = np.random.default_rng(750)
    emit_phase = {i: rng.uniform(0, 1 / m.FRAME_HZ) for i in sorted({a.owner for a in arcs})}
    drift = 4.75
    observed = []
    for arc, propagation in zip(arcs, delays, strict=True):
        travel = propagation / rate
        phase = emit_phase[arc.owner]
        q = np.rint((arc.time_s - travel - phase) * m.FRAME_HZ)
        arriving_sample = (q / m.FRAME_HZ + phase + travel) * rate
        samples = arriving_sample + drift * arc.time_s + rng.normal(0.0, 0.12, len(arc.time_s))
        observed.append(samples % (rate / m.FRAME_HZ))
    return observed


def score_epochs(arcs, propagation, rate, *, per_arc=False, observed=None):
    residual, slope = m.frame_residual(arcs, propagation, rate, per_arc=per_arc, observed=observed)
    return dict(m.held_loss(arcs, residual), trained_clock_slopes_sample_s=slope)


def geometric_offers(truth):
    yield "reference", 0.0, truth
    for radius in OFFSETS:
        for j, direction in enumerate(("N", "E", "S", "W")):
            yield f"{radius:g} km {direction}", radius, _destination(truth, radius, j * np.pi / 2)


def evaluate(ident, arcs, sats, origin, rate, proof, truth):
    state = predict_states(arcs, sats, origin)
    at_truth, _ = geometry(arcs, state, truth, rate)
    time_shifted, _ = geometry(arcs, predict_states(arcs, sats, origin, 15.0), truth, rate)
    zeros = [np.zeros_like(d) for d in at_truth]
    reflected = [-d for d in at_truth]
    injected = injected_epochs(arcs, at_truth, rate)
    models = {}
    for variant, values, observed in (
        ("propagation", at_truth, None),
        ("clock_only", zeros, None),
        ("reflected", reflected, None),
        ("delay_15s", time_shifted, None),
        ("shuffled_epochs", at_truth, m.shuffled_epochs(arcs)),
        ("injected_propagation", at_truth, injected),
        ("injected_reflected", reflected, injected),
    ):
        models[variant] = {
            aid: score_epochs(arcs, values, rate, per_arc=per_arc, observed=observed)
            for aid, per_arc in (("shared_clock", False), ("independent_arc_clock", True))
        }
    candidates = []
    for label, radius, site in geometric_offers(truth):
        p, f = geometry(arcs, state, site, rate)
        epoch = score_epochs(arcs, p, rate)
        sensitivity = score_epochs(arcs, p, rate, per_arc=True)
        frequency = m.held_loss(arcs, m.frequency_residual(arcs, f))
        cfo = frequency["arc_median_mae"] / m.CFO_UNIT
        candidates.append(
            dict(
                location=label,
                offset_km=radius,
                frame=epoch,
                frame_per_arc=sensitivity,
                cfo=frequency,
                score=dict(
                    cfo=cfo,
                    frame=epoch["arc_median_mae"] / m.EPOCH_UNIT,
                    frame_per_arc=sensitivity["arc_median_mae"] / m.EPOCH_UNIT,
                    joint=cfo + epoch["arc_median_mae"] / m.EPOCH_UNIT,
                    joint_per_arc=cfo + sensitivity["arc_median_mae"] / m.EPOCH_UNIT,
                ),
            )
        )
    rankings = {
        key: [p["location"] for p in sorted(candidates, key=lambda p: p["score"][key])]
        for key in candidates[0]["score"]
    }
    return dict(
        id=ident,
        cohort="development" if ident in DEVELOPMENT else "held",
        proof=proof,
        controls=models,
        geometry=candidates,
        rankings=rankings,
    )


def main():
    cases = (*DEVELOPMENT, *RESERVE)
    plan = OUT / "plan.json"
    if plan.exists():
        raise ValueError("the predeclared epoch benchmark has already been launched")
    sources = (
        Path(__file__),
        Path(m.__file__),
        Path(owner_factor_archive.__file__),
        OUT / "PROTOCOL.md",
    )
    save_json(
        plan,
        dict(
            cases=cases,
            development=DEVELOPMENT,
            held=RESERVE,
            source_files={str(p.relative_to(ROOT)): _sha(p) for p in sources},
        ),
    )
    _, references = held_references(None, cases)
    refs = {r["id"]: r["truth"] for r in references}
    rows = []
    for ident in cases:
        began = perf_counter()
        evidence = load_case(ident)
        if evidence[-1]["arcs"]:
            result = evaluate(ident, *evidence, refs[ident])
            rows.append(result)
            print(
                ident,
                result["proof"]["arcs"],
                result["proof"]["held_points"],
                {k: v.index("reference") + 1 for k, v in result["rankings"].items()},
                f"{perf_counter() - began:.2f}s",
                flush=True,
            )
    for source, digest in read(plan)["source_files"].items():
        check(ROOT / source, digest)
    path = OUT / "scores.json"
    save_json(path, rows)
    save_json(
        OUT / "measurement-lock.json",
        dict(cases=cases, files={p.name: _sha(p) for p in (plan, path)}),
    )


if __name__ == "__main__":
    main()
