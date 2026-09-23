"""Evaluate the eight sealed selected-rule TEST arms after all inference seals."""

import json
import math
from pathlib import Path

from baseline import load
from export import CACHE, HERE, ROOT, digest


def main():
    frozen = json.loads((HERE / "freeze.json").read_text())
    amendment = json.loads((HERE / "execution_amendment.json").read_text())
    assert amendment["original_freeze"] == digest(HERE / "freeze.json")
    for relative, expected in frozen["sources"].items():
        if relative.endswith("/evaluate.py"):
            assert expected == amendment["original_sources"]["evaluate.py"]
        elif relative.endswith("/baseline.py") or relative.endswith("/timing.py"):
            continue
        else:
            assert digest(ROOT / relative) == expected
    assert digest(Path(__file__)) == amendment["amended_sources"]["evaluate.py"]
    receipts = json.loads((HERE / "cache_receipts.json").read_text())
    assert digest(HERE / "cache_receipts.json") == amendment["cache_receipts"]
    assert receipts["freeze"] == digest(HERE / "freeze.json")
    assert [row["session_id"] for row in receipts["rows"]] == frozen["session_ids"]
    failed = [row for row in receipts["rows"] if "failure" in row]
    assert len(failed) == 1 and failed[0]["session_id"] == amendment["failed_session_id"]
    for binding in receipts["rows"]:
        if "failure" not in binding:
            for filename, key in (("cache_receipt.json", "receipt"), ("state_cache.npz", "cache")):
                assert digest(CACHE / binding["session_id"] / filename) == binding[key]
    inputs = {}
    for key in ("baseline", "timing"):
        path = HERE / key / "inference.json"
        assert digest(path).split(":")[1] == path.with_suffix(".sha256").read_text().strip()
        inputs[key] = json.loads(path.read_text())
        assert inputs[key]["bindings"]["freeze"] == digest(HERE / "freeze.json")
        assert inputs[key]["bindings"]["tool"] == digest(HERE / f"{key}.py")
    assert inputs["timing"]["bindings"]["baseline"] == digest(HERE / "baseline/inference.json")
    helper = load(ROOT / "reports/2026_09_23_long_global_epoch_position/fit.py", "global_helper")
    single = load(ROOT / "reports/2026_09_23_long_training_search/search.py", "single")
    group = frozen["groups"][0]
    baseline = {(a["scan_count"], a["prior"]): a for a in inputs["baseline"]["arms"]}
    rows = []
    for arm in inputs["timing"]["arms"]:
        if "failure" in arm:
            rows.append(arm)
            continue
        base = baseline[arm["view_scan_count"], arm["prior"]]
        tracks, _ = helper.prepare(
            single,
            CACHE,
            group["session_ids"][: arm["view_scan_count"]],
            base["search"]["selected"]["scans"],
        )
        score = helper.score(
            single,
            tracks,
            (arm["latitude_deg"], arm["longitude_deg"]),
            {"global": arm["global_tau_s"]},
            0.2,
            True,
        )
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
                "global_tau_s",
                "stopping_rule_satisfied",
                "tau_boundary_count",
            )
        }
        row["visibility_failure_count"] = score["visibility_failure_count"]
        row["within_prior"] = (
            math.hypot(arm["east_km"], arm["north_km"]) <= single.PRIORS[arm["prior"]][2] + 1e-8
        )
        row["track_count"] = len(tracks)
        row["reference_error_km"] = single.haversine_km(
            (arm["latitude_deg"], arm["longitude_deg"]), single.REFERENCE
        )
        for name, cap in (("held_capped_rms_hz", 800.0), ("held_uncapped_rms_hz", math.inf)):
            row[name] = math.sqrt(
                sum(r["weight_s"] * min(cap, r["evaluation_rms_hz"]) ** 2 for r in score["rows"])
                / total
            )
        rows.append(row)
    assert len(rows) == 8
    result = {
        "rows": rows,
        "reference_role": "once-only post-seal TEST evaluation",
        "bindings": {
            "tool": digest(Path(__file__)),
            "freeze": digest(HERE / "freeze.json"),
            "validation_selection": frozen["validation_selection"]["results_sha256"],
            "baseline": digest(HERE / "baseline/inference.json"),
            "timing": digest(HERE / "timing/inference.json"),
            "receipts": digest(HERE / "cache_receipts.json"),
            "execution_amendment": digest(HERE / "execution_amendment.json"),
        },
    }
    path = HERE / "results.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    path.with_suffix(".sha256").write_text(digest(path).split(":")[1] + "\n")


if __name__ == "__main__":
    main()
