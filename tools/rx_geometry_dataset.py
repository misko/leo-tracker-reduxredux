#!/usr/bin/env python3
"""Assemble unique exact-lane windows for receiver-geometry evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def _lane(row: dict[str, Any]) -> tuple[str, int, str, float]:
    return (
        str(row["session_id"]),
        int(row["channel"]),
        str(row["edge"]),
        float(row["actual_rf_hz"]),
    )


def _logsumexp(values: list[float]) -> float:
    peak = max(values)
    return peak + math.log(sum(math.exp(value - peak) for value in values))


def _finite(value: Any, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _index_unique(rows: list[dict[str, Any]], field: str, label: str) -> dict[str, dict[str, Any]]:
    result = {}
    for row in rows:
        key = row.get(field)
        if not isinstance(key, str):
            raise ValueError(f"{label} has invalid {field}")
        if key in result:
            raise ValueError(f"duplicate {label} {field}: {key}")
        result[key] = row
    return result


def _observation(
    candidate: dict[str, Any], receiver: int, scale: float, bias: float
) -> dict[str, Any]:
    raw = _finite(candidate.get("fractional_tracking_cfo_hz"), "candidate CFO")
    canonical = (raw - bias if receiver == 1 else raw) * scale
    return {
        "candidate_id": candidate.get("candidate_id"),
        "candidate_rank": candidate.get("candidate_rank"),
        "fractional_margin": candidate.get("fractional_margin"),
        "canonical_rx0_hz": canonical,
    }


def _passed_candidates(view: dict[str, Any]) -> list[dict[str, Any]] | None:
    passed = [
        item
        for item in view.get("candidates", [])
        if item.get("passed_fractional_margin_gate") is True
    ]
    identifiers = [item.get("candidate_id") for item in passed]
    if any(not isinstance(value, str) or not value for value in identifiers):
        return None
    if len(set(identifiers)) != len(identifiers):
        return None
    for item in passed:
        rank, margin, cfo = (
            item.get("candidate_rank"),
            item.get("fractional_margin"),
            item.get("fractional_tracking_cfo_hz"),
        )
        if (
            not isinstance(rank, int)
            or isinstance(rank, bool)
            or rank < 0
            or not isinstance(margin, (int, float))
            or not math.isfinite(float(margin))
            or float(margin) <= 0
            or not isinstance(cfo, (int, float))
            or not math.isfinite(float(cfo))
        ):
            return None
    return passed


def build_dataset(
    bank: dict[str, Any],
    mapping: dict[str, Any],
    partitions: dict[str, Any],
    opportunities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return one JSON-compatible record per eligible exact RF lane."""
    if bank.get("schema") != "rx-training-candidate-bank/v1" or bank.get("status") != "complete":
        raise ValueError("candidate bank is not complete v1 evidence")
    if (
        mapping.get("schema") != "rx-training-alias-mapping/v1"
        or mapping.get("status") != "complete"
    ):
        raise ValueError("alias mapping is not complete v1 evidence")
    if partitions.get("schema") != "rx-grouped-partition/v1":
        raise ValueError("unsupported grouped partition schema")

    partition_by_id = _index_unique(partitions.get("windows", []), "source_window_id", "partition")
    roles_by_group: dict[str, set[str]] = defaultdict(set)
    for row in partition_by_id.values():
        group_id = row.get("group_id")
        if not isinstance(group_id, str) or not group_id:
            raise ValueError("partition window has invalid group_id")
        roles_by_group[group_id].add(str(row.get("role")))
    if any(len(roles) != 1 for roles in roles_by_group.values()):
        raise ValueError("partition group spans roles")
    opportunity_by_id = _index_unique(opportunities, "source_window_id", "opportunity")
    split_by_session = {}
    rate_by_session = {}
    for row in partitions.get("recordings", []):
        sid = str(row["session_id"])
        if sid in split_by_session:
            raise ValueError(f"duplicate partition recording: {sid}")
        split = row.get("recording_split")
        if split not in {"calibration", "evaluation"}:
            raise ValueError(f"partition recording has invalid split: {sid}")
        split_by_session[sid] = split
        rate_by_session[sid] = int(row["sample_rate_hz"])

    bank_tracks = {}
    for track in bank.get("tracks", []):
        key = (str(track["session_id"]), str(track["track_id"]))
        if key in bank_tracks:
            raise ValueError(f"duplicate candidate-bank track: {key}")
        bank_tracks[key] = track

    calibrations = {}
    for row in mapping.get("receiver_calibrations", []):
        key = _lane(row)
        if key in calibrations:
            raise ValueError(f"duplicate receiver calibration lane: {key}")
        calibrations[key] = row

    mapped_by_lane: dict[tuple[str, int, str, float], list[dict[str, Any]]] = defaultdict(list)
    seen_tracks = set()
    for row in mapping.get("tracks", []):
        key = (str(row["session_id"]), str(row["track_id"]))
        if key in seen_tracks:
            raise ValueError(f"duplicate alias-mapping track: {key}")
        seen_tracks.add(key)
        if key not in bank_tracks:
            raise ValueError(f"mapped track absent from candidate bank: {key}")
        mapped_by_lane[_lane(row)].append(row)
    if seen_tracks != set(bank_tracks):
        raise ValueError("candidate bank and alias mapping track sets differ")

    lanes = []
    used_windows: set[str] = set()
    for lane_key in sorted(mapped_by_lane):
        session, channel, edge, rf = lane_key
        mapped_tracks = sorted(mapped_by_lane[lane_key], key=lambda row: str(row["track_id"]))
        calibration = calibrations.get(lane_key)
        exclusions: Counter[str] = Counter()
        scales = {_finite(row.get("canonical_scale"), "canonical scale") for row in mapped_tracks}
        periods = {
            _finite(row.get("normalized_alias_spacing_hz"), "normalized alias period")
            for row in mapped_tracks
        }
        if len(scales) != 1 or len(periods) != 1:
            raise ValueError(f"lane has inconsistent normalized coordinates: {lane_key}")
        scale, period = next(iter(scales)), next(iter(periods))

        prediction_sets = [
            {
                prediction["source_window_id"]
                for prediction in candidate.get("window_predictions", [])
            }
            for track in mapped_tracks
            for candidate in bank_tracks[(session, str(track["track_id"]))]["top_candidates"]
        ]
        if not prediction_sets:
            raise ValueError(f"lane has no candidate forecasts: {lane_key}")
        future_ids = prediction_sets[0]
        if any(values != future_ids for values in prediction_sets[1:]):
            raise ValueError(f"lane tracks have different future window sets: {lane_key}")
        if calibration is None or not calibration.get("qualified"):
            forecast_roles: Counter[str] = Counter()
            for window_id in future_ids:
                partition = partition_by_id.get(window_id)
                if partition is None or partition.get("role") not in {
                    "reception",
                    "held_frequency",
                }:
                    raise ValueError(f"forecast window absent or invalid in partition: {window_id}")
                forecast_roles[partition["role"]] += 1
            exclusions["unqualified_receiver_bias"] = len(future_ids)
            lanes.append(
                {
                    "lane": {
                        "session_id": session,
                        "channel": channel,
                        "edge": edge,
                        "actual_rf_hz": rf,
                    },
                    "recording_split": split_by_session.get(session),
                    "sample_rate_hz": rate_by_session.get(session),
                    "canonical_scale": scale,
                    "alias_period_hz": period,
                    "bias_rx1_minus_rx0_hz": None,
                    "components": [],
                    "retained_mass_rounding_corrections": [],
                    "windows": [],
                    "accounting": {
                        "forecast_windows_by_role": dict(sorted(forecast_roles.items())),
                        "windows_by_role": {},
                        "excluded_windows_by_role": dict(sorted(forecast_roles.items())),
                        "raw_candidates": {"rx0": 0, "rx1": 0},
                        "exclusions": dict(exclusions),
                    },
                }
            )
            continue
        bias = _finite(calibration.get("bias_rx1_minus_rx0_hz"), "receiver bias")
        candidate_tracks = []
        component_rows = []
        retained_mass_rounding_corrections = []
        track_log_prior = -math.log(len(mapped_tracks))
        other_terms = []
        for mapped in mapped_tracks:
            source = bank_tracks[(session, str(mapped["track_id"]))]
            original_retained = _finite(
                source["retained_catalogue_probability_mass"], "retained mass"
            )
            if original_retained < -1e-12 or original_retained > 1 + 1e-12:
                raise ValueError("retained mass must lie in [0, 1]")
            retained = min(1.0, max(0.0, original_retained))
            if retained != original_retained:
                retained_mass_rounding_corrections.append(
                    {
                        "track_id": str(mapped["track_id"]),
                        "original": original_retained,
                        "bounded": retained,
                    }
                )
            candidates = source.get("top_candidates", [])
            likelihoods = [
                _finite(row["training_log_likelihood"], "training log likelihood")
                for row in candidates
            ]
            if not likelihoods:
                raise ValueError("selected track has no candidates")
            normalizer = _logsumexp(likelihoods)
            predictions_by_candidate = []
            for candidate, likelihood in zip(candidates, likelihoods, strict=True):
                predictions = _index_unique(
                    candidate.get("window_predictions", []), "source_window_id", "prediction"
                )
                predictions_by_candidate.append(predictions)
                log_prior = (
                    None
                    if retained == 0
                    else track_log_prior + math.log(retained) + likelihood - normalizer
                )
                component_rows.append(
                    {
                        "kind": "track_candidate",
                        "track_id": str(mapped["track_id"]),
                        "catalog_number": candidate["catalog_number"],
                        "rank": candidate["rank"],
                        "training_log_likelihood": likelihood,
                        "log_prior": log_prior,
                    }
                )
            candidate_tracks.append((mapped, source, candidates, predictions_by_candidate))
            if retained < 1:
                other_terms.append(track_log_prior + math.log1p(-retained))
        component_rows.append(
            {"kind": "other", "log_prior": _logsumexp(other_terms) if other_terms else None}
        )

        windows = []
        role_counts: Counter[str] = Counter()
        excluded_role_counts: Counter[str] = Counter()
        forecast_role_counts: Counter[str] = Counter()
        raw_counts = {"rx0": 0, "rx1": 0}
        for window_id in sorted(
            future_ids,
            key=lambda value: (partition_by_id.get(value, {}).get("window_start_utc_ns", 0), value),
        ):
            partition = partition_by_id.get(window_id)
            opportunity = opportunity_by_id.get(window_id)
            if partition is None:
                raise ValueError(f"forecast window absent from partition: {window_id}")
            role = partition.get("role")
            if role not in {"reception", "held_frequency"}:
                raise ValueError(f"forecast window has invalid role: {window_id}")
            forecast_role_counts[role] += 1
            if opportunity is None:
                exclusions["missing_opportunity"] += 1
                excluded_role_counts[role] += 1
                continue
            source_window = opportunity.get("source_window", {})
            if (
                partition.get("session_id") != session
                or int(partition.get("channel", -1)) != channel
                or str(partition.get("edge")) != edge
                or partition.get("recording_split") != split_by_session.get(session)
                or source_window.get("session_id") != session
                or int(source_window.get("channel", -1)) != channel
                or str(source_window.get("edge")) != edge
                or opportunity.get("window_start_utc_ns") != partition.get("window_start_utc_ns")
                or opportunity.get("window_end_utc_ns") != partition.get("window_end_utc_ns")
            ):
                exclusions["identity_or_timestamp_mismatch"] += 1
                excluded_role_counts[role] += 1
                continue
            source_rate = source_window.get("sample_rate_hz")
            partition_rate = partition.get("sample_rate_hz", rate_by_session.get(session))
            if (
                not isinstance(source_rate, int)
                or source_rate != rate_by_session.get(session)
                or source_rate != partition_rate
            ):
                exclusions["sample_rate_mismatch"] += 1
                excluded_role_counts[role] += 1
                continue
            views = opportunity.get("receivers", {})
            if set(views) != {"rx0", "rx1"}:
                exclusions["malformed_receiver_views"] += 1
                excluded_role_counts[role] += 1
                continue
            if any(
                view.get("receiver_status")
                not in {"observed_candidate_present", "observed_candidate_absent"}
                or float(view.get("actual_rf_hz", math.nan)) != rf
                for view in views.values()
            ):
                exclusions["unqualified_or_lane_mismatch"] += 1
                excluded_role_counts[role] += 1
                continue
            passed_by_receiver = {
                receiver: _passed_candidates(views[f"rx{receiver}"]) for receiver in (0, 1)
            }
            if any(value is None for value in passed_by_receiver.values()):
                exclusions["malformed_passed_candidate"] += 1
                excluded_role_counts[role] += 1
                continue
            if window_id in used_windows:
                raise ValueError(f"source window appears in multiple lanes: {window_id}")

            predictions = []
            malformed = False
            for mapped, _source, candidates, prediction_indexes in candidate_tracks:
                anchor = int(mapped["receiver_id"])
                for candidate, prediction_index in zip(candidates, prediction_indexes, strict=True):
                    prediction = prediction_index.get(window_id)
                    if (
                        prediction is None
                        or prediction.get("role") != role
                        or prediction.get("prediction_utc_ns")
                        != partition.get("window_midpoint_utc_ns")
                    ):
                        malformed = True
                        break
                    mu = _finite(prediction["predicted_hz"], "prediction mean")
                    if anchor == 1:
                        mu -= bias * scale
                    elif anchor != 0:
                        malformed = True
                        break
                    predictions.append(
                        {
                            "track_id": str(mapped["track_id"]),
                            "catalog_number": candidate["catalog_number"],
                            "mu_canonical_rx0_hz": mu,
                            "elevation_deg": prediction["elevation_deg"],
                            "visible": bool(prediction["visible"]),
                            "los_enu_unit": dict(prediction["los_enu_unit"]),
                        }
                    )
                if malformed:
                    break
            if malformed:
                exclusions["malformed_prediction"] += 1
                excluded_role_counts[role] += 1
                continue
            observed = {}
            for receiver in (0, 1):
                passed = passed_by_receiver[receiver]
                assert passed is not None
                observed[f"rx{receiver}"] = [
                    _observation(item, receiver, scale, bias) for item in passed
                ]
                raw_counts[f"rx{receiver}"] += len(passed)
            used_windows.add(window_id)
            role_counts[role] += 1
            windows.append(
                {
                    "source_window_id": window_id,
                    "window_start_utc_ns": partition["window_start_utc_ns"],
                    "window_end_utc_ns": partition["window_end_utc_ns"],
                    "prediction_utc_ns": partition["window_midpoint_utc_ns"],
                    "group_id": partition["group_id"],
                    "role": role,
                    "sample_rate_hz": int(source_window["sample_rate_hz"]),
                    "observed": observed,
                    "predictions": predictions,
                }
            )
        lanes.append(
            {
                "lane": {
                    "session_id": session,
                    "channel": channel,
                    "edge": edge,
                    "actual_rf_hz": rf,
                },
                "recording_split": split_by_session.get(session),
                "sample_rate_hz": rate_by_session.get(session),
                "canonical_scale": scale,
                "alias_period_hz": period,
                "bias_rx1_minus_rx0_hz": bias,
                "components": component_rows,
                "retained_mass_rounding_corrections": retained_mass_rounding_corrections,
                "windows": windows,
                "accounting": {
                    "forecast_windows_by_role": dict(sorted(forecast_role_counts.items())),
                    "windows_by_role": dict(sorted(role_counts.items())),
                    "excluded_windows_by_role": dict(sorted(excluded_role_counts.items())),
                    "raw_candidates": raw_counts,
                    "exclusions": dict(sorted(exclusions.items())),
                },
            }
        )
    return lanes


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--partitions", type=Path, required=True)
    parser.add_argument("--opportunities", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = {
        name: getattr(args, name) for name in ("bank", "mapping", "partitions", "opportunities")
    }
    bank = json.loads(args.bank.read_text())
    mapping = json.loads(args.mapping.read_text())
    partitions = json.loads(args.partitions.read_text())
    if bank.get("source_digests", {}).get("partitions") != _digest(args.partitions):
        raise ValueError("candidate bank/partition hash binding mismatch")
    if mapping.get("source_digests", {}).get("candidate_bank") != _digest(args.bank):
        raise ValueError("alias mapping/candidate bank hash binding mismatch")
    if mapping.get("source_digests", {}).get("partitions") != _digest(args.partitions):
        raise ValueError("alias mapping/partition hash binding mismatch")
    lanes = build_dataset(bank, mapping, partitions, _read_jsonl(args.opportunities))
    document = {
        "schema": "rx-geometry-dataset/v1",
        "source_digests": {name: _digest(path) for name, path in paths.items()},
        "lanes": lanes,
        "accounting": {
            "lanes": len(lanes),
            "windows": sum(len(lane["windows"]) for lane in lanes),
        },
    }
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(document, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
