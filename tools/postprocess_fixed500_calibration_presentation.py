#!/usr/bin/env python3
"""Clarify fixed500 interval provenance in the sealed result presentation."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

from leo.analysis.starlink.local_doppler import stable_measurement_floats  # noqa: E402

ROOT = Path.cwd().resolve()
AMENDMENT = Path("config/analysis/fixed500-calibration-presentation-amendment-v1.json")
METRICS = Path("reports/figures/2026_08_26_fixed500_calibration/metrics.json")
FIGURE = Path("reports/figures/2026_08_26_fixed500_calibration/01-primary-calibration.png")


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _required_float(row: dict[str, object], field: str) -> float:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"sealed primary metric is absent: {field}")
    return float(value)


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(stable_measurement_floats(value), allow_nan=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _plot(aggregate: list[dict[str, object]]) -> None:
    methods = (
        "fixed_125ms_linear",
        "fixed_500ms_linear",
        "fixed_500ms_calibrated",
        "lean_curvature_500ms",
    )
    labels = (
        "125 ms\nlegacy σ",
        "500 ms\nlegacy σ",
        "500 ms\ngrouped calibrated",
        "500 ms quadratic\nlegacy σ",
    )
    lookup = {str(row["estimator"]): row for row in aggregate}
    if set(lookup) != set(methods):
        raise ValueError("sealed primary estimator membership differs")
    figure = Figure(figsize=(15.5, 8.2), constrained_layout=True)
    axes = figure.subplots(2, 2)
    x = np.arange(len(methods))
    colors = ("#6b7280", "#2563eb", "#059669", "#7c3aed")
    fields = (
        ("rmse_hz_s", "Rate RMSE (Hz/s)", None),
        ("endpoint_coverage", "Descriptive endpoint coverage", 0.95),
        (
            "scenario_simultaneous_coverage",
            "Descriptive scenario-simultaneous coverage",
            0.80,
        ),
        ("median_interval_half_width_hz_s", "Displayed interval half-width (Hz/s)", 600.0),
    )
    for axis, (field, ylabel, reference) in zip(axes.flat, fields, strict=True):
        axis.bar(x, [_required_float(lookup[item], field) for item in methods], color=colors)
        if reference is not None:
            axis.axhline(reference, color="black", linestyle="--", linewidth=1)
        axis.set_xticks(x, labels)
        axis.set_ylabel(ylabel)
        axis.grid(alpha=0.25, axis="y")
    axes[0, 0].set_title("A · Known-truth endpoint accuracy", loc="left")
    axes[0, 1].set_title("B · Interval coverage (green alone is grouped-calibrated)", loc="left")
    axes[1, 0].set_title("C · All-endpoint coverage by whole scenario", loc="left")
    axes[1, 1].set_title("D · Interval sharpness; calibration method differs", loc="left")
    figure.savefig(FIGURE, dpi=170)


def main() -> None:
    amendment = json.loads(AMENDMENT.read_text(encoding="utf-8"))
    if (
        not isinstance(amendment, dict)
        or amendment.get("schema")
        != "org.leo.research.fixed500-calibration-presentation-amendment/v1"
    ):
        raise ValueError("presentation amendment identity differs")
    metrics: dict[str, Any] = json.loads(METRICS.read_text(encoding="utf-8"))
    if metrics.get("repository_head_at_execution") != amendment.get("execution_repository_head"):
        raise ValueError("sealed execution evidence differs from presentation amendment")
    aggregate = metrics.get("primary_aggregate")
    if not isinstance(aggregate, list) or len(aggregate) != 4:
        raise ValueError("sealed primary aggregate differs")
    _plot(aggregate)
    relative_figure = str(FIGURE.resolve().relative_to(ROOT))
    artifacts = metrics.get("artifact_sha256")
    if not isinstance(artifacts, dict) or relative_figure not in artifacts:
        raise ValueError("sealed artifact inventory lacks the summary figure")
    artifacts[relative_figure] = _sha256(FIGURE)
    metrics["presentation_postprocess"] = {
        "repository_head": _git_head(),
        "completed_utc": datetime.now(UTC).isoformat(),
        "amendment_path": str(AMENDMENT),
        "amendment_sha256": _sha256(AMENDMENT),
        "script_path": str(Path(__file__).resolve().relative_to(ROOT)),
        "script_sha256": _sha256(Path(__file__)),
        "changed_artifact": relative_figure,
        "scientific_metrics_changed": False,
    }
    METRICS.write_bytes(_json_bytes(metrics))


if __name__ == "__main__":
    main()
