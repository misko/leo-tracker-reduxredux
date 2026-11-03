import hashlib
import itertools
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "2026_09_29_time_balanced_scans"
hashes = {}


def read(name):
    path = SOURCE / name
    data = path.read_bytes()
    hashes[name] = hashlib.sha256(data).hexdigest()
    return json.loads(data)


def separation(a, b):
    return 1000 * math.hypot(a[0] - b[0], a[1] - b[1])


def reference_distance(point):
    lat, lon = map(math.radians, point)
    a, b = map(math.radians, (37.849056280893684, -122.48575489722863))
    h = math.sin((lat - a) / 2) ** 2 + math.cos(lat) * math.cos(a) * math.sin((lon - b) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1, h)))


def main():
    panels, pairs = [], []
    pools = {}
    for ds in ("DS7", "DS8", "DS9"):
        for family, suffixes in [("contiguous", ["early", "middle", "late"]), ("balanced", [0, 1, 2])]:
            members = []
            for suffix in suffixes:
                name = f"{ds}_{family}_{suffix}.json"
                cold, grid = read(name), read("grid_" + name)
                assert cold["sessions"] == grid["sessions"]
                starts = cold["starts"] + grid["additional_starts"]
                assert len(starts) == 6
                valid = [s for s in starts if s["qualified"]]
                best = max(s["score"] for s in valid)
                assert grid["selected"]["qualified"] and abs(best - grid["selected"]["score"]) < 1e-6
                near = [s for s in valid if best - s["score"] <= 1]
                diameter = lambda ss: max((separation(a["x"], b["x"]) for a, b in itertools.combinations(ss, 2)), default=0)
                record = dict(dataset=ds, family=family, panel=str(suffix), qualified_starts=len(valid), near_best_starts=len(near), all_diameter_m=diameter(valid), near_diameter_m=diameter(near), selected_xy=grid["selected"]["x"][:2], estimate_deg=grid["selected"]["estimate_deg"], near_xy=[s["x"][:2] for s in near], sessions=grid["sessions"])
                panels.append(record)
                members.append(record)
            ids = [s for m in members for s in m["sessions"]]
            assert len(ids) == len(set(ids)) == 24
            if ds in pools:
                assert pools[ds] == set(ids)
            pools[ds] = set(ids)
            for a, b in itertools.combinations(members, 2):
                dist = separation(a["selected_xy"], b["selected_xy"])
                mid = [(x + y) / 2 for x, y in zip(a["estimate_deg"], b["estimate_deg"])]
                pairs.append(dict(dataset=ds, family=family, panels=[a["panel"], b["panel"]], selected_separation_m=dist, minimum_near_mode_separation_m=min(separation(x, y) for x in a["near_xy"] for y in b["near_xy"]), accepted=dist < 1000, midpoint_deg=mid, midpoint_reference_distance_m=reference_distance(mid)))
    summary = {}
    for family in ("contiguous", "balanced"):
        pp = [p for p in pairs if p["family"] == family]
        accepted = [p for p in pp if p["accepted"]]
        summary[family] = dict(pairs=len(pp), accepted=len(accepted), accepted_below_1km=sum(p["midpoint_reference_distance_m"] < 1000 for p in accepted), accepted_at_least_1km=sum(p["midpoint_reference_distance_m"] >= 1000 for p in accepted), minimum_selected_separation_m=min(p["selected_separation_m"] for p in pp), maximum_selected_separation_m=max(p["selected_separation_m"] for p in pp))
    result = dict(panels=panels, pairs=pairs, summary=summary, source_sha256=hashes)
    with (HERE / "results.json").open("x") as out:
        json.dump(result, out, indent=2, allow_nan=False)
    table = ["| DS | Family | Pair | Selected separation (m) | Closest near-best modes (m) | Agreement gate | Midpoint reference distance (m) |", "|---|---|---|---:|---:|---|---:|"]
    for p in pairs:
        table.append(f"| {p['dataset']} | {p['family']} | {' / '.join(p['panels'])} | {p['selected_separation_m']:.1f} | {p['minimum_near_mode_separation_m']:.1f} | {p['accepted']} | {p['midpoint_reference_distance_m']:.1f} |")
    (HERE / "table.md").write_text("\n".join(table) + "\n")
    print(json.dumps(summary, indent=2))
    print('Qualified starts', sum(p['qualified_starts'] for p in panels))
    print('Largest near-best diameter', max(p['near_diameter_m'] for p in panels))
    print('Largest all-qualified diameter', max(p['all_diameter_m'] for p in panels))


if __name__ == "__main__":
    main()
