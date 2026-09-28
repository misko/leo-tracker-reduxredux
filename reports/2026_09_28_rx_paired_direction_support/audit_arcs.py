"""Independently check partial-arc disagreement using weighted pairwise distances."""

import hashlib
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def main():
    source = ROOT / "reports/2026_09_28_rx_geometry_association/dataset.json"
    document = json.loads(source.read_bytes())
    output = json.loads((HERE / "partial_arc.json").read_text())
    assert output["dataset_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    lanes = [x for x in document["lanes"] if x["recording_split"] == "calibration"]
    assert len(lanes) == len(output["lanes"]) == 12
    rows = []
    for lane, result in zip(lanes, output["lanes"], strict=True):
        assert lane["lane"] == result["lane"]
        components = lane["components"][:-1]
        raw = [0.0 if c["log_prior"] is None else math.exp(c["log_prior"]) for c in components]
        p = np.array(raw) / math.fsum(raw)
        for role in ("reception", "held_frequency"):
            windows = [w for w in lane["windows"] if w["role"] == role]
            q = np.array(
                [
                    [
                        2 * math.sin(math.pi / 18) * h["los_enu_unit"]["east"]
                        for h in w["predictions"]
                    ]
                    for w in windows
                ]
            )
            variance = 0.0
            for i in range(len(p)):
                for j in range(i):
                    difference = q[:, i] - q[:, j]
                    variance += p[i] * p[j] * float(np.mean((difference - difference.mean()) ** 2))
            rms = math.sqrt(variance)
            reported = result["roles"][role]
            assert math.isclose(
                rms,
                reported["prior_weighted_centered_trajectory_rms_disagreement"],
                rel_tol=1e-8,
                abs_tol=1e-14,
            )
            assert reported["windows"] == len(windows)
            rows.append(
                {
                    "lane": lane["lane"],
                    "role": role,
                    "windows": len(windows),
                    "rms_disagreement": rms,
                    "effective_nominees": reported["prior_effective_nominee_count"],
                    "weighted_excursion": reported[
                        "prior_weighted_mean_within_trajectory_excursion"
                    ],
                }
            )
    result = {"status": "pass", "audited_lane_roles": len(rows), "rows": rows}
    with (HERE / "arc-audit.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    for row in rows:
        print(
            row["lane"]["session_id"],
            row["lane"]["channel"],
            row["role"],
            row["rms_disagreement"],
            row["effective_nominees"],
        )


if __name__ == "__main__":
    main()
