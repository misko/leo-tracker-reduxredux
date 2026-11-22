"""Replay primary-only rescue from the sealed pre-continuation factor ledger."""

import argparse
import json
from pathlib import Path
from statistics import median
from time import process_time_ns

from residual_schedule_trial import changes, read

from leo.contracts.digests import canonical_digest
from tools.pipeline_eval.variants.experimental.residual_rescue import (
    PENDING_LANES,
    STEREO_WINDOW_BYTES,
    PrimaryRescue,
    primary_only,
)
from tools.pipeline_eval.variants.experimental.residual_schedule import Replay


def replay(rows, mode):
    policy = PrimaryRescue() if mode == "rescue" else Replay(mode)
    foreground, backfilled, selected = [], [], []
    available = [{k: v for k, v in row.items() if k != "candidates"} for row in rows]
    start = process_time_ns()
    trigger = [None]
    for index, metadata in enumerate(available):
        trigger[0] = index

        def measure(use_residual, index=index):
            factors = rows[index]["candidates"]
            current = trigger[0]
            if index == current:
                foreground.append((index, use_residual))
            else:
                if index >= current or not use_residual:
                    raise ValueError("A backfill requires a strictly earlier full call")
                backfilled.append((current, index))
            return factors if use_residual else primary_only(factors)

        _, _, chosen = policy.visit(metadata, measure)
        selected.append(dict(metadata, candidates=chosen))
    cpu_ns = process_time_ns() - start
    if [index for index, _ in foreground] != list(range(len(rows))):
        raise ValueError("Expected one ordered foreground query per admitted lane")
    original_skips = {index for index, full in foreground if not full}
    historical = [index for _, index in backfilled]
    if len(set(historical)) != len(historical) or set(historical) - original_skips:
        raise ValueError("Backfill must resolve each skipped historical lane at most once")
    reasons = policy.foreground.reasons if mode == "rescue" else policy.reasons
    counts = policy.counts if mode == "rescue" else {}
    return dict(cpu_ns=cpu_ns, selected=selected, foreground=foreground, backfilled=backfilled,
                reasons=dict(reasons), counts=dict(counts))


def timed(rows, modes, repeats=5):
    order = list(modes)
    arms = {}
    for repeat in range(repeats):
        sequence = order[::-1] if repeat % 2 else order
        for mode in sequence:
            current = replay(rows, mode)
            elapsed = current.pop("cpu_ns")
            if mode in arms:
                control = {k: v for k, v in arms[mode].items() if k != "cpu_ns"}
                if control != current:
                    raise ValueError("Causal replay changed under a different arm order")
            else:
                arms[mode] = dict(current, cpu_ns=[])
            arms[mode]["cpu_ns"].append(elapsed)
    return arms


def summary(ledger_path, detection_path, native_prefix_path):
    ledger_sha, ledger, native = read(ledger_path, detection_path)
    rows, ns = ledger["rows"], ledger["native_cpu_ns"]
    arms = timed(rows, ("always-two", "conditional", "rescue"))
    deployed, conditional, rescue = (arms[mode] for mode in ("always-two", "conditional", "rescue"))
    if deployed["selected"] != native["source"]["probes"]:
        raise ValueError("Two-scan replay differs from the original ordered publication")
    if conditional["foreground"] != rescue["foreground"]:
        raise ValueError("Historical rescue altered the frozen foreground schedule")
    recovered = [0, 0]
    missed = [0, 0]
    new_errors = [0, 0]
    for correct, old, new in zip(deployed["selected"], conditional["selected"], rescue["selected"],
                                 strict=True):
        selection = correct["candidates"]
        if selection:
            rank = selection[0]["candidate_rank"]
            recovered[rank] += new == correct and old != correct
            new_errors[rank] += new != correct and old == correct
            missed[rank] += new != correct

    measured = [idx for _, idx in rescue["backfilled"]]
    raw_skips = [idx for idx, full in rescue["foreground"] if not full]
    backfill_ns = sum(ns[i] for i in measured)
    full_skip_ns = sum(ns[i] for i in raw_skips)
    extra_vs_conditional = paired_cpu(conditional, rescue)
    extra_vs_deployed = paired_cpu(deployed, rescue)
    before_after, changed_vs_deployed = changes(deployed["selected"], rescue["selected"])
    vs_conditional, changed_vs_conditional = changes(conditional["selected"], rescue["selected"])
    memory = rescue["counts"]["peak_stereo_windows"]
    reads = len({rows[i]["visit_index"] for i in measured})
    operational = {
        mode: dict(
            selected_count=sum(bool(row["candidates"]) for row in result["selected"]),
            selected_sha256=canonical_digest(result["selected"]),
            foreground_full=sum(full for _, full in result["foreground"]),
            foreground_primary_only=sum(not full for _, full in result["foreground"]),
            historical_full=len(result["backfilled"]), planner_cpu_ns=result["cpu_ns"],
            schedule_reasons=result["reasons"], policy_counts=result["counts"],
        )
        for mode, result in arms.items()
    }
    return dict(
        ledger_sha256=ledger_sha, raw_authority=ledger["raw_authority"],
        native_detector_sha256=ledger["detector_sha256"], lanes=len(rows),
        pending_budget=PENDING_LANES, arms=operational,
        rescued_deployed_rank_0=recovered[0], rescued_deployed_rank_1=recovered[1],
        missed_deployed_rank_0=missed[0], missed_deployed_rank_1=missed[1],
        newly_changed_deployed_rank_0=new_errors[0], newly_changed_deployed_rank_1=new_errors[1],
        differences_vs_deployed=dict(counts=before_after, rows=changed_vs_deployed),
        differences_vs_conditional=dict(counts=vs_conditional, rows=changed_vs_conditional),
        peak_retained_stereo_bytes=memory * STEREO_WINDOW_BYTES,
        historical_stereo_windows=reads,
        minimum_decoded_revisit_bytes_without_retention=reads * STEREO_WINDOW_BYTES,
        native_full_clock_ns=sum(ns), skipped_full_clock_ceiling_ns=full_skip_ns,
        backfill_native_clock_ns=backfill_ns,
        additional_planner_ns_vs_conditional=extra_vs_conditional,
        additional_planner_ns_vs_deployed=extra_vs_deployed,
        total_incremental_cost_ns_vs_conditional=backfill_ns + extra_vs_conditional,
        optimistic_saving_ceiling_ns_vs_deployed=full_skip_ns - backfill_ns - extra_vs_deployed,
        measured_prefix_estimate=prefix(
            native_prefix_path, ledger_sha, ledger["detector_sha256"], rows, ns, rescue,
        ),
    )


