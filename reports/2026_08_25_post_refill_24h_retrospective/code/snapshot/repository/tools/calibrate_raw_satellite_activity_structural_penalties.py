#!/usr/bin/env python3
"""Lock and qualify raw satellite-activity structural penalties from JSON.

This is a deliberately offline research adjudicator.  ``lock`` chooses the
first explicitly ordered ``(satellite_cost, episode_cost)`` pair for which
every tuning cluster is conclusively null.  ``qualify`` then evaluates only
that locked pair on exactly 59 predeclared, source-disjoint holdout clusters.

A cluster is a false activation when any member contains a selected-catalogue
witness.  It is certified null only when every member carries the global
optimistic null certificate.  Everything else is inconclusive and therefore
cannot pass either stage.  Replay bytes, their complete search configuration,
their member evaluation scope, the configuration family with only the two
structural costs removed, and the common controlled-study settings are all
digest-bound. Qualification re-adjudicates the lock's tuning evidence before
opening holdout evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.raw_satellite_activity_search_configuration import (  # noqa: E402
    NULL_CERTIFICATE_ALGORITHM,
    controlled_study_configuration_family_digest,
)

PLAN_SCHEMA = "org.leo.research.raw-satellite-activity-structural-penalty-plan/v1"
EVIDENCE_INDEX_SCHEMA = (
    "org.leo.research.raw-satellite-activity-structural-penalty-evidence-index/v1"
)
LOCK_SCHEMA = "org.leo.research.raw-satellite-activity-structural-penalty-lock/v1"
QUALIFICATION_SCHEMA = "org.leo.research.raw-satellite-activity-structural-penalty-qualification/v1"
REPLAY_SCHEMA = "org.leo.research.raw-catalogue-satellite-activity-replay/v1"
ALGORITHM = "ordered-cluster-null-structural-penalty-calibration-v1"
SEARCH_FAMILY_ALGORITHM = "search-configuration-minus-structural-costs-v1"
INTERVAL_METHOD = "clopper-pearson-one-sided-exact"
REQUIRED_HOLDOUT_CLUSTER_COUNT = 59
REQUIRED_TUNING_CLUSTER_COUNT = 15
CONFIDENCE_LEVEL = 0.95
MAXIMUM_FALSE_ACTIVATION_RATE = 0.05
SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
QNAP_ROOT = Path("/mnt/qnap01")


@dataclass(frozen=True, slots=True)
class PenaltyPair:
    pair_index: int
    satellite_cost: float
    episode_cost: float

    def document(self) -> dict[str, Any]:
        return {
            "pair_index": self.pair_index,
            "satellite_cost": self.satellite_cost,
            "episode_cost": self.episode_cost,
        }


@dataclass(frozen=True, slots=True)
class MemberSpec:
    member_id: str
    duration_dataset_digest: str
    pilot_scan_digest: str
    member_evaluation_scope_digest: str
    search_configuration_family_digest: str
    search_configuration_digests: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClusterSpec:
    cluster_id: str
    source_provenance_ids: tuple[str, ...]
    members: tuple[MemberSpec, ...]


@dataclass(frozen=True, slots=True)
class StudyPlan:
    study_id: str
    controlled_study_family_digest: str
    pairs: tuple[PenaltyPair, ...]
    tuning_clusters: tuple[ClusterSpec, ...]
    holdout_clusters: tuple[ClusterSpec, ...]
    unused_clusters: tuple[ClusterSpec, ...]


@dataclass(frozen=True, slots=True)
class EvidenceEntry:
    cluster_id: str
    member_id: str
    pair_index: int
    replay_path: Path
    replay_file_digest: str


@dataclass(frozen=True, slots=True)
class MemberOutcome:
    status: Literal["activation", "certified_null", "inconclusive"]
    selected_catalog_numbers: tuple[int, ...]
    replay_file_digest: str
    search_configuration_digest: str


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _read_bound_object(path: Path, expected_digest: str, label: str) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    expected = _sha256(expected_digest, f"expected {label} digest")
    observed = _file_digest(resolved)
    if observed != expected:
        raise ValueError(f"{label} digest mismatch: expected {expected}, observed {observed}")
    return _read_object(resolved)


def _refuse_qnap_output(path: Path) -> None:
    resolved = path.resolve(strict=False)
    if resolved == QNAP_ROOT or QNAP_ROOT in resolved.parents:
        raise ValueError("this JSON-only research tool refuses output beneath /mnt/qnap01")


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


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _number(value: object, label: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    if nonnegative and result < 0.0:
        raise ValueError(f"{label} must be nonnegative")
    return result


def _sha256(value: object, label: str) -> str:
    result = _string(value, label)
    if SHA256_PATTERN.fullmatch(result) is None:
        raise ValueError(f"{label} must be a lowercase tagged SHA-256 digest")
    return result


def _parse_pair(value: object, expected_index: int) -> PenaltyPair:
    item = _object(value, f"penalty pair {expected_index}")
    pair_index = _integer(item.get("pair_index"), f"penalty pair {expected_index} index")
    if pair_index != expected_index:
        raise ValueError("penalty pairs must carry contiguous indices in declared order")
    return PenaltyPair(
        pair_index=pair_index,
        satellite_cost=_number(
            item.get("satellite_cost"),
            f"penalty pair {expected_index} satellite cost",
            nonnegative=True,
        ),
        episode_cost=_number(
            item.get("episode_cost"),
            f"penalty pair {expected_index} episode cost",
            nonnegative=True,
        ),
    )


def _parse_member(value: object, label: str, pair_count: int) -> MemberSpec:
    item = _object(value, label)
    digest_rows = _list(
        item.get("search_configuration_digests"), f"{label} search configuration digests"
    )
    if len(digest_rows) != pair_count:
        raise ValueError(f"{label} must predeclare one full search digest per penalty pair")
    full_digests: list[str] = []
    for expected_index, raw_row in enumerate(digest_rows):
        row = _object(raw_row, f"{label} search digest {expected_index}")
        observed_index = _integer(
            row.get("pair_index"), f"{label} search digest {expected_index} pair index"
        )
        if observed_index != expected_index:
            raise ValueError(f"{label} search digests must follow declared pair order")
        full_digests.append(_sha256(row.get("digest"), f"{label} search digest {expected_index}"))
    return MemberSpec(
        member_id=_string(item.get("member_id"), f"{label} member id"),
        duration_dataset_digest=_sha256(
            item.get("duration_dataset_digest"), f"{label} duration dataset digest"
        ),
        pilot_scan_digest=_sha256(item.get("pilot_scan_digest"), f"{label} pilot scan digest"),
        member_evaluation_scope_digest=_sha256(
            item.get("member_evaluation_scope_digest"),
            f"{label} member evaluation scope digest",
        ),
        search_configuration_family_digest=_sha256(
            item.get("search_configuration_family_digest"),
            f"{label} search configuration family digest",
        ),
        search_configuration_digests=tuple(full_digests),
    )


def _parse_clusters(value: object, split: str, pair_count: int) -> tuple[ClusterSpec, ...]:
    split_document = _object(value, f"{split} split")
    if split == "holdout" and split_document.get("predeclared") is not True:
        raise ValueError("holdout split must be explicitly marked predeclared")
    rows = _list(split_document.get("clusters"), f"{split} clusters")
    clusters: list[ClusterSpec] = []
    for cluster_index, raw_cluster in enumerate(rows):
        label = f"{split} cluster {cluster_index}"
        cluster = _object(raw_cluster, label)
        source_ids = tuple(
            _string(item, f"{label} source provenance id")
            for item in _list(cluster.get("source_provenance_ids"), f"{label} provenance")
        )
        if not source_ids or len(set(source_ids)) != len(source_ids):
            raise ValueError(f"{label} needs unique non-empty source provenance IDs")
        members = tuple(
            _parse_member(item, f"{label} member {member_index}", pair_count)
            for member_index, item in enumerate(_list(cluster.get("members"), f"{label} members"))
        )
        if not members:
            raise ValueError(f"{label} must contain at least one member")
        clusters.append(
            ClusterSpec(
                cluster_id=_string(cluster.get("cluster_id"), f"{label} cluster id"),
                source_provenance_ids=source_ids,
                members=members,
            )
        )
    return tuple(clusters)


def parse_plan(document: dict[str, Any]) -> StudyPlan:
    """Validate the immutable tuning/holdout predeclaration."""

    if document.get("schema") != PLAN_SCHEMA:
        raise ValueError(f"expected plan schema {PLAN_SCHEMA}")
    pairs = tuple(
        _parse_pair(item, index)
        for index, item in enumerate(
            _list(document.get("ordered_penalty_pairs"), "ordered penalty pairs")
        )
    )
    if not pairs:
        raise ValueError("at least one ordered penalty pair is required")
    if len({(item.satellite_cost, item.episode_cost) for item in pairs}) != len(pairs):
        raise ValueError("ordered penalty pairs must be unique")
    for previous, current in zip(pairs, pairs[1:], strict=False):
        if (
            current.satellite_cost < previous.satellite_cost
            or current.episode_cost < previous.episode_cost
        ):
            raise ValueError("ordered penalty pairs must be componentwise nondecreasing")

    qualification = _object(document.get("qualification"), "qualification")
    if (
        qualification.get("interval_method") != INTERVAL_METHOD
        or _integer(
            qualification.get("required_holdout_cluster_count"),
            "required holdout cluster count",
            minimum=1,
        )
        != REQUIRED_HOLDOUT_CLUSTER_COUNT
        or _number(qualification.get("confidence_level"), "confidence level") != CONFIDENCE_LEVEL
        or _number(
            qualification.get("maximum_false_activation_rate"),
            "maximum false activation rate",
            nonnegative=True,
        )
        != MAXIMUM_FALSE_ACTIVATION_RATE
    ):
        raise ValueError("qualification must use the fixed exact one-sided 95% 59-cluster gate")

    splits = _object(document.get("splits"), "splits")
    tuning = _parse_clusters(splits.get("tuning"), "tuning", len(pairs))
    holdout = _parse_clusters(splits.get("holdout"), "holdout", len(pairs))
    unused_value = splits.get("unused")
    unused = () if unused_value is None else _parse_clusters(unused_value, "unused", len(pairs))
    if len(tuning) != REQUIRED_TUNING_CLUSTER_COUNT:
        raise ValueError(
            f"tuning predeclaration must contain exactly {REQUIRED_TUNING_CLUSTER_COUNT} clusters"
        )
    if len(holdout) != REQUIRED_HOLDOUT_CLUSTER_COUNT:
        raise ValueError(
            f"holdout predeclaration must contain exactly {REQUIRED_HOLDOUT_CLUSTER_COUNT} clusters"
        )

    all_clusters = (*tuning, *holdout, *unused)
    cluster_ids = [item.cluster_id for item in all_clusters]
    if len(set(cluster_ids)) != len(cluster_ids):
        raise ValueError("cluster IDs must be unique across tuning and holdout")
    member_ids = [member.member_id for cluster in all_clusters for member in cluster.members]
    if len(set(member_ids)) != len(member_ids):
        raise ValueError("member IDs must be unique across tuning and holdout")

    provenance_owner: dict[tuple[str, str], str] = {}
    for cluster in all_clusters:
        provenance = [
            *(("declared_source", item) for item in cluster.source_provenance_ids),
            *(("duration_dataset", item.duration_dataset_digest) for item in cluster.members),
            *(("pilot_scan", item.pilot_scan_digest) for item in cluster.members),
            *(
                ("evaluation_scope", item.member_evaluation_scope_digest)
                for item in cluster.members
            ),
        ]
        for identity in provenance:
            prior = provenance_owner.get(identity)
            if prior is not None:
                raise ValueError(
                    "source provenance may belong to only one member/cluster/split: "
                    f"{identity[0]} {identity[1]}"
                )
            provenance_owner[identity] = cluster.cluster_id
    return StudyPlan(
        study_id=_string(document.get("study_id"), "study id"),
        controlled_study_family_digest=_sha256(
            document.get("controlled_study_family_digest"),
            "controlled study family digest",
        ),
        pairs=pairs,
        tuning_clusters=tuning,
        holdout_clusters=holdout,
        unused_clusters=unused,
    )


def search_configuration_family(search_configuration: dict[str, Any]) -> dict[str, Any]:
    """Remove exactly the two calibrated costs and retain every other search setting."""

    # JSON round-tripping gives a deep copy and rejects non-JSON values.
    copied = json.loads(json.dumps(search_configuration, allow_nan=False))
    if not isinstance(copied, dict):
        raise ValueError("search configuration must be an object")
    raw_replay = _object(copied.get("raw_replay"), "search configuration raw replay")
    for label in ("satellite_cost", "episode_cost"):
        if label not in raw_replay:
            raise ValueError(f"search configuration raw replay omits {label}")
        del raw_replay[label]
    return {
        "algorithm": SEARCH_FAMILY_ALGORITHM,
        "search_configuration_without_structural_costs": copied,
    }


def search_configuration_family_digest(search_configuration: dict[str, Any]) -> str:
    return canonical_digest(search_configuration_family(search_configuration))


def _parse_evidence_index(
    document: dict[str, Any],
    *,
    index_path: Path,
    plan: StudyPlan,
    plan_digest: str,
    split: Literal["tuning", "holdout"],
    pair_indices: tuple[int, ...],
    lock_digest: str | None,
) -> dict[tuple[str, str, int], EvidenceEntry]:
    if document.get("schema") != EVIDENCE_INDEX_SCHEMA:
        raise ValueError(f"expected evidence-index schema {EVIDENCE_INDEX_SCHEMA}")
    if document.get("study_id") != plan.study_id:
        raise ValueError("evidence index study ID does not match the plan")
    if document.get("plan_digest") != plan_digest:
        raise ValueError("evidence index is not bound to the supplied plan")
    if document.get("split") != split:
        raise ValueError(f"expected a {split} evidence index")
    if split == "tuning":
        if document.get("lock_digest") is not None:
            raise ValueError("tuning evidence must not be conditioned on a penalty lock")
    elif document.get("lock_digest") != lock_digest:
        raise ValueError("holdout evidence index is not bound to the supplied penalty lock")

    clusters = plan.tuning_clusters if split == "tuning" else plan.holdout_clusters
    expected = {
        (cluster.cluster_id, member.member_id, pair_index)
        for cluster in clusters
        for member in cluster.members
        for pair_index in pair_indices
    }
    entries: dict[tuple[str, str, int], EvidenceEntry] = {}
    for entry_index, raw_entry in enumerate(
        _list(document.get("entries"), f"{split} evidence entries")
    ):
        label = f"{split} evidence entry {entry_index}"
        item = _object(raw_entry, label)
        key = (
            _string(item.get("cluster_id"), f"{label} cluster id"),
            _string(item.get("member_id"), f"{label} member id"),
            _integer(item.get("pair_index"), f"{label} pair index"),
        )
        if key in entries:
            raise ValueError(f"duplicate evidence entry for {key}")
        raw_path = Path(_string(item.get("replay_path"), f"{label} replay path"))
        resolved_path = (
            raw_path if raw_path.is_absolute() else index_path.resolve().parent / raw_path
        ).resolve(strict=True)
        entries[key] = EvidenceEntry(
            cluster_id=key[0],
            member_id=key[1],
            pair_index=key[2],
            replay_path=resolved_path,
            replay_file_digest=_sha256(
                item.get("replay_file_digest"), f"{label} replay file digest"
            ),
        )
    missing = sorted(expected - entries.keys())
    extra = sorted(entries.keys() - expected)
    if missing or extra:
        raise ValueError(f"evidence coverage mismatch; missing={missing}, extra={extra}")
    return entries


def _member_lookup(clusters: tuple[ClusterSpec, ...]) -> dict[tuple[str, str], MemberSpec]:
    return {
        (cluster.cluster_id, member.member_id): member
        for cluster in clusters
        for member in cluster.members
    }


def _objective_triplet(value: object, label: str) -> tuple[float, float, float]:
    objective = _object(value, label)
    null_cost = _number(objective.get("null_cost"), f"{label} null cost")
    total_cost = _number(objective.get("total_cost"), f"{label} total cost")
    delta = _number(objective.get("delta_from_null"), f"{label} delta from null")
    if not math.isclose(delta, total_cost - null_cost, rel_tol=1e-12, abs_tol=1e-9):
        raise ValueError(f"{label} objective delta is inconsistent")
    return null_cost, total_cost, delta


def _validate_objective(
    decision: dict[str, Any], selected_count: int, label: str
) -> tuple[float, float, float]:
    objective = _object(
        decision.get("full_persisted_inventory_objective"), f"{label} persisted objective"
    )
    values = _objective_triplet(objective, f"{label} persisted objective")
    _number(
        objective.get("constant_elided_from_exact_decision_problem"),
        f"{label} elided objective constant",
        nonnegative=True,
    )
    delta = values[2]
    if selected_count > 0 and not delta < 0.0:
        raise ValueError(f"{label} selected activation does not beat the null")
    if selected_count == 0 and not math.isclose(delta, 0.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError(f"{label} empty selection has a nonzero decision delta")
    return values


def _require_matching_objective(
    value: object,
    expected: tuple[float, float, float],
    label: str,
) -> None:
    observed = _objective_triplet(value, label)
    if any(
        not math.isclose(first, second, rel_tol=1e-12, abs_tol=1e-9)
        for first, second in zip(observed, expected, strict=True)
    ):
        raise ValueError(f"{label} disagrees with the decision objective")


def _require_modeled_objective(
    value: object,
    expected: tuple[float, float, float],
    elided_constant: float,
    label: str,
) -> None:
    observed = _objective_triplet(value, label)
    restored = (observed[0] + elided_constant, observed[1] + elided_constant, observed[2])
    if any(
        not math.isclose(first, second, rel_tol=1e-12, abs_tol=1e-9)
        for first, second in zip(restored, expected, strict=True)
    ):
        raise ValueError(f"{label} disagrees with the full persisted objective")


def _catalog_numbers(value: object, label: str) -> tuple[int, ...]:
    selected = tuple(
        _integer(item, f"{label} catalog number", minimum=1)
        for item in _list(value, f"{label} catalog numbers")
    )
    if len(set(selected)) != len(selected):
        raise ValueError(f"{label} catalogue identities are not unique")
    return selected


def _branch_elided_clutter_constant(
    raw_inventory: dict[str, Any],
    *,
    result_kind: str,
    label: str,
) -> float:
    """Read the producer's branch-specific persisted objective constant."""

    top_level_key = "omitted_clutter_objective_constant"
    nested_key = "dominated_weak_candidate_elision"
    top_level_present = top_level_key in raw_inventory
    nested_value = raw_inventory.get(nested_key)
    nested_present = isinstance(nested_value, dict) and top_level_key in nested_value
    if result_kind == "catalogue_screened_grouped_activity":
        if top_level_present or not nested_present:
            raise ValueError(
                f"{label} catalogue-screen raw objective constant must appear only in "
                f"{nested_key}.{top_level_key}"
            )
        nested = _object(nested_value, f"{label} dominated weak candidate elision")
        return _number(
            nested.get(top_level_key),
            f"{label} omitted clutter objective constant",
            nonnegative=True,
        )
    if result_kind == "certified_null":
        if not top_level_present or nested_present:
            raise ValueError(
                f"{label} certified-null raw objective constant must appear only at "
                f"raw_inventory.{top_level_key}"
            )
        return _number(
            raw_inventory.get(top_level_key),
            f"{label} omitted clutter objective constant",
            nonnegative=True,
        )
    raise ValueError(f"{label} has an unknown decision result kind")


