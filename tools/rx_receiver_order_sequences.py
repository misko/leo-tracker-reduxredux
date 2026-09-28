#!/usr/bin/env python3
"""Build candidate-consistent dual-receiver proxy sequences from frozen inputs.

The candidate bank and receiver mapping are training-only authorities.  This
stage consumes recorded later opportunities without selecting an integer CFO
alias, changing a candidate weight, or interpreting a match as identification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

CANONICAL_GATE_HZ = 2_500.0
ROLES = ("reception", "held_frequency")
VALID_VIEW_STATUSES = {"observed_candidate_present", "observed_candidate_absent"}


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _finite(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("boolean is not a finite frequency")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("frequency must be finite")
    return result


def circular_residual_hz(observed_hz: float, expected_hz: float, period_hz: float) -> float:
    """Return a signed modulo residual without selecting an integer alias."""
    observed, expected, period = map(_finite, (observed_hz, expected_hz, period_hz))
    if period <= 0:
        raise ValueError("alias period must be positive")
    return (observed - expected + period / 2.0) % period - period / 2.0


def anchor_equivalent_native_hz(
    raw_hz: float, receiver_id: int, anchor_receiver_id: int, bias_rx1_minus_rx0_hz: float
) -> float:
    """Transfer a raw CFO into the anchor receiver coordinate with fixed sign."""
    raw, bias = _finite(raw_hz), _finite(bias_rx1_minus_rx0_hz)
    if receiver_id == anchor_receiver_id:
        return raw
    if (receiver_id, anchor_receiver_id) == (1, 0):
        return raw - bias
    if (receiver_id, anchor_receiver_id) == (0, 1):
        return raw + bias
    raise ValueError("only receivers 0 and 1 are supported")


def _index_unique(
    rows: Iterable[dict[str, Any]], keys: tuple[str, ...], label: str
) -> dict[tuple[Any, ...], dict[str, Any]]:
    result = {}
    for row in rows:
        key = tuple(row.get(name) for name in keys)
        if key in result:
            raise ValueError(f"duplicate {label}: {key}")
        result[key] = row
    return result


def _receiver_views(row: dict[str, Any]) -> dict[int, dict[str, Any]]:
    views = row.get("receivers")
    if not isinstance(views, dict):
        return {}
    result = {}
    for name, view in views.items():
        if not isinstance(view, dict):
            continue
        rid = view.get("receiver_id")
        if rid is None and name in {"rx0", "rx1"}:
            rid = int(name[-1])
        if rid in (0, 1) and rid not in result:
            result[int(rid)] = view
    return result


def _hypotheses(
    bank: dict[str, Any], mappings: dict[tuple[str, str], dict[str, Any]]
) -> list[dict[str, Any]]:
    result = []
    for track in bank.get("tracks", []):
        key = (str(track.get("session_id")), str(track.get("track_id")))
        mapping = mappings.get(key)
        if mapping is None:
            raise ValueError(f"candidate-bank track lacks frozen mapping: {key}")
        for candidate in track.get("top_candidates", []):
            predictions = _index_unique(
                candidate.get("window_predictions", []), ("source_window_id",), "prediction window"
            )
            result.append(
                {
                    "hypothesis_id": f"{key[0]}/{key[1]}/{int(candidate['catalog_number'])}",
                    "session_id": key[0],
                    "track_id": key[1],
                    "catalog_number": int(candidate["catalog_number"]),
                    "rank": int(candidate["rank"]),
                    "conditional_top3_probability": _finite(
                        candidate["conditional_top3_probability"]
                    ),
                    "retained_catalogue_probability_mass": _finite(
                        track["retained_catalogue_probability_mass"]
                    ),
                    "mapping": mapping,
                    "predictions": predictions,
                }
            )
    ids = [row["hypothesis_id"] for row in result]
    if len(ids) != len(set(ids)):
        raise ValueError("frozen hypothesis identity is duplicated")
    return result


def _lane_state(
    opportunity: dict[str, Any], hypothesis: dict[str, Any], calibration: dict[str, Any] | None
) -> tuple[str, str | None]:
    mapping = hypothesis["mapping"]
    source = opportunity.get("source_window", {})
    if (source.get("session_id"), source.get("channel"), str(source.get("edge"))) != (
        mapping["session_id"],
        mapping["channel"],
        str(mapping["edge"]),
    ):
        return "out_of_scope", "lane_mismatch"
    views = _receiver_views(opportunity)
    if set(views) != {0, 1}:
        return "missing_or_invalid", "receiver_probe_incomplete"
    expected_rf = _finite(mapping["actual_rf_hz"])
    try:
        rf_values = {_finite(views[rid].get("actual_rf_hz")) for rid in (0, 1)}
    except (TypeError, ValueError):
        return "missing_or_invalid", "missing_actual_rf_hz"
    if rf_values != {expected_rf}:
        return "out_of_scope", "actual_rf_mismatch"
    if (
        opportunity.get("window_start_utc_ns") is None
        or opportunity.get("window_end_utc_ns") is None
    ):
        return "missing_or_invalid", "timestamp_unavailable"
    if any(views[rid].get("receiver_status") not in VALID_VIEW_STATUSES for rid in (0, 1)):
        return "missing_or_invalid", "receiver_unqualified"
    if calibration is None or calibration.get("qualified") is not True:
        return "missing_or_invalid", "unsupported_receiver_calibration"
    return "eligible", None


def _candidate_matches(
    view: dict[str, Any],
    receiver_id: int,
    hypothesis: dict[str, Any],
    calibration: dict[str, Any],
    expected_hz: float,
) -> tuple[list[dict[str, Any]], bool]:
    mapping = hypothesis["mapping"]
    scale = _finite(mapping["canonical_scale"])
    period = _finite(mapping["normalized_alias_spacing_hz"])
    bias = _finite(calibration["bias_rx1_minus_rx0_hz"])
    malformed = False
    matches = []
    for raw in view.get("candidates", []):
        if raw.get("passed_fractional_margin_gate") is not True:
            continue
        try:
            candidate_id = str(raw["candidate_id"])
            native = _finite(raw["fractional_tracking_cfo_hz"])
            rank = int(raw["candidate_rank"])
            margin = _finite(raw["fractional_margin"])
            if not candidate_id:
                raise ValueError("empty candidate ID")
        except (KeyError, TypeError, ValueError, OverflowError):
            malformed = True
            continue
        anchor_native = anchor_equivalent_native_hz(
            native, receiver_id, int(mapping["receiver_id"]), bias
        )
        canonical = anchor_native * scale
        residual = circular_residual_hz(canonical, expected_hz, period)
        if abs(residual) <= CANONICAL_GATE_HZ:
            matches.append(
                {
                    "candidate_id": candidate_id,
                    "detector_rank": rank,
                    "detector_margin": margin,
                    "raw_native_cfo_hz": native,
                    "anchor_equivalent_canonical_hz": canonical,
                    "residual_hz": residual,
                    "match_class": "alias_equivalent",
                    "alias_period_hz": period,
                    "compatible_aliases": "unresolved_integer_class",
                }
            )
    matches.sort(key=lambda row: (row["candidate_id"], row["detector_rank"]))
    return matches, malformed


def classify_opportunities(
    bank: dict[str, Any],
    mapping: dict[str, Any],
    partitions: dict[str, Any],
    opportunities: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return hypothesis/receiver rows and hypotheses, with global collisions resolved."""
    if bank.get("schema") != "rx-training-candidate-bank/v1" or bank.get("status") != "complete":
        raise ValueError("candidate bank must be complete v1 evidence")
    if (
        mapping.get("schema") != "rx-training-alias-mapping/v1"
        or mapping.get("status") != "complete"
    ):
        raise ValueError("receiver mapping must be complete v1 evidence")
    if partitions.get("schema") != "rx-grouped-partition/v1":
        raise ValueError("grouped partitions must be v1 evidence")
    map_index = _index_unique(mapping.get("tracks", []), ("session_id", "track_id"), "mapped track")
    hypotheses = _hypotheses(bank, map_index)
    part_index = _index_unique(
        partitions.get("windows", []), ("source_window_id",), "partition window"
    )
    opportunity_index = _index_unique(opportunities, ("source_window_id",), "opportunity window")
    calibrations = _index_unique(
        mapping.get("receiver_calibrations", []),
        ("session_id", "channel", "edge", "actual_rf_hz"),
        "receiver calibration",
    )
    rows = []
    collision: dict[tuple[str, int, str], set[str]] = defaultdict(set)
    for hyp in hypotheses:
        lane = hyp["mapping"]
        cal = calibrations.get(
            (lane["session_id"], lane["channel"], lane["edge"], lane["actual_rf_hz"])
        )
        for (window_id,), prediction in sorted(hyp["predictions"].items()):
            role = prediction.get("role")
            if role not in ROLES:
                continue
            partition = part_index.get((window_id,))
            opportunity = opportunity_index.get((window_id,))
            base = {
                key: hyp[key]
                for key in (
                    "hypothesis_id",
                    "session_id",
                    "track_id",
                    "catalog_number",
                    "rank",
                    "conditional_top3_probability",
                )
            }
            base.update(
                {
                    "source_window_id": window_id,
                    "role": role,
                    "prediction_utc_ns": prediction.get("prediction_utc_ns"),
                    "window_start_utc_ns": prediction.get("window_start_utc_ns"),
                    "window_end_utc_ns": prediction.get("window_end_utc_ns"),
                    "visible": bool(prediction.get("visible")),
                    "expected_canonical_hz": _finite(prediction["predicted_hz"]),
                }
            )
            timing_consistent = (
                partition is not None
                and opportunity is not None
                and partition.get("role") == role
                and prediction.get("window_start_utc_ns") == partition.get("window_start_utc_ns")
                and prediction.get("window_end_utc_ns") == partition.get("window_end_utc_ns")
                and prediction.get("prediction_utc_ns") == partition.get("window_midpoint_utc_ns")
                and opportunity.get("window_start_utc_ns") == partition.get("window_start_utc_ns")
                and opportunity.get("window_end_utc_ns") == partition.get("window_end_utc_ns")
            )
            if not timing_consistent:
                for rid in (0, 1):
                    rows.append(
                        {
                            **base,
                            "receiver_id": rid,
                            "status": "missing_or_invalid",
                            "exclusion_reason": "missing_or_inconsistent_partition_or_opportunity",
                            "matches": [],
                        }
                    )
                continue
            if not base["visible"]:
                for rid in (0, 1):
                    rows.append(
                        {
                            **base,
                            "receiver_id": rid,
                            "status": "out_of_scope",
                            "exclusion_reason": "forecast_not_visible",
                            "matches": [],
                        }
                    )
                continue
            state, reason = _lane_state(opportunity, hyp, cal)
            if state != "eligible":
                for rid in (0, 1):
                    rows.append(
                        {
                            **base,
                            "receiver_id": rid,
                            "status": state,
                            "exclusion_reason": reason,
                            "matches": [],
                        }
                    )
                continue
            views = _receiver_views(opportunity)
            for rid in (0, 1):
                matches, malformed = _candidate_matches(
                    views[rid], rid, hyp, cal, base["expected_canonical_hz"]
                )
                status = "missing_or_invalid" if malformed else "pending"
                reason = "malformed_passing_candidate" if malformed else None
                row = {
                    **base,
                    "receiver_id": rid,
                    "status": status,
                    "exclusion_reason": reason,
                    "matches": matches,
                }
                rows.append(row)
                if not malformed:
                    for match in matches:
                        collision[(window_id, rid, match["candidate_id"])].add(hyp["hypothesis_id"])
    for row in rows:
        if row["status"] != "pending":
            continue
        collided = sorted(
            {
                hid
                for match in row["matches"]
                for hid in collision[
                    (row["source_window_id"], row["receiver_id"], match["candidate_id"])
                ]
                if hid != row["hypothesis_id"]
            }
        )
        row["colliding_hypothesis_ids"] = collided
        if collided:
            row["status"] = "ambiguous_hypothesis"
        elif len(row["matches"]) > 1:
            row["status"] = "ambiguous_candidate"
        elif len(row["matches"]) == 1:
            row["status"] = "unique_hit"
        else:
            row["status"] = "no_matching_candidate"
    return rows, hypotheses


