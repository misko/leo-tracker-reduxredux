"""Extract the versioned release panel and the matched successor comparisons."""

import argparse
import csv
import gzip
import io
import json
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
PUBLIC = "48895a9070b6874e1229e9996135d9f2dc1fd2d1"
RESEARCH = "bf3a5584065b2a7206af2eb4e4fa2a977cdc159c"
BASE = "reports/ALGO08/v3/"


def blob(repo, version, path):
    return subprocess.check_output(["git", "-C", str(repo), "show", f"{version}:{BASE}{path}"])


def extract(public_repo, research_repo):
    def receipt(name):
        data = blob(research_repo, RESEARCH, f"measurements/{name}.json.gz")
        return json.loads(gzip.decompress(data))

    rows = []

    def add(scope, case, algorithm, order, status, elapsed, cpu, c0=None, fitted=None):
        assert elapsed > 0 and cpu > 0
        assert (c0 is None) == (fitted is None) == (status != "complete")
        rows.append(dict(scope=scope, recording=case, algorithm=algorithm, run=order, decision=status,
                         elapsed_s=elapsed, cpu_s=cpu, c0_error_km=c0, fitted_c_error_km=fitted))

    release = blob(public_repo, PUBLIC, "ds30-100/recordings.csv")
    panel_ids = set()
    for r in csv.DictReader(io.StringIO(release.decode())):
        # The historical qualification called what is now ALGO08v3 its candidate.
        if r["build"] != "candidate":
            continue
        assert r["case"] not in panel_ids
        panel_ids.add(r["case"])
        add("release_100", r["case"], "ALGO08v3", "historical", r["decision"],
            float(r["elapsed_s"]), float(r["cpu_s"]),
            float(r["c0_error_km"]) if r["c0_error_km"] else None,
            float(r["fitted_c_error_km"]) if r["fitted_c_error_km"] else None)
    assert len(panel_ids) == 100

    packed = receipt("integrated-packed-full")
    pair = packed["pair"]["document"]
    errors = packed["cases"]["DS30-0016"]["result"]["document"]["physical"]["runs"]
    for i, case in enumerate(pair["cases"]):
        assert case not in panel_ids
        result = packed["cases"][case]["result"]["document"]
        assert result["qualified"]
        fixed = result["terminal"]["decision"] == "ok"
        for algo, order, clock in (
            ("ALGO08v3", "fresh", pair["fresh_stock"][i]),
            ("candidate", "fix first", pair["current_original"]["positive_first"][i]),
            ("candidate", "withhold first", pair["current_original"]["withholding_first"][i]),
        ):
            arm = errors["stock" if algo == "ALGO08v3" else "candidate"]["horizontal_error_km"] if fixed else {}
            add("matched_original", case, algo, order, "complete" if fixed else "withheld",
                clock["elapsed_s"], clock["cpu_s"], arm.get("c0"), arm.get("fitted_c"))

    for case in ("DS30-0163", "DS30-0173", "DS30-0359"):
        assert case in panel_ids
        study = receipt(case.lower() + "-composed-saved")
        assert study["qualified"] and all(study["checks"].values())
        fresh = case == "DS30-0359"
        if fresh:
            control = receipt("ds30-0359-installed-control")
            assert control["qualified"] and all(control["checks"].values())
        costs = control["cost"] if fresh else study["cost"]
        geography = study["reference_geographic"] if fresh else study["historical_geography"]
        for algo in ("ALGO08v3", "candidate"):
            key = "installed" if algo == "ALGO08v3" else ("candidate" if fresh else "child")
            arm = geography["installed" if algo == "ALGO08v3" else "routed"]
            add("matched_saved", case, algo, "historical" if algo == "ALGO08v3" and not fresh else "fresh",
                "complete", costs["elapsed_s"][key], costs["cpu_s"][key],
                arm["c0"]["horizontal_error_km"], arm["fitted_c"]["horizontal_error_km"])
    assert len(rows) == 112
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("public_repo", type=Path)
    parser.add_argument("research_repo", type=Path)
    args = parser.parse_args()
    observations = extract(args.public_repo, args.research_repo)
    with (HERE / "recordings.csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(observations[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(observations)
