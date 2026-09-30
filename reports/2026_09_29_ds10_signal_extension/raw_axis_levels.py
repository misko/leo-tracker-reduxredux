"""Uncentered-per-carrier binary mixture test with a public soft-reference control."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from scipy.optimize import minimize
from scipy.special import expit, logsumexp

BASE = Path(__file__).resolve().parent


def logpdf(x, p):
    center, amplitude, sigma, probability = p[0], np.exp(p[1]), np.exp(p[2]), expit(p[3])
    means = center + amplitude * np.array([-1., 1.])
    z = (x[:, None] - means) / sigma
    return logsumexp(-.5 * z ** 2 - np.log(sigma) - .5 * np.log(2 * np.pi)
                     + np.log([1 - probability, probability]), axis=1)


def assess(train, test):
    # One scalar normalization over the whole training population preserves
    # each carrier's differing occupancy. No per-carrier centering/scaling.
    mean, scale = train.mean(), max(train.std(), 1e-8)
    x, y = (train.ravel() - mean) / scale, (test.ravel() - mean) / scale
    fits = [minimize(lambda p: -logpdf(x, p).mean(),
                     [0, np.log(a), np.log(np.sqrt(1 - a * a)), logit],
                     method="L-BFGS-B", bounds=[(-3, 3), (-7, 2), (-7, 2), (-5, 5)])
            for a in (.3, .8) for logit in (-1., 0., 1.)]
    good = [f for f in fits if f.success and np.isfinite(f.fun)]
    if not good:
        raise ValueError("No converged mixture fit")
    best = min(good, key=lambda f: f.fun)
    gaussian = -.5 * y ** 2 - .5 * np.log(2 * np.pi)
    delta = (logpdf(y, best.x) - gaussian).reshape(test.shape).mean(axis=1)
    return dict(delta_from_gaussian=float(delta.mean()), frame_deltas=delta.tolist(),
                centers=(mean + scale * (best.x[0] + np.exp(best.x[1])
                                         * np.array([-1., 1.]))).tolist(),
                noise_std=float(scale * np.exp(best.x[2])),
                upper_probability=float(expit(best.x[3])), converged_starts=len(good))


def main():
    rows, hashes = [], {}
    bins = None
    for path in sorted((BASE / "local/paired").glob("*/*-data-soft.npz")):
        h = json.loads((path.parent / "summary.json").read_text())["header"]
        if "evaluation_frames" not in h:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == h["sha256"]
        hashes[str(path)] = digest
        with np.load(path) as d:
            assert np.array_equal(d["bins0"], d["bins1"])
            if bins is None:
                bins = d["bins0"]
            assert np.array_equal(bins, d["bins0"])
            for rx in range(2):
                for symbol in (4, 6):
                    z = d[f"z{rx}"][:, symbol - 2].real
                    rows.append(dict(source=path.parent.name, rx=rx, symbol=symbol,
                                     **assess(z[h["discovery_frames"]],
                                              z[h["evaluation_frames"]])))
    reference = BASE.parent / "2026_09_28_sequence_semantics/local/full-soft-reference-0-12.npz"
    template_path = BASE.parents[1] / (
        "docs/research/starlink-literature/local/data/ut-pilots/supplement/"
        "reference-template/referenceTemplate.mat")
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = np.load(reference)["symbols"][:, :, bins] * np.exp(-.5j * np.pi * template[bins].T)
    for symbol in (4, 6):
        rows.append(dict(source="public_soft_reference", rx=None, symbol=symbol,
                         **assess(z[:6, symbol - 1].real, z[6:, symbol - 1].real)))
    for path in (reference, template_path, Path(__file__)):
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    result = dict(rows=rows, bins=bins.tolist(), input_sha256=hashes,
                  limitations="Raw real axis, scalar train normalization. Free mixture weight, "
                  "midpoint, spacing and common noise variance. Fits chosen on discovery only. "
                  "Reference is published soft estimation, not independent raw truth. "
                  "Pooled carriers/frames dependent; mixture advantage does not decode fields.")
    out = BASE / "local/within-visit/raw-axis-levels.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    for r in rows:
        print(r["source"], r["rx"], r["symbol"], r["delta_from_gaussian"], r["centers"])


if __name__ == "__main__":
    main()