def _classify_replay(
    entry: EvidenceEntry,
    member: MemberSpec,
    pair: PenaltyPair,
    controlled_study_family_digest: str,
) -> MemberOutcome:
    observed_file_digest = _file_digest(entry.replay_path)
    if observed_file_digest != entry.replay_file_digest:
        raise ValueError(f"replay file digest mismatch: {entry.replay_path}")
    document = _read_object(entry.replay_path)
    label = f"replay {entry.replay_path}"
    if document.get("schema") != REPLAY_SCHEMA:
        raise ValueError(f"{label} has the wrong schema")
    for flag, expected in (
        ("candidate_only", True),
        ("specificity_claimed", False),
        ("payload_decoded", False),
        ("structural_costs_calibrated", False),
        ("unknown_satellite_count_solved", False),
        ("global_optimum_claimed", False),
    ):
        if _boolean(document.get(flag), f"{label} {flag}") is not expected:
            raise ValueError(f"{label} carries an incompatible {flag} claim")
    raw_inventory = _object(document.get("raw_inventory"), f"{label} raw inventory")
    if (
        raw_inventory.get("declared_post_acquisition_inventory_complete") is not True
        or _integer(
            raw_inventory.get("truncated_candidate_count"),
            f"{label} truncated candidate count",
        )
        != 0
    ):
        raise ValueError(f"{label} does not contain a complete retained raw inventory")
    inputs = _object(document.get("input"), f"{label} inputs")
    if (
        _sha256(inputs.get("duration_dataset_digest"), f"{label} duration digest")
        != member.duration_dataset_digest
        or _sha256(inputs.get("pilot_scan_digest"), f"{label} pilot digest")
        != member.pilot_scan_digest
    ):
        raise ValueError(f"{label} source provenance does not match the predeclaration")

    search_configuration = _object(
        document.get("search_configuration"), f"{label} search configuration"
    )
    observed_search_digest = _sha256(
        document.get("search_configuration_digest"), f"{label} search configuration digest"
    )
    recomputed_search_digest = canonical_digest(search_configuration)
    if observed_search_digest != recomputed_search_digest:
        raise ValueError(f"{label} search configuration digest is internally inconsistent")
    if observed_search_digest != member.search_configuration_digests[pair.pair_index]:
        raise ValueError(f"{label} full search configuration was not predeclared for this pair")
    family_digest = search_configuration_family_digest(search_configuration)
    if family_digest != member.search_configuration_family_digest:
        raise ValueError(f"{label} search configuration family mismatch")
    scope_digest = _sha256(
        search_configuration.get("member_evaluation_scope_digest"),
        f"{label} member evaluation scope digest",
    )
    if scope_digest != member.member_evaluation_scope_digest:
        raise ValueError(f"{label} member evaluation scope mismatch")
    controlled_digest = controlled_study_configuration_family_digest(search_configuration)
    if controlled_digest != controlled_study_family_digest:
        raise ValueError(f"{label} controlled study search family mismatch")
    null_certificate_algorithm = _string(
        search_configuration.get("null_certificate_algorithm"),
        f"{label} null certificate algorithm",
    )
    if null_certificate_algorithm != NULL_CERTIFICATE_ALGORITHM:
        raise ValueError(f"{label} search configuration has an unknown null certificate algorithm")
    raw_replay = _object(
        search_configuration.get("raw_replay"), f"{label} search raw replay configuration"
    )
    if (
        _number(raw_replay.get("satellite_cost"), f"{label} satellite cost", nonnegative=True)
        != pair.satellite_cost
        or _number(raw_replay.get("episode_cost"), f"{label} episode cost", nonnegative=True)
        != pair.episode_cost
    ):
        raise ValueError(f"{label} structural costs do not match the declared pair")
    if document.get("configuration") != raw_replay:
        raise ValueError(f"{label} top-level and search-bound replay configurations differ")

    decision = _object(document.get("decision"), f"{label} decision")
    selected = _catalog_numbers(decision.get("selected_catalog_numbers"), f"{label} selected")
    selected_count = _integer(
        decision.get("selected_satellite_count"), f"{label} selected satellite count"
    )
    if selected_count != len(selected):
        raise ValueError(f"{label} selected satellite count is inconsistent")
    objective = _validate_objective(decision, selected_count, label)
    persisted_objective = _object(
        decision.get("full_persisted_inventory_objective"),
        f"{label} persisted objective",
    )
    decision_elided_constant = _number(
        persisted_objective.get("constant_elided_from_exact_decision_problem"),
        f"{label} decision elided objective constant",
        nonnegative=True,
    )
    solved = _boolean(
        document.get("null_vs_any_activation_solved"), f"{label} null-vs-activation flag"
    )
    search_performed = _boolean(
        document.get("catalogue_search_performed"), f"{label} catalogue-search-performed flag"
    )
    search_avoided = _boolean(
        document.get("catalogue_search_avoided_by_global_null_certificate"),
        f"{label} catalogue-search-avoided flag",
    )
    search_exact = _boolean(
        document.get("catalogue_search_exact"), f"{label} catalogue-search-exact flag"
    )
    if search_exact or search_performed == search_avoided:
        raise ValueError(f"{label} catalogue search flags are internally inconsistent")

    result_kind = _string(decision.get("result_kind"), f"{label} result kind")
    raw_elided_constant = _branch_elided_clutter_constant(
        raw_inventory,
        result_kind=result_kind,
        label=label,
    )
    if not math.isclose(
        decision_elided_constant,
        raw_elided_constant,
        rel_tol=1e-12,
        abs_tol=1e-9,
    ):
        raise ValueError(f"{label} raw-inventory and decision objective constants differ")
    certificate_value = document.get("null_certificate")
    if result_kind == "catalogue_screened_grouped_activity":
        if not search_performed or search_avoided:
            raise ValueError(f"{label} catalogue-screen result has contradictory search flags")
        association = _object(document.get("association"), f"{label} association")
        decoded = _object(association.get("association"), f"{label} decoded association")
        association_selected = _catalog_numbers(
            decoded.get("selected_catalog_numbers"), f"{label} association selected"
        )
        if association_selected != selected:
            raise ValueError(f"{label} decision and association selections differ")
        _require_modeled_objective(
            decoded.get("objective"),
            objective,
            raw_elided_constant,
            f"{label} association objective",
        )
        if document.get("full_persisted_inventory_objective") != persisted_objective:
            raise ValueError(f"{label} top-level and decision persisted objectives differ")
        _require_matching_objective(
            document.get("full_persisted_inventory_objective"),
            objective,
            f"{label} top-level persisted objective",
        )
        if certificate_value is not None:
            raise ValueError(f"{label} catalogue-screen result must not carry a null certificate")
        joint_search = _object(document.get("joint_search"), f"{label} joint search")
        joint_selected = _catalog_numbers(
            joint_search.get("selected_catalog_numbers"), f"{label} joint-search selected"
        )
        if joint_selected != selected:
            raise ValueError(f"{label} decision and joint-search selections differ")
        if selected and not solved:
            raise ValueError(f"{label} selected witness is not marked null-vs-activation solved")
        if not selected and solved:
            raise ValueError(f"{label} empty pruned search cannot certify the global null")
        status: Literal["activation", "inconclusive"] = "activation" if selected else "inconclusive"
        return MemberOutcome(
            status=status,
            selected_catalog_numbers=selected,
            replay_file_digest=observed_file_digest,
            search_configuration_digest=observed_search_digest,
        )
    if selected or search_performed or not search_avoided:
        raise ValueError(f"{label} certified-null result has contradictory search/selection claims")
    association = _object(document.get("association"), f"{label} null association")
    association_selected = _catalog_numbers(
        association.get("selected_catalog_numbers"), f"{label} null association selected"
    )
    association_count = _integer(
        association.get("selected_satellite_count"),
        f"{label} null association selected satellite count",
    )
    if association_selected or association_count != 0:
        raise ValueError(f"{label} null association contains a selected catalogue")
    _require_matching_objective(
        association.get("objective"), objective, f"{label} null association objective"
    )
    if document.get("full_persisted_inventory_objective") is not None:
        raise ValueError(f"{label} certified-null branch has a top-level replay objective")
    if not isinstance(certificate_value, dict):
        raise ValueError(f"{label} claims a certified null without its certificate")
    certificate = certificate_value
    certificate_algorithm = _string(certificate.get("algorithm"), f"{label} certificate algorithm")
    modeled_null_cost = _number(certificate.get("modeled_null_cost"), f"{label} modeled null cost")
    if (
        certificate_algorithm != null_certificate_algorithm
        or not _boolean(certificate.get("certified"), f"{label} certificate flag")
        or not solved
        or certificate.get("optimistic_selected") is not False
        or _number(
            certificate.get("optimistic_delta_from_null"),
            f"{label} optimistic delta",
        )
        != 0.0
        or _integer(certificate.get("active_cell_count"), f"{label} active cell count") != 0
        or _integer(certificate.get("episode_count"), f"{label} episode count") != 0
        or _integer(certificate.get("assignment_count"), f"{label} assignment count") != 0
        or not math.isclose(
            modeled_null_cost + decision_elided_constant,
            objective[0],
            rel_tol=1e-12,
            abs_tol=1e-9,
        )
    ):
        raise ValueError(f"{label} global null certificate is internally inconsistent")
    return MemberOutcome(
        status="certified_null",
        selected_catalog_numbers=(),
        replay_file_digest=observed_file_digest,
        search_configuration_digest=observed_search_digest,
    )


