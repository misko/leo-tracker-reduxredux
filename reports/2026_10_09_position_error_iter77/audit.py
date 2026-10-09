"""Uniform existing endpoint comparison; no new fits or truth-based selection."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(path):
    return json.loads(path.read_text())


def main():
    plan = read(HERE / "protocol.json")
    for path, digest in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
    assert not (HERE / "results.json").exists(), "Preserve executed audit"
    cohort = read(ROOT / "reports/2026_10_09_position_error_iter65/snapshot.json")
    rows = []
    for case in cohort["cases"]:
        result = read(ROOT / case["result_source"])
        endpoints = {
            "upstream": result["upstream"]["operational"],
            "control-refit": result["extension"]["control_operational"],
            "satellite-slope": result["extension"]["operational"],
        }
        values = {}
        for name, endpoint in endpoints.items():
            values[name] = {}
            for arm in ("fitted-c", "zero-c"):
                r = endpoint[arm]
                values[name][arm] = {
                    k: r.get(k)
                    for k in ("stage", "converged", "error_km", "posterior_rms_hz", "objective")
                }
                assert values[name][arm]["error_km"] is not None
                if name == "satellite-slope":
                    assert abs(r["error_km"] - case["arms"][arm]["candidate"]["error_km"]) < 1e-9
        rows.append(dict(member=case["member"], endpoints=values))
    assert len(rows) == 148
    (HERE / "results.json").write_text(json.dumps(dict(rows=rows), indent=2) + "\n")
    print("148 matched endpoint comparisons; frozen final reproduces iteration65")


if __name__ == "__main__":
    main()
