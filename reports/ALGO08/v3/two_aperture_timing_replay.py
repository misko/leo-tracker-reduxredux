"""Read saved exact callbacks and independent full-aperture timing proposals."""

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from math import remainder
from pathlib import Path


MEASUREMENTS = Path(__file__).resolve().parent / "measurements"
PINS = {
    "differential-fold.json": "2f9cb104300f22ade2c15ce7d47d01278ea34aabc76a3a655e3fc6d9627cc3b2",
    "ds30-0049-receiver-factorial.json.gz": "4af8b73101dce9b71a06b38a10e2484ef04b74f42b5221cfec1e818d21ea3b58",
    "eight-ms-primary.json.gz": "a6b67123abe0a740b2843f08cc1cde7f603e6f18dd890ad15cc3b3243fc317b3",
    "late-pilot-rescue.json.gz": "2b725ccdb473948c2fdbd042a4029060912783f424b8d73c98db34e7537e5a50",
    "timing-only-oracle.json.gz": "8ca823ea9a3e563c018c0b078ae162c69604e341798bc2532cf7692d753a5dcc",
}
MODES = ("8-primary", "20-primary", "20-two")
PERIOD = 13_333
WIDE_TIMING = 7
EXACT_TIMING = 2
SIGNED_CFO = 250
ROWS = 4


def read(name):
    content = (MEASUREMENTS / name).read_bytes()
    if sha256(content).hexdigest() != PINS[name]:
        raise ValueError(f"Saved source changed: {name}")
    return json.loads(gzip.decompress(content) if name.endswith(".gz") else content)


def first(rows):
    return rows[0] if rows else None


def coordinates(factor):
    if factor is None:
        return None
    return factor["integer_epoch_sample"]+factor["fractional_epoch_offset_samples"], factor["fractional_tracking_cfo_hz"]


def distance(a, b):
    return abs(remainder(a-b, PERIOD))


def same_measurement(a, b):
    return a is not None and b is not None and distance(a[0], b[0]) <= EXACT_TIMING and abs(a[1]-b[1]) <= SIGNED_CFO


def main_prices(rows):
    paid = {mode: [0, 0] for mode in MODES}
    retries = {mode: [0, 0] for mode in ("all_short_empty", "oracle_recovered_empties", "oracle_all_missed_primary")}
    stats = Counter()
    for row in rows:
        for mode in MODES:
            actual = "20-two" if row["anchor"] else mode
            for i, ns in enumerate(row["clocks"][actual]):
                paid[mode][i] += ns
        if row["anchor"]:
            stats["common_anchors"] += 1
            continue
        small, large = (coordinates(first(row["alternatives"][k])) for k in MODES[:2])
        acquired = same_measurement(small, large)
        for label, selected in (
                ("all_short_empty", small is None), ("oracle_recovered_empties", small is None and large is not None),
                ("oracle_all_missed_primary", large is not None and not acquired)):
            if selected:
                stats[label] += 1
                for i, ns in enumerate(row["clocks"]["20-primary"]):
                    retries[label][i] += ns
        stats["nonanchors"] += 1
        stats["short_positive"] += small is not None
        stats["full_primary_positive"] += large is not None
        stats["short_matches_full_primary"] += acquired
        stats["short_only_positive"] += small is not None and large is None
    total = {k:[a+b for a,b in zip(paid["8-primary"], timing, strict=True)] for k,timing in retries.items()}
    uncharged = {k:[a-b for a,b in zip(paid["20-primary"], timing, strict=True)] for k,timing in total.items()}
    return dict(lanes=dict(stats), original_native_cpu_wall_ns=paid, added_retries_cpu_wall_ns=retries,
                complete_short_plus_retries_cpu_wall_ns=total, remaining_vs_full_primary_cpu_wall_ns=uncharged,
                all_lane_rescue_budget_cpu_ns=(paid["20-primary"][0]-paid["8-primary"][0])/stats["nonanchors"])


def short_inputs(aperture, cohort):
    if cohort == "weak":
        return {(r["id"], r["rx"]): (r["sample_sha256"], r["edge"], None, None, coordinates(r["factors"]["8ms"]))
                for r in aperture["weak"]["records"]}
    digests = aperture["input_sha256"]["chronological_dense_iq_sha256"]
    return {(f'DS30-0008:{r["visit_index"]}', r["receiver_id"]):
            (digests[r["visit_index"]], r["edge"], r["valid_start_counter"], r["actual_rf_hz"], coordinates(first(r["candidates"])))
            for r in aperture["dense"]["probes"]["8ms"]}


