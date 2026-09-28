"""Reference-relative scoring for serialized ``DwellGlrt64Analysis`` rows.

This module deliberately measures agreement with a frozen reference run.  It
does not infer signal truth, select candidates, or label unmatched candidates
as false alarms.
"""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


TIMING_GATE_US = 2.0
TRACKING_CFO_GATE_HZ = 8_000.0
MARGIN_GATE = 0.025
NONOVERLAP_MS = 20


@dataclass(frozen=True, slots=True)
class _Candidate:
    context: str
    rate_hz: int
    receiver_id: int
    probe_index: int
    probe_start_ms: int
    rank: int
    epoch_sample: int
    tracking_cfo_hz: float
    exact_score: float
    control_score: float
    margin: float
    passed_margin_gate: bool

    @property
    def identity(self) -> tuple[str, int, int]:
        return (self.context, self.receiver_id, self.probe_index)


def _canonical_context(row: Mapping[str, Any]) -> str:
    context = row.get("context")
    if not isinstance(context, Mapping) or not context:
        raise ValueError("each row requires a nonempty context mapping")
    repeat = row.get("repeat")
    if isinstance(repeat, bool) or not isinstance(repeat, int) or repeat < 0:
        raise ValueError("row repeat must be a nonnegative integer")
    try:
        return json.dumps({"context": context, "repeat": repeat}, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("row context must be JSON-canonicalizable") from error


def _rate(row: Mapping[str, Any]) -> int:
    context = row["context"]
    rate = context.get("sample_rate_hz", context.get("rate_hz"))
    if isinstance(rate, bool) or not isinstance(rate, int) or rate <= 0:
        raise ValueError("row context requires a positive integer sample rate")
    return rate


def _processed(row: Mapping[str, Any]) -> bool:
    result = row.get("result")
    status = row.get("status")
    if status not in ("ok", "complete", "failed"):
        raise ValueError("row status must be ok, complete, or failed")
    if status == "failed" and result is not None:
        raise ValueError("failed row cannot carry a Dwell result")
    if status in ("ok", "complete") and not isinstance(result, Mapping):
        raise ValueError("successful row requires a Dwell result")
    return status in ("ok", "complete")


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"candidate {name} must be finite")
    return float(value)


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"candidate {name} must be an integer")
    return value


def _candidates(row: Mapping[str, Any]) -> tuple[_Candidate, ...]:
    if not _processed(row):
        return ()
    context = _canonical_context(row)
    rate_hz = _rate(row)
    probes = row["result"].get("probes")
    if not isinstance(probes, list):
        raise ValueError("complete Dwell result requires probes")
    candidates: list[_Candidate] = []
    seen_probes: set[tuple[int, int]] = set()
    for probe in probes:
        if not isinstance(probe, Mapping):
            raise ValueError("probe must be a mapping")
        receiver_id = _integer(probe.get("receiver_id"), "receiver_id")
        probe_index = _integer(probe.get("probe_index"), "probe_index")
        probe_start_ms = _integer(probe.get("probe_start_ms"), "probe_start_ms")
        if probe_index < 0 or probe_start_ms < 0 or (receiver_id, probe_index) in seen_probes:
            raise ValueError("duplicate or invalid receiver/probe")
        seen_probes.add((receiver_id, probe_index))
        entries = probe.get("candidates")
        if not isinstance(entries, list):
            raise ValueError("probe candidates must be a list")
        ranks: set[int] = set()
        for item in entries:
            if not isinstance(item, Mapping):
                raise ValueError("candidate must be a mapping")
            rank = _integer(item.get("candidate_rank"), "rank")
            if rank < 0 or rank in ranks:
                raise ValueError("candidate ranks must be unique and nonnegative")
            ranks.add(rank)
            margin = _finite(item.get("margin"), "margin")
            passed = item.get("passed_margin_gate")
            if not isinstance(passed, bool) or passed != (margin >= MARGIN_GATE):
                raise ValueError("candidate margin-gate flag disagrees with standard gate")
            candidates.append(
                _Candidate(
                    context,
                    rate_hz,
                    receiver_id,
                    probe_index,
                    probe_start_ms,
                    rank,
                    _integer(item.get("epoch_sample"), "epoch_sample"),
                    _finite(item.get("tracking_cfo_hz"), "tracking_cfo_hz"),
                    _finite(item.get("exact_score"), "exact_score"),
                    _finite(item.get("control_score"), "control_score"),
                    margin,
                    passed,
                )
            )
    return tuple(candidates)


