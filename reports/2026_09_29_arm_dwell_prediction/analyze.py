"""Causal, oracle-seeded frequency-prediction feasibility audit.

This reads completed standard GLRT rows.  Its positive candidates are prior
seeds only: it neither reads IQ nor executes GLRT, so its coverage values are
not recovery.  A future detector must obtain equivalent seeds causally.
"""
from __future__ import annotations

import json
import hashlib
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADJACENT_SOURCE = ROOT / "reports/2026_09_28_ds7_glrt_benchmark/run-01/rows.jsonl"
SPARSE_SOURCE = ROOT / "reports/2026_09_28_ds7_large_arm/baseline-01/rows.jsonl"
GATE = 0.025
TOLERANCE_HZ = 8_000.0
DRIFT_ASSOCIATION_GATE_HZ = 20_000.0


def assumed_lo_reference(context: dict) -> float:
    # Metadata-only hypothesis. The standard acquisition path does not consume
    # these fields, so this must not be treated as a verified correction rule.
    return float(context["actual_lo_frequency_hz"] + context["actual_if_offset_hz"])


def load_visits(path: Path) -> list[dict]:
    visits = []
    for line in path.read_text().splitlines():
        row = json.loads(line)
        if row.get("method") not in (None, "original") or row.get("repeat", 0) != 0:
            continue
        if row["status"] != "ok":
            raise ValueError("incomplete standard row")
        context = row["context"]
        grouped: dict[int, list[float]] = defaultdict(list)
        receivers = set()
        for probe in row["result"]["probes"]:
            receivers.add(int(probe["receiver_id"]))
            for candidate in probe["candidates"]:
                if candidate["margin"] >= GATE:
                    grouped[int(probe["receiver_id"])].append(
                        float(candidate["tracking_cfo_hz"])
                    )
        for receiver in receivers:
            frequencies = grouped[receiver]
            visits.append({
                "key": (context["session_id"], context["target"]["channel"],
                        context["target"]["edge"], receiver, context["rate_hz"]),
                "counter": int(context["sample_start_counter"]),
                "rate": float(context["rate_hz"]),
                "lo": assumed_lo_reference(context),
                "frequencies": frequencies,
            })
    return visits


def predict_last(previous: dict, current: dict) -> list[float]:
    """Map prior baseband CFO hypotheses into the current LO reference."""
    return [f + previous["lo"] - current["lo"] for f in previous["frequencies"]]


def predict_last_two(older: dict, previous: dict, current: dict) -> list[float]:
    """Return the causal all-pairs linear-extrapolation bank in current CFO."""
    old_time = older["counter"] / older["rate"]
    previous_time = previous["counter"] / previous["rate"]
    current_time = current["counter"] / current["rate"]
    if previous_time <= old_time or current_time <= previous_time:
        return []
    scale = (current_time - previous_time) / (previous_time - old_time)
    old_absolute = [f + older["lo"] for f in older["frequencies"]]
    previous_absolute = [f + previous["lo"] for f in previous["frequencies"]]
    return [new + (new - old) * scale - current["lo"]
            for old in old_absolute for new in previous_absolute]


def predict_bounded_drift(older: dict, previous: dict, current: dict) -> list[float]:
    """One causal extrapolation per unique latest seed, gated before current IQ."""
    old_time = older["counter"] / older["rate"]
    previous_time = previous["counter"] / previous["rate"]
    current_time = current["counter"] / current["rate"]
    if previous_time <= old_time or current_time <= previous_time:
        return []
    older_absolute = [value + older["lo"] for value in older["frequencies"]]
    scale = (current_time - previous_time) / (previous_time - old_time)
    predictions = []
    for latest in sorted(set(value + previous["lo"] for value in previous["frequencies"])):
        nearest = min(older_absolute, key=lambda value: abs(value - latest), default=None)
        if nearest is not None and abs(nearest - latest) <= DRIFT_ASSOCIATION_GATE_HZ:
            predictions.append(latest + (latest - nearest) * scale - current["lo"])
    return predictions


def minimum_error(predictions: list[float], truth: float) -> float | None:
    return min((abs(value - truth) for value in predictions), default=None)


