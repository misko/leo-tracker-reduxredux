"""Compare the temporal span of saved Doppler associations on matched field recordings."""

import argparse
from collections import defaultdict
from gzip import decompress
import json
from math import fsum
from pathlib import Path
from statistics import fmean

from .ds30_centered_error import verified_overlay
from .ds30_evidence_transfer import classify, signed
from .ds30_grid_triage import case_group, snapshot_inputs, tau_b, verified_attempt
from .ds30_oracle_routing import CAMPAIGN, checked, digest
from .field_fallback_budget import FIRST, FIRST_SEAL
from .full_successor_score import ARMS, BUILDS, OFFER, paired_rows, roster
from .signed_cfo_time import MAX_GAP, SAMPLE_RATE


MEASURES = ("count", "slope", "quadratic")


def design(counters):
    """Information for 1, t and t² after fitting all lower-order terms."""
    if not counters:
        return (0, 0., 0.)
    t = [(c - counters[0]) / SAMPLE_RATE for c in counters]
    mean = fmean(t)
    t = [x - mean for x in t]
    linear = fsum(x*x for x in t)
    if len(set(counters)) < 3:
        return (len(t), linear, 0.)
    mean_square = linear / len(t)
    coefficient = fsum(x**3 for x in t) / linear
    residual = fsum((x*x - mean_square - coefficient*x)**2 for x in t)
    return (len(t), linear, residual)


def support(groups):
    totals = {key: [0., 0., 0.] for key in ("all", "corroborated", "anchors")}
    segments = 0
    for series in groups.values():
        ordered = sorted(series)
        starts = [0] + [j for j in range(1, len(ordered)) if ordered[j][0] - ordered[j-1][0] > MAX_GAP]
        for start, end in zip(starts, starts[1:] + [len(ordered)], strict=True):
            segment = ordered[start:end]
            segments += 1
            for tag, times in (("all", [t for t, _, _ in segment]),
                               ("corroborated", [t for t, matched, _ in segment if matched]),
                               ("anchors", [t for t, _, anchor in segment if anchor])):
                for j, value in enumerate(design(times)):
                    totals[tag][j] += value
    loss = {}
    for tag in ("corroborated", "anchors"):
        loss[tag] = {}
        for name, selected, total in zip(MEASURES, totals[tag], totals["all"], strict=True):
            if selected > total * (1 + 1e-9):
                raise ValueError("A subset exceeds the full fitted time design")
            loss[tag][name] = max(0., 1. - selected/total) if total else None
    return dict(segments=segments, totals=totals, loss=loss)


def features(snapshot, cohort, seal_pin):
    entries, rows, _, seal, pins = snapshot_inputs(snapshot, cohort)
    if pins["seal"] != seal_pin or (cohort == "first24" and (seal_pin != FIRST_SEAL or pins["combined_export"] != FIRST)):
        raise ValueError("Time support analysis needs the enrolled, sealed export")
    overlay = verified_overlay(CAMPAIGN, seal) if cohort == "first24" else None
    cases = {}
    for entry in entries:
        case = entry["case"]
        enrolled = rows[case]
        group = case_group(CAMPAIGN, entry, enrolled, overlay)
        if group is None:
            raise ValueError(f"Await all enrolled pairs, including {case}")
        case_data = cases[case] = dict(pair=group[2], outcomes={k: enrolled[k]["outcome"] for k in BUILDS})
        if any(value != "complete" for value in case_data["outcomes"].values()):
            continue
        stock, candidate = [verified_attempt(CAMPAIGN, group, enrolled[role]) for role in BUILDS]
        result, pub = candidate
        raw = signed.document(pub/"unified-short-bootstrap.json")
        right, witness, _ = signed.qualified_candidate(pub, raw, result["native_sha256"], OFFER)
        left = signed.read_native(stock[1], stock[0]["native_sha256"])
        if (stock[0]["raw_identity"] != result["raw_identity"] or left["provenance"]["detector_sha256"] != "sha256:"+signed.FULL
                or left["source"]["raw_recording_authority_digest"] != enrolled["installed"]["raw_authority_sha256"]
                or witness["evidence"]["detail"]["terminal_sha256"] != enrolled["successor"]["terminal_sha256"]):
            raise ValueError("Saved factors or owners belong to a different paired run")
        a, b = map(signed.opportunities, (left, right))
        signed.bind_pair(left, right, a, b)
        owners = signed.owners(witness["evidence"]["owner_rows"], result["evidence"]["owners"])
        case_data.update(native={role: r["native_sha256"] for role, (r, _) in zip(BUILDS, (stock,candidate), strict=True)},
                         owners=result["evidence"]["owners"], arms={})
        for arm, members in owners.items():
            groups = defaultdict(list)
            for oid, (satellite, _) in members.items():
                obs = b[oid]
                if obs["factor"] is None:
                    raise ValueError("Candidate owner lacks a native winner")
                matched = classify(a[oid]["factor"], obs["factor"])[0] == "same_carrier"
                key = (satellite, obs["radio"], *(obs["row"][k] for k in ("actual_rf_hz","edge","channel")))
                groups[key].append((obs["counter"], matched, not obs["short"]))
            case_data["arms"][arm] = support(groups)
    return dict(seal=seal_pin, ledger=pins["combined_export"], cohort=cohort, cases=cases)


def score(snapshot, packet):
    cases = packet["cases"]
    rows = [r for line in checked(snapshot/"rows-with-relocations.jsonl", packet["ledger"]).splitlines()
            if (r := json.loads(line))["case"] in cases]
    references = roster()
    pairs = paired_rows(rows, {case: references[case] for case in cases})
    summary = {}
    for arm in ARMS:
        delta = {}
        for a, b in pairs:
            metric = arm+"_error_km"
            if a[metric] is not None and b[metric] is not None:
                delta[a["case"]] = b[metric] - a[metric]
        primary = [case for case in delta if case != "DS30-0049"]
        ranks = {}
        for tag in ("corroborated", "anchors"):
            ranks[tag] = {}
            for measure in MEASURES:
                values = [(cases[c]["arms"][arm]["loss"][tag][measure], delta[c]) for c in primary]
                usable = [(x,y) for x,y in values if x is not None]
                ranks[tag][measure] = dict(n=len(usable), tau=tau_b(usable))
        summary[arm] = dict(delta_km=delta, rank=ranks)
    return dict(feature_ledger=packet["ledger"], results=summary)


def read_features(path, pin):
    body = path.read_bytes()
    if path.suffix == ".gz":
        body = decompress(body)
    if digest(body) != "sha256:" + pin.removeprefix("sha256:"):
        raise ValueError("Saved time-support features differ from their sealed JSON")
    return body


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--cohort", choices=("first24","next3"), default="first24")
    parser.add_argument("--seal-pin", default=FIRST_SEAL)
    parser.add_argument("--score-features", type=Path)
    parser.add_argument("--feature-pin")
    args = parser.parse_args()
    if args.score_features is None:
        result = features(args.snapshot, args.cohort, args.seal_pin)
    else:
        if not args.feature_pin:
            parser.error("Supply the SHA-256 of the sealed features")
        body = read_features(args.score_features, args.feature_pin)
        result = score(args.snapshot, json.loads(body)) | dict(features=digest(body))
    print(json.dumps(result, sort_keys=True, allow_nan=False, separators=(",",":")))
