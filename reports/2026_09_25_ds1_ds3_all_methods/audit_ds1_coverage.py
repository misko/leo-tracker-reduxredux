#!/usr/bin/env python3
"""Audit DS1 coverage without upgrading historical evidence into a ranking.

The all-method report distinguishes a sealed historical *evaluation* from a
sealed qualification.  Older DS1 suites often contain several development
views per method and no single ranking-eligible aggregate.  This audit makes
those exact-method evaluations visible, while leaving qualification and any
DS1-versus-DS3 performance ranking fail-closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DEFAULT_REGISTRY = HERE / "method-registry.json"
DEFAULT_COMPARISON = HERE / "comparison.json"
DEFAULT_JSON = HERE / "DS1_COVERAGE_AUDIT.json"
DEFAULT_MARKDOWN = HERE / "DS1_COVERAGE_AUDIT.md"


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verify(path: Path) -> dict[str, Any]:
    actual = digest(path).removeprefix("sha256:")
    sidecars = (path.with_suffix(path.suffix + ".sha256"), path.with_suffix(".sha256"))
    if not any(
        item.is_file()
        and item.read_text().strip().split()[0].removeprefix("sha256:") == actual
        for item in sidecars
    ):
        raise ValueError(f"unsealed artifact: {path}")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def write(path: Path, value: dict[str, Any]) -> None:
    text = canonical(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(text.encode()).hexdigest() + "\n"
    )


def display(path: Path) -> str:
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize every selected historical case, never choose a best case."""
    by_scan_count: dict[str, list[float]] = {}
    for row in rows:
        error = row.get("reference_error_km")
        scan_count = row.get("scan_count")
        if isinstance(error, (int, float)) and isinstance(scan_count, int):
            by_scan_count.setdefault(str(scan_count), []).append(float(error))
    return {
        "matching_row_count": len(rows),
        "completed_row_count": sum(row.get("status") == "completed" for row in rows),
        "reference_error_km_median_by_scan_count": {
            scan_count: statistics.median(errors)
            for scan_count, errors in sorted(by_scan_count.items(), key=lambda item: int(item[0]))
        },
    }


def build(
    registry_path: Path = DEFAULT_REGISTRY,
    comparison_path: Path = DEFAULT_COMPARISON,
) -> dict[str, Any]:
    registry = verify(registry_path)
    comparison = verify(comparison_path)
    prior = {
        row["method_id"]: row
        for row in comparison.get("rows", [])
        if isinstance(row, dict) and isinstance(row.get("method_id"), str)
    }
    findings: list[dict[str, Any]] = []
    for method in registry.get("methods", []):
        if not isinstance(method, dict):
            continue
        method_id = method["method_id"]
        old = prior.get(method_id, {})
        if old.get("ds1_qualification_status") != "unavailable":
            continue
        ds1 = method.get("ds1", {})
        evidence = ds1.get("historical_evidence") if isinstance(ds1, dict) else None
        if not isinstance(evidence, dict):
            findings.append(
                {
                    "method_id": method_id,
                    "iteration": method.get("iteration"),
                    "status": "still_unavailable",
                    "reason": "no exact sealed DS1 method-evaluation binding",
                    "report_dir": ds1.get("report_dir") if isinstance(ds1, dict) else None,
                }
            )
            continue
        if evidence.get("kind") != "sealed_method_rows":
            raise ValueError(f"unsupported DS1 evidence binding: {method_id}")
        artifact = evidence.get("artifact")
        selector = evidence.get("selector")
        if not isinstance(artifact, dict) or not isinstance(artifact.get("path"), str):
            raise ValueError(f"bad DS1 evidence artifact: {method_id}")
        if not isinstance(selector, dict) or not isinstance(selector.get("method"), str):
            raise ValueError(f"bad DS1 evidence selector: {method_id}")
        path = ROOT / artifact["path"]
        value = verify(path)
        if artifact.get("sha256") != digest(path):
            raise ValueError(f"DS1 evidence digest mismatch: {method_id}")
        selected = [
            row
            for row in value.get("rows", [])
            if isinstance(row, dict) and row.get("method") == selector["method"]
        ]
        if not selected:
            raise ValueError(f"DS1 selector had no matching rows: {method_id}")
        findings.append(
            {
                "method_id": method_id,
                "iteration": method.get("iteration"),
                "status": "sealed_method_matched_evaluation",
                "reason": (
                    "same method selector in a sealed multi-case DS1 evaluation; "
                    "not a single qualified DS1 aggregate"
                ),
                "artifact": {"path": display(path), "sha256": digest(path)},
                "selector": selector,
                "summary": summary(selected),
            }
        )
    mapped = [row for row in findings if row["status"] == "sealed_method_matched_evaluation"]
    return {
        "schema": "ds1-historical-coverage-audit/v1",
        "registry": {"path": display(registry_path), "sha256": digest(registry_path)},
        "comparison": {"path": display(comparison_path), "sha256": digest(comparison_path)},
        "counts": {
            "prior_unavailable_rows": len(findings),
            "sealed_method_matched_evaluations": len(mapped),
            "still_unavailable": len(findings) - len(mapped),
        },
        "findings": findings,
        "limitations": [
            "A sealed multi-case development evaluation is evidence of DS1 method coverage, "
            "not a DS1 qualification.",
            "No selected best case or synthetic aggregate is used as a DS1-versus-DS3 "
            "ranking value.",
            "Rows without an exact sealed method selector remain unavailable.",
        ],
    }


def markdown(value: dict[str, Any]) -> str:
    lines = [
        "# DS1 historical coverage audit",
        "",
        "This audit repairs provenance visibility only. It does not turn historical "
        "multi-case development results into qualified DS1 rankings.",
        "",
        "| Method | Iteration | Coverage | Sealed evidence | Selector | Case summary |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for row in value["findings"]:
        artifact = row.get("artifact", {})
        summary_value = row.get("summary", {})
        cases = summary_value.get("matching_row_count", "—")
        medians = summary_value.get("reference_error_km_median_by_scan_count", {})
        median_text = ", ".join(
            f"{key}-scan: {median:.3f} km" for key, median in medians.items()
        ) or "—"
        lines.append(
            (
                "| {method} | {iteration} | {status} | {artifact} | {selector} | "
                "{cases} cases; {medians} |"
            ).format(
                method=row["method_id"],
                iteration=row.get("iteration"),
                status=row["status"],
                artifact=artifact.get("path", "—"),
                selector=row.get("selector", {}).get("method", "—"),
                cases=cases,
                medians=median_text,
            )
        )
    lines.extend(["", "## Limits", ""] + [f"- {item}" for item in value["limitations"]])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--comparison", type=Path, default=DEFAULT_COMPARISON)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()
    value = build(args.registry, args.comparison)
    write(args.json_output, value)
    args.markdown_output.write_text(markdown(value))
    print(json.dumps(value["counts"], sort_keys=True))


if __name__ == "__main__":
    main()
