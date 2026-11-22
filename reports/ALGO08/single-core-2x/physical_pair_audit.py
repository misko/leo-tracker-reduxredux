"""Reopen one verified DS30 pair for a per-recording report during staged testing."""

import argparse
import json
from pathlib import Path

from . import ds30_stage as stage
from . import selected_changes
from .compare_publications import compare


def audit_pair(inventory, path):
    case = path.parent.name
    rows = [row for row in inventory["cases"] if row["case"] == case]
    if len(rows) != 1 or rows[0]["state"] != "verified":
        raise ValueError("Pair must belong to a verified recording in the stage inventory")
    row = rows[0]
    spec = inventory["candidate_specification_digest"]
    if stage.file_sha(path) != row["pair_sha256"] or stage.read(path)["candidate_specification_digest"] != spec:
        raise ValueError("Pair receipt or candidate differs from the stage inventory")
    measured = compare(path, stage_clocks=True)
    if row["raw_authority"] != measured["raw_authority"] or (
        "region" in row and row["region"] != measured["region"]
    ):
        raise ValueError("Recording or region differs from the reopened publication")
    truth = stage.pinned(stage.OUT / "reference-audit.json", stage.REFERENCE_SHA256)["cases"]
    refs = {r["dataset_label"]: (r["reference"]["latitude_deg"], r["reference"]["longitude_deg"])
            for r in truth if r["authority_eligible"]}
    # Compute position and timing from the reopened publications.
    verified = dict(row, region=measured["region"], arms={name: measured[name]["arms"] for name in stage.BUILDS},
                    elapsed_s={name: measured[name]["elapsed_s"] for name in stage.BUILDS})
    selected = selected_changes.compare(path, summary=True)
    if stage.file_sha(path) != row["pair_sha256"]:
        raise ValueError("Pair receipt changed during audit")
    return dict(measured, case=case, candidate_specification_digest=spec, pair_sha256=row["pair_sha256"],
                selected_fields=selected, verified_subset_quality=stage.local_quality([verified], refs))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("pair", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit_pair(stage.read(args.inventory), args.pair), indent=2, allow_nan=False))
