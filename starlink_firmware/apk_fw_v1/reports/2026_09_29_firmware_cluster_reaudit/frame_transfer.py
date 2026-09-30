"""Discovery-frame hierarchy transfer to a reserved frame with grouped controls."""

import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import cut_tree, linkage
from scipy.spatial.distance import cdist, pdist

BASE = Path(__file__).resolve().parent
SOURCE = (BASE.parents[3] / "reports") / "2026_09_29_identity_resumption/local/rows.json"


def normalize(z):
    phase = z / np.maximum(abs(z), 1e-12)
    x = np.concatenate([phase.real.reshape(len(z), -1), phase.imag.reshape(len(z), -1)], axis=1)
    x -= x.mean(axis=1, keepdims=True)
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)


def balanced_accuracy(truth, predicted):
    return float(np.mean([(predicted[truth == k] == k).mean() for k in np.unique(truth)]))


def family_controls(scores):
    """Column zero is observed; center the full reference set symmetrically."""
    scores = np.asarray(scores)
    centered = scores - scores.mean(axis=1, keepdims=True)
    active = np.ptp(scores, axis=1) > 1e-12
    maxima = centered[active].max(axis=0) if active.any() else np.zeros(scores.shape[1])
    p = [float(np.mean(maxima >= row[0] - 1e-12)) if ok else None
         for row, ok in zip(centered, active, strict=True)]
    return p, maxima.tolist()


def main():
    rows = json.loads(SOURCE.read_text())
    observations = []
    for r in rows:
        path = Path(r["source_artifact"])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == r["source_artifact_sha256"]
        with np.load(path) as d:
            meta = json.loads(str(d["metadata"]))
            bins = [486, 487, 496, 497] if r["edge"] == "upper" else [526, 527, 536, 537]
            index = np.searchsorted(d["bins"], bins)
            assert np.array_equal(d["bins"][index], bins)
            assert not set(bins) & set(meta["pilot_bins"])
            z = d["z"][meta["evaluation_frames"], :6][:, :, index]
            assert z.shape == (2, 6, 4)
            observations.append(normalize(z))
    observations = np.array(observations)
    experiments = []
    rng = np.random.default_rng(291029)
    shuffle_scores, shift_scores = [], []
    for edge in ("upper", "lower"):
        indices = [i for i, r in enumerate(rows) if r["edge"] == edge]
        entries = [rows[i] for i in indices]
        train, held = observations[indices, 0], observations[indices, 1]
        partitions = cut_tree(linkage(pdist(train), method="average"), n_clusters=[2, 4, 8])
        strata = defaultdict(list)
        for i, r in enumerate(entries):
            strata[r["session"], r["channel"], r["rate"], r["receiver"]].append(i)
        groups = [np.array(sorted(g, key=lambda i: entries[i]["selected_utc_ns"]))
                  for g in strata.values()]
        permutations, shifts = [], []
        for _ in range(499):
            perm, shifted = np.arange(len(entries)), np.arange(len(entries))
            for g in groups:
                perm[g] = rng.permutation(g)
                shifted[g] = np.roll(g, rng.integers(len(g)))
            permutations.append(perm)
            shifts.append(shifted)
        for column, k in enumerate((2, 4, 8)):
            labels = partitions[:, column]
            centers = np.array([train[labels == c].mean(axis=0) for c in range(k)])
            predicted = cdist(held, centers).argmin(axis=1)
            fitted = cdist(train, centers).argmin(axis=1)
            score = balanced_accuracy(labels, predicted)
            shuffled = [balanced_accuracy(labels, predicted[p]) for p in permutations]
            rotated = [balanced_accuracy(labels, predicted[p]) for p in shifts]
            shuffle_scores.append(np.array(shuffled) - 1 / k)
            shift_scores.append(np.array(rotated) - 1 / k)
            experiments.append(dict(edge=edge, groups=k, entries=len(entries),
                discovery_group_sizes=np.bincount(labels).tolist(),
                held_predicted_sizes=np.bincount(predicted, minlength=k).tolist(),
                discovery_centroid_balanced_accuracy=balanced_accuracy(labels, fitted),
                held_balanced_accuracy=score, majority_balanced_baseline=1 / k,
                held_recall_by_group=[float((predicted[labels == c] == c).mean())
                                      for c in range(k)],
                excess=score - 1 / k, shuffled_mean=float(np.mean(shuffled)),
                circular_mean=float(np.mean(rotated)),
                movable_entries=sum(len(g) for g in groups if len(g) > 1),
                cluster_members={str(c): [entries[i]["id"] for i in np.flatnonzero(labels == c)]
                                 for c in range(k)}))
    # A stratum-frozen small cluster can have a high but constant score. Center
    # each test's reference set, including the observed score, before maxima.
    observed = np.array([r["excess"] for r in experiments])[:, None]
    shuffle_p, maximum_shuffle = family_controls(np.c_[observed, shuffle_scores])
    shift_p, maximum_shift = family_controls(np.c_[observed, shift_scores])
    for i, r in enumerate(experiments):
        r["shuffle_family_p"] = shuffle_p[i]
        r["circular_family_p"] = shift_p[i]
        r["control_status"] = (
            "no exchangeable score variation" if shuffle_p[i] is None else "tested")
    result = dict(experiments=experiments,
        maximum_shuffle=maximum_shuffle, maximum_circular=maximum_shift,
        source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitation="Exploratory reused data; discovery labels derive from first reserved frame. "
        "Second frame assigns to frozen centroids, not reclustering. Controls preserve session, "
        "channel, rate and receiver; circular controls preserve within-stratum time order except "
        "wrap. Small/singleton groups and shared synchronization limit interpretation. "
        "Centered family maxima across six edge/cut tests; constant-score controls abstain. "
        "Reference centering includes the observation symmetrically; no satellite labels used.")
    (BASE / "local/frame-transfer.json").write_text(json.dumps(result, indent=2) + "\n")
    for r in experiments:
        print(r["edge"], r["groups"], r["discovery_group_sizes"],
              r["held_balanced_accuracy"], r["shuffle_family_p"], r["circular_family_p"])


if __name__ == "__main__":
    main()
