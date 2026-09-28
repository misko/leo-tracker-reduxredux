"""Local-only metric/linkage and equal-count sensitivity on saved decoded words."""

import base64
import csv
import hashlib
import html
import json
from collections import Counter

import numpy as np
from cluster_signals import OUT, clustered_plot, csv_write, distance_hierarchy, matrix_csv
from scipy.cluster.hierarchy import cophenet, cut_tree
from scipy.spatial.distance import pdist, squareform
from scipy.stats import spearmanr


def profile_matrix(sequences, metric="js"):
    """Missing profiles are errors, not identical empty distributions."""
    if len(sequences) < 2 or any(not len(s) for s in sequences):
        raise ValueError("At least two nonempty profiles are required")
    keys = sorted({v for s in sequences for v in s})
    counts = np.array([[Counter(s)[k] for k in keys] for s in sequences], dtype=float)
    probabilities = counts / counts.sum(axis=1, keepdims=True)
    if metric == "js":
        distances = pdist(probabilities, metric="jensenshannon") / np.sqrt(np.log(2))
    elif metric == "hellinger":
        distances = pdist(np.sqrt(probabilities), metric="euclidean") / np.sqrt(2)
    elif metric == "jaccard":
        distances = pdist(counts > 0, metric="jaccard")
    else:
        raise ValueError(f"Unknown metric: {metric}")
    # All three metrics are bounded by one; remove floating-point endpoint overshoot.
    return squareform(np.clip(distances, 0, 1))


def balanced_resampling(sequences, size=10, repetitions=300, seed=20260928, cuts=(2, 3, 4)):
    """Subsample observations without replacement; ranges are not confidence intervals."""
    if size < 1 or repetitions < 1 or any(len(s) < size for s in sequences):
        raise ValueError("Each sequence must have at least the requested sample size")
    if len(sequences) < 2 or any(k < 2 or k > len(sequences) for k in cuts):
        raise ValueError("Tree cuts must be between two and the number of visits")
    rng = np.random.default_rng(seed)
    distances = []
    agreements = {k: np.zeros((len(sequences), len(sequences))) for k in cuts}
    for _ in range(repetitions):
        sampled = [rng.choice(s, size=size, replace=False).tolist() for s in sequences]
        matrix = profile_matrix(sampled)
        tree = distance_hierarchy(matrix, list(range(len(sequences))))
        distances.append(matrix)
        for k in cuts:
            labels = cut_tree(tree, n_clusters=k).ravel()
            agreements[k] += labels[:, None] == labels[None, :]
    return np.array(distances), {k: value / repetitions for k, value in agreements.items()}