def _cluster_evaluation(
    cluster: ClusterSpec,
    pair: PenaltyPair,
    entries: dict[tuple[str, str, int], EvidenceEntry],
    controlled_study_family_digest: str,
) -> dict[str, Any]:
    outcomes = [
        (
            member,
            _classify_replay(
                entries[(cluster.cluster_id, member.member_id, pair.pair_index)],
                member,
                pair,
                controlled_study_family_digest,
            ),
        )
        for member in cluster.members
    ]
    statuses = [outcome.status for _, outcome in outcomes]
    if "activation" in statuses:
        status = "false_activation"
    elif all(item == "certified_null" for item in statuses):
        status = "certified_null"
    else:
        status = "inconclusive"
    return {
        "cluster_id": cluster.cluster_id,
        "status": status,
        "member_count": len(cluster.members),
        "any_member_activated": "activation" in statuses,
        "all_members_certified_null": all(item == "certified_null" for item in statuses),
        "members": [
            {
                "member_id": member.member_id,
                "status": outcome.status,
                "selected_catalog_numbers": list(outcome.selected_catalog_numbers),
                "replay_file_digest": outcome.replay_file_digest,
                "search_configuration_digest": outcome.search_configuration_digest,
            }
            for member, outcome in outcomes
        ],
    }


