from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest

from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]
from tools import freeze_raw_satellite_activity_structural_penalty_plan as tool
from tools import replay_raw_grouped_satellite_activity as raw_replay
from tools.raw_satellite_activity_search_configuration import (
    CatalogueScreenConfig,
    build_search_configuration,
    controlled_study_configuration_family_digest,
    member_evaluation_scope_digest,
    producer_implementation_manifest,
)


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _identity(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode()).hexdigest()


def _write(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def _pilot_configuration() -> dict[str, Any]:
    return {
        "schema_version": 3,
        "algorithm_version": "standard-pilot-scan-v3",
        "maximum_scored_candidates_per_probe": 10,
        "methods": ["anchor8", "glrt64", "symbolwise"],
        "probe_samples": 1,
        "coarse_window_samples": 10,
        "subwindow_samples": 2,
        "frequency_coordinate": "baseband_cfo_hz",
        "frequency_reference": "uncalibrated_prior",
    }


def _duration_dataset(
    *,
    cluster_id: str,
    member_id: str,
    session_id: str,
    recording_digest: str,
    receiver_id: int = 0,
    sky_frequency_hz: float = 10e9,
) -> dict[str, Any]:
    return {
        "schema": tool.INPUT_SCHEMA,
        "capture": {
            "session_id": session_id,
            "recording_manifest_digest": recording_digest,
            "stream_id": "stream-0",
            "receiver_id": receiver_id,
            "sample_rate_hz": 10,
            "declared_sample_count": 2,
        },
        "frequency_binding": {
            "tuning_tag": f"tuning:{cluster_id}",
            "sky_frequency_hz": sky_frequency_hz,
        },
        "source_products": {
            "scan": {"file_digest": _identity(f"scan:{member_id}")},
        },
        "scheduled_probes": [
            {
                "schedule_ordinal": index,
                "probe_id": f"{member_id}-probe-{index}",
                "probe_sample_start": index,
                "probe_start_time_s": index / 10,
            }
            for index in range(2)
        ],
    }


class _Corpus:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.calibration_path = _write(
            tmp_path / "calibration.json",
            {"schema": raw_replay.CALIBRATION_SCHEMA_V3},
        )
        self.tle_path = tmp_path / "catalog.tle"
        self.tle_path.write_text("fixed tle bytes\n", encoding="utf-8")
        self.datasets: dict[str, dict[str, Any]] = {}

        splits: dict[str, dict[str, Any]] = {}
        for split, count in (("tuning", 15), ("holdout", 59), ("unused", 1)):
            clusters: list[dict[str, Any]] = []
            for index in range(count):
                cluster_id = f"{split}-{index:02d}"
                member_ids = [f"{cluster_id}-rx0"]
                if cluster_id == "tuning-00":
                    member_ids.append(f"{cluster_id}-rx1")
                recording_digest = _identity(f"recording:{cluster_id}")
                members: list[dict[str, Any]] = []
                for receiver_id, member_id in enumerate(member_ids):
                    dataset = _duration_dataset(
                        cluster_id=cluster_id,
                        member_id=member_id,
                        session_id=f"session-{cluster_id}",
                        recording_digest=recording_digest,
                        receiver_id=receiver_id,
                        sky_frequency_hz=10e9 + index,
                    )
                    path = _write(tmp_path / "datasets" / f"{member_id}.json", dataset)
                    self.datasets[member_id] = dataset
                    members.append(
                        {
                            "member_id": member_id,
                            "duration_dataset_path": str(path.relative_to(tmp_path)),
                            "duration_dataset_digest": _digest(path),
                            "pilot_scan_digest": dataset["source_products"]["scan"]["file_digest"],
                        }
                    )
                clusters.append(
                    {
                        "cluster_id": cluster_id,
                        "source_provenance_ids": [f"physical-dwell:{cluster_id}"],
                        "members": members,
                    }
                )
            splits[split] = {"clusters": clusters}

        raw_config = asdict(
            raw_replay.RawReplayConfig(
                minimum_active_duration_s=0.1,
                delay_min_s=0.0,
                delay_max_s=0.0,
            )
        )
        raw_config.pop("satellite_cost")
        raw_config.pop("episode_cost")
        self.specification = {
            "schema": tool.CORPUS_SPECIFICATION_SCHEMA,
            "study_id": "real-null-corpus-v1",
            "ordered_penalty_pairs": [
                {"satellite_cost": 1.0, "episode_cost": 2.0},
                {"satellite_cost": 5.25, "episode_cost": 5.75},
            ],
            "settings": {
                "score_calibration": {
                    "path": self.calibration_path.name,
                    "digest": _digest(self.calibration_path),
                    "schema": raw_replay.CALIBRATION_SCHEMA_V3,
                },
                "tle": {
                    "path": self.tle_path.name,
                    "digest": _digest(self.tle_path),
                },
                "observer": {
                    "schema_version": 1,
                    "latitude_deg": 37.0,
                    "longitude_deg": -122.0,
                    "altitude_m": 10.0,
                    "label": "fixed-test-site",
                },
                "window": {
                    "start_s": 0.0,
                    "end_s": 0.2,
                    "scheduled_probe_count": 2,
                    "cell_count": 2,
                },
                "pilot_scan": _pilot_configuration(),
                "raw_replay": raw_config,
                "catalogue_screen": asdict(CatalogueScreenConfig()),
            },
            "splits": splits,
        }
        self.specification_path = _write(tmp_path / "corpus.json", self.specification)

    def build(self) -> dict[str, Any]:
        return tool.build_study_plan(self.specification, base_directory=self.tmp_path)


def test_freezes_exact_15_59_plan_and_shared_replay_digests(tmp_path: Path) -> None:
    corpus = _Corpus(tmp_path)
    plan = corpus.build()
    repeated = corpus.build()

    assert plan == repeated
    assert plan["schema"] == tool.adjudicator.PLAN_SCHEMA
    assert len(plan["splits"]["tuning"]["clusters"]) == 15
    assert len(plan["splits"]["holdout"]["clusters"]) == 59
    assert plan["splits"]["holdout"]["predeclared"] is True
    assert len(plan["splits"]["unused"]["clusters"]) == 1

    member = plan["splits"]["tuning"]["clusters"][0]["members"][0]
    assert Path(member["duration_dataset_path"]).is_absolute()
    assert Path(member["duration_dataset_path"]) == (
        corpus.tmp_path / "datasets" / f"{member['member_id']}.json"
    ).resolve()
    execution = plan["execution_inputs"]
    assert execution["score_calibration"] == {
        "path": str(corpus.calibration_path.resolve()),
        "digest": _digest(corpus.calibration_path),
        "schema": raw_replay.CALIBRATION_SCHEMA_V3,
    }
    assert execution["tle"] == {
        "path": str(corpus.tle_path.resolve()),
        "digest": _digest(corpus.tle_path),
    }
    assert "satellite_cost" not in execution["raw_replay_without_structural_costs"]
    assert "episode_cost" not in execution["raw_replay_without_structural_costs"]
    dataset = corpus.datasets[member["member_id"]]
    raw_base = raw_replay.RawReplayConfig(
        minimum_active_duration_s=0.1,
        delay_min_s=0.0,
        delay_max_s=0.0,
    )
    scope_digest = member_evaluation_scope_digest(
        duration_dataset_digest=member["duration_dataset_digest"],
        pilot_scan_digest=member["pilot_scan_digest"],
        session_id=dataset["capture"]["session_id"],
        recording_manifest_digest=dataset["capture"]["recording_manifest_digest"],
        stream_id=dataset["capture"]["stream_id"],
        receiver_id=dataset["capture"]["receiver_id"],
        tuning_tag=dataset["frequency_binding"]["tuning_tag"],
        sky_frequency_hz=dataset["frequency_binding"]["sky_frequency_hz"],
        scheduled_probe_ids=tuple(row["probe_id"] for row in dataset["scheduled_probes"]),
        window_start_s=0.0,
        window_end_s=0.2,
    )
    expected_configuration = build_search_configuration(
        calibration_schema=raw_replay.CALIBRATION_SCHEMA_V3,
        calibration_digest=_digest(corpus.calibration_path),
        tle_digest=_digest(corpus.tle_path),
        sky_frequency_hz=dataset["frequency_binding"]["sky_frequency_hz"],
        pilot_scan_configuration=_pilot_configuration(),
        observer_configuration=corpus.specification["settings"]["observer"],
        window_start_s=0.0,
        window_end_s=0.2,
        scheduled_probe_count=2,
        cell_count=2,
        member_evaluation_scope_digest=scope_digest,
        producer_implementation=producer_implementation_manifest(),
        raw_replay_configuration=asdict(replace(raw_base, satellite_cost=1.0, episode_cost=2.0)),
        catalogue_screen_configuration=asdict(CatalogueScreenConfig()),
    )
    assert member["member_evaluation_scope_digest"] == scope_digest
    assert member["search_configuration_digests"][0]["digest"] == canonical_digest(
        expected_configuration
    )
    assert member["search_configuration_family_digest"] == (
        tool.adjudicator.search_configuration_family_digest(expected_configuration)
    )
    assert plan["controlled_study_family_digest"] == (
        controlled_study_configuration_family_digest(expected_configuration)
    )


def test_rejects_wrong_cluster_counts_and_bound_file_tampering(tmp_path: Path) -> None:
    corpus = _Corpus(tmp_path)
    corpus.specification["splits"]["tuning"]["clusters"].pop()
    with pytest.raises(ValueError, match="exactly 15"):
        corpus.build()

    corpus = _Corpus(tmp_path / "tamper")
    first_member = corpus.specification["splits"]["holdout"]["clusters"][0]["members"][0]
    path = corpus.tmp_path / first_member["duration_dataset_path"]
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duration dataset digest mismatch"):
        corpus.build()


def test_derived_session_identity_cannot_leak_across_splits(tmp_path: Path) -> None:
    corpus = _Corpus(tmp_path)
    tuning_member = corpus.specification["splits"]["tuning"]["clusters"][0]["members"][0]
    holdout_member = corpus.specification["splits"]["holdout"]["clusters"][0]["members"][0]
    tuning_dataset = corpus.datasets[tuning_member["member_id"]]
    holdout_dataset = corpus.datasets[holdout_member["member_id"]]
    holdout_dataset["capture"]["session_id"] = tuning_dataset["capture"]["session_id"]
    holdout_dataset["capture"]["recording_manifest_digest"] = tuning_dataset["capture"][
        "recording_manifest_digest"
    ]
    holdout_path = corpus.tmp_path / holdout_member["duration_dataset_path"]
    _write(holdout_path, holdout_dataset)
    holdout_member["duration_dataset_digest"] = _digest(holdout_path)

    with pytest.raises(ValueError, match="one physical source identity"):
        corpus.build()


def test_scope_binds_window_and_controlled_family_rejects_noncost_drift() -> None:
    common_scope = {
        "duration_dataset_digest": _identity("duration"),
        "pilot_scan_digest": _identity("pilot"),
        "session_id": "session-a",
        "recording_manifest_digest": _identity("recording"),
        "stream_id": "stream-0",
        "receiver_id": 0,
        "tuning_tag": "tuning:a",
        "sky_frequency_hz": 10e9,
        "scheduled_probe_ids": ("probe-0", "probe-1"),
    }
    first_scope = member_evaluation_scope_digest(
        **common_scope,
        window_start_s=0.0,
        window_end_s=0.2,
    )
    shifted_scope = member_evaluation_scope_digest(
        **common_scope,
        window_start_s=0.1,
        window_end_s=0.3,
    )
    assert first_scope != shifted_scope

    base = build_search_configuration(
        calibration_schema="calibration-v1",
        calibration_digest=_identity("calibration"),
        tle_digest=_identity("tle"),
        sky_frequency_hz=10e9,
        pilot_scan_configuration=_pilot_configuration(),
        observer_configuration={"site": "fixed"},
        window_start_s=0.0,
        window_end_s=0.2,
        scheduled_probe_count=2,
        cell_count=2,
        member_evaluation_scope_digest=first_scope,
        producer_implementation=producer_implementation_manifest(),
        raw_replay_configuration={
            "cell_duration_s": 0.1,
            "satellite_cost": 1.0,
            "episode_cost": 2.0,
        },
        catalogue_screen_configuration={"final_catalog_count": 3},
    )
    source_variant = json.loads(json.dumps(base))
    source_variant["sky_frequency_hz"] = 11e9
    source_variant["member_evaluation_scope_digest"] = shifted_scope
    assert controlled_study_configuration_family_digest(base) == (
        controlled_study_configuration_family_digest(source_variant)
    )
    source_variant["raw_replay"]["cell_duration_s"] = 9.9
    assert controlled_study_configuration_family_digest(base) != (
        controlled_study_configuration_family_digest(source_variant)
    )


def test_producer_manifest_binds_transitive_geometry_and_runtime() -> None:
    manifest = producer_implementation_manifest()
    paths = {item["path"] for item in manifest["files"]}
    assert {
        "tools/screen_raw_satellite_activity_catalog.py",
        "tools/replay_raw_grouped_satellite_activity.py",
        "tools/replay_joint_fixed_satellite_activity.py",
        "src/leo/analysis/research/satellite_activity.py",
        "src/leo/analysis/research/multi_satellite_activity.py",
        "src/leo/analysis/research/grouped_satellite_activity.py",
        "src/leo/analysis/research/satellite_activity_scores.py",
        "src/leo/sky/doppler.py",
        "src/leo/sky/frames.py",
        "src/leo/sky/propagation.py",
        "src/leo/sky/sampling.py",
        "src/leo/sky/screening.py",
        "src/leo/contracts/base.py",
        "src/leo/contracts/digests.py",
        "src/leo/contracts/sky.py",
        "pyproject.toml",
        "uv.lock",
    } <= paths
    assert set(manifest["runtime_versions"]) == {"python", "numpy", "sgp4"}


def test_freeze_requires_the_reviewed_corpus_specification_bytes(tmp_path: Path) -> None:
    corpus = _Corpus(tmp_path)
    expected = _digest(corpus.specification_path)
    result = tool.freeze_study_plan(
        specification_path=corpus.specification_path,
        expected_specification_digest=expected,
    )
    assert result["study_id"] == "real-null-corpus-v1"
    with pytest.raises(ValueError, match="corpus specification digest mismatch"):
        tool.freeze_study_plan(
            specification_path=corpus.specification_path,
            expected_specification_digest=_identity("wrong"),
        )


def test_freeze_rejects_an_incomparable_ordered_penalty_path(tmp_path: Path) -> None:
    corpus = _Corpus(tmp_path)
    corpus.specification["ordered_penalty_pairs"] = [
        {"satellite_cost": 1.0, "episode_cost": 3.0},
        {"satellite_cost": 2.0, "episode_cost": 2.0},
    ]
    _write(corpus.specification_path, corpus.specification)

    with pytest.raises(ValueError, match="componentwise nondecreasing"):
        corpus.build()
