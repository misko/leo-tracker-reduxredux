"""Fit one bounded revision coefficient on donor training observations only."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar

HERE = Path(__file__).resolve().parent


def centered(row):
    m = np.asarray(row["mask"], bool)
    e = np.asarray(row["residual"])
    d = np.asarray(row["delta"])
    return e - e[m].mean(), d - d[m].mean(), m


def fit(rows):
    groups = {}
    for r in rows:
        e, d, m = centered(r)
        groups.setdefault(r["unit_id"][:3], []).append((e[m], d[m]))

    def loss(beta):
        return float(
            np.mean(
                [
                    np.mean(
                        [np.mean(2.5 * np.log1p(((e - beta * d) / 100) ** 2 / 4)) for e, d in cases]
                    )
                    for cases in groups.values()
                ]
            )
        )

    grid = np.linspace(-1, 1, 81)
    scores = [loss(b) for b in grid]
    candidates = [(s, float(b)) for s, b in zip(scores, grid, strict=True)]
    for i in range(1, 80):
        if scores[i] <= scores[i - 1] and scores[i] <= scores[i + 1]:
            result = minimize_scalar(
                loss, bounds=(grid[i - 1], grid[i + 1]), method="bounded", options={"xatol": 1e-9}
            )
            assert result.success
            candidates.append((float(result.fun), float(result.x)))
    score, beta = min(candidates)
    return dict(beta=beta, training_loss=score, zero_training_loss=loss(0))


def main():
    source = HERE / "directions.json"
    doc = json.loads(source.read_text())
    for path, digest in doc["hashes"].items():
        assert hashlib.sha256((HERE.parent.parent / path).read_bytes()).hexdigest() == digest
    rows = doc["rows"]
    folds = {}
    results = []
    for ds in ("DS7", "DS8", "DS9"):
        donors = [r for r in rows if not r["unit_id"].startswith(ds)]
        fitted = fit(donors)
        folds[ds] = dict(**fitted, donor_cases=len(donors))
        for r in rows:
            if not r["unit_id"].startswith(ds):
                continue
            e, d, m = centered(r)
            result = {
                k: r[k]
                for k in ("unit_id", "session_id", "track_id", "number", "status", "changed")
            }
            for arm, beta in (
                ("zero", 0),
                ("fitted", fitted["beta"]),
                ("older", 1),
                ("extrapolate", -1),
            ):
                result[arm] = float(np.median(abs((e - beta * d)[~m])))
            results.append(result)
        print(ds, fitted, flush=True)
    hashes = {
        str(p.relative_to(HERE.parent.parent)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (source, HERE / "fit.py", HERE / "PROTOCOL.md")
    }
    (HERE / "results.json").write_text(
        json.dumps(dict(hashes=hashes, folds=folds, rows=results), indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