def _counts(cluster_rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "cluster_count": len(cluster_rows),
        "false_activation_count": sum(
            item["status"] == "false_activation" for item in cluster_rows
        ),
        "certified_null_count": sum(item["status"] == "certified_null" for item in cluster_rows),
        "inconclusive_count": sum(item["status"] == "inconclusive" for item in cluster_rows),
    }


def exact_one_sided_binomial_upper(
    false_activation_count: int,
    cluster_count: int,
    *,
    alpha: float = 1.0 - CONFIDENCE_LEVEL,
) -> float:
    """Return the exact one-sided Clopper--Pearson binomial upper limit."""

    if (
        isinstance(false_activation_count, bool)
        or isinstance(cluster_count, bool)
        or not isinstance(false_activation_count, int)
        or not isinstance(cluster_count, int)
        or cluster_count < 1
        or false_activation_count < 0
        or false_activation_count > cluster_count
    ):
        raise ValueError("binomial counts must satisfy 0 <= false activations <= clusters")
    if not math.isfinite(alpha) or not 0.0 < alpha < 1.0:
        raise ValueError("binomial alpha must lie strictly between zero and one")
    if false_activation_count == cluster_count:
        return 1.0
    if false_activation_count == 0:
        return 1.0 - alpha ** (1.0 / cluster_count)

    def lower_tail(probability: float) -> float:
        complement = 1.0 - probability
        return sum(
            math.comb(cluster_count, index)
            * probability**index
            * complement ** (cluster_count - index)
            for index in range(false_activation_count + 1)
        )

    lower = 0.0
    upper = 1.0
    for _ in range(200):
        midpoint = (lower + upper) / 2.0
        if lower_tail(midpoint) > alpha:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2.0


