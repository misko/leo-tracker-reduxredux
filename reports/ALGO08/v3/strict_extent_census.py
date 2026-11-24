"""Count recordings whose signed decoded byte lengths rule out fixed 20 ms windows."""

import csv
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path


REPORTS = Path(__file__).resolve().parents[2]
NOMINAL_BYTES = 200_000 * 2 * 2 * 2  # samples × radios × I/Q × bytes per scalar


def checked(data, digest):
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("Unexpected inventory or evaluation file digest")
    return data


def census(members, cohort, outcomes):
    originals = {r["raw_recording"]["identity_sha256"]: r for r in members}
    if len(originals) != len(members) or {r["content"] for r in cohort} != originals.keys():
        raise ValueError("Expected the same unique original recording identities")
    affected = {}
    total_chunks = non_nominal = incomplete = 0
    for row in cohort:
        source = originals[row["content"]]
        chunks = source["raw_recording"]["chunks"]
        if (row["windows"] != source["window_count"] or row["recording_state"] != source["recording_state"]
                or sum(c["window_count"] for c in chunks) != row["windows"]):
            raise ValueError("Cohort and original recording disagree")
        total_chunks += len(chunks)
        incomplete += row["recording_state"] == "incomplete"
        differences = [NOMINAL_BYTES * c["window_count"] - c["uncompressed_bytes"] for c in chunks]
        if any(differences):
            affected[row["id"]] = {"state": row["recording_state"], "nominal_minus_actual_bytes": sum(differences)}
            non_nominal += sum(value != 0 for value in differences)
    case_ids = {r["id"] for r in cohort}
    if len(case_ids) != len(cohort) or len(cohort) != len(members):
        raise ValueError("Expected distinct cohort cases for each original recording")
    fixes = Counter()
    fixed_arms = Counter()
    seen = set()
    for row in outcomes:
        if row["method"] != "compact_two_scan":
            continue
        key = (row["case"], row["calibration"])
        if key in seen or row["fix"] not in ("True", "False"):
            raise ValueError("Repeated outcome or unknown fix status")
        seen.add(key)
        if row["case"] in affected and row["fix"] == "True":
            fixes[row["calibration"]] += 1
            fixed_arms[row["case"]] += 1
    if seen != {(case, arm) for case in case_ids for arm in ("c0", "fitted_c")}:
        raise ValueError("Incomplete compact two-scan evaluation")
    return dict(recordings=len(case_ids), incomplete_recordings=incomplete, chunks=total_chunks,
                non_nominal_chunks=non_nominal, affected=affected, historical_compact_fixes=dict(fixes),
                historical_compact_fixes_both=sum(value == 2 for value in fixed_arms.values()))


if __name__ == "__main__":
    dataset = REPORTS / "2026_11_20_ds30_fast/dataset/manifest.json.gz"
    evaluation = REPORTS / "2026_11_21_ds30_full"
    manifest = checked(gzip.decompress(dataset.read_bytes()),
                       "a4ce879975be0593f1adeb7c106f31660c6c423f17e2c7858985244530dc0eb8")
    cohort = checked((evaluation / "cohort.json").read_bytes(),
                     "e7820b05f5ac829fa65860e0ae53cc523edd9ab9160d46216b071c86ff0deb20")
    outcomes = checked((evaluation / "recordings.csv").read_bytes(),
                       "5bf1ad2c255c51ff5325592607b1aa6c3007012432abe447f83c6847fa859caa")
    print(json.dumps(census(json.loads(manifest)["members"], json.loads(cohort)["members"],
                            csv.DictReader(outcomes.decode().splitlines())), indent=2))