def proposal_coverage(short, long, folded, cohort):
    recorded = dict(folded["inputs"])
    unsupported = {(key, lane, rank): (integer, frequency, phase, verified)
                   for key, lane, rank, integer, frequency, _, phase, verified in folded["misses"]}
    denominator = Counter()
    evidence = []
    for row in long:
        if row["kind"] != "full" or row["key"] not in recorded:
            continue
        if cohort == "dense" and row["scheduled"] != "short":
            continue
        key, lane = row["key"], row["antenna"]
        digest, edge, counter, rf, short_peak = short[key, lane]
        if digest != recorded[key] or digest != row["iq"] or edge != row["edge"] or (
                counter is not None and (counter, rf) != (row["sample"], row["rf"])):
            raise ValueError("The archived physical or simulation lanes do not bind identical source samples")
        denominator["schedule_lanes"] += 1
        denominator["empty_full_primary_lanes"] += not any(r[0] == 0 for r in row["factors"])
        for rank, epoch, fraction, hz, _, _ in row["factors"]:
            if rank != 0:
                continue
            picks = row["scopes"][0][0]
            if len(picks) != 12:
                raise ValueError("Original full timing grid row count changed")
            nearest = min(distance(4*i, epoch+fraction) for i in picks[:ROWS])
            any_original = min(distance(4*i, epoch+fraction) for i in picks)
            empty = short_peak is None
            hit = same_measurement(short_peak, (epoch+fraction, hz))
            short_timing = not empty and distance(short_peak[0], epoch+fraction) <= WIDE_TIMING
            legacy_miss = unsupported.get((key, lane, rank))
            if legacy_miss is not None and legacy_miss[:2] != (epoch, hz):
                raise ValueError("The differential and exact full ledgers disagree on the reference factor")
            fold_phase = legacy_miss is None or legacy_miss[2]
            fold_signed = legacy_miss is None
            for label, selected in (("all_primary", True), ("short_empty", empty), ("short_unmatched", not hit)):
                if selected:
                    denominator.update({f"{label}/factors": 1, f"{label}/short_signed_match": hit,
                        f"{label}/short_phase": short_timing, f"{label}/full_top4_phase": nearest<=WIDE_TIMING,
                        f"{label}/full_top12_phase": any_original<=WIDE_TIMING,
                        f"{label}/differential_phase": fold_phase, f"{label}/differential_signed_seed": fold_signed,
                        f"{label}/short_or_full_top4_phase": short_timing or nearest<=WIDE_TIMING,
                        f"{label}/short_or_differential_phase": short_timing or fold_phase})
            evidence.append(dict(original_visit=key, receiver=lane, iq=digest, full_primary=[epoch, fraction, hz],
                                 short_peak=short_peak, full_top4=picks[:ROWS], distance_from_full4=nearest,
                                 distance_from_full12=any_original, differential_phase=fold_phase,
                                 differential_signed_seed=fold_signed))
    return dict(counts=dict(denominator), lanes=evidence)


def audit():
    main = read("ds30-0049-receiver-factorial.json.gz")
    main_rows = main["native-rows.json"]["document"]
    price = main_prices(main_rows)
    factorial = main["scored.json.gz"]["document"]["measurements"]
    for mode, clocks in price["original_native_cpu_wall_ns"].items():
        if clocks != factorial[f"{mode}/strongest"]["callback_cpu_wall_ns"]:
            raise ValueError("The new timing partition revised a sealed callback clock")
    price["owned_empty_recoveries"] = {mode: {arm: factorial[f"{mode}/strongest"]["owners"][f"{arm}/lost_empty"]
        for arm in ("c0", "fitted_c")} for mode in MODES}

    aperture = read("eight-ms-primary.json.gz")
    timing = read("timing-only-oracle.json.gz")
    differential = read("differential-fold.json")
    late = read("late-pilot-rescue.json.gz")
    return dict(source_sha256=PINS, measured_0049=price,
                independent_timing={cohort: proposal_coverage(short_inputs(aperture, cohort), timing[cohort]["rows"],
                                                             differential[cohort], cohort) for cohort in ("dense", "weak")},
                late_prior_scopes=sorted(late), waveform_bytes=0, new_native_runs=0)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    result = audit()
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
