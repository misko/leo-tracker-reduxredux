"""Test whether saved word-distribution splits survive harmless leaf reorderings."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import cut_tree, linkage
from scipy.spatial.distance import pdist

BASE = Path(__file__).resolve().parent
SOURCE = (BASE.parents[3] / "reports") / "2026_09_29_all_track_symbols/local/clusters"


def adjusted_rand(a, b):
    _, a = np.unique(a, return_inverse=True)
    _, b = np.unique(b, return_inverse=True)
    table = np.zeros((a.max() + 1, b.max() + 1), dtype=int)
    np.add.at(table, (a, b), 1)
    def choose(x):
        return np.sum(x * (x - 1) / 2)

    n = len(a) * (len(a) - 1) / 2
    left, right, both = choose(table.sum(axis=0)), choose(table.sum(axis=1)), choose(table)
    expected = left * right / n
    denominator = (left + right) / 2 - expected
    return 1. if denominator == 0 else float((both - expected) / denominator)


def main():
    rng = np.random.default_rng(290926)
    outputs = []
    for name in ("qualified_observed_word_distributions", "qualified_mean_word_bits"):
        folder = SOURCE / name
        names = ("features.npy", "linkage.npy", "labels.json", "word_basis.json")
        paths = [folder / f for f in names]
        features = np.load(paths[0])
        original = np.load(paths[1])
        reference = linkage(pdist(features), method="average")
        np.testing.assert_allclose(reference, original, atol=1e-12, rtol=1e-12)
        baseline = cut_tree(original, n_clusters=[2, 4, 8])
        scores = []
        for _ in range(99):
            order = rng.permutation(len(features))
            tree = linkage(pdist(features[order]), method="average")
            groups = cut_tree(tree, n_clusters=[2, 4, 8])
            aligned = np.empty_like(groups)
            aligned[order] = groups
            scores.append([adjusted_rand(baseline[:, j], aligned[:, j]) for j in range(3)])
        distances = pdist(features)
        outputs.append(dict(name=name, observations=len(features), cuts=[2, 4, 8],
            maximum_distance_fraction=float(np.mean(np.isclose(distances, distances.max()))),
            reorder_ARI=scores, median_ARI=np.median(scores, axis=0).tolist(),
            minimum_ARI=np.min(scores, axis=0).tolist(),
            source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}))
    result = dict(results=outputs,
        method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitation="Numerical invariance audit, not a significance test or identity test. "
        "No observations changed and no label outcomes optimized. Exact-count cuts can split "
        "tied heights. Ninety-nine permutations probe input-order sensitivity only.")
    out = BASE / "local"
    (out / "tie-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.5), layout="constrained")
    for ax, row in zip(axes, outputs, strict=True):
        ax.boxplot(np.array(row["reorder_ARI"]), tick_labels=["2", "4", "8"])
        ax.set(title=row["name"].replace("qualified_", "").replace("_", " "),
               xlabel="Number of dendrogram groups", ylabel="Agreement after leaf reordering",
               ylim=(-.1, 1.05))
        print(row["name"], "maximum-distance fraction", row["maximum_distance_fraction"],
              "median ARI", row["median_ARI"], "minimum", row["minimum_ARI"])
    fig.savefig(out / "tie-stability.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()