def size_summary(values: list[int]) -> dict:
    ordered = sorted(values)
    return {
        "eligible_dwells": len(ordered),
        "mean": sum(ordered) / len(ordered) if ordered else None,
        "median": ordered[len(ordered) // 2] if ordered else None,
        "p95": ordered[int(.95 * (len(ordered) - 1))] if ordered else None,
        "max": max(ordered, default=None),
    }


def summarize(visits: list[dict], source: Path, scope: str) -> dict:
    histories: dict[tuple, list[dict]] = defaultdict(list)
    last_errors, slope_errors, drift_errors, gaps, corrections = [], [], [], [], []
    last_raw_sizes, last_unique_sizes = [], []
    slope_raw_sizes, slope_unique_sizes, drift_raw_sizes, drift_unique_sizes = [], [], [], []
    total_positive = cold_positive = no_last_seed = no_slope_seed = no_drift_seed = 0
    for current in sorted(visits, key=lambda item: (item["key"], item["counter"])):
        history = histories[current["key"]]
        total_positive += len(current["frequencies"])
        if history:
            previous = history[-1]
            gap = current["counter"] / current["rate"] - previous["counter"] / previous["rate"]
            if gap > 0:
                corrections.append(abs(previous["lo"] - current["lo"]))
                predictions = predict_last(previous, current)
                if predictions:
                    last_raw_sizes.append(len(predictions))
                    last_unique_sizes.append(len(set(predictions)))
                    for truth in current["frequencies"]:
                        last_errors.append(minimum_error(predictions, truth))
                        gaps.append(gap)
                else:
                    no_last_seed += len(current["frequencies"])
                if len(history) >= 2:
                    slope = predict_last_two(history[-2], previous, current)
                    if slope:
                        slope_raw_sizes.append(len(slope))
                        slope_unique_sizes.append(len(set(slope)))
                        for truth in current["frequencies"]:
                            slope_errors.append(minimum_error(slope, truth))
                    else:
                        no_slope_seed += len(current["frequencies"])
                    drift = predict_bounded_drift(history[-2], previous, current)
                    if drift:
                        drift_raw_sizes.append(len(drift))
                        drift_unique_sizes.append(len(set(drift)))
                        for truth in current["frequencies"]:
                            drift_errors.append(minimum_error(drift, truth))
                    else:
                        no_drift_seed += len(current["frequencies"])
                else:
                    no_slope_seed += len(current["frequencies"])
                    no_drift_seed += len(current["frequencies"])
        else:
            cold_positive += len(current["frequencies"])
        history.append(current)
    def metrics(errors: list[float], name: str) -> dict:
        ordered = sorted(error for error in errors if error is not None)
        covered = sum(error <= TOLERANCE_HZ for error in ordered)
        return {
            "eligible_positive_entries": len(ordered),
            "within_8khz": covered,
            "conditional_coverage": covered / len(ordered) if ordered else None,
            "prospective_full_denominator_coverage": covered / total_positive if total_positive else None,
            "not_covered_requires_blind_path": total_positive - covered,
            "median_abs_error_hz": ordered[len(ordered) // 2] if ordered else None,
            "p95_abs_error_hz": ordered[int(.95 * (len(ordered) - 1))] if ordered else None,
            "bank": name,
        }
    ordered_gaps = sorted(gaps)
    return {
        "schema": "arm-dwell-prediction-feasibility/v2",
        "source": str(source.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "scope": scope,
        "positive_gate": GATE,
        "match_tolerance_hz": TOLERANCE_HZ,
        "bounded_drift_association_gate_hz": DRIFT_ASSOCIATION_GATE_HZ,
        "receiver_dwell_records": len(visits),
        "standard_positive_entries": total_positive,
        "cold_start_positive_entries": cold_positive,
        "history_without_last_positive_seed_entries": no_last_seed,
        "history_without_two_positive_seed_entries": no_slope_seed,
        "history_without_bounded_drift_seed_entries": no_drift_seed,
        "last_prior_oracle_seed_bank": metrics(last_errors, "last prior dwell positive entries"),
        "last_two_oracle_seed_bank": metrics(slope_errors, "all older/prior positive-entry pairs"),
        "bounded_causal_drift_bank": metrics(
            drift_errors,
            "one extrapolation per unique latest seed after a 20 kHz causal nearest-history gate",
        ),
        "proposal_bank_sizes_per_eligible_dwell": {
            "last_prior_raw": size_summary(last_raw_sizes),
            "last_prior_unique": size_summary(last_unique_sizes),
            "last_two_all_pairs_raw": size_summary(slope_raw_sizes),
            "last_two_all_pairs_unique": size_summary(slope_unique_sizes),
            "bounded_drift_raw": size_summary(drift_raw_sizes),
            "bounded_drift_unique": size_summary(drift_unique_sizes),
        },
        "gap_seconds": {"min": min(ordered_gaps), "median": ordered_gaps[len(ordered_gaps)//2], "max": max(ordered_gaps)},
        "lo_reference_change_hz": {"max": max(corrections, default=0.0), "nonzero_pairs": sum(value != 0 for value in corrections)},
        "interpretation": (
            "Coverage is an oracle-seeded all-positive-bank upper envelope, not a narrow predictor. "
            "It is not IQ-to-GLRT recovery, does not account for cold starts or negative proposals, "
            "and cannot justify a runtime claim."
        ),
    }


def main() -> None:
    output = Path(__file__).with_name("summary.json")
    output.write_text(json.dumps({
        "frequency_reference_note": (
            "The arithmetic uses actual_lo_frequency_hz + actual_if_offset_hz as a metadata hypothesis. "
            "The standard acquisition code does not consume these fields, so its sign and applicability are unverified. "
            "Every eligible same-key pair here has zero reference delta; this assumption changes none of these results."
        ),
        "causality_policy": {
            "same_key": "session_id, channel, edge, receiver_id, and rate_hz",
            "history": "strictly earlier sample_start_counter only",
            "gap": "positive counter/rate seconds; cross-rate history is excluded",
            "cold_starts": "counted in full denominator and require a blind path",
            "bounded_drift": "fixed 20 kHz nearest-older association before current IQ; one prediction per unique latest seed",
        },
        "command": ".venv/bin/python reports/2026_09_29_arm_dwell_prediction/analyze.py",
        "test_command": ".venv/bin/python -m pytest -q reports/2026_09_29_arm_dwell_prediction/test_analyze.py",
        "next_same_channel_smoke": summarize(
            load_visits(ADJACENT_SOURCE), ADJACENT_SOURCE,
            "DS7 28-dwell chronological smoke cohort; same session/channel/edge/receiver/rate only",
        ),
        "sparse_history_stress": summarize(
            load_visits(SPARSE_SOURCE), SPARSE_SOURCE,
            "DS7 704-dwell stratified cohort; same session/channel/edge/receiver/rate only; not adjacent dwells",
        ),
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
