"""Frozen-group phase invariance and pilot-quality coverage sensitivity."""

import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from frame_transfer import balanced_accuracy, family_controls, normalize
from scipy.spatial.distance import cdist

BASE = Path(__file__).resolve().parent
SOURCE = (BASE.parents[3] / "reports") / "2026_09_29_identity_resumption/local/rows.json"


def invariants(z):
    u = z / np.maximum(abs(z), 1e-12)
    return {"within_symbol": u[:, :, [0, 2]] * u[:, :, [1, 3]].conj(),
            "between_symbols": u[:, 1:] * u[:, :-1].conj()}


def main():
    source = BASE / "local/frame-transfer.json"
    original = json.loads(source.read_text())
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == original["source_sha256"]
    selected = next(r for r in original["experiments"] if r["edge"] == "upper" and r["groups"] == 8)
    membership = {name: int(c) for c, names in selected["cluster_members"].items()
                  for name in names}
    rows = [r for r in json.loads(SOURCE.read_text()) if r["edge"] == "upper"]
    labels = np.array([membership[r["id"]] for r in rows])
    arrays = defaultdict(list)
    for r in rows:
        p = Path(r["source_artifact"])
        assert hashlib.sha256(p.read_bytes()).hexdigest() == r["source_artifact_sha256"]
        with np.load(p) as d:
            m = json.loads(str(d["metadata"]))
            ix = np.searchsorted(d["bins"], [486, 487, 496, 497])
            np.testing.assert_array_equal(d["bins"][ix], [486, 487, 496, 497])
            z = d["z"][m["evaluation_frames"], :6][:, :, ix]
            for name, values in dict(absolute=z, **invariants(z)).items():
                arrays[name].append(normalize(values))
    strata = defaultdict(list)
    for i, r in enumerate(rows):
        strata[r["session"], r["channel"], r["rate"], r["receiver"]].append(i)
    groups = [np.array(sorted(g, key=lambda i: rows[i]["selected_utc_ns"]))
              for g in strata.values()]
    rng = np.random.default_rng(291031)
    permutations, rotations = [], []
    for _ in range(499):
        p, q = np.arange(len(rows)), np.arange(len(rows))
        for g in groups:
            p[g] = rng.permutation(g)
            q[g] = np.roll(g, rng.integers(len(g)))
        permutations.append(p)
        rotations.append(q)
    results, shuffles, shifts = [], [], []
    for name, values in arrays.items():
        values = np.array(values)
        centers = np.array([values[labels == c, 0].mean(axis=0) for c in range(8)])
        train = cdist(values[:, 0], centers).argmin(axis=1)
        held = cdist(values[:, 1], centers).argmin(axis=1)
        score = balanced_accuracy(labels, held)
        perm = [balanced_accuracy(labels, held[p]) for p in permutations]
        shift = [balanced_accuracy(labels, held[p]) for p in rotations]
        shuffles.append([score] + perm)
        shifts.append([score] + shift)
        results.append(dict(feature=name, discovery_accuracy=balanced_accuracy(labels, train),
            held_accuracy=score, shuffle_mean=float(np.mean(perm)),
            circular_mean=float(np.mean(shift))))
    ps, _ = family_controls(shuffles)
    pc, _ = family_controls(shifts)
    for i, r in enumerate(results):
        r.update(shuffle_family_p=ps[i], circular_family_p=pc[i])
    quality = []
    for threshold in (.52, .55, .60):
        counts = np.bincount(labels[[r["pilot"] > threshold for r in rows]], minlength=8)
        quality.append(dict(threshold=threshold, group_counts=counts.tolist(),
                            missing_groups=np.flatnonzero(counts == 0).tolist(),
                            status="abstain: lost original classes" if np.any(counts == 0)
                            else "coverage available"))
    result = dict(features=results, quality=quality,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitation="Post-selection sensitivity, not independent confirmation. "
        "Frozen absolute-phase "
        "labels reused; invariant centroids fit discovery only. Invariants may erase genuine "
        "modulation as well as nuisance. Max correction covers three feature variants here, "
        "not the entire history of exploratory tests. No identity labels or RF mapping.")
    (BASE / "local/phase-sensitivity.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
