"""Join actual native first-scan measurements to dense all-visit anchors."""

import json
from pathlib import Path
import sys

from anchor_exposure import enroll
from leo.contracts.digests import canonical_digest
from mixed_aperture_receiver import strongest
from prefix_history_gate import load_original
from whole_stereo_blocks import HERE, load_checked


LEDGER = "9080bb1d5bb69d2df770593bc1878e6f151d1ba0a7cbbe320e365177552b0556"


def check_candidates(original, full, first):
    winner = strongest(full)
    if original != ([winner] if winner is not None else []):
        raise ValueError("Original anchor disagrees with the archived native two-scan winner")
    if first != [factor for factor in full if factor["candidate_rank"] == 0]:
        raise ValueError("The actual first scan failed to reproduce the original rank zero")


def run():
    mixed, _, source = load_original("DS30-0008")
    ledger = load_checked(HERE/"measurements/primary-schedule.json.gz", LEDGER)
    if ledger["cost_census"]["full_raw_authority"] != source["raw_authority"]:
        raise ValueError("The timing ledger comes from a different recording")
    original = mixed["source"]["probes"]
    records = ledger["costs_and_factors"]
    if len(records) != 256 or canonical_digest([r["primary"] for r in records]) != ledger["primary_trace_digest"]:
        raise ValueError("Expected all actual native first-scan lane measurements")
    slots = iter(enroll(mixed))
    changed = []
    full_ns = first_ns = anchors = 0
    for index, sample in enumerate(records):
        row = original[index]
        visit, _, radio, _, slot, _ = next(slots)
        if sample["index"] != index or sample["metadata"] != dict(row, candidates=[]):
            raise ValueError("Hardware timeline differs from the mixed schedule")
        if slot != "anchor":
            continue
        anchors += 1
        full, first = sample["full"], sample["primary"]
        check_candidates(row["candidates"], full, first)
        _, primary_cost, full_cost = sample["native_cpu_ns"]
        first_ns += primary_cost
        full_ns += full_cost
        if first != row["candidates"]:
            changed.append(dict(visit=visit, radio=radio, full=row["candidates"], first=first,
                                named_owners={arm:rows.get(str(index)) for arm,rows in ledger["ownership"]["by_arm"].items()}))
    return dict(raw_authority=source["raw_authority"], original_signed_packet=source["native_sha256"], ledger_sha256=LEDGER,
                issued_visits=128, anchors=anchors, full_ns=full_ns, first_ns=first_ns, changed=changed)


if __name__ == "__main__":
    with Path(sys.argv[1]).open("x") as stream:
        json.dump(run(), stream, indent=2, sort_keys=True)
