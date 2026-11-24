"""Price fixed lookahead allocation from archived member order and timing only."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path


MAX_SLOT = 128 * 1024**2
RESIDENT_PIN = "sha256:e395cfb23e155b13373e77bda89262be84605f22869922a17e82d79f020a8af9"


def digest(body):
    return "sha256:" + sha256(body).hexdigest()


def allocation_plan(sizes):
    capacities = [0, 0]
    events = []
    for ordinal, size in enumerate(sizes):
        if type(size) is not int or not 0 < size <= MAX_SLOT:
            raise ValueError("Expected an eligible bounded member size")
        slot = ordinal % 2
        before = capacities[slot]
        kind = "initial" if before == 0 else "growth" if size > before else "reuse"
        events.append(dict(ordinal=ordinal, slot=slot, size=size, before=before, kind=kind))
        capacities[slot] = max(size, before)
    return dict(capacities=capacities, safe_equal_capacity=max(capacities),
                additional_capacity_for_equal_slots=abs(capacities[0] - capacities[1]),
                repeated_capacity_on_growth=sum(e["before"] for e in events if e["kind"] == "growth"), events=events)


def observed(arm):
    producer = arm["prefetch"]
    members = producer["members"]
    plan = allocation_plan([row["bytes"] for row in members])
    stats = producer["prefetch"]
    if (stats["hits"] != len(members) or stats["fallback"] or len(producer["slots"]) != 2
            or any(slot.get("ordinary", 0) for slot in producer["slots"])):
        raise ValueError("The measured alternation requires two slots with no refusals")
    for i, slot in enumerate(producer["slots"]):
        these = [e for e in plan["events"] if e["slot"] == i]
        counts = dict(allocations=sum(e["kind"] != "reuse" for e in these),
                      reuses=sum(e["kind"] == "reuse" for e in these), peak_bytes=plan["capacities"][i])
        if slot != counts:
            raise ValueError("Observed allocation counters differ from ordered size model")
    for event, member in zip(plan["events"], members, strict=True):
        calls = [call for call in member["calls"] if call["operation"] == "readv"]
        if not member["supplied"] or sum(c["bytes"] for c in calls) != member["bytes"]:
            raise ValueError("Expected every complete original read in the observer")
        event.update({key: sum(call[key] for call in calls) for key in ("cpu_ns", "minor_faults", "input_blocks")})
        event.update(segment=member["segment"], member=member["name"])
    plan["totals"] = {kind: {key: sum(e[key] for e in plan["events"] if e["kind"] == kind)
                            for key in ("size", "cpu_ns", "minor_faults", "input_blocks")}
                      for kind in ("initial", "growth", "reuse")}
    return plan


def campaign(root, rows, case):
    match, = [r for r in rows if (r["case"], r["algorithm"], r.get("verified_pair")) == (case, "successor", True)]
    path = root / match["attempt"]
    if not path.resolve(strict=True).is_relative_to(root / "cases" / case / "successor"):
        raise ValueError("Expected a verified successor attempt inside its own archived case")
    body = path.read_bytes()
    if digest(body) != match["attempt_result_sha256"]:
        raise ValueError("The sealed attempt changed")
    result = json.loads(body)
    source = (path.parent / "publication/legacy-original-acquisition.json").read_bytes()
    wrapper = (path.parent / "publication/unified-short-bootstrap.json").read_bytes()
    admission, runtime = map(json.loads, (source, wrapper))
    if (runtime["native_sha256"] != result["native_sha256"]
            or admission["finished_raw_authority"] != result["raw_identity"]["raw_authority_sha256"]):
        raise ValueError("Signed roster and timing are for different acquisitions")
    sizes = [row["encoded"] for row in admission["members"] if row["chunk_index"]]
    stats = runtime["prefetch"]
    if (stats["submitted"] != stats["hits"] or stats["fallback"]
            or (len(sizes), sum(sizes)) != (stats["hits"], stats["hit_bytes"])):
        raise ValueError("Could not infer exact original producer order")
    plan = allocation_plan(sizes)
    plan["events"] = [event for event in plan["events"] if event["kind"] != "reuse"]
    return dict(plan=plan, existing_read_ahead=stats, attempt_sha256=digest(body), signed_member_sha256=digest(source),
                runtime_sha256=digest(wrapper), segment_start_demand_reads=len(admission["members"]) - len(sizes))


def study(source, root, cases):
    blob = gzip.decompress(source.read_bytes())
    if digest(blob) != RESIDENT_PIN:
        raise ValueError("The as-run source-pinned resident trace changed")
    measured = json.loads(blob)
    root = root.resolve(strict=True)
    data = (root / "rows.jsonl").read_bytes()
    rows = list(map(json.loads, data.splitlines()))
    return dict(scope="receipt-only", fresh_waveform_bytes=0, fresh_processes=0, resident_trace_sha256=RESIDENT_PIN,
                measured_resident={key: observed(measured["arms"][key]) for key in ("reuse-1", "reuse-2")},
                campaign_rows_sha256=digest(data), modeled_campaign={case: campaign(root, rows, case) for case in cases})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("resident_trace", type=Path)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("cases", nargs="+")
    args = parser.parse_args()
    print(json.dumps(study(args.resident_trace, args.campaign, args.cases), sort_keys=True, indent=2, allow_nan=False))