def _receiver_endpoint(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: (row["prediction_utc_ns"], row["source_window_id"]))
    eligible = [
        row for row in ordered if row["status"] not in {"out_of_scope", "missing_or_invalid"}
    ]
    hits = [row for row in eligible if row["status"] == "unique_hit"]
    if not eligible:
        return {
            "censoring": "unavailable",
            "first_hit_window_id": None,
            "first_hit_utc_ns": None,
            "earlier_ambiguous_or_missing": False,
        }
    if not hits:
        return {
            "censoring": "right",
            "first_hit_window_id": None,
            "first_hit_utc_ns": None,
            "earlier_ambiguous_or_missing": any(
                row["status"]
                in {"missing_or_invalid", "ambiguous_candidate", "ambiguous_hypothesis"}
                for row in ordered
            ),
        }
    first = hits[0]
    prior_all = ordered[: ordered.index(first)]
    earlier_problem = any(
        row["status"] in {"missing_or_invalid", "ambiguous_candidate", "ambiguous_hypothesis"}
        for row in prior_all
    )
    censoring = (
        "earlier_ambiguity" if earlier_problem else "left" if first is eligible[0] else "observed"
    )
    return {
        "censoring": censoring,
        "first_hit_window_id": first["source_window_id"],
        "first_hit_utc_ns": first["prediction_utc_ns"],
        "earlier_ambiguous_or_missing": earlier_problem,
    }


