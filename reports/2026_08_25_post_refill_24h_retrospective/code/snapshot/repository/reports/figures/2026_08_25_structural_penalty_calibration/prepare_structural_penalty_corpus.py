#!/usr/bin/env python3
"""Materialize the predeclared 2026-08-25 structural-penalty corpus.

This is a study-specific, read-only adapter over sealed Standard products.  It
checks eligibility metadata, writes duration inputs beneath the requested
report directory, and emits a census plus freezer-compatible corpus
specification.  It never runs a catalogue screen and refuses output beneath
the analysis corpus or QNAP.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools import evaluate_duration_constrained_satellite_assignment as duration  # noqa: E402
from tools import freeze_raw_satellite_activity_structural_penalty_plan as freezer  # noqa: E402
from tools import replay_raw_grouped_satellite_activity as raw_replay  # noqa: E402
from tools.raw_satellite_activity_search_configuration import (  # noqa: E402
    CatalogueScreenConfig,
)

CENSUS_SCHEMA = "org.leo.research.raw-satellite-activity-structural-penalty-census/v1"
STUDY_ID = "raw-satellite-activity-structural-penalty-20260825-cap10-v1"
CENSUS_START_SESSION = "cap-20260821T000000"
CENSUS_CUTOFF_SESSION = "cap-20260825T121500"
CENSUS_START_UTC = "2026-08-21T00:00:00Z"
CENSUS_CUTOFF_UTC = "2026-08-25T12:15:00Z"
SELECTION_ALGORITHM = "sha256-study-id-nul-session-id-ascending-v1"

EXPECTED_TUNING_COUNT = 15
EXPECTED_HOLDOUT_COUNT = 59
EXPECTED_ELIGIBLE_COUNT = EXPECTED_TUNING_COUNT + EXPECTED_HOLDOUT_COUNT
EXPECTED_ELIGIBLE_MEMBER_COUNT = 120

CALIBRATION_PATH = REPOSITORY_ROOT / (
    "reports/figures/2026_08_25_raw_satellite_activity_calibration/score-calibration-v3.json"
)
CALIBRATION_DIGEST = "sha256:86e9e6bee34ccc178ae83788ae1a8dbda36fdf7646f1c28a1984a2c7408000d1"
TLE_PATH = Path(
    "/home/mouse9911/.codex/visualizations/2026/08/22/"
    "01a02af8-cec4-7703-a883-75760f132c40/"
    "radio1-rx1-catalog-search-agent/causal-space-track-ac36512e.tle"
)
TLE_DIGEST = "sha256:ac36512e603e6a21bc2ca16d0512a1e14db846ccbad9409d9ac601b371f16dee"

FORCED_TUNING_SESSIONS = {
    "cap-20260823T022003-6aeb95ddead5": (
        "inspected legacy empty-no-result path with a missing frame receipt"
    ),
    "cap-20260825T022509-735366370195": "manual search-gap resolution-group audit",
    "cap-20260825T024108-b84b64ae03dd": "manual search-gap resolution-group audit",
    "cap-20260825T062228-886fe2dd9cde": "persisted structural-null replay inspection",
    "cap-20260825T063754-ef4ff74230d6": "manual search-gap resolution-group audit",
    "cap-20260825T082057-aa0a740de6db": "manual search-gap resolution-group audit",
    "cap-20260825T082330-c8a2692839cd": "manual structural-null inspection",
    "cap-20260825T084200-6614872688fa": "manual structural-null inspection",
    "cap-20260825T085857-6d87a16d291d": "manual structural-null inspection",
    "cap-20260825T091429-c1446df4dd6a": "manual structural-null inspection",
    "cap-20260825T101702-f60463e1402e": "manual structural-null inspection",
    "cap-20260825T105640-facdadeffb3b": "manual structural-null inspection",
    "cap-20260825T105915-2770b84587cc": "manual structural-null inspection",
    "cap-20260825T111222-a2d4ce2afb9a": "manual structural-null inspection",
}
REQUESTED_FORCED_BUT_INELIGIBLE = {
    "cap-20260825T071811-863ec02af098": (
        "manually inspected, but only a research run exists; no sealed Standard "
        "capture-run member meets the corpus contract"
    )
}

ORDERED_PENALTY_PAIRS = (
    {"satellite_cost": 5.25, "episode_cost": 5.75},
    {"satellite_cost": 6.25, "episode_cost": 6.75},
    {"satellite_cost": 8.25, "episode_cost": 8.75},
    {"satellite_cost": 10.25, "episode_cost": 10.75},
    {"satellite_cost": 14.25, "episode_cost": 14.75},
    {"satellite_cost": 22.25, "episode_cost": 22.75},
)
PENALTY_RATIONALE = (
    "The current 5.25/5.75 prototype pair is evaluated first. Costs near 6 are "
    "the log-count scale for roughly 440 visible catalogues and 600 possible "
    "episode starts. Later componentwise-monotone pairs add conservative safety "
    "margin, reaching a combined cost of 45 for hard minimum-duration clutter bursts."
)

PILOT_CONFIGURATION = {
    "schema_version": 3,
    "algorithm_version": "standard-pilot-scan-v3",
    "maximum_scored_candidates_per_probe": 10,
    "methods": ["anchor8", "glrt64", "symbolwise"],
    "probe_samples": 50_000,
    "coarse_window_samples": 2_500_000,
    "subwindow_samples": 125_000,
    "frequency_coordinate": "baseband_cfo_hz",
    "frequency_reference": "uncalibrated_prior",
}
OBSERVER = {
    "schema_version": 1,
    "latitude_deg": 37.858988,
    "longitude_deg": -122.478103,
    "altitude_m": -29.0,
    "label": "spinnaker-sausalito",
}

SESSION_PATTERN = re.compile(r"/analysis/(cap-[^/]+)/")
DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-root", type=Path, default=Path("/srv/bulk/leo/analysis"))
    parser.add_argument("--recordings-root", type=Path, default=Path("/srv/bulk/leo/recordings"))
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args()


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _safe_output_root(path: Path) -> Path:
    resolved = path.resolve(strict=False)
    for prohibited in (Path("/srv"), Path("/mnt/qnap01")):
        if resolved == prohibited or prohibited in resolved.parents:
            raise ValueError(f"output root may not be beneath {prohibited}")
    return resolved


def _source_session_ids(calibration: dict[str, Any]) -> set[str]:
    sessions: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, str):
            match = SESSION_PATTERN.search(value)
            if match is not None:
                sessions.add(match.group(1))

    visit(calibration.get("sources"))
    return sessions


def _analysis_path(logical_uri: object, analysis_root: Path) -> Path:
    if not isinstance(logical_uri, str) or not logical_uri.startswith("bulk://analysis/"):
        raise ValueError("path-report product has an invalid analysis logical URI")
    path = (analysis_root / logical_uri.removeprefix("bulk://analysis/")).resolve(strict=True)
    root = analysis_root.resolve(strict=True)
    if root not in path.parents:
        raise ValueError("analysis logical URI escapes the configured analysis root")
    return path


def _recording_manifest_path(recordings_root: Path, session_id: str) -> Path:
    date = session_id.removeprefix("cap-")[:8]
    return (
        recordings_root / date[:4] / date[4:6] / date[6:8] / session_id / "manifest.json"
    ).resolve(strict=True)


def _candidate_product_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in manifest.get("products", [])
        if row.get("stage_key") == "path-standard"
        and row.get("kind") == "standard.path-report"
        and row.get("role") == "scientific"
        and row.get("status") == "no_result"
    ]


def _eligibility_failure(
    *,
    product: dict[str, Any],
    analysis_root: Path,
) -> tuple[str | None, dict[str, Any] | None]:
    report_path = _analysis_path(product.get("logical_uri"), analysis_root)
    scientific_root = report_path.parent
    source_paths = {key: scientific_root / name for key, name in duration.PRODUCT_NAMES.items()}
    missing = sorted(key for key, path in source_paths.items() if not path.is_file())
    if missing and missing != ["frame_segments"]:
        return "missing_duration_source_products:" + ",".join(missing), None

    try:
        report = _read_object(source_paths["path_report"])
        final = _read_object(source_paths["final_bank"])
        schedule = _read_object(source_paths["schedule"])
        scan = _read_object(source_paths["scan"])
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "duration_source_product_is_not_valid_utf8_json", None
    raw = report.get("raw_report")
    if not isinstance(raw, dict):
        return "path_report_missing_raw_authority", None
    if product.get("digest") != _file_digest(report_path):
        return "analysis_manifest_path_report_digest_mismatch", None
    if not (
        report.get("schema_version") == 2
        and report.get("algorithm_version") == "standard-path-report-v2"
        and report.get("status") == "no_result"
        and report.get("returned_trajectory_count") == 0
        and report.get("truncated_trajectory_count") == 0
    ):
        return "path_report_not_complete_no_result", None
    if not (
        final.get("schema_version") == 3
        and final.get("algorithm_version") == "final-trajectory-bank-v3"
        and final.get("status") == "no_result"
        and final.get("returned_trajectory_count") == 0
        and final.get("truncated_trajectory_count") == 0
        and final.get("trajectories") == []
    ):
        return "final_bank_not_complete_no_result", None
    if not (
        raw.get("sample_rate_hz") == 2_500_000
        and raw.get("declared_sample_count") == 150_000_000
        and raw.get("observed_sample_count") == 150_000_000
        and raw.get("coverage_fraction") == 1.0
    ):
        return "capture_not_gap_free_60s_2p5Msps", None
    probes = schedule.get("probes")
    if not isinstance(probes, list) or not (
        schedule.get("schema_version") == 2
        and schedule.get("algorithm_version") == "standard-probe-schedule-v2"
        and schedule.get("sample_rate_hz") == 2_500_000
        and schedule.get("declared_sample_count") == 150_000_000
        and schedule.get("source_probe_count") == 2400
        and schedule.get("returned_probe_count") == 2400
        and schedule.get("truncated_probe_count") == 0
        and len(probes) == 2400
    ):
        return "probe_schedule_not_exact_2400", None
    expected_starts = [index * 62_500 for index in range(2400)]
    if [int(row["sample_start"]) for row in probes] != expected_starts:
        return "probe_schedule_has_gap_or_reordering", None
    for key, expected in PILOT_CONFIGURATION.items():
        if scan.get(key) != expected:
            return f"pilot_configuration_mismatch:{key}", None
    detections = scan.get("detections")
    if not isinstance(detections, list) or len(detections) != 2400:
        return "pilot_detection_count_not_2400", None
    if [int(row["sample_start"]) for row in detections] != expected_starts:
        return "pilot_detection_schedule_has_gap_or_reordering", None
    for detection in detections:
        candidates = detection.get("candidates")
        if not isinstance(candidates, list) or not (
            detection.get("status") in {"complete", "no_result"}
            and detection.get("source_candidate_count") == 10
            and detection.get("truncated_candidate_count") == 0
            and len(candidates) == 10
        ):
            return "pilot_candidate_inventory_not_exact_10_per_probe", None
        for candidate in candidates:
            methods = [row.get("method") for row in candidate.get("scores", [])]
            if methods.count("glrt64") != 1:
                return "pilot_candidate_missing_unique_glrt64_score", None
    if scan.get("probe_schedule_digest") != schedule.get("schedule_digest"):
        return "pilot_scan_schedule_digest_mismatch", None

    if missing == ["frame_segments"]:
        try:
            duration._require_complete_empty_no_result_without_frame_segments(
                paths=source_paths,
                schedule=schedule,
                scan=scan,
                alias_map=_read_object(source_paths["alias_map"]),
                bank=_read_object(source_paths["dealiased_bank"]),
                final_bank=final,
                path_report=report,
            )
        except ValueError:
            return "missing_frame_receipt_not_safe_for_raw_activity", None

    return None, {
        "scientific_root": scientific_root,
        "scope_key": product["scope_key"],
        "raw_report": raw,
        "pilot_scan_digest": _file_digest(source_paths["scan"]),
        "path_report_digest": _file_digest(source_paths["path_report"]),
        "final_bank_digest": _file_digest(source_paths["final_bank"]),
        "frame_evidence_available": missing != ["frame_segments"],
    }


def _sky_frequency_hz(recording: dict[str, Any], stream_id: str, radio_id: str) -> int:
    streams = [
        row
        for row in recording.get("streams", [])
        if row.get("stream_id") == stream_id and row.get("radio", {}).get("radio_id") == radio_id
    ]
    if len(streams) != 1:
        raise ValueError("recording manifest lacks one requested stream/radio")
    settings = streams[0].get("applied_settings") or streams[0].get("requested_settings")
    if not isinstance(settings, dict):
        raise ValueError("recording stream lacks applied/requested settings")
    profile = recording["capture_plan"]["profile_revision"]["profile"]
    return int(profile["lnb_lo_hz"]) + int(settings["center_frequency_hz"])


def _selection_key(session_id: str) -> str:
    return hashlib.sha256(f"{STUDY_ID}\0{session_id}".encode()).hexdigest()


def _relative_path(path: Path, base: Path) -> str:
    return str(path.relative_to(base))


def materialize(
    *,
    analysis_root: Path,
    recordings_root: Path,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    output_root = _safe_output_root(output_root)
    analysis_root = analysis_root.resolve(strict=True)
    recordings_root = recordings_root.resolve(strict=True)
    for path, expected in (
        (CALIBRATION_PATH, CALIBRATION_DIGEST),
        (TLE_PATH, TLE_DIGEST),
    ):
        observed = _file_digest(path)
        if observed != expected:
            raise ValueError(f"fixed input digest mismatch for {path}: {observed}")

    calibration = _read_object(CALIBRATION_PATH)
    source_sessions = _source_session_ids(calibration)
    expected_sources = {
        "cap-20260824T124902-20c1bfc10f52",
        "cap-20260824T193733-1454b499b8bb",
        "cap-20260825T065355-ba3e4fb8857b",
    }
    if source_sessions != expected_sources:
        raise ValueError(f"score-calibration source sessions changed: {sorted(source_sessions)}")

    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    run_evidence: dict[str, dict[str, str]] = {}
    rejection_counts: Counter[str] = Counter()
    rejected_source_members = 0
    candidate_member_count = 0
    manifest_count = 0
    for manifest_path in sorted(analysis_root.glob("cap-*/capture-*/manifest.json")):
        session_id = manifest_path.parts[-3]
        if session_id < CENSUS_START_SESSION or session_id >= CENSUS_CUTOFF_SESSION:
            continue
        manifest_count += 1
        manifest = _read_object(manifest_path)
        if manifest.get("pipeline_lane") != "standard":
            rejection_counts["analysis_run_not_standard_lane"] += 1
            continue
        manifest_digest = _file_digest(manifest_path)
        for product in _candidate_product_rows(manifest):
            candidate_member_count += 1
            failure, evidence = _eligibility_failure(
                product=product,
                analysis_root=analysis_root,
            )
            if failure is not None:
                rejection_counts[failure] += 1
                continue
            assert evidence is not None
            if session_id in source_sessions:
                rejected_source_members += 1
                continue
            run_evidence[session_id] = {
                "analysis_manifest_path": str(manifest_path.resolve(strict=True)),
                "analysis_manifest_digest": manifest_digest,
            }
            clusters[session_id].append(evidence)

    if len(clusters) != EXPECTED_ELIGIBLE_COUNT:
        raise ValueError(
            "expected 74 eligible clusters, observed "
            f"{len(clusters)}; rejections={dict(sorted(rejection_counts.items()))}"
        )
    if sum(len(rows) for rows in clusters.values()) != EXPECTED_ELIGIBLE_MEMBER_COUNT:
        raise ValueError("eligible member count differs from the reviewed census")
    absent_forced = sorted(set(FORCED_TUNING_SESSIONS) - set(clusters))
    if absent_forced:
        raise ValueError(f"forced tuning sessions are not eligible: {absent_forced}")

    remaining = sorted(
        set(clusters) - set(FORCED_TUNING_SESSIONS),
        key=lambda session_id: (_selection_key(session_id), session_id),
    )
    added_count = EXPECTED_TUNING_COUNT - len(FORCED_TUNING_SESSIONS)
    tuning_added = set(remaining[:added_count])
    tuning = set(FORCED_TUNING_SESSIONS) | tuning_added
    holdout = set(clusters) - tuning
    if len(tuning) != EXPECTED_TUNING_COUNT or len(holdout) != EXPECTED_HOLDOUT_COUNT:
        raise AssertionError("deterministic split accounting failed")

    duration_root = output_root / "duration-inputs"
    split_rows: dict[str, list[dict[str, Any]]] = {"tuning": [], "holdout": []}
    census_clusters = []
    for session_id in sorted(clusters):
        split = "tuning" if session_id in tuning else "holdout"
        recording_path = _recording_manifest_path(recordings_root, session_id)
        recording = _read_object(recording_path)
        recording_digest = _file_digest(recording_path)
        members = []
        census_members = []
        for source in sorted(
            clusters[session_id],
            key=lambda row: (
                str(row["raw_report"]["stream_id"]),
                str(row["raw_report"]["radio_id"]),
                int(row["raw_report"]["receiver_id"]),
                str(row["scope_key"]),
            ),
        ):
            raw = source["raw_report"]
            stream_id = str(raw["stream_id"])
            radio_id = str(raw["radio_id"])
            receiver_id = int(raw["receiver_id"])
            scope_key = str(source["scope_key"])
            radio_suffix = radio_id.removeprefix("radio_pluto_")
            timestamp = session_id.split("T", 1)[1].split("-", 1)[0]
            filename = (
                f"duration-input-{timestamp}-{radio_suffix}-rx{receiver_id}-"
                f"{scope_key.removeprefix('sha256:')[:12]}.json"
            )
            dataset_path = duration_root / filename
            dataset = duration.build_dataset(
                recording_manifest_path=recording_path,
                scientific_root=source["scientific_root"],
                session_id=session_id,
                stream_id=stream_id,
                radio_id=radio_id,
                receiver_id=receiver_id,
                expected_sky_frequency_hz=_sky_frequency_hz(recording, stream_id, radio_id),
                minimum_duration_s=0.5,
                allow_missing_empty_no_result_frame_segments=(
                    not bool(source["frame_evidence_available"])
                ),
            )
            if dataset["probe_geometry"]["scheduled_probe_count"] != 2400:
                raise ValueError("duration extraction changed scheduled probe accounting")
            _write_json(dataset_path, dataset)
            duration_digest = _file_digest(dataset_path)
            member_id = (
                f"{session_id}:{stream_id}:{radio_id}:rx{receiver_id}:"
                f"{scope_key.removeprefix('sha256:')[:12]}"
            )
            members.append(
                {
                    "member_id": member_id,
                    "duration_dataset_path": _relative_path(dataset_path, output_root),
                    "duration_dataset_digest": duration_digest,
                    "pilot_scan_digest": source["pilot_scan_digest"],
                }
            )
            census_members.append(
                {
                    "member_id": member_id,
                    "stream_id": stream_id,
                    "radio_id": radio_id,
                    "receiver_id": receiver_id,
                    "scope_key": scope_key,
                    "scientific_root": str(source["scientific_root"]),
                    "pilot_scan_digest": source["pilot_scan_digest"],
                    "path_report_digest": source["path_report_digest"],
                    "final_bank_digest": source["final_bank_digest"],
                    "frame_evidence_available": source["frame_evidence_available"],
                    "duration_dataset_path": _relative_path(dataset_path, output_root),
                    "duration_dataset_digest": duration_digest,
                }
            )
        analysis_evidence = run_evidence[session_id]
        provenance = [
            f"analysis-manifest:{analysis_evidence['analysis_manifest_digest']}",
            f"recording-manifest:{recording_digest}",
            f"session:{session_id}",
        ]
        split_rows[split].append(
            {
                "cluster_id": f"dwell:{session_id}",
                "source_provenance_ids": provenance,
                "members": members,
            }
        )
        census_clusters.append(
            {
                "session_id": session_id,
                "cluster_id": f"dwell:{session_id}",
                "split": split,
                "prior_structural_inspection": (
                    {
                        "status": "inspected_before_predeclaration",
                        "reason": FORCED_TUNING_SESSIONS[session_id],
                    }
                    if session_id in FORCED_TUNING_SESSIONS
                    else {
                        "status": "not_known_inspected_before_predeclaration",
                        "reason": None,
                    }
                ),
                "selection_digest": "sha256:" + _selection_key(session_id),
                "selected_as_deterministic_tuning_filler": session_id in tuning_added,
                **analysis_evidence,
                "recording_manifest_path": str(recording_path),
                "recording_manifest_digest": recording_digest,
                "members": census_members,
            }
        )

    census = {
        "schema": CENSUS_SCHEMA,
        "study_id": STUDY_ID,
        "created_from_sealed_metadata_only_before_any_study_replay": True,
        "catalogue_replay_executed_by_this_tool": False,
        "census_window": {
            "start_utc_inclusive": CENSUS_START_UTC,
            "cutoff_utc_exclusive": CENSUS_CUTOFF_UTC,
        },
        "eligibility": {
            "analysis_lane": "standard",
            "analysis_run_directory_pattern": "cap-*/capture-*/manifest.json",
            "path_and_final_bank_status": "no_result",
            "sample_rate_hz": 2_500_000,
            "declared_and_observed_sample_count": 150_000_000,
            "coverage_fraction": 1.0,
            "scheduled_probe_count": 2400,
            "probe_start_cadence_samples": 62_500,
            "pilot_scan": PILOT_CONFIGURATION,
            "per_probe_source_and_retained_candidate_count": 10,
            "per_probe_truncated_candidate_count": 0,
            "returned_and_truncated_trajectory_count": 0,
        },
        "source_exclusion": {
            "rule": "exclude an entire session appearing anywhere in score-calibration-v3 sources",
            "score_calibration_path": str(CALIBRATION_PATH),
            "score_calibration_digest": CALIBRATION_DIGEST,
            "session_ids": sorted(source_sessions),
            "eligible_member_count_removed": rejected_source_members,
        },
        "selection": {
            "algorithm": SELECTION_ALGORITHM,
            "forced_tuning_sessions": [
                {"session_id": session_id, "reason": reason}
                for session_id, reason in sorted(FORCED_TUNING_SESSIONS.items())
            ],
            "requested_forced_but_ineligible": [
                {"session_id": session_id, "reason": reason}
                for session_id, reason in sorted(REQUESTED_FORCED_BUT_INELIGIBLE.items())
            ],
            "deterministic_tuning_fillers": sorted(tuning_added),
            "holdout_was_not_screened_or_adjudicated_during_selection": True,
        },
        "penalty_path": {
            "ordered_pairs": list(ORDERED_PENALTY_PAIRS),
            "rationale": PENALTY_RATIONALE,
        },
        "accounting": {
            "analysis_manifests_in_census_window": manifest_count,
            "candidate_no_result_path_member_count": candidate_member_count,
            "eligible_cluster_count": len(clusters),
            "eligible_member_count": sum(len(rows) for rows in clusters.values()),
            "tuning_cluster_count": len(tuning),
            "tuning_member_count": sum(len(clusters[session_id]) for session_id in tuning),
            "holdout_cluster_count": len(holdout),
            "holdout_member_count": sum(len(clusters[session_id]) for session_id in holdout),
            "unused_cluster_count": 0,
            "cluster_size_distribution": {
                str(size): count
                for size, count in sorted(Counter(map(len, clusters.values())).items())
            },
            "pre_eligibility_rejection_counts": dict(sorted(rejection_counts.items())),
        },
        "clusters": census_clusters,
    }
    census_path = output_root / "structural-penalty-census.json"
    _write_json(census_path, census)
    census_digest = _file_digest(census_path)

    raw_configuration = asdict(raw_replay.RawReplayConfig())
    del raw_configuration["satellite_cost"]
    del raw_configuration["episode_cost"]
    specification = {
        "schema": freezer.CORPUS_SPECIFICATION_SCHEMA,
        "study_id": STUDY_ID,
        "census": {
            "path": census_path.name,
            "digest": census_digest,
            "cutoff_utc_exclusive": CENSUS_CUTOFF_UTC,
            "selection_algorithm": SELECTION_ALGORITHM,
        },
        "penalty_rationale": PENALTY_RATIONALE,
        "ordered_penalty_pairs": list(ORDERED_PENALTY_PAIRS),
        "settings": {
            "score_calibration": {
                "path": str(CALIBRATION_PATH),
                "digest": CALIBRATION_DIGEST,
                "schema": "org.leo.research.raw-pilot-activity-score-calibration/v3",
            },
            "tle": {"path": str(TLE_PATH), "digest": TLE_DIGEST},
            "observer": OBSERVER,
            "pilot_scan": PILOT_CONFIGURATION,
            "raw_replay": raw_configuration,
            "catalogue_screen": asdict(CatalogueScreenConfig()),
            "window": {
                "start_s": 0.0,
                "end_s": 60.0,
                "scheduled_probe_count": 2400,
                "cell_count": 600,
            },
        },
        "splits": {
            "tuning": {"clusters": split_rows["tuning"]},
            "holdout": {"clusters": split_rows["holdout"]},
            "unused": {"clusters": []},
        },
    }
    specification_path = output_root / "structural-penalty-corpus-specification.json"
    _write_json(specification_path, specification)
    return census, specification


def main() -> int:
    arguments = _arguments()
    census, specification = materialize(
        analysis_root=arguments.analysis_root,
        recordings_root=arguments.recordings_root,
        output_root=arguments.output_root,
    )
    print(
        json.dumps(
            {
                "census_digest": _file_digest(
                    arguments.output_root / "structural-penalty-census.json"
                ),
                "corpus_specification_digest": _file_digest(
                    arguments.output_root / "structural-penalty-corpus-specification.json"
                ),
                "accounting": census["accounting"],
                "penalty_pair_count": len(specification["ordered_penalty_pairs"]),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
