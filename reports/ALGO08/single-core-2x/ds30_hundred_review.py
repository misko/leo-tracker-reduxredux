"""Summarize verified recording pairs and the nested four- and sixteen-case stages."""

import argparse
import json
from pathlib import Path

from . import ds30_hundred as study
from . import ds30_stage as stage


def review(archive):
    manifest = stage.read(archive / "panel.json")
    ordering = "\n".join(row["case"] for row in manifest["cases"]) + "\n"
    if (stage.sha256(ordering.encode()).hexdigest() != study.ORDER_SHA256 or
            manifest["candidate"] != stage.EXACT_CURVED_LOOKAHEAD or
            manifest["baseline"] != str(stage.pair.BASELINE) or
            manifest["baseline_detector"] != stage.BASELINE_DETECTOR):
        raise ValueError("Archive belongs to another panel or build")
    truth = stage.pinned(stage.OUT / "reference-audit.json", stage.REFERENCE_SHA256)
    refs = {r["dataset_label"]: (r["reference"]["latitude_deg"], r["reference"]["longitude_deg"])
            for r in truth["cases"] if r["authority_eligible"]}
    rows = []
    for i, assigned in enumerate(manifest["cases"], 1):
        name = assigned["case"]
        audit = archive / "audits" / (name + ".json")
        if not audit.exists():
            continue
        row = stage.read(audit)
        if (row["state"] != "verified" or row["rank"] != i or row["case"] != name or
                row["raw_authority"] != assigned["raw_authority"] or
                row["actual_order"] != assigned["order"] or row["region"] != assigned["region"] or
                stage.file_sha(archive / "publications" / name / "pair.json") != row["pair_sha256"]):
            raise ValueError(f"Invalid archived comparison for {name}")
        rows.append(row)
    result = dict(assigned=study.COUNT, verified=len(rows), stages={})
    for size in (4, 16, study.COUNT):
        selected = [row for row in rows if row["rank"] <= size]
        if len(selected) != size:
            result["stages"][str(size)] = dict(assigned=size, verified=len(selected))
            continue
        result["stages"][str(size)] = describe(selected, refs)
    if rows:
        result["verified_subset"] = describe(rows, refs)
    return result


def describe(rows, refs):
    _, summary = study.summarize(rows, refs)
    timing = summary["timing"]["all_verified"]["elapsed_s"]
    return dict(
        verified=len(rows), builds=summary["builds"], timing=summary["timing"],
        passed_elapsed=max(timing.values()) <= .5, quality=stage.local_quality(rows, refs),
        solver_failures={name: [r["case"] for r in rows if r["audit"]["decisions"][name] == "solver_failed"]
                         for name in stage.BUILDS},
        by_first_build={
            label: stage.observed_timing([r for r in rows if r["actual_order"][0] == label])
            for label in stage.BUILDS
        },
        same_pixels_all_returned=sum(
            bool(row["audit"]["decisions"]["baseline"] == row["audit"]["decisions"]["candidate"] == "complete"
                 and not any(row["audit"][k] for k in ("figures_changed", "figures_added", "figures_lost")))
            for row in rows
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    print(json.dumps(review(args.archive), indent=2, allow_nan=False))
