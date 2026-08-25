#!/usr/bin/env python3
"""Freeze an explicit raw-activity structural-penalty corpus into a study plan.

The input is a reviewed JSON corpus specification. This tool never discovers
captures or follows source-product paths: it reads only the specification and
the calibration, TLE, and duration-dataset paths named there. It emits plan
metadata and digests only; it does not run catalogue replay or inspect holdout
evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import asdict, fields, replace
from pathlib import Path
from typing import Any

from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]
from leo.contracts.sky import ObserverSiteV1  # type: ignore[import-untyped]

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools import calibrate_raw_satellite_activity_structural_penalties as adjudicator  # noqa: E402
from tools import replay_raw_grouped_satellite_activity as raw_replay  # noqa: E402
from tools.raw_satellite_activity_search_configuration import (  # noqa: E402
    INPUT_SCHEMA,
    CatalogueScreenConfig,
    build_search_configuration,
    controlled_study_configuration_family_digest,
    member_evaluation_scope_digest,
    pilot_scan_search_configuration,
    producer_implementation_manifest,
)
from tools.replay_joint_fixed_satellite_activity import (  # noqa: E402
    ReplayConfig as _WindowConfig,
)
from tools.replay_joint_fixed_satellite_activity import (  # noqa: E402
    _ordered_schedule,
    _window_inventory,
)

CORPUS_SPECIFICATION_SCHEMA = (
    "org.leo.research.raw-satellite-activity-structural-penalty-corpus-specification/v1"
)
REQUIRED_TUNING_CLUSTER_COUNT = 15


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _number(value: object, label: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or (nonnegative and result < 0.0):
        qualifier = "finite and nonnegative" if nonnegative else "finite"
        raise ValueError(f"{label} must be {qualifier}")
    return result


def _sha256(value: object, label: str) -> str:
    result = _string(value, label)
    if adjudicator.SHA256_PATTERN.fullmatch(result) is None:
        raise ValueError(f"{label} must be a lowercase tagged SHA-256 digest")
    return result


def _resolve_path(value: object, *, base_directory: Path, label: str) -> Path:
    raw_path = Path(_string(value, f"{label} path"))
    path = raw_path if raw_path.is_absolute() else base_directory / raw_path
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"{label} path must name a file")
    return resolved


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return _object(value, f"JSON file {path}")


def _read_bound_object(
    reference: dict[str, Any],
    *,
    base_directory: Path,
    label: str,
) -> tuple[Path, str, dict[str, Any]]:
    path = _resolve_path(reference.get("path"), base_directory=base_directory, label=label)
    expected_digest = _sha256(reference.get("digest"), f"{label} digest")
    observed_digest = _file_digest(path)
    if observed_digest != expected_digest:
        raise ValueError(
            f"{label} digest mismatch: expected {expected_digest}, observed {observed_digest}"
        )
    return path, observed_digest, _read_object(path)


def _read_bound_bytes(
    reference: dict[str, Any],
    *,
    base_directory: Path,
    label: str,
) -> tuple[Path, str]:
    path = _resolve_path(reference.get("path"), base_directory=base_directory, label=label)
    expected_digest = _sha256(reference.get("digest"), f"{label} digest")
    observed_digest = _file_digest(path)
    if observed_digest != expected_digest:
        raise ValueError(
            f"{label} digest mismatch: expected {expected_digest}, observed {observed_digest}"
        )
    return path, observed_digest


def _ordered_pairs(value: object) -> tuple[dict[str, Any], ...]:
    rows = _list(value, "ordered penalty pairs")
    if not rows:
        raise ValueError("at least one ordered penalty pair is required")
    result: list[dict[str, Any]] = []
    identities: set[tuple[float, float]] = set()
    for pair_index, raw_pair in enumerate(rows):
        pair = _object(raw_pair, f"penalty pair {pair_index}")
        if set(pair) != {"satellite_cost", "episode_cost"}:
            raise ValueError(
                "each input penalty pair must contain only satellite_cost and episode_cost"
            )
        satellite_cost = _number(
            pair.get("satellite_cost"),
            f"penalty pair {pair_index} satellite cost",
            nonnegative=True,
        )
        episode_cost = _number(
            pair.get("episode_cost"),
            f"penalty pair {pair_index} episode cost",
            nonnegative=True,
        )
        identity = (satellite_cost, episode_cost)
        if identity in identities:
            raise ValueError("ordered penalty pairs must be unique")
        identities.add(identity)
        result.append(
            {
                "pair_index": pair_index,
                "satellite_cost": satellite_cost,
                "episode_cost": episode_cost,
            }
        )
    for previous, current in zip(result, result[1:], strict=False):
        if (
            current["satellite_cost"] < previous["satellite_cost"]
            or current["episode_cost"] < previous["episode_cost"]
        ):
            raise ValueError("ordered penalty pairs must be componentwise nondecreasing")
    return tuple(result)


def _fixed_raw_replay_configuration(value: object) -> raw_replay.RawReplayConfig:
    document = _object(value, "raw replay settings")
    prohibited = {"satellite_cost", "episode_cost"} & document.keys()
    if prohibited:
        raise ValueError("raw replay settings must omit the ordered structural costs")
    expected = {item.name for item in fields(raw_replay.RawReplayConfig)} - {
        "satellite_cost",
        "episode_cost",
    }
    if set(document) != expected:
        raise ValueError(
            "raw replay settings must explicitly freeze every noncost field; "
            f"missing={sorted(expected - document.keys())}, "
            f"extra={sorted(document.keys() - expected)}"
        )
    config = raw_replay.RawReplayConfig(
        **document,
        satellite_cost=0.0,
        episode_cost=0.0,
    )
    # Validate the derived grid now rather than first discovering a bad setting in replay.
    _ = config.delay_grid
    return config


def _fixed_catalogue_screen_configuration(value: object) -> CatalogueScreenConfig:
    document = _object(value, "catalogue screen settings")
    expected = {item.name for item in fields(CatalogueScreenConfig)}
    if set(document) != expected:
        raise ValueError(
            "catalogue screen settings must explicitly freeze every field; "
            f"missing={sorted(expected - document.keys())}, "
            f"extra={sorted(document.keys() - expected)}"
        )
    return CatalogueScreenConfig(**document)


def _source_identity(
    dataset: dict[str, Any],
    *,
    label: str,
) -> tuple[dict[str, Any], dict[str, Any], tuple[str, ...]]:
    if dataset.get("schema") != INPUT_SCHEMA:
        raise ValueError(f"{label} has unexpected duration-dataset schema")
    capture = _object(dataset.get("capture"), f"{label} capture")
    frequency = _object(dataset.get("frequency_binding"), f"{label} frequency binding")
    session_id = _string(capture.get("session_id"), f"{label} session ID")
    recording_digest = _sha256(
        capture.get("recording_manifest_digest"), f"{label} recording manifest digest"
    )
    _string(capture.get("stream_id"), f"{label} stream ID")
    _integer(capture.get("receiver_id"), f"{label} receiver ID")
    _string(frequency.get("tuning_tag"), f"{label} tuning tag")
    _number(frequency.get("sky_frequency_hz"), f"{label} sky frequency")
    return (
        capture,
        frequency,
        (
            f"recording-manifest:{recording_digest}",
            f"session:{session_id}",
        ),
    )


def _pilot_scan_digest(dataset: dict[str, Any], *, label: str) -> str:
    products = _object(dataset.get("source_products"), f"{label} source products")
    scan = _object(products.get("scan"), f"{label} pilot scan source")
    return _sha256(scan.get("file_digest"), f"{label} pilot scan digest")


def _window(
    dataset: dict[str, Any],
    *,
    raw_config: raw_replay.RawReplayConfig,
    start_s: float,
    end_s: float,
    expected_probe_count: int,
    expected_cell_count: int,
    label: str,
) -> Any:
    inventory = _window_inventory(
        dataset=dataset,
        ordered_schedule=_ordered_schedule(dataset),
        start_s=start_s,
        end_s=end_s,
        config=_WindowConfig(
            cell_duration_s=raw_config.cell_duration_s,
            minimum_active_duration_s=raw_config.minimum_active_duration_s,
            allow_left_censored=raw_config.allow_left_censored,
            allow_right_censored=raw_config.allow_right_censored,
        ),
    )
    if len(inventory.rows) != expected_probe_count or inventory.cell_count != expected_cell_count:
        raise ValueError(
            f"{label} window accounting differs from the fixed study settings: "
            f"probes={len(inventory.rows)}, cells={inventory.cell_count}"
        )
    return inventory


def build_study_plan(
    specification: dict[str, Any],
    *,
    base_directory: Path,
) -> dict[str, Any]:
    """Validate an explicit corpus specification and build deterministic PLAN_SCHEMA JSON."""

    if specification.get("schema") != CORPUS_SPECIFICATION_SCHEMA:
        raise ValueError(f"expected corpus specification schema {CORPUS_SPECIFICATION_SCHEMA}")
    study_id = _string(specification.get("study_id"), "study ID")
    ordered_pairs = _ordered_pairs(specification.get("ordered_penalty_pairs"))

    settings = _object(specification.get("settings"), "fixed settings")
    calibration_reference = _object(
        settings.get("score_calibration"), "score calibration reference"
    )
    calibration_path, calibration_digest, calibration = _read_bound_object(
        calibration_reference,
        base_directory=base_directory,
        label="score calibration",
    )
    calibration_schema = calibration_reference.get("schema")
    if calibration.get("schema") != calibration_schema:
        raise ValueError("score calibration schema does not match the fixed reference")
    _string(calibration_schema, "score calibration schema")

    tle_reference = _object(settings.get("tle"), "TLE reference")
    tle_path, tle_digest = _read_bound_bytes(
        tle_reference,
        base_directory=base_directory,
        label="TLE",
    )
    observer = ObserverSiteV1.model_validate(_object(settings.get("observer"), "observer"))
    pilot_scan_configuration = pilot_scan_search_configuration(
        _object(settings.get("pilot_scan"), "pilot scan settings")
    )
    raw_config = _fixed_raw_replay_configuration(settings.get("raw_replay"))
    screen_config = _fixed_catalogue_screen_configuration(settings.get("catalogue_screen"))
    producer_implementation = producer_implementation_manifest()

    window_settings = _object(settings.get("window"), "window settings")
    if set(window_settings) != {"start_s", "end_s", "scheduled_probe_count", "cell_count"}:
        raise ValueError("window settings must freeze start, end, scheduled probes, and cells")
    start_s = _number(window_settings.get("start_s"), "window start", nonnegative=True)
    end_s = _number(window_settings.get("end_s"), "window end", nonnegative=True)
    if end_s <= start_s:
        raise ValueError("window end must be greater than its start")
    scheduled_probe_count = _integer(
        window_settings.get("scheduled_probe_count"), "scheduled probe count", minimum=2
    )
    cell_count = _integer(window_settings.get("cell_count"), "cell count", minimum=1)

    split_specifications = _object(specification.get("splits"), "splits")
    split_counts = {
        "tuning": REQUIRED_TUNING_CLUSTER_COUNT,
        "holdout": adjudicator.REQUIRED_HOLDOUT_CLUSTER_COUNT,
    }
    output_splits: dict[str, Any] = {}
    cluster_ids: set[str] = set()
    member_ids: set[str] = set()
    member_artifacts: set[tuple[str, str]] = set()
    evaluation_scope_digests: set[str] = set()
    provenance_owner: dict[str, str] = {}
    controlled_family_digests: set[str] = set()

    for split in ("tuning", "holdout", "unused"):
        raw_split = split_specifications.get(split)
        if raw_split is None:
            if split != "unused":
                raise ValueError(f"missing required {split} split")
            cluster_rows: list[Any] = []
        else:
            split_document = _object(raw_split, f"{split} split")
            cluster_rows = _list(split_document.get("clusters"), f"{split} clusters")
        required_count = split_counts.get(split)
        if required_count is not None and len(cluster_rows) != required_count:
            raise ValueError(f"{split} split must contain exactly {required_count} dwell clusters")

        output_clusters: list[dict[str, Any]] = []
        for cluster_index, raw_cluster in enumerate(cluster_rows):
            label = f"{split} cluster {cluster_index}"
            cluster = _object(raw_cluster, label)
            cluster_id = _string(cluster.get("cluster_id"), f"{label} ID")
            if cluster_id in cluster_ids:
                raise ValueError("cluster IDs must be unique across all splits")
            cluster_ids.add(cluster_id)
            declared_provenance = {
                _string(item, f"{label} source provenance ID")
                for item in _list(
                    cluster.get("source_provenance_ids"), f"{label} source provenance IDs"
                )
            }
            if not declared_provenance:
                raise ValueError(f"{label} needs explicit physical-event provenance")
            members = _list(cluster.get("members"), f"{label} members")
            if not members:
                raise ValueError(f"{label} must contain at least one member")

            output_members: list[dict[str, Any]] = []
            derived_provenance: set[str] = set()
            for member_index, raw_member in enumerate(members):
                member_label = f"{label} member {member_index}"
                member = _object(raw_member, member_label)
                member_id = _string(member.get("member_id"), f"{member_label} ID")
                if member_id in member_ids:
                    raise ValueError("member IDs must be unique across all splits")
                member_ids.add(member_id)

                dataset_reference = {
                    "path": member.get("duration_dataset_path"),
                    "digest": member.get("duration_dataset_digest"),
                }
                duration_path, duration_digest, dataset = _read_bound_object(
                    dataset_reference,
                    base_directory=base_directory,
                    label=f"{member_label} duration dataset",
                )
                pilot_digest = _pilot_scan_digest(dataset, label=member_label)
                expected_pilot_digest = _sha256(
                    member.get("pilot_scan_digest"), f"{member_label} expected pilot scan digest"
                )
                if pilot_digest != expected_pilot_digest:
                    raise ValueError(f"{member_label} pilot scan digest disagrees with its dataset")
                for artifact in (
                    ("duration_dataset", duration_digest),
                    ("pilot_scan", pilot_digest),
                ):
                    if artifact in member_artifacts:
                        raise ValueError(f"member artifact is reused in the corpus: {artifact}")
                    member_artifacts.add(artifact)

                capture, frequency, source_ids = _source_identity(dataset, label=member_label)
                derived_provenance.update(source_ids)
                member_window = _window(
                    dataset,
                    raw_config=raw_config,
                    start_s=start_s,
                    end_s=end_s,
                    expected_probe_count=scheduled_probe_count,
                    expected_cell_count=cell_count,
                    label=member_label,
                )
                scope_digest = member_evaluation_scope_digest(
                    duration_dataset_digest=duration_digest,
                    pilot_scan_digest=pilot_digest,
                    session_id=str(capture["session_id"]),
                    recording_manifest_digest=str(capture["recording_manifest_digest"]),
                    stream_id=str(capture["stream_id"]),
                    receiver_id=int(capture["receiver_id"]),
                    tuning_tag=str(frequency["tuning_tag"]),
                    sky_frequency_hz=float(frequency["sky_frequency_hz"]),
                    scheduled_probe_ids=tuple(str(row["probe_id"]) for row in member_window.rows),
                    window_start_s=start_s,
                    window_end_s=end_s,
                )
                if scope_digest in evaluation_scope_digests:
                    raise ValueError("member evaluation scope is reused in the corpus")
                evaluation_scope_digests.add(scope_digest)

                configurations = []
                for pair in ordered_pairs:
                    pair_config = replace(
                        raw_config,
                        satellite_cost=float(pair["satellite_cost"]),
                        episode_cost=float(pair["episode_cost"]),
                    )
                    configurations.append(
                        build_search_configuration(
                            calibration_schema=calibration_schema,
                            calibration_digest=calibration_digest,
                            tle_digest=tle_digest,
                            sky_frequency_hz=float(frequency["sky_frequency_hz"]),
                            pilot_scan_configuration=pilot_scan_configuration,
                            observer_configuration=observer.model_dump(mode="json"),
                            window_start_s=start_s,
                            window_end_s=end_s,
                            scheduled_probe_count=scheduled_probe_count,
                            cell_count=cell_count,
                            member_evaluation_scope_digest=scope_digest,
                            producer_implementation=producer_implementation,
                            raw_replay_configuration=asdict(pair_config),
                            catalogue_screen_configuration=asdict(screen_config),
                        )
                    )
                family_digests = {
                    adjudicator.search_configuration_family_digest(item) for item in configurations
                }
                if len(family_digests) != 1:
                    raise ValueError("only the two ordered structural costs may vary across pairs")
                controlled_family_digests.update(
                    controlled_study_configuration_family_digest(item) for item in configurations
                )
                output_members.append(
                    {
                        "member_id": member_id,
                        # This is an execution locator, not scientific identity. Replay
                        # re-hashes the bytes against duration_dataset_digest before use;
                        # all family and scope comparisons remain path-independent.
                        "duration_dataset_path": str(duration_path),
                        "duration_dataset_digest": duration_digest,
                        "pilot_scan_digest": pilot_digest,
                        "member_evaluation_scope_digest": scope_digest,
                        "search_configuration_family_digest": next(iter(family_digests)),
                        "search_configuration_digests": [
                            {
                                "pair_index": pair_index,
                                "digest": canonical_digest(configuration),
                            }
                            for pair_index, configuration in enumerate(configurations)
                        ],
                    }
                )

            combined_provenance = tuple(sorted(declared_provenance | derived_provenance))
            for provenance_id in combined_provenance:
                prior = provenance_owner.setdefault(provenance_id, cluster_id)
                if prior != cluster_id:
                    raise ValueError(
                        "one physical source identity may belong to only one dwell cluster: "
                        f"{provenance_id}"
                    )
            output_clusters.append(
                {
                    "cluster_id": cluster_id,
                    "source_provenance_ids": list(combined_provenance),
                    "members": output_members,
                }
            )

        output_splits[split] = {
            **({"predeclared": True} if split == "holdout" else {}),
            "clusters": output_clusters,
        }

    if len(controlled_family_digests) != 1:
        raise ValueError("every study member must share one controlled non-source search family")
    plan = {
        "schema": adjudicator.PLAN_SCHEMA,
        "study_id": study_id,
        "controlled_study_family_digest": next(iter(controlled_family_digests)),
        "ordered_penalty_pairs": list(ordered_pairs),
        # Retain the exact, reviewed execution arguments so a runner can consume
        # this frozen plan without rediscovering inputs or inferring defaults.
        # Paths are locators only: every external byte source is digest-bound.
        "execution_inputs": {
            "score_calibration": {
                "path": str(calibration_path),
                "digest": calibration_digest,
                "schema": calibration_schema,
            },
            "tle": {
                "path": str(tle_path),
                "digest": tle_digest,
            },
            "observer": observer.model_dump(mode="json"),
            "window": {
                "start_s": start_s,
                "end_s": end_s,
                "scheduled_probe_count": scheduled_probe_count,
                "cell_count": cell_count,
            },
            "pilot_scan": pilot_scan_configuration,
            "raw_replay_without_structural_costs": {
                key: value
                for key, value in asdict(raw_config).items()
                if key not in {"satellite_cost", "episode_cost"}
            },
            "catalogue_screen": asdict(screen_config),
        },
        "qualification": {
            "interval_method": adjudicator.INTERVAL_METHOD,
            "required_holdout_cluster_count": adjudicator.REQUIRED_HOLDOUT_CLUSTER_COUNT,
            "confidence_level": adjudicator.CONFIDENCE_LEVEL,
            "maximum_false_activation_rate": adjudicator.MAXIMUM_FALSE_ACTIVATION_RATE,
        },
        "splits": output_splits,
    }
    adjudicator.parse_plan(plan)
    return plan


def freeze_study_plan(
    *,
    specification_path: Path,
    expected_specification_digest: str,
) -> dict[str, Any]:
    """Digest-bind a corpus specification and freeze its study plan."""

    expected_digest = _sha256(expected_specification_digest, "corpus specification digest")
    resolved = specification_path.resolve(strict=True)
    observed_digest = _file_digest(resolved)
    if observed_digest != expected_digest:
        raise ValueError(
            "corpus specification digest mismatch: "
            f"expected {expected_digest}, observed {observed_digest}"
        )
    return build_study_plan(_read_object(resolved), base_directory=resolved.parent)


def _write(document: dict[str, Any], output: Path | None) -> None:
    rendered = json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if output is None:
        sys.stdout.write(rendered)
        return
    adjudicator._refuse_qnap_output(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-specification", type=Path, required=True)
    parser.add_argument("--corpus-specification-sha256", required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    document = freeze_study_plan(
        specification_path=arguments.corpus_specification,
        expected_specification_digest=arguments.corpus_specification_sha256,
    )
    _write(document, arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
