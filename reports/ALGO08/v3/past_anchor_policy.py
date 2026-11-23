"""Evaluate the frozen past-only full-anchor rule without opening a solver."""

import argparse
from collections import Counter, defaultdict
from fractions import Fraction
from hashlib import sha256
import json
from math import ceil
from pathlib import Path
from time import perf_counter_ns, process_time_ns

from .anchor_exposure import PINS, bind, enroll, packet, positive


WIDTH = 128
SAMPLE_RATE = 10_000_000
HELD = {
    "12ms": ("/dev/shm/leo-past-anchor-held-south", "a10693d167757124a036cfcd63e90966760e52b755f4bb834605ccaf74426d2e"),
    "stock": ("/tmp/leo-algo08v2-2x-bench/exact-curved-lookahead-south-inside/baseline",
              "9ead12e735906a95066b77dfcaca54e9bdf68dc0a2c816a95fa3bca3419a3d49"),
}


class ObservedBlock:
    def __init__(self):
        self.exposure = Counter()
        self.passed = Counter()
        self.margins = defaultdict(list)

    def observe(self, mode, stream, margin):
        self.exposure[mode] += 1
        if margin is not None:
            self.passed[mode] += 1
            if mode == "short":
                self.margins[stream].append(margin)

    def rate(self, mode):
        return Fraction(self.passed[mode], self.exposure[mode])


def threshold(previous):
    if any(block is None or not all(block.exposure[mode] for mode in ("anchor", "short")) for block in previous):
        return False, None, {}
    a = max(block.rate("anchor") for block in previous)
    s = min(block.rate("short") for block in previous)
    if not 0 < a < s:
        return True, None, {}
    keep = a/s
    cutoff = {}
    first, second = (block.margins for block in previous)
    for stream in first.keys() | second.keys():
        values = first.get(stream, []) + second.get(stream, [])
        rank = ceil(len(values) * keep)
        if rank < len(values):
            cutoff[stream] = sorted(values, reverse=True)[rank-1]
    return True, keep, cutoff


def factor_margin(row):
    selected = [factor for factor in row["candidates"] if factor["passed_fractional_margin_gate"]]
    if len(selected) > 1:
        raise ValueError("The unfiltered mixed receiver must publish a single verified candidate per opportunity")
    return selected[0]["fractional_margin"] if selected else None


def apply(doc, reference):
    if reference is not None:
        bind(reference, doc)
    rows = doc["source"]["probes"]
    stock = reference["source"]["probes"] if reference else [None] * len(rows)
    session = doc["source"]["session_id"]
    initial_counter = rows[0]["valid_start_counter"]
    if doc["source"]["sample_rate_hz"] != SAMPLE_RATE:
        raise ValueError("Expected original 10 MS/s hardware timestamps")
    history, by_radio, first, decisions = {}, {}, {}, []
    active_block, fitted = -1, None
    work_start = process_time_ns(), perf_counter_ns()
    for opportunity, row, other in zip(enroll(doc), rows, stock, strict=True):
        visit, _, radio, stream, mode, _ = opportunity
        block = visit // WIDTH
        if block != active_block:
            fitted = {
                receiver: threshold([history.get((b, receiver)) for b in (block-2, block-1)])
                for receiver in (0, 1)
            }
            history = {key: value for key, value in history.items() if key[0] >= block-2}
            active_block = block
        margin = factor_margin(row)
        eligibility, keep, cutoffs = fitted[radio]
        cutoff = cutoffs.get(stream) if mode == "short" else None
        removed = cutoff is not None and margin is not None and margin < cutoff
        arrived = row["valid_start_counter"]
        event = dict(visit=visit, receiver_id=radio, valid_start_counter=arrived,
                     seconds_from_first_opportunity=(arrived-initial_counter)/SAMPLE_RATE)
        totals = by_radio.setdefault(radio, Counter())
        totals.update({f"{mode}_opportunities": 1})
        if mode == "short" and eligibility:
            first.setdefault("eligible", event)
            totals["eligible_short_opportunities"] += 1
        if mode == "short" and keep is not None:
            first.setdefault("active", event)
            totals["active_short_opportunities"] += 1
        if removed:
            first.setdefault("removed", event)
            totals["removed"] += 1
        if margin is not None:
            totals[f"{mode}_positive"] += 1
            totals["kept"] += int(not removed)
            has_reference = positive(other) if other is not None else None
            if has_reference:
                totals["stock_present_candidate_positive"] += 1
                totals["stock_present_removed"] += int(removed)
            oid = "sha256:" + sha256(f"{session}:{radio}:{arrived}".encode()).hexdigest()
            decisions.append(dict(event, observed_id=oid, mode=mode, kept=not removed, margin=margin,
                                  cutoff=cutoff, stock_present=has_reference))
        if other is not None and positive(other):
            totals["stock_present"] += 1
        key = (block, radio)
        if key not in history:
            history[key] = ObservedBlock()
        history[key].observe(mode, stream, margin)
    clocks = dict(cpu_ns=process_time_ns()-work_start[0], elapsed_ns=perf_counter_ns()-work_start[1])
    total = Counter()
    for radio in by_radio.values():
        total.update(radio)
    if total["kept"] + total["removed"] != len(decisions) or len({row["observed_id"] for row in decisions}) != len(decisions):
        raise ValueError("The signed factor decision list changed membership")
    return dict(first=first, all_streams=dict(total), by_radio={str(k): dict(v) for k, v in by_radio.items()},
                clocks=clocks, decisions=decisions)


def passed(cases):
    north = cases["north"]["12ms"]["all_streams"].get("removed", 0) > 0
    physical = {site: all(100*row.get("removed", 0) <= row["short_positive"] + row["anchor_positive"]
                          for row in cases[site]["12ms"]["by_radio"].values())
                for site in ("DS30-0016", "DS30-0008")}
    south = all(100*row.get("stock_present_removed", 0) <= row["stock_present"]
                for row in cases["south"]["12ms"]["by_radio"].values())
    return dict(north_active=north, physical_retained=physical, south_reference_retained=south,
                solver_authorized=north and all(physical.values()) and south)


def run():
    inputs = dict(PINS, south=HELD)
    cases = {}
    for site, arms in inputs.items():
        reference = packet(*arms["stock"]) if "stock" in arms else None
        cases[site] = {name: apply(packet(*pin), reference) for name, pin in arms.items() if name != "stock"}
    return dict(cases=cases, gate=passed(cases), pins=inputs, block_issued_visits=WIDTH,
                source_sha256=sha256(Path(__file__).read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    outcome = run()
    with args.receipt.open("x") as stream:
        json.dump(outcome, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
        stream.write("\n")
