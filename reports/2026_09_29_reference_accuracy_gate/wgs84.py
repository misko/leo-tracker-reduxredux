"""Use ellipsoidal distances for the conditional physical-distance bound."""

import hashlib
import importlib.metadata
import json
from pathlib import Path

from geographiclib.geodesic import Geodesic
from study import HERE, REPORTS, ROOT, gate, read


def main():
    initial = read(HERE / "results.json")
    for name, h in initial["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == h, name
    ref = initial["reference"]
    manifest = read(REPORTS / "2026_09_29_scan_budget/manifest.json")
    rows = []
    for r in initial["rows"]:
        method, ds = r["method"], r["dataset"]
        if method == "configured_center":
            point = manifest["config"]["geographic_prior_center_deg"]
        else:
            p = (
                REPORTS
                / f"2026_09_29_{method}"
                / (f"{ds}_n24_0.json" if method == "scan_budget" else f"{ds}.json")
            )
            point = read(p)["selected"]["estimate_deg"]
        error = Geodesic.WGS84.Inverse(*point, *ref)["s12"]
        rows.append(
            dict(
                dataset=ds,
                method=method,
                wgs84_reference_error_m=error,
                spherical_minus_wgs84_m=r["reference_error_m"] - error,
                strict_reference_bound_limit_m=1000 - error if error < 1000 else None,
                current_gate=gate(error),
                conditional_gates={
                    str(bound): gate(error, bound) for bound in (25, 50, 100, 250, 500)
                },
            )
        )
    result = dict(
        rows=rows,
        reference=ref,
        reference_bound_status="not supplied",
        geographiclib_version=importlib.metadata.version("geographiclib"),
        hashes={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (HERE / "results.json", Path(__file__))
        },
    )
    with (HERE / "wgs84-results.json").open("x") as out:
        json.dump(result, out, indent=2, allow_nan=False)
    for r in rows:
        print(
            r["dataset"],
            r["method"],
            r["wgs84_reference_error_m"],
            r["strict_reference_bound_limit_m"],
        )


if __name__ == "__main__":
    main()
