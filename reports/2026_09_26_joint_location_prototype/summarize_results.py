"""Read-only summary of frozen joint replay outputs (no model selection)."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import mean


def distance_km(a: dict, b: dict) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (
        a["latitude_deg"], a["longitude_deg"],
        b["latitude_deg"], b["longitude_deg"],
    ))
    q = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 12742.0176 * math.asin(math.sqrt(min(1.0, q)))


def independent_selections(group: dict, model: str) -> list[dict]:
    """Rank each scan alone under a frozen model, never using reference error."""
    choices: dict[str, list[tuple[float, str, dict]]] = {}
    for row in group["hypotheses"]:
        if row["model"] != model:
            continue
        for scan in row["scans"]:
            score = scan["training_objective"] / scan["fixed_weight_seconds"]
            choices.setdefault(scan["session_id"], []).append((score, row["location_id"], row))
    return [min(rows, key=lambda item: item[:2])[2] for rows in choices.values()]


def summarize(payloads: list[dict]) -> str:
    groups = [group for payload in payloads for group in payload["groups"]]
    ids = [group["group_id"] for group in groups]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate groups: do not double-count replay checkpoints")
    lines = [
        "# Frozen-model comparison", "",
        "Each joint entry is ONE group estimate, not three independent observations. Errors are km; no model is selected using these errors.", "",
        "| Group | Role | Independent λ=0 mean / max | Joint λ=0 | Joint λ=100 | Joint λ=1000 | Joint λ=10000 | Hard shared |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    models = ["lambda_0", "lambda_100", "lambda_1000", "lambda_10000", "hard_shared"]
    for group in groups:
        controls = group["independent_scan_lambda_0_control"]
        errors = [row["reference_error_km"] for row in controls]
        winners = [group["top_hypotheses"][model][0] for model in models]
        values = " | ".join(f'{row["reference_error_km"]:.2f}' for row in winners)
        lines.append(f'| {group["group_id"]} | {group.get("role", "")} | {mean(errors):.2f} / {max(errors):.2f} | {values} |')
    lines += ["", "## Clock-only control: independent scan locations", "",
        "Same group-wide candidate inventory; each scan selects its own site on that model's penalized training objective. Entries are mean / maximum error km, not joint group estimates.", "",
        "| Group | λ=0 | λ=100 | λ=1000 | λ=10000 | Hard shared |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for group in groups:
        entries = []
        for model in models:
            selections = independent_selections(group, model)
            errors = [row["reference_error_km"] for row in selections]
            entries.append(f"{mean(errors):.2f} / {max(errors):.2f}")
        lines.append(f'| {group["group_id"]} | ' + " | ".join(entries) + " |")
    lines += ["", "## Competing hypotheses and weighting sensitivity", "",
        "Objective gaps below compare only hypotheses within one fixed model; they are not calibrated probabilities or confidence thresholds.", "",
        "| Group | Model | Best objective | Runner-up gap | Runner-up separation km | Duration-pooled winner error km |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for group in groups:
        for model in models:
            rows = group["top_hypotheses"][model]
            first = rows[0]
            score = first["regularized_equal_scan_rms_hz"]
            gap = rows[1]["regularized_equal_scan_rms_hz"] - score if len(rows) > 1 else math.nan
            separation = distance_km(first, rows[1]) if len(rows) > 1 else math.nan
            pooled = min((row for row in group["hypotheses"] if row["model"] == model), key=lambda row: (row["regularized_pooled_rms_hz"], row["location_id"]))
            lines.append(f'| {group["group_id"]} | {model} | {score:.3f} | {gap:.3f} | {separation:.2f} | {pooled["reference_error_km"]:.2f} |')
    parity = [abs(row["difference_hz"]) for group in groups for row in group["production_hard_parity"]]
    lines += ["", f'Production parity: {len(parity)} published-site checks; maximum absolute difference {max(parity, default=0):.3g} Hz.', ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path, nargs="+")
    args = parser.parse_args()
    print(summarize([json.loads(path.read_text()) for path in args.results]))


if __name__ == "__main__":
    main()
