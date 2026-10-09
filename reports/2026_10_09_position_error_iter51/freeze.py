"""Freeze uniform full-membership region expansion without outcome-based exclusions."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
ROOT = REPORTS.parent


def read(path):
    return json.loads(path.read_text())


def main():
    if (HERE / "protocol.json").exists():
        raise FileExistsError("Preserve first cohort protocol")
    readiness = read(REPORTS / "2026_10_08_position_error_iter44/readiness.json")
    prior_path = REPORTS / "2026_10_08_position_error_iter45/summary.json"
    prior = {r["member"]["inventory_label"]: r for r in read(prior_path)["cases"]}
    archive_digest = read(REPORTS / "2026_10_08_position_error_iter44/archive-binding.json")[
        "input_digest"
    ]
    ready44 = {
        r["member"]["inventory_label"]
        for r in read(REPORTS / "2026_10_08_position_error_iter44/protocol.json")["ready"]
    }
    retry = {"DS18-034", "DS16-001", "DS16-008", "DS16-011", "DS16-015", "DS16-034", "DS16-042"}
    members = []
    bound_files = []
    for row in readiness["members"]:
        member = row["member"]
        label = member["inventory_label"]
        binding = dict(
            member=member,
            previous_candidate=prior[label]["candidate"],
            effective_input_digest=member["recording_manifest_sha256"] or archive_digest,
            baseline_path=None,
            sep25_path=None,
            sep50_path=None,
        )
        legacy = member["legacy_labels"]
        if member["dataset"] == "DS16" and legacy:
            old = legacy[0]
            binding.update(kind="legacy_ds16", legacy_label=old)
            if old in ("S14", "S27"):
                binding["baseline_path"] = (
                    f"reports/2026_10_08_hard60_bounded_recovery/{old}-document.json"
                )
            bound_files.append(
                REPORTS / "2026_10_08_hard60_bounded_recovery/cohort" / f"{old}.json"
            )
        elif member["dataset"] == "DS17":
            binding.update(
                kind="legacy_ds17",
                baseline_path=f"reports/2026_10_08_position_error_iter01/baseline/{label}.json",
            )
        elif label in ready44:
            binding.update(
                kind="snapshot",
                baseline_path=f"reports/2026_10_08_position_error_iter44/baselines/{label}.json",
                sep25_path=f"reports/2026_10_08_position_error_iter44/regions/{label}.json",
            )
        elif member["evaluation_status"] == "pending":
            folder = "reports/2026_10_08_position_error_iter45" + (
                "/retry" if label in retry else ""
            )
            binding.update(
                kind="completion",
                baseline_path=f"{folder}/baselines/{label}.json",
                sep25_path=f"{folder}/regions/{label}.json",
                completion_path=f"{folder}/results/{label}.json",
            )
        else:
            assert member["dataset"] == "DS18" and row["baseline_status"] == "compatible"
            binding.update(kind="published", baseline_document_digest=row["document_digest"])
        if legacy:
            old = legacy[0]
            candidates = [
                REPORTS / f"2026_10_08_position_error_iter06/results/{old}/separation-25.json",
                REPORTS / f"2026_10_08_position_error_iter20/regions/{old}.json",
                REPORTS / f"2026_10_08_position_error_iter29/regions/{old}.json",
            ]
            if old == "FRESH-005":
                candidates.append(
                    REPORTS / "2026_10_08_position_error_iter21/additional-region.json"
                )
            for path in candidates:
                if path.exists():
                    assert read(path)["session_id"] == member["session_id"]
                    binding["sep25_path"] = str(path.relative_to(ROOT))
                    break
        if label == "DS16-046":
            binding["sep50_path"] = "reports/2026_10_08_position_error_iter48/regions.json"
        for field in ("baseline_path", "sep25_path", "sep50_path", "completion_path"):
            if binding.get(field) and (ROOT / binding[field]).exists():
                bound_files.append(ROOT / binding[field])
        members.append(binding)
    assert len(members) == 148 and len({r["member"]["session_id"] for r in members}) == 148
    hashes = read(REPORTS / "2026_10_08_position_error_iter50/legacy-protocol.json")[
        "source_sha256"
    ].copy()
    for path in [
        *HERE.glob("*.py"),
        *bound_files,
        REPORTS / "2026_10_08_hard60_bounded_recovery/frozen-inputs.json",
        REPORTS / "2026_10_08_position_error_iter44/readiness.json",
    ]:
        hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    plan = dict(
        frozen_at=datetime.now(UTC).isoformat(),
        members=members,
        scope="All 148 members; descriptive consumed-data policy evaluation, no new holdout claim",
        policy=(
            "Retain baseline then add sep25 and sep50; eligible score, earlier ties. "
            "Shared fitted-region downstream bank/calibration/seeds; unchanged stages."
        ),
        budgets=(
            "Identical ordered400grid; regional replay up to4x500s checkpoint slices; "
            "unchanged per-fit budgets. Extra regional computation measured; "
            "not equal-total-compute."
        ),
        incomplete=(
            "Unfinished baselines remain pending; no quality/readiness exclusions. "
            "Later receipts bind frozen input digest/configuration and record digests."
        ),
        reuse=(
            "Reuse bound archived regional documents; run missing sep25 as well as sep50. "
            "DS16-046 sep50 reuses consumed diagnostic, not unseen validation."
        ),
        source_sha256=hashes,
    )
    (HERE / "protocol.json").write_text(json.dumps(plan, indent=2) + "\n")
    print(
        "Frozen",
        len(members),
        "members; kinds",
        {k: sum(r["kind"] == k for r in members) for k in {r["kind"] for r in members}},
    )


if __name__ == "__main__":
    main()
