"""Saved-position directional evaluation; run only after protocol publication."""

import hashlib
import json
import runpy
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def summaries(vectors):
    v = np.asarray(vectors, dtype=float)
    return {
        "count": len(v),
        "mean_vector_km": np.mean(v, axis=0).tolist(),
        "coordinate_median_vector_km": np.median(v, axis=0).tolist(),
        "rms_vector_km": float(np.sqrt(np.mean(np.sum(v * v, axis=1)))),
    }


def alignment(residual, displacement):
    r, d = np.asarray(residual), np.asarray(displacement)
    norms = np.linalg.norm(r) * np.linalg.norm(d)
    return None if norms <= 1e-12 else float(np.dot(r, d) / norms)


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    for path, digest in plan["source_sha256"].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    source = json.loads((ROOT / plan["positions"]).read_text())
    rows = sorted(source["members"], key=lambda x: (x["capture_start_utc_ns"], x["label"]))
    assert len(rows) == 193 and all(
        x["arms"][a] and x["arms"][a]["qualified"] for x in rows for a in ("fitted-c", "zero-c")
    )
    chart = runpy.run_path(str(ROOT / plan["chart_source"]))["chart"]
    origin = rows[0]["arms"]["fitted-c"]["latlon"]
    old = ROOT / "reports/2026_10_09_position_error_iter107"
    port = runpy.run_path(str(old / "report.py"))
    members = json.loads((old / "protocol.json").read_text())["members"]
    authority = {port["member_label"](m): m for m in members}
    evaluated = []
    for row in rows:
        doc = port["evaluation_document"](authority[row["label"]])
        truth = [doc["reference_latitude_deg"], doc["reference_longitude_deg"]]
        fixes = {a: chart(row["arms"][a]["latlon"], origin) for a in ("fitted-c", "zero-c")}
        residuals = {a: fix - chart(truth, origin) for a, fix in fixes.items()}
        displacement = fixes["fitted-c"] - fixes["zero-c"]
        evaluated.append(
            {
                "label": row["label"],
                "dataset": row["dataset"],
                "signed_residual_km": {a: r.tolist() for a, r in residuals.items()},
                "fitted_minus_zero_displacement_km": displacement.tolist(),
                "alignment": {a: alignment(r, displacement) for a, r in residuals.items()},
            }
        )
    groups = ["full", *sorted({r["dataset"] for r in evaluated})]
    summary = {
        g: {
            "arms": {
                a: summaries(
                    [
                        r["signed_residual_km"][a]
                        for r in evaluated
                        if g == "full" or r["dataset"] == g
                    ]
                )
                for a in ("fitted-c", "zero-c")
            },
            "paired_displacement": summaries(
                [
                    r["fitted_minus_zero_displacement_km"]
                    for r in evaluated
                    if g == "full" or r["dataset"] == g
                ]
            ),
        }
        for g in groups
    }
    payload = {
        "scope": plan["scope"],
        "origin_selected_endpoint": origin,
        "origin_label": rows[0]["label"],
        "coordinate_basis": ["east_km", "north_km"],
        "summaries": summary,
        "members": evaluated,
        "reference_use": "evaluation signed residuals only",
        "weak_direction_alignment": "not performed; basis transport not admitted",
        "clock_features": "not performed; gauges not admitted",
    }
    with (HERE / "evaluation.json").open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
