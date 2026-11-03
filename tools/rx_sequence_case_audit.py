#!/usr/bin/env python3
"""Descriptively audit the 17 dual-hit receiver-order sequences.

This consumes frozen matching output.  It does not rematch candidates, tune a
gate, or turn candidate consistency into an identity claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ELIGIBLE = {
    "unique_hit",
    "no_matching_candidate",
    "ambiguous_candidate",
    "ambiguous_hypothesis",
    "missing_or_invalid",
}
EPOCH_PERIOD_NS = 1_000_000_000 / 750
EPOCH_GATE_NS = 2_200


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open() as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _candidate_index(
    opportunities: Iterable[dict[str, Any]],
) -> dict[tuple[str, int, str], dict[str, Any]]:
    result = {}
    windows = set()
    for opportunity in opportunities:
        wid = opportunity["source_window_id"]
        if wid in windows:
            raise ValueError(f"duplicate raw opportunity window: {wid}")
        windows.add(wid)
        for name, view in opportunity.get("receivers", {}).items():
            rid = int(view.get("receiver_id", name[-1]))
            for candidate in view.get("candidates", []):
                key = (wid, rid, str(candidate.get("candidate_id")))
                if key in result:
                    raise ValueError(f"duplicate raw candidate join key: {key}")
                result[key] = candidate
    return result


def _runs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs, current = [], []
    for row in rows:
        if row["status"] == "unique_hit":
            current.append(row)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return [
        {
            "start_utc_ns": r[0]["prediction_utc_ns"],
            "end_utc_ns": r[-1]["prediction_utc_ns"],
            "window_count": len(r),
            "window_ids": [x["source_window_id"] for x in r],
        }
        for r in runs
    ]


def _interval(rows: list[dict[str, Any]]) -> dict[str, Any]:
    hit_index = next((i for i, row in enumerate(rows) if row["status"] == "unique_hit"), None)
    if hit_index is None:
        return {"valid": False, "reason": "no_unique_hit"}
    if hit_index == 0:
        return {"valid": False, "reason": "no_preceding_eligible_observation"}
    earlier_bad = [
        row["status"]
        for row in rows[:hit_index]
        if row["status"] in {"ambiguous_candidate", "ambiguous_hypothesis", "missing_or_invalid"}
    ]
    if earlier_bad:
        return {
            "valid": False,
            "reason": "earlier_eligible_observation_is_ambiguous_or_invalid",
            "earlier_invalidating_statuses": earlier_bad,
        }
    previous = rows[hit_index - 1]
    if previous["status"] != "no_matching_candidate":
        return {
            "valid": False,
            "reason": "preceding_eligible_observation_is_ambiguous_or_invalid",
            "preceding_status": previous["status"],
        }
    return {
        "valid": True,
        "lower_exclusive_utc_ns": previous["prediction_utc_ns"],
        "upper_inclusive_utc_ns": rows[hit_index]["prediction_utc_ns"],
        "width_s": (rows[hit_index]["prediction_utc_ns"] - previous["prediction_utc_ns"]) / 1e9,
    }


def build_audit(
    sequences: dict[str, Any],
    matched: Iterable[dict[str, Any]],
    opportunities: Iterable[dict[str, Any]],
    source_digests: dict[str, str] | None = None,
) -> dict[str, Any]:
    selected = [
        s
        for s in sequences["sequences"]
        if all(s["receivers"][rx].get("first_hit_utc_ns") is not None for rx in ("rx0", "rx1"))
    ]
    keys = {(s["hypothesis_id"], s["role"]) for s in selected}
    grouped = {key: [] for key in keys}
    matched_keys = set()
    for row in matched:
        key = (row["hypothesis_id"], row["role"])
        if key in grouped and row["status"] in ELIGIBLE:
            row_key = (*key, row["source_window_id"], row["receiver_id"])
            if row_key in matched_keys:
                raise ValueError(f"duplicate matched opportunity key: {row_key}")
            matched_keys.add(row_key)
            grouped[key].append(row)
    candidates = _candidate_index(opportunities)
    cases = []
    for sequence in selected:
        rows = grouped[(sequence["hypothesis_id"], sequence["role"])]
        by_rx = {}
        for rid in (0, 1):
            ordered = sorted(
                (r for r in rows if r["receiver_id"] == rid),
                key=lambda r: (r["prediction_utc_ns"], r["source_window_id"]),
            )
            exported = []
            for row in ordered:
                matches = []
                for match in row.get("matches", []):
                    join_key = (row["source_window_id"], rid, match["candidate_id"])
                    if join_key not in candidates:
                        raise ValueError(f"matched candidate lacks raw opportunity row: {join_key}")
                    raw = candidates[join_key]
                    matches.append(
                        {
                            **match,
                            "fractional_exact_score": raw.get("fractional_exact_score"),
                            "fractional_control_score": raw.get("fractional_control_score"),
                            "fractional_margin": raw.get("fractional_margin"),
                            "fractional_epoch_offset_samples": raw.get(
                                "fractional_epoch_offset_samples"
                            ),
                            "integer_epoch_sample": raw.get("integer_epoch_sample"),
                            "support_center_utc_ns": (raw.get("source_interval") or {}).get(
                                "support_center_utc_ns"
                            ),
                            "source_interval": raw.get("source_interval"),
                        }
                    )
                exported.append(
                    {
                        "source_window_id": row["source_window_id"],
                        "prediction_utc_ns": row["prediction_utc_ns"],
                        "window_start_utc_ns": row.get("window_start_utc_ns"),
                        "window_end_utc_ns": row.get("window_end_utc_ns"),
                        "status": row["status"],
                        "matches": matches,
                    }
                )
            times = [r["prediction_utc_ns"] for r in ordered]
            gaps = [(b - a) / 1e9 for a, b in zip(times, times[1:], strict=False)]
            by_rx[f"rx{rid}"] = {
                "eligible_observations": exported,
                "status_counts": dict(sorted(Counter(r["status"] for r in ordered).items())),
                "cadence_gaps_s": gaps,
                "unique_hit_runs": _runs(ordered),
                "first_hit_interval": _interval(ordered),
            }
        r0 = {
            r["source_window_id"]: r
            for r in rows
            if r["receiver_id"] == 0 and r["status"] == "unique_hit"
        }
        r1 = {
            r["source_window_id"]: r
            for r in rows
            if r["receiver_id"] == 1 and r["status"] == "unique_hit"
        }
        common = []
        for wid in sorted(r0.keys() & r1.keys()):
            m0, m1 = r0[wid]["matches"][0], r1[wid]["matches"][0]
            key0 = (wid, 0, m0["candidate_id"])
            key1 = (wid, 1, m1["candidate_id"])
            if key0 not in candidates or key1 not in candidates:
                raise ValueError(f"dual-hit window lacks raw candidates: {wid}")
            c0, c1 = candidates[key0], candidates[key1]
            i0, i1 = c0.get("source_interval") or {}, c1.get("source_interval") or {}
            center0, center1 = i0.get("support_center_utc_ns"), i1.get("support_center_utc_ns")
            phase_delta = None
            compatible = None
            if center0 is not None and center1 is not None:
                delta = center1 - center0
                phase_delta = (delta + EPOCH_PERIOD_NS / 2) % EPOCH_PERIOD_NS - EPOCH_PERIOD_NS / 2
                compatible = abs(phase_delta) <= EPOCH_GATE_NS
            integer_delta = None
            if (
                c0.get("integer_epoch_sample") is not None
                and c1.get("integer_epoch_sample") is not None
            ):
                integer_delta = c1["integer_epoch_sample"] - c0["integer_epoch_sample"]
            common.append(
                {
                    "source_window_id": wid,
                    "support_center_delta_rx1_minus_rx0_ns": None
                    if center0 is None or center1 is None
                    else center1 - center0,
                    "support_center_epoch_phase_delta_rx1_minus_rx0_ns": phase_delta,
                    "proxy_epoch_gate_ns": EPOCH_GATE_NS,
                    "proxy_epoch_compatible": compatible,
                    "integer_epoch_sample_delta_rx1_minus_rx0": integer_delta,
                    "interpretation": (
                        "Timing-phase compatibility proxy only; it does not establish "
                        "a shared target."
                    ),
                }
            )
        cases.append(
            {
                "sequence": sequence,
                "receivers": by_rx,
                "common_dual_unique_hit_windows": common,
                "continuity_assessment": "descriptive_candidate_consistency_only",
            }
        )
    return {
        "schema": "rx-sequence-case-audit/v1",
        "case_count": len(cases),
        "source_digests": source_digests or {},
        "selection": "all sequences with a recorded first unique hit on both receivers",
        "uncensored_lag_case_count": sum(
            s.get("uncensored_lag_rx1_minus_rx0_s") is not None for s in selected
        ),
        "interpretation": (
            "Frozen candidate-consistent observations only; ambiguity is retained and no "
            "continuity, physical arrival order, or object identity is established."
        ),
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sequences", type=Path, required=True)
    parser.add_argument("--matched", type=Path, required=True)
    parser.add_argument("--opportunities", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sequence_bytes = args.sequences.read_bytes()
    matched_bytes = args.matched.read_bytes()
    opportunity_bytes = args.opportunities.read_bytes()
    sequences = json.loads(sequence_bytes)
    actual_opportunities_digest = digest(opportunity_bytes)
    expected_opportunities_digest = sequences.get("source_digests", {}).get("opportunities")
    if expected_opportunities_digest != actual_opportunities_digest:
        raise ValueError("sequence opportunities digest does not match supplied opportunities")
    result = build_audit(
        sequences,
        [json.loads(line) for line in matched_bytes.splitlines() if line.strip()],
        [json.loads(line) for line in opportunity_bytes.splitlines() if line.strip()],
        source_digests={
            "sequences": digest(sequence_bytes),
            "matched_opportunities": digest(matched_bytes),
            "opportunities": actual_opportunities_digest,
        },
    )
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as stream:
            stream.write(payload)
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
