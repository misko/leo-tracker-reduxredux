"""Recompute saved adjacent-tile geometry and audit permissible node controls."""

import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from scipy.stats import spearmanr
from tie_audit import adjusted_rand

BASE = Path(__file__).resolve().parent
SOURCE = (BASE.parents[3] / "reports") / "2026_09_29_all_track_symbols/local"


def geometry(similarity):
    gram = squareform(similarity)
    np.fill_diagonal(gram, 1)
    eigenvalues = np.linalg.eigvalsh(gram)
    return dict(minimum_gram_eigenvalue=float(eigenvalues[0]),
                negative_eigenvalues=int(np.count_nonzero(eigenvalues < -1e-10)))


def main():
    path = SOURCE / "tile-alignment/summary.json"
    receipt = json.loads(path.read_text())
    rows = []
    for edge, group in receipt["edges"].items():
        counts = Counter((t["session"], t["channel"], t["receiver"], t["rate"])
                         for t in group["tracks"])
        for tile in group["tiles"]:
            artifact = path.parent / f"{edge}-{tile['width']}.npz"
            with np.load(artifact) as data:
                values = data["values"]
                trees = [linkage(np.sqrt(np.maximum(0, 2 - 2 * values[:, c])), method="average")
                         for c in (1, 3)]
                np.testing.assert_allclose(trees[0], data["linkage"], atol=1e-12, rtol=0)
                np.testing.assert_allclose(trees[1], data["adjacent_linkage"], atol=1e-12, rtol=0)
            ari = adjusted_rand(*(fcluster(t, 4, criterion="maxclust") for t in trees))
            rho = float(spearmanr(values[:, 1], values[:, 3]).statistic)
            assert abs(ari - tile["adjacent_four_cluster_ARI"]) < 1e-12
            assert abs(rho - tile["adjacent_matrix_spearman"]) < 1e-12
            rows.append(dict(edge=edge, width=tile["width"], original_metrics=tile,
                             tracks=group["tracks"], recomputed_ARI=ari,
                             recomputed_spearman=rho,
                             held_geometry=geometry(values[:, 1]),
                             adjacent_geometry=geometry(values[:, 3]),
                             movable_tracks=sum(n for n in counts.values() if n > 1),
                             permissible_node_permutations=math.prod(math.factorial(n)
                                                                    for n in counts.values()),
                             control_status="Abstain: only two distinct permitted permutations",
                             artifact_path=str(artifact),
                             artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest()))
    paired_path = SOURCE / "paired-tiles/summary.json"
    paired = json.loads(paired_path.read_text())
    result = dict(adjacent_tiles=rows, paired_tile_evidence=paired,
                  source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (path, paired_path)},
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  interpretation="Distance geometry reproduced; adjacent group memberships "
                  "do not recur. Paired receiver agreement is distinct from cross-visit "
                  "partition stability. Known-state comparisons are not satellite-ID tests.",
                  limitation="Saved DS7–DS9 selected 10 MS/s tiles, no new IQ/shift search. "
                  "Receipt reproduction, not independent replication. Permissible node "
                  "controls preserve session/channel/rate/receiver but have insufficient support.")
    (BASE / "local/tile-receipt-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    for r in rows:
        print(r["edge"], r["width"], "ARI", r["recomputed_ARI"], "geometries",
              r["held_geometry"], r["adjacent_geometry"],
              "permutations", r["permissible_node_permutations"])


if __name__ == "__main__":
    main()
