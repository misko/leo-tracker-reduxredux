"""Price the best output-preserving empty-call oracle on sealed field rows."""

import argparse
from collections import Counter
import gzip
from math import fsum, inf
from pathlib import Path
from statistics import fmean, median
import json

from field_speed_reachability import BUILD, STOCK, checked
from first30_native_agreement import LANE, ROWS_SHA, RULE, enroll
from signed_cfo_time_readout import FULL, SPARSE, canonical, document


MODES = ("short_primary", "full")
MEASUREMENTS = Path(__file__).resolve().parent / "measurements"
PINS = {
    "first30-native-agreement": "c9f14a2380f5d1fc58cefdeaf03ff40368b73f1f5beefc921f0a84d016863ed8",
    "late-pilot-rescue": "2b725ccdb473948c2fdbd042a4029060912783f424b8d73c98db34e7537e5a50",
    "short-rank-transfer-DS30-0008": "362052fd7641a0b0175cf90da02234c612e04c6edbd34413c44632ee97c235bd",
    "short-rank-transfer-DS30-0016": "b2354bc31a37b86914d8bbbcb09f96f1f68b88760f4046d2037d48edf89d44ea",
    "three-origin-negative": "de03dc30d9f8be23eff3f3d5ad4642d685037c4cc990e15fc97754b21404dba9",
    "repeat-negative-held": "bde32f5328e1d2bd653c8a5daf6eae6857f75f184ec4371112681a6cd609943b",
    "cyclic-presence": "c2521c28b6d3a193ed83ec3d81c8c6d6209c0031bd8c8836a7b6847dbc3ad65a",
}


def saved(name):
    return json.loads(gzip.decompress(checked(MEASUREMENTS / f"{name}.json.gz", PINS[name])))


def visit_key(row):
    return (row["visit_index"], row["valid_start_counter"], *(row[k] for k in LANE))


def stereo_counts(probes):
    """Recover true paired opportunities and use paid per-stream cadence."""
    cadence, valid = Counter(), []
    out = {mode: Counter() for mode in MODES}
    pairs = zip(probes[::2], probes[1::2], strict=True)
    for a, b in pairs:
        key = visit_key(a)
        if (key != visit_key(b) or [a["receiver_id"], b["receiver_id"]] != [0, 1]
                or (valid and key[0] <= valid[-1])):
            raise ValueError("The signed packets lost chronological stereo pairing")
        valid.append(key[0])
        stream = key[2:]
        mode = RULE[cadence[stream] % len(RULE)]
        cadence[stream] += 1
        if any(len(r["candidates"]) > 1 or any(c["passed_fractional_margin_gate"] is not True
                                              for c in r["candidates"]) for r in (a, b)):
            raise ValueError("Expected original strongest verified lane output")
        e0, e1 = (not r["candidates"] for r in (a, b))
        out[mode].update(visits=1, lanes=2, empty_lanes=e0+e1, rx0_empty=e0, rx1_empty=e1,
                         both_empty=bool(e0 and e1), one_empty=bool(e0 != e1), both_positive=not(e0 or e1))
    return out, valid


