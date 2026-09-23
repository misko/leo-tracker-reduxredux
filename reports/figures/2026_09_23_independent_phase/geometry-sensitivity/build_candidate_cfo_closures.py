"""Enumerate CFO closure for the six retained metadata-only opportunities."""

from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
INPUT = Path(__file__).with_name("raw-candidate-opportunities.json")
OUTPUT = Path(__file__).with_name("raw-candidate-cfo-closures.json")
FULL_ALIAS_HZ = 1.0 / 4.4e-6
HALF_ALIAS_HZ = FULL_ALIAS_HZ / 2.0


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wrap(value: float, period: float) -> float:
    return (value + period / 2.0) % period - period / 2.0


def bounds(values: list[float]) -> dict:
    return {"minimum": min(values), "maximum": max(values)}


def build() -> dict:
    source = json.loads(INPUT.read_text())
    opportunities = []
    total = 0
    for opportunity in source["opportunities"]:
        components = opportunity["receiver_components"]
        rows = []
        for matching_index, matching in enumerate(
            opportunity["one_to_one_component_matchings"]
        ):
            if not matching["both_pairs_timing_compatible"]:
                continue
            member_pairs = matching["compatible_candidate_members_by_pair"]
            for first, second in itertools.product(*member_pairs):
                pair_rows = []
                for pair in (first, second):
                    rx0 = next(
                        row
                        for component in components["0"]
                        for row in component
                        if row["candidate_rank"] == pair["rx0_candidate_rank"]
                    )
                    rx1 = next(
                        row
                        for component in components["1"]
                        for row in component
                        if row["candidate_rank"] == pair["rx1_candidate_rank"]
                    )
                    pair_rows.append((rx0, rx1, pair["timing_offset_samples"]))
                (rx0a, rx1a, timing_a), (rx0b, rx1b, timing_b) = pair_rows
                d_a = rx1a["tracking_cfo_hz"] - rx0a["tracking_cfo_hz"]
                d_b = rx1b["tracking_cfo_hz"] - rx0b["tracking_cfo_hz"]
                closure = d_b - d_a
                rx0_separation = rx0b["tracking_cfo_hz"] - rx0a["tracking_cfo_hz"]
                rx1_separation = rx1b["tracking_cfo_hz"] - rx1a["tracking_cfo_hz"]
                rows.append(
                    {
                        "matching_index": matching_index,
                        "pair_a": {
                            "rx0_candidate_rank": rx0a["candidate_rank"],
                            "rx1_candidate_rank": rx1a["candidate_rank"],
                            "timing_offset_samples": timing_a,
                            "receiver_cfo_offset_hz": d_a,
                        },
                        "pair_b": {
                            "rx0_candidate_rank": rx0b["candidate_rank"],
                            "rx1_candidate_rank": rx1b["candidate_rank"],
                            "timing_offset_samples": timing_b,
                            "receiver_cfo_offset_hz": d_b,
                        },
                        "source_cfo_separation_hz": {
                            "rx0_b_minus_a": rx0_separation,
                            "rx1_b_minus_a": rx1_separation,
                        },
                        "receiver_offset_closure_hz": closure,
                        "closure_wrapped_full_alias_hz": wrap(closure, FULL_ALIAS_HZ),
                        "closure_wrapped_half_alias_hz": wrap(closure, HALF_ALIAS_HZ),
                    }
                )
        closures = [row["receiver_offset_closure_hz"] for row in rows]
        full = [row["closure_wrapped_full_alias_hz"] for row in rows]
        half = [row["closure_wrapped_half_alias_hz"] for row in rows]
        rx0_sep = [row["source_cfo_separation_hz"]["rx0_b_minus_a"] for row in rows]
        rx1_sep = [row["source_cfo_separation_hz"]["rx1_b_minus_a"] for row in rows]
        opportunities.append(
            {
                "sample_start": opportunity["sample_start"],
                "time_s": opportunity["time_s"],
                "member_combination_count": len(rows),
                "ranges_hz": {
                    "raw_receiver_offset_closure": bounds(closures),
                    "full_alias_wrapped_closure": bounds(full),
                    "half_alias_wrapped_closure": bounds(half),
                    "rx0_source_separation": bounds(rx0_sep),
                    "rx1_source_separation": bounds(rx1_sep),
                },
                "member_combinations": rows,
            }
        )
        total += len(rows)
    builder = Path(__file__)
    return {
        "schema": "raw-pilot-candidate-cfo-closures/v1",
        "source_artifact": str(INPUT.relative_to(ROOT)),
        "source_artifact_sha256": sha256(INPUT),
        "native_full_alias_period_hz": FULL_ALIAS_HZ,
        "native_half_alias_period_hz_diagnostic": HALF_ALIAS_HZ,
        "opportunity_count": len(opportunities),
        "member_combination_count": total,
        "opportunities": opportunities,
        "interpretation": (
            "Every timing-compatible member combination is retained. Raw CFO offsets and "
            "closures are observations; wrapped values are alias diagnostics. No unwrap, "
            "nearest-CFO choice, path, pass gate, phase selection, or source identity is applied."
        ),
        "no_iq_read": True,
        "source_sha256": {str(builder.relative_to(ROOT)): sha256(builder)},
    }


if __name__ == "__main__":
    if OUTPUT.exists():
        raise ValueError("fresh output path required")
    OUTPUT.write_text(json.dumps(build(), indent=2, allow_nan=False) + "\n")
