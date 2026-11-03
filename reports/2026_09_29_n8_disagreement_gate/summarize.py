import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent


def distance(point):
    lat, lon = map(math.radians, point)
    a, b = map(math.radians, (37.849056280893684, -122.48575489722863))
    h = math.sin((lat - a) / 2) ** 2 + math.cos(lat) * math.cos(a) * math.sin((lon - b) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1, h)))


def tally(rows):
    accepted = [r for r in rows if r["accepted"]]
    return dict(total=len(rows), qualified=sum(r["qualified"] for r in rows), accepted=len(accepted), accepted_below_1km=sum(r["error_m"] < 1000 for r in accepted), accepted_at_least_1km=sum(r["error_m"] >= 1000 for r in accepted), rejected_below_1km=sum(not r["accepted"] and r["error_m"] < 1000 for r in rows), accepted_max_error_m=max((r["error_m"] for r in accepted), default=None))


def main():
    rows = []
    for ds in ("DS7", "DS8", "DS9"):
        assert json.loads((HERE / f"{ds}.receipt.json").read_text())["exit_code"] == 0
        for p in json.loads((HERE / f"{ds}.json").read_text())["panels"]:
            rows.append(dict(dataset=ds, family=p["family"], panel=p["panel"], qualified=p["qualified"], accepted=p["accepted"], error_m=distance(p["estimate_deg"]), scan_scale_m=p.get("scan_scale_m"), pair_scale_m=p.get("pair_scale_m")))
    assert len(rows) == 18
    summary = dict(overall=tally(rows), families={f: tally([r for r in rows if r["family"] == f]) for f in ("contiguous", "balanced")}, datasets={ds: tally([r for r in rows if r["dataset"] == ds]) for ds in ("DS7", "DS8", "DS9")}, rows=rows)
    with (HERE / "summary.json").open("x") as out:
        json.dump(summary, out, indent=2)
    table = ["| Dataset | Family | Panel | Scan scale (m) | Pair scale (m) | Accepted | Reference distance (m) |", "|---|---|---|---:|---:|---|---:|"]
    for r in rows:
        scales = ["unqualified" if r[k] is None else f"{r[k]:.1f}" for k in ("scan_scale_m", "pair_scale_m")]
        table.append(f"| {r['dataset']} | {r['family']} | {r['panel']} | {scales[0]} | {scales[1]} | {r['accepted']} | {r['error_m']:.1f} |")
    (HERE / "table.md").write_text("\n".join(table) + "\n")
    for name, h in json.loads((HERE / "manifest.json").read_text())["hashes"].items():
        assert hashlib.sha256((HERE.parents[1] / name).read_bytes()).hexdigest() == h
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
