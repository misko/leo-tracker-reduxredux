"""Apply explicit metadata-only exposure review without opening localization data."""

import json
import math
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    path = HERE / "membership.json"
    original = path.read_bytes()
    archive = HERE / "membership.before-exposure-review.json"
    assert not archive.exists()
    archive.write_bytes(original)
    data = json.loads(original)
    target = "scan-fw-e52e11f984aea90c"
    matches = [r for r in data["members"] if r["session_id"] == target]
    assert len(matches) == 1
    exposure = matches[0]["exposure"]
    assert exposure["exposure"] == "prior_identity_match_requires_classification"
    assert len(exposure["matching_files"]) == 1
    assert exposure["matching_files"][0].endswith("/2026_10_09_hard60_b7_rollout/live-jobs.json")
    exposure.update(
        exposure="metadata_only_queue_receipt_independence_unproven",
        consumed=False,
        classification_authority="Parent thread context review: job48943 leased, V3pending; "
        "only queue/API state inspected. live-jobs.json fields are ID/session/jobkind/state/"
        "outcome/error/input/configdigests/timestamps. No coordinates/position error/frequency "
        "results inspected in this thread. External UI or other-thread exposure not certified.",
    )
    lookup = {r["session_id"]: r["exposure"] for r in data["members"]}
    groups = data["grouping"]["groups"]
    for group in groups:
        group["consumed"] = any(lookup[s]["consumed"] for s in group["session_ids"])
        group["unresolved_exposure"] = any(
            lookup[s]["exposure"] == "prior_identity_match_requires_classification"
            for s in group["session_ids"]
        )
        group["assignment"] = "development" if group["consumed"] else "unassigned"
    assert not any(g["unresolved_exposure"] for g in groups)
    eligible = sorted([g for g in groups if not g["consumed"]], key=lambda g: g["random_rank"])
    reserve_count = max(1, math.floor(0.2 * len(eligible))) if len(eligible) >= 5 else 0
    for i, group in enumerate(eligible):
        group["assignment"] = "closed_reserve" if i < reserve_count else "development"
    data["grouping"]["reserve_count"] = reserve_count
    data["grouping"]["group_assignment_counts"] = dict(Counter(g["assignment"] for g in groups))
    data["exposure_review_complete"] = True
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                groups=len(groups),
                unconsumed_groups=len(eligible),
                assignments=data["grouping"]["group_assignment_counts"],
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
