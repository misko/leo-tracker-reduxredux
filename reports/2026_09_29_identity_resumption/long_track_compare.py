"""Exploratory within-trajectory early-sign comparison, six stored excerpts."""

import hashlib
import itertools
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
OUT = BASE / "local/long-track"


def contrast(matrix, labels):
    i, j = np.triu_indices(len(labels), 1)
    same = np.asarray(labels)[i] == np.asarray(labels)[j]
    return float(matrix[i[same], j[same]].mean() - matrix[i[~same], j[~same]].mean())


def main():
    receipt = OUT / "recovery.json"
    rows = json.loads(receipt.read_text())["rows"]
    arrays = []
    # Fix common support before inspecting signs. First qualified frame trains;
    # remaining qualified frames are evaluations, including gaps as recorded.
    bins = np.r_[np.arange(516, 528), np.arange(536, 550)]
    for r in rows:
        path = Path(r["artifact"])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == r["artifact_sha256"]
        with np.load(path) as d:
            ids = np.searchsorted(d["bins"], bins)
            assert np.array_equal(d["bins"][ids], bins)
            assert len(r["qualified"]) >= 2
            arrays.append(np.where(d["z"][r["qualified"], :6][:, :, ids].real >= 0, 1., -1.))
    labels = [r["id"] for r in rows]
    results, matrices = [], []
    for name, subset in (("four_carriers", np.isin(bins, [526, 527, 536, 537])),
                         ("26_carriers", np.ones(len(bins), bool))):
        train = np.array([a[:, :, subset][0].ravel() for a in arrays])
        population = train.mean(axis=0)
        train -= population
        train /= np.maximum(np.linalg.norm(train, axis=1, keepdims=True), 1e-12)
        test = []
        for a in arrays:
            v = a[1:][:, :, subset].reshape(len(a) - 1, -1) - population
            v /= np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)
            test.append(v.mean(axis=0))
        directional = train @ np.array(test).T
        matrix = (directional + directional.T) / 2
        matrices.append(matrix)
        results.append(dict(feature=name, contrast=contrast(matrix, labels),
                            similarity=matrix.tolist()))
    # Exhaustive balanced label partitions; temporal exchangeability is NOT
    # established. These ranks are descriptive, not calibrated identity tests.
    controls = []
    for chosen in itertools.combinations(range(6), 3):
        shuffled = [int(i in chosen) for i in range(6)]
        controls.append(max(contrast(m, shuffled) for m in matrices))
    for r in results:
        r["max_feature_partition_rank"] = sum(v >= r["contrast"] - 1e-12
                                               for v in controls) / len(controls)
    times = np.array([r["time_ns"] for r in rows], dtype=np.int64)
    nearest = np.abs(times[:, None] - times[None, :]).astype(float)
    np.fill_diagonal(nearest, np.inf)
    time_accuracy = np.mean([labels[i] == labels[j] for i, j in enumerate(nearest.argmin(axis=1))])
    output = dict(rows=[{k: r[k] for k in ("id", "part", "time_ns", "qualified")} for r in rows],
                  results=results, partition_maxima=controls,
                  nearest_time_track_accuracy=float(time_accuracy),
                  source_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest(),
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Two trajectories, six excerpts, temporally confounded. No "
                  "independent satellite truth, no receiver consensus. One discovery frame "
                  "per excerpt fits label-blind population centering. Reused raw recordings; "
                  "physical track continuity does not prove constant transmitter or beam.")
    (OUT / "comparison.json").write_text(json.dumps(output, indent=2) + "\n")
    for r in results:
        print(r["feature"], r["contrast"], r["max_feature_partition_rank"])
    print("Nearest-time track accuracy", time_accuracy)


if __name__ == "__main__":
    main()
