"""Audit information discarded by phase-histogram hierarchies."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import fcluster
from scipy.stats import spearmanr

BASE = Path(__file__).resolve().parent
SOURCE = (BASE.parents[3] / "reports") / "2026_09_29_all_track_symbols/local"
REGIONS = [(0, 6), (6, 32), (32, 128), (128, 300)]


def histogram(z):
    return np.concatenate([np.histogram((np.angle(z[:, a:b]) + np.pi / 16) % (2 * np.pi),
                                       bins=16, range=(0, 2 * np.pi))[0]
                           / z[:, a:b].size / 4 for a, b in REGIONS])


def reordered(z):
    result = z.copy()
    rng = np.random.default_rng(291102)
    for a, b in REGIONS:
        tile = z[:, a:b]
        result[:, a:b] = rng.permutation(tile.ravel()).reshape(tile.shape)
    return result


def main():
    inventory = SOURCE / "clustering.json"
    tracks = {r["id"]: r for r in json.loads(inventory.read_text())["tracks"]}
    results = []
    for name in ("all_recovered_phase_shapes", "qualified_phase_shapes"):
        folder = SOURCE / "clusters" / name
        paths = [folder / n for n in ("features.npy", "linkage.npy", "labels.json")]
        labels = json.loads(paths[2].read_text())
        features = np.load(paths[0])
        probabilities = 2 * features ** 2
        np.testing.assert_allclose(probabilities.sum(axis=1), 1, atol=1e-12)
        regions = probabilities.reshape(-1, 4, 16) * 4
        concentration = abs(regions @ np.exp(2j * np.arange(16) * 2 * np.pi / 16)).mean(axis=1)
        pilot = np.array([tracks[label]["pilot"] for label in labels])
        tree = np.load(paths[1])
        cuts = []
        for count in (2, 4, 8):
            groups = fcluster(tree, count, criterion="maxclust")
            rows = []
            for group in np.unique(groups):
                ix = np.flatnonzero(groups == group)
                rows.append(dict(group=int(group), count=len(ix),
                                 quality=dict(Counter(tracks[labels[i]]["status"] for i in ix)),
                                 median_pilot=float(np.median(pilot[ix])),
                                 median_axial_concentration=float(np.median(concentration[ix]))))
            cuts.append(dict(requested_groups=count, actual_groups=len(rows), groups=rows))
        results.append(dict(name=name, count=len(labels), cuts=cuts,
                            pilot_concentration_spearman=float(
                                spearmanr(pilot, concentration).statistic),
                            source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                           for p in paths}))
    # One deterministic actual-data example; no new hypothesis/shift search.
    target = max((tracks[n] for n in labels), key=lambda t: (t["pilot"], t["id"]))
    artifact = Path(target["artifact"])
    receipt = json.loads((artifact.parent / "results.json").read_text())
    row = next(r for r in receipt["rows"] if r["track_id"] == target["track_id"])
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == row["artifact_sha256"]
    meta = row["receiver_metadata"]
    with np.load(artifact) as data:
        keep = ~np.isin(data["bins"], meta["pilot_bins"])
        z = data["z"][meta["evaluation_frames"]][:, :, keep]
    scrambled = reordered(z)
    observed = histogram(z)
    np.testing.assert_allclose(observed, probabilities[labels.index(target["id"])], atol=1e-12)
    np.testing.assert_array_equal(observed, histogram(scrambled))
    example = dict(id=target["id"], source_sha256=row["artifact_sha256"],
                   changed_complex_sample_fraction=float(np.mean(z != scrambled)),
                   maximum_histogram_difference=float(abs(observed - histogram(scrambled)).max()))
    result = dict(hierarchies=results, order_loss_example=example,
                  inventory_sha256=hashlib.sha256(inventory.read_bytes()).hexdigest(),
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Existing phase-distribution features, not ordered bits. "
                  "Concentration/quality correlation is descriptive without a population "
                  "p-value; no identity training. Pilot bins excluded, known T-code not "
                  "subtracted. Physical units and sample-rate supports differ across tracks.")
    (BASE / "local/phase-histogram-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Order loss", example)


if __name__ == "__main__":
    main()