def case_result(capture, case, pair, previous):
    paths, rows = {}, {}
    for role, build in (("installed", STOCK), ("successor", BUILD)):
        root, row = pair[role]
        if not root.resolve(strict=True).is_relative_to(capture.resolve(strict=True)):
            raise ValueError("Expected the selected local receipt")
        result = document(root, row["attempt_result_sha256"])
        if (row["build_sha256"] != "sha256:" + build or row["case"] != case or not row["acquisition_verified"]
                or any(row[k] != result[k] for k in ("elapsed_s", "cpu_s", "outcome", "algorithm", "authority_sha256"))):
            raise ValueError("Field attempt differs from its immutable ledger")
        paths[role], rows[role] = root.parent, result
    stock, candidate = (rows[a] for a in ("installed", "successor"))
    pub = paths["successor"] / "publication"
    native_path, = (pub / "fast-scan-automatic-work").glob("*/detections.json")
    packet = document(native_path, candidate["native_sha256"])
    boot = document(pub / "unified-short-bootstrap.json")
    marker = document(pub / "algo08v3-successor-release.json")
    auth = candidate["raw_identity"]
    source = packet["source"]
    recipe = boot["held_anchor_route"]["receiver_recipe"]
    selected, receiver = boot["held_anchor_route"], boot["receiver_audit"]
    native = receiver["native"]
    if (auth != stock["raw_identity"] or candidate["authority_sha256"] != stock["authority_sha256"]
            or marker["authority_sha256"] != candidate["authority_sha256"]
            or marker["build_sha256"] != "sha256:" + BUILD or marker["decision"] != candidate["outcome"]
            or candidate["native_sha256"] != selected["native_sha256"]
            or {"mixed": candidate["native_sha256"], "installed": stock["native_sha256"]} != previous["native_sha256"]
            or auth["raw_authority_sha256"] != source["raw_recording_authority_digest"]
            or receiver["recording_authority"] != auth["raw_authority_sha256"]
            or source["input_manifest_sha256"] != auth["inventory_sha256"]
            or source["session_id"] != auth["session_id"] or source["sample_rate_hz"] != 10_000_000
            or packet["provenance"]["detector_sha256"] != canonical(recipe)
            or native["short_primary_sha256"] != SPARSE or native["installed_sha256"] != FULL
            or recipe["shortened_sha256"] != SPARSE or recipe["installed_sha256"] != FULL
            or native["rule"] != RULE or recipe["rule"] != RULE or recipe["streams"] != list(LANE)
            or recipe["aperture_samples"] != [200_000, 80_000] or selected["choice"]["route"] != "unfiltered"
            or selected["refinement_calls"] or boot["raw_acquisitions"] != 1 or boot["verified_handoffs"] != 1):
        raise ValueError("The selected native packet does not prove the directly measured 20/8 scope")

    probes = source["probes"]
    counts, valid = stereo_counts(probes)
    issued = receiver["issued"]
    invalid = [r["visit"] for r in packet["provenance"]["excluded_windows"]]
    if sorted(valid+invalid) != list(range(issued)) or issued != pair["successor"][1]["window_count"]:
        raise ValueError("Issued and excluded visits do not partition the full signed original")
    for mode in MODES:
        old = previous["counts"]["short" if mode == "short_primary" else "anchor"]
        c = counts[mode]
        if (c["lanes"] != old.get("lanes", 0) or c["lanes"] != native["native_calls"].get(mode, 0)
                or c["visits"] != native["visits"].get(mode, 0)
                or c["empty_lanes"] != old.get("both_empty", 0)+old.get("installed_only_lanes", 0)
                or c["lanes"]-c["empty_lanes"] != old.get("mixed_peaks", 0)
                or c["lanes"]-c["empty_lanes"] != native["factors"].get(mode, 0)):
            raise ValueError("The saved opportunity census differs from the paid native calls")
        c["elapsed_ns"] = native["native_wall_ns"].get(mode, 0)
        c["process_cpu_ns"] = native["native_cpu_ns"].get(mode, 0)
    acquire = boot["phases"]["authenticated_raw_acquisition"]
    if (selected["observed"] != selected["selected"]
            or selected["selected"] != sum(n["lanes"]-n["empty_lanes"] for n in counts.values())
            or not 0 <= fsum(n["elapsed_ns"] for n in counts.values())/1e9 <= acquire["elapsed_s"] <= candidate["elapsed_s"]
            or not 0 <= fsum(n["process_cpu_ns"] for n in counts.values())/1e9 <= acquire["cpu_s"] <= candidate["cpu_s"]):
        raise ValueError("Native clocks or selected evidence do not nest within acquisition")
    return dict(case=case, issued=issued, excluded=len(invalid), admitted=len(valid), modes=counts,
                paid_installed_s=stock["elapsed_s"], paid_installed_cpu_s=stock["cpu_s"],
                paid_candidate_s=candidate["elapsed_s"], paid_candidate_cpu_s=candidate["cpu_s"],
                installed_outcome=stock["outcome"], candidate_outcome=candidate["outcome"],
                acquisition=acquire, native_sha256=candidate["native_sha256"],
                candidate_join_sha256=pair["successor"][1]["attempt_result_sha256"])


def measure_group(times):
    return dict(samples=len(times), cpu_ns=dict(zip(("min", "mean", "max"), (min(x[0] for x in times),
        fmean(x[0] for x in times), max(x[0] for x in times)), strict=True)),
        wall_ns=dict(zip(("min", "mean", "max"), (min(x[1] for x in times),
        fmean(x[1] for x in times), max(x[1] for x in times)), strict=True)))


