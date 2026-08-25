#!/usr/bin/env python3
"""Archive non-mainline research sources used by this retrospective.

The research worktree was intentionally dirty while these reports were built.
This script copies the current bytes of every known report-only source into the
report bundle and records SHA-256 provenance. Files already tracked by Git are
recorded as mainline dependencies and are not duplicated.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

REPOSITORY_SOURCES = (
    "reports/figures/2026_08_25_structural_penalty_calibration/prepare_structural_penalty_corpus.py",
    "tools/associate_cross_dwell_shared_norad.py",
    "tools/calibrate_raw_pilot_activity_scores.py",
    "tools/calibrate_raw_satellite_activity_structural_penalties.py",
    "tools/control_raw_multipath_activity_block_derangement.py",
    "tools/decide_raw_catalogue_null_vs_any.py",
    "tools/evaluate_duration_constrained_satellite_assignment.py",
    "tools/freeze_raw_satellite_activity_structural_penalty_plan.py",
    "tools/raw_satellite_activity_search_configuration.py",
    "tools/replay_joint_fixed_satellite_activity.py",
    "tools/replay_raw_grouped_satellite_activity.py",
    "tools/replay_raw_multipath_paired_prediction_time_specificity.py",
    "tools/replay_raw_multipath_satellite_activity.py",
    "tools/replay_raw_single_path_fixed_norad_paired_prediction_time_specificity.py",
    "tools/replay_single_satellite_activity.py",
    "tools/run_raw_satellite_activity_structural_penalty_study.py",
    "tools/screen_raw_satellite_activity_catalog.py",
    "src/leo/analysis/research/activity_block_derangement.py",
    "src/leo/analysis/research/activity_block_permutation.py",
    "src/leo/analysis/research/cross_dwell_shared_norad.py",
    "src/leo/analysis/research/grouped_satellite_activity.py",
    "src/leo/analysis/research/joint_multipath_satellite_activity.py",
    "src/leo/analysis/research/multi_satellite_activity.py",
    "src/leo/analysis/research/multipath_satellite_activity.py",
    "src/leo/analysis/research/satellite_activity.py",
    "src/leo/analysis/research/satellite_activity_scores.py",
    "src/leo/analysis/research/satellite_assignment.py",
    "src/leo/analysis/research/scalable_grouped_satellite_activity.py",
    "src/leo/analysis/research/scalable_multi_satellite_activity.py",
    "tests/analysis/test_activity_block_derangement.py",
    "tests/analysis/test_activity_block_permutation.py",
    "tests/analysis/test_calibrate_raw_pilot_activity_scores_tool.py",
    "tests/analysis/test_calibrate_raw_satellite_activity_structural_penalties_tool.py",
    "tests/analysis/test_cross_dwell_shared_norad.py",
    "tests/analysis/test_cross_dwell_shared_norad_adapter_tool.py",
    "tests/analysis/test_decide_raw_catalogue_null_vs_any_tool.py",
    "tests/analysis/test_duration_constrained_satellite_assignment_tool.py",
    "tests/analysis/test_freeze_raw_satellite_activity_structural_penalty_plan_tool.py",
    "tests/analysis/test_grouped_satellite_activity.py",
    "tests/analysis/test_joint_multipath_satellite_activity.py",
    "tests/analysis/test_multi_satellite_activity.py",
    "tests/analysis/test_multipath_satellite_activity.py",
    "tests/analysis/test_raw_multipath_activity_block_derangement_control_tool.py",
    "tests/analysis/test_raw_multipath_paired_prediction_time_specificity_tool.py",
    "tests/analysis/test_raw_single_path_fixed_norad_paired_prediction_time_specificity_tool.py",
    "tests/analysis/test_replay_joint_fixed_satellite_activity_tool.py",
    "tests/analysis/test_replay_raw_grouped_satellite_activity_tool.py",
    "tests/analysis/test_replay_raw_multipath_satellite_activity_tool.py",
    "tests/analysis/test_replay_single_satellite_activity_tool.py",
    "tests/analysis/test_run_raw_satellite_activity_structural_penalty_study_tool.py",
    "tests/analysis/test_satellite_activity.py",
    "tests/analysis/test_satellite_activity_scores.py",
    "tests/analysis/test_satellite_assignment.py",
    "tests/analysis/test_scalable_grouped_satellite_activity.py",
    "tests/analysis/test_scalable_multi_satellite_activity.py",
    "tests/analysis/test_screen_raw_satellite_activity_catalog_tool.py",
)

MAINLINE_DEPENDENCIES = (
    "pyproject.toml",
    "uv.lock",
    "src/leo/contracts/base.py",
    "src/leo/contracts/digests.py",
    "src/leo/contracts/sky.py",
    "src/leo/sky/doppler.py",
    "src/leo/sky/frames.py",
    "src/leo/sky/propagation.py",
    "src/leo/sky/sampling.py",
    "src/leo/sky/screening.py",
)

RELATED_REPORTS = (
    "reports/2026_08_25_065355_satellite_activity.md",
    "reports/2026_08_25_073628_raw_satellite_activity.md",
    "reports/2026_08_25_103607_raw_satellite_activity.md",
    "reports/figures/2026_08_25_structural_penalty_calibration/README.md",
)

VISUALIZATION_ROOT = Path(
    "/home/mouse9911/.codex/visualizations/2026/08/25/01a036e6-81b5-7f91-83bf-c12b18268cb3"
)
EXTERNAL_SOURCES = (
    "build-115401-four-path-candidate.py",
    "build-four-path-cfo-tle-data.py",
    "build-shared-multipath-dwell-replay.py",
    "build_dwell_activity_data.py",
    "135219-catalogue-screen/build_wrong_time_aggregate_summary.py",
    "135219-catalogue-screen/run_posthoc_nearest_wrong_time.py",
    "135219-catalogue-screen/run_wrong_time_diagnostic.py",
)

EVIDENCE_ARTIFACTS = (
    "reports/figures/2026_08_25_073628_satellite_activity/raw-catalogue-37p5-60-score-v3-exhaustive-fine.json",
    "reports/figures/2026_08_25_085623_satellite_activity/raw-multipath-catalogue-utc-52p5-60-score-v3.json",
    "reports/figures/2026_08_25_103607_satellite_activity/raw-multipath-catalogue-utc-46-60-score-v3-wide-posthoc.json",
    "reports/figures/2026_08_25_structural_penalty_calibration/holdout-evidence/structural-penalty-qualification.json",
)
EXTERNAL_EVIDENCE_ARTIFACTS = (
    "115401-paired-specificity/identity-vs-four-nonaffine-controls.json",
    "115401-multipath-replay/replay-wide-fine-delay-minus2-to-plus2-step-0p1s.json",
    "135219-catalogue-screen/wrong-time-aggregate-summary.json",
    "cross-dwell-085623-103607/shared-norad-freeze-50-60-controls-v2/association.json",
    "cross-dwell-085623-103607/fixed-target-controls-final/085623-50-60-norad-66811.json",
    "cross-dwell-085623-103607/fixed-target-controls-final/103607-norad-66811.json",
)

REPORT_OWNED_SOURCES = (
    "code/build_retrospective_bundle.py",
    "code/snapshot_report_sources.py",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _run(repository: Path, *command: str) -> str:
    return subprocess.run(
        command,
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _is_tracked(repository: Path, relative_path: str) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", relative_path],
        cwd=repository,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _copy_and_record(
    source: Path,
    destination: Path,
    *,
    original_path: str,
    origin: str,
    tracked: bool,
) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {
        "origin": origin,
        "original_path": original_path,
        "snapshot_path": str(destination),
        "git_tracked_at_snapshot": tracked,
        "byte_size": destination.stat().st_size,
        "sha256": _sha256(destination),
    }


def main() -> None:
    report_root = Path(__file__).resolve().parents[1]
    repository = report_root.parents[1]
    snapshot_root = report_root / "code" / "snapshot"
    related_root = report_root / "related_reports"
    records: list[dict[str, Any]] = []

    for relative_path in REPORT_OWNED_SOURCES:
        source = report_root / relative_path
        records.append(
            {
                "origin": "report-owned",
                "original_path": str(source),
                "snapshot_path": relative_path,
                "git_tracked_at_snapshot": False,
                "byte_size": source.stat().st_size,
                "sha256": _sha256(source),
            }
        )

    for relative_path in REPOSITORY_SOURCES:
        source = repository / relative_path
        if not source.is_file():
            raise FileNotFoundError(source)
        tracked = _is_tracked(repository, relative_path)
        if tracked:
            records.append(
                {
                    "origin": "repository-mainline",
                    "original_path": relative_path,
                    "snapshot_path": None,
                    "git_tracked_at_snapshot": True,
                    "byte_size": source.stat().st_size,
                    "sha256": _sha256(source),
                }
            )
        else:
            records.append(
                _copy_and_record(
                    source,
                    snapshot_root / "repository" / relative_path,
                    original_path=relative_path,
                    origin="repository-non-mainline",
                    tracked=False,
                )
            )

    for relative_path in MAINLINE_DEPENDENCIES:
        source = repository / relative_path
        records.append(
            {
                "origin": "repository-mainline",
                "original_path": relative_path,
                "snapshot_path": None,
                "git_tracked_at_snapshot": _is_tracked(repository, relative_path),
                "byte_size": source.stat().st_size,
                "sha256": _sha256(source),
            }
        )

    related_records: list[dict[str, Any]] = []
    for relative_path in RELATED_REPORTS:
        source = repository / relative_path
        destination = related_root / Path(relative_path).name
        related_records.append(
            _copy_and_record(
                source,
                destination,
                original_path=relative_path,
                origin="related-report",
                tracked=_is_tracked(repository, relative_path),
            )
        )

    for relative_path in EXTERNAL_SOURCES:
        source = VISUALIZATION_ROOT / relative_path
        if not source.is_file():
            raise FileNotFoundError(source)
        records.append(
            _copy_and_record(
                source,
                snapshot_root / "visualization" / relative_path,
                original_path=str(source),
                origin="visualization-workspace",
                tracked=False,
            )
        )

    evidence: list[dict[str, Any]] = []
    for relative_path in EVIDENCE_ARTIFACTS:
        source = repository / relative_path
        evidence.append(
            {
                "location": relative_path,
                "byte_size": source.stat().st_size,
                "sha256": _sha256(source),
            }
        )
    for relative_path in EXTERNAL_EVIDENCE_ARTIFACTS:
        source = VISUALIZATION_ROOT / relative_path
        if not source.is_file():
            raise FileNotFoundError(source)
        evidence.append(
            {
                "location": str(source),
                "byte_size": source.stat().st_size,
                "sha256": _sha256(source),
            }
        )

    manifest = {
        "schema": "org.leo.research.report-source-snapshot/v1",
        "repository_root": str(repository),
        "repository_head": _run(repository, "git", "rev-parse", "HEAD"),
        "note": (
            "Non-mainline source bytes are copied for forensic review. Some "
            "historical artifacts bind earlier source hashes; SNAPSHOT_NOTES.md "
            "documents known drift. Mainline dependencies are bound to Git and "
            "their current SHA-256 values rather than duplicated."
        ),
        "sources": sorted(records, key=lambda item: item["original_path"]),
        "related_reports": sorted(related_records, key=lambda item: item["original_path"]),
        "evidence_artifacts": sorted(evidence, key=lambda item: item["location"]),
    }
    (report_root / "code" / "SNAPSHOT_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    main()
