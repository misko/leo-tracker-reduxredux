"""Align original observations and test early-tree partitions after corpus extension."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import cut_tree, linkage
from scipy.spatial.distance import pdist
from tie_audit import adjusted_rand

BASE = Path(__file__).resolve().parent
OLD = (BASE.parents[3] / "reports") / "2026_09_29_all_track_symbols/local/clusters"
JOINT = (BASE.parents[3] / "reports") / "2026_09_29_ds10_signal_extension/local"


def align(old, new):
    if len(set(old)) != len(old) or len(set(new)) != len(new):
        raise ValueError("Observation IDs must be unique")
    index = {name: i for i, name in enumerate(new)}
    return np.array([index[name] for name in old], dtype=int)


def main():
    meta = JOINT / "qualified-tracks.json"
    feat = JOINT / "qualified-features.npz"
    rows = json.loads(meta.read_text())
    with np.load(feat) as d:
        all_features = d["region0"].copy()
    results = []
    for edge in ("upper", "lower"):
        folder = OLD / f"{edge}_early_profiles"
        paths = [folder / n for n in ("labels.json", "features.npy", "linkage.npy")]
        ids = json.loads(paths[0].read_text())
        old_features, old_tree = np.load(paths[1]), np.load(paths[2])
        selected = [i for i, r in enumerate(rows) if r["edge"] == edge]
        current = [rows[i] for i in selected]
        features = all_features[selected]
        mapped = align(ids, [r["id"] for r in current])
        max_difference = float(np.max(abs(old_features - features[mapped])))
        np.testing.assert_allclose(old_features, features[mapped], atol=1e-7, rtol=1e-6)
        old_dist, repeated_dist = pdist(old_features), pdist(features[mapped])
        path = JOINT / f"{edge}-early-linkage.npy"
        tree = np.load(path)
        np.testing.assert_allclose(linkage(pdist(features), method="average"), tree,
                                   atol=1e-12, rtol=1e-12)
        original = cut_tree(old_tree, n_clusters=[2, 4, 8])
        extended = cut_tree(tree, n_clusters=[2, 4, 8])[mapped]
        controls, added_counts = [], []
        extra = sorted(set(range(len(features))) - set(mapped))
        sessions = sorted({current[i]["session"] for i in extra})
        rng = np.random.default_rng(291028)
        # Add half the new sessions as intact blocks. This preserves dependencies
        # among added receiver/visit observations; row counts can vary.
        for _ in range(99):
            chosen = set(rng.choice(sessions, size=max(1, len(sessions) // 2), replace=False))
            added = [i for i in extra if current[i]["session"] in chosen]
            added_counts.append(len(added))
            indices = np.r_[mapped, added]
            small = linkage(pdist(features[indices]), method="average")
            groups = cut_tree(small, n_clusters=[2, 4, 8])[:len(mapped)]
            controls.append([adjusted_rand(original[:, k], groups[:, k]) for k in range(3)])
        contingencies = []
        for k, size in enumerate([2, 4, 8]):
            table = np.zeros((size, size), int)
            np.add.at(table, (original[:, k], extended[:, k]), 1)
            contingencies.append(table.tolist())
        results.append(dict(edge=edge, original_entries=len(ids), extended_entries=len(current),
            added_by_dataset={ds: sum(current[i]["dataset"] == ds for i in extra)
                              for ds in sorted({current[i]["dataset"] for i in extra})},
            maximum_feature_difference=max_difference,
            maximum_old_distance_difference=float(np.max(abs(old_dist - repeated_dist))),
            cuts=[2, 4, 8], full_extension_ARI=[adjusted_rand(original[:, k], extended[:, k])
                                             for k in range(3)],
            half_extension_ARI=controls, half_extension_median=np.median(controls, axis=0).tolist(),
            new_sessions=len(sessions), half_session_added_counts=added_counts,
            contingency=contingencies,
            source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in paths + [meta, feat, path]}))
    result = dict(results=results,
        method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitation="Fixed-count unsupervised cuts may change when observations are added. "
        "Sensitivity is not a statistical rejection of firmware fields or satellite identity; "
        "no held-out frame classifier is fitted. Sampling controls retain entire added "
        "session blocks and are descriptive composition checks, not identity p-values.")
    (BASE / "local/corpus-extension.json").write_text(json.dumps(result, indent=2) + "\n")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(8, 3.5), layout="constrained")
    for ax, row in zip(axes, results, strict=True):
        table = np.array(row["contingency"][1])
        ax.imshow(table, cmap="Blues")
        for (i, j), value in np.ndenumerate(table):
            ax.text(j, i, str(value), ha="center", va="center",
                    color="white" if value > table.max() / 2 else "black")
        ax.set(title=row["edge"].title() + ": shared observations, four groups",
               xlabel="Group after extension", ylabel="Original group",
               xticks=range(4), yticks=range(4))
        print(row["edge"], row["added_by_dataset"], row["full_extension_ARI"],
              "feature difference", row["maximum_feature_difference"])
    fig.savefig(BASE / "local/corpus-extension.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()
