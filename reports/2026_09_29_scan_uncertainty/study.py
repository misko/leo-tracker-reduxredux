import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "2026_09_29_scan_disagreement"


def covariance(hessian, scores):
    hessian, scores = np.asarray(hessian), np.asarray(scores)
    assert scores.ndim == 2 and scores.shape[1] == hessian.shape[0] and len(scores) > 1
    assert np.isfinite(hessian).all() and np.isfinite(scores).all()
    assert np.linalg.eigvalsh(hessian).min() > 0
    inverse = np.linalg.inv(hessian)
    centered = scores - scores.mean(axis=0)
    meat = centered.T @ centered * len(scores) / (len(scores) - 1)
    result = inverse @ meat @ inverse
    return (result + result.T) / 2


def describe(c, h):
    eigen, vectors = np.linalg.eigh(c)
    assert eigen.min() > 0
    he, hv = np.linalg.eigh(h)
    root = (hv * np.sqrt(he)) @ hv.T
    inflation = np.linalg.eigvalsh(root @ c @ root)
    return dict(
        covariance_km2=c.tolist(),
        axis_scales_m=(1000 * np.sqrt(eigen)).tolist(),
        major_axis_east_north=vectors[:, -1].tolist(),
        generalized_variance_inflation=inflation.tolist(),
        generalized_scale_inflation=np.sqrt(inflation).tolist(),
    )


def main():
    for line in (SOURCE / "evidence.sha256").read_text().splitlines():
        h, name = line.split("  ", 1)
        assert hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == h, name
    rows = []
    for ds in ("DS7", "DS8", "DS9"):
        data = json.loads((SOURCE / f"{ds}.json").read_text())
        assert len(data["rows"]) == 24 and all(r["qualified"] for r in data["rows"])
        h = sum(np.array(r["profiled_hessian"]) for r in data["rows"])
        scores = np.array([r["profiled_gradient"] for r in data["rows"]])
        blocks = np.array(
            [
                sum(np.array(r["profiled_gradient"]) for r in data["rows"] if r["window"] == w)
                for w in ("early", "middle", "late")
            ]
        )
        assert all(
            sum(r["window"] == w for r in data["rows"]) == 8 for w in ("early", "middle", "late")
        )
        np.testing.assert_allclose(blocks.sum(0), scores.sum(0), atol=1e-10)
        rows.append(
            dict(
                dataset=ds,
                score_sum=scores.sum(0).tolist(),
                pooled_hessian=h.tolist(),
                curvature=describe(np.linalg.inv(h), h),
                scan=describe(covariance(h, scores), h),
                window=describe(covariance(h, blocks), h),
            )
        )
    hashes = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [
            SOURCE / "evidence.sha256",
            HERE / "study.py",
            HERE / "test_study.py",
            HERE / "PROTOCOL.md",
        ]
    }
    with (HERE / "results.json").open("x") as out:
        json.dump(dict(rows=rows, hashes=hashes), out, indent=2, allow_nan=False)
    for r in rows:
        print(
            r["dataset"],
            {key: r[key]["axis_scales_m"] for key in ("curvature", "scan", "window")},
            "scan scale inflation",
            r["scan"]["generalized_scale_inflation"],
        )


if __name__ == "__main__":
    main()
