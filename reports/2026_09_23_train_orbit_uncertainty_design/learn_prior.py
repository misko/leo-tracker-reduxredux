#!/usr/bin/env python3
"""Learn the frozen causal phase-rate prior for blind fixed TRAIN identities."""

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import defaultdict
from importlib.metadata import version
from pathlib import Path

from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_set_records, parse_element_sets

ROOT = Path(__file__).resolve().parents[2]
EPOCHS = Path("/tmp/leo-train-orbit-epochs.json")
METADATA = Path("/tmp/leo-train-rx-metadata.json")
ORIGINAL = ROOT / "tools/study_causal_orbit_phase_prior.py"
TRANSITIVE = {
    "orbit_update_modes": ROOT / "tools/study_orbit_update_modes.py",
    "propagation": ROOT / "src/leo/sky/propagation.py",
    "tle_archive": ROOT / "src/leo/operations/tle_archive.py",
}
PARENTS = (
    ROOT / "reports/2026_09_23_long_full8h_shared_epoch_position/results/inference.json",
    ROOT / "reports/2026_09_23_second_train_epoch_replication/results/inference.json",
)
PAIRED = ROOT / "reports/2026_09_23_train_receiver_orbit_diagnostic/results/inference.json"


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_original():
    tools = str(ROOT / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    spec = importlib.util.spec_from_file_location("causal_prior_original", ORIGINAL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("fresh output required")
    epochs = json.loads(EPOCHS.read_text())
    if epochs["bindings"]["strict_metadata"] != digest(METADATA):
        raise ValueError("epoch export strict-metadata binding differs")
    if epochs["bindings"]["fixed_track_parents"] != [digest(path) for path in PARENTS]:
        raise ValueError("epoch export fixed-track parent bindings differ")
    if epochs["bindings"]["paired_inference"] != digest(PAIRED):
        raise ValueError("epoch export paired-inference binding differs")
    wanted = {int(row["candidate_id"]) for row in epochs["rows"]}
    metadata = json.loads(METADATA.read_text())["sessions"]
    earliest_cutoff = (
        min(
            min(track["support_start_utc_ns"] for track in session["tracks"])
            for session in metadata
        )
        - 505_000_000_000
    )
    reader = TleArchiveReader(args.tle_root)
    references = [row for row in reader.list_snapshots() if row.collected_utc_ns < earliest_cutoff]
    histories = defaultdict(dict)
    used = []
    for ordinal, reference in enumerate(references, start=1):
        used.append({"digest": reference.digest, "collected_utc_ns": reference.collected_utc_ns})
        for record in parse_element_set_records(reader.read(reference)):
            if record.satellite_number not in wanted:
                continue
            epoch = parse_element_sets(record.text).element_epoch_utc_ns()[0]
            if epoch >= earliest_cutoff:
                continue
            current = histories[record.satellite_number].get(record.text)
            if current is None or reference.collected_utc_ns < current["first_collected_utc_ns"]:
                histories[record.satellite_number][record.text] = {
                    "text": record.text,
                    "epoch_utc_ns": epoch,
                    "first_collected_utc_ns": reference.collected_utc_ns,
                }
        if ordinal % 50 == 0:
            print(f"archive {ordinal}/{len(references)}", flush=True)
    original = load_original()
    frozen = original.freeze_model(
        {number: list(records.values()) for number, records in histories.items()},
        earliest_cutoff,
    )
    result = {
        "schema": "leo.blind_train_causal_phase_rate_prior.v1",
        "earliest_train_cutoff_utc_ns": earliest_cutoff,
        "blind_fixed_candidate_count": len(wanted),
        "candidates_with_any_history": len(histories),
        "frozen_model": frozen,
        "archive_records_read": used,
        "bindings": {
            "tool": digest(Path(__file__)),
            "original_algorithm": digest(ORIGINAL),
            "fixed_epoch_export": digest(EPOCHS),
            "strict_metadata": digest(METADATA),
            "fixed_track_parents": [digest(path) for path in PARENTS],
            "paired_inference": digest(PAIRED),
            "transitive_sources": {key: digest(path) for key, path in TRANSITIVE.items()},
            "runtime_versions": {name: version(name) for name in ("numpy", "scipy", "sgp4")},
        },
        "rf_outcomes_used": False,
        "reference_position_used": False,
        "future_tle_used": False,
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
