"""Train receiver weights on known tail signs; evaluate disjoint frames and symbols."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent / "2026_09_29_all_track_symbols"))
from decode_tracks import SEED, codebook, slots  # noqa: E402


def fit_combiner(values, signs):
    """Per-carrier intercept/gain and regularized 2x2 receiver-noise covariance."""
    carriers = values.shape[-2]
    offset, weights = [], []
    for c in range(carriers):
        y, t = values[:, :, c].reshape(-1, 2), signs[:, :, c].ravel()
        design = np.column_stack([np.ones(len(t)), t])
        bias, gain = np.linalg.lstsq(design, y, rcond=None)[0]
        residual = y - bias - t[:, None] * gain
        covariance = residual.T @ residual / len(t)
        covariance += np.eye(2) * max(.05 * np.trace(covariance), 1e-8)
        w = np.linalg.solve(covariance, gain)
        w /= max(float(w @ gain), 1e-8)
        offset.append(bias)
        weights.append(w)
    return np.array(offset), np.array(weights)


def apply(values, offset, weights):
    return ((values - offset) * weights).sum(axis=-1)


def measure(values, truth, threshold=0):
    mask = abs(values) >= threshold
    errors = int(((values >= 0) != (truth >= 0))[mask].sum())
    return dict(count=int(mask.sum()), errors=errors,
                disagreement=errors / int(mask.sum()) if mask.any() else None)


def main():
    words = np.array([[1 if x == "1" else -1 for x in w]
                      for w in codebook(list(map(int, SEED)))])
    rows = []
    out = BASE / "local/within-visit/receiver-combining"
    out.mkdir(exist_ok=True)
    for path in sorted((BASE / "local/paired").glob("*/*-data-soft.npz")):
        source = json.loads((path.parent / "summary.json").read_text())
        header = source["header"]
        if "evaluation_frames" not in header:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == header["sha256"]
        states = {w["frame"]: w["phase_hypothesis"] for w in source["windows"]
                  if w["label"] == 1}
        train = [f for f in header["discovery_frames"] if f in states]
        test = [f for f in header["evaluation_frames"] if f in states]
        if min(len(train), len(test)) < 3:
            continue
        with np.load(path) as data:
            bins = data["bins0"]
            assert np.array_equal(bins, data["bins1"])
            z = np.stack([data["z0"].real, data["z1"].real], axis=-1)
        def expected(frames, start, stop, states=states, bins=bins):
            return words[[states[f] for f in frames]][:, slots(bins, np.arange(start, stop))]
        a, b = z[train, 224:256], z[test, 256:288]
        ta, tb = expected(train, 226, 258), expected(test, 258, 290)
        offset, weights = fit_combiner(a, ta)
        fit, held = apply(a, offset, weights), apply(b, offset, weights)
        gates, equal_gates = [], []
        for q in (0., .5, .75, .9):
            threshold = float(np.quantile(abs(fit), q)) if q else 0.
            gates.append(dict(quantile=q, threshold=threshold, **measure(held, tb, threshold)))
            threshold = float(np.quantile(abs(a.mean(axis=-1)), q)) if q else 0.
            equal_gates.append(dict(quantile=q, threshold=threshold,
                                    **measure(b.mean(axis=-1), tb, threshold)))
        # These are unvalidated early scores, not probabilities or corrected bits.
        early_frames = header["evaluation_frames"]
        np.savez_compressed(out / f"{path.parent.name}.npz", bins=bins,
                            frames=early_frames, soft=apply(z[early_frames, :6], offset, weights),
                            equal_soft=z[early_frames, :6].mean(axis=-1),
                            offset=offset, weights=weights)
        rows.append(dict(visit=path.parent.name, source_sha256=digest,
                         train_frames=train, test_frames=test,
                         rx0=measure(b[..., 0], tb), rx1=measure(b[..., 1], tb),
                         equal_average=measure(b.mean(axis=-1), tb),
                         weighted=measure(held, tb), gates=gates, equal_gates=equal_gates))
    result = dict(visits=rows,
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="States inferred from 194–225; weights trained on earlier frames "
                  "226–257, evaluated on later frames 258–289. Disagreement with inferred known "
                  "sequence, not independently verified BER. Early scores have no reliability "
                  "guarantee. No field interpretation or correction using a parity assumption.")
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