def _index(rows: Sequence[Mapping[str, Any]], label: str) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError(f"{label} row must be a mapping")
        key = _canonical_context(row)
        if key in indexed:
            raise ValueError(f"duplicate {label} row context")
        indexed[key] = row
    return indexed


def _maximum_matching(
    reference: Sequence[_Candidate], candidate: Sequence[_Candidate], edges: set[tuple[int, int]]
) -> int:
    assigned: dict[int, int] = {}

    def visit(reference_index: int, seen: set[int]) -> bool:
        for candidate_index in sorted(
            (right for left, right in edges if left == reference_index)
        ):
            if candidate_index in seen:
                continue
            seen.add(candidate_index)
            prior = assigned.get(candidate_index)
            if prior is None or visit(prior, seen):
                assigned[candidate_index] = reference_index
                return True
        return False

    return sum(visit(index, set()) for index in range(len(reference)))


def _match_group(
    reference: Sequence[_Candidate], candidate: Sequence[_Candidate]
) -> tuple[tuple[int, int], ...]:
    """Maximum-cardinality matching with deterministic nearest-edge preference."""

    edges: set[tuple[int, int]] = set()
    ranked: list[tuple[tuple[float, float, int, int], int, int]] = []
    for left, ref in enumerate(reference):
        for right, got in enumerate(candidate):
            timing_us = abs(ref.epoch_sample - got.epoch_sample) / ref.rate_hz * 1e6
            cfo_hz = abs(ref.tracking_cfo_hz - got.tracking_cfo_hz)
            if timing_us <= TIMING_GATE_US and cfo_hz <= TRACKING_CFO_GATE_HZ:
                edges.add((left, right))
                ranked.append(((timing_us / TIMING_GATE_US, cfo_hz / TRACKING_CFO_GATE_HZ,
                                ref.rank, got.rank), left, right))
    target = _maximum_matching(reference, candidate, edges)
    selected: list[tuple[int, int]] = []
    used_left: set[int] = set()
    used_right: set[int] = set()
    for _, left, right in sorted(ranked):
        if len(selected) == target or left in used_left or right in used_right:
            continue
        remaining = {
            (a, b)
            for a, b in edges
            if a not in used_left | {left} and b not in used_right | {right}
        }
        if len(selected) + 1 + _maximum_matching(reference, candidate, remaining) >= target:
            selected.append((left, right))
            used_left.add(left)
            used_right.add(right)
    return tuple(selected)


def _confirmed(candidates: Sequence[_Candidate]) -> set[tuple[str, int]]:
    by_receiver: dict[tuple[str, int], list[_Candidate]] = {}
    for item in candidates:
        if item.passed_margin_gate:
            by_receiver.setdefault((item.context, item.receiver_id), []).append(item)
    result = set()
    for key, items in by_receiver.items():
        if any(_confirmation_pair(left, right) for left in items for right in items):
            result.add(key)
    return result


def _confirmation_pair(left: _Candidate, right: _Candidate) -> bool:
    """Whether two same-receiver positives meet the frozen confirmation gate."""

    if left.probe_start_ms >= right.probe_start_ms:
        return False
    return (
        right.probe_start_ms - left.probe_start_ms >= NONOVERLAP_MS
        and abs(right.tracking_cfo_hz - left.tracking_cfo_hz) <= TRACKING_CFO_GATE_HZ
    )


