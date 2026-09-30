"""Fixed ridge models for neighboring-symbol/carrier explanations of early I."""

import hashlib
import json
from pathlib import Path

import numpy as np
from early_iq import compare

BASE = Path(__file__).resolve().parent


def predict(x, y, test, shift=0):
    """Per-coordinate ridge with fixed penalty; only discovery data fit parameters."""
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale = np.maximum(scale, 1e-8)
    a, b = (x - mean) / scale, (test - mean) / scale
    center = y.mean()
    coef = np.linalg.solve(a.T @ a + len(a) * np.eye(a.shape[1]),
                           a.T @ (np.roll(y, shift) - center))
    return b @ coef + center


def analyze(path):
    source = json.loads((path.parent / "summary.json").read_text())
    h = source["header"]
    if "evaluation_frames" not in h:
        return None
    assert hashlib.sha256(path.read_bytes()).hexdigest() == h["sha256"]
    train, test = h["discovery_frames"], h["evaluation_frames"]
    with np.load(path) as d:
        bins = d["bins0"]
        assert np.array_equal(bins, d["bins1"])
        streams = [d["z0"], d["z1"]]
    lookup = {int(k): i for i, k in enumerate(bins)}
    targets = [int(k) for k in bins if k - 1 in lookup and k + 1 in lookup]
    rows = []
    for symbol in (4, 6):
        s = symbol - 2
        for mode in ("adjacent_carriers", "adjacent_symbols", "both"):
            raw, residual, errors, controls = [], [], [], []
            for z in streams:
                ys, ps, ms, nulls = [], [], [], []
                for k in targets:
                    c = lookup[k]
                    neighbors = []
                    if mode in ("adjacent_carriers", "both"):
                        neighbors.extend([z[:, s, lookup[k - 1]], z[:, s, lookup[k + 1]]])
                    if mode in ("adjacent_symbols", "both"):
                        neighbors.extend([z[:, s - 1, c], z[:, s + 1, c]])
                    x = np.column_stack([v for q in neighbors for v in (q.real, q.imag)])
                    y = z[:, s, c].real
                    ys.append(y[test])
                    ms.append(np.full(len(test), y[train].mean()))
                    ps.append(predict(x[train], y[train], x[test]))
                    nulls.append([predict(x[train], y[train], x[test], shift)
                                  for shift in range(1, len(train))])
                y, p, m = np.array(ys).T, np.array(ps).T, np.array(ms).T
                null = np.array(nulls).transpose(1, 2, 0)
                base = np.mean((y - m) ** 2)
                raw.append(y - m)
                residual.append(y - p)
                errors.append(float(1 - np.mean((y - p) ** 2) / base))
                controls.append((1 - np.mean((y[None] - null) ** 2, axis=(1, 2)) / base).tolist())
            rows.append(dict(symbol=symbol, model=mode, target_bins=targets,
                             heldout_mse_reduction=errors,
                             shuffled_training_mse_reductions=controls,
                             before=compare(*raw), after=compare(*residual)))
    return dict(visit=path.parent.name, source_sha256=h["sha256"],
                train_frames=train, evaluation_frames=test, rows=rows)


def main():
    rows = [r for p in sorted((BASE / "local/paired").glob("*/*-data-soft.npz"))
            if (r := analyze(p)) is not None]
    result = dict(visits=rows,
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Fixed per-target ridge alpha=1 on standardized features, fitted "
                  "independently per RX on discovery frames. Same targets for every model. "
                  "Predictability does not distinguish physical leakage from coded redundancy; "
                  "failure does not exclude nonlinear or unobserved-carrier leakage. No new bits.")
    out = BASE / "local/within-visit/neighbor-prediction.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    for r in rows:
        print(r["visit"])
        for a in r["rows"]:
            print(a["symbol"], a["model"], a["heldout_mse_reduction"],
                  a["before"]["centered_correlation"], a["after"]["centered_correlation"])


if __name__ == "__main__":
    main()