def build_sequences(
    rows: list[dict[str, Any]], hypotheses: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["hypothesis_id"], row["role"])].append(row)
    output = []
    for hyp in hypotheses:
        for role in ROLES:
            selected = grouped.get((hyp["hypothesis_id"], role), [])
            endpoint = {
                rid: _receiver_endpoint([row for row in selected if row["receiver_id"] == rid])
                for rid in (0, 1)
            }
            left, right = endpoint[0], endpoint[1]
            tied = (
                left["first_hit_window_id"] is not None
                and left["first_hit_window_id"] == right["first_hit_window_id"]
            )
            lag = None
            direction = None
            if left["censoring"] == right["censoring"] == "observed" and not tied:
                lag = (right["first_hit_utc_ns"] - left["first_hit_utc_ns"]) / 1e9
                direction = "rx0_then_rx1" if lag > 0 else "rx1_then_rx0"
            counts = Counter(row["status"] for row in selected)
            output.append(
                {
                    "hypothesis_id": hyp["hypothesis_id"],
                    "session_id": hyp["session_id"],
                    "track_id": hyp["track_id"],
                    "catalog_number": hyp["catalog_number"],
                    "candidate_rank": hyp["rank"],
                    "conditional_top3_probability": hyp["conditional_top3_probability"],
                    "role": role,
                    "endpoint_name": "first candidate-consistent detector hit",
                    "receivers": {"rx0": left, "rx1": right},
                    "same_window_tie": tied,
                    "uncensored_lag_rx1_minus_rx0_s": lag,
                    "recorded_proxy_order": direction,
                    "opportunity_status_counts": dict(sorted(counts.items())),
                    "opportunity_row_count": len(selected),
                }
            )
    return output


