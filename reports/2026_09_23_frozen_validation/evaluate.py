"""Evaluate every sealed validation arm, then apply the frozen selection rule."""

import json
import math
from pathlib import Path

from baseline import load
from export import CACHE, HERE, ROOT, digest
from selection import select
from timing import HELPERS


def main():
    frozen = json.loads((HERE / "freeze.json").read_text())
    for relative, expected in frozen["sources"].items():
        assert digest(ROOT / relative) == expected
    data = {}
    for key in ("baseline", "timing"):
        path = HERE / key / "inference.json"
        assert digest(path).split(":")[1] == path.with_suffix(".sha256").read_text().strip()
        data[key] = json.loads(path.read_text())
        assert data[key]["bindings"]["freeze"] == digest(HERE / "freeze.json")
        assert data[key]["bindings"]["tool"] == digest(HERE / (key + ".py"))
    assert data["timing"]["bindings"]["baseline"] == digest(HERE / "baseline/inference.json")
    assert data["baseline"]["bindings"]["receipts"] == digest(HERE / "cache_receipts.json")
    for binding in json.loads((HERE / "cache_receipts.json").read_text())["rows"]:
        for filename, key in [("cache_receipt.json", "receipt"), ("state_cache.npz", "cache")]:
            assert digest(CACHE / binding["session_id"] / filename) == binding[key]
    single = load(ROOT / "reports/2026_09_23_long_training_search/search.py", "single")
    groups = {g["utc_8h_start"]: g["session_ids"] for g in frozen["groups"]}
    rows = []
    helpers = {name: load(path, name) for name, path in HELPERS.items()}
    for baseline in data["baseline"]["arms"]:
        prior, count, group = baseline["prior"], baseline["scan_count"], baseline["group"]
        point = baseline["search"]["selected"]
        tracks, _ = helpers["scan"].prepare(single, CACHE, groups[group][:count], point["scans"])
        zero = {
            "model": "baseline",
            "scale_s": 0.0,
            "prior": prior,
            "group": group,
            "view_scan_count": count,
            "latitude_deg": point["latitude_deg"],
            "longitude_deg": point["longitude_deg"],
            "east_km": point["east_km"],
            "north_km": point["north_km"],
            "taus_s": dict.fromkeys(groups[group][:count], 0.0),
            "stopping_rule_satisfied": True,
            "tau_boundary_count": 0,
        }
        arms = [zero] + [
            a
            for a in data["timing"]["arms"]
            if (a["prior"], a["group"], a["view_scan_count"]) == (prior, group, count)
        ]
        assert len(arms) == 7
        for arm in arms:
            if "failure" in arm:
                rows.append(arm)
                continue
            model = arm["model"]
            helper = helpers["global" if model == "global" else "scan"]
            taus = {"global": arm["global_tau_s"]} if model == "global" else arm["taus_s"]
            coordinate = arm["latitude_deg"], arm["longitude_deg"]
            score = helper.score(
                single,
                tracks,
                coordinate,
                taus,
                arm["scale_s"] if model != "baseline" else 1.0,
                True,
            )
            if model != "baseline":
                assert math.isclose(
                    score["penalized_objective_rmse_hz"],
                    arm["penalized_objective_rmse_hz"],
                    abs_tol=1e-8,
                    rel_tol=0,
                )
            total = sum(r["weight_s"] for r in score["rows"])
            row = {
                k: arm[k]
                for k in (
                    "model",
                    "scale_s",
                    "prior",
                    "group",
                    "view_scan_count",
                    "latitude_deg",
                    "longitude_deg",
                    "stopping_rule_satisfied",
                    "tau_boundary_count",
                )
            }
            row["visibility_failure_count"] = score["visibility_failure_count"]
            row["within_prior"] = (
                math.hypot(arm["east_km"], arm["north_km"]) <= single.PRIORS[prior][2] + 1e-8
            )
            row["track_count"] = len(tracks)
            row["reference_error_km"] = single.haversine_km(coordinate, single.REFERENCE)
            for name, cap in [("held_capped_rms_hz", 800.0), ("held_uncapped_rms_hz", math.inf)]:
                row[name] = math.sqrt(
                    sum(
                        r["weight_s"] * min(cap, r["evaluation_rms_hz"]) ** 2 for r in score["rows"]
                    )
                    / total
                )
            rows.append(row)
    assert len(rows) == 112
    result = {
        "rows": rows,
        "selection": select(rows, {k: len(v) for k, v in groups.items()}),
        "bindings": {
            "tool": digest(Path(__file__)),
            "selection": digest(HERE / "selection.py"),
            "baseline": digest(HERE / "baseline/inference.json"),
            "timing": digest(HERE / "timing/inference.json"),
        },
        "reference_role": "post-seal evaluation and explicit validation model selection only",
    }
    path = HERE / "results.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    path.with_suffix(".sha256").write_text(digest(path).split(":")[1] + "\n")


if __name__ == "__main__":
    main()
