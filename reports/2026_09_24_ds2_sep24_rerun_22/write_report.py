#!/usr/bin/env python3
"""Write a human-readable report from the sealed DS2-22 post-seal evaluation."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def number(value: Any, digits: int = 3) -> str:
    return "—" if value is None else f"{float(value):.{digits}f}"


def heading(title: str) -> list[str]:
    return [f"## {title}", ""]


def cohort_table(manifest: dict[str, Any]) -> list[str]:
    lines = [
        "| Cohort | Radio | Sample rate | Sessions | Geometry sessions | Joint eligible |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for cohort in manifest.get("cohorts", []):
        lines.append(
            "| {cohort_id} | {radio_id} | {sample_rate_hz:,} Hz | {session_count} | "
            "{geometry_count} | {eligible} |".format(
                cohort_id=cohort.get("cohort_id", "—"),
                radio_id=cohort.get("radio_id", "—"),
                sample_rate_hz=int(cohort.get("sample_rate_hz", 0)),
                session_count=cohort.get("session_count", 0),
                geometry_count=len(cohort.get("geometry_session_ids", [])),
                eligible="yes" if cohort.get("joint_inference_eligible") else "no",
            )
        )
    return lines


def model_table(rows: list[dict[str, Any]], scope: str) -> list[str]:
    lines = ["| Model family | Post-seal error (km) | RF objective |", "| --- | ---: | ---: |"]
    for row in rows:
        if row.get("scope") == scope:
            lines.append(
                "| `{method}` | {error} | {objective} |".format(
                    method=row.get("method", "—"),
                    error=number(row.get("postseal_error_km")),
                    objective=number(row.get("rf_objective"), 6),
                )
            )
    return lines


def cone_table(geometry: dict[str, Any]) -> list[str]:
    """Summarize the joint three-capture cone sweep across both RX mappings."""
    result = next(
        (
            item
            for item in geometry.get("results", [])
            if item.get("label") == "joint-three-geometry-captures"
        ),
        None,
    )
    if not isinstance(result, dict):
        return ["Joint cone summary unavailable."]
    scenarios = result.get("staged_full_fov", {}).get("scenarios", [])
    grouped: dict[int, list[dict[str, Any]]] = {}
    for scenario in scenarios:
        if isinstance(scenario, dict):
            grouped.setdefault(int(scenario["full_fov_deg"]), []).append(scenario)
    lines = [
        "| Full FOV | Tracks retained | Occupied support | Held RMS |",
        "| ---: | ---: | ---: | ---: |",
    ]
    for fov, items in sorted(grouped.items()):
        tracks = [int(item["supported_tracks"]) for item in items]
        support = [100.0 * float(item["supported_occupied_second_fraction"]) for item in items]
        rms = [float(item["held_rms_hz_supported"]) for item in items]
        lines.append(
            f"| {fov}° | {min(tracks)}–{max(tracks)} | "
            f"{min(support):.1f}–{max(support):.1f}% | {min(rms):.1f}–{max(rms):.1f} Hz |"
        )
    return lines


def followup_dispositions(bindings: dict[str, str], rows: list[dict[str, Any]]) -> list[str]:
    completed = {key.removeprefix("followup:") for key in bindings if key.startswith("followup:")}
    row_methods = {str(row.get("method")) for row in rows if row.get("scope") == "followup"}
    descriptions = {
        "consistent-cap800": (
            "completed exact capped-loss search; its winning point is evaluated below"
        ),
        "rate-aware-screen": (
            "completed bounded rate-aware local screen; its winner is evaluated below"
        ),
        "session-scale-residual": (
            "completed diagnostic residual accounting; it does not emit a position"
        ),
        "shared-norad": "completed shared-NORAD overlap accounting; it does not emit a position",
    }
    lines = ["| Follow-up | Disposition |", "| --- | --- |"]
    for name in sorted(completed):
        detail = descriptions.get(name, "completed and sealed")
        if name in row_methods:
            detail = detail.replace(" below", "")
        lines.append(f"| `{name}` | {detail} |")
    return lines


def write_report(
    evaluation: dict[str, Any], manifest: dict[str, Any], geometry: dict[str, Any]
) -> str:
    rows = list(evaluation.get("rows", []))
    bindings = dict(evaluation.get("bindings", {}))
    comparison = list(evaluation.get("ds2_20_comparison", []))
    total_sessions = sum(int(item.get("session_count", 0)) for item in manifest.get("cohorts", []))
    geometry_sessions = sum(
        len(item.get("geometry_session_ids", [])) for item in manifest.get("cohorts", [])
    )
    scopes = Counter(str(row.get("scope")) for row in rows)
    lines = [
        "# DS2 September 24 successor: post-seal evaluation",
        "",
        "This report evaluates the sealed DS2-22 inference products after completion. "
        "The reference coordinate was supplied only to the evaluator through its CLI; it is not "
        "an inference input and is not reproduced here.",
        "",
    ]
    lines += heading("Dataset and admission")
    lines += [
        f"The successor manifest admits **{total_sessions} sessions** in "
        f"**{len(manifest.get('cohorts', []))} cohorts**. It retains exactly "
        f"**{geometry_sessions} explicit geometry bindings**. Ordinary model families use all 22 "
        "admitted sessions under the sealed admission plan.",
        "",
    ]
    lines += cohort_table(manifest) + [""]
    lines += heading("Portable and refinement model families")
    lines += [
        f"The sealed portable execution contains 116 outputs. The evaluator records "
        f"{scopes['portable']} portable rows, {scopes['stage-one']} stage-one rows, and "
        f"{scopes['fine']} fine rows. The two tables show every refined model family; the fine "
        "families are the publishable DS2-22 comparison set.",
        "",
    ]
    lines += ["### Stage-one families", ""]
    lines += model_table(rows, "stage-one") + [""]
    lines += ["### Fine families", ""]
    lines += model_table(rows, "fine") + [""]
    lines += heading("DS2-22 versus published DS2-20 fine comparison")
    lines += [
        "| Fine method | DS2-22 error (km) | DS2-20 error (km) | Change (km) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in comparison:
        delta = "—" if row.get("delta_km") is None else f"{float(row['delta_km']):+.3f}"
        lines.append(
            "| `{method}` | {current} | {prior} | {delta} |".format(
                method=row.get("method", "—"),
                current=number(row.get("ds2_22_error_km")),
                prior=number(row.get("ds2_20_error_km")),
                delta=delta,
            )
        )
    lines += [""]
    lines += heading("Geometry and cone evidence")
    lines += [
        "Geometry uses only the original three explicit bindings. Baseline and staged full-FOV "
        "estimates are reported separately so that a staged result is never mistaken for a new "
        "independent capture.",
        "",
    ]
    lines += model_table(rows, "geometry") + [""]
    lines += [
        "The staged sweep fitted the cone orientation at each tested position for full fields "
        "of view from 10° through 90°. The local fitted branch repeated 10° through 50°. Both "
        "provisional LT3D-001A RX-to-slot mappings were evaluated and were symmetric; each row "
        "below is their stored representative.",
        "",
    ]
    lines += cone_table(geometry) + [""]
    lines += heading("Follow-up dispositions")
    lines += followup_dispositions(bindings, rows) + [""]
    if any(row.get("scope") == "followup" for row in rows):
        lines += ["### Post-seal positions", ""] + model_table(rows, "followup") + [""]
    lines += heading("Validation and reproduction")
    lines += [
        "The evaluator rejected unsealed artifacts, incomplete portable/refinement indexes, and "
        "artifacts declaring reference or truth use. It bound the completed portable execution, "
        "both six-model refinement indexes, geometry inference, the follow-up plan, and every "
        "completed follow-up output listed above.",
        "",
        "Rebuild the machine-readable evaluation after obtaining the established coordinate "
        "through the approved evaluation procedure:",
        "",
        "```bash",
        "python postseal_evaluation.py --reference-latitude <lat> --reference-longitude <lon>",
        "python render_evaluation.py",
        "python write_report.py",
        "```",
        "",
        "`evaluation.json.sha256` and `comparison.csv.sha256` seal the two machine-readable "
        "outputs. `postseal-comparison.png` is rendered solely from the sealed comparison rows.",
        "",
    ]
    lines += heading("Limitations")
    lines += [
        "This is a development evaluation, not an independent holdout result. The post-seal error "
        "is useful for comparison but depends on the supplied reference coordinate. The 22-session "
        "admission does not create new geometry evidence beyond the original three bindings. "
        "Follow-up searches are bounded diagnostics, and candidate identity or orbital "
        "interpretation requires separate evidence.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, default=HERE / "evaluation.json")
    parser.add_argument("--manifest", type=Path, default=HERE / "manifest.json")
    parser.add_argument(
        "--geometry", type=Path, default=HERE / "output" / "geometry" / "inference.json"
    )
    parser.add_argument("--output", type=Path, default=HERE / "REPORT.md")
    args = parser.parse_args()
    args.output.write_text(
        write_report(load(args.evaluation), load(args.manifest), load(args.geometry))
    )


if __name__ == "__main__":
    main()
