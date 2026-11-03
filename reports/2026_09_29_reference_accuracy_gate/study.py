"""Conditional metric bounds; never infer missing reference uncertainty."""

import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPORTS = HERE.parent


def read(p):
    return json.loads(p.read_text())


def distance(a, b):
    p, q, r, s = map(math.radians, [*a, *b])
    return (
        2
        * 6371008.8
        * math.asin(
            math.sqrt(
                math.sin((p - r) / 2) ** 2 + math.cos(p) * math.cos(r) * math.sin((q - s) / 2) ** 2
            )
        )
    )


def gate(error_m, reference_bound_m=None, threshold_m=1000.0):
    assert math.isfinite(error_m) and error_m >= 0
    if reference_bound_m is None:
        return dict(status="unverified_reference_bound", true_error_upper_bound_m=None)
    if not math.isfinite(reference_bound_m) or reference_bound_m < 0:
        raise ValueError("Reference bound must be finite and nonnegative")
    upper = error_m + reference_bound_m
    return dict(
        status="below_threshold" if upper < threshold_m else "not_certified",
        true_error_upper_bound_m=upper,
    )


def main():
    posepath = ROOT / "deploy/station/gauss-r20-roof-20260926-v1.json"
    pose = read(posepath)
    reference = [pose["latitude_deg"], pose["longitude_deg"]]
    path = REPORTS / "2026_09_29_scan_budget/manifest.json"
    manifest = read(path)
    center = manifest["config"]["geographic_prior_center_deg"]
    paths = [posepath, path, HERE / "study.py", HERE / "test_study.py"]
    rows = []
    for ds in ("DS7", "DS8", "DS9"):
        pool = next(s for s in manifest["sets"] if s["dataset"] == ds and s["count"] == 24)
        # Timestamp compatibility is not a complete radio/pose binding audit.
        assert all(
            pose["valid_from_utc_ns"] <= s["start_utc_ns"]
            and s["start_utc_ns"] + 300_000_000_000 <= pose["valid_until_utc_ns"]
            for s in pool["scans"]
        )
        estimates = [("configured_center", center)]
        for folder, key in (
            ("2026_09_29_scan_budget", "selected"),
            ("2026_09_29_information_selection", "selected"),
            ("2026_09_29_score_balanced_selection", "selected"),
        ):
            p = (
                REPORTS
                / folder
                / (f"{ds}_n24_0.json" if folder.endswith("scan_budget") else f"{ds}.json")
            )
            paths.append(p)
            r = read(p)
            assert r[key]["qualified"]
            estimates.append((folder.removeprefix("2026_09_29_"), r[key]["estimate_deg"]))
        for label, point in estimates:
            error = distance(point, reference)
            rows.append(
                dict(
                    dataset=ds,
                    method=label,
                    reference_error_m=error,
                    strict_reference_bound_limit_m=1000 - error if error < 1000 else None,
                    current_gate=gate(error),
                    conditional_gates={
                        str(bound): gate(error, bound) for bound in (25, 50, 100, 250, 500)
                    },
                )
            )
    result = dict(
        reference=reference,
        position_evidence=pose["position_evidence"],
        datum_assumption="WGS84 as interpreted in station record",
        reference_uncertainty_supplied=False,
        rows=rows,
        hashes={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
        },
    )
    with (HERE / "results.json").open("x") as out:
        json.dump(result, out, indent=2, allow_nan=False)
    for r in rows:
        print(
            r["dataset"], r["method"], r["reference_error_m"], r["strict_reference_bound_limit_m"]
        )


if __name__ == "__main__":
    main()