def lock_penalty_pair(
    *,
    plan_path: Path,
    expected_plan_digest: str,
    evidence_index_path: Path,
    expected_evidence_index_digest: str,
) -> dict[str, Any]:
    """Choose the first all-certified-null pair from tuning evidence only."""

    plan_document = _read_bound_object(plan_path, expected_plan_digest, "plan")
    plan = parse_plan(plan_document)
    plan_digest = _file_digest(plan_path.resolve(strict=True))
    index_document = _read_bound_object(
        evidence_index_path, expected_evidence_index_digest, "tuning evidence index"
    )
    index_digest = _file_digest(evidence_index_path.resolve(strict=True))
    entries = _parse_evidence_index(
        index_document,
        index_path=evidence_index_path,
        plan=plan,
        plan_digest=plan_digest,
        split="tuning",
        pair_indices=tuple(item.pair_index for item in plan.pairs),
        lock_digest=None,
    )

    evaluations: list[dict[str, Any]] = []
    for pair in plan.pairs:
        cluster_rows = [
            _cluster_evaluation(
                cluster,
                pair,
                entries,
                plan.controlled_study_family_digest,
            )
            for cluster in plan.tuning_clusters
        ]
        counts = _counts(cluster_rows)
        evaluations.append(
            {
                "penalty_pair": pair.document(),
                "eligible_for_lock": (
                    counts["false_activation_count"] == 0 and counts["inconclusive_count"] == 0
                ),
                "cluster_accounting": counts,
                "clusters": cluster_rows,
            }
        )
    locked_index = next(
        (index for index, evaluation in enumerate(evaluations) if evaluation["eligible_for_lock"]),
        None,
    )
    locked_pair = None if locked_index is None else plan.pairs[locked_index]
    return {
        "schema": LOCK_SCHEMA,
        "algorithm": ALGORITHM,
        "study_id": plan.study_id,
        "inputs": {
            "plan_path": str(plan_path.resolve(strict=True)),
            "plan_digest": plan_digest,
            "tuning_evidence_index_path": str(evidence_index_path.resolve(strict=True)),
            "tuning_evidence_index_digest": index_digest,
        },
        "ordered_penalty_pairs": [item.document() for item in plan.pairs],
        "selection_rule": (
            "first declared pair with zero false-activation clusters and zero "
            "inconclusive clusters; a cluster activates if any member activates and is "
            "null only if every member is globally certified null"
        ),
        "holdout_evidence_inspected": False,
        "predeclared_split_accounting": {
            "tuning_cluster_count": len(plan.tuning_clusters),
            "holdout_cluster_count": len(plan.holdout_clusters),
            "unused_cluster_count": len(plan.unused_clusters),
        },
        "candidate_evaluations": evaluations,
        "decision": {
            "locked": locked_pair is not None,
            "locked_pair_index": None if locked_pair is None else locked_pair.pair_index,
            "locked_penalty_pair": None if locked_pair is None else locked_pair.document(),
            "reason": (
                "first_ordered_pair_passing_complete_tuning_null_gate"
                if locked_pair is not None
                else "no_ordered_pair_passed_complete_tuning_null_gate"
            ),
        },
        "caveats": [
            "tuning clusters are empirical analyzer-null controls, not known satellite absence",
            "the plan predeclaration is digest-bound but not externally time-attested",
            "the replay null proof remains conditional on its bounded retained candidate inventory",
        ],
    }


