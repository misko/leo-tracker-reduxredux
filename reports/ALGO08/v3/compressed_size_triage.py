"""Test a signed compressed-size proxy against saved detector and owner support."""

from collections import Counter
from fractions import Fraction
import gzip
from itertools import groupby
import json
from pathlib import Path
import sys

from reports.ALGO08.v3.ds30_owner_support_four import digest, encoded, owner_map, peaks
from reports.ALGO08.v3.full_successor_score import MANIFEST, PINS, ROOT, checked


DEVELOPMENT = ("DS30-0107", "DS30-0049", "DS30-0178", "DS30-0019",
               "DS30-0274", "DS30-0330", "DS30-0397", "DS30-0452")
CONFIRMATION = "DS30-0124"


def selection(original):
    """Bind issued visits to original members and select within each complete quartet."""
    raw = original["raw_recording"]
    indices, groups, chosen = [], [], []
    segments = [(path, list(items)) for path, items in groupby(raw["chunks"], key=lambda c: c["segment_manifest"])]
    if [path for path, _ in segments] != [s["path"] for s in raw["segments"]]:
        raise ValueError("Member order disagrees with the signed segment order")
    member = 0
    for _, chunks in segments:
        group = []
        next_visit = 0
        for index, chunk in enumerate(chunks):
            count = chunk["window_count"]
            if (chunk["first_sequence"] != next_visit or chunk["chunk_index"] != index or count <= 0
                    or min(chunk["compressed_bytes"], chunk["uncompressed_bytes"]) <= 0):
                raise ValueError("Broken member extent")
            indices.extend([member] * count)
            next_visit += count
            if count == 64:
                group.append((member, Fraction(chunk["compressed_bytes"], chunk["uncompressed_bytes"])))
                if len(group) == 4:
                    groups.append([j for j, _ in group])
                    chosen.append(min(group, key=lambda x: (x[1], x[0]))[0])
                    group.clear()
            else:
                group.clear()
            member += 1
    if len(indices) != original["window_count"]:
        raise ValueError("Incomplete signed member membership")
    return indices, groups, chosen


def tally(counts, groups, chosen):
    phases = [sum(counts[g[phase]] for g in groups) for phase in range(4)]
    return dict(total=sum(counts.values()), omitted_by_size=sum(counts[j] for j in chosen),
                omitted_by_fixed_phases=phases, fixed_phase_mean=sum(phases)/4,
                oracle_minimum=sum(min(counts[j] for j in g) for g in groups))


def packet(root, row):
    case, arm = row["case"], row["algorithm"]
    base = root / "cases" / case / arm
    f = (root / row["attempt"]).resolve(strict=True)
    if not f.is_relative_to(base) or row["build_sha256"] != PINS[arm] or not row["verified_pair"]:
        raise ValueError("Unverified original arm")
    body = f.read_bytes()
    if digest(body) != row["attempt_result_sha256"]:
        raise ValueError("Selected attempt changed")
    result = json.loads(body)
    parent = f.parent / "publication"
    native_file, = parent.glob("fast-scan-automatic-work/*/detections.json")
    data = native_file.read_bytes()
    if digest(data) != result["native_sha256"]:
        raise ValueError("Detector packet changed")
    native = json.loads(data)
    if native["source"]["raw_recording_authority_digest"] != row["raw_authority_sha256"]:
        raise ValueError("Detector source differs from the measured original")
    return native, parent, result


def assess(root, rows, original):
    indices, groups, chosen = selection(original)
    packets = [packet(root, row) for row in rows]
    a, b = (p[0] for p in packets)
    if (a["delivery_clocks"] != b["delivery_clocks"] or len(a["delivery_clocks"]) != len(indices)
            or a["provenance"]["excluded_windows"] != b["provenance"]["excluded_windows"]
            or a["source"]["raw_recording_authority_digest"] != b["source"]["raw_recording_authority_digest"]):
        raise ValueError("Receiver time or original capture changed")
    observations = [peaks(native) for native in (a, b)]
    first, second = observations
    if first.keys() != second.keys() or any(row.signature != second[key].signature for key, row in first.items()):
        raise ValueError("Methods used different admitted lanes")
    maps = []
    for native in (a, b):
        session = native["source"]["session_id"]
        maps.append({digest(f"{session}:{p['receiver_id']}:{p['valid_start_counter']}".encode()): p["visit_index"]
                     for p in native["source"]["probes"]})
    if maps[0] != maps[1] or maps[0].keys() != first.keys() or any(not 0 <= i < len(indices) for i in maps[0].values()):
        raise ValueError("Observation identity or visit number changed")
    def counts(keys):
        return Counter(indices[maps[0][key]] for key in keys)
    measured = dict(issued=Counter(indices), admitted=counts(first))
    for role, obs in zip(("installed_positive", "successor_positive"), observations, strict=True):
        measured[role] = counts(key for key, lane in obs.items() if lane.cfo is not None)
    _, parent, result = packets[1]
    if result["outcome"] == "complete":
        evidence = json.loads((parent / "exact-named-raw-witness.json").read_bytes())["evidence"]
        eligible = {k for k, v in second.items() if v.cfo is not None}
        for arm in ("c0", "fitted_c"):
            trusted = evidence["detail"]["arms"][arm]
            if trusted["owner_sha256"] != result["evidence"]["owners"][arm]:
                raise ValueError("Successor owner witness changed")
            measured[arm + "_owners"] = counts(owner_map(evidence["owner_rows"][arm], trusted, eligible))
    return dict(eligible_quartets=len(groups), selected_members=chosen,
                selected_members_sha256=digest(encoded(chosen)),
                attempt_sha256=[row["attempt_result_sha256"] for row in rows],
                metrics={k: tally(v, groups, chosen) for k,v in measured.items()})


def run(root):
    accession = gzip.decompress((ROOT / "reports/2026_11_20_ds30_fast/dataset/manifest.json.gz").read_bytes())
    originals = {r["dataset_label"]: r for r in json.loads(checked(accession, MANIFEST))["members"]}
    raw = [json.loads(s) for s in (root / "rows.jsonl").read_bytes().splitlines()]
    by_key = {(r["case"], r["algorithm"]): r for r in raw}
    results = {}
    for case in (*DEVELOPMENT, CONFIRMATION):
        rows = [by_key[case, arm] for arm in ("installed", "successor")]
        if all(r["verified_pair"] for r in rows):
            if any(r["raw_identity_sha256"] != originals[case]["raw_recording"]["identity_sha256"] for r in rows):
                raise ValueError("Signed recording identity changed")
            results[case] = assess(root, rows, originals[case])
        else:
            results[case] = {"disposition": [row["outcome"] for row in rows]}
    return dict(manifest_sha256=MANIFEST, development=DEVELOPMENT, confirmation=CONFIRMATION, cases=results)


if __name__ == "__main__":
    print(json.dumps(run(Path(sys.argv[1])), indent=2, allow_nan=False))
