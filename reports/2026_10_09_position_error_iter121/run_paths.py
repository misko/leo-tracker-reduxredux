"""Freeze approved conditional policy and export inference-only causal paths."""

import hashlib
import json
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    source = HERE / "selected-positions.json"
    data = json.loads(source.read_text())
    assert data["count"] == len(data["members"]) == 193
    forbidden = {"error_km", "reference_latitude_deg", "reference_longitude_deg", "research_errors"}

    def check(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for item in value.values():
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)

    check(data)
    sources = [
        source,
        HERE / "causal.py",
        HERE / "extract.py",
        HERE / "run_paths.py",
        HERE / "AUTHORITY.md",
    ]
    protocol = {
        "scope": ("Conditional stationary capture-order retrospective; "
                  "standalone comparator107recovery candidate, not deployedB7"),
        "members": 193,
        "stationarity": "hypothetical unverified",
        "availability": "capture-start order, no online latency claim",
        "ordering": ["capture_start_utc_ns", "label"],
        "arms": ["fitted-c", "zero-c"],
        "algorithms": [
            "standalone107candidate",
            "cumulative arithmetic mean",
            "cumulative coordinate median",
        ],
        "resets": {"primary": "one hypothetical episode", "secondary": "dataset"},
        "qualification": ("existing selected fit converged; "
                          "absent/unqualified yields outage with held state"),
        "chart": ("arm-specific first qualified endpoint equirectangular,"
                  "6371.0088km radius;nonpolar only"),
        "accuracy_evaluated": False,
        "source_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
    }
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(protocol, stream, indent=2)
        stream.write("\n")
    api = runpy.run_path(str(HERE / "causal.py"))
    ordered = sorted(data["members"], key=lambda x: (x["capture_start_utc_ns"], x["label"]))
    results = {}
    for mode in ("primary", "secondary"):
        rows = [
            {
                "label": m["label"],
                "order_ns": m["capture_start_utc_ns"],
                "reset_group": "conditional-static" if mode == "primary" else m["dataset"],
                "arms": {
                    a: None
                    if m["arms"][a] is None or not m["arms"][a]["qualified"]
                    else m["arms"][a]["latlon"]
                    for a in ("fitted-c", "zero-c")
                },
            }
            for m in ordered
        ]
        results[mode] = api["fuse"](rows)
    coverage = {
        dataset: {
            "members": sum(m["dataset"] == dataset for m in ordered),
            "outages": {
                a: sum(
                    m["dataset"] == dataset
                    and (m["arms"][a] is None or not m["arms"][a]["qualified"])
                    for m in ordered
                )
                for a in ("fitted-c", "zero-c")
            },
        }
        for dataset in sorted({m["dataset"] for m in ordered})
    }
    payload = {
        "protocol_sha256": hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest(),
        "coverage": coverage,
        "paths": results,
        "accuracy_evaluated": False,
    }
    with (HERE / "causal-paths.json").open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
