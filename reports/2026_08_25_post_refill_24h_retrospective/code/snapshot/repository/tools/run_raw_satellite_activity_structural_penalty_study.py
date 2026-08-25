#!/usr/bin/env python3
"""Execute a frozen raw-activity structural-penalty study split.

This research runner consumes only an immutable study plan. It never discovers
captures or selects members. Tuning evaluates every predeclared member at every
ordered penalty pair. Holdout is inaccessible without a digest-bound canonical
lock and then evaluates only that lock's selected pair.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any, Literal

from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]
from leo.contracts.sky import ObserverSiteV1  # type: ignore[import-untyped]

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools import calibrate_raw_satellite_activity_structural_penalties as adjudicator  # noqa: E402
from tools import replay_raw_grouped_satellite_activity as raw_replay  # noqa: E402
from tools import screen_raw_satellite_activity_catalog as catalogue_screen  # noqa: E402
from tools.raw_satellite_activity_search_configuration import (  # noqa: E402
    CatalogueScreenConfig,
    build_search_configuration,
    pilot_scan_search_configuration,
    producer_implementation_manifest,
)

Split = Literal["tuning", "holdout"]
ScreenFunction = Callable[..., dict[str, Any]]
QNAP_ROOT = Path("/mnt/qnap01")
SERVER_ROOT = Path("/srv")


@dataclass(frozen=True, slots=True)
class ExecutionInputs:
    calibration_path: Path
    calibration_digest: str
    calibration_document: dict[str, Any]
    tle_path: Path
    tle_digest: str
    observer: ObserverSiteV1
    start_s: float
    end_s: float
    scheduled_probe_count: int
    cell_count: int
    pilot_scan: dict[str, Any]
    raw_replay: raw_replay.RawReplayConfig
    catalogue_screen: CatalogueScreenConfig
    producer_implementation: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RunnableMember:
    cluster_id: str
    cluster_index: int
    member_index: int
    member: adjudicator.MemberSpec
    dataset_path: Path
    dataset: dict[str, Any]
    expected_search_configurations: dict[int, dict[str, Any]]


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _refuse_output(path: Path) -> Path:
    resolved = path.resolve(strict=False)
    if resolved == QNAP_ROOT or QNAP_ROOT in resolved.parents:
        raise ValueError("study runner refuses output beneath /mnt/qnap01")
    if resolved == SERVER_ROOT or SERVER_ROOT in resolved.parents:
        raise ValueError("study runner refuses output beneath /srv")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError("study output root exists and is not a directory")
    return resolved


def _resolved_bound_path(reference: dict[str, Any], label: str) -> tuple[Path, str]:
    raw_path = Path(adjudicator._string(reference.get("path"), f"{label} path"))
    if not raw_path.is_absolute():
        raise ValueError(f"frozen {label} path must be absolute")
    path = raw_path.resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"frozen {label} path must name a file")
    expected_digest = adjudicator._sha256(reference.get("digest"), f"{label} digest")
    observed_digest = _file_digest(path)
    if observed_digest != expected_digest:
        raise ValueError(
            f"{label} digest mismatch: expected {expected_digest}, observed {observed_digest}"
        )
    return path, observed_digest


def _execution_inputs(plan_document: dict[str, Any]) -> ExecutionInputs:
    document = adjudicator._object(plan_document.get("execution_inputs"), "execution inputs")
    expected_keys = {
        "score_calibration",
        "tle",
        "observer",
        "window",
        "pilot_scan",
        "raw_replay_without_structural_costs",
        "catalogue_screen",
    }
    if set(document) != expected_keys:
        raise ValueError(
            "execution inputs must contain exactly the frozen runner arguments; "
            f"missing={sorted(expected_keys - document.keys())}, "
            f"extra={sorted(document.keys() - expected_keys)}"
        )

    calibration_reference = adjudicator._object(
        document.get("score_calibration"), "score calibration execution input"
    )
    if set(calibration_reference) != {"path", "digest", "schema"}:
        raise ValueError("score calibration execution input has unexpected fields")
    calibration_path, calibration_digest = _resolved_bound_path(
        calibration_reference, "score calibration"
    )
    calibration_document = _read_object(calibration_path)
    calibration_schema = adjudicator._string(
        calibration_reference.get("schema"), "score calibration schema"
    )
    if calibration_document.get("schema") != calibration_schema:
        raise ValueError("score calibration schema differs from the frozen execution input")

    tle_reference = adjudicator._object(document.get("tle"), "TLE execution input")
    if set(tle_reference) != {"path", "digest"}:
        raise ValueError("TLE execution input has unexpected fields")
    tle_path, tle_digest = _resolved_bound_path(tle_reference, "TLE")

    observer = ObserverSiteV1.model_validate(
        adjudicator._object(document.get("observer"), "observer execution input")
    )
    window = adjudicator._object(document.get("window"), "window execution input")
    if set(window) != {"start_s", "end_s", "scheduled_probe_count", "cell_count"}:
        raise ValueError("window execution input has unexpected fields")
    start_s = adjudicator._number(window.get("start_s"), "window start", nonnegative=True)
    end_s = adjudicator._number(window.get("end_s"), "window end", nonnegative=True)
    if end_s <= start_s:
        raise ValueError("window end must be greater than window start")
    scheduled_probe_count = adjudicator._integer(
        window.get("scheduled_probe_count"), "scheduled probe count", minimum=2
    )
    cell_count = adjudicator._integer(window.get("cell_count"), "cell count", minimum=1)

    raw_document = adjudicator._object(
        document.get("raw_replay_without_structural_costs"), "raw replay execution input"
    )
    raw_fields = {item.name for item in fields(raw_replay.RawReplayConfig)} - {
        "satellite_cost",
        "episode_cost",
    }
    if set(raw_document) != raw_fields:
        raise ValueError(
            "raw replay execution input must freeze every noncost field; "
            f"missing={sorted(raw_fields - raw_document.keys())}, "
            f"extra={sorted(raw_document.keys() - raw_fields)}"
        )
    raw_configuration = raw_replay.RawReplayConfig(
        **raw_document,
        satellite_cost=0.0,
        episode_cost=0.0,
    )
    _ = raw_configuration.delay_grid

    screen_document = adjudicator._object(
        document.get("catalogue_screen"), "catalogue screen execution input"
    )
    screen_fields = {item.name for item in fields(CatalogueScreenConfig)}
    if set(screen_document) != screen_fields:
        raise ValueError(
            "catalogue screen execution input must freeze every field; "
            f"missing={sorted(screen_fields - screen_document.keys())}, "
            f"extra={sorted(screen_document.keys() - screen_fields)}"
        )
    screen_configuration = CatalogueScreenConfig(**screen_document)

    pilot_document = adjudicator._object(document.get("pilot_scan"), "pilot scan execution input")
    normalized_pilot = pilot_scan_search_configuration(pilot_document)
    if normalized_pilot != pilot_document:
        raise ValueError(
            "pilot scan execution input contains fields outside its bound search scope"
        )

    return ExecutionInputs(
        calibration_path=calibration_path,
        calibration_digest=calibration_digest,
        calibration_document=calibration_document,
        tle_path=tle_path,
        tle_digest=tle_digest,
        observer=observer,
        start_s=start_s,
        end_s=end_s,
        scheduled_probe_count=scheduled_probe_count,
        cell_count=cell_count,
        pilot_scan=normalized_pilot,
        raw_replay=raw_configuration,
        catalogue_screen=screen_configuration,
        producer_implementation=producer_implementation_manifest(),
    )


def _pair_indices_and_lock(
    *,
    split: Split,
    plan: adjudicator.StudyPlan,
    plan_path: Path,
    plan_digest: str,
    lock_path: Path | None,
    expected_lock_digest: str | None,
) -> tuple[tuple[int, ...], str | None]:
    if split == "tuning":
        if lock_path is not None or expected_lock_digest is not None:
            raise ValueError("tuning execution must not be conditioned on a penalty lock")
        return tuple(pair.pair_index for pair in plan.pairs), None
    if lock_path is None or expected_lock_digest is None:
        raise ValueError("holdout execution requires both a penalty lock and its SHA-256 digest")
    lock_document = adjudicator._read_bound_object(
        lock_path, expected_lock_digest, "penalty lock"
    )
    resolved_lock_path = lock_path.resolve(strict=True)
    lock_digest = _file_digest(resolved_lock_path)
    pair = adjudicator._validate_lock(lock_document, plan, plan_digest)
    # A syntactically valid lock is insufficient: re-open its bound tuning
    # evidence and require byte-for-byte canonical adjudication before holdout.
    adjudicator._recompute_lock(
        lock_document,
        plan_path=plan_path,
        plan_digest=plan_digest,
        lock_path=resolved_lock_path,
    )
    return (pair.pair_index,), lock_digest


def _raw_split_clusters(plan_document: dict[str, Any], split: Split) -> list[Any]:
    splits = adjudicator._object(plan_document.get("splits"), "plan splits")
    split_document = adjudicator._object(splits.get(split), f"{split} split")
    return adjudicator._list(split_document.get("clusters"), f"{split} clusters")


def _preflight_members(
    *,
    plan_document: dict[str, Any],
    plan: adjudicator.StudyPlan,
    split: Split,
    pair_indices: tuple[int, ...],
    execution: ExecutionInputs,
) -> tuple[RunnableMember, ...]:
    parsed_clusters = plan.tuning_clusters if split == "tuning" else plan.holdout_clusters
    raw_clusters = _raw_split_clusters(plan_document, split)
    if len(raw_clusters) != len(parsed_clusters):
        raise ValueError(f"{split} raw and parsed cluster accounting differs")

    runnable: list[RunnableMember] = []
    for cluster_index, (raw_cluster_value, cluster) in enumerate(
        zip(raw_clusters, parsed_clusters, strict=True)
    ):
        raw_cluster = adjudicator._object(raw_cluster_value, f"{split} cluster {cluster_index}")
        if raw_cluster.get("cluster_id") != cluster.cluster_id:
            raise ValueError(f"{split} raw and parsed cluster order differs")
        raw_members = adjudicator._list(
            raw_cluster.get("members"), f"{split} cluster {cluster_index} members"
        )
        if len(raw_members) != len(cluster.members):
            raise ValueError(f"{split} raw and parsed member accounting differs")
        for member_index, (raw_member_value, member) in enumerate(
            zip(raw_members, cluster.members, strict=True)
        ):
            label = f"{split} cluster {cluster_index} member {member_index}"
            raw_member = adjudicator._object(raw_member_value, label)
            if raw_member.get("member_id") != member.member_id:
                raise ValueError(f"{label} raw and parsed identities differ")
            raw_path = Path(
                adjudicator._string(
                    raw_member.get("duration_dataset_path"), f"{label} duration dataset path"
                )
            )
            if not raw_path.is_absolute():
                raise ValueError(f"{label} duration dataset path must be frozen as absolute")
            dataset_path = raw_path.resolve(strict=True)
            if not dataset_path.is_file():
                raise ValueError(f"{label} duration dataset path must name a file")
            observed_digest = _file_digest(dataset_path)
            if observed_digest != member.duration_dataset_digest:
                raise ValueError(
                    f"{label} duration dataset digest mismatch: expected "
                    f"{member.duration_dataset_digest}, observed {observed_digest}"
                )
            dataset = _read_object(dataset_path)
            frequency = adjudicator._object(
                dataset.get("frequency_binding"), f"{label} frequency binding"
            )
            sky_frequency_hz = adjudicator._number(
                frequency.get("sky_frequency_hz"), f"{label} sky frequency"
            )
            expected_configurations: dict[int, dict[str, Any]] = {}
            for pair_index in pair_indices:
                pair = plan.pairs[pair_index]
                pair_configuration = replace(
                    execution.raw_replay,
                    satellite_cost=pair.satellite_cost,
                    episode_cost=pair.episode_cost,
                )
                search_configuration = build_search_configuration(
                    calibration_schema=execution.calibration_document.get("schema"),
                    calibration_digest=execution.calibration_digest,
                    tle_digest=execution.tle_digest,
                    sky_frequency_hz=sky_frequency_hz,
                    pilot_scan_configuration=execution.pilot_scan,
                    observer_configuration=execution.observer.model_dump(mode="json"),
                    window_start_s=execution.start_s,
                    window_end_s=execution.end_s,
                    scheduled_probe_count=execution.scheduled_probe_count,
                    cell_count=execution.cell_count,
                    member_evaluation_scope_digest=member.member_evaluation_scope_digest,
                    producer_implementation=execution.producer_implementation,
                    raw_replay_configuration=asdict(pair_configuration),
                    catalogue_screen_configuration=asdict(execution.catalogue_screen),
                )
                observed_search_digest = canonical_digest(search_configuration)
                expected_search_digest = member.search_configuration_digests[pair_index]
                if observed_search_digest != expected_search_digest:
                    raise ValueError(
                        f"{label} pair {pair_index} frozen execution inputs no longer match "
                        f"the predeclared search digest: expected {expected_search_digest}, "
                        f"observed {observed_search_digest}"
                    )
                expected_configurations[pair_index] = search_configuration
            runnable.append(
                RunnableMember(
                    cluster_id=cluster.cluster_id,
                    cluster_index=cluster_index,
                    member_index=member_index,
                    member=member,
                    dataset_path=dataset_path,
                    dataset=dataset,
                    expected_search_configurations=expected_configurations,
                )
            )
    return tuple(runnable)


def _render(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _write_validated_replay(
    *,
    replay_path: Path,
    document: dict[str, Any],
    member: adjudicator.MemberSpec,
    pair: adjudicator.PenaltyPair,
    expected_search_configuration: dict[str, Any],
    controlled_study_family_digest: str,
) -> str:
    expected_search_digest = member.search_configuration_digests[pair.pair_index]
    if document.get("search_configuration_digest") != expected_search_digest:
        raise ValueError("produced replay search digest differs from the frozen plan")
    search_configuration = adjudicator._object(
        document.get("search_configuration"), "produced replay search configuration"
    )
    if search_configuration != expected_search_configuration:
        raise ValueError("produced replay search configuration differs from frozen arguments")
    if canonical_digest(search_configuration) != expected_search_digest:
        raise ValueError("produced replay search configuration is internally inconsistent")

    replay_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = replay_path.with_name(f".{replay_path.name}.partial")
    if temporary_path.exists():
        raise ValueError(f"stale partial replay output requires review: {temporary_path}")
    try:
        with temporary_path.open("x", encoding="utf-8") as stream:
            stream.write(_render(document))
        digest = _file_digest(temporary_path)
        entry = adjudicator.EvidenceEntry(
            cluster_id="precommit-validation",
            member_id=member.member_id,
            pair_index=pair.pair_index,
            replay_path=temporary_path,
            replay_file_digest=digest,
        )
        adjudicator._classify_replay(
            entry,
            member,
            pair,
            controlled_study_family_digest,
        )
        temporary_path.replace(replay_path)
        return digest
    finally:
        temporary_path.unlink(missing_ok=True)


def _existing_replay_digest(
    *,
    replay_path: Path,
    member: adjudicator.MemberSpec,
    pair: adjudicator.PenaltyPair,
    expected_search_configuration: dict[str, Any],
    controlled_study_family_digest: str,
) -> str:
    document = _read_object(replay_path)
    if document.get("search_configuration") != expected_search_configuration:
        raise ValueError("existing replay search configuration differs from frozen arguments")
    digest = _file_digest(replay_path)
    entry = adjudicator.EvidenceEntry(
        cluster_id="resume-validation",
        member_id=member.member_id,
        pair_index=pair.pair_index,
        replay_path=replay_path,
        replay_file_digest=digest,
    )
    adjudicator._classify_replay(
        entry,
        member,
        pair,
        controlled_study_family_digest,
    )
    return digest


def _write_index(path: Path, document: dict[str, Any]) -> None:
    rendered = _render(document)
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise ValueError(f"existing evidence index differs from deterministic result: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(rendered)


def run_study_split(
    *,
    plan_path: Path,
    expected_plan_digest: str,
    split: Split,
    output_root: Path,
    lock_path: Path | None = None,
    expected_lock_digest: str | None = None,
    screen_function: ScreenFunction | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Run one authorized split and emit a complete adjudicator evidence index."""

    resolved_output_root = _refuse_output(output_root)
    plan_document = adjudicator._read_bound_object(plan_path, expected_plan_digest, "plan")
    resolved_plan_path = plan_path.resolve(strict=True)
    plan_digest = _file_digest(resolved_plan_path)
    plan = adjudicator.parse_plan(plan_document)
    pair_indices, lock_digest = _pair_indices_and_lock(
        split=split,
        plan=plan,
        plan_path=resolved_plan_path,
        plan_digest=plan_digest,
        lock_path=lock_path,
        expected_lock_digest=expected_lock_digest,
    )
    execution = _execution_inputs(plan_document)
    members = _preflight_members(
        plan_document=plan_document,
        plan=plan,
        split=split,
        pair_indices=pair_indices,
        execution=execution,
    )

    producer = (
        catalogue_screen.screen_raw_catalogue_window
        if screen_function is None
        else screen_function
    )
    index_path = resolved_output_root / f"{split}-evidence-index.json"
    entries: list[dict[str, Any]] = []
    for runnable in members:
        for pair_index in pair_indices:
            pair = plan.pairs[pair_index]
            replay_path = (
                resolved_output_root
                / split
                / f"cluster-{runnable.cluster_index:03d}"
                / f"member-{runnable.member_index:02d}"
                / f"pair-{pair_index:02d}.json"
            )
            if replay_path.exists():
                replay_digest = _existing_replay_digest(
                    replay_path=replay_path,
                    member=runnable.member,
                    pair=pair,
                    expected_search_configuration=(
                        runnable.expected_search_configurations[pair_index]
                    ),
                    controlled_study_family_digest=plan.controlled_study_family_digest,
                )
            else:
                pair_configuration = replace(
                    execution.raw_replay,
                    satellite_cost=pair.satellite_cost,
                    episode_cost=pair.episode_cost,
                )
                document = producer(
                    dataset=runnable.dataset,
                    dataset_path=runnable.dataset_path,
                    calibration_document=execution.calibration_document,
                    calibration_path=execution.calibration_path,
                    tle_path=execution.tle_path,
                    expected_tle_digest=execution.tle_digest,
                    start_s=execution.start_s,
                    end_s=execution.end_s,
                    observer=execution.observer,
                    config=pair_configuration,
                    screen_config=execution.catalogue_screen,
                )
                if not isinstance(document, dict):
                    raise ValueError("catalogue screen returned a non-object replay")
                replay_digest = _write_validated_replay(
                    replay_path=replay_path,
                    document=document,
                    member=runnable.member,
                    pair=pair,
                    expected_search_configuration=(
                        runnable.expected_search_configurations[pair_index]
                    ),
                    controlled_study_family_digest=plan.controlled_study_family_digest,
                )
            entries.append(
                {
                    "cluster_id": runnable.cluster_id,
                    "member_id": runnable.member.member_id,
                    "pair_index": pair_index,
                    "replay_path": str(replay_path.relative_to(index_path.parent)),
                    "replay_file_digest": replay_digest,
                }
            )

    index_document = {
        "schema": adjudicator.EVIDENCE_INDEX_SCHEMA,
        "study_id": plan.study_id,
        "plan_digest": plan_digest,
        "split": split,
        "lock_digest": lock_digest,
        "entries": entries,
    }
    _write_index(index_path, index_document)
    # Exercise the consumer parser now, including complete coverage and relative
    # path resolution, before reporting a usable index.
    adjudicator._parse_evidence_index(
        index_document,
        index_path=index_path,
        plan=plan,
        plan_digest=plan_digest,
        split=split,
        pair_indices=pair_indices,
        lock_digest=lock_digest,
    )
    return index_path, index_document


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--split", choices=("tuning", "holdout"), required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--lock-sha256")
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    index_path, index_document = run_study_split(
        plan_path=arguments.plan,
        expected_plan_digest=arguments.plan_sha256,
        split=arguments.split,
        output_root=arguments.output_root,
        lock_path=arguments.lock,
        expected_lock_digest=arguments.lock_sha256,
    )
    sys.stdout.write(
        _render(
            {
                "evidence_index_path": str(index_path),
                "evidence_index_digest": _file_digest(index_path),
                "split": index_document["split"],
                "entry_count": len(index_document["entries"]),
                "lock_digest": index_document["lock_digest"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
