"""Replay an adaptive stereo schedule from frozen factors without opening raw I/Q."""

import argparse
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path
from time import process_time

from residual_schedule_trial import read

from leo.contracts.digests import canonical_digest
from leo.contracts.fast_standard_analysis import PLOTS
from tools.pipeline_eval.variants.carrier_continuation import Continuation
from tools.pipeline_eval.variants.experimental.adaptive_stereo_visits import (
    AdaptiveStereo,
    optimistic_skip_limit,
)
from tools.pipeline_eval.variants.selective_capture import visit_pairs


def replay(ledger, native):
    released = Continuation()
    policy = AdaptiveStereo()
    published = native["source"]["probes"]
    observed, proposed, skipped = [], [], []
    counts = Counter()
    changes = []
    visits = []
    start = process_time()
    for index, (visit, pair) in enumerate(visit_pairs(ledger["rows"])):
        base = index * 2
        cpu = ledger["native_cpu_ns"][base:base + 2]
        metadata = tuple({k: v for k, v in row.items() if k != "candidates"} for row in pair)
        measured = False

        def factors(pair=pair):
            nonlocal measured
            if measured:
                raise ValueError("Stereo visit measured twice")
            measured = True
            return tuple(tuple(row["candidates"]) for row in pair)

        omitted, actual, selected, votes = policy.visit(metadata, factors)
        if measured == omitted:
            raise ValueError("Schedule and callback receipt disagree")
        visits.append(dict(visit=visit, skipped=omitted, votes=votes))
        if omitted:
            skipped.append(dict(visit=visit, native_cpu_ns=cpu, ledger=pair))
        for lane, (row, current) in enumerate(zip(pair, selected, strict=True)):
            preferred, chosen, vote_counts = released.select(row)
            original = dict(row, candidates=[] if chosen is None else [row["candidates"][chosen]])
            if original != published[base + lane]:
                raise ValueError("The full causal replay changed the saved publication")
            full_votes = dict(preferred=preferred, selected=chosen, votes=vote_counts)
            observed.append(dict(metadata[lane], candidates=list(actual[lane])))
            proposed.append(current)
            counts["verified_factors"] += len(row["candidates"])
            counts["measured_factors"] += len(actual[lane])
            counts["selected_full"] += bool(original["candidates"])
            counts["selected_candidate"] += bool(current["candidates"])
            scope = "omitted" if omitted else "retained"
            if full_votes != votes[lane]:
                counts[f"{scope}_vote_changes"] += 1
            if original["candidates"] != current["candidates"]:
                a, b = original["candidates"], current["candidates"]
                change = "changed" if a and b else "lost" if a else "gained"
                counts[f"{scope}_{change}_selections"] += 1
                changes.append(dict(visit=visit, receiver_id=lane, scope=scope, change=change,
                                    full=a, candidate=b, full_votes=full_votes, votes=votes[lane]))
    replay_cpu = process_time() - start
    admitted = len(visits)
    if (admitted * 2 != len(published)
            or admitted + len(ledger["excluded_windows"]) != ledger["window_count"]
            or len(skipped) != policy.reasons["skip"]):
        raise ValueError("Observed, missing or skipped visits do not reconcile")
    bound = optimistic_skip_limit(pair for _, pair in visit_pairs(ledger["rows"]))
    if len(skipped) > bound["maximum_nonconsecutive_skips"]:
        raise ValueError("Actual skips exceed the optimistic timestamp ceiling")
    full_cpu = sum(ledger["native_cpu_ns"]) / 1e9
    saved_cpu = sum(sum(row["native_cpu_ns"]) for row in skipped) / 1e9
    return proposed, dict(scheduled_visits=ledger["window_count"], admitted_visits=admitted,
                          measured_visits=admitted-len(skipped), skipped_visits=len(skipped),
                          reasons=policy.reasons, counts=counts, changes=changes,
                          native_cpu_s=full_cpu, maximum_saved_native_cpu_s=saved_cpu,
                          offline_replay_cpu_s=replay_cpu, skipped=skipped, visits=visits,
                          optimistic_timestamps=bound,
                          ordered_measured_sha256=canonical_digest(observed),
                          full_selected_sha256=canonical_digest(published),
                          candidate_selected_sha256=canonical_digest(proposed))


def scientific_receipt(native, proposed, pair_path):
    result = json.loads(pair_path.read_bytes())["runs"]["candidate"]
    if (native["source"]["raw_recording_authority_digest"] != result["raw_authority"] or
            native["source"]["session_id"] != result["receipt"]["session_id"] or
            native["provenance"]["processed_windows"] != result["receipt"]["counts"]["processed"]):
        raise ValueError("Science receipt and factor ledger do not bind the same acquisition")
    if proposed == native["source"]["probes"]:
        artifacts = result["artifacts"]
        if tuple(item["name"] for item in artifacts) != PLOTS:
            raise ValueError("The prior scientific receipt is missing a required figure")
        return dict(status="same_saved_probes", arms=result["arms"], owners=result["owners"],
                    numerical_artifacts=result["scientific_digests"], plots=artifacts,
                    region=result["receipt"]["region"])
    return {"status": "changed_probes"}


def dense_bounds(receipt_path, detection_path):
    raw = detection_path.read_bytes()
    native = json.loads(raw)
    source = native["source"]
    receipt = json.loads(receipt_path.read_bytes())["runs"]["candidate"]
    counts = receipt["receipt"]["counts"]
    diagnostics = receipt["receipt"]["deferred_continuation"]
    calls = diagnostics["native_calls"]
    pairs = [pair for _, pair in visit_pairs(source["probes"])]
    if (source["raw_recording_authority_digest"] != receipt["raw_authority"]
            or counts["processed"] != len(pairs) or
            native["provenance"]["window_count"] != len(pairs) + counts["invalid_capture"]):
        raise ValueError("Dense detection and measured callback population disagree")
    bounds = optimistic_skip_limit(pairs)
    native_cpu = diagnostics["query_cpu_ns"] / 1e9
    mean_projection = min(2 * bounds["maximum_nonconsecutive_skips"], calls) * native_cpu / calls
    return dict(admitted_visits=len(pairs), paid_calls=calls, paid_callback_cpu_s=native_cpu,
                detection_sha256=sha256(raw).hexdigest(),
                mean_callback_cpu_projection_s=mean_projection,
                measured_full_candidate_cpu_s=receipt["cpu_s"], **bounds)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", nargs=4, required=True,
                        metavar=("NAME", "LEDGER", "DETECTIONS", "PAIR"))
    parser.add_argument("--dense", nargs=2, required=True, metavar=("RECEIPT", "DETECTIONS"))
    args = parser.parse_args()
    if len(args.case) > 2:
        parser.error("At most two matched cases")
    output = dict(dense=dense_bounds(*map(Path, args.dense)), cases={})
    for name, ledger_path, detection, pair in args.case:
        ledger_sha256, ledger, native = read(Path(ledger_path), Path(detection))
        proposed, receipt = replay(ledger, native)
        receipt.update(ledger_sha256=ledger_sha256,
                       detection_sha256=ledger["saved_detections_sha256"])
        receipt["solver"] = scientific_receipt(native, proposed, Path(pair))
        output["cases"][name] = receipt
    print(json.dumps(output, allow_nan=False))


if __name__ == "__main__":
    main()
