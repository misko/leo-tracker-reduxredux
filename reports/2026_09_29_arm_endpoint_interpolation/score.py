"""Frozen full-cohort hit scorer for endpoint-interpolation experiments.

The native runner writes one JSON object per selected dwell with ``context`` and
22 ``rows``.  This scorer deliberately credits only margin-gated candidate
hits that maximum-cardinality match the sealed original baseline; it does not
turn unmatched candidate detections into truth labels.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping


SOURCE = Path(__file__).resolve().parent.parent / "2026_09_28_arm_full_optimization" / "independent_summary.py"
_spec = importlib.util.spec_from_file_location("frozen_original_hit_matcher", SOURCE)
audit = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(audit)

MARGIN_GATE = 0.025


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return float(value)


def _field(item: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in item:
            return item[name]
    raise ValueError(f"candidate missing {'/'.join(names)}")


def _candidate(item: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        raise ValueError("candidate must be an object")
    # refined_epoch and tracking CFO are the final local-GLRT coordinates.  The
    # unrefined epoch is retained only as provenance when both are emitted.
    epoch = _integer(_field(item, "refined_epoch", "epoch"), "candidate refined_epoch/epoch")
    tracking_cfo_hz = _finite(
        _field(item, "tracking_cfo_hz", "tracking_cfo", "trackingCFO"),
        "candidate tracking_cfo_hz",
    )
    margin = _finite(_field(item, "margin"), "candidate margin")
    normalized = dict(item)
    normalized.update(epoch=epoch, tracking_cfo_hz=tracking_cfo_hz, margin=margin)
    return normalized


def _kernel_calls(row: Mapping[str, Any]) -> int:
    instrumentation = row.get("instrumentation")
    if not isinstance(instrumentation, Mapping):
        raise ValueError("native window requires instrumentation object")
    calls = _integer(instrumentation.get("kernel_calls"), "instrumentation.kernel_calls")
    if calls < 0:
        raise ValueError("instrumentation.kernel_calls cannot be negative")
    return calls


def _instrumentation_integer(row: Mapping[str, Any], name: str) -> int:
    """Read optional native instrumentation without inventing a kernel count."""
    instrumentation = row.get("instrumentation")
    assert isinstance(instrumentation, Mapping)  # established by _kernel_calls
    value = instrumentation.get(name, 0)
    parsed = _integer(value, f"instrumentation.{name}")
    if parsed < 0:
        raise ValueError(f"instrumentation.{name} cannot be negative")
    return parsed


def _total_cpu_ms(row: Mapping[str, Any]) -> float:
    timing = row.get("timings_ms", {})
    if not isinstance(timing, Mapping):
        raise ValueError("native window timings_ms must be an object")
    value = _finite(timing.get("total_cpu", 0.0), "timings_ms.total_cpu")
    if value < 0:
        raise ValueError("timings_ms.total_cpu cannot be negative")
    return value


def load_native(path: Path, selected: list[dict]) -> dict[tuple[str, int], dict[tuple[int, int], dict]]:
    """Validate and normalize the runner's complete 22-window inventory."""
    expected = {(item["session_id"], item["visit_index"]): item for item in selected}
    result: dict[tuple[str, int], dict[tuple[int, int], dict]] = {}
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        record = json.loads(line)
        if not isinstance(record, Mapping):
            raise ValueError(f"line {line_number}: native dwell must be an object")
        context = record.get("context")
        if not isinstance(context, Mapping):
            raise ValueError(f"line {line_number}: native dwell lacks context")
        case = (context.get("session_id"), context.get("visit_index"))
        if case not in expected or case in result:
            raise ValueError(f"line {line_number}: unexpected or duplicate dwell")
        if context.get("sha256") != expected[case].get("sha256"):
            raise ValueError(f"line {line_number}: input hash differs")
        if record.get("returncode", 0) != 0 or record.get("stderr", ""):
            raise ValueError(f"line {line_number}: native execution failed")
        rows = record.get("rows")
        if not isinstance(rows, list):
            raise ValueError(f"line {line_number}: native dwell requires rows")
        windows: dict[tuple[int, int], dict] = {}
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError(f"line {line_number}: native window must be an object")
            key = (_integer(row.get("receiver_id"), "receiver_id"), _integer(row.get("probe_index"), "probe_index"))
            if key in windows:
                raise ValueError(f"line {line_number}: duplicate native window {key}")
            if key not in audit.WINDOW_KEYS:
                raise ValueError(f"line {line_number}: extra native window {key}")
            entries = row.get("candidates")
            if not isinstance(entries, list):
                raise ValueError(f"line {line_number}: native window candidates must be a list")
            declared = _integer(row.get("candidate_count"), "candidate_count")
            if declared != len(entries) or not 0 <= declared <= 16:
                raise ValueError(f"line {line_number}: candidate inventory must be 0..16 and exact")
            normalized = dict(row)
            normalized["candidates"] = [_candidate(item) for item in entries]
            normalized["kernel_calls"] = _kernel_calls(row)
            normalized["anchor_search_count"] = _instrumentation_integer(row, "anchor_search_count")
            normalized["middle_glrt_kernel_attempts"] = _instrumentation_integer(
                row, "middle_glrt_kernel_attempts"
            )
            fallback_used = row["instrumentation"].get("fallback_used", False)
            if not isinstance(fallback_used, bool):
                raise ValueError("instrumentation.fallback_used must be boolean")
            normalized["fallback_used"] = fallback_used
            normalized["total_cpu_ms"] = _total_cpu_ms(row)
            windows[key] = normalized
        missing = sorted(audit.WINDOW_KEYS - windows.keys())
        if missing:
            raise ValueError(f"line {line_number}: missing native windows {missing}")
        result[case] = windows
    missing_cases = expected.keys() - result.keys()
    if missing_cases:
        raise ValueError(f"missing native dwells: {sorted(missing_cases)}")
    return result