def main():
    import matplotlib

    matplotlib.use("Agg")
    input_paths = [OUT / "signals.csv", OUT / "observations.csv"]
    with input_paths[0].open() as stream:
        signals = {r["signal"]: r for r in csv.DictReader(stream)}
    with input_paths[1].open() as stream:
        observations = [r for r in csv.DictReader(stream) if r["accepted"] == "True"]
    local = [r for r in observations if r["signal"].startswith("S")]
    names = sorted(s for s in signals if s.startswith("S") and int(signals[s]["accepted"]) >= 10)
    families = [[r["family"] for r in local if r["signal"] == s] for s in names]
    exact = [[r["word"] for r in local if r["signal"] == s] for s in names]
    labels = [
        f"{s} n={len(f)} | {float(signals[s]['rate_hz']) / 1e6:g}M "
        f"{signals[s]['edge']} | {signals[s]['norad_id'] or '?'}"
        for s, f in zip(names, families, strict=True)
    ]
    methods = [
        ("family_js_average", families, "js", "average"),
        ("family_js_complete", families, "js", "complete"),
        ("family_hellinger_average", families, "hellinger", "average"),
        ("family_jaccard_average", families, "jaccard", "average"),
        ("exact_js_average", exact, "js", "average"),
    ]
    matrices, diagnostics = {}, []
    for name, sequence, metric, method in methods:
        matrix = profile_matrix(sequence, metric)
        matrices[name] = matrix
        tree = np.array(clustered_plot(matrix, labels, OUT / f"{name}.png", name, method=method))
        matrix_csv(OUT / f"{name}.csv", names, matrix)
        pairs = sorted(
            (matrix[i, j], names[i], names[j])
            for i in range(len(names))
            for j in range(i + 1, len(names))
        )
        diagnostics.append(
            dict(
                method=name,
                cophenetic_correlation=float(cophenet(tree, squareform(matrix))[0]),
                closest_pairs=[dict(a=a, b=b, distance=float(d)) for d, a, b in pairs[:5]],
                top_three_clusters=cut_tree(tree, n_clusters=3).ravel().tolist(),
            )
        )

    draws, consensus = balanced_resampling(families)
    mean, low, high = draws.mean(axis=0), *np.quantile(draws, [0.025, 0.975], axis=0)
    matrix_csv(OUT / "balanced_mean_js.csv", names, mean)
    clustered_plot(
        mean,
        labels,
        OUT / "balanced_mean_js.png",
        "Equal-count sensitivity: mean JS distance over 300 subsets of 10 words per visit",
    )
    for k, coassignment in consensus.items():
        matrix_csv(OUT / f"coassignment_k{k}.csv", names, coassignment)
    clustered_plot(
        1 - consensus[3],
        labels,
        OUT / "coassignment_k3.png",
        "Subsampling sensitivity at a chosen 3-group cut\n"
        "Distance = fraction of draws assigned to different groups; not confidence",
    )
    pairs = []
    for i, a in enumerate(names):
        for j in range(i + 1, len(names)):
            b = names[j]
            pairs.append(
                dict(
                    a=a,
                    b=b,
                    full_js=matrices["family_js_average"][i, j],
                    balanced_mean=mean[i, j],
                    subset_p025=low[i, j],
                    subset_p975=high[i, j],
                    **{f"coassignment_k{k}": v[i, j] for k, v in consensus.items()},
                )
            )
    csv_write(OUT / "clustering_sensitivity_pairs.csv", pairs)

    strict_names = [
        s
        for s in names
        if sum(r["strict_pilot_accepted"] == "True" for r in local if r["signal"] == s) >= 10
    ]
    strict_sequences = [
        [r["family"] for r in local if r["signal"] == s and r["strict_pilot_accepted"] == "True"]
        for s in strict_names
    ]
    # Compare quality filters on exactly the same visits.
    full_matched = profile_matrix([families[names.index(s)] for s in strict_names])
    strict_matrix = profile_matrix(strict_sequences)
    matrix_csv(OUT / "matched_quality_full.csv", strict_names, full_matched)
    matrix_csv(OUT / "matched_quality_strict.csv", strict_names, strict_matrix)
    matched_correlation = float(
        spearmanr(squareform(full_matched), squareform(strict_matrix)).statistic
    )
    summary = dict(
        cohort=names,
        minimum_observations=10,
        excluded_local=[s for s in signals if s.startswith("S") and s not in names],
        reference_policy="UT pool excluded from local-visit clustering; kept in original lookup",
        repetitions=300,
        subset_size=10,
        seed=20260928,
        uncertainty="Empirical without-replacement subset sensitivity, not confidence intervals; "
        "does not model temporal dependence, rejected frames, or new passes",
        methods=diagnostics,
        strict_matched_cohort=strict_names,
        strict_full_distance_spearman=matched_correlation,
        method_distance_spearman={
            name: float(
                spearmanr(squareform(matrices["family_js_average"]), squareform(matrix)).statistic
            )
            for name, matrix in matrices.items()
        },
        input_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in input_paths},
    )
    (OUT / "clustering_review.json").write_text(json.dumps(summary, indent=2) + "\n")
    body = """<!doctype html><meta charset="utf-8"><title>Clustering review</title>
<style>body{font:16px system-ui;max-width:1500px;margin:30px}img{max-width:100%}
pre{white-space:pre-wrap}td,th{padding:8px;border:1px solid #ccc}
table{border-collapse:collapse}</style>
<h1>Clustering review and alternatives</h1>
<p>Corrected tree/heatmap row alignment. All methods below use the same local visits
with at least 10 qualified observations; UT is a reference pool, not an equal-duration visit.
This threshold is exploratory. Missing and low-count visits remain in the original lookup.</p>
<p>Average versus complete linkage tests merge-rule sensitivity. Hellinger compares square-root
frequencies. Jaccard compares family presence, ignoring multiplicity but remaining sensitive to
sampling depth. Exact-word JS retains rotations and inversion that family JS removes.
Tree cuts at 2, 3 and 4 groups are sensitivity choices, not discovered satellite counts.</p>
<p>Equal-count results use 300 random subsets of 10 accepted observations per visit without
replacement. Percentile ranges are subset sensitivity, not confidence intervals. This does not
correct receiver selection bias or establish independence of successive frames. The strict
pilot-quality comparison uses exactly the same visits under both quality filters.</p>
<p><a href="all_vs_all.html">Original inventory and raw-bit lookup</a> ·
<a href="clustering_sensitivity_pairs.csv">Pairwise sensitivity CSV</a> ·
<a href="clustering_review.json">Diagnostics and provenance</a></p>
<p>Method definitions: <a
href="https://docs.scipy.org/doc/scipy/reference/generated/scipy.cluster.hierarchy.linkage.html"
>SciPy linkage</a>; <a
href="https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.jensenshannon.html"
>Jensen–Shannon distance</a>.</p>"""
    body += (
        "<h2>Diagnostics</h2><p>Cophenetic correlation measures how well a tree represents "
        "its own distance matrix, not whether clusters are satellites.</p>"
    )
    body += "<pre>" + html.escape(json.dumps(summary, indent=2)) + "</pre>"
    for name in [
        "family_js_average",
        "balanced_mean_js",
        "coassignment_k3",
        "family_js_complete",
        "family_hellinger_average",
        "family_jaccard_average",
        "exact_js_average",
    ]:
        encoded = base64.b64encode((OUT / f"{name}.png").read_bytes()).decode()
        body += f'<h2>{html.escape(name)}</h2><img src="data:image/png;base64,{encoded}">'
    (OUT / "alternatives.html").write_text(body)
    print(json.dumps({k: v for k, v in summary.items() if k != "input_sha256"}, indent=2))


if __name__ == "__main__":
    main()
