"""Re-evaluate frozen local amplitude fits; inventory neighboring-symbol controls."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

BASE = Path(__file__).resolve().parent
EXT = (BASE.parents[3] / "reports") / "2026_09_29_ds10_signal_extension/local"


def read(path):
    raw = path.read_bytes()
    return json.loads(raw), dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest())


def discrete_density(values, levels, amplitude, noise):
    centers = np.arange(levels) * 2 - (levels - 1)
    centers = centers / np.sqrt(np.mean(centers ** 2))
    residual = (values[:, None] - centers[None, :, None] * amplitude) / noise
    conditional = -.5 * np.sum(residual ** 2, axis=2)
    conditional -= np.log(noise).sum() + np.log(2 * np.pi)
    return logsumexp(conditional, axis=1) - np.log(levels)


def main():
    paired, paired_source = read(EXT / "within-visit/amplitude-levels/summary.json")
    neighbors, neighbor_source = read(EXT / "within-visit/neighbor-prediction.json")
    raw, raw_source = read(EXT / "within-visit/raw-axis-levels.json")
    models, neighbor_rows = [], []
    for visit in paired["visits"]:
        name = visit["visit"]
        path = EXT / "paired" / name / f"{name}-data-soft.npz"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == visit["source_sha256"]
        train, test = visit["discovery_frames"], visit["evaluation_frames"]
        with np.load(path) as data:
            for row in visit["rows"]:
                a, b = [], []
                for rx in range(2):
                    z = data[f"z{rx}"][:, row["symbol"] - 2].real
                    mean, std = z[train].mean(axis=0), np.maximum(z[train].std(axis=0), 1e-8)
                    a.append((z[train] - mean) / std)
                    b.append((z[test] - mean) / std)
                x = np.stack(a, axis=-1).reshape(-1, 2)
                y = np.stack(b, axis=-1).reshape(-1, 2)
                cov = np.cov(x.T, bias=True) + np.eye(2) * 1e-8
                residual = y - x.mean(axis=0)
                gaussian = -.5 * np.sum(residual * np.linalg.solve(cov, residual.T).T, axis=1)
                gaussian -= np.log(2 * np.pi) + .5 * np.linalg.slogdet(cov)[1]
                np.testing.assert_allclose(gaussian.mean(), row["gaussian_test_log_likelihood"])
                for model in row["models"]:
                    likelihood = discrete_density(y, model["levels"],
                                                  np.array(model["amplitude"]),
                                                  np.array(model["noise_std"]))
                    delta = (likelihood - gaussian).reshape(len(test), -1).mean(axis=1)
                    np.testing.assert_allclose(delta, model["frame_deltas"], atol=1e-10)
                    np.testing.assert_allclose(delta.mean(), model["delta_from_gaussian"])
                    models.append(dict(visit=name, symbol=row["symbol"], **model))
    for visit in neighbors["visits"]:
        for row in visit["rows"]:
            for rx in range(2):
                observed = row["heldout_mse_reduction"][rx]
                null = np.asarray(row["shuffled_training_mse_reductions"][rx])
                rank = float((1 + np.sum(null >= observed - 1e-12)) / (1 + len(null)))
                neighbor_rows.append(dict(visit=visit["visit"], symbol=row["symbol"], rx=rx,
                                          model=row["model"], mse_reduction=observed,
                                          training_shift_rank=rank,
                                          before=row["before"], after=row["after"]))
    for row in raw["rows"]:
        np.testing.assert_allclose(np.mean(row["frame_deltas"]), row["delta_from_gaussian"])
    pooled = [dict(symbol=s, levels=k, equal_visit_mean=float(np.mean([
        r["delta_from_gaussian"] for r in models if r["symbol"] == s and r["levels"] == k])))
        for s in (4, 6) for k in (2, 4)]
    result = dict(models=models, equal_visit_descriptive=pooled, neighbors=neighbor_rows,
                  raw_axis_rows=raw["rows"], sources=[paired_source, neighbor_source, raw_source],
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Frozen local paired likelihoods re-evaluated from hash-verified "
                  "NPZ; raw-axis and neighbor receipts arithmetically audited, not refitted. "
                  "Public reference rows are historical only. No new RF or new hypothesis bank. "
                  "All pooled scores descriptive: same session, dependent frames/carriers. "
                  "Discrete-model failure does not identify physical origin "
                  "or disprove modulation.")
    (BASE / "local/amplitude-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Paired fits", len(models), "equal-visit gains", pooled)
    print("Neighbor tests", len(neighbor_rows), "positive reductions",
          sum(r["mse_reduction"] > 0 for r in neighbor_rows), "range",
          min(r["mse_reduction"] for r in neighbor_rows),
          max(r["mse_reduction"] for r in neighbor_rows))


if __name__ == "__main__":
    main()