def _counts() -> dict[str, int]:
    return dict(dwells=0, windows=0, candidate_entries=0, actual_glrt_kernel_attempts=0,
                windows_with_glrt_attempts=0, windows_without_glrt_attempts=0,
                full_search_windows=0, local_search_windows=0, total_cpu_ms=0.0,
                reference_positive_windows=0, native_positive_windows=0,
                windows_with_recovered_hit=0, reference_positive_hits=0,
                native_positive_hits=0, recovered_positive_hits=0,
                unmatched_positive_hits=0, unrecovered_reference_positive_hits=0)


def _add(counts: dict[str, int], reference: list[dict], candidate: list[dict], row: Mapping[str, Any]) -> None:
    matched = audit.maximum_matches(reference, candidate)
    counts["reference_positive_windows"] += bool(reference)
    counts["native_positive_windows"] += bool(candidate)
    counts["windows_with_recovered_hit"] += bool(matched)
    counts["reference_positive_hits"] += len(reference)
    counts["native_positive_hits"] += len(candidate)
    counts["recovered_positive_hits"] += matched
    counts["unmatched_positive_hits"] += len(candidate) - matched
    counts["unrecovered_reference_positive_hits"] += len(reference) - matched
    calls = row["kernel_calls"]
    counts["actual_glrt_kernel_attempts"] += calls
    counts["windows_with_glrt_attempts"] += calls > 0
    counts["windows_without_glrt_attempts"] += calls == 0
    counts["full_search_windows"] += row["anchor_search_count"] + bool(row["fallback_used"])
    counts["local_search_windows"] += row["middle_glrt_kernel_attempts"] > 0
    counts["total_cpu_ms"] += row["total_cpu_ms"]


def score(folder: Path, baseline: Path) -> dict:
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    selected = manifest.get("selected")
    if not isinstance(selected, list) or not manifest.get("complete"):
        raise ValueError("manifest must be complete with selected dwells")
    if manifest.get("processed_dwells") != len(selected):
        raise ValueError("manifest processed dwell count differs")
    cases = [(item.get("session_id"), item.get("visit_index")) for item in selected]
    if len(cases) != len(set(cases)):
        raise ValueError("manifest selected dwells are duplicated")
    native_path = folder / "rows.jsonl"
    if manifest.get("rows_sha256") is not None and manifest["rows_sha256"] != sha256(native_path):
        raise ValueError("native rows hash differs from completed manifest")
    native = load_native(native_path, selected)
    frozen = audit.load_baseline(baseline)
    totals = _counts()
    by_rate: dict[int, dict[str, int]] = defaultdict(_counts)
    for context in selected:
        case = (context["session_id"], context["visit_index"])
        reference_windows = frozen.get(case)
        if reference_windows is None or set(reference_windows) != audit.WINDOW_KEYS:
            raise ValueError(f"sealed baseline window inventory differs: {case}")
        rate = _integer(context.get("rate_hz"), "context rate_hz")
        for counts in (totals, by_rate[rate]):
            counts["dwells"] += 1
        for key in sorted(audit.WINDOW_KEYS):
            expected = reference_windows[key].get("candidates")
            if not isinstance(expected, list) or len(expected) != 8:
                raise ValueError(f"sealed baseline candidate inventory differs: {case} {key}")
            row = native[case][key]
            actual = row["candidates"]
            reference_hits = [item for item in expected if float(item["margin"]) >= MARGIN_GATE]
            native_hits = [item for item in actual if item["margin"] >= MARGIN_GATE]
            for counts in (totals, by_rate[rate]):
                counts["windows"] += 1
                counts["candidate_entries"] += len(actual)
                _add(counts, reference_hits, native_hits, row)
    for counts in (totals, *by_rate.values()):
        counts["hit_recovery_fraction"] = (counts["recovered_positive_hits"] / counts["reference_positive_hits"]
                                           if counts["reference_positive_hits"] else None)
        counts["mean_cpu_ms_per_dwell"] = counts["total_cpu_ms"] / counts["dwells"] if counts["dwells"] else None
    return {
        "schema": "arm-endpoint-interpolation-frozen-hit-audit/v1",
        "scope": "Margin-gated candidate hits, one-to-one maximum-cardinality association within the frozen <=2-sample and <=8-kHz gates.",
        "mode": manifest.get("mode"),
        "margin_gate": MARGIN_GATE,
        "totals": totals,
        "by_rate": {str(rate): counts for rate, counts in sorted(by_rate.items())},
        "source_sha256": {"score.py": sha256(Path(__file__)), "frozen_matcher": sha256(SOURCE)},
        "manifest_sha256": sha256(manifest_path),
        "native_sha256": sha256(native_path),
        "baseline_sha256": sha256(baseline),
        "kernel_attempt_accounting": "Sum native rows[].instrumentation.kernel_calls; candidate_entries are intentionally not used as a proxy.",
        "cpu_accounting": "Sum each native rows[].timings_ms.total_cpu once; stage timings are not summed.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--baseline", type=Path,
                        default=Path("reports/2026_09_28_ds7_large_arm/baseline-01/rows.jsonl"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = score(args.cohort, args.baseline)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["totals"], indent=2))


if __name__ == "__main__":
    main()
