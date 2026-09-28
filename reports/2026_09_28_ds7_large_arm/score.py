#!/usr/bin/env python3
"""Score the fixed DS7 large ARM cohort against full-original GLRT rows.

This is deliberately a report-local reader.  It accepts the frozen original
runner schema and the ARM RAM worker's ``type: job`` records; neither format is
a production contract.  A candidate positive is an individual GLRT hypothesis,
while a positive window is a receiver x 20 ms interval containing one.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TIMING_GATE_US = 2.0
CFO_GATE_HZ = 8_000.0
MARGIN_GATE = 0.025


@dataclass(frozen=True)
class Candidate:
    case_id: str
    receiver: int
    start_ms: int
    epoch: float
    cfo_hz: float
    margin: float
    positive: bool

    @property
    def window(self) -> tuple[str, int, int]:
        return self.case_id, self.receiver, self.start_ms


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{field} must be finite")
    return float(value)


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def case_id(row: Mapping[str, Any]) -> str:
    value = row.get("case_id")
    context = row.get("context")
    if isinstance(value, str) and value and (
        not isinstance(context, Mapping)
        or not isinstance(context.get("session_id"), str)
        or not isinstance(context.get("visit_index"), int)
    ):
        return value
    if not isinstance(context, Mapping):
        raise ValueError("row requires case_id or context")
    session, visit = context.get("session_id"), context.get("visit_index")
    if not isinstance(session, str) or not session or isinstance(visit, bool) or not isinstance(visit, int):
        raise ValueError("context requires session_id and integer visit_index")
    derived = f"ds7-{session}-v{visit}"
    if isinstance(value, str) and value and value != derived:
        raise ValueError(f"case_id disagrees with context: {value} != {derived}")
    return derived


def _baseline(row: Mapping[str, Any]) -> tuple[dict[tuple[str, int, int], list[Candidate]], set[str]]:
    key = case_id(row)
    if row.get("status") not in ("ok", "complete"):
        raise ValueError(f"baseline {key} is not successful")
    result = row.get("result")
    if not isinstance(result, Mapping) or not isinstance(result.get("probes"), list):
        raise ValueError(f"baseline {key} lacks result.probes")
    windows: dict[tuple[str, int, int], list[Candidate]] = {}
    for probe in result["probes"]:
        if not isinstance(probe, Mapping): raise ValueError("baseline probe must be an object")
        receiver = _integer(probe.get("receiver_id"), "receiver_id")
        start = _integer(probe.get("probe_start_ms"), "probe_start_ms")
        window = (key, receiver, start)
        if window in windows: raise ValueError(f"duplicate baseline window {window}")
        entries = probe.get("candidates")
        if not isinstance(entries, list): raise ValueError("baseline candidates must be a list")
        candidates = []
        for item in entries:
            if not isinstance(item, Mapping): raise ValueError("baseline candidate must be an object")
            margin = _finite(item.get("margin"), "baseline margin")
            passed = item.get("passed_margin_gate")
            if not isinstance(passed, bool) or passed != (margin >= MARGIN_GATE):
                raise ValueError("baseline passed_margin_gate disagrees with margin >= 0.025")
            candidates.append(Candidate(key, receiver, start, _finite(item.get("epoch_sample"), "epoch_sample"),
                                        _finite(item.get("tracking_cfo_hz"), "tracking_cfo_hz"), margin, passed))
        windows[window] = candidates
    return windows, {key}


def _arm(row: Mapping[str, Any]) -> tuple[dict[tuple[str, int, int], list[Candidate]], set[tuple[str, int, int]], set[tuple[str, int, int]], set[str]]:
    key = case_id(row)
    if row.get("type", "job") != "job" or row.get("status") != "processed":
        raise ValueError(f"ARM {key} is not a processed job")
    receivers = row.get("receivers")
    if not isinstance(receivers, list): raise ValueError(f"ARM {key} lacks receivers")
    if len(receivers) != 2:
        raise ValueError("ARM job must contain exactly two receiver payloads")
    positives: dict[tuple[str, int, int], list[Candidate]] = {}
    ranked: set[tuple[str, int, int]] = set()
    executed: set[tuple[str, int, int]] = set()
    receiver_ids: set[int] = set()
    for entry in receivers:
        if not isinstance(entry, Mapping): raise ValueError("ARM receiver must be an object")
        receiver = _integer(entry.get("receiver"), "receiver")
        receiver_ids.add(receiver)
        result = entry.get("result")
        if not isinstance(result, Mapping): raise ValueError("ARM receiver lacks result")
        rank = result.get("rank")
        if not isinstance(rank, Mapping) or not isinstance(rank.get("order"), list):
            raise ValueError("ARM receiver lacks rank.order")
        order = [_integer(bit, "rank.order bit") for bit in rank["order"]]
        if sorted(order) != list(range(6)):
            raise ValueError("ARM rank.order must be a permutation of the six 20 ms windows 0..5")
        for bit in order: ranked.add((key, receiver, 20 * bit))
        mask = _integer(result.get("confirmation_window_mask"), "confirmation_window_mask")
        if mask < 0: raise ValueError("confirmation_window_mask cannot be negative")
        bits = [bit for bit in range(mask.bit_length()) if mask & (1 << bit)]
        count = _integer(result.get("confirmation_count"), "confirmation_count")
        if count != len(bits) or count > 1:
            raise ValueError("ARM confirmation_count must equal one-or-zero executed window bits")
        confirmations = result.get("confirmations")
        if not isinstance(confirmations, list) or len(confirmations) != len(bits):
            raise ValueError("ARM confirmations must align one-for-one with confirmation_window_mask")
        for bit, confirmation in zip(bits, confirmations):
            window = (key, receiver, 20 * bit)
            if window not in ranked: raise ValueError(f"executed window was not ranked: {window}")
            executed.add(window)
            entries = confirmation.get("candidates") if isinstance(confirmation, Mapping) else None
            if not isinstance(entries, list): raise ValueError("ARM confirmation candidates must be a list")
            if _integer(confirmation.get("candidate_count"), "candidate_count") != len(entries):
                raise ValueError("ARM confirmation candidate_count differs from candidates")
            parsed: list[Candidate] = []
            for item in entries:
                if not isinstance(item, Mapping): raise ValueError("ARM candidate must be an object")
                margin = _finite(item.get("margin"), "ARM margin")
                complete = item.get("fractional_complete")
                if complete not in (0, 1, False, True): raise ValueError("fractional_complete must be 0 or 1")
                # ARM's strict threshold is intentionally different from original's >= gate.
                positive = bool(complete) and margin > MARGIN_GATE
                epoch = _finite(item.get("epoch", item.get("epoch_sample")), "ARM epoch")
                fractional = _finite(item.get("fractional_offset_samples", 0.0), "fractional_offset_samples")
                parsed.append(Candidate(key, receiver, 20 * bit, epoch + fractional,
                                        _finite(item.get("tracking_cfo_hz"), "tracking_cfo_hz"), margin, positive))
            positives[window] = parsed
    if receiver_ids != {0, 1}:
        raise ValueError("ARM job receiver inventory must be exactly {0, 1}")
    return positives, ranked, executed, {key}


def _read(path: Path) -> list[dict[str, Any]]:
    rows = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict): raise ValueError(f"{path}:{number}: JSON row must be an object")
            rows.append(value)
    return rows


def _maximum_pairs(reference: Sequence[Candidate], arm: Sequence[Candidate], rate_hz: int) -> int:
    edges = {i: [] for i in range(len(reference))}
    for i, left in enumerate(reference):
        for j, right in enumerate(arm):
            if abs(left.epoch - right.epoch) / rate_hz * 1e6 <= TIMING_GATE_US and abs(left.cfo_hz - right.cfo_hz) <= CFO_GATE_HZ:
                edges[i].append(j)
    assigned: dict[int, int] = {}
    def visit(i: int, seen: set[int]) -> bool:
        for j in edges[i]:
            if j not in seen:
                seen.add(j)
                if j not in assigned or visit(assigned[j], seen): assigned[j] = i; return True
        return False
    return sum(visit(i, set()) for i in range(len(reference)))


def _inventory(inputs: Mapping[str, Any]) -> set[str]:
    if isinstance(inputs.get("case_ids"), list): values = inputs["case_ids"]
    elif isinstance(inputs.get("planned_case_ids"), list): values = inputs["planned_case_ids"]
    elif isinstance(inputs.get("jobs"), list): values = [x.get("case_id") for x in inputs["jobs"] if isinstance(x, Mapping)]
    elif isinstance(inputs.get("rows"), list):
        if inputs.get("complete") is not True: raise ValueError("inputs receipt is not complete")
        values = [case_id({"context": x}) for x in inputs["rows"] if isinstance(x, Mapping)]
    else: raise ValueError("inputs requires case_ids, planned_case_ids, or jobs")
    if not all(isinstance(x, str) and x for x in values): raise ValueError("planned case IDs must be nonempty strings")
    if len(values) != len(set(values)): raise ValueError("planned case IDs are duplicated")
    return set(values)


def _input_contexts(inputs: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = inputs.get("rows")
    if not isinstance(rows, list):
        return {}
    if inputs.get("complete") is not True:
        raise ValueError("inputs receipt is not complete")
    contexts: dict[str, Mapping[str, Any]] = {}
    for context in rows:
        if not isinstance(context, Mapping): raise ValueError("input row must be an object")
        key = case_id({"context": context})
        if key in contexts: raise ValueError(f"duplicate input case {key}")
        contexts[key] = context
    return contexts


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _receipt(receipt: Mapping[str, Any], label: str, expected: int, inputs: Path, rows: Path) -> None:
    if receipt.get("complete") is not True:
        raise ValueError(f"{label} run receipt is not complete")
    for field in ("planned_calls", "calls", "failed_calls"):
        value = receipt.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{label} run receipt lacks integer {field}")
    if receipt["planned_calls"] != expected or receipt["calls"] != expected or receipt["failed_calls"] != 0:
        raise ValueError(f"{label} run receipt does not prove {expected} successful planned calls")
    for field, actual in (("input_manifest_sha256", _sha(inputs)), ("rows_sha256", _sha(rows))):
        declared = receipt.get(field)
        if declared is not None and (not isinstance(declared, str) or declared != actual):
            raise ValueError(f"{label} run receipt {field} differs from supplied artifact")


def score(baseline_rows: Sequence[Mapping[str, Any]], arm_rows: Sequence[Mapping[str, Any]], inputs: Mapping[str, Any], *, _per_rate: bool = True) -> dict[str, Any]:
    planned = _inventory(inputs)
    input_contexts = _input_contexts(inputs)
    baseline: dict[tuple[str, int, int], list[Candidate]] = {}
    baseline_cases: set[str] = set()
    for row in baseline_rows:
        windows, cases = _baseline(row)
        if baseline_cases & cases: raise ValueError(f"duplicate baseline case {next(iter(baseline_cases & cases))}")
        baseline.update(windows); baseline_cases |= cases
    arm: dict[tuple[str, int, int], list[Candidate]] = {}
    ranked: set[tuple[str, int, int]] = set(); executed: set[tuple[str, int, int]] = set(); arm_cases: set[str] = set()
    for row in arm_rows:
        windows, row_ranked, row_executed, cases = _arm(row)
        if arm_cases & cases: raise ValueError(f"duplicate ARM case {next(iter(arm_cases & cases))}; repeated jobs cannot enter science counts")
        arm.update(windows); ranked |= row_ranked; executed |= row_executed; arm_cases |= cases
    if input_contexts:
        for row in [*baseline_rows, *arm_rows]:
            key = case_id(row)
            if row.get("context") != input_contexts.get(key):
                raise ValueError(f"{key} context differs from sealed inputs row")
    for label, actual in (("baseline", baseline_cases), ("ARM", arm_cases)):
        if actual != planned:
            raise ValueError(f"{label} cohort does not equal planned inventory: missing={sorted(planned-actual)[:3]} extra={sorted(actual-planned)[:3]}")
    if input_contexts:
        expected_starts = set(range(0, 101, 10))
        for key in planned:
            starts_by_receiver: dict[int, set[int]] = defaultdict(set)
            for case, receiver, start in baseline:
                if case == key: starts_by_receiver[receiver].add(start)
            if set(starts_by_receiver) != {0, 1} or any(starts != expected_starts for starts in starts_by_receiver.values()):
                raise ValueError(f"baseline {key} must retain all 22 original 20 ms probe windows")
    rate_by_case = {}
    for row in baseline_rows:
        context = row.get("context", {})
        rate_by_case[case_id(row)] = _integer(context.get("rate_hz", context.get("sample_rate_hz")), "baseline rate_hz")
    baseline_positive = {window: [x for x in values if x.positive] for window, values in baseline.items()}
    baseline_positive = {window: values for window, values in baseline_positive.items() if values}
    arm_positive = {window: [x for x in values if x.positive] for window, values in arm.items()}
    arm_positive = {window: values for window, values in arm_positive.items() if values}
    evaluated = set(baseline_positive) & executed
    positive_again = set(baseline_positive) & set(arm_positive)
    candidate_matches = sum(_maximum_pairs(baseline_positive[window], arm_positive.get(window, ()), rate_by_case[window[0]]) for window in evaluated)
    baseline_candidate_count = sum(map(len, baseline_positive.values()))
    evaluated_candidate_count = sum(len(baseline_positive[x]) for x in evaluated)
    arm_positive_count = sum(map(len, arm_positive.values()))
    baseline_margin_boundary = sum(item.margin == MARGIN_GATE for values in baseline.values() for item in values)
    arm_margin_boundary = sum(item.margin == MARGIN_GATE for values in arm.values() for item in values)
    arm_complete_margin_boundary = sum(item.margin == MARGIN_GATE and item.positive is False for values in arm.values() for item in values)
    identity_windows = sum(_maximum_pairs(baseline_positive[window], arm_positive.get(window, ()), rate_by_case[window[0]]) > 0 for window in evaluated)
    report = {
        "schema": "leo.ds7.large-arm-score.v1", "oracle_truth_claimed": False,
        "cohort": {"planned_cases": len(planned), "baseline_cases": len(baseline_cases), "arm_cases": len(arm_cases)},
        "gates": {"baseline_positive": "passed_margin_gate (margin >= 0.025)", "arm_positive": "fractional_complete and margin > 0.025", "timing_gate_us": TIMING_GATE_US, "tracking_cfo_gate_hz": CFO_GATE_HZ},
        "windows": {"baseline_total": len(baseline), "baseline_positive": len(baseline_positive), "arm_ranked": len(ranked), "arm_executed": len(executed), "baseline_positive_evaluated": len(evaluated), "baseline_positive_positive_again_activity": len(positive_again), "matched_baseline_positive_windows_identity": identity_windows},
        "candidates": {"baseline_positive": baseline_candidate_count, "baseline_positive_evaluated": evaluated_candidate_count, "positive_candidate_identity_recovered_one_to_one": candidate_matches, "arm_positive": arm_positive_count, "arm_positive_unmatched_not_false_alarms": arm_positive_count - candidate_matches},
        "margin_boundary": {"threshold": MARGIN_GATE, "baseline_candidates_margin_exactly_threshold": baseline_margin_boundary, "arm_confirmation_candidates_margin_exactly_threshold": arm_margin_boundary, "arm_exact_threshold_candidates_not_positive_under_strict_gate": arm_complete_margin_boundary},
        "boundary_difference": "Original accepts margin == 0.025 through passed_margin_gate; ARM requires fractional_complete and strictly margin > 0.025.",
    }
    if _per_rate and input_contexts:
        per_rate = {}
        for rate in sorted({context["rate_hz"] for context in input_contexts.values()}):
            selected = {key for key, context in input_contexts.items() if context["rate_hz"] == rate}
            subset_inputs = dict(inputs, rows=[input_contexts[key] for key in input_contexts if key in selected])
            per_rate[str(rate)] = score(
                [row for row in baseline_rows if case_id(row) in selected],
                [row for row in arm_rows if case_id(row) in selected],
                subset_inputs, _per_rate=False,
            )
        report["per_rate"] = per_rate
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--arm", type=Path, required=True)
    parser.add_argument("--baseline-run", type=Path, required=True)
    parser.add_argument("--arm-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inputs = json.loads(args.inputs.read_text())
    expected = len(_inventory(inputs))
    _receipt(json.loads(args.baseline_run.read_text()), "baseline", expected, args.inputs, args.baseline)
    _receipt(json.loads(args.arm_run.read_text()), "ARM", expected, args.inputs, args.arm)
    report = score(_read(args.baseline), _read(args.arm), inputs)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

if __name__ == "__main__": main()