def paired_cpu(before, after):
    return median(b - a for a, b in zip(before["cpu_ns"], after["cpu_ns"], strict=True))


def prefix(path, ledger_sha, detector, rows, native_ns, all_rescue):
    measured = json.loads(path.read_bytes())
    if (measured["ledger_sha256"] != ledger_sha
            or measured["frozen_detector_sha256"] != detector):
        raise ValueError("Measured prefix uses different ledger or receiver")
    limit = measured["requested_visits"]
    prefix_rows = [row for row in rows if row["visit_index"] < limit]
    if prefix_rows != rows[:len(prefix_rows)]:
        raise ValueError("Measured visits are not a chronological prefix")
    arms = timed(prefix_rows, ("always-two", "conditional", "rescue"))
    deployed, conditional, rescue = (arms[mode] for mode in ("always-two", "conditional", "rescue"))
    original_prefix = [(a, b) for a, b in all_rescue["backfilled"] if a < len(prefix_rows)]
    if rescue["backfilled"] != original_prefix:
        raise ValueError("Extending the recording changed the cold prefix queries")
    if rescue["selected"] != all_rescue["selected"][:len(prefix_rows)]:
        raise ValueError("Extending the recording changed the cold prefix selections")
    actual = measured["repeats"]
    selected_shas = {mode: canonical_digest(arms[mode]["selected"])
                     for mode in ("always-two", "conditional")}
    if any(conditional["reasons"]["skip"] != repeat["lane_counts"]["residual_skipped"]
           or len(prefix_rows) != sum(repeat["lane_counts"].values())
           or selected_shas != repeat["selections_sha256"] for repeat in actual):
        raise ValueError("Recorded native prefix had a different foreground schedule")
    gross = [sum(row["native_cpu_s"]["always-two"].values())
             - sum(row["native_cpu_s"]["conditional"].values()) for row in actual]
    added = sum(native_ns[i] for _, i in rescue["backfilled"]) / 1e9
    extra_planner = paired_cpu(deployed, rescue) / 1e9
    return dict(
        scheduled_visits=limit, admitted_lanes=len(prefix_rows),
        measured_conditional_native_savings_s=gross, charged_extra_full_cpu_s=added,
        additional_planner_cpu_s_vs_deployed=extra_planner,
        net_saving_estimate_s=[s - added - extra_planner for s in gross],
        resolved_historical_lanes=len(rescue["backfilled"]),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", nargs=4, action="append", required=True,
                        metavar=("NAME", "LEDGER", "DETECTIONS", "PREFIX_TIMING"))
    args = parser.parse_args()
    cases = {name: summary(Path(ledger), Path(detections), Path(timing))
             for name, ledger, detections, timing in args.case}
    print(json.dumps(cases, indent=2, allow_nan=False))
