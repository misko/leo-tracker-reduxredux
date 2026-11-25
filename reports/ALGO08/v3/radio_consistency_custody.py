"""Count signed stereo opportunities and audit custody of released joint labels."""

from collections import Counter
from hashlib import sha256
from math import remainder
from pathlib import Path
from statistics import median
import argparse
import json

from deferred_family_held_support import time_separated
from opposite_radio_profile_preflight import GATE_PIN, PLAN_PIN
from pre_screen_owner_readout import ARMS, CASES, HERE, RELEASE, SOURCES, document, owner_map


RATE = 10_000_000
PILOT_PERIOD = 40_000 / 3
CFO_PERIOD = RATE / 44
GRAPH_GAP_S = 10


def winner(probe):
    gated = [row for row in probe["candidates"] if row["passed_fractional_margin_gate"] is True]
    return max(gated, key=lambda row: (row["fractional_margin"], -row["candidate_rank"]), default=None)


def exact_pairs(native):
    source = native["source"]
    if source["sample_rate_hz"] != RATE or source["probe_ms"] != 20:
        raise ValueError("Unexpected signed receiver clock or aperture")
    radios = sorted({p["receiver_id"] for p in source["probes"]})
    if len(radios) != 2:
        raise ValueError("Need the original two physical radios")
    by_clock = {}
    for p in source["probes"]:
        start, rx = p["valid_start_counter"], p["receiver_id"]
        lanes = by_clock.setdefault((start, p["channel"], p["actual_rf_hz"]), {})
        if rx in lanes:
            raise ValueError("Duplicated exact radio opportunity")
        oid = "sha256:" + sha256(f'{source["session_id"]}:{rx}:{start}'.encode()).hexdigest()
        lanes[rx] = oid, winner(p)
    pairs = []
    for (start, channel, rf), lanes in sorted(by_clock.items()):
        a, b = [lanes.get(rx, (None, None)) for rx in radios]
        item = dict(start=start, channel=channel, rf=rf, ids=[a[0], b[0]],
                    positive=[a[1] is not None, b[1] is not None])
        if all(item["positive"]):
            x, y = a[1], b[1]
            cfo = y["fractional_tracking_cfo_hz"] - x["fractional_tracking_cfo_hz"]
            epoch = ((y["integer_epoch_sample"] - x["integer_epoch_sample"])
                     + (y["fractional_epoch_offset_samples"] - x["fractional_epoch_offset_samples"]))
            item.update(delta_signed_hz=cfo, delta_modulo_hz=remainder(cfo, CFO_PERIOD),
                        removed_cfo_periods=round(cfo / CFO_PERIOD), delta_epoch_samples=remainder(epoch, PILOT_PERIOD))
        pairs.append(item)
    return pairs


