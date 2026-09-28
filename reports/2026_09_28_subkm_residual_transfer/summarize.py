"""Summarize fixed predictions without consulting reference-coordinate scores."""

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from ds7_residual_audit import summarize_groups  # noqa: E402


def main():
    source = json.loads((HERE / "results/summary.json").read_text())
    assert source["status"] == "complete" and len(source["recordings"]) == 88
    records = source["recordings"]
    paired = [r for r in records if r["independent_qualified"]]
    panels = []
    for start in range(0, 88, 8):
        selected = records[start : start + 8]
        paired_panel = [r for r in selected if r["independent_qualified"]]
        panels.append(
            {
                "first_unit": selected[0]["unit_id"],
                "last_unit": selected[-1]["unit_id"],
                "joint_records": len(selected),
                "paired_records": len(paired_panel),
                "joint_minus_independent_held": math.fsum(
                    r["joint_minus_independent_held"] for r in paired_panel
                ),
            }
        )
    tracks = []
    for record in records:
        details = json.loads((HERE / f"results/{record['unit_id']}.json").read_text())
        tracks.extend(
            {**row, "session_id": record["session_id"]} for row in details["joint_tracks"]
        )
    groups = summarize_groups(tracks, ("receiver_id", "channel"))
    totals = {
        key: math.fsum(r["joint"][key] for r in records)
        for key in (
            "tracks",
            "training_observations",
            "held_observations",
            "training_log_score",
            "held_predictive_log_density",
        )
    }
    for role in ("training", "held"):
        totals[role + "_rms_hz"] = math.sqrt(
            math.fsum(
                r["joint"][role + "_rms_hz"] ** 2 * r["joint"][role + "_observations"]
                for r in records
            )
            / totals[role + "_observations"]
        )
    result = {
        "joint_all88": totals,
        "paired_comparison": {
            "records": len(paired),
            "joint_minus_independent_held": math.fsum(
                r["joint_minus_independent_held"] for r in paired
            ),
            "positive_records": sum(r["joint_minus_independent_held"] > 0 for r in paired),
            "excluded_controls": [r["unit_id"] for r in records if not r["independent_qualified"]],
        },
        "chronological_panels": panels,
        "receiver_channel_slopes": groups,
        "candidate_effective_count_median": float(
            np.median([r["effective_candidate_count"] for r in tracks])
        ),
        "top_held_rms_tracks": sorted(
            (
                {
                    k: r[k]
                    for k in (
                        "session_id",
                        "track_id",
                        "receiver_id",
                        "channel",
                        "training_rms_hz",
                        "held_rms_hz",
                        "map_candidate_probability",
                    )
                }
                for r in tracks
            ),
            key=lambda r: r["held_rms_hz"],
            reverse=True,
        )[:20],
    }
    with (HERE / "diagnostics.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != "top_held_rms_tracks"}, indent=2))


if __name__ == "__main__":
    main()
