"""Measure retained original observations and price the frozen whole-cycle schedule."""

import json
from pathlib import Path
import sys
from time import process_time

from anchor_cycle_route import select_route
from anchor_exposure import bind
from anchor_holds import history_rows
from cycle_stereo import project
from full_short_run import checked_recipe
from leo.contracts.digests import canonical_digest
from prefix_history_gate import load_original
from whole_stereo_8ms import price


def selection(packet):
    evidence = select_route(packet)
    rows = packet["source"]["probes"]
    return evidence, history_rows(rows) if evidence["route"] == "history" else rows


def compare_rows(full, masked, omitted):
    both = removed = added = loss_on_paid = 0
    for first, second in zip(full, masked, strict=True):
        if (first["visit_index"], first["receiver_id"]) != (second["visit_index"], second["receiver_id"]):
            raise ValueError("Opportunity identities differ")
        a, b = first["candidates"], second["candidates"]
        if a and b:
            if a != b:
                raise ValueError("Measurement on retained lane changed")
            both += 1
        elif a:
            removed += 1
            loss_on_paid += int(first["visit_index"] not in omitted)
        elif b:
            added += 1
        if b and second["visit_index"] in omitted:
            raise ValueError("Unpaid observations entered the selection")
    return dict(common=both, lost=removed, added=added, lost_on_paid=loss_on_paid)


def screen(case):
    original, audit, source = load_original(case)
    recipe = checked_recipe()
    if canonical_digest(recipe) != original["provenance"]["detector_sha256"]:
        raise ValueError("Incorrect candidate parent recipe")
    baseline, all_rows = selection(original)
    begin = process_time()
    masked, _, schedule = project(original, recipe)
    proposal, paid_rows = selection(masked)
    elapsed = process_time() - begin
    bind(original, masked)
    coverage = compare_rows(all_rows, paid_rows, set(schedule["skipped_stereo_visits"]))
    return dict(case=case, source=source, input_visits=audit["issued"], admitted_stereo=len(all_rows)//2,
                baseline=baseline, proposal=proposal, same_route=baseline["route"] == proposal["route"],
                same_measurement_counts=coverage, budget=price(audit, schedule, elapsed),
                paid=schedule["paid_native_lanes"], omitted=schedule["skipped_native_lanes"],
                schedule_sha256=canonical_digest(schedule), selected_sha256=canonical_digest(paid_rows))


if __name__ == "__main__":
    dest = Path(sys.argv[1])
    results = [screen(case) for case in ("DS30-0016", "DS30-0057", "DS30-0008", "north", "south")]
    with dest.open("x") as stream:
        json.dump(results, stream, indent=2, sort_keys=True)
