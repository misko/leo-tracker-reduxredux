"""Freeze common method-comparison locations using inference outputs only."""
import json
from pathlib import Path

out = Path(__file__).resolve().parent
joint = json.loads((out / "joint/inference_partial.json").read_text())
full = next(row for row in joint["results"] if row["scan_count"] == 16)
locations = [dict(location_id=f"joint_basin_{index+1}", prior="common_intersection",
                  latitude_deg=row["latitude_deg"], longitude_deg=row["longitude_deg"],
                  source="16-scan residual-selected joint basin")
             for index, row in enumerate(full["basins"])]
# Only coordinates from the predeclared controls are used, never reference errors.
for row in json.loads((out / "ensemble_control.json").read_text()):
    if row["scan_count"] == 16 and row["method"] == "equal_scan_mean":
        locations.append(dict(location_id=f"{row['prior']}_coordinate_mean",
            prior="common_intersection", latitude_deg=row["latitude_deg"],
            longitude_deg=row["longitude_deg"], source="Mean of independently fitted coordinates"))
(out / "common_finalists.json").write_text(json.dumps(locations, indent=2)+"\n")
print(f"Frozen {len(locations)} shared locations without reference-coordinate selection")
