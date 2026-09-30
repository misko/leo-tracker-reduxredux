"""Frozen local symbol pairs: exact visit-preserving cyclic family controls."""

import hashlib
import itertools
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
SOURCE = (BASE.parents[3] / "reports") / "2026_09_29_ds10_signal_extension"


def partitions(edges):
    """Keep shared coordinates together; reject incompatible odd-cycle graphs."""
    graph, colors = {}, {}
    for a, b in edges:
        graph.setdefault(a, []).append(b)
        graph.setdefault(b, []).append(a)
    for root in sorted(graph):
        if root in colors:
            continue
        colors[root] = 0
        pending = [root]
        while pending:
            a = pending.pop()
            for b in graph[a]:
                if b in colors:
                    if colors[a] == colors[b]:
                        raise ValueError("Frozen pair graph is not bipartite")
                else:
                    colors[b] = 1 - colors[a]
                    pending.append(b)
    return colors


def orbit(bits, edges, parity):
    colors = partitions(edges)
    shifted_columns = [c for c, color in colors.items() if color]
    scores = []
    for shift in range(len(bits)):
        shifted = bits.copy()
        shifted[:, shifted_columns] = np.roll(bits[:, shifted_columns], shift, axis=0)
        scores.append([(shifted[:, a] ^ shifted[:, b] == p).mean()
                       for (a, b), p in zip(edges, parity, strict=True)])
    return np.asarray(scores).T, colors


def main():
    source = SOURCE / "local/within-visit/early-redundancy.json"
    receipt = json.loads(source.read_text())
    donors = [v for v in receipt["visits"] if v["learned_pairs"]]
    assert len(donors) == 1
    rules = donors[0]["learned_pairs"]
    visits, matrices = [], []
    for visit in receipt["visits"]:
        paths = list((SOURCE / "local/paired" / visit["visit"]).glob("*-data-soft.npz"))
        assert len(paths) == 1
        raw = paths[0].read_bytes()
        assert hashlib.sha256(raw).hexdigest() == visit["source_sha256"]
        with np.load(paths[0]) as data:
            coords = [(s + 2, int(k)) for s in range(6) for k in data["bins1"]]
            lookup = {c: i for i, c in enumerate(coords)}
            test = visit["test_frames"]
            bits = data["z1"][test, :6].real.reshape(len(test), -1) >= 0
        edges = [tuple(lookup[tuple(c)] for c in r["coordinates"]) for r in rules]
        scores, colors = orbit(bits, edges, [r["parity"] for r in rules])
        matrices.append(scores)
        visits.append(dict(visit=visit["visit"], frames=test,
                           source_sha256=visit["source_sha256"],
                           shifted_coordinates=[coords[c] for c in colors if colors[c]],
                           agreement=scores[:, 0].tolist(),
                           cyclic_mean=scores.mean(axis=1).tolist(),
                           exact_individual_p=(scores >= scores[:, :1] - 1e-12).mean(
                               axis=1).tolist()))
    centered = [m - m.mean(axis=1, keepdims=True) for m in matrices]
    indices = list(itertools.product(*(range(m.shape[1]) for m in matrices)))
    null = np.asarray([np.concatenate([m[:, k] for m, k in zip(centered, ks, strict=True)])
                       for ks in indices])
    observed = null[0]
    maxima = null.max(axis=1)
    family = (maxima[:, None] >= observed[None, :] - 1e-12).mean(axis=0)
    for i, visit in enumerate(visits):
        visit["cyclic_max_family_p"] = family[i * len(rules):(i + 1) * len(rules)].tolist()
    result = dict(donor=donors[0]["visit"], rules=rules, visits=visits,
                  family_tests=len(observed), exact_joint_rotations=len(indices),
                  pooled_mean_excess=float(observed.mean()),
                  pooled_exact_p=float((null.mean(axis=1) >= observed.mean() - 1e-12).mean()),
                  pooled_max_family_p=float((maxima >= observed.mean() - 1e-12).mean()),
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Frozen RX0 discovery pairs, RX1 held chronological frames only. "
                  "No new pair search. All seven pairs in all three visits form the family. "
                  "Bipartite column rotation preserves shared coordinates and within-part "
                  "dependence; visits rotate independently. Exact finite cyclic reference, "
                  "not a claim that irregular qualified frames are stationary or independent. "
                  "Previously studied held frames are not pristine confirmation. No satellite "
                  "identity, RF bit-order, FEC or field mapping follows from a pair relation.")
    (BASE / "local/pair-family.json").write_text(json.dumps(result, indent=2) + "\n")
    for v in visits:
        print(v["visit"], "agreement", v["agreement"], "family", v["cyclic_max_family_p"])
    print("Joint rotations", len(indices), "pooled excess", result["pooled_mean_excess"],
          "pooled p", result["pooled_exact_p"])


if __name__ == "__main__":
    main()
