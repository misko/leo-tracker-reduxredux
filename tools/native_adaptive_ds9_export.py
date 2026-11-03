#!/usr/bin/env python3
"""Build hash-bound DS9 detector fixtures, compare evidence, and run replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import BinaryIO

ROOT = Path(__file__).resolve().parents[1]
COMPARISON = ROOT / "reports/2026_09_30_arm_ds9_native_comparison"
LOCATION = ROOT / "reports/2026_09_30_arm_location_prototype"
DEFAULT_PANEL = COMPARISON / "panel.json"
DEFAULT_ARCHIVE = COMPARISON / "local/inputs.tar"
DEFAULT_LOCATION_SOURCE = Path("/var/tmp/leo-arm-ds89-validation/inputs")
LOCATION_SESSION = "scan-fw-3cfdaa6d75762cad"
FRACTIONAL_MARGIN_GATE = 0.025


def sha256_stream(stream: BinaryIO) -> str:
    value = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        value.update(block)
    return value.hexdigest()


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return sha256_stream(stream)


def write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def refuse_qnap_output(path: Path) -> None:
    resolved = path.resolve()
    qnap = Path("/mnt/qnap01")
    if resolved == qnap or qnap in resolved.parents:
        raise ValueError("DS9 export output cannot be beneath read-only QNAP")


def scientific_rows(result: dict[str, object]) -> list[dict[str, object]]:
    return [
        {key: value for key, value in row.items() if key != "timings_ms"}
        for row in result["rows"]  # type: ignore[index,union-attr]
    ]


def result_lines(path: Path) -> list[dict[str, object]]:
    rows = []
    for line in path.read_text().splitlines():
        document = json.loads(line)
        if document.get("result", {}).get("kind") == "call":
            rows.append(document)
    return rows


def _native_calls(paths: list[Path]) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []
    for path in paths:
        for wrapper in result_lines(path):
            result = wrapper["result"]
            metadata = json.loads(result["metadata"])  # type: ignore[index]
            for row in result["rows"]:  # type: ignore[index,union-attr]
                calls.append(
                    {
                        "session_id": metadata["session_id"],
                        "visit_index": metadata["visit_index"],
                        "receiver_id": row["receiver_id"],
                        "sample_rate_hz": result["rate_hz"],  # type: ignore[index]
                        "call_cpu_ms": result["call_cpu_ms"],  # type: ignore[index]
                        "proposal_tracking_fallback": row["proposal_tracking_fallback"],
                        "candidates": row["candidates"],
                    }
                )
    keys = [
        (row["session_id"], row["visit_index"], row["receiver_id"])
        for row in calls
    ]
    if len(keys) != len(set(keys)):
        raise ValueError("native comparison input repeats a receiver row")
    return calls


def _circular_epoch_distance(left: int, right: int, epoch_count: int) -> int:
    distance = abs(left - right)
    return min(distance, epoch_count - distance)


def _one_to_one_candidate_matches(
    native: list[dict[str, object]],
    server: list[dict[str, object]],
    epoch_count: int,
) -> list[tuple[int, int]]:
    """Deterministic minimum-cost greedy matching with no reused endpoint."""
    edges = []
    for native_index, candidate in enumerate(native):
        fractional = candidate["fractional_epoch"]
        if fractional["status"] != "complete":  # type: ignore[index]
            continue
        for server_index, reference in enumerate(server):
            epoch_delta = _circular_epoch_distance(
                int(candidate["epoch"]), int(reference["integer_epoch_sample"]), epoch_count
            )
            cfo_delta = abs(
                float(candidate["acquired_cfo_hz"])
                - float(reference["acquired_cfo_hz"])
            )
            if epoch_delta <= 2 and cfo_delta <= 10_000.0:
                edges.append(
                    (
                        epoch_delta,
                        cfo_delta,
                        int(reference["candidate_rank"]),
                        native_index,
                        server_index,
                    )
                )
    used_native: set[int] = set()
    used_server: set[int] = set()
    matches = []
    for _, _, _, native_index, server_index in sorted(edges):
        if native_index in used_native or server_index in used_server:
            continue
        used_native.add(native_index)
        used_server.add(server_index)
        matches.append((native_index, server_index))
    if len({native_index for native_index, _ in matches}) != len(matches):
        raise AssertionError("one-to-one matcher reused a native candidate")
    if len({server_index for _, server_index in matches}) != len(matches):
        raise AssertionError("one-to-one matcher reused a server candidate")
    return matches


def _statistics(values: list[float]) -> dict[str, object]:
    return {
        "count": len(values),
        "mean": sum(values) / len(values) if values else None,
        "maximum": max(values) if values else None,
    }


def compare_fractional_cohort(
    native_paths: list[Path], oracle_path: Path, cohort: str
) -> dict[str, object]:
    """Compare native and deployed candidates with audited one-to-one pairing."""
    native_rows = _native_calls(native_paths)
    oracle = json.loads(oracle_path.read_text())
    oracle_by_key = {
        (row["session_id"], row["visit_index"], row["probe"]["receiver_id"]): row
        for row in oracle["rows"]
    }
    details = []
    deltas: dict[str, list[float]] = {
        name: []
        for name in (
            "integer_epoch_samples",
            "acquired_cfo_hz",
            "fractional_offset_samples",
            "exact_score",
            "control_score",
            "margin",
            "tracking_cfo_hz",
        )
    }
    totals = {
        "native": 0,
        "native_complete": 0,
        "native_gate": 0,
        "server": 0,
        "server_unavailable": 0,
        "server_gate": 0,
        "matched": 0,
        "matched_native_gate": 0,
        "matched_server_gate": 0,
    }
    miss_causes: dict[str, int] = {}
    call_cpu_ms: dict[tuple[object, object], float] = {}
    for native_row in native_rows:
        key = (
            native_row["session_id"],
            native_row["visit_index"],
            native_row["receiver_id"],
        )
        if key not in oracle_by_key:
            raise ValueError(f"server oracle is missing native row {key}")
        oracle_row = oracle_by_key[key]
        server = oracle_row["probe"]["candidates"]
        unavailable = oracle_row["probe"]["unavailable_candidates"]
        native = native_row["candidates"]
        epoch_count = round(int(native_row["sample_rate_hz"]) / 750)
        matches = _one_to_one_candidate_matches(native, server, epoch_count)
        matched_native = {pair[0] for pair in matches}
        matched_server = {pair[1] for pair in matches}
        totals["native"] += len(native)
        totals["native_complete"] += sum(
            candidate["fractional_epoch"]["status"] == "complete" for candidate in native
        )
        totals["native_gate"] += sum(
            candidate["fractional_epoch"]["status"] == "complete"
            and candidate["fractional_epoch"]["margin"] >= FRACTIONAL_MARGIN_GATE
            for candidate in native
        )
        totals["server"] += len(server)
        totals["server_unavailable"] += len(unavailable)
        totals["server_gate"] += sum(
            bool(candidate["passed_fractional_margin_gate"]) for candidate in server
        )
        totals["matched"] += len(matches)
        row_matches = []
        for native_index, server_index in matches:
            candidate = native[native_index]
            reference = server[server_index]
            fractional = candidate["fractional_epoch"]
            native_gate = fractional["margin"] >= FRACTIONAL_MARGIN_GATE
            server_gate = bool(reference["passed_fractional_margin_gate"])
            totals["matched_native_gate"] += int(native_gate)
            totals["matched_server_gate"] += int(server_gate)
            values = {
                "integer_epoch_samples": _circular_epoch_distance(
                    int(candidate["epoch"]),
                    int(reference["integer_epoch_sample"]),
                    epoch_count,
                ),
                "acquired_cfo_hz": float(candidate["acquired_cfo_hz"])
                - float(reference["acquired_cfo_hz"]),
                "fractional_offset_samples": float(fractional["offset_samples"])
                - float(reference["fractional_epoch_offset_samples"]),
                "exact_score": float(fractional["exact_score"])
                - float(reference["fractional_exact_score"]),
                "control_score": float(fractional["control_score"])
                - float(reference["fractional_control_score"]),
                "margin": float(fractional["margin"])
                - float(reference["fractional_margin"]),
                "tracking_cfo_hz": float(fractional["tracking_cfo_hz"])
                - float(reference["fractional_tracking_cfo_hz"]),
            }
            for name, value in values.items():
                deltas[name].append(abs(float(value)))
            row_matches.append(
                {
                    "native_candidate_index": native_index,
                    "server_candidate_rank": reference["candidate_rank"],
                    "native_passed_gate": native_gate,
                    "server_passed_gate": server_gate,
                    "native_minus_server": values,
                }
            )
        if len({row["native_candidate_index"] for row in row_matches}) != len(row_matches):
            raise AssertionError("detail row repeats a native candidate")
        if len({row["server_candidate_rank"] for row in row_matches}) != len(row_matches):
            raise AssertionError("detail row repeats a server candidate")
        for server_index, reference in enumerate(server):
            if server_index in matched_server or not reference["passed_fractional_margin_gate"]:
                continue
            epoch_near = [
                candidate
                for candidate in native
                if _circular_epoch_distance(
                    int(candidate["epoch"]),
                    int(reference["integer_epoch_sample"]),
                    epoch_count,
                )
                <= 2
            ]
            cfo_near = [
                candidate
                for candidate in epoch_near
                if abs(
                    float(candidate["acquired_cfo_hz"])
                    - float(reference["acquired_cfo_hz"])
                )
                <= 10_000.0
            ]
            if not epoch_near:
                cause = "epoch_absent_after_native_inventory"
            elif not cfo_near:
                cause = "epoch_present_acquired_cfo_diff_gt_10k"
            elif not any(
                candidate["fractional_epoch"]["status"] == "complete"
                for candidate in cfo_near
            ):
                cause = "native_fractional_unbracketed"
            else:
                cause = "server_hypothesis_has_no_distinct_native_candidate"
            miss_causes[cause] = miss_causes.get(cause, 0) + 1
        details.append(
            {
                "session_id": key[0],
                "visit_index": key[1],
                "receiver_id": key[2],
                "matches": row_matches,
                "native_unmatched_candidate_indices": sorted(
                    set(range(len(native))) - matched_native
                ),
                "server_unmatched_candidate_ranks": [
                    server[index]["candidate_rank"]
                    for index in range(len(server))
                    if index not in matched_server
                ],
            }
        )
        call_cpu_ms[(key[0], key[1])] = float(native_row["call_cpu_ms"])
    missing_oracle = set(oracle_by_key) - {
        (row["session_id"], row["visit_index"], row["receiver_id"])
        for row in native_rows
    }
    # The oracle also contains the other declared cohort; only require that all
    # native rows were found, rather than consuming unrelated rows.
    del missing_oracle
    if totals["matched"] > min(totals["native_complete"], totals["server"]):
        raise AssertionError("matched total exceeds a candidate inventory")
    if totals["matched_server_gate"] > totals["server_gate"]:
        raise AssertionError("matched server positives exceed server positives")
    if totals["matched_native_gate"] > totals["native_gate"]:
        raise AssertionError("matched native positives exceed native positives")
    summary = {
        "schema": "org.leo.native-adaptive-fractional-cohort-comparison/v4",
        "cohort": cohort,
        "matching_rule": (
            "one-to-one greedy minimum (circular epoch delta, acquired CFO delta, "
            "server rank, native index); epoch <=2 samples and acquired CFO <=10000 Hz"
        ),
        "one_to_one_invariants_verified": True,
        "probe_row_count": len(native_rows),
        "call_count": len(call_cpu_ms),
        "native_candidate_count": totals["native"],
        "native_complete_candidate_count": totals["native_complete"],
        "native_gate_candidate_count": totals["native_gate"],
        "server_candidate_count": totals["server"],
        "server_unavailable_candidate_count": totals["server_unavailable"],
        "server_gate_candidate_count": totals["server_gate"],
        "matched_candidate_count": totals["matched"],
        "matched_native_gate_candidate_count": totals["matched_native_gate"],
        "matched_server_gate_candidate_count": totals["matched_server_gate"],
        "server_gate_candidate_recall": (
            totals["matched_server_gate"] / totals["server_gate"]
            if totals["server_gate"]
            else None
        ),
        "native_complete_match_precision": (
            totals["matched"] / totals["native_complete"]
            if totals["native_complete"]
            else None
        ),
        "server_gate_miss_causes": dict(sorted(miss_causes.items())),
        "absolute_deltas_for_matches": {
            name: _statistics(values) for name, values in deltas.items()
        },
        "call_cpu_ms": _statistics(list(call_cpu_ms.values())),
    }
    return {"rows": details, "summary": summary}


def compare_deployed_wrapper_strict(
    native_paths: list[Path], oracle_path: Path
) -> dict[str, object]:
    """Compare wrapper output by the deployed candidate-rank contract."""
    oracle = json.loads(oracle_path.read_text())
    oracle_by_key = {
        (row["session_id"], row["visit_index"], row["probe"]["receiver_id"]): row["probe"]
        for row in oracle["rows"]
    }
    tolerances = {
        "acquired_cfo_hz": 1e-6,
        "integer_score": 1e-10,
        "fractional_offset_samples": 1e-10,
        "fractional_score": 1e-10,
        "fractional_cfo_hz": 1e-6,
    }
    maxima = {name: 0.0 for name in tolerances}
    counts = {
        "probe_rows": 0,
        "candidate_ranks": 0,
        "complete_ranks": 0,
        "unavailable_ranks": 0,
        "server_gate_ranks": 0,
        "native_gate_ranks": 0,
        "peer_fallback_rows": 0,
        "missing_ranks": 0,
        "additional_ranks": 0,
        "availability_mismatches": 0,
        "epoch_mismatches": 0,
        "gate_mismatches": 0,
        "numerical_tolerance_mismatches": 0,
        "tolerance_match_off_diagonal_pairs": 0,
    }
    details: list[dict[str, object]] = []
    seen: set[tuple[str, int, int]] = set()
    for native in _native_calls(native_paths):
        key = (native["session_id"], native["visit_index"], native["receiver_id"])
        if key not in oracle_by_key or key in seen:
            raise ValueError(f"unexpected or repeated native row: {key}")
        seen.add(key)
        server = oracle_by_key[key]
        server_complete = {item["candidate_rank"]: item for item in server["candidates"]}
        server_unavailable = {
            item["candidate_rank"]: item for item in server["unavailable_candidates"]
        }
        expected_count = int(server["candidate_count"])
        candidates = native["candidates"]
        counts["probe_rows"] += 1
        counts["candidate_ranks"] += expected_count
        counts["peer_fallback_rows"] += int(bool(native["proposal_tracking_fallback"]))
        counts["missing_ranks"] += max(0, expected_count - len(candidates))
        counts["additional_ranks"] += max(0, len(candidates) - expected_count)
        epoch_count = round(int(native["sample_rate_hz"]) / 750)
        counts["tolerance_match_off_diagonal_pairs"] += sum(
            native_rank
            != int(server["candidates"][server_index]["candidate_rank"])
            for native_rank, server_index in _one_to_one_candidate_matches(
                candidates, server["candidates"], epoch_count
            )
        )
        row_issues = []
        for rank in range(min(expected_count, len(candidates))):
            candidate = candidates[rank]
            fractional = candidate["fractional_epoch"]
            status = fractional["status"]
            if rank in server_unavailable:
                counts["unavailable_ranks"] += 1
                if status != server_unavailable[rank]["fractional_epoch_status"]:
                    counts["availability_mismatches"] += 1
                    row_issues.append({"rank": rank, "issue": "availability"})
                continue
            reference = server_complete.get(rank)
            counts["complete_ranks"] += 1
            if reference is None or status != "complete":
                counts["availability_mismatches"] += 1
                row_issues.append({"rank": rank, "issue": "availability"})
                continue
            if int(candidate["epoch"]) != int(reference["integer_epoch_sample"]):
                counts["epoch_mismatches"] += 1
                row_issues.append({"rank": rank, "issue": "integer_epoch"})
            server_gate = bool(reference["passed_fractional_margin_gate"])
            native_gate = float(fractional["margin"]) >= FRACTIONAL_MARGIN_GATE
            counts["server_gate_ranks"] += int(server_gate)
            counts["native_gate_ranks"] += int(native_gate)
            if server_gate != native_gate:
                counts["gate_mismatches"] += 1
                row_issues.append({"rank": rank, "issue": "fractional_gate"})
            comparisons = {
                "acquired_cfo_hz": abs(
                    float(candidate["acquired_cfo_hz"])
                    - float(reference["acquired_cfo_hz"])
                ),
                "integer_score": max(
                    abs(float(candidate["exact_score"]) - float(reference["integer_exact_score"])),
                    abs(
                        float(candidate["control_score"])
                        - float(reference["integer_control_score"])
                    ),
                    abs(float(candidate["margin"]) - float(reference["integer_margin"])),
                ),
                "fractional_offset_samples": abs(
                    float(fractional["offset_samples"])
                    - float(reference["fractional_epoch_offset_samples"])
                ),
                "fractional_score": max(
                    abs(
                        float(fractional["exact_score"])
                        - float(reference["fractional_exact_score"])
                    ),
                    abs(
                        float(fractional["control_score"])
                        - float(reference["fractional_control_score"])
                    ),
                    abs(
                        float(fractional["margin"])
                        - float(reference["fractional_margin"])
                    ),
                ),
                "fractional_cfo_hz": max(
                    abs(
                        float(fractional["residual_cfo_hz"])
                        - float(reference["fractional_residual_cfo_hz"])
                    ),
                    abs(
                        float(fractional["tracking_cfo_hz"])
                        - float(reference["fractional_tracking_cfo_hz"])
                    ),
                ),
            }
            for name, delta in comparisons.items():
                maxima[name] = max(maxima[name], delta)
                if delta > tolerances[name]:
                    counts["numerical_tolerance_mismatches"] += 1
                    row_issues.append({"rank": rank, "issue": name, "delta": delta})
        if row_issues:
            details.append(
                {
                    "session_id": key[0],
                    "visit_index": key[1],
                    "receiver_id": key[2],
                    "issues": row_issues,
                }
            )
    relevant_oracle = {
        key for key in oracle_by_key if key[:2] in {(item[0], item[1]) for item in seen}
    }
    missing_rows = sorted(relevant_oracle - seen)
    passed = not missing_rows and not details and all(
        counts[name] == 0
        for name in (
            "missing_ranks",
            "additional_ranks",
            "availability_mismatches",
            "epoch_mismatches",
            "gate_mismatches",
            "numerical_tolerance_mismatches",
        )
    )
    return {
        "schema": "org.leo.native-adaptive-deployed-wrapper-strict-comparison/v1",
        "fractional_margin_gate": FRACTIONAL_MARGIN_GATE,
        "tolerances": tolerances,
        "maximum_absolute_deltas": maxima,
        "rank_comparison": (
            "Direct candidate-array index versus deployed candidate_rank. The separate "
            "tolerance matcher can cross equally refined duplicate hypotheses."
        ),
        "counts": counts,
        "missing_probe_rows": [list(key) for key in missing_rows],
        "rows_with_issues": details,
        "saved_panel_scientific_parity_passed": passed,
        "production_capability_parity_qualified": False,
    }


def regenerate_fractional_comparisons(report: Path) -> dict[str, object]:
    oracle = report / "deployed-fractional-oracle.json"
    ordinary = compare_fractional_cohort(
        sorted(report.glob("arm-cached-*.jsonl")), oracle, "portable80-2.5MS-saved-selection"
    )
    location = compare_fractional_cohort(
        [report / "location-selection/native-fractional.jsonl"],
        oracle,
        "location-four-visit-host-result",
    )
    combined = {
        "schema": "org.leo.native-adaptive-fractional-server-comparison/v4",
        "baseline_fractional_margin_gate": FRACTIONAL_MARGIN_GATE,
        "oracle_source": "public read-only persisted analysis export",
        "cohorts": [ordinary, location],
        "limitations": [
            "Candidate ranks are local to different acquisition algorithms.",
            "Matching is audited one-to-one under declared epoch and CFO tolerances.",
            "The portable cohort is the saved 80-dwell selection, not every DS9 visit.",
            "The location cohort is four visits, not the complete 2,215-visit scan.",
        ],
    }
    write_json(report / "fractional-server-comparison.json", combined)
    summary = {**combined, "cohorts": [entry["summary"] for entry in combined["cohorts"]]}
    write_json(report / "fractional-server-comparison-summary.json", summary)
    coverage = compare_fractional_cohort(
        sorted((report / "portable80").glob("server-coverage-*.jsonl")),
        oracle,
        "portable80-server-coverage-host",
    )
    coverage_document = {
        "rows": coverage["rows"],
        "summary": {
            **coverage["summary"],
            "schema": "org.leo.native-adaptive-server-coverage-comparison/v2",
            "mode": "separate-server-coverage-fractional",
            "baseline_fractional_margin_gate": FRACTIONAL_MARGIN_GATE,
            "server_parity_qualified": False,
            "limitations": [
                "This mode does not port the deployed Python symbolwise acquisition.",
                "Timing is host CPU evidence, not ARM or realtime evidence.",
            ],
        },
    }
    write_json(report / "server-coverage-comparison.json", coverage_document)
    return {
        "ordinary": ordinary["summary"],
        "location": location["summary"],
        "coverage": coverage_document["summary"],
    }


def regenerate_deployed_wrapper_comparison(report: Path) -> dict[str, object]:
    paths = sorted(report.glob("deployed-wrapper-*.jsonl"))
    if not paths:
        raise FileNotFoundError("no deployed-wrapper JSONL inputs")
    oracle = report / "deployed-fractional-oracle.json"
    comparison = compare_fractional_cohort(
        paths, oracle, "portable80-deployed-server-wrapper-host"
    )
    summary = {
        **comparison["summary"],
        "schema": "org.leo.native-adaptive-deployed-server-wrapper-comparison/v1",
        "mode": "deployed-server-wrapper-fractional",
        "baseline_fractional_margin_gate": FRACTIONAL_MARGIN_GATE,
        "server_parity_qualified": False,
        "implementation": {
            "per_visit_search_geometry": True,
            "retained_candidate_count": 8,
            "candidate_epoch_separation_samples": 5,
            "candidate_cfo_separation_hz": 10_000.0,
            "normal_anchor_symbols": list(range(2, 302, 26)),
            "peer_fallback_anchor_symbols": list(range(2, 302, 14)),
            "peer_fallback_trigger": (
                "either receiver has complete fractional margin >= 0.025 and peer does not"
            ),
        },
        "inputs": [{"file": path.name, "sha256": sha256_file(path)} for path in paths],
        "limitations": [
            "Host saved-IQ evidence is not ARM timing or realtime evidence.",
            (
                "Tolerance matching can cross duplicate hypotheses; candidate-rank identity "
                "is assessed by the strict comparison."
            ),
            "Production capability parity remains false pending integration qualification.",
        ],
    }
    document = {"rows": comparison["rows"], "summary": summary}
    write_json(report / "deployed-server-wrapper-comparison.json", document)
    write_json(report / "deployed-server-wrapper-comparison-summary.json", summary)
    strict = compare_deployed_wrapper_strict(paths, oracle)
    write_json(report / "deployed-server-wrapper-strict-comparison.json", strict)
    return {"tolerance_comparison": summary, "strict_rank_comparison": strict}


def compare_deployed_wrapper_result_directory(
    native_directory: Path, oracle: Path
) -> dict[str, object]:
    paths = sorted(native_directory.glob("*.jsonl"))
    if not paths:
        raise FileNotFoundError("native result directory has no JSONL inputs")
    tolerance = compare_fractional_cohort(
        paths, oracle, "portable80-deployed-server-wrapper-arm"
    )["summary"]
    strict = compare_deployed_wrapper_strict(paths, oracle)
    return {
        "schema": "org.leo.native-adaptive-deployed-wrapper-result-comparison/v1",
        "inputs": [
            {"file": path.name, "sha256": sha256_file(path)} for path in paths
        ],
        "tolerance_comparison": tolerance,
        "strict_rank_comparison": strict,
    }


def compare_arm_panel(comparison: Path = COMPARISON) -> dict[str, object]:
    local = comparison / "local"
    mismatches: list[dict[str, object]] = []
    calls = 0
    candidates = 0
    refinement_skipped = 0
    for control_path in sorted(local.glob("control-*.jsonl")):
        suffix = control_path.name.removeprefix("control-")
        ordinary_path = local / ("ordinary-" + suffix)
        if not ordinary_path.is_file():
            raise FileNotFoundError(ordinary_path)
        control = result_lines(control_path)
        ordinary = result_lines(ordinary_path)
        if len(control) != len(ordinary):
            mismatches.append(
                {
                    "group": suffix,
                    "reason": "call-count",
                    "control": len(control),
                    "ordinary": len(ordinary),
                }
            )
            continue
        for index, (reference, actual) in enumerate(zip(control, ordinary, strict=True)):
            calls += 1
            expected_result = reference["result"]
            actual_result = actual["result"]
            if scientific_rows(expected_result) != scientific_rows(actual_result):  # type: ignore[arg-type]
                mismatches.append({"group": suffix, "call_index": index})
            for row in expected_result["rows"]:  # type: ignore[index,union-attr]
                for candidate in row["candidates"]:
                    candidates += 1
                    refinement_skipped += int(candidate["refinement_skipped"])
    return {
        "schema": "org.leo.native-adaptive-detector-arm-parity/v1",
        "comparison": "ordinary-versus-native-control",
        "calls": calls,
        "candidate_entries_across_repetitions": candidates,
        "refinement_skipped_entries_across_repetitions": refinement_skipped,
        "mismatches": mismatches,
        "passed": not mismatches and calls == 800,
    }


def portable_manifest(panel_path: Path, archive_path: Path) -> dict[str, object]:
    panel = json.loads(panel_path.read_text())
    if len(panel["cases"]) != 80:
        raise ValueError("DS9 detector panel must contain exactly 80 cases")
    required: dict[str, str] = {}
    for edge, roles in panel["templates"].items():
        for role_name, role in roles.items():
            required[f"{edge}-{role_name}.c128"] = role["sha256"]
    for case in panel["cases"]:
        required[case["raw_file"]] = case["raw_sha256"]
    with tarfile.open(archive_path, "r") as archive:
        names = {member.name: member for member in archive.getmembers() if member.isfile()}
        for name, expected in required.items():
            if name not in names:
                raise ValueError(f"fixture archive is missing {name}")
            stream = archive.extractfile(names[name])
            if stream is None or sha256_stream(stream) != expected:
                raise ValueError(f"fixture archive hash mismatch: {name}")
    cases = []
    for case in panel["cases"]:
        cases.append(
            {
                key: case[key]
                for key in (
                    "ordinal",
                    "dataset_id",
                    "session_id",
                    "visit_index",
                    "manifest_sha256",
                    "sample_start_counter",
                    "sample_end_counter",
                    "rate_hz",
                    "target_index",
                    "target",
                    "actual_lo_frequency_hz",
                    "actual_if_offset_hz",
                    "shape",
                    "dtype",
                    "raw_file",
                    "raw_sha256",
                )
            }
        )
    return {
        "schema": "org.leo.native-adaptive-detector-fixture/v1",
        "dataset_id": "DS9",
        "profile": {"dwell_ms": 120, "probe_ms": 20, "probe_stride_ms": 120},
        "selection": panel["selection"],
        "source_panel": panel_path.relative_to(ROOT).as_posix(),
        "source_panel_sha256": sha256_file(panel_path),
        "source_archive": archive_path.relative_to(ROOT).as_posix(),
        "source_archive_sha256": sha256_file(archive_path),
        "input_manifest_sha256": panel["input_manifest_sha256"],
        "templates": panel["templates"],
        "case_count": len(cases),
        "session_count": len({case["session_id"] for case in cases}),
        "cases": cases,
    }


def export_location(source: Path, output: Path) -> dict[str, object]:
    refuse_qnap_output(output)
    import numpy as np

    batch_path = source / f"batches/ds9-{LOCATION_SESSION}.json"
    batch = json.loads(batch_path.read_text())
    if not batch["complete"] or batch["expected_rows"] != 4 or len(batch["rows"]) != 4:
        raise ValueError("saved lag-discovery selection is incomplete")
    raw_directory = output / "raw"
    raw_directory.mkdir(parents=True, exist_ok=True)
    exported_rows = []
    for row in batch["rows"]:
        npy_path = source / row["file"]
        if sha256_file(npy_path) != row["sha256"]:
            raise ValueError(f"source NPY hash mismatch: {npy_path}")
        values = np.load(npy_path, mmap_mode="r", allow_pickle=False)
        if values.dtype != np.dtype("<i2") or list(values.shape) != row["shape"]:
            raise ValueError(f"source NPY layout mismatch: {npy_path}")
        raw_name = f"{LOCATION_SESSION}-{row['visit_index']}.ci16"
        raw_path = raw_directory / raw_name
        temporary = raw_path.with_name(raw_path.name + ".partial")
        with temporary.open("wb") as stream:
            stream.write(values.tobytes(order="C"))
        temporary.replace(raw_path)
        actual_raw_hash = sha256_file(raw_path)
        exported_rows.append(
            {
                **{key: value for key, value in row.items() if key not in {"file", "sha256"}},
                "source_npy_sha256": row["sha256"],
                "source_npy_file": row["file"],
                "raw_file": f"raw/{raw_name}",
                "raw_sha256": actual_raw_hash,
                "raw_bytes": raw_path.stat().st_size,
                "sample_layout": "sample-receiver-iq-ci16le",
            }
        )
    references = {
        "location_inputs": LOCATION / "inputs.json",
        "server_analysis": Path(
            "/var/tmp/leo-arm-realtime-publication/reports/2026_09_28_ds9_post_ds8/analysis"
        )
        / f"{LOCATION_SESSION}.json",
        "capture_pose": Path(
            "/var/tmp/leo-arm-realtime-publication/reports/2026_09_28_ds9_post_ds8/pose"
        )
        / f"{LOCATION_SESSION}.json",
    }
    copied_references = {}
    for label, reference in references.items():
        if not reference.is_file():
            copied_references[label] = {"available": False, "source": os.fspath(reference)}
            continue
        destination = output / (label + ".json")
        shutil.copyfile(reference, destination)
        copied_references[label] = {
            "available": True,
            "file": destination.relative_to(output).as_posix(),
            "sha256": sha256_file(destination),
            "source": os.fspath(reference),
        }
    manifest = {
        "schema": "org.leo.native-adaptive-location-selection/v1",
        "dataset_id": "DS9",
        "session_id": LOCATION_SESSION,
        "complete_scan": False,
        "selection_complete": True,
        "selection_purpose": "saved-lag-discovery-subset",
        "source_batch": os.fspath(batch_path),
        "source_batch_sha256": sha256_file(batch_path),
        "manifest_sha256": batch["manifest_sha256"],
        "selected_visit_count": 4,
        "selected_visit_indices": [row["visit_index"] for row in exported_rows],
        "rows": exported_rows,
        "references": copied_references,
        "gaps": [
            (
                "This is four selected visits, not the original session visit inventory "
                "or a complete scan."
            ),
            (
                "The source complete flag means only that the four-row lag-discovery "
                "selection was saved completely."
            ),
            (
                "The original capture manifest and all original visits still require "
                "read-only export through the public capture store."
            ),
            "No 7.5 MS/s lower-edge template is included in this export.",
            (
                "The saved location reference was produced by the server pipeline, "
                "not this native detector."
            ),
            "Raw CI16 files are local ignored artifacts; verify each hash before use.",
        ],
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def inventory_location_store(bulk_root: Path, output: Path) -> dict[str, object]:
    """Export complete capture metadata through the read-only public store."""
    refuse_qnap_output(output)
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    store = AdaptiveHopIqStore(bulk_root, read_only=True)
    try:
        published = store.inspect(LOCATION_SESSION)
        capture = published.manifest.model_dump(mode="json")
    finally:
        store.close()
    receipt = capture["receipt"]
    events = receipt["events"]
    chunks = capture["chunks"]
    visit_indices = [event["visit_index"] for event in events]
    if visit_indices != list(range(len(events))):
        raise ValueError("capture events are not a complete contiguous visit inventory")
    if len(chunks) != len(events):
        raise ValueError("capture chunk and event inventories differ")
    for event, chunk in zip(events, chunks, strict=True):
        count = event["valid_end_counter_exclusive"] - event["valid_start_counter"]
        if (
            chunk["first_visit_index"] != event["visit_index"]
            or chunk["visit_count"] != 1
            or chunk["sample_count"] != count
        ):
            raise ValueError("capture event and chunk geometry differ")
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "capture-manifest.json", capture)
    geometry = receipt["plan"]["geometry"]
    selected = [276, 830, 1384, 1938]
    inventory = {
        "schema": "org.leo.native-adaptive-location-source-inventory/v1",
        "dataset_id": "DS9",
        "session_id": LOCATION_SESSION,
        "source_port": "AdaptiveHopIqStore(read_only=True).inspect",
        "source_bulk_root": os.fspath(bulk_root),
        "input_manifest_sha256": published.manifest_sha256,
        "capture_manifest_file": "capture-manifest.json",
        "capture_manifest_sha256": sha256_file(output / "capture-manifest.json"),
        "capture_visit_inventory_complete": True,
        "capture_outcome": receipt.get("capture_outcome"),
        "visit_count": len(events),
        "chunk_count": len(chunks),
        "sample_rate_hz": geometry["sample_rate_hz"],
        "valid_visit_ms": geometry["valid_visit_ms"],
        "receiver_ids": geometry["receiver_ids"],
        "sample_format": capture["sample_format"],
        "sample_layout": capture["sample_layout"],
        "total_complex_times": capture["total_sample_count"],
        "uncompressed_bytes": capture["uncompressed_bytes"],
        "compressed_bytes": capture["compressed_bytes"],
        "uncompressed_sha256": capture["uncompressed_sha256"],
        "target_edges": sorted({event["target"]["edge"] for event in events}),
        "first_visit_index": visit_indices[0],
        "last_visit_index": visit_indices[-1],
        "saved_lag_selection_visit_indices": selected,
        "saved_lag_selection_is_complete_scan": False,
        "all_selected_visits_exist": all(index in visit_indices for index in selected),
        "raw_ci16_exported": False,
        "raw_export_gap": (
            "The source contains 15,948,000,000 uncompressed bytes across 2,215 visits. "
            "This bounded fixture export preserves its complete hash-bound metadata but does "
            "not duplicate the 15.948 GB raw session."
        ),
    }
    write_json(output / "source-inventory.json", inventory)
    return inventory


def generate_location_templates(output: Path) -> dict[str, object]:
    refuse_qnap_output(output)
    import numpy as np

    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame

    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for role, roll in (("exact", 0), ("control", CONTROL_SYMBOL_ROLL)):
        samples = np.asarray(
            qin_edge_pilot_frame(7_500_000, "lower", symbol_roll=roll), dtype="<c16"
        )
        path = output / f"lower-{role}.c128"
        path.write_bytes(samples.tobytes(order="C"))
        rows.append(
            {
                "role": role,
                "symbol_roll": roll,
                "file": path.name,
                "sha256": sha256_file(path),
                "dtype": "<c16",
                "shape": list(samples.shape),
            }
        )
    manifest = {
        "schema": "org.leo.native-adaptive-qin-templates/v1",
        "sample_rate_hz": 7_500_000,
        "edge": "lower",
        "source_api": "leo.analysis.starlink.templates.qin_edge_pilot_frame",
        "control_symbol_roll_constant": "CONTROL_SYMBOL_ROLL",
        "templates": rows,
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def export_server_oracle(panel_path: Path, bulk_root: Path, output: Path) -> dict[str, object]:
    """Export deployed fractional candidates for the portable panel and location subset."""
    refuse_qnap_output(output)
    from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    panel = json.loads(panel_path.read_text())
    requests = {
        (case["session_id"], case["visit_index"])
        for case in panel["cases"]
    }
    requests.update((LOCATION_SESSION, index) for index in (276, 830, 1384, 1938))
    store = ScannerTrackingInputStore(bulk_root)
    rows = []
    try:
        for session_id in sorted({session for session, _ in requests}):
            tracking = store.load(session_id)
            selected = {visit for session, visit in requests if session == session_id}
            published = store.adaptive.inspect(session_id)
            binding = bind_actual_visit_analysis(
                published.manifest.receipt,
                input_manifest_sha256=published.manifest_sha256,
                probe_stride_ms=120,
            )
            probes = []
            with store.adaptive_analysis.job(binding) as job:
                for product in job.published_visits():
                    if product.visit_index not in selected:
                        continue
                    probes.extend(
                        (product.visit_index, probe)
                        for probe in product.probes
                        if probe.probe_start_ms == 0
                    )
            expected = 2 * len(selected)
            if len(probes) != expected:
                raise ValueError(
                    f"{session_id}: expected {expected} receiver/probe rows, got {len(probes)}"
                )
            for visit_index, probe in probes:
                rows.append(
                    {
                        "session_id": session_id,
                        "sample_rate_hz": tracking.sample_rate_hz,
                        "input_manifest_sha256": tracking.input_manifest_sha256,
                        "analysis_manifest_sha256": tracking.analysis_manifest_sha256,
                        "visit_index": visit_index,
                        "probe": probe.model_dump(mode="json"),
                    }
                )
    finally:
        store.close()
    document = {
        "schema": "org.leo.native-adaptive-deployed-fractional-oracle/v1",
        "source_port": "ScannerTrackingInputStore.load",
        "source_bulk_root": os.fspath(bulk_root),
        "panel_sha256": sha256_file(panel_path),
        "request_count": len(requests),
        "probe_row_count": len(rows),
        "rows": sorted(
            rows,
            key=lambda row: (
                row["session_id"],
                row["visit_index"],
                row["probe"]["receiver_id"],  # type: ignore[index]
            ),
        ),
    }
    write_json(output, document)
    return document


def export_schedules(
    panel_path: Path,
    fixture_root: Path,
    output: Path,
    *,
    deployed_server_wrapper: bool = False,
) -> dict[str, object]:
    """Write bounded persistent-context schedules covering each case once."""
    refuse_qnap_output(output)
    panel = json.loads(panel_path.read_text())
    cases = panel["cases"]
    if len(cases) != 80:
        raise ValueError("schedule export requires the complete portable 80-case panel")
    fixture_root = fixture_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    schedules = []
    sequence = 0
    for edge in ("lower", "upper"):
        selected = [case for case in cases if case["target"]["edge"] == edge]
        for start in range(0, len(selected), 8):
            group = selected[start : start + 8]
            name = f"{edge}-{start:03d}.tsv"
            lines = []
            for case in group:
                metadata = json.dumps(
                    {
                        "dataset_id": case["dataset_id"],
                        "session_id": case["session_id"],
                        "visit_index": case["visit_index"],
                        "raw_sha256": case["raw_sha256"],
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
                fields = [
                            str(len(lines)),
                            str(case["rate_hz"]),
                            "120",
                            "120",
                            os.fspath(fixture_root / f"{edge}-exact.c128"),
                            os.fspath(fixture_root / f"{edge}-control.c128"),
                            os.fspath(fixture_root / case["raw_file"]),
                ]
                if deployed_server_wrapper:
                    nominal_center_hz = float(
                        case["target"]["if_center_hz"] - case["actual_lo_frequency_hz"]
                    )
                    # The source capture plans bind bandwidth to sample rate. The
                    # Qin template occupies +/-820312.5 Hz at this rate.
                    residual_half_width_hz = min(
                        800_000.0,
                        case["rate_hz"] / 2.0
                        - abs(nominal_center_hz)
                        - 820_312.5,
                    )
                    if residual_half_width_hz <= 0:
                        raise ValueError("portable case cannot contain the selected pilot")
                    fields.extend(
                        (
                            format(nominal_center_hz, ".17g"),
                            format(nominal_center_hz, ".17g"),
                            format(-residual_half_width_hz, ".17g"),
                            format(residual_half_width_hz, ".17g"),
                        )
                    )
                fields.append(metadata)
                lines.append("\t".join(fields))
                sequence += 1
            (output / name).write_text("\n".join(lines) + "\n")
            schedules.append({"file": name, "edge": edge, "call_count": len(group)})
    manifest = {
        "schema": (
            "org.leo.native-adaptive-deployed-wrapper-schedules/v1"
            if deployed_server_wrapper
            else "org.leo.native-adaptive-replay-schedules/v1"
        ),
        "source_panel_sha256": sha256_file(panel_path),
        "fixture_root": os.fspath(fixture_root),
        "dwell_ms": 120,
        "probe_stride_ms": 120,
        "case_count": sequence,
        "deployed_server_wrapper_geometry": deployed_server_wrapper,
        "schedules": schedules,
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def extract_member(archive: tarfile.TarFile, name: str, destination: Path) -> Path:
    member = archive.getmember(name)
    stream = archive.extractfile(member)
    if stream is None:
        raise ValueError(f"archive member is not a file: {name}")
    path = destination / name
    with path.open("wb") as output:
        shutil.copyfileobj(stream, output)
    return path


def run_panel(binary: Path, panel_path: Path, archive_path: Path, output: Path) -> None:
    panel = json.loads(panel_path.read_text())
    if len(panel["cases"]) != 80:
        raise ValueError("run-panel requires the complete 80-case panel")
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="leo-ds9-panel-") as temporary_name:
        temporary = Path(temporary_name)
        with tarfile.open(archive_path, "r") as archive:
            templates = {}
            for edge, roles in panel["templates"].items():
                templates[edge] = {
                    role: extract_member(archive, f"{edge}-{role}.c128", temporary)
                    for role in roles
                }
            raw = {
                case["raw_file"]: extract_member(archive, case["raw_file"], temporary)
                for case in panel["cases"]
            }
        partial = output.with_name(output.name + ".partial")
        with partial.open("w") as stream:
            for sequence, case in enumerate(panel["cases"]):
                edge = case["target"]["edge"]
                command = [
                    os.fspath(binary),
                    "--rate-hz",
                    str(case["rate_hz"]),
                    "--exact-template",
                    os.fspath(templates[edge]["exact"]),
                    "--control-template",
                    os.fspath(templates[edge]["control"]),
                    "--input-ci16",
                    os.fspath(raw[case["raw_file"]]),
                    "--dwell-ms",
                    "120",
                    "--probe-stride-ms",
                    "120",
                ]
                result = subprocess.run(command, capture_output=True, text=True, check=False)
                if result.returncode:
                    raise RuntimeError(
                        f"detector failed for case {sequence}: {result.stderr.strip()}"
                    )
                stream.write(
                    json.dumps(
                        {"sequence": sequence, "case": case, "result": json.loads(result.stdout)},
                        separators=(",", ":"),
                    )
                    + "\n"
                )
        partial.replace(output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inventory = subparsers.add_parser("inventory")
    inventory.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    inventory.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    inventory.add_argument("--output", type=Path, required=True)
    compare = subparsers.add_parser("compare-arm-panel")
    compare.add_argument("--comparison", type=Path, default=COMPARISON)
    compare.add_argument("--output", type=Path)
    location = subparsers.add_parser("export-location")
    location.add_argument("--source", type=Path, default=DEFAULT_LOCATION_SOURCE)
    location.add_argument("--output", type=Path, required=True)
    source_inventory = subparsers.add_parser("inventory-location-store")
    source_inventory.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    source_inventory.add_argument("--output", type=Path, required=True)
    templates = subparsers.add_parser("generate-location-templates")
    templates.add_argument("--output", type=Path, required=True)
    schedules = subparsers.add_parser("export-schedules")
    schedules.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    schedules.add_argument("--fixture-root", type=Path, required=True)
    schedules.add_argument("--output", type=Path, required=True)
    schedules.add_argument("--deployed-server-wrapper", action="store_true")
    oracle = subparsers.add_parser("export-server-oracle")
    oracle.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    oracle.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    oracle.add_argument("--output", type=Path, required=True)
    fractional_comparison = subparsers.add_parser("compare-fractional-server")
    fractional_comparison.add_argument(
        "--report",
        type=Path,
        default=ROOT / "reports/2026_09_30_native_adaptive_deployment/ds9",
    )
    wrapper_comparison = subparsers.add_parser("compare-deployed-wrapper")
    wrapper_comparison.add_argument(
        "--report",
        type=Path,
        default=ROOT / "reports/2026_09_30_native_adaptive_deployment/ds9",
    )
    wrapper_results = subparsers.add_parser("compare-deployed-wrapper-results")
    wrapper_results.add_argument("--native-directory", type=Path, required=True)
    wrapper_results.add_argument(
        "--oracle",
        type=Path,
        default=(
            ROOT
            / "reports/2026_09_30_native_adaptive_deployment/ds9/"
            "deployed-fractional-oracle.json"
        ),
    )
    wrapper_results.add_argument("--output", type=Path, required=True)
    replay = subparsers.add_parser("run-panel")
    replay.add_argument("--binary", type=Path, required=True)
    replay.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    replay.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    replay.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "inventory":
        refuse_qnap_output(args.output)
        document = portable_manifest(args.panel, args.archive)
        write_json(args.output, document)
    elif args.command == "compare-arm-panel":
        document = compare_arm_panel(args.comparison)
        if args.output:
            refuse_qnap_output(args.output)
            write_json(args.output, document)
        print(json.dumps(document, sort_keys=True))
        if not document["passed"]:
            return 1
    elif args.command == "export-location":
        document = export_location(args.source, args.output)
        print(json.dumps({"session_id": document["session_id"], "rows": len(document["rows"])}))
    elif args.command == "inventory-location-store":
        document = inventory_location_store(args.bulk_root, args.output)
        print(json.dumps({"session_id": document["session_id"], "visits": document["visit_count"]}))
    elif args.command == "generate-location-templates":
        document = generate_location_templates(args.output)
        print(json.dumps(document, sort_keys=True))
    elif args.command == "export-schedules":
        document = export_schedules(
            args.panel,
            args.fixture_root,
            args.output,
            deployed_server_wrapper=args.deployed_server_wrapper,
        )
        print(json.dumps(document, sort_keys=True))
    elif args.command == "export-server-oracle":
        document = export_server_oracle(args.panel, args.bulk_root, args.output)
        print(json.dumps({"requests": document["request_count"], "rows": len(document["rows"])}))
    elif args.command == "compare-fractional-server":
        refuse_qnap_output(args.report)
        document = regenerate_fractional_comparisons(args.report)
        print(json.dumps(document, sort_keys=True))
    elif args.command == "compare-deployed-wrapper":
        refuse_qnap_output(args.report)
        document = regenerate_deployed_wrapper_comparison(args.report)
        print(json.dumps(document, sort_keys=True))
    elif args.command == "compare-deployed-wrapper-results":
        refuse_qnap_output(args.output)
        document = compare_deployed_wrapper_result_directory(
            args.native_directory, args.oracle
        )
        write_json(args.output, document)
        print(json.dumps(document, sort_keys=True))
    elif args.command == "run-panel":
        refuse_qnap_output(args.output)
        run_panel(args.binary, args.panel, args.archive, args.output)
    else:
        parser.error("unknown command")
    return 0


if __name__ == "__main__":
    sys.exit(main())