def _validate_lock(document: dict[str, Any], plan: StudyPlan, plan_digest: str) -> PenaltyPair:
    if document.get("schema") != LOCK_SCHEMA or document.get("algorithm") != ALGORITHM:
        raise ValueError("supplied lock is not a structural-penalty lock V1")
    if document.get("study_id") != plan.study_id:
        raise ValueError("lock study ID does not match the plan")
    inputs = _object(document.get("inputs"), "lock inputs")
    if inputs.get("plan_digest") != plan_digest:
        raise ValueError("lock is not bound to the supplied plan")
    if document.get("ordered_penalty_pairs") != [item.document() for item in plan.pairs]:
        raise ValueError("lock ordered penalty pairs differ from the plan")
    if document.get("holdout_evidence_inspected") is not False:
        raise ValueError("penalty lock must attest that it did not inspect holdout evidence")
    decision = _object(document.get("decision"), "lock decision")
    if decision.get("locked") is not True:
        raise ValueError("cannot qualify because no structural penalty pair was locked")
    pair_index = _integer(decision.get("locked_pair_index"), "locked pair index")
    if pair_index >= len(plan.pairs):
        raise ValueError("locked pair index is outside the plan")
    pair = plan.pairs[pair_index]
    if decision.get("locked_penalty_pair") != pair.document():
        raise ValueError("locked penalty pair is inconsistent with its index")
    evaluations = _list(document.get("candidate_evaluations"), "lock candidate evaluations")
    if len(evaluations) != len(plan.pairs):
        raise ValueError("lock must retain one tuning evaluation per declared pair")
    eligible_indices: list[int] = []
    expected_cluster_ids = [item.cluster_id for item in plan.tuning_clusters]
    for index, (raw_evaluation, declared_pair) in enumerate(
        zip(evaluations, plan.pairs, strict=True)
    ):
        evaluation = _object(raw_evaluation, f"lock evaluation {index}")
        if evaluation.get("penalty_pair") != declared_pair.document():
            raise ValueError("lock evaluation penalty pair differs from the plan")
        accounting = _object(
            evaluation.get("cluster_accounting"), f"lock evaluation {index} accounting"
        )
        cluster_count = _integer(
            accounting.get("cluster_count"), f"lock evaluation {index} cluster count"
        )
        false_count = _integer(
            accounting.get("false_activation_count"),
            f"lock evaluation {index} false activation count",
        )
        null_count = _integer(
            accounting.get("certified_null_count"),
            f"lock evaluation {index} certified null count",
        )
        inconclusive_count = _integer(
            accounting.get("inconclusive_count"),
            f"lock evaluation {index} inconclusive count",
        )
        if (
            cluster_count != len(plan.tuning_clusters)
            or false_count + null_count + inconclusive_count != cluster_count
        ):
            raise ValueError("lock tuning cluster accounting is inconsistent")
        clusters = _list(evaluation.get("clusters"), f"lock evaluation {index} clusters")
        if [item.get("cluster_id") if isinstance(item, dict) else None for item in clusters] != (
            expected_cluster_ids
        ):
            raise ValueError("lock tuning cluster identities differ from the plan")
        eligible = _boolean(
            evaluation.get("eligible_for_lock"), f"lock evaluation {index} eligibility"
        )
        if eligible != (false_count == 0 and inconclusive_count == 0):
            raise ValueError("lock eligibility is inconsistent with cluster accounting")
        if eligible:
            eligible_indices.append(index)
    if not eligible_indices or pair_index != eligible_indices[0]:
        raise ValueError("lock did not select the first eligible ordered pair")
    return pair


