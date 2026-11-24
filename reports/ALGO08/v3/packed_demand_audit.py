"""Audit combined packed-input demand from already sealed acquisition metadata."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
from statistics import median

from .anchor_exposure import enroll


HERE = Path(__file__).resolve().parent
COMBINED = HERE / "measurements" / "packed-combined-0016.json.gz"
COMBINED_PIN = "4c2a467306118dc7ce28867c7890c738726d67071fbc83c326612d7d9505d457"
ORIGINAL_PIN = "b95c3a5fc21ab89dae16619a66e41c6155ff123bb1300ea833525788b713fdc2"
PART_BYTES = (960_000, 640_000)


def digest(data):
    return sha256(data).hexdigest()


def recent_scope(combined, original):
    current = combined["common"]
    for field in ("input_native_sha256", "pre_refinement_probes_sha256", "selected_native_sha256", "input_inventory"):
        if current["held"][field] != original["held_choice"][field]:
            raise ValueError(f"Original combined acquisition disagrees on {field}")
    if (current["native_sha256"] != original["native_sha256"]
            or current["inventory_sha256"] != original["prefix_inventory"]
            or current["schedule"]["visits"] != original["acquisition"]["native"]["visits"]):
        raise ValueError("Original matched scope or aperture schedule changed")


def demand(probes, paid, records, rule):
    if rule != ["full"] + ["short_primary"] * 7:
        raise ValueError("Expected the combined full-coverage visit schedule")
    issued, processed = len(records), len(probes) // 2
    source = dict(source=dict(probes=probes), provenance=dict(window_count=issued, processed_windows=processed,
                                                              invalid_capture=issued - processed))
    visits = list(enroll(source))
    admit = {visit for visit, *_ in visits}
    full = {visit for visit, _, _, _, kind, _ in visits if kind == "anchor"}
    selected = {(visit, lane) for visit, _, lane, _, kind, events in visits if events[1] and kind == "short"}
    paid_keys = set(map(tuple, paid))
    paid_visits = {visit for visit, _ in paid_keys}
    if len(paid) != len(paid_keys) or not paid_keys <= selected or full & paid_visits:
        raise ValueError("A paid CFO attempt belongs to a duplicate, empty or full lane")
    if [row["sequence"] for row in records] != list(range(len(records))) or not admit <= set(range(len(records))):
        raise ValueError("Packed extents and signed visits do not share an original ordered member")

    def priced(prefix, tail):
        chosen = prefix, tail
        return dict(prefix_blocks=len(prefix), tail_blocks=len(tail),
                    decoded_bytes=sum(len(part) * PART_BYTES[i] for i, part in enumerate(chosen)),
                    encoded_payload_bytes=sum(row["parts"][i][1] for i, part in enumerate(chosen)
                                              for row in records if row["sequence"] in part))

    everything = set(range(len(records)))
    return dict(full_visits=sorted(full), paid_lanes=paid, paid_visits=sorted(paid_visits),
                invalid_visits=sorted(everything - admit), all_blocks=priced(everything, everything),
                earlier_unrefined=priced(admit, full), combined_demand=priced(admit, full | paid_visits))


def run(original_path, seek_path):
    combined_bytes = gzip.decompress(COMBINED.read_bytes())
    prior = original_path.read_bytes()
    seek = seek_path.read_bytes()
    if digest(combined_bytes) != COMBINED_PIN or digest(prior) != ORIGINAL_PIN:
        raise ValueError("A signed acquisition receipt changed")
    combined, original, packed = map(json.loads, (combined_bytes, prior, seek))
    recent_scope(combined, original)
    [mapped] = combined["setup"]["map"]["members"]
    if "sha256:" + digest(seek) != mapped["seek_sha256"] or packed["original_manifest"] != mapped["manifest_sha256"]:
        raise ValueError("Seek extents are not bound to the measured combined acquisition")
    result = demand(original["original_probes"], original["paid"], packed["records"],
                    combined["common"]["schedule"]["rule"])
    packed_runs = [pair["measurements"]["packed"]["evidence"]["storage"]["members"][0] for pair in combined["pairs"]]
    medians = {key: median(run[key]["wall_ns"] for run in packed_runs) for key in ("authenticate", "decode")}
    return dict(result, source_sha256=dict(combined=COMBINED_PIN, original=ORIGINAL_PIN, seek=digest(seek)),
                current_median_component_wall_ns=medians)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("seek", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.original, args.seek), sort_keys=True, indent=2))
