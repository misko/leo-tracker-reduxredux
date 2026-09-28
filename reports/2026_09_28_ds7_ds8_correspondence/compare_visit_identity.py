"""Descriptive same/different-identity visit comparisons, without RF identity claims."""

import csv
import hashlib
import itertools
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent
OUT = BASE / "local/visit-identity"
NAMES = {57526: "STARLINK-30257", 59199: "STARLINK-31567", 59250: "STARLINK-31407"}


def overlap(a, b, sample=4):
    """Exact expected distinct overlap of independent without-replacement samples."""
    ca, cb = Counter(a), Counter(b)
    if min(len(a), len(b)) < sample:
        raise ValueError("Insufficient observations for equal-size sampling")

    def present(n, count):
        return 1 - (math.comb(n - count, sample) if n - count >= sample else 0) / math.comb(
            n, sample
        )

    shared = set(ca) & set(cb)
    return dict(
        shared=len(shared),
        union=len(set(ca) | set(cb)),
        jaccard=len(shared) / len(set(ca) | set(cb)),
        random_observation_match=sum(ca[w] * cb[w] for w in shared) / (len(a) * len(b)),
        expected_shared_at_four=sum(
            present(len(a), ca[w]) * present(len(b), cb[w]) for w in shared
        ),
    )


def main():
    OUT.mkdir(exist_ok=True)
    sources = [BASE / "local/joint-results.json", BASE / "local/decoded-bits.csv"]
    groups = json.loads(sources[0].read_text())["groups"]
    rows = list(csv.DictReader(sources[1].open()))
    selected = [g for g in groups if g["norad_id"] is not None and g["qualified_codes"] > 0]
    selected.sort(key=lambda g: (g["norad_id"], g["dataset"], g["visit"]))
    assert len({(g["session_id"], g["visit"]) for g in selected}) == len(selected)
    for g in selected:
        g["words"] = [r["raw_bits"] for r in rows if r["group"] == g["group"]]
        g["families"] = [r["family"] for r in rows if r["group"] == g["group"]]
        assert len(g["words"]) == g["qualified_codes"]
    pairs = []
    for a, b in itertools.combinations(selected, 2):
        same = a["norad_id"] == b["norad_id"]
        category = "different_identity"
        if same:
            category = (
                "same_identity_same_pass"
                if a["session_id"] == b["session_id"]
                else "same_identity_different_pass"
            )
        pairs.append(
            dict(
                a=a["group"],
                b=b["group"],
                category=category,
                same_edge=a["edge"] == b["edge"],
                words=overlap(a["words"], b["words"]),
                families=overlap(a["families"], b["families"]),
            )
        )
    summaries = []
    for category in [
        "same_identity_same_pass",
        "same_identity_different_pass",
        "different_identity",
    ]:
        subset = [p for p in pairs if p["category"] == category]
        summaries.append(
            dict(
                category=category,
                pairs=len(subset),
                **{
                    kind: {
                        metric: float(np.mean([p[kind][metric] for p in subset]))
                        for metric in [
                            "shared",
                            "jaccard",
                            "random_observation_match",
                            "expected_shared_at_four",
                        ]
                    }
                    for kind in ["words", "families"]
                },
            )
        )
    result = dict(
        summaries=summaries,
        pairs=pairs,
        visits=[
            {
                k: g[k]
                for k in [
                    "group",
                    "dataset",
                    "session_id",
                    "visit",
                    "edge",
                    "norad_id",
                    "qualified_codes",
                ]
            }
            for g in selected
        ],
        input_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        limitations="Conditional Doppler identities. "
        "Seven selected successful visits, three identities. "
        "Pairs share visits and are dependent. Same/different-pass classification uses previously "
        "established encounter assignments: the same-session pairs here are each in one pass. "
        "Different-pass same-identity pairs also change band edge. "
        "No significance or general classifier claim.",
    )
    (OUT / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(summaries, indent=2))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(13, 6), layout="constrained")
    labels = [
        f"{NAMES[g['norad_id']].replace('STARLINK-', '')}\n"
        f"{g['dataset']} v{g['visit']} {g['edge'][0].upper()}"
        for g in selected
    ]
    for ax, kind, title in zip(
        axes,
        ["words", "families"],
        ["Exact 60-bit words", "Rotation/inversion-normalized families"],
        strict=True,
    ):
        matrix = np.full((len(selected), len(selected)), np.nan)
        for i, a in enumerate(selected):
            for j, b in enumerate(selected):
                if i != j:
                    matrix[i, j] = overlap(a[kind], b[kind])["expected_shared_at_four"]
        im = ax.imshow(matrix, vmin=0, vmax=4, cmap="Blues")
        ax.set_xticks(range(len(labels)), labels, rotation=65, ha="right", fontsize=8)
        ax.set_yticks(range(len(labels)), labels, fontsize=8)
        ax.set_title(title)
        for i in range(len(selected)):
            for j in range(len(selected)):
                if i != j:
                    ax.text(j, i, f"{matrix[i, j]:.2f}", ha="center", va="center", fontsize=8)
        for boundary in [1.5, 5.5]:
            ax.axhline(boundary, color="orange", lw=1.5)
            ax.axvline(boundary, color="orange", lw=1.5)
    fig.colorbar(
        im,
        ax=axes,
        label="Expected shared distinct patterns after sampling 4 observations per visit",
        shrink=0.7,
    )
    fig.suptitle(
        "DS7 + DS8: visit overlap by likely satellite\n"
        "Orange lines separate inferred identities; identities are not decoded from bits",
        fontsize=12,
    )
    fig.savefig(OUT / "overlap.png", dpi=180)


if __name__ == "__main__":
    main()
