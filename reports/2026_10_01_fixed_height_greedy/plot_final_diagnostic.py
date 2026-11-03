#!/usr/bin/env python3
"""Post-hoc ECDF adding the separately qualified third-stage polish."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from plot_continuation import validate_continuation
from plot_primary import failure_aware_ecdf, validate_complete


def diagnostic_rows(primary: dict, continuation: dict, audit: dict) -> dict[str, list[dict]]:
    rows = validate_continuation(continuation)
    primary_rows = validate_complete(primary)
    direct = {row["unit_id"]: row for row in primary_rows}
    for row in rows:
        nested = row["primary"]
        original = direct.get(row["unit_id"])
        if original is None or any(
            original.get(key) != nested.get(key)
            for key in ("accepted", "error_m", "receipt_sha256")
        ):
            raise ValueError("continuation does not embed the supplied primary evaluation")
    if not audit.get("valid") or audit.get("unit_id") != "DS11-F087":
        raise ValueError("polish audit is not valid for DS11-F087")
    error = audit.get("evaluator_only_error_m")
    if error is None or not np.isfinite(error):
        raise ValueError("polish audit lacks a finite evaluator-only error")
    failed = [row for row in rows if not row.get("effective_accepted")]
    if len(failed) != 1 or failed[0]["unit_id"] != audit["unit_id"]:
        raise ValueError("polish must correspond to the sole two-stage failure")
    effective = [{"error_m": row.get("effective_error_m")} for row in rows]
    polished = [dict(row) for row in effective]
    index = next(i for i, row in enumerate(rows) if row["unit_id"] == audit["unit_id"])
    polished[index]["error_m"] = float(error)
    return {
        "previous": [{"error_m": row.get("old_greedy_error_m")} for row in primary_rows],
        "primary": [{"error_m": row.get("error_m") if row.get("accepted") else None}
                    for row in primary_rows],
        "two_stage": effective,
        "polished": polished,
    }


def generate(primary: dict, continuation: dict, audit: dict, output: Path) -> Path:
    series = diagnostic_rows(primary, continuation, audit)
    output.mkdir(parents=True, exist_ok=True)
    fig, axis = plt.subplots(figsize=(8, 5.3), constrained_layout=True)
    specs = (
        ("previous", "Previous greedy", "0.45"),
        ("primary", "Student-t primary, 90 s", "tab:orange"),
        ("two_stage", "Frozen two-stage, 180 s", "tab:blue"),
        ("polished", "Post-hoc third-stage diagnostic", "tab:green"),
    )
    for key, label, color in specs:
        x, y = failure_aware_ecdf(series[key], "error_m")
        axis.step(x, y, where="post", marker="o", markersize=2.8, color=color,
                  label=f"{label}: {x.size}/64")
    axis.axvline(1000, color="tab:red", linestyle="--", linewidth=1, label="1 km")
    axis.axvline(10000, color="0.3", linestyle=":", linewidth=1, label="10 km")
    axis.set(xscale="log", ylim=(0, 1.02), xlabel="roof-reference error (m)",
             ylabel="fraction of all 64 planned scans",
             title="Post-hoc diagnostic comparison; frozen results unchanged")
    axis.legend(fontsize="small")
    path = output / "final-diagnostic-error-ecdf-all64.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--continuation", type=Path, required=True)
    parser.add_argument("--polish-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    path = generate(json.loads(args.primary.read_text()),
                    json.loads(args.continuation.read_text()),
                    json.loads(args.polish_audit.read_text()), args.output)
    print(path)


if __name__ == "__main__":
    main()