def _recompute_lock(
    document: dict[str, Any],
    *,
    plan_path: Path,
    plan_digest: str,
    lock_path: Path,
) -> None:
    """Re-open tuning evidence and require the supplied lock to be canonical."""

    inputs = _object(document.get("inputs"), "lock inputs")
    raw_plan_path = Path(_string(inputs.get("plan_path"), "lock-bound plan path"))
    bound_plan_path = (
        raw_plan_path
        if raw_plan_path.is_absolute()
        else lock_path.resolve(strict=True).parent / raw_plan_path
    ).resolve(strict=True)
    if bound_plan_path != plan_path.resolve(strict=True):
        raise ValueError("lock-bound plan path differs from the supplied plan")

    raw_index_path = Path(
        _string(inputs.get("tuning_evidence_index_path"), "lock-bound tuning evidence path")
    )
    index_path = (
        raw_index_path
        if raw_index_path.is_absolute()
        else lock_path.resolve(strict=True).parent / raw_index_path
    ).resolve(strict=True)
    index_digest = _sha256(
        inputs.get("tuning_evidence_index_digest"),
        "lock-bound tuning evidence index digest",
    )
    canonical_lock = lock_penalty_pair(
        plan_path=bound_plan_path,
        expected_plan_digest=plan_digest,
        evidence_index_path=index_path,
        expected_evidence_index_digest=index_digest,
    )
    if canonical_lock != document:
        raise ValueError("supplied lock differs from canonical tuning-evidence adjudication")