def make_document(
    bank: dict[str, Any],
    mapping: dict[str, Any],
    partitions: dict[str, Any],
    opportunities: list[dict[str, Any]],
    source_digests: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    mapping_sources = mapping.get("source_digests", {})
    bank_sources = bank.get("source_digests", {})
    bindings = (
        (mapping_sources.get("candidate_bank"), source_digests["candidate_bank"], "mapping/bank"),
        (mapping_sources.get("partitions"), source_digests["partitions"], "mapping/partitions"),
        (bank_sources.get("partitions"), source_digests["partitions"], "bank/partitions"),
    )
    for declared, actual, label in bindings:
        if declared != actual:
            raise ValueError(f"{label} digest binding mismatch")
    rows, hypotheses = classify_opportunities(bank, mapping, partitions, opportunities)
    sequences = build_sequences(rows, hypotheses)
    statuses = Counter(row["status"] for row in rows)
    exclusions = Counter(
        row["exclusion_reason"] for row in rows if row.get("exclusion_reason") is not None
    )
    by_role = {
        role: dict(sorted(Counter(row["status"] for row in rows if row["role"] == role).items()))
        for role in ROLES
    }
    return (
        {
            "schema": "rx-receiver-order-proxy-sequences/v1",
            "status": "complete",
            "source_digests": source_digests,
            "matching_contract": {
                "canonical_gate_hz": CANONICAL_GATE_HZ,
                "alias_rule": "fixed-period circular residual; integer alias unresolved",
                "collision_scope": (
                    "global frozen hypotheses per source_window/receiver/raw_candidate"
                ),
                "candidate_weights_updated": False,
                "endpoint": "first candidate-consistent detector hit",
            },
            "accounting": {
                "frozen_hypotheses": len(hypotheses),
                "opportunity_rows": len(rows),
                "status_counts": dict(sorted(statuses.items())),
                "status_counts_by_role": by_role,
                "exclusion_reason_counts": dict(sorted(exclusions.items())),
                "sequences": len(sequences),
                "input_opportunities": len(opportunities),
                "accounted_rows_equal_status_sum": len(rows) == sum(statuses.values()),
            },
            "sequences": sequences,
            "interpretation": (
                "Recorded candidate-consistent proxy feasibility only; no new model, "
                "satellite identification, physical arrival order, or held-residual "
                "performance claim."
            ),
        },
        rows,
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-bank", required=True, type=Path)
    parser.add_argument("--rx-alias-mapping", required=True, type=Path)
    parser.add_argument("--partitions", required=True, type=Path)
    parser.add_argument("--opportunities", required=True, type=Path)
    parser.add_argument("--output-summary", required=True, type=Path)
    parser.add_argument("--output-opportunities", required=True, type=Path)
    args = parser.parse_args()
    for output in (args.output_summary, args.output_opportunities):
        if output.exists():
            raise FileExistsError(f"output already exists: {output}")
    inputs = {
        "candidate_bank": args.candidate_bank,
        "rx_alias_mapping": args.rx_alias_mapping,
        "partitions": args.partitions,
        "opportunities": args.opportunities,
    }
    payloads = {name: path.read_bytes() for name, path in inputs.items()}
    bank, mapping, partitions = (
        json.loads(payloads[name]) for name in ("candidate_bank", "rx_alias_mapping", "partitions")
    )
    opportunities = _read_jsonl(args.opportunities)
    document, rows = make_document(
        bank,
        mapping,
        partitions,
        opportunities,
        {name: digest(payload) for name, payload in payloads.items()},
    )
    args.output_opportunities.write_text(
        "".join(json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    args.output_summary.write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(digest(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()))


if __name__ == "__main__":
    main()
