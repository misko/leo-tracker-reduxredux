#!/usr/bin/env python3
"""Render the sealed DS2 portable development-evaluation report."""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def value(number: float | None, digits: int = 3) -> str:
    if number is None:
        return "—"
    return f"{number:.{digits}f}"


def main() -> None:
    dataset = json.loads((HERE / "dataset.json").read_text())
    evaluation = json.loads((HERE / "evaluation.json").read_text())
    accounting = json.loads((HERE / "registry-accounting.json").read_text())
    session_count = len(dataset["sessions"])
    track_count = sum(row["cache"]["eligible_track_count"] for row in dataset["sessions"])
    observation_count = sum(
        row["cache"]["eligible_observation_count"] for row in dataset["sessions"]
    )
    summaries = sorted(
        evaluation["single_scan_summaries"], key=lambda row: row["median_error_km"]
    )
    coarse = {row["method"]: row for row in evaluation["coarse_joint_rows"]}
    refined = {row["method"]: row for row in evaluation["refined_joint_rows"]}
    joints = sorted(evaluation["joint_rows"], key=lambda row: row["postseal_error_km"])
    joint = {row["method"]: row for row in joints}
    best = joints[0]
    baseline_delta = abs(
        refined["baseline"]["postseal_error_km"] - joint["baseline"]["postseal_error_km"]
    )

    lines = [
        "# DS2 Sept 24 portable positioning evaluation",
        "",
        "## Result",
        "",
        (
            f"This development evaluation uses all {session_count} sealed Sept 24 captures "
            f"({track_count:,} qualified tracks and {observation_count:,} observations). "
            "Each capture is kept whole. The reference coordinate was absent from inference "
            "and introduced only after every position artifact was sealed."
        ),
        "",
        (
            f"The best portable fine-grid result is `{best['method']}` at "
            f"{value(best['postseal_error_km'])} km. Baseline, shared-time, and regularized "
            f"per-scan timing all converge to {value(joint['baseline']['postseal_error_km'])} "
            "km and choose zero global timing shift. Moving from the 0.391 km stage to the "
            f"0.098 km stage changes baseline error by only "
            f"{value(baseline_delta)} "
            "km. The remaining roughly 1.9 km error is therefore a model/evidence plateau, "
            "rather than a coarse-lattice artifact; DS2 does not demonstrate sub-kilometre "
            "portable accuracy. The causal-rate winner passes its exact SGP4 gate with a "
            f"{joint['equal-weight-joint-rate']['exact_gate_maximum_absolute_hz']:.3g} Hz "
            "maximum cached-versus-exact discrepancy."
        ),
        "",
        "### Single-scan estimates",
        "",
        "| Method | Captures | Median error (km) | P25–P75 (km) | Best (km) | "
        "Worst (km) | <10 km | <1 km |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summaries:
        lines.append(
            f"| `{row['method']}` | {row['count']} | {value(row['median_error_km'])} | "
            f"{value(row['p25_error_km'])}–{value(row['p75_error_km'])} | "
            f"{value(row['minimum_error_km'])} | {value(row['maximum_error_km'])} | "
            f"{row['sub_10km_count']} | {row['sub_1km_count']} |"
        )
    lines.extend(
        [
            "",
            "### Joint all-session estimates",
            "",
            "Each joint objective gives every whole session equal total weight, so dense scans "
            "cannot dominate merely because they contain more tracks or observations.",
            "",
            "| Method | Coarse error (km) | 0.391-km error | 0.098-km error | Latitude | "
            "Longitude | RF objective | "
            "Global time (s) | Runtime (s) |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in joints:
        lines.append(
            f"| `{row['method']}` | {value(coarse[row['method']]['postseal_error_km'])} | "
            f"{value(refined[row['method']]['postseal_error_km'])} | "
            f"{value(row['postseal_error_km'])} | "
            f"{value(row['latitude_deg'], 6)} | {value(row['longitude_deg'], 6)} | "
            f"{value(row['rf_objective'], 6)} | {value(row['global_tau_s'])} | "
            f"{value(row['elapsed_s'], 1)} |"
        )
    lines.extend(
        [
            "",
            "![DS2 portable model comparison](portable-model-comparison.png)",
            "",
            "## Methods and interpretation",
            "",
            "- **Baseline Doppler** reacquires a satellite identity for every track at every "
            "geographic trial and fits a nuisance CFO per track.",
            "- **Shared global time** adds one receive-time displacement shared by every scan, "
            "receiver, track, and candidate.",
            "- **Regularized per-scan timing** adds bounded scan corrections around the shared "
            "time and penalizes those corrections.",
            "- **Independent track time** is a deliberately flexible diagnostic. It can expose "
            "timing-model mismatch, but its many nuisance parameters make it a weak portable "
            "positioning model.",
            "- **Causal per-NORAD rate** fits a shared rate correction for each associated NORAD "
            "on exact causal SGP4 predictions after geographic screening.",
            "- **Soft identity mixture** marginalizes nearby candidate identities rather than "
            "treating the top hard match as certain.",
            "",
            "All frequency losses use the declared 800 Hz cap and every qualified observation; "
            "there is no chronological or within-track holdout. These are development comparisons "
            "against a post-seal reference, not untouched validation/test results.",
            "",
            "## Frozen registry accounting",
            "",
            "| Model | Registry role | DS2 execution state | Reason |",
            "|---|---|---|---|",
        ]
    )
    for row in accounting["models"]:
        reason = (row.get("reason") or "sealed portable artifact").replace("|", "\\|")
        lines.append(
            f"| `{row['model_id']}` | `{row['registry_status']}` | "
            f"`{row['execution_state']}` | {reason} |"
        )
    lines.extend(
        [
            "",
            "The registry table accounts for all 17 frozen candidates. An arm marked adapter "
            "required or bounded-runtime deferred was not replaced by a cheaper surrogate. The "
            "four LT3D-001A cone/geometry arms are evaluated in the separate geometry package.",
            "",
            "## Reproducibility and bounds",
            "",
            f"- Final manifest: `{dataset['final_manifest_sha256']}`.",
            "- Runtime caches are receipt-bound exports of causal TLE snapshots. Cache bytes are "
            "intentionally outside git; their digests and receipts are frozen in `dataset.json`.",
            "- Single scans use 100, 25, and 6.25 km geographic levels. Joint coarse fits add a "
            "1.5625 km level. Every sealed joint winner then receives a symmetric reference-free "
            "local search at 1.5625, 0.78125, and 0.390625 km, with bounded expansion when the "
            "winner lies within one first-level cell of the search edge.",
            "- Each sealed 0.390625-km winner receives a second truth-free local search at "
            "0.1953125 and 0.09765625 km with the same symmetric edge-expansion rule.",
            "- A small reported reference error does not by itself establish equivalent "
            "statistical resolution. The fine 0.09765625 km lattice and variation across methods "
            "bound what this experiment can claim.",
            "- The radio corpus is read only. This evaluation collected no new RF data.",
            "",
            "From the repository root, after restoring the receipt-bound runtime caches:",
            "",
            "```bash",
            ".venv/bin/python reports/2026_09_24_ds2_portable_evaluation/build.py \\",
            "  --cache-root /var/tmp/leo-ds2-portable-cache",
            ".venv/bin/python reports/2026_09_24_ds2_portable_evaluation/execute.py \\",
            "  --cache-root /var/tmp/leo-ds2-portable-cache --workers 4",
            ".venv/bin/python reports/2026_09_24_ds2_portable_evaluation/refine_joint.py \\",
            "  --cache-root /var/tmp/leo-ds2-portable-cache --workers 3",
            ".venv/bin/python reports/2026_09_24_ds2_portable_evaluation/refine_joint_fine.py \\",
            "  --cache-root /var/tmp/leo-ds2-portable-cache --workers 3",
            ".venv/bin/python reports/2026_09_24_ds2_portable_evaluation/evaluate_postseal.py",
            ".venv/bin/python reports/2026_09_24_ds2_portable_evaluation/account_registry.py",
            ".venv/bin/python reports/2026_09_24_ds2_portable_evaluation/render.py",
            ".venv/bin/python reports/2026_09_24_ds2_portable_evaluation/write_report.py",
            "```",
            "",
        ]
    )
    (HERE / "REPORT.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
