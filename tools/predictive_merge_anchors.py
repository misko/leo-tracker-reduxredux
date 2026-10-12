"""Apply the frozen nested curve diagnostic to the two previously inspected pairs."""

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
from band_calibrated_merge_study import REPORT
from continuous_merge_study import sha, write
from predictive_merge_census import ORIGINAL

from leo.analysis.continuous_track_merge import TrackSeries
from leo.analysis.predictive_merge_curves import (
    PredictiveCurveConfiguration,
    compare_predictive_curves,
)


def main():
    output = REPORT / "local/predictive-curves/anchors.json"
    if output.exists():
        raise ValueError("anchor predictive outputs already exist")
    authority_path = ORIGINAL / "anchor-results.json"
    anchors = json.loads(authority_path.read_bytes())
    config = PredictiveCurveConfiguration()
    rows = []
    for label, authority in anchors.items():
        path = Path(authority["input"])
        if sha(path) != authority["sha256"]:
            raise ValueError("anchor input changed")
        data = json.loads(path.read_bytes())
        groups = []
        for track in data["tracks"]:
            ids = {p["candidate_id"] for p in track["points"]}
            support = sorted(
                (r for r in data["rows"] if r["candidate_id"] in ids), key=lambda r: r["time_s"]
            )
            raw = {p["candidate_id"]: p["normalized_raw_cfo_hz"] for p in track["points"]}
            groups.append(
                TrackSeries(
                    (track["tracklet_id"],),
                    tuple(track["lane_key"]),
                    tuple(r["candidate_id"] for r in support),
                    tuple(r["source_group_id"] for r in support),
                    np.array([r["time_s"] for r in support]),
                    np.array([raw[r["candidate_id"]] for r in support]),
                    np.array([r["weight"] for r in support]),
                    data["normalized_alias_spacing_hz"],
                )
            )
        row = {
            "label": label,
            "input_sha256": sha(path),
            "comparison": compare_predictive_curves(groups, config),
        }
        rows.append(row)
        print(json.dumps({"label": label, "rms_hz": row["comparison"]["rms_hz"]}), flush=True)
    write(
        output,
        {
            "rows": rows,
            "configuration": asdict(config),
            "script_sha256": sha(Path(__file__)),
            "authority_sha256": sha(authority_path),
            "component_sha256": sha(
                Path(__file__).parents[1] / "src/leo/analysis/predictive_merge_curves.py"
            ),
            "reference_usage": "none",
            "scope": "Previously selected exposed anchor examples.",
        },
    )


if __name__ == "__main__":
    main()
