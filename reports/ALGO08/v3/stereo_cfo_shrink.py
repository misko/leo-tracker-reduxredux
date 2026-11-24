"""Shrink simultaneous short-lane CFO discrepancies with a past-only radio offset."""

import argparse
from collections import Counter, defaultdict, deque
import json
from math import fsum, isfinite
from pathlib import Path
import sys

from .anchor_cfo_innovation import paired_measurements, summarize
from .capped_revisit import HERTZ, STREAM, candidate_packet, saved_only, signed
from .calibration_transport import FIELD, FIRST30, signed_attempt
from .ds30_paired_inputs import checked
from .track_cfo_denoise import COHORTS, original_pairs
from short_stereo_evidence import MAX_TIMING_SAMPLES, WINDOWS, timing_delta, witness_offset
from signed_cfo_time import epoch


def predict(opportunities):
    streams = defaultdict(lambda: deque(maxlen=WINDOWS))
    changes, counts = {}, Counter()
    lanes = iter(opportunities.values())
    for left, right in zip(lanes, lanes, strict=True):
        rows = left["row"], right["row"]
        key = tuple(rows[0][k] for k in STREAM[:3])
        now = left["counter"]
        if ((left["radio"], right["radio"]) != (0, 1) or left["short"] != right["short"]
                or right["counter"] != now or key != tuple(rows[1][k] for k in STREAM[:3])
                or rows[0]["visit_index"] != rows[1]["visit_index"]):
            raise ValueError("Stereo operands require the same signed visit and tuning")
        past = streams[key]
        if past and past[-1][0] >= now:
            raise ValueError("Expected strictly advancing per-stream hardware time")
        first, second = left["factor"], right["factor"]
        witness = None
        if first is not None and second is not None:
            delay = timing_delta(*rows, first, second)
            difference = second[HERTZ] - first[HERTZ]
            if not all(map(isfinite, (delay, difference))):
                raise ValueError("Nonfinite signed timing or CFO")
            if abs(delay) <= MAX_TIMING_SAMPLES:
                witness = difference
                if left["short"]:
                    counts["short_stereo_epoch_matches"] += 1
                    prior = witness_offset(past, now)
                    residual = difference - (0. if prior is None else prior)
                    if 0 < abs(residual) <= 250:
                        shift = residual / 4
                        changes[left["id"]] = (shift, right["id"])
                        changes[right["id"]] = (-shift, left["id"])
                        counts["direct_visits" if prior is None else "history_visits"] += 1
        past.append((now, witness))
    return changes, dict(counts)


def pair_modes(original, candidate, changes):
    modes = defaultdict(list)
    for oid, (delta, peer) in changes.items():
        if candidate[oid]["radio"] != 0:
            continue
        if tuple(changes[peer]) != (-delta, oid):
            raise ValueError("Every proposed stereo update must preserve the pair mean")
        factors = [(original[k]["factor"], candidate[k]["factor"]) for k in (oid, peer)]
        if any(a is None or abs(epoch(a) - epoch(b)) > 2 for a, b in factors):
            continue
        a, b = (n[HERTZ] - o[HERTZ] for o, n in factors)
        mean, diff = (a+b)/2, (a-b)/2
        values = mean**2, diff**2, (diff+delta)**2
        modes["epoch_close"].append(values)
        if max(abs(a), abs(b)) <= 250:
            modes["strict"].append(values)
    return modes


def energy(values):
    common, before, after = (fsum(row[i] for row in values) for i in range(3))
    return dict(visits=len(values), common_sq_hz2=common, diff_before_sq_hz2=before, diff_after_sq_hz2=after,
                max_removable_fraction=before/(before+common) if before+common else None)


def run(snapshot, plan=None):
    cases, pooled, paired = {}, defaultdict(list), defaultdict(list)
    for cohort, ids in COHORTS.items():
        rows = original_pairs(snapshot, cohort)
        for case in ids:
            result, native, candidate, _ = candidate_packet(rows[case, "successor"])
            corrections, counts = predict(candidate)
            identity = dict(native=result["native_sha256"], changes=corrections, counts=counts)
            if plan is None:
                cases[case] = identity
                continue
            if json.loads(json.dumps(identity)) != plan["cases"][case] or plan["ledger"] != FIRST30:
                raise ValueError("Candidate predictions or enrolled ledger changed after sealing")
            old = rows[case, "installed"]
            result_old = signed_attempt(FIELD, old)
            stock = signed.read_native((FIELD / old["attempt"]).parent / "publication", result_old["native_sha256"])
            if result_old["raw_identity"] != result["raw_identity"] or stock["provenance"]["detector_sha256"] != "sha256:"+signed.FULL:
                raise ValueError("Expected the independently verified installed packet on the same original")
            original = signed.opportunities(stock)
            signed.bind_pair(stock, native, original, candidate)
            obs, coverage = paired_measurements(original, candidate, corrections)
            modes = pair_modes(original, candidate, corrections)
            cases[case] = dict(candidate=result["native_sha256"], installed=result_old["native_sha256"],
                               counts=counts, coverage=coverage, disagreement=summarize(obs),
                               paired_energy={k: energy(v) for k, v in modes.items()})
            if cohort == "held":
                for key, values in obs.items():
                    pooled[key].extend(values)
                for key, values in modes.items():
                    paired[key].extend(values)
    report = dict(ledger=FIRST30, cases=cases)
    if plan is not None:
        report.update(held=summarize(pooled), held_energy={k: energy(v) for k, v in paired.items()})
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--score-plan", type=Path)
    parser.add_argument("--sha256")
    args = parser.parse_args()
    if bool(args.score_plan) != bool(args.sha256):
        parser.error("Scoring needs the sealed prediction and its SHA-256")
    sys.addaudithook(lambda event, params: saved_only(event, params, prediction=args.score_plan is None))
    plan = json.loads(checked(args.score_plan, args.sha256)) if args.score_plan else None
    report = run(args.snapshot, plan)
    if plan is not None:
        report["prediction_sha256"] = args.sha256
    print(json.dumps(report, sort_keys=True, allow_nan=False, separators=(",", ":")))
