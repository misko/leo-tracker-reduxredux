"""Replay the history-only bound against saved factors and native-call clocks."""

import argparse
import gzip
import inspect
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path
from statistics import median
from textwrap import dedent
from time import process_time_ns

from tools.pipeline_eval.variants.carrier_continuation import Continuation, votes
from tools.pipeline_eval.variants.experimental.continuation_history_bound import (
    history_allows_three,
)
from tools.pipeline_eval.variants.experimental.deferred_continuation import (
    DeferredContinuation,
    Visit,
    possible_line,
)


def planner_with_bound(bound=history_allows_three):
    # Alter only the early-deferral condition in this offline trial. FIFO,
    # released votes and the post-measurement path remain the reference.
    source = dedent(inspect.getsource(DeferredContinuation.select))
    anchor = "    if len(possible) < 3 or now - possible[0].counter < 4_000_000:"
    if source.count(anchor) != 1:
        raise ValueError("Expected the frozen deferred planner's early gate")
    updated = source.replace(
        anchor,
        "    structural = len(possible) >= 3 and now - possible[0].counter >= 4_000_000\n"
        "    eligible = structural and history_allows_three(possible, now)\n"
        "    if structural and not eligible:\n"
        "        self.counts['ruled_out_before_native'] += 1\n"
        "    if not eligible:",
    )
    methods = dict(Continuation=Continuation, Visit=Visit, possible_line=possible_line,
                   votes=votes, history_allows_three=bound)
    exec(compile(updated, "<history bound trial>", "exec"), methods)

    class HistoryBoundContinuation(DeferredContinuation):
        select = methods["select"]

    return HistoryBoundContinuation


def compare(ledger_path, detections_path, capacity, repeats):
    ledger_bytes = ledger_path.read_bytes()
    ledger = json.loads(gzip.decompress(ledger_bytes))
    reference = json.loads(detections_path.read_bytes())["source"]
    if ledger["raw_authority"] != reference["raw_recording_authority_digest"]:
        raise ValueError("Ledger and detector publication refer to different samples")
    rows, clocks = ledger["rows"], ledger["native_cpu_ns"]
    if not len(rows) == len(clocks) == len(reference["probes"]):
        raise ValueError("Incomplete factor ledger")
    metadata = [{k: v for k, v in row.items() if k != "candidates"} for row in rows]
    stock = Continuation()
    expected = []
    for row, original in zip(rows, reference["probes"], strict=True):
        _, pick, _ = stock.select(row)
        factors = [row["candidates"][pick]] if pick is not None else []
        if dict(row, candidates=factors) != original:
            raise ValueError("Released continuation disagrees with its publication")
        expected.append(factors)

    def replay(planner_type):
        planner = planner_type(capacity)
        selected, queries = [], set()

        def measure(index):
            if index in queries:
                raise ValueError("Native measurement charged twice")
            queries.add(index)
            return rows[index]["candidates"]

        start = process_time_ns()
        for index, probe in enumerate(metadata):
            selected.append(planner.select(probe, lambda i=index: measure(i)))
        planner_ns = process_time_ns() - start
        if selected != expected:
            raise ValueError("History bound changed at least one selected factor")
        return planner_ns, queries, planner.counts

    timings, queries, counts = [[], []], [None, None], [None, None]
    arms = DeferredContinuation, planner_with_bound()
    for repeat in range(repeats):
        for arm in (repeat % 2, 1 - repeat % 2):
            elapsed, requested, stats = replay(arms[arm])
            if queries[arm] is not None and (requested != queries[arm] or stats != counts[arm]):
                raise ValueError("Planner query set changed across repeats")
            timings[arm].append(elapsed)
            queries[arm], counts[arm] = requested, stats
    avoided, added = queries[0] - queries[1], queries[1] - queries[0]
    checks = Counter()
    blocked = Counter()

    def trace(possible, now):
        unknown = min(3, sum(visit.frequencies is None for visit in possible))
        result = history_allows_three(possible, now)
        checks[unknown] += 1
        blocked[unknown] += not result
        return result

    _, traced, _ = replay(planner_with_bound(trace))
    if traced != queries[1]:
        raise ValueError("History trace changed the requested lanes")
    clock_seconds = [sum(clocks[index] for index in arm) / 1e9 for arm in queries]
    paired_overhead = [(new - base) / 1e9 for base, new in zip(*timings, strict=True)]
    return dict(
        ledger_sha256=sha256(ledger_bytes).hexdigest(), detector_sha256=ledger["detector_sha256"],
        raw_authority=ledger["raw_authority"], pending_budget=capacity, rows=len(rows),
        selections=sum(bool(factors) for factors in expected), total_native_cpu_s=sum(clocks) / 1e9,
        queried_lanes=[len(arm) for arm in queries], queried_native_cpu_s=clock_seconds,
        avoided_lanes=len(avoided), added_lanes=len(added),
        avoided_native_cpu_s=sum(clocks[index] for index in avoided) / 1e9,
        added_native_cpu_s=sum(clocks[index] for index in added) / 1e9,
        planner_cpu_s=[[elapsed / 1e9 for elapsed in pair] for pair in zip(*timings, strict=True)],
        median_additional_planner_cpu_s=median(paired_overhead),
        estimated_net_cpu_s=clock_seconds[0] - clock_seconds[1] - median(paired_overhead),
        history_bound_checks=dict(checks), history_bound_blocks=dict(blocked),
        counters=counts,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", nargs=3, action="append", required=True,
                        metavar=("NAME", "LEDGER", "DETECTIONS"))
    parser.add_argument("--pending", nargs="+", type=int, default=[16, 64, 192])
    parser.add_argument("--repeats", type=int, default=7)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("Expected positive repeats")
    cases = {
        name: {
            capacity: compare(Path(ledger), Path(detections), capacity, args.repeats)
            for capacity in args.pending
        }
        for name, ledger, detections in args.case
    }
    print(json.dumps(cases, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