def _matched_identity_confirmed(
    positive_matches: Sequence[tuple[_Candidate, _Candidate]],
) -> set[tuple[str, int]]:
    """Confirm only when the two credited identities form the same pair."""

    by_receiver: dict[tuple[str, int], list[tuple[_Candidate, _Candidate]]] = {}
    for reference, candidate in positive_matches:
        by_receiver.setdefault((reference.context, reference.receiver_id), []).append(
            (reference, candidate)
        )
    result = set()
    for key, pairs in by_receiver.items():
        if any(
            _confirmation_pair(left_reference, right_reference)
            and _confirmation_pair(left_candidate, right_candidate)
            for left_reference, left_candidate in pairs
            for right_reference, right_candidate in pairs
        ):
            result.add(key)
    return result


def _summary(values: Sequence[float]) -> dict[str, float | int | None]:
    absolute = [abs(value) for value in values]
    return {
        "count": len(values),
        "max_abs": max(absolute) if absolute else None,
        "mean_abs": statistics.fmean(absolute) if absolute else None,
        "median_abs": statistics.median(absolute) if absolute else None,
    }


def _timing(row: Mapping[str, Any]) -> tuple[float | None, float | None]:
    timing = row.get("timing", {})
    if not isinstance(timing, Mapping):
        raise ValueError("row timing must be a mapping")
    cpu = timing.get("cpu_s", timing.get("cpu_ms"))
    wall = timing.get("wall_s", timing.get("wall_ms"))
    def value(item: Any, seconds: bool) -> float | None:
        if item is None:
            return None
        parsed = _finite(item, "timing")
        if parsed < 0:
            raise ValueError("timing values cannot be negative")
        return parsed if seconds else parsed / 1000.0
    return value(cpu, "cpu_s" in timing), value(wall, "wall_s" in timing)