def donor_clocks():
    result = {}
    for case, saved_case in saved("late-pilot-rescue").items():
        admit, scan = (saved_case[name+".json"] for name in ("admission", "nominations"))
        if (not {FULL, SPARSE}.issubset(admit["document"]["receivers"].values())
                or saved_case["sealed-nominations.json"]["document"] != {
                    "admission.json": admit["source_sha256"], "nominations.json": scan["source_sha256"]}):
            raise ValueError("Donor ABI and signed call clock seal differ")
        by_mode = {}
        for mode in MODES:
            exposed = [r for r in scan["document"]["short"] if r["anchor"] == (mode == "full")]
            by_mode[mode] = {name: measure_group([r["short_cpu_wall_ns"] for r in exposed if r["short_positive"] == flag])
                             for flag, name in ((False, "empty"), (True, "positive"))}
        result[case] = by_mode
    repeated = {}
    for case in ("DS30-0008", "DS30-0016"):
        run = saved(f"short-rank-transfer-{case}")
        if run["build"]["pins"]["sparse"] != SPARSE:
            raise ValueError("A different short binary cannot supply donor clocks")
        records = run["records"]
        repeated[case] = [dict(
            (name, measure_group([(r["runs"][i]["sparse"]["cpu"], r["runs"][i]["sparse"]["wall"])
                                   for r in records if r["positive"] == flag]))
            for flag, name in ((False, "empty"), (True, "positive"))) for i in range(len(records[0]["runs"]))]
    return result, repeated


def empty_credit(mode, clock, ratio, *, pair_only=False):
    """Allocate a real aperture clock by an explicitly transferred cost ratio."""
    empty = mode["empty_lanes"]
    if not empty:
        return 0.
    positive = mode["lanes"] - empty
    share = 1. if ratio == inf else empty*ratio / (empty*ratio+positive)
    eligible = 2*mode["both_empty"] / empty if pair_only else 1.
    return mode[clock]/1e9 * share * eligible


def wall_gate(cases, savings):
    paid = [c["paid_installed_s"] for c in cases]
    adjusted = [c["paid_candidate_s"]-s for c, s in zip(cases, savings, strict=True)]
    values = [c/r for c, r in zip(adjusted, paid, strict=True)]
    center, mass = median(values), fsum(adjusted)/fsum(paid)
    return dict(saved_s=fsum(savings), candidate_s=fsum(adjusted), paired_median_ratio=center,
                summed_ratio=mass, individual_half_time=sum(v <= .5 for v in values),
                qualifies_median=center <= .5, qualifies_sum=mass <= .5)