def candidate(nomination, stage, native):
    origin = native["clock_anchor"]["sample_counter"]
    pairs = exact_pairs(native)
    by_id = {oid: row for row in pairs for oid in row["ids"] if oid is not None}
    tracks = {row["component"]: set(row["observation_ids"]) for row in stage["tracks"]}
    result = {}
    for family, target in nomination["families"].items():
        seed = set().union(*(tracks[name] for name in target["components"]))
        rfs = {by_id[oid]["rf"] for oid in seed}
        window = target["seed_span"]
        train = [row for row in pairs if row["rf"] in rfs and
                 time_separated(row["start"], RATE // 50, [window], RATE * GRAPH_GAP_S)]
        radio = target["seed_radio"]
        test = [row for row in pairs if row["ids"][radio - 1] in seed and all(row["positive"])]
        comparison = {}
        for name, ids in tracks.items():
            clocks = [row["start"] for row in test if row["ids"][2 - radio] in ids]
            if clocks:
                comparison[name] = clocks
        result[family] = dict(train=train, seed_dual=test, comparison_clocks=comparison,
                              seed_span=window, seed_radio=radio, origin=origin)
    return result


def label_types(row, installed, charted):
    a, b = row["ids"]
    if not all(oid in installed and oid in charted for oid in (a, b)):
        return "unowned_in_one_or_both"
    if installed[a] != charted[a] or installed[b] != charted[b]:
        return "joint_assignments_disagree"
    return "joint_same_family" if installed[a][0] == installed[b][0] else "joint_different_families"


def summary(rows, origin):
    if not rows:
        return dict(pairs=0, occupied_10s_blocks=0, span_s=None)
    t = [row["start"] for row in rows]
    return dict(pairs=len(rows), occupied_10s_blocks=len({(x - origin) // (GRAPH_GAP_S * RATE) for x in t}),
                first_relative_s=(min(t) - origin) / RATE, last_relative_s=(max(t) - origin) / RATE,
                span_s=(max(t) - min(t)) / RATE,
                phase2=sum(abs(row["delta_epoch_samples"]) <= 2 for row in rows),
                signed250=sum(abs(row["delta_signed_hz"]) <= 250 for row in rows),
                modulo250=sum(abs(row["delta_modulo_hz"]) <= 250 for row in rows),
                phase2_and_signed250=sum(abs(row["delta_epoch_samples"]) <= 2 and abs(row["delta_signed_hz"]) <= 250 for row in rows),
                phase2_and_modulo250=sum(abs(row["delta_epoch_samples"]) <= 2 and abs(row["delta_modulo_hz"]) <= 250 for row in rows),
                median_signed_abs_hz=median(abs(row["delta_signed_hz"]) for row in rows),
                median_modulo_abs_hz=median(abs(row["delta_modulo_hz"]) for row in rows),
                removed_period_histogram=dict(Counter(row["removed_cfo_periods"] for row in rows)))


def grade(target, family, named, charted):
    train = target["train"]
    origin = target["origin"]
    groups = {key: [] for key in ("joint_same_family", "joint_different_families", "unowned_in_one_or_both", "joint_assignments_disagree")}
    for pair in train:
        if all(pair["positive"]):
            groups[label_types(pair, named, charted)].append(pair)
    held = target["seed_dual"]
    pred = {oid for oid, owner in named.items() if owner == (family, "predictive") and oid not in charted}
    overlaps = [row for row in held if row["ids"][2 - target["seed_radio"]] in pred]
    controls = {key: summary([row for row in held if row["start"] in starts], origin)
                for key, starts in target["comparison_clocks"].items()}
    return dict(train_opportunities_by_number_of_positives=dict(Counter(sum(row["positive"]) for row in train)),
                training_proxies={key: summary(rows, origin) for key, rows in groups.items()},
                independently_labelled_training_pairs=0, independently_labelled_negative_pairs=0,
                held_seed_dual_positive=summary(held, origin),
                held_exact_missing_predictive_pairs=summary(overlaps, origin),
                held_pred_owner_ids_available=len(pred), held_opposite_curved_controls=controls)


def plan(native_paths, nomination_path):
    metadata = document(nomination_path, PLAN_PIN)
    tape = document(HERE / "measurements/second-curve-gate.json.gz", GATE_PIN)
    config = document(RELEASE / "assets/tracks.json", SOURCES["assets/tracks.json"])["config"]
    if config["alias_spacing_hz"] != CFO_PERIOD or config["max_gap_s"] != GRAPH_GAP_S:
        raise ValueError("Installed alias period or time guard changed")
    result = {}
    for (case, pins), path in zip(CASES.items(), native_paths, strict=True):
        native = document(path, pins["native"])
        scope = metadata["cases"][case]
        if scope["native_sha256"] != pins["native"] or tape[case]["stage"]["native_sha256"] != "sha256:" + pins["native"]:
            raise ValueError("Native packet detached from registered scope")
        result[case] = dict(native_sha256=pins["native"],
                            timing_authority_present=native["source"].get("timing_authority") is not None,
                            targets=candidate(scope, tape[case]["masks"]["after_salvage"], native))
    return dict(cases=result, candidate_window_sha256=PLAN_PIN, source_sha256=sha256(Path(__file__).read_bytes()).hexdigest())


def score(plan_path, pin, witnesses):
    plans = document(plan_path, pin)
    if plans["source_sha256"] != sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError("Candidate windows were produced by a different reducer")
    result = {}
    for (case, pins), path in zip(CASES.items(), witnesses, strict=True):
        evidence = document(path, pins["charted"])["evidence"]
        cross = document(HERE / f"measurements/field-receiver-solver-cross-{case[-4:]}.json.gz", pins["crossover"])
        scope = plans["cases"][case]
        named = cross["score"]
        if (cross["clock"]["exit_code"] or named["new_owners"] != cross["worker"]["ordered_owners"]
                or scope["native_sha256"] != pins["native"]
                or evidence["detail"]["input_sha256"] != cross["admission"]["native_sha256"]
                or evidence["detail"]["input_sha256"] != "sha256:" + pins["native"]
                or evidence["detail"]["region"] != named["named_mixed"]["region"]):
            raise ValueError("Published owner labels are unqualified for same-packet comparison")
        arms = {}
        for arm in ARMS:
            original = owner_map(named["new_owners"][arm], named["new_owner_maps"][arm])
            current = owner_map(evidence["owner_rows"][arm], evidence["owner_maps"][arm])
            arms[arm] = {key: grade(target, int(key), original, current) for key, target in scope["targets"].items()}
        result[case] = dict(native_sha256=pins["native"], charted_witness_sha256=pins["charted"],
                            crossover_sha256=pins["crossover"], timing_authority_present=scope["timing_authority_present"], arms=arms)
    return dict(cases=result, sealed_before_owner_join=pin, source_sha256=plans["source_sha256"],
                ambiguity_period_hz=CFO_PERIOD, pilot_period_samples=PILOT_PERIOD,
                offset_fits=0, orbital_reads=0, waveform_reads=0, lease_attempts=0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    predict = sub.add_parser("plan")
    predict.add_argument("nomination", type=Path)
    predict.add_argument("native", nargs=2, type=Path, metavar=("MIXED_0220", "MIXED_0086"))
    assess = sub.add_parser("score")
    assess.add_argument("plan", type=Path)
    assess.add_argument("pin")
    assess.add_argument("witnesses", nargs=2, type=Path, metavar=("CHARTED_0220", "CHARTED_0086"))
    args = parser.parse_args()
    output = plan(args.native, args.nomination) if args.mode == "plan" else score(args.plan, args.pin, args.witnesses)
    print(json.dumps(output, indent=2, sort_keys=True, allow_nan=False))
