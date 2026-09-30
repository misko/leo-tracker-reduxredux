"""Held-out paired likelihood: equally spaced discrete levels vs continuous variation."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp

BASE = Path(__file__).resolve().parent


def discrete_logpdf(x, parameters, levels):
    # Independent receiver noise conditional on a shared discrete level.
    amplitude = np.exp(parameters[:2])
    noise = np.exp(parameters[2:])
    z = (x[:, None, :] - levels[None, :, None] * amplitude) / noise
    conditional = -.5 * (z ** 2).sum(axis=2) - np.log(noise).sum() - np.log(2 * np.pi)
    return logsumexp(conditional, axis=1) - np.log(len(levels))


def fit_levels(train, test, k):
    levels = np.arange(k, dtype=float) * 2 - (k - 1)
    levels /= np.sqrt(np.mean(levels ** 2))
    fits = []
    for initial in (.2, .6, .9):
        guess = np.log([initial, initial, np.sqrt(1 - initial ** 2),
                        np.sqrt(1 - initial ** 2)])
        fits.append(minimize(lambda p: -discrete_logpdf(train, p, levels).mean(), guess,
                             method="L-BFGS-B", bounds=[(-7, 2)] * 4))
    successful = [f for f in fits if f.success and np.isfinite(f.fun)]
    if not successful:
        raise ValueError("No converged discrete-level fit")
    best = min(successful, key=lambda f: f.fun)
    ll = discrete_logpdf(test, best.x, levels)
    return dict(levels=k, amplitude=np.exp(best.x[:2]).tolist(),
                noise_std=np.exp(best.x[2:]).tolist(), train_log_likelihood=-float(best.fun),
                test_log_likelihood=float(ll.mean()), converged_starts=len(successful)), ll


def gaussian(train, test):
    mean = train.mean(axis=0)
    covariance = np.cov(train.T, bias=True) + np.eye(2) * 1e-8
    z = test - mean
    values = -.5 * np.einsum("ni,ij,nj->n", z, np.linalg.inv(covariance), z)
    values -= np.log(2 * np.pi) + .5 * np.linalg.slogdet(covariance)[1]
    return values


def main():
    visits = []
    out = BASE / "local/within-visit/amplitude-levels"
    out.mkdir(exist_ok=True)
    for path in sorted((BASE / "local/paired").glob("*/*-data-soft.npz")):
        summary = json.loads((path.parent / "summary.json").read_text())
        header = summary["header"]
        if "evaluation_frames" not in header:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == header["sha256"]
        train_frames, test_frames = header["discovery_frames"], header["evaluation_frames"]
        with np.load(path) as data:
            assert np.array_equal(data["bins0"], data["bins1"])
            arrays = [data[f"z{rx}"] for rx in range(2)]
        rows = []
        for symbol in (4, 6):
            train, test = [], []
            for z in arrays:
                a, b = z[train_frames, symbol - 2].real, z[test_frames, symbol - 2].real
                center, scale = a.mean(axis=0), np.maximum(a.std(axis=0), 1e-8)
                train.append((a - center) / scale)
                test.append((b - center) / scale)
            x, y = np.stack(train, axis=-1).reshape(-1, 2), np.stack(test, axis=-1).reshape(-1, 2)
            baseline = gaussian(x, y)
            models = []
            for k in (2, 4):
                fitted, likelihood = fit_levels(x, y, k)
                delta = (likelihood - baseline).reshape(len(test_frames), -1).mean(axis=1)
                models.append(dict(**fitted, delta_from_gaussian=float(delta.mean()),
                                   frame_deltas=delta.tolist()))
            rows.append(dict(symbol=symbol, train_pairs=len(x), test_pairs=len(y),
                             gaussian_test_log_likelihood=float(baseline.mean()), models=models))
            np.savez_compressed(out / f"{path.parent.name}-symbol{symbol}.npz", train=x, test=y)
        visits.append(dict(visit=path.parent.name, source_sha256=digest,
                           discovery_frames=train_frames, evaluation_frames=test_frames, rows=rows))
    result = dict(visits=visits,
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Each carrier/RX centered and scaled using discovery only. Pooling "
                  "assumes a common normalized distribution. Uniform equally spaced shared levels "
                  "with independent Gaussian RX noise versus a full bivariate Gaussian. Failure "
                  "does not exclude other alphabets, nonuniform symbols or channel distortion. "
                  "Dependent frames/carriers; scores descriptive, no bit labels or significance.")
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    for r in visits:
        print(r["visit"])
        for s in r["rows"]:
            print(s["symbol"], [(m["levels"], m["delta_from_gaussian"], m["amplitude"],
                                  m["noise_std"]) for m in s["models"]])


if __name__ == "__main__":
    main()
