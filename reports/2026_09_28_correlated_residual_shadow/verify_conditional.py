"""Independent selected-arm replay through SciPy conditional-t densities."""

import json
import sys
from pathlib import Path

import numpy as np
from scipy.special import logsumexp
from scipy.stats import multivariate_t

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402

plan = json.loads((HERE.parent / "2026_09_28_cross_dataset_position/plan.json").read_text())
scores = json.loads((HERE / "scores.json").read_text())
checked, errors = 0, []
for group in plan["groups"]:
    ds = group["dataset_id"]
    result = json.loads((HERE / ds / "result.json").read_text())
    selected = next(s for s in scores["selections"] if s["dataset"] == ds)["selected"]["correlated"]
    originals = json.loads((ROOT / group["source_point_path"]).read_text())
    old = {
        (r["session_id"], t["track_id"]): t
        for r in originals["evaluation"]
        for rx in r["receivers"]
        for t in rx["tracks"]
    }
    expected = {
        (r["session_id"], r["track_id"]): r for r in result["rows"] if r["arm"] == selected["id"]
    }
    docs = baseline.load_documents({"config": plan["config"], "inputs": group["inputs"]})
    for di, doc in enumerate(docs):
        model = baseline.Stationary(doc, plan["config"])
        point = np.array(originals["x"][:2] + [originals["x"][di + 2]])
        for track in doc["tracks"]:
            key = (doc["session_id"], track["track_id"])
            prediction, visible = model.prediction(track, point)
            offset = np.asarray(old[key]["offsets"])
            r = track["y"][None, :] - prediction - offset[:, None]
            times = np.asarray(track["times_s"])
            n = len(times)
            cov = selected["scale"] ** 2 * (
                0.8 * np.exp(-np.abs(np.subtract.outer(times, times)) / selected["decay_s"])
                + 0.2 * np.eye(n)
            )
            ti = np.flatnonzero(track["mask"])
            hi = np.flatnonzero(~track["mask"])
            a, b, c = cov[np.ix_(ti, ti)], cov[np.ix_(hi, ti)], cov[np.ix_(hi, hi)]
            inverse_residual = np.linalg.solve(a, r[:, ti].T)
            q = np.sum(r[:, ti].T * inverse_residual, axis=0)
            mean = (b @ inverse_residual).T
            schur = c - b @ np.linalg.solve(a, b.T)
            train = (
                np.asarray(multivariate_t.logpdf(r[:, ti], loc=np.zeros(len(ti)), shape=a, df=4))
                - 0.5 * offset**2 / 1e12
            )
            conditional = np.array(
                [
                    float(
                        multivariate_t.logpdf(
                            r[k, hi] - mean[k],
                            loc=np.zeros(len(hi)),
                            shape=schur * (4 + q[k]) / (4 + len(ti)),
                            df=4 + len(ti),
                        )
                    )
                    for k in range(len(r))
                ]
            )
            train = np.where(visible, train, -np.inf)
            held = float(logsumexp(train + conditional) - logsumexp(train))
            error = abs(held - expected[key]["held"])
            assert error < 1e-7, (key, error)
            errors.append(error)
            checked += 1
    print(ds, "checked", len(expected), flush=True)
print(json.dumps({"checked_tracks": checked, "maximum_absolute_held_difference": max(errors)}))