def score(
    reference_rows: Sequence[Mapping[str, Any]], candidate_rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Score candidate rows against reference rows without outcome selection.

    Each row has a nonempty JSON-canonicalizable ``context`` with ``rate_hz``
    or ``sample_rate_hz``, an optional ``result`` serialized from
    ``DwellGlrt64Analysis``, and optional ``timing``. A row without a complete
    result is retained as failed/unprocessed accounting rather than discarded.
    """

    reference_by_context = _index(reference_rows, "reference")
    candidate_by_context = _index(candidate_rows, "candidate")
    reference_contexts = set(reference_by_context)
    candidate_contexts = set(candidate_by_context)
    common_contexts = sorted(reference_contexts & candidate_contexts)

    reference_all: list[_Candidate] = []
    candidate_all: list[_Candidate] = []
    all_matches: list[tuple[_Candidate, _Candidate]] = []
    positive_matches: list[tuple[_Candidate, _Candidate]] = []
    matched_candidate: set[tuple[str, int, int, int]] = set()
    matched_positive_candidate: set[tuple[str, int, int, int]] = set()
    exact_outputs = 0
    runtime = {"reference_cpu_s": [], "reference_wall_s": [], "candidate_cpu_s": [], "candidate_wall_s": []}

    for row in reference_rows:
        cpu, wall = _timing(row)
        if cpu is not None: runtime["reference_cpu_s"].append(cpu)
        if wall is not None: runtime["reference_wall_s"].append(wall)
    for row in candidate_rows:
        cpu, wall = _timing(row)
        if cpu is not None: runtime["candidate_cpu_s"].append(cpu)
        if wall is not None: runtime["candidate_wall_s"].append(wall)

    for context in common_contexts:
        ref_row, got_row = reference_by_context[context], candidate_by_context[context]
        ref_done, got_done = _processed(ref_row), _processed(got_row)
        ref_candidates, got_candidates = _candidates(ref_row), _candidates(got_row)
        reference_all.extend(ref_candidates)
        candidate_all.extend(got_candidates)
        if ref_done and got_done and ref_row["result"] == got_row["result"]:
            exact_outputs += 1
        by_probe_reference: dict[tuple[str, int, int], list[_Candidate]] = {}
        by_probe_candidate: dict[tuple[str, int, int], list[_Candidate]] = {}
        for item in ref_candidates: by_probe_reference.setdefault(item.identity, []).append(item)
        for item in got_candidates: by_probe_candidate.setdefault(item.identity, []).append(item)
        for key in sorted(set(by_probe_reference) & set(by_probe_candidate)):
            left, right = by_probe_reference[key], by_probe_candidate[key]
            for left_index, right_index in _match_group(left, right):
                ref, got = left[left_index], right[right_index]
                all_matches.append((ref, got))
                matched_candidate.add((got.context, got.receiver_id, got.probe_index, got.rank))
            positive_left = [item for item in left if item.passed_margin_gate]
            positive_right = [item for item in right if item.passed_margin_gate]
            for left_index, right_index in _match_group(positive_left, positive_right):
                ref, got = positive_left[left_index], positive_right[right_index]
                positive_matches.append((ref, got))
                matched_positive_candidate.add(
                    (got.context, got.receiver_id, got.probe_index, got.rank)
                )

    for context in sorted(reference_contexts - candidate_contexts):
        reference_all.extend(_candidates(reference_by_context[context]))
    for context in sorted(candidate_contexts - reference_contexts):
        candidate_all.extend(_candidates(candidate_by_context[context]))

    reference_positive = [item for item in reference_all if item.passed_margin_gate]
    reference_negative = [item for item in reference_all if not item.passed_margin_gate]
    candidate_positive = [item for item in candidate_all if item.passed_margin_gate]
    identity_recovered = [ref for ref, _ in positive_matches]
    reference_positive_probes = {item.identity for item in reference_positive}
    candidate_positive_probes = {item.identity for item in candidate_positive}
    unprocessed_contexts = {
        context for context in reference_contexts
        if context not in candidate_by_context or not _processed(candidate_by_context[context])
    }
    method_unprocessed_positive = [item for item in reference_positive if item.context in unprocessed_contexts]
    method_unprocessed_negative = [item for item in reference_negative if item.context in unprocessed_contexts]
    deltas = {
        "timing_us": [], "tracking_cfo_hz": [], "exact_score": [], "control_score": [], "margin": []
    }
    for ref, got in all_matches:
        deltas["timing_us"].append((got.epoch_sample - ref.epoch_sample) / ref.rate_hz * 1e6)
        deltas["tracking_cfo_hz"].append(got.tracking_cfo_hz - ref.tracking_cfo_hz)
        deltas["exact_score"].append(got.exact_score - ref.exact_score)
        deltas["control_score"].append(got.control_score - ref.control_score)
        deltas["margin"].append(got.margin - ref.margin)
    reference_confirmed, candidate_confirmed = _confirmed(reference_all), _confirmed(candidate_all)
    matched_identity_confirmed = _matched_identity_confirmed(positive_matches)
    successful_pairs = sum(
        _processed(reference_by_context[context]) and _processed(candidate_by_context[context])
        for context in common_contexts
    )
    complete_coverage = (
        bool(reference_rows)
        and reference_contexts == candidate_contexts
        and len(reference_rows) == len(candidate_rows)
        and successful_pairs == len(reference_rows)
        and all(len(runtime[name]) == len(reference_rows)
                for name in ("reference_cpu_s", "reference_wall_s"))
        and all(len(runtime[name]) == len(candidate_rows)
                for name in ("candidate_cpu_s", "candidate_wall_s"))
    )

    def recovery(matched: int, denominator: int) -> dict[str, int | float | None]:
        return {
            "matched": matched,
            "denominator": denominator,
            "fraction": matched / denominator if denominator else None,
        }

    runtime_summary = {
        name: {"sum": sum(values), "count": len(values),
               "median": statistics.median(values) if values else None}
        for name, values in runtime.items()
    }
    runtime_summary["complete_coverage"] = complete_coverage
    runtime_summary["cpu_speedup_reference_over_candidate"] = (
        sum(runtime["reference_cpu_s"]) / sum(runtime["candidate_cpu_s"])
        if complete_coverage and sum(runtime["candidate_cpu_s"]) > 0 else None
    )
    runtime_summary["wall_speedup_reference_over_candidate"] = (
        sum(runtime["reference_wall_s"]) / sum(runtime["candidate_wall_s"])
        if complete_coverage and sum(runtime["candidate_wall_s"]) > 0 else None
    )

    return {
        "schema": "leo.ds7.glrt-reference-score.v1",
        "association": {"timing_gate_us": TIMING_GATE_US, "tracking_cfo_gate_hz": TRACKING_CFO_GATE_HZ,
                        "matching": "deterministic nearest-edge maximum-cardinality per context/receiver/probe"},
        "row_accounting": {
            "reference_total": len(reference_rows), "candidate_total": len(candidate_rows),
            "reference_successful": sum(_processed(row) for row in reference_rows),
            "reference_failed": sum(not _processed(row) for row in reference_rows),
            "candidate_successful": sum(_processed(row) for row in candidate_rows),
            "candidate_failed": sum(not _processed(row) for row in candidate_rows),
            "matched_contexts": len(common_contexts),
            "reference_unmatched_contexts": len(reference_contexts - candidate_contexts),
            "candidate_unmatched_contexts": len(candidate_contexts - reference_contexts),
            "exact_full_output_equal": exact_outputs,
        },
        "science_equivalence": {
            "successful_row_pairs": successful_pairs,
            "exact_full_output_equal": exact_outputs,
            "exact_full_output_fraction": (
                exact_outputs / successful_pairs if successful_pairs else None
            ),
        },
        "reference_denominators": {
            "positive_candidates": len(reference_positive), "negative_candidates": len(reference_negative),
            "positive_receiver_probe_pairs": len(reference_positive_probes),
            "confirmed_receiver_visit_pairs": len(reference_confirmed),
            "method_unprocessed_positive_candidates": len(method_unprocessed_positive),
            "method_unprocessed_negative_candidates": len(method_unprocessed_negative),
        },
        "recovery": {
            "positive_candidate_identity": recovery(len(identity_recovered), len(reference_positive)),
            "positive_receiver_probe": recovery(
                len(reference_positive_probes & candidate_positive_probes),
                len(reference_positive_probes),
            ),
            "confirmed_receiver_visit_matched_identity": recovery(
                len(matched_identity_confirmed), len(reference_confirmed)
            ),
            "confirmed_receiver_visit_activity_only": recovery(
                len(reference_confirmed & candidate_confirmed), len(reference_confirmed)
            ),
        },
        "candidate_extras_unmatched_not_false_alarms": {
            "positive_candidates": len(candidate_positive),
            "positive_candidates_unmatched_identity": sum(
                (item.context, item.receiver_id, item.probe_index, item.rank)
                not in matched_positive_candidate
                for item in candidate_positive
            ),
            "all_candidates_unmatched_identity": sum(
                (item.context, item.receiver_id, item.probe_index, item.rank) not in matched_candidate
                for item in candidate_all
            ),
            "positive_candidates_associated_with_reference_negative": sum(
                got.passed_margin_gate and not reference.passed_margin_gate
                for reference, got in all_matches
            ),
        },
        "matched_candidate_pairs": len(all_matches),
        "matched_positive_hypothesis_pairs": len(positive_matches),
        "deltas": {name: _summary(values) for name, values in deltas.items()},
        "runtime_seconds": runtime_summary,
        "oracle_truth_claimed": False,
    }
