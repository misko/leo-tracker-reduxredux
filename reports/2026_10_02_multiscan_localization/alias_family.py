"""Candidate-independent metadata grouping for edge/zero alias families."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections import defaultdict

from finite_set_likelihood import DEFAULT_ALIAS_HZ, _period_equivalent

REQUIRED_FIELDS = (
    "candidate_id",
    "probe_key",
    "residual_class",
    "tracking_cfo_hz",
    "fractional_epoch_samples",
    "fractional_margin",
    "candidate_rank",
)


def _circular_distance(left, right, period):
    return abs(float((left - right + 0.5 * period) % period - 0.5 * period))


def _stable_candidate_key(row):
    return (
        -float(row["fractional_margin"]),
        int(row["candidate_rank"]),
        str(row["candidate_id"]),
    )


def _family_id(candidate_ids):
    payload = json.dumps(sorted(candidate_ids), separators=(",", ":"))
    return "alias-family:sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _validate_rows(rows):
    normalized = []
    candidate_ids = set()
    for input_row_index, source in enumerate(rows):
        if not isinstance(source, dict):
            raise TypeError("each alias-family row must be a dictionary")
        missing = [field for field in REQUIRED_FIELDS if field not in source]
        if missing:
            raise ValueError(f"row {input_row_index} lacks fields: {', '.join(missing)}")
        row = copy.deepcopy(source)
        candidate_id = row["candidate_id"]
        if not isinstance(candidate_id, str) or not candidate_id:
            raise ValueError("candidate_id must be a nonempty string")
        if candidate_id in candidate_ids:
            raise ValueError(f"candidate_id is not unique: {candidate_id}")
        candidate_ids.add(candidate_id)
        probe_key = row["probe_key"]
        if not isinstance(probe_key, (list, tuple)) or not probe_key:
            raise ValueError("probe_key must be a nonempty list or tuple")
        row["probe_key"] = list(probe_key)
        if not isinstance(row["residual_class"], str) or not row["residual_class"]:
            raise ValueError("residual_class must be a nonempty string")
        for field in (
            "tracking_cfo_hz",
            "fractional_epoch_samples",
            "fractional_margin",
        ):
            if not isinstance(row[field], (int, float)) or not math.isfinite(row[field]):
                raise ValueError(f"{field} must be finite")
            row[field] = float(row[field])
        if not isinstance(row["candidate_rank"], int) or isinstance(
            row["candidate_rank"], bool
        ):
            raise ValueError("candidate_rank must be an integer")
        normalized.append(
            {
                "input_row_index": input_row_index,
                "row": row,
            }
        )
    json.dumps([item["row"] for item in normalized], sort_keys=True)
    return normalized


def _pair_compatible(left, right, *, alias_hz, frequency_tolerance_hz, frame_period_samples,
                     epoch_tolerance_samples):
    return (
        tuple(left["probe_key"]) == tuple(right["probe_key"])
        and _circular_distance(
            left["tracking_cfo_hz"], right["tracking_cfo_hz"], alias_hz
        )
        <= frequency_tolerance_hz
        and _circular_distance(
            left["fractional_epoch_samples"],
            right["fractional_epoch_samples"],
            frame_period_samples,
        )
        <= epoch_tolerance_samples
    )


def _zero_compatible(
    candidate,
    cluster,
    *,
    alias_hz,
    frame_period_samples,
    epoch_tolerance_samples,
):
    return all(
        _period_equivalent(
            candidate["row"]["tracking_cfo_hz"],
            member["row"]["tracking_cfo_hz"],
            alias_hz,
        )
        and _circular_distance(
            candidate["row"]["fractional_epoch_samples"],
            member["row"]["fractional_epoch_samples"],
            frame_period_samples,
        )
        <= epoch_tolerance_samples
        for member in cluster
    )


def _zero_anchor_clusters(
    zero_rows,
    *,
    alias_hz,
    frame_period_samples,
    epoch_tolerance_samples,
):
    clusters = []
    bridge_rows = []
    for candidate in sorted(zero_rows, key=lambda item: item["row"]["candidate_id"]):
        compatible = [
            cluster
            for cluster in clusters
            if _zero_compatible(
                candidate,
                cluster,
                alias_hz=alias_hz,
                frame_period_samples=frame_period_samples,
                epoch_tolerance_samples=epoch_tolerance_samples,
            )
        ]
        if len(compatible) == 1:
            compatible[0].append(candidate)
        else:
            clusters.append([candidate])
            if len(compatible) > 1:
                bridge_rows.append(candidate["row"]["candidate_id"])
    return clusters, bridge_rows


def _complete_link(rows, **compatibility_options):
    return all(
        _pair_compatible(left["row"], right["row"], **compatibility_options)
        for left_index, left in enumerate(rows)
        for right in rows[left_index + 1 :]
    )


def _family_record(kind, members, *, zero_members=(), edge_members=()):
    ordered_members = sorted(members, key=lambda item: item["row"]["candidate_id"])
    representative = min(ordered_members, key=lambda item: _stable_candidate_key(item["row"]))
    member_ids = [item["row"]["candidate_id"] for item in ordered_members]
    return {
        "family_id": _family_id(member_ids),
        "kind": kind,
        "probe_key": copy.deepcopy(representative["row"]["probe_key"]),
        "representative_candidate_id": representative["row"]["candidate_id"],
        "member_candidate_ids": member_ids,
        "zero_anchor_candidate_ids": sorted(
            item["row"]["candidate_id"] for item in zero_members
        ),
        "edge_candidate_ids": sorted(item["row"]["candidate_id"] for item in edge_members),
        "lineage": [
            {
                "candidate_id": item["row"]["candidate_id"],
                "input_row_index": item["input_row_index"],
            }
            for item in ordered_members
        ],
        "representative_selection": {
            "primary": "maximum persisted fractional_margin",
            "tie_breaks": ["minimum candidate_rank", "lexicographic candidate_id"],
            "scores_changed": False,
        },
        "representative_row": copy.deepcopy(representative["row"]),
    }


def group_alias_families(
    rows,
    *,
    frame_period_samples,
    alias_hz=DEFAULT_ALIAS_HZ,
    frequency_tolerance_hz=DEFAULT_ALIAS_HZ / 512,
    epoch_tolerance_samples=0.5,
):
    """Collapse unambiguous metadata-only edge/zero alias families.

    Every input candidate appears in exactly one output family. Exact full-alias
    zero duplicates form complete-link anchor clusters. Edge candidates join
    only one qualifying anchor cluster, and only when all edges assigned to that
    anchor form one complete-link family. Ambiguity is never tie-broken.
    """

    for value, name in (
        (frame_period_samples, "frame_period_samples"),
        (alias_hz, "alias_hz"),
        (frequency_tolerance_hz, "frequency_tolerance_hz"),
        (epoch_tolerance_samples, "epoch_tolerance_samples"),
    ):
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    if frame_period_samples <= 0 or alias_hz <= 0:
        raise ValueError("frame_period_samples and alias_hz must be positive")
    if frequency_tolerance_hz < 0 or frequency_tolerance_hz > alias_hz / 2:
        raise ValueError("frequency_tolerance_hz must lie in [0, alias_hz/2]")
    if epoch_tolerance_samples < 0 or epoch_tolerance_samples > frame_period_samples / 2:
        raise ValueError(
            "epoch_tolerance_samples must lie in [0, frame_period_samples/2]"
        )

    normalized = _validate_rows(rows)
    by_probe = defaultdict(list)
    for item in normalized:
        by_probe[tuple(item["row"]["probe_key"])].append(item)

    families = []
    ambiguous_edges = []
    unmatched_edges = []
    zero_bridge_rows = []
    compatibility_options = {
        "alias_hz": float(alias_hz),
        "frequency_tolerance_hz": float(frequency_tolerance_hz),
        "frame_period_samples": float(frame_period_samples),
        "epoch_tolerance_samples": float(epoch_tolerance_samples),
    }

    for probe_key in sorted(by_probe, key=lambda key: json.dumps(key, separators=(",", ":"))):
        probe_rows = by_probe[probe_key]
        zero_rows = [item for item in probe_rows if item["row"]["residual_class"] == "zero"]
        edge_rows = [item for item in probe_rows if item["row"]["residual_class"] == "edge"]
        passthrough = [
            item
            for item in probe_rows
            if item["row"]["residual_class"] not in ("zero", "edge")
        ]
        anchors, current_bridges = _zero_anchor_clusters(
            zero_rows,
            alias_hz=alias_hz,
            frame_period_samples=frame_period_samples,
            epoch_tolerance_samples=epoch_tolerance_samples,
        )
        zero_bridge_rows.extend(current_bridges)
        anchor_ids = [
            _family_id(item["row"]["candidate_id"] for item in anchor)
            for anchor in anchors
        ]
        assigned_edges = defaultdict(list)
        singleton_edges = []
        for edge in sorted(edge_rows, key=lambda item: item["row"]["candidate_id"]):
            qualifying = [
                index
                for index, anchor in enumerate(anchors)
                if all(
                    _pair_compatible(edge["row"], zero["row"], **compatibility_options)
                    for zero in anchor
                )
            ]
            if not qualifying:
                unmatched_edges.append(
                    {
                        "candidate_id": edge["row"]["candidate_id"],
                        "input_row_index": edge["input_row_index"],
                        "probe_key": copy.deepcopy(edge["row"]["probe_key"]),
                        "reason": "no_zero_anchor_cluster_passed_joint_frequency_epoch_gates",
                    }
                )
                singleton_edges.append((edge, "unmatched_edge"))
            elif len(qualifying) > 1:
                ambiguous_edges.append(
                    {
                        "candidate_id": edge["row"]["candidate_id"],
                        "input_row_index": edge["input_row_index"],
                        "probe_key": copy.deepcopy(edge["row"]["probe_key"]),
                        "reason": "multiple_distinct_zero_anchor_clusters_qualified",
                        "qualifying_zero_anchor_family_ids": [
                            anchor_ids[index] for index in qualifying
                        ],
                    }
                )
                singleton_edges.append((edge, "ambiguous_edge"))
            else:
                assigned_edges[qualifying[0]].append(edge)

        for anchor_index, anchor in enumerate(anchors):
            edges = assigned_edges[anchor_index]
            proposed = anchor + edges
            if edges and not _complete_link(proposed, **compatibility_options):
                for edge in edges:
                    ambiguous_edges.append(
                        {
                            "candidate_id": edge["row"]["candidate_id"],
                            "input_row_index": edge["input_row_index"],
                            "probe_key": copy.deepcopy(edge["row"]["probe_key"]),
                            "reason": "anchor_family_failed_complete_link",
                            "qualifying_zero_anchor_family_ids": [anchor_ids[anchor_index]],
                        }
                    )
                    singleton_edges.append((edge, "ambiguous_edge"))
                edges = []
            families.append(
                _family_record(
                    "zero_anchor_with_edges" if edges else "zero_anchor",
                    anchor + edges,
                    zero_members=anchor,
                    edge_members=edges,
                )
            )
        for edge, kind in singleton_edges:
            families.append(_family_record(kind, [edge], edge_members=[edge]))
        for item in passthrough:
            families.append(_family_record("passthrough", [item]))

    families.sort(key=lambda family: family["family_id"])
    representative_rows = [copy.deepcopy(family["representative_row"]) for family in families]
    ambiguous_edges.sort(key=lambda item: item["candidate_id"])
    unmatched_edges.sort(key=lambda item: item["candidate_id"])
    result = {
        "representative_rows": representative_rows,
        "families": families,
        "ambiguous_edges": ambiguous_edges,
        "unmatched_edges": unmatched_edges,
        "policy": {
            "schema": "candidate-independent-alias-family/v1",
            "alias_period_hz": float(alias_hz),
            "frequency_distance": "shortest circular distance under the full alias period",
            "frequency_tolerance_hz": float(frequency_tolerance_hz),
            "zero_anchor_frequency_equivalence": (
                "finite_set_likelihood._period_equivalent under the full alias period"
            ),
            "frame_period_samples": float(frame_period_samples),
            "epoch_tolerance_samples": float(epoch_tolerance_samples),
            "zero_anchor_rule": (
                "exact-frequency and epoch complete-link; bridge rows start new singleton anchors"
            ),
            "edge_rule": (
                "same probe; joint frequency/epoch gates to every zero anchor member; exactly one "
                "qualifying anchor; complete-link across the proposed family"
            ),
            "transitive_closure_used": False,
            "physical_ambiguity_tie_break_used": False,
            "representative_rule": (
                "maximum fractional_margin, then minimum candidate_rank, then candidate_id"
            ),
            "scores_changed": False,
            "other_residual_classes": "preserved as unchanged singleton representatives",
            "original_row_lineage_retained": True,
            "zero_bridge_candidate_ids": sorted(zero_bridge_rows),
            "input_row_count": len(normalized),
            "representative_row_count": len(representative_rows),
        },
    }
    json.dumps(result, sort_keys=True)
    return result


__all__ = ["group_alias_families"]