def qualify_locked_penalty(
    *,
    plan_path: Path,
    expected_plan_digest: str,
    lock_path: Path,
    expected_lock_digest: str,
    evidence_index_path: Path,
    expected_evidence_index_digest: str,
) -> dict[str, Any]:
    """Qualify one immutable lock on exactly 59 predeclared holdout clusters."""

    plan_document = _read_bound_object(plan_path, expected_plan_digest, "plan")
    plan = parse_plan(plan_document)
    plan_digest = _file_digest(plan_path.resolve(strict=True))
    lock_document = _read_bound_object(lock_path, expected_lock_digest, "penalty lock")
    lock_digest = _file_digest(lock_path.resolve(strict=True))
    pair = _validate_lock(lock_document, plan, plan_digest)
    _recompute_lock(
        lock_document,
        plan_path=plan_path,
        plan_digest=plan_digest,
        lock_path=lock_path,
    )
    index_document = _read_bound_object(
        evidence_index_path, expected_evidence_index_digest, "holdout evidence index"
    )
    index_digest = _file_digest(evidence_index_path.resolve(strict=True))
    entries = _parse_evidence_index(
        index_document,
        index_path=evidence_index_path,
        plan=plan,
        plan_digest=plan_digest,
        split="holdout",
        pair_indices=(pair.pair_index,),
        lock_digest=lock_digest,
    )
    cluster_rows = [
        _cluster_evaluation(
            cluster,
            pair,
            entries,
            plan.controlled_study_family_digest,
        )
        for cluster in plan.holdout_clusters
    ]
    counts = _counts(cluster_rows)
    complete = counts["inconclusive_count"] == 0
    best_case_upper = exact_one_sided_binomial_upper(
        counts["false_activation_count"],
        counts["cluster_count"],
    )
    failure_is_certain = best_case_upper > MAXIMUM_FALSE_ACTIVATION_RATE
    upper = best_case_upper if complete else None
    gate_passed = complete and not failure_is_certain
    if failure_is_certain:
        status = "failed_false_activation_rate_gate"
    elif gate_passed:
        status = "qualified"
    elif not complete:
        status = "inconclusive"
    else:
        status = "failed_false_activation_rate_gate"
    return {
        "schema": QUALIFICATION_SCHEMA,
        "algorithm": ALGORITHM,
        "study_id": plan.study_id,
        "inputs": {
            "plan_path": str(plan_path.resolve(strict=True)),
            "plan_digest": plan_digest,
            "lock_path": str(lock_path.resolve(strict=True)),
            "lock_digest": lock_digest,
            "holdout_evidence_index_path": str(evidence_index_path.resolve(strict=True)),
            "holdout_evidence_index_digest": index_digest,
        },
        "locked_penalty_pair": pair.document(),
        "holdout_pair_indices_inspected": [pair.pair_index],
        "holdout_cluster_accounting": counts,
        "clusters": cluster_rows,
        "false_activation_rate_gate": {
            "interval_method": INTERVAL_METHOD,
            "confidence_level": CONFIDENCE_LEVEL,
            "alpha": 1.0 - CONFIDENCE_LEVEL,
            "maximum_false_activation_rate": MAXIMUM_FALSE_ACTIVATION_RATE,
            "observed_false_activation_rate": (
                counts["false_activation_count"] / counts["cluster_count"] if complete else None
            ),
            "exact_one_sided_upper_bound": upper,
            "best_case_exact_one_sided_upper_bound": best_case_upper,
            "failure_certain_under_best_case": failure_is_certain,
            "passed": gate_passed,
            "requires_every_cluster_conclusive": True,
        },
        "decision": {
            "status": status,
            "qualified": status == "qualified",
            "structural_costs_calibrated_for_declared_empirical_null_scope": (
                status == "qualified"
            ),
        },
        "caveats": [
            "holdout clusters are empirical analyzer-null controls, not known satellite absence",
            "the exact binomial interval assumes exchangeable independent cluster outcomes",
            "qualification applies only to the digest-bound search families and source scope",
            "the plan predeclaration is digest-bound but not externally time-attested",
            "the replay null proof remains conditional on its bounded retained candidate inventory",
        ],
    }


def _write(document: dict[str, Any], output: Path | None) -> None:
    rendered = json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if output is None:
        sys.stdout.write(rendered)
        return
    _refuse_qnap_output(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)

    lock = subparsers.add_parser("lock", help="lock the first tuning-qualified pair")
    lock.add_argument("--plan", type=Path, required=True)
    lock.add_argument("--plan-sha256", required=True)
    lock.add_argument("--evidence-index", type=Path, required=True)
    lock.add_argument("--evidence-index-sha256", required=True)
    lock.add_argument("--output", type=Path)

    qualify = subparsers.add_parser("qualify", help="qualify one immutable lock on holdout")
    qualify.add_argument("--plan", type=Path, required=True)
    qualify.add_argument("--plan-sha256", required=True)
    qualify.add_argument("--lock", type=Path, required=True)
    qualify.add_argument("--lock-sha256", required=True)
    qualify.add_argument("--evidence-index", type=Path, required=True)
    qualify.add_argument("--evidence-index-sha256", required=True)
    qualify.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    if arguments.operation == "lock":
        document = lock_penalty_pair(
            plan_path=arguments.plan,
            expected_plan_digest=arguments.plan_sha256,
            evidence_index_path=arguments.evidence_index,
            expected_evidence_index_digest=arguments.evidence_index_sha256,
        )
    else:
        document = qualify_locked_penalty(
            plan_path=arguments.plan,
            expected_plan_digest=arguments.plan_sha256,
            lock_path=arguments.lock,
            expected_lock_digest=arguments.lock_sha256,
            evidence_index_path=arguments.evidence_index,
            expected_evidence_index_digest=arguments.evidence_index_sha256,
        )
    _write(document, arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
