"""Regenerate the checkpoint from saved, qualified research results (stdlib only)."""

import hashlib
import json
import math
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
REFERENCE = (37.849056280893684, -122.48575489722863)
sources = {}


def read(folder, filename="summary.json"):
    path = REPORTS / ("2026_09_29_" + folder) / filename
    data = path.read_bytes()
    sources[str(path.relative_to(REPORTS))] = hashlib.sha256(data).hexdigest()
    return json.loads(data)


def distance(point):
    lat, lon = map(math.radians, point)
    rlat, rlon = map(math.radians, REFERENCE)
    a = math.sin((lat - rlat) / 2) ** 2
    a += math.cos(lat) * math.cos(rlat) * math.sin((lon - rlon) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1, a)))


def values(folder, key):
    rows = read(folder)["rows"]
    assert [r["dataset"] for r in rows] == ["DS7", "DS8", "DS9"]
    assert all(r["qualified"] for r in rows)
    return [key(r) for r in rows]


def panel_errors(kind, suffixes):
    result = []
    for ds in (7, 8, 9):
        points = [read("time_balanced_scans", f"grid_DS{ds}_{kind}_{s}.json")["selected"] for s in suffixes]
        assert all(p["qualified"] for p in points)
        result.append(statistics.median(distance(p["estimate_deg"]) for p in points))
    return result


rows = [
    ("Configured center", "0 scans; fixed point", [distance((37.856249999999996, -122.484375))] * 3),
    ("Contiguous N8", "8 per fit; median of 3 windows", panel_errors("contiguous", ("early", "middle", "late"))),
    ("Time-balanced N8", "8 per fit; median of 3 sets", panel_errors("balanced", (0, 1, 2))),
    ("Cumulative N16", "16 scans; one fit", values("temporal_forecast", lambda r: r["reference_errors_m"]["cumulative"])),
    ("Pooled N24", "24 scans; one fit", values("curvature_n24", lambda r: r["baseline_error_m"])),
    ("Geometry-selected N8", "24 scouting scans; 8 retained", values("information_selection", lambda r: r["selected_error_m"])),
    ("Score-balanced N8", "24 scouting scans; 8 retained", values("score_balanced_selection", lambda r: r["selected_error_m"])),
    ("Prefix score-balanced N8", "12 scouting scans; 8 retained", values("prefix_score_selection", lambda r: r["errors_m"]["selected8"])),
    ("Shared-curvature N24", "24 scans; one fit", values("curvature_n24", lambda r: r["curvature_error_m"])),
]
table = ["| Method | Data and aggregation | DS7 (m) | DS8 (m) | DS9 (m) |", "|---|---|---:|---:|---:|"]
for name, scope, errors in rows:
    assert all(math.isfinite(e) and e >= 0 for e in errors)
    table.append(f"| {name} | {scope} | " + " | ".join(f"{e:,.1f}" for e in errors) + " |")
(HERE / "table.md").write_text("\n".join(table) + "\n")
(HERE / "results.json").write_text(json.dumps({"metric": "spherical distance to operator reference, metres", "earth_radius_m": 6371008.8, "rows": [{"method": n, "scope": s, "errors_m": dict(zip(("DS7", "DS8", "DS9"), e))} for n, s, e in rows], "source_sha256": sources}, indent=2) + "\n")
print("\n".join(table))
