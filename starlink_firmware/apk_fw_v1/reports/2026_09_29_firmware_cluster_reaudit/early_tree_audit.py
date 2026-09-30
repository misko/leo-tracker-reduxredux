"""Input-order robustness of early-symbol trees, including the DS10 extension."""

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


def evaluate(features, tree, repeats=99):
    np.testing.assert_allclose(linkage(pdist(features), method="average"), tree,
                               atol=1e-12, rtol=1e-12)
    original = cut_tree(tree, n_clusters=[2, 4, 8])
    rng = np.random.default_rng(291027)
    scores = []
    for _ in range(repeats):
        order = rng.permutation(len(features))
        groups = cut_tree(linkage(pdist(features[order]), method="average"),
                          n_clusters=[2, 4, 8])
        restored = np.empty_like(groups)
        restored[order] = groups
        scores.append([adjusted_rand(original[:, k], restored[:, k]) for k in range(3)])
    return dict(observations=len(features), cuts=[2, 4, 8], reorder_ARI=scores,
                minimum_ARI=np.min(scores, axis=0).tolist(),
                median_ARI=np.median(scores, axis=0).tolist())


def main():
    results = []
    for edge in ("upper", "lower"):
        folder = OLD / f"{edge}_early_profiles"
        paths = [folder / n for n in ("features.npy", "linkage.npy", "labels.json")]
        results.append(dict(name=f"DS789_{edge}",
            **evaluate(np.load(paths[0]), np.load(paths[1])),
            source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}))
    paths = [JOINT / "qualified-tracks.json", JOINT / "qualified-features.npz"]
    rows = json.loads(paths[0].read_text())
    with np.load(paths[1]) as data:
        features = data["region0"].copy()
    for edge in ("upper", "lower"):
        tree_path = JOINT / f"{edge}-early-linkage.npy"
        indices = [i for i, r in enumerate(rows) if r["edge"] == edge]
        results.append(dict(name=f"DS78910_{edge}",
            **evaluate(features[indices], np.load(tree_path)),
            source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in paths + [tree_path]}))
    output = dict(results=results,
        method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitation="Saved-tree numerical robustness only. No new frames, identity labels, "
        "or field mapping inferred. Original duplicate/receiver dependence is retained.")
    (BASE / "local/early-tree-audit.json").write_text(json.dumps(output, indent=2) + "\n")
    for r in results:
        print(r["name"], r["observations"], "minimum ARI", r["minimum_ARI"])


if __name__ == "__main__":
    main()