def oracle(cases, donor, repeated):
    total_short = sum((c["modes"]["short_primary"] for c in cases), Counter())
    deficit = fsum(c["paid_candidate_s"]-.5*c["paid_installed_s"] for c in cases)
    short_s = total_short["elapsed_ns"]/1e9
    empty, positive = total_short["empty_lanes"], total_short["lanes"]-total_short["empty_lanes"]
    estimates = {}

    def apply(name, ratios, *, pairs=False, timing="elapsed_ns"):
        estimates[name] = wall_gate(cases, [fsum(empty_credit(c["modes"][m], timing, r, pair_only=pairs)
                                                  for m, r in ratios.items()) for c in cases])

    apply("free_empty_short_equal_mean", {"short_primary": 1.})
    apply("free_empty_stereo_short_equal_mean", {"short_primary": 1.}, pairs=True)
    apply("free_empty_short_and_anchor_equal_mean", dict.fromkeys(MODES, 1.))
    apply("free_empty_stereo_short_and_anchor_equal_mean", dict.fromkeys(MODES, 1.), pairs=True)
    fav, extremes = {}, {}
    for mode in MODES:
        groups = [d[mode] for d in donor.values()]
        if mode == "short_primary":
            groups += [x for runs in repeated.values() for x in runs]
        fav[mode] = max(g["empty"]["wall_ns"]["mean"]/g["positive"]["wall_ns"]["mean"] for g in groups)
        extremes[mode] = max(g["empty"]["wall_ns"]["max"] for g in groups)/min(g["positive"]["wall_ns"]["min"] for g in groups)
    apply("free_empty_short_donor_ratio", {"short_primary": fav["short_primary"]})
    apply("free_empty_stereo_short_donor_ratio", {"short_primary": fav["short_primary"]}, pairs=True)
    apply("free_empty_short_and_anchor_donor_ratios", fav)
    apply("free_empty_short_donor_extreme", {"short_primary": extremes["short_primary"]})
    apply("free_empty_short_and_anchor_donor_extremes", extremes)
    estimates["free_all_short_wall"] = wall_gate(cases, [c["modes"]["short_primary"]["elapsed_ns"]/1e9 for c in cases])
    estimates["free_all_short_process_cpu_as_wall"] = wall_gate(
        cases, [c["modes"]["short_primary"]["process_cpu_ns"]/1e9 for c in cases])
    estimates["free_all_native_wall"] = wall_gate(cases, [sum(v["elapsed_ns"] for v in c["modes"].values())/1e9 for c in cases])
    estimates["observed"] = wall_gate(cases, [0.]*len(cases))
    donor_both = estimates["free_empty_short_and_anchor_donor_ratios"]
    remaining = deficit - donor_both["saved_s"]
    threshold = dict(required_wall_s=deficit, short_wall_share_required=deficit/short_s,
                     mean_empty_wall_ms_min=1000*deficit/empty, mean_positive_wall_ms_max=1000*(short_s-deficit)/positive,
                     pooled_mean_empty_to_positive_min=(deficit/empty)/((short_s-deficit)/positive),
                     dual_aperture_donor_remaining_wall_s=remaining,
                     dual_aperture_donor_remaining_fraction_of_modeled_candidate=remaining/donor_both["candidate_s"],
                     dual_aperture_donor_remaining_fraction_of_observed_candidate=remaining/estimates["observed"]["candidate_s"],
                     favorable_transferred_mean_ratio=fav, optimistic_transferred_extrema_ratio=extremes)
    return estimates, threshold


def screens():
    three = saved("three-origin-negative")["summaries"]
    repeat = saved("repeat-negative-held")["arms"]
    cyclic = saved("cyclic-presence")["summary"]
    return dict(three_origin={key: {field: three[key][field] for field in
                ("counts", "feature_cpu_ns", "feature_wall_ns", "hindsight_empty")}
                for key in ("dense_total", "independent")}, repeat_negative={key: a["pooled"] for key, a in repeat.items()},
                cyclic_shape={k: {f: cyclic[k][f] for f in ("calibrated", "hindsight")}
                              for k in ("dense", "weak", "held_north")})


def evaluate(capture, ledger):
    groups, _native_pair_bytes = enroll(capture, ledger)
    previous = saved("first30-native-agreement")
    if previous["rows_sha256"] != ROWS_SHA or set(groups) != {r["case"] for r in previous["cases"]}:
        raise ValueError("The earlier signed population census differs")
    cases = [case_result(capture, row["case"], groups[row["case"]], row) for row in previous["cases"]]
    donor, repeated = donor_clocks()
    scenarios, threshold = oracle(cases, donor, repeated)
    return dict(schema_version=1, rows_sha256=ROWS_SHA, prior_receipt_sha256=PINS, cases=cases,
                modes={m: dict(sum((c["modes"][m] for c in cases), Counter())) for m in MODES},
                issued=sum(c["issued"] for c in cases), admitted=sum(c["admitted"] for c in cases),
                excluded=sum(c["excluded"] for c in cases), thresholds=threshold,
                oracle_scope="Every original signed output, aperture and opportunity remains unchanged",
                installed_outcomes=Counter(c["installed_outcome"] for c in cases),
                candidate_outcomes=Counter(c["candidate_outcome"] for c in cases),
                acquisition={k: fsum(c["acquisition"][k] for c in cases) for k in ("cpu_s", "elapsed_s")},
                independent_signed_receipt=previous["counts"], scenarios=scenarios,
                late_pilot_donor_clocks=donor, repeated_sparse_donor_clocks=repeated, old_screens=screens(),
                replayed_receiver_calls=0, replayed_solvers=0, waveform_reads=0, orbit_reads=0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("ledger", type=Path)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.capture, args.ledger), indent=2, sort_keys=True, allow_nan=False))
