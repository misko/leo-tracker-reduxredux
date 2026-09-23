"""Score frozen final identities on complementary rows after all-arm sealing."""

import json
import math
from pathlib import Path

import run as runner


def main():
    output = runner.HERE / "results"
    path = output / "inference.json"
    assert runner.digest(path).split(":")[1] == path.with_suffix(".sha256").read_text().strip()
    result = json.loads(path.read_text())
    for key, source in runner.PATHS.items():
        assert runner.digest(source) == result["bindings"][key]
    for binding in result["cache_bindings"]:
        for filename, key in [("state_cache.npz", "cache"), ("cache_receipt.json", "receipt")]:
            assert runner.digest(runner.CACHE / binding["session_id"] / filename) == binding[key]
    helper, single = [runner.load(runner.PATHS[key], key) for key in ("helper", "single")]
    for arm in result["arms"]:
        scans = [
            {
                "session_id": sid,
                "tracks": [r for r in arm["fixed_tracks"] if r["session_id"] == sid],
            }
            for sid in result["sessions"]
        ]
        tracks, _ = helper.prepare(single, runner.CACHE, result["sessions"], scans)
        point = arm["latitude_deg"], arm["longitude_deg"]
        scored = helper.score(single, tracks, point, arm["taus_s"], arm["scale_s"], True)
        assert math.isclose(
            scored["penalized_objective_rmse_hz"],
            arm["penalized_objective_rmse_hz"],
            abs_tol=1e-8,
            rel_tol=0,
        )
        total = sum(row["weight_s"] for row in scored["rows"])
        for key, cap in [("held_capped_rms_hz", 800), ("held_uncapped_rms_hz", math.inf)]:
            arm[key] = math.sqrt(
                sum(
                    row["weight_s"] * min(cap, row["evaluation_rms_hz"]) ** 2
                    for row in scored["rows"]
                )
                / total
            )
        arm["reference_error_km"] = single.haversine_km(point, single.REFERENCE)
        arm["tau_boundary_count"] = sum(abs(value) >= 4.998 for value in arm["taus_s"].values())
    result["evaluation_bindings"] = {
        "tool": runner.digest(Path(__file__)),
        "inference": runner.digest(path),
    }
    path = output / "results.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    path.with_suffix(".sha256").write_text(runner.digest(path).split(":")[1] + "\n")


if __name__ == "__main__":
    main()
