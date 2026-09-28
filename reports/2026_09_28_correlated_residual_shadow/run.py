"""Evaluate prespecified covariance arms without changing frozen locations."""

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from ds789_correlated_residual import independent_t, kernel, multivariate_t, quadratic  # noqa: E402

dataset = sys.argv[1]
plan = json.loads((HERE.parent / "2026_09_28_cross_dataset_position/plan.json").read_text())
group = next(g for g in plan["groups"] if g["dataset_id"] == dataset)
original = json.loads((ROOT / group["source_point_path"]).read_text())
stored = {
    (record["session_id"], t["track_id"]): t
    for record in original["evaluation"]
    for rx in record["receivers"]
    for t in rx["tracks"]
}
documents = baseline.load_documents({"config": plan["config"], "inputs": group["inputs"]})
arms = [
    {"family": family, "scale": scale, "decay_s": tau, "id": f"{family}_s{scale}_t{tau}"}
    for family, decays in (("iid", [0]), ("mvt", [0, 1, 10, 60]))
    for tau in decays
    for scale in (100, 300, 1000)
]
rows, variograms = [], []
rng = np.random.default_rng(20260928)
edges = np.array([0.0, 1.0, 5.0, 20.0, 60.0, np.inf])
for di, document in enumerate(documents):
    model = baseline.Stationary(document, plan["config"])
    point = np.array(original["x"][:2] + [original["x"][di + 2]])
    for track in document["tracks"]:
        old = stored[(document["session_id"], track["track_id"])]
        prediction, visible = model.prediction(track, point)
        offset = np.asarray(old["offsets"])
        residual = track["y"][None, :] - prediction - offset[:, None]
        mask = track["mask"]
        times = np.asarray(track["times_s"])
        stats = {}
        for tau in (0, 1, 10, 60):
            stats[tau] = (
                quadratic(residual[:, mask], kernel(times[mask], tau)),
                quadratic(residual, kernel(times, tau)),
            )
        for arm in arms:
            if arm["family"] == "iid":
                train = independent_t(residual[:, mask], arm["scale"])
                joint = independent_t(residual, arm["scale"])
            else:
                (qt, ldt), (qj, ldj) = stats[arm["decay_s"]]
                train = multivariate_t(qt, ldt, int(mask.sum()), arm["scale"])
                joint = multivariate_t(qj, ldj, len(times), arm["scale"])
            train = np.where(visible, train - 0.5 * offset**2 / 1e12, -np.inf)
            joint = np.where(visible, joint - 0.5 * offset**2 / 1e12, -np.inf)
            held = float(logsumexp(joint) - logsumexp(train))
            if arm["id"] == "iid_s100_t0":
                assert abs(held - old["held_log_score"]) < 1e-7
                assert np.allclose(np.exp(train - logsumexp(train)), old["weights"], atol=1e-9)
            rows.append(
                {
                    "dataset": dataset,
                    "session_id": document["session_id"],
                    "track_id": track["track_id"],
                    "receiver": track["receiver_id"],
                    "channel": track["channel"],
                    "arm": arm["id"],
                    "train": float(logsumexp(train) - math.log(track["catalogue_size"])),
                    "held": held,
                    "training_count": int(mask.sum()),
                    "held_count": int((~mask).sum()),
                }
            )
        # Only original training residuals enter the descriptive lag diagnostic.
        u = np.clip(residual[old["map"], mask] / 100, -5, 5)
        shuffled = rng.permutation(u)
        a, b = np.triu_indices(len(u), 1)
        lag = abs(times[mask][a] - times[mask][b])
        bins = np.searchsorted(edges, lag, side="left")
        for bin_id in range(6):
            use = bins == bin_id
            variograms.append(
                {
                    "session_id": document["session_id"],
                    "track_id": track["track_id"],
                    "bin": bin_id,
                    "pairs": int(use.sum()),
                    "squared_difference_sum": float(((u[a] - u[b]) ** 2)[use].sum()),
                    "shuffled_squared_difference_sum": float(
                        ((shuffled[a] - shuffled[b]) ** 2)[use].sum()
                    ),
                }
            )
assert len({(r["session_id"], r["track_id"]) for r in rows}) == len(stored)
totals = [
    {
        **arm,
        "train": sum(r["train"] for r in rows if r["arm"] == arm["id"]),
        "held": sum(r["held"] for r in rows if r["arm"] == arm["id"]),
    }
    for arm in arms
]
with (HERE / dataset / "result.json").open("x") as stream:
    json.dump(
        {"dataset": dataset, "arms": totals, "rows": rows, "variograms": variograms},
        stream,
        indent=2,
        allow_nan=False,
    )
print(json.dumps(totals, indent=2))
