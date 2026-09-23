"""Evaluate completed sealed replication; handle each helper's native tau schema."""

import json
import math
from pathlib import Path

import run as runner


def main():
    output = runner.HERE / "results"
    path = output / "inference.json"
    assert runner.digest(path).split(":")[1] == path.with_suffix(".sha256").read_text().strip()
    result = json.loads(path.read_text())
    for key, source in {
        "tool": runner.HERE / "run.py",
        "protocol": runner.HERE / "PROTOCOL.md",
        "baseline": runner.BASE,
        "single": runner.SINGLE,
        "loader": runner.LOADER,
        **runner.HELPERS,
    }.items():
        assert runner.digest(source) == result["bindings"][key]
    for row in result["cache_bindings"]:
        for filename, key in [("cache_receipt.json", "receipt"), ("state_cache.npz", "cache")]:
            assert runner.digest(runner.CACHE / row["session_id"] / filename) == row[key]
    baseline = json.loads(runner.BASE.read_text())
    single = runner.module(runner.SINGLE, "single")
    for model in runner.HELPERS:
        helper = runner.module(runner.HELPERS[model], "helper")
        for source in baseline["arms"]:
            count, prior = source["scan_count"], source["prior"]
            sessions = baseline["session_ids"][:count]
            tracks, _ = helper.prepare(
                single,
                runner.CACHE,
                sessions,
                runner.replay_scans(single, sessions, source["search"]["selected"]),
            )
            for arm in result["arms"]:
                if (arm["model"], arm["view_scan_count"], arm["prior"]) != (model, count, prior):
                    continue
                if "failure" in arm:
                    continue
                taus = {"global": arm["global_tau_s"]} if model == "global" else arm["taus_s"]
                point = arm["latitude_deg"], arm["longitude_deg"]
                score = helper.score(single, tracks, point, taus, arm["scale_s"], True)
                assert math.isclose(
                    score["penalized_objective_rmse_hz"],
                    arm["penalized_objective_rmse_hz"],
                    abs_tol=1e-8,
                    rel_tol=0,
                )
                total = sum(row["weight_s"] for row in score["rows"])
                for name, cap in [
                    ("held_capped_rms_hz", 800.0),
                    ("held_uncapped_rms_hz", math.inf),
                ]:
                    arm[name] = math.sqrt(
                        sum(
                            row["weight_s"] * min(cap, row["evaluation_rms_hz"]) ** 2
                            for row in score["rows"]
                        )
                        / total
                    )
                arm["reference_error_km"] = single.haversine_km(point, single.REFERENCE)
    result["evaluation_bindings"] = {
        "tool": runner.digest(Path(__file__)),
        "inference": runner.digest(path),
    }
    (output / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    (output / "results.sha256").write_text(
        runner.digest(output / "results.json").split(":")[1] + "\n"
    )


if __name__ == "__main__":
    main()
